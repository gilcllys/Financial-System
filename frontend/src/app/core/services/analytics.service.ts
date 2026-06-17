import { Injectable, inject } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';

export interface MonthlyAnalytics {
  month: number;
  month_name: string;
  income: number;
  expenses: number;
  balance: number;
  count: number;
}

export interface CategoryAnalytics {
  category_id: number;
  category_name: string;
  total: number;
  count: number;
  percentage: number;
}

export interface CardAnalytics {
  card_id: number;
  card_name: string;
  last_four_digits: string;
  total: number;
  count: number;
  percentage: number;
}

export interface DailyAnalytics {
  day: number;
  date: string;
  total: number;
  count: number;
}

@Injectable({ providedIn: 'root' })
export class AnalyticsService {
  private http = inject(HttpClient);
  private base = `${environment.apiBaseUrl}/api/expenses/expenses/analytics`;

  monthly(year?: number): Observable<MonthlyAnalytics[]> {
    let params = new HttpParams();
    if (year) params = params.set('year', year);
    return this.http.get<MonthlyAnalytics[]>(`${this.base}/monthly/`, { params });
  }

  byCategory(month?: number, year?: number): Observable<CategoryAnalytics[]> {
    let params = new HttpParams();
    if (month) params = params.set('month', month);
    if (year) params = params.set('year', year);
    return this.http.get<CategoryAnalytics[]>(`${this.base}/by-category/`, { params });
  }

  byCard(month?: number, year?: number): Observable<CardAnalytics[]> {
    let params = new HttpParams();
    if (month) params = params.set('month', month);
    if (year) params = params.set('year', year);
    return this.http.get<CardAnalytics[]>(`${this.base}/by-card/`, { params });
  }

  daily(month?: number, year?: number): Observable<DailyAnalytics[]> {
    let params = new HttpParams();
    if (month) params = params.set('month', month);
    if (year) params = params.set('year', year);
    return this.http.get<DailyAnalytics[]>(`${this.base}/daily/`, { params });
  }
}
