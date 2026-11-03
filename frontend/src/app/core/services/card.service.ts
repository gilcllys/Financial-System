import { Injectable, inject } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';
import { map } from 'rxjs/operators';
import { environment } from '../../../environments/environment';
import { CreditCard, CreateCreditCardPayload, Expense, Invoice, InvoiceExpensesResponse } from '../models';
import { SharedDebtEntry } from './shared-debt.service';

export interface InvoiceViewResponse {
  card: CreditCard;
  invoices: Invoice[];
  selected_invoice: Invoice;
  invoice_data: InvoiceExpensesResponse;
  chart_data: InvoiceExpensesResponse;
  shared_entries: SharedDebtEntry[];
  categories: import('../models').ExpenseCategory[];
  annual_invoice_totals: number[];
}

@Injectable({ providedIn: 'root' })
export class CardService {
  private http = inject(HttpClient);
  private base = `${environment.apiBaseUrl}/api/cards/credit-cards`;

  list(): Observable<CreditCard[]> {
    return this.http.get<CreditCard[]>(`${this.base}/`);
  }

  get(id: number): Observable<CreditCard> {
    return this.http.get<CreditCard>(`${this.base}/${id}/`);
  }

  create(payload: CreateCreditCardPayload): Observable<CreditCard> {
    return this.http.post<CreditCard>(`${this.base}/`, payload);
  }

  update(id: number, payload: Partial<CreateCreditCardPayload>): Observable<CreditCard> {
    return this.http.put<CreditCard>(`${this.base}/${id}/`, payload);
  }

  delete(id: number): Observable<void> {
    return this.http.delete<void>(`${this.base}/${id}/`);
  }

  getInvoices(id: number, count = 13): Observable<Invoice[]> {
    return this.http.get<Invoice[]>(`${this.base}/${id}/invoices/`, {
      params: { count: count.toString() }
    });
  }

  getInvoiceView(
    id: number,
    invoice?: Pick<Invoice, 'invoice_month' | 'invoice_year'>,
    filters: { category_id?: number | null; page?: number; page_size?: number; search?: string } = {},
  ): Observable<InvoiceViewResponse> {
    let params = new HttpParams();
    if (invoice) params = params.set('invoice_month', invoice.invoice_month).set('invoice_year', invoice.invoice_year);
    if (filters.category_id != null) params = params.set('category_id', filters.category_id);
    if (filters.page != null) params = params.set('page', filters.page);
    if (filters.page_size != null) params = params.set('page_size', filters.page_size);
    if (filters.search?.trim()) params = params.set('search', filters.search.trim());
    return this.http.get<InvoiceViewResponse>(`${this.base}/${id}/invoice-view/`, { params }).pipe(
      map(view => ({
        ...view,
        invoice_data: { ...view.invoice_data, expenses: view.invoice_data.expenses.map(e => ({ ...e, amount: Number(e.amount) })) },
        chart_data: { ...view.chart_data, expenses: view.chart_data.expenses.map(e => ({ ...e, amount: Number(e.amount) })) },
      }))
    );
  }

  getInvoiceExpenses(
    id: number,
    invoiceMonth: number,
    invoiceYear: number,
    categoryId?: number,
    page = 1,
    pageSize = 20,
    search?: string,
  ): Observable<InvoiceExpensesResponse> {
    let params = new HttpParams()
      .set('invoice_month', invoiceMonth)
      .set('invoice_year', invoiceYear)
      .set('page', page)
      .set('page_size', pageSize);
    if (categoryId !== undefined && categoryId !== null) {
      params = params.set('category_id', categoryId);
    }
    if (search) params = params.set('search', search);
    return this.http.get<InvoiceExpensesResponse>(
      `${this.base}/${id}/invoice-expenses/`, { params }
    ).pipe(
      map(res => ({
        ...res,
        expenses: res.expenses.map(e => ({ ...e, amount: parseFloat(e.amount as any) }))
      }))
    );
  }

}
