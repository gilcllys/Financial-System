// src/app/services/base.service.ts
import { Injectable, inject } from '@angular/core';
import type { HttpParams } from '@angular/common/http';
import { HttpClient, HttpHeaders } from '@angular/common/http';
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
    responseType?: 'json' | 'blob';
  } = {};

  private http = inject(HttpClient);
  /**
   * Método para obter dados de uma API.
   * @param endpoint - O endpoint da API.
   * @returns Um Observable com os dados obtidos.
   */
  protected get<T>(endpoint: string): Observable<T> {
    this.httpOptions.headers = new HttpHeaders({
      Authorization: `Bearer ${localStorage.getItem('token')}`,
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
    this.httpOptions.headers = new HttpHeaders({
      Authorization: `Bearer ${localStorage.getItem('token')}`,
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
    this.httpOptions.headers = new HttpHeaders({
      Authorization: `Bearer ${localStorage.getItem('token')}`,
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
    this.httpOptions.headers = new HttpHeaders({
      Authorization: `Bearer ${localStorage.getItem('token')}`,
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
