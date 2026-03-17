// src/app/services/base.service.ts
import { isPlatformBrowser } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import { Injectable, PLATFORM_ID, inject } from '@angular/core';
import type { Observable } from 'rxjs';
import { throwError } from 'rxjs';
import { catchError } from 'rxjs/operators';
import { API_BASE_URL } from '../utils/constants';

@Injectable({
  providedIn: 'root',
})
export class BaseService {
  private http = inject(HttpClient);
  private platformId = inject(PLATFORM_ID);
  protected isBrowser = isPlatformBrowser(this.platformId);

  protected get<T>(endpoint: string): Observable<T> {
    return this.http
      .get<T>(`${API_BASE_URL}${endpoint}`)
      .pipe(catchError((error) => this.handleError(error)));
  }

  protected post<T, B = T>(endpoint: string, body: B): Observable<T> {
    return this.http
      .post<T>(`${API_BASE_URL}${endpoint}`, body)
      .pipe(catchError((error) => this.handleError(error)));
  }

  protected put<T, B = T>(endpoint: string, body: B): Observable<T> {
    return this.http
      .put<T>(`${API_BASE_URL}${endpoint}`, body)
      .pipe(catchError((error) => this.handleError(error)));
  }

  protected delete<T>(endpoint: string): Observable<T> {
    return this.http
      .delete<T>(`${API_BASE_URL}${endpoint}`)
      .pipe(catchError((error) => this.handleError(error)));
  }

  private handleError(error: unknown): Observable<never> {
    console.error('Error:', error);
    return throwError(() => error);
  }
}
