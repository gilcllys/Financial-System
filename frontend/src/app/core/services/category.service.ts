import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';
import { ExpenseCategory } from '../models';

@Injectable({ providedIn: 'root' })
export class CategoryService {
  private http = inject(HttpClient);
  private base = `${environment.apiBaseUrl}/api/catalog/categories`;

  list(): Observable<ExpenseCategory[]> {
    return this.http.get<ExpenseCategory[]>(`${this.base}/`);
  }

  get(id: number): Observable<ExpenseCategory> {
    return this.http.get<ExpenseCategory>(`${this.base}/${id}/`);
  }

  create(payload: Pick<ExpenseCategory, 'name' | 'description'>): Observable<ExpenseCategory> {
    return this.http.post<ExpenseCategory>(`${this.base}/`, payload);
  }

  update(id: number, payload: Partial<ExpenseCategory>): Observable<ExpenseCategory> {
    return this.http.put<ExpenseCategory>(`${this.base}/${id}/`, payload);
  }

  delete(id: number): Observable<void> {
    return this.http.delete<void>(`${this.base}/${id}/`);
  }
}
