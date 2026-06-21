import { Injectable, inject } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';
import { map } from 'rxjs/operators';
import { environment } from '../../../environments/environment';
import { CreditCard, CreateCreditCardPayload, Invoice, InvoiceExpensesResponse } from '../models';

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

  getInvoiceExpenses(
    id: number,
    invoiceMonth: number,
    invoiceYear: number,
    categoryId?: number
  ): Observable<InvoiceExpensesResponse> {
    let params = new HttpParams()
      .set('invoice_month', invoiceMonth)
      .set('invoice_year', invoiceYear);
    if (categoryId !== undefined && categoryId !== null) {
      params = params.set('category_id', categoryId);
    }
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
