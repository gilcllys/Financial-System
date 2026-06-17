import { Injectable, inject } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';
import { Expense, CreateExpensePayload, ExpenseFilters } from '../models';

@Injectable({ providedIn: 'root' })
export class ExpenseService {
  private http = inject(HttpClient);
  private base = `${environment.apiBaseUrl}/api/expenses`;

  list(filters?: ExpenseFilters): Observable<Expense[]> {
    let params = new HttpParams();
    if (filters?.month) params = params.set('month', filters.month);
    if (filters?.year) params = params.set('year', filters.year);
    if (filters?.category_id) params = params.set('category_id', filters.category_id);
    if (filters?.payment_method) params = params.set('payment_method', filters.payment_method);
    if (filters?.credit_card_id) params = params.set('credit_card_id', filters.credit_card_id);
    return this.http.get<Expense[]>(`${this.base}/`, { params });
  }

  get(id: number): Observable<Expense> {
    return this.http.get<Expense>(`${this.base}/${id}/`);
  }

  create(payload: CreateExpensePayload): Observable<Expense> {
    return this.http.post<Expense>(`${this.base}/create-expense/`, payload);
  }

  update(id: number, payload: Partial<CreateExpensePayload>): Observable<Expense> {
    return this.http.put<Expense>(`${this.base}/${id}/`, payload);
  }

  delete(id: number): Observable<void> {
    return this.http.delete<void>(`${this.base}/${id}/`);
  }
}
