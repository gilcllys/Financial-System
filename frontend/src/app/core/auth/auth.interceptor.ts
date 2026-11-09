import { HttpInterceptorFn, HttpRequest, HttpHandlerFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { finalize } from 'rxjs';
import { AuthService } from './auth.service';
import { RouteLoadingService } from '../services/route-loading.service';
import { environment } from '../../../environments/environment';

export const authInterceptor: HttpInterceptorFn = (
  req: HttpRequest<unknown>,
  next: HttpHandlerFn
) => {
  const auth = inject(AuthService);
  const routeLoading = inject(RouteLoadingService);
  const token = auth.token;
  const navigationId = req.url.startsWith(environment.apiBaseUrl)
    ? routeLoading.requestStarted()
    : null;

  let request = req;
  if (token) {
    request = req.clone({
      headers: req.headers.set('Authorization', `Bearer ${token}`),
    });
  }

  return next(request).pipe(finalize(() => routeLoading.requestFinished(navigationId)));
};
