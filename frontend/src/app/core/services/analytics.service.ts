import { Injectable, inject } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';

export interface MonthlyAnalytics {
  month: number;
  month_name: string;
  income: number;
  expenses: number;
  cash_expenses: number;
  card_expenses: number;
  shared_my_portion: number;
  balance: number;
  count: number;
}
export interface CategoryAnalytics {
  category_id: number; category_name: string; total: number; count: number; percentage: number;
}
export interface CardAnalytics {
  card_id: number; card_name: string; last_four_digits: string; total: number; count: number; percentage: number;
}
export interface DailyAnalytics {
  day: number; date: string; total: number; count: number;
}
export interface HomeCharts {
  month: number;
  year: number;
  summary: { income: number; expenses: number; balance: number; count: number };
  by_category: CategoryAnalytics[];
  daily: { day: number; total: number; count: number }[];
  weekly: { week: number; label: string; total: number }[];
}

export interface CardInvoiceDetail {
  card_id: number;
  card_name: string;
  last_four_digits: string;
  invoice_month: number;
  invoice_year: number;
  due_date: string;
  total: number;
  count: number;
}

export interface ConsolidatedSummary {
  month: number;
  year: number;
  income: number;
  cash_expenses: number;
  cash_count: number;
  card_invoices: number;
  card_invoices_count: number;
  card_invoices_detail: CardInvoiceDetail[];
  shared_my_portion: number;
  shared_count: number;
  total_expenses: number;
  balance: number;
}

@Injectable({ providedIn: 'root' })
export class AnalyticsService {
  private http = inject(HttpClient);
  private base = `${environment.apiBaseUrl}/api/expenses/expenses/analytics`;

  monthly(year?: number, paymentMethod?: string): Observable<MonthlyAnalytics[]> {
    let params = new HttpParams();
    if (year) params = params.set('year', year);
    if (paymentMethod) params = params.set('payment_method', paymentMethod);
    return this.http.get<MonthlyAnalytics[]>(`${this.base}/monthly/`, { params });
  }

  byCategory(month?: number, year?: number, paymentMethod?: string): Observable<CategoryAnalytics[]> {
    let params = new HttpParams();
    if (month) params = params.set('month', month);
    if (year) params = params.set('year', year);
    if (paymentMethod) params = params.set('payment_method', paymentMethod);
    return this.http.get<CategoryAnalytics[]>(`${this.base}/by-category/`, { params });
  }

  byCard(month?: number, year?: number): Observable<CardAnalytics[]> {
    let params = new HttpParams();
    if (month) params = params.set('month', month);
    if (year) params = params.set('year', year);
    return this.http.get<CardAnalytics[]>(`${this.base}/by-card/`, { params });
  }

  daily(month?: number, year?: number, paymentMethod?: string): Observable<DailyAnalytics[]> {
    let params = new HttpParams();
    if (month) params = params.set('month', month);
    if (year) params = params.set('year', year);
    if (paymentMethod) params = params.set('payment_method', paymentMethod);
    return this.http.get<DailyAnalytics[]>(`${this.base}/daily/`, { params });
  }


  consolidatedSummary(month?: number, year?: number): Observable<ConsolidatedSummary> {
    let params = new HttpParams();
    if (month) params = params.set('month', month);
    if (year)  params = params.set('year', year);
    return this.http.get<ConsolidatedSummary>(
      `${environment.apiBaseUrl}/api/expenses/expenses/consolidated-summary/`, { params }
    );
  }

  /** Endpoint otimizado — retorna todos os dados da tela Home em 1 request */
  homeCharts(month?: number, year?: number, paymentMethod?: string): Observable<HomeCharts> {
    let params = new HttpParams();
    if (month) params = params.set('month', month);
    if (year) params = params.set('year', year);
    if (paymentMethod) params = params.set('payment_method', paymentMethod);
    return this.http.get<HomeCharts>(
      `${environment.apiBaseUrl}/api/expenses/expenses/home-charts/`, { params }
    );
  }
}
