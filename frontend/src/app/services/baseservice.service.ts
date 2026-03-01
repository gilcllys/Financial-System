// src/app/services/base.service.ts
import { isPlatformBrowser } from '@angular/common';
import type { HttpParams } from '@angular/common/http';
import { HttpClient, HttpHeaders } from '@angular/common/http';
import { Injectable, PLATFORM_ID, inject } from '@angular/core';
import type { Observable } from 'rxjs';
import { throwError } from 'rxjs';
import { catchError } from 'rxjs/operators';
import { API_BASE_URL } from '../utils/constants';

@Injectable({
  providedIn: 'root',
})
export class BaseService {
  protected httpOptions: {
    headers?: HttpHeaders;
    params?: HttpParams;
  } = {};

  private http = inject(HttpClient);
  private platformId = inject(PLATFORM_ID);
  private isBrowser = isPlatformBrowser(this.platformId);

  /**
   * Obtém o token de autenticação do localStorage
   */
  private getToken(): string | null {
    if (!this.isBrowser) {
      return null;
    }
    return localStorage.getItem('access_token');
  }

  /**
   * Método para obter dados de uma API.
   * @param endpoint - O endpoint da API.
   * @returns Um Observable com os dados obtidos.
   */
  protected get<T>(endpoint: string): Observable<T> {
    const token = this.getToken();
    this.httpOptions.headers = new HttpHeaders({
      Authorization: `Bearer ${token || ''}`,
    });
    return this.http
      .get<T>(`${API_BASE_URL}${endpoint}`, this.httpOptions)
      .pipe(catchError((error) => this.handleError(error)));
  }

  /**
   * Método para enviar dados para uma API.
   * @param endpoint - O endpoint da API.
   * @param body - Os dados a serem enviados.
   * @returns Um Observable com os dados obtidos.
   */
  protected post<T, B = T>(endpoint: string, body: B): Observable<T> {
    const token = this.getToken();
    this.httpOptions.headers = new HttpHeaders({
      Authorization: `Bearer ${token || ''}`,
    });
    return this.http
      .post<T>(`${API_BASE_URL}${endpoint}`, body, this.httpOptions)
      .pipe(catchError((error) => this.handleError(error)));
  }

  /**
   * Método para atualizar dados em uma API.
   * @param endpoint - O endpoint da API.
   * @param body - Os dados a serem atualizados.
   * @returns Um Observable com os dados obtidos.
   */
  protected put<T, B = T>(endpoint: string, body: B): Observable<T> {
    const token = this.getToken();
    this.httpOptions.headers = new HttpHeaders({
      Authorization: `Bearer ${token || ''}`,
    });
    return this.http
      .put<T>(`${API_BASE_URL}${endpoint}`, body, this.httpOptions)
      .pipe(catchError((error) => this.handleError(error)));
  }

  /**
   * Método para remover dados de uma API.
   * @param endpoint - O endpoint da API.
   * @returns Um Observable com os dados obtidos.
   */
  protected delete<T>(endpoint: string): Observable<T> {
    const token = this.getToken();
    this.httpOptions.headers = new HttpHeaders({
      Authorization: `Bearer ${token || ''}`,
    });
    return this.http
      .delete<T>(`${API_BASE_URL}${endpoint}`, this.httpOptions)
      .pipe(catchError((error) => this.handleError(error)));
  }

  /**
   * Método para lidar com erros de requisição HTTP.
   * @param error - O objeto de erro.
   * @returns Um Observable de erro.
   */
  private handleError(error: unknown): Observable<never> {
    console.error('Error:', error);
    alert(`An error occurred: ${(error as Error)?.message ?? 'Unknown error'}`);
    return throwError(() => error);
  }
}
