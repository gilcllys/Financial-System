import { Injectable, inject } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';
import { map } from 'rxjs/operators';
import { environment } from '../../../environments/environment';
import { Expense, CreateExpensePayload, ExpenseFilters, PaginatedResponse } from '../models';

function normalize(raw: any): Expense {
  return {
    ...raw,
    category_id: raw.category_id ?? raw.category,
    amount: parseFloat(raw.amount),
  };
}

@Injectable({ providedIn: 'root' })
export class ExpenseService {
  private http = inject(HttpClient);
  private base = `${environment.apiBaseUrl}/api/expenses/expenses`;

  list(filters?: ExpenseFilters & { page?: number; page_size?: number; search?: string }): Observable<PaginatedResponse<Expense>> {
    let params = new HttpParams();
    if (filters?.month)          params = params.set('month', filters.month);
    if (filters?.year)           params = params.set('year', filters.year);
    if (filters?.category_id)    params = params.set('category_id', filters.category_id);
    if (filters?.payment_method) params = params.set('payment_method', filters.payment_method);
    if (filters?.search)         params = params.set('search', filters.search);
    if (filters?.page)           params = params.set('page', filters.page);
    if (filters?.page_size)      params = params.set('page_size', filters.page_size);

    return this.http.get<PaginatedResponse<any>>(`${this.base}/`, { params }).pipe(
      map(res => ({ ...res, results: res.results.map(normalize) }))
    );
  }

  listByCard(cardId: number): Observable<Expense[]> {
    return this.http.get<any[]>(`${this.base}/per-credit-card/${cardId}/`).pipe(
      map(list => list.map(normalize))
    );
  }

  get(id: number): Observable<Expense> {
    return this.http.get<any>(`${this.base}/${id}/`).pipe(map(normalize));
  }

  create(payload: CreateExpensePayload): Observable<any> {
    return this.http.post<any>(`${this.base}/create-expense/`, payload);
  }

  update(id: number, payload: Partial<CreateExpensePayload>): Observable<Expense> {
    return this.http.put<any>(`${this.base}/${id}/`, payload).pipe(map(normalize));
  }

  delete(id: number): Observable<void> {
    return this.http.delete<void>(`${this.base}/${id}/`);
  }
}
