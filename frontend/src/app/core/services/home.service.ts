import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { forkJoin, Observable } from 'rxjs';
import { map } from 'rxjs/operators';
import { environment } from '../../../environments/environment';
import { OpenInvoice, Expense } from '../models';
import { AnalyticsService, MonthlyAnalytics, CategoryAnalytics } from './analytics.service';
import { SharedDebtService, SharedDebtGroup } from './shared-debt.service';
import { ExpenseService } from './expense.service';

export interface HomeSummary {
  summary: { income: number; expenses: number; balance: number; count: number };
  evolution: MonthlyAnalytics[];
  openInvoices: OpenInvoice[];
  sharedDebts: SharedDebtGroup[];
  byCategory: CategoryAnalytics[];
  recentExpenses: Expense[];
}

@Injectable({ providedIn: 'root' })
export class HomeService {
  private http = inject(HttpClient);
  private analytics = inject(AnalyticsService);
  private sharedDebt = inject(SharedDebtService);
  private expenseService = inject(ExpenseService);

  private cardsBase = `${environment.apiBaseUrl}/api/cards/credit-cards`;

  load(month: number, year: number): Observable<HomeSummary> {
    return forkJoin({
      homeCharts: this.analytics.homeCharts(month, year),
      evolution:  this.analytics.monthly(year),
      openInvoices: this.http.get<OpenInvoice[]>(`${this.cardsBase}/open-invoices/`),
      sharedDebts:  this.sharedDebt.listGroups(),
      recentExpenses: this.expenseService.list({ month, year, page: 1, page_size: 5 }),
    }).pipe(
      map(({ homeCharts, evolution, openInvoices, sharedDebts, recentExpenses }) => ({
        summary: homeCharts.summary,
        evolution,
        openInvoices,
        sharedDebts,
        byCategory: homeCharts.by_category,
        recentExpenses: recentExpenses.results,
      }))
    );
  }
}
