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


export interface RecurringExpenseTemplate {
  id: number;
  description: string;
  amount: number;
  day_of_month: number;
  payment_method: 'dinheiro' | 'cartao';
  credit_card: number | null;
  credit_card_name: string | null;
  category: number | null;
  category_name: string | null;
  is_active: boolean;
  created_at: string;
}

export interface GenerateMonthResult {
  created: string[];
  skipped: string[];
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

  bulkCreate(items: CreateExpensePayload[]): Observable<{ success: boolean; created: number; message: string }> {
    return this.http.post<any>(`${this.base}/bulk-create/`, { items });
  }

  downloadTemplate(): Observable<Blob> {
    return this.http.get(`${this.base}/import-template/`, { responseType: 'blob' });
  }

  importExcel(file: File): Observable<any> {
    const fd = new FormData();
    fd.append('file', file);
    return this.http.post<any>(`${this.base}/import-excel/`, fd);
  }

  deleteInstallments(descriptionPrefix: string, totalInstallments: number): Observable<{ deleted: number }> {
    return this.http.post<{ deleted: number }>(`${this.base}/delete-installments/`, {
      description_prefix: descriptionPrefix,
      total_installments: totalInstallments,
    });
  }
  listRecurringTemplates(): Observable<RecurringExpenseTemplate[]> {
    return this.http.get<RecurringExpenseTemplate[]>(`${this.base}/recurring-templates/`);
  }

  createRecurringTemplate(payload: {
    description: string; amount: number; day_of_month?: number;
    payment_method?: string; credit_card_id?: number | null; category_id?: number | null;
  }): Observable<RecurringExpenseTemplate> {
    return this.http.post<RecurringExpenseTemplate>(`${this.base}/recurring-templates/`, payload);
  }

  deleteRecurringTemplate(id: number): Observable<void> {
    return this.http.delete<void>(`${this.base}/recurring-templates/${id}/`);
  }

  toggleRecurringTemplate(id: number): Observable<RecurringExpenseTemplate> {
    return this.http.patch<RecurringExpenseTemplate>(`${this.base}/recurring-templates/${id}/`, {});
  }

  generateMonthRecurring(month: number, year: number): Observable<GenerateMonthResult> {
    return this.http.post<GenerateMonthResult>(
      `${this.base}/recurring-templates/generate-month/`, { month, year });
  }

}
