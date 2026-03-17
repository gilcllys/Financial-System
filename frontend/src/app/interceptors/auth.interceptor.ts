import { isPlatformBrowser } from '@angular/common';
import type {
    HttpErrorResponse,
    HttpHandlerFn,
    HttpInterceptorFn,
    HttpRequest,
} from '@angular/common/http';
import { HttpClient } from '@angular/common/http';
import { inject, PLATFORM_ID } from '@angular/core';
import { Router } from '@angular/router';
import { BehaviorSubject, throwError } from 'rxjs';
import { catchError, filter, switchMap, take } from 'rxjs/operators';
import { API_BASE_URL } from '../utils/constants';

let isRefreshing = false;
const refreshTokenSubject = new BehaviorSubject<string | null>(null);

export const authInterceptor: HttpInterceptorFn = (
  req: HttpRequest<unknown>,
  next: HttpHandlerFn,
) => {
  const platformId = inject(PLATFORM_ID);
  const router = inject(Router);
  const http = inject(HttpClient);
  const isBrowser = isPlatformBrowser(platformId);

  // Não interceptar requisições de login, register ou refresh
  if (
    req.url.includes('/api/login/') ||
    req.url.includes('/api/register/') ||
    req.url.includes('/api/token/refresh/')
  ) {
    return next(req);
  }

  // Adicionar token se disponível
  const token = isBrowser ? localStorage.getItem('access_token') : null;
  const authReq = token
    ? req.clone({
        setHeaders: { Authorization: `Bearer ${token}` },
      })
    : req;

  return next(authReq).pipe(
    catchError((error: HttpErrorResponse) => {
      if (error.status === 401 && isBrowser) {
        return handleUnauthorized(authReq, next, http, router, isBrowser);
      }
      return throwError(() => error);
    }),
  );
};

function handleUnauthorized(
  req: HttpRequest<unknown>,
  next: HttpHandlerFn,
  http: HttpClient,
  router: Router,
  isBrowser: boolean,
) {
  if (!isRefreshing) {
    isRefreshing = true;
    refreshTokenSubject.next(null);

    const refreshToken = isBrowser
      ? localStorage.getItem('refresh_token')
      : null;

    if (!refreshToken) {
      isRefreshing = false;
      doLogout(router, isBrowser);
      return throwError(() => new Error('No refresh token'));
    }

    return http
      .post<{ access: string }>(`${API_BASE_URL}/api/token/refresh/`, {
        refresh: refreshToken,
      })
      .pipe(
        switchMap((response) => {
          isRefreshing = false;
          if (isBrowser) {
            localStorage.setItem('access_token', response.access);
          }
          refreshTokenSubject.next(response.access);

          // Repetir a requisição original com o novo token
          const retryReq = req.clone({
            setHeaders: { Authorization: `Bearer ${response.access}` },
          });
          return next(retryReq);
        }),
        catchError((refreshError) => {
          isRefreshing = false;
          doLogout(router, isBrowser);
          return throwError(() => refreshError);
        }),
      );
  }

  // Se já está fazendo refresh, esperar o novo token
  return refreshTokenSubject.pipe(
    filter((token) => token !== null),
    take(1),
    switchMap((token) => {
      const retryReq = req.clone({
        setHeaders: { Authorization: `Bearer ${token}` },
      });
      return next(retryReq);
    }),
  );
}

function doLogout(router: Router, isBrowser: boolean) {
  if (isBrowser) {
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    localStorage.removeItem('user');
  }
  router.navigate(['/']);
}
