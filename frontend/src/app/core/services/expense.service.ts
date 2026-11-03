import { Injectable, inject } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable, forkJoin, of } from 'rxjs';
import { switchMap } from 'rxjs/operators';
import { map } from 'rxjs/operators';
import { environment } from '../../../environments/environment';
import { Expense, CreateExpensePayload, ExpenseFilters, PaginatedResponse } from '../models';

function normalize(raw: any): Expense {
  return {
    ...raw,
    category_id: raw.category_id ?? raw.category,
    credit_card_id: raw.credit_card_id ?? raw.credit_card ?? null,
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


export interface HistoryEntry {
  id: number;
  type: 'individual' | 'shared';
  description: string;
  date: string;
  amount: number;
  category_id: number | null;
  category_name: string;
  payment_method: 'dinheiro' | 'cartao';
  credit_card_id: number | null;
  card_name: string | null;
  group_id: number | null;
  group_name: string | null;
  paid_by_name: string | null;
  installment_number: number | null;
  total_installments: number | null;
  participant_count?: number;
  own_portion?: number;
  is_recurring: boolean;
}

export interface HistoryTotals {
  count: number;
  income: number;
  expenses: number;
  net: number;
}

export interface HistoryResponse extends PaginatedResponse<HistoryEntry> {
  totals: HistoryTotals;
}

export interface GenerateMonthResult {
  created: string[];
  skipped: string[];
  /** Templates ignorados por configuracao invalida (ex: cartao sem cartao). */
  skipped_invalid?: string[];
}

@Injectable({ providedIn: 'root' })
export class ExpenseService {
  private http = inject(HttpClient);
  private base = `${environment.apiBaseUrl}/api/expenses/expenses`;

  list(filters?: ExpenseFilters & { category_key?: string; page?: number; page_size?: number }): Observable<PaginatedResponse<Expense>> {
    let params = new HttpParams();
    if (filters?.month)          params = params.set('month', filters.month);
    if (filters?.year)           params = params.set('year', filters.year);
    if (filters?.category_id)    params = params.set('category_id', filters.category_id);
    if (filters?.category_key)   params = params.set('category_key', filters.category_key);
    if (filters?.payment_method) params = params.set('payment_method', filters.payment_method);
    if (filters?.credit_card_id) params = params.set('credit_card_id', filters.credit_card_id);
    if (filters?.start_date)     params = params.set('start_date', filters.start_date);
    if (filters?.end_date)       params = params.set('end_date', filters.end_date);
    if (filters?.search)         params = params.set('search', filters.search);
    if (filters?.page)           params = params.set('page', filters.page);
    if (filters?.page_size)      params = params.set('page_size', filters.page_size);

    return this.http.get<PaginatedResponse<any>>(`${this.base}/`, { params }).pipe(
      map(res => ({ ...res, results: res.results.map(normalize) }))
    );
  }

  history(filters: Record<string, string | number | boolean | null | undefined> = {}): Observable<HistoryResponse> {
    let params = new HttpParams();
    for (const [key, value] of Object.entries(filters)) {
      if (value !== undefined && value !== null && value !== '') params = params.set(key, String(value));
    }
    return this.http.get<HistoryResponse>(`${this.base}/history/`, { params });
  }

  downloadHistoryCsv(filters: Record<string, string | number | boolean | null | undefined> = {}): Observable<Blob> {
    let params = new HttpParams().set('export', 'csv');
    for (const [key, value] of Object.entries(filters)) {
      if (value !== undefined && value !== null && value !== '') params = params.set(key, String(value));
    }
    return this.http.get(`${this.base}/history/`, { params, responseType: 'blob' });
  }

  updateHistoryCategories(expenseIds: number[], categoryId: number): Observable<{ updated: number }> {
    return this.http.post<{ updated: number }>(`${this.base}/history/bulk-category/`, {
      expense_ids: expenseIds, category_id: categoryId,
    });
  }

  listAll(filters?: ExpenseFilters & { category_key?: string }): Observable<Expense[]> {
    const pageSize = 100;
    return this.list({ ...filters, page: 1, page_size: pageSize }).pipe(
      switchMap(first => {
        const pageCount = Math.ceil(first.count / pageSize);
        if (pageCount <= 1) return of(first.results);
        const requests = Array.from({ length: pageCount - 1 }, (_, index) =>
          this.list({ ...filters, page: index + 2, page_size: pageSize })
        );
        return forkJoin(requests).pipe(
          map(pages => [first, ...pages].flatMap(page => page.results))
        );
      })
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

  deleteInstallments(descriptionPrefix: string, totalInstallments: number, expenseIds?: number[]): Observable<{ deleted: number }> {
    return this.http.post<{ deleted: number }>(`${this.base}/delete-installments/`, {
      description_prefix: descriptionPrefix,
      total_installments: totalInstallments,
      ...(expenseIds ? { expense_ids: expenseIds } : {}),
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

  updateRecurringTemplate(id: number, payload: {
    description: string; amount: number; day_of_month?: number;
    payment_method?: string; credit_card_id?: number | null; category_id?: number | null;
  }): Observable<RecurringExpenseTemplate> {
    return this.http.put<RecurringExpenseTemplate>(`${this.base}/recurring-templates/${id}/`, payload);
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
