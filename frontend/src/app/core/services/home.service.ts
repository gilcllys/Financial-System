import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { forkJoin, Observable } from 'rxjs';
import { map } from 'rxjs/operators';
import { environment } from '../../../environments/environment';
import { OpenInvoice, Expense } from '../models';
import { AnalyticsService, MonthlyAnalytics, CategoryAnalytics, ConsolidatedSummary } from './analytics.service';
import { SharedDebtService, SharedDebtGroup } from './shared-debt.service';
import { ExpenseService } from './expense.service';

export interface InstallmentGroup {
  name: string;
  totalInstallments: number;
  paidInstallments: number;
  amountPerInstallment: number;
  totalAmount: number;
  remainingAmount: number;
  nextDate: string | null;
}

export interface HomeSummary {
  consolidated: ConsolidatedSummary;
  evolution: MonthlyAnalytics[];
  openInvoices: OpenInvoice[];
  sharedDebts: SharedDebtGroup[];
  byCategory: CategoryAnalytics[];
  recentExpenses: Expense[];
  installmentGroups: InstallmentGroup[];
}

@Injectable({ providedIn: 'root' })
export class HomeService {
  private http           = inject(HttpClient);
  private analytics      = inject(AnalyticsService);
  private sharedDebt     = inject(SharedDebtService);
  private expenseService = inject(ExpenseService);

  private cardsBase = `${environment.apiBaseUrl}/api/cards/credit-cards`;

  load(month: number, year: number): Observable<HomeSummary> {
    return forkJoin({
      consolidated:        this.analytics.consolidatedSummary(month, year),
      homeCharts:          this.analytics.homeCharts(month, year),
      evolution:           this.analytics.monthly(year),
      openInvoices:        this.http.get<OpenInvoice[]>(`${this.cardsBase}/open-invoices/`),
      sharedDebts:         this.sharedDebt.listGroups(),
      recentExpenses:      this.expenseService.list({ month, year, page: 1, page_size: 5 }),
      allInstallmentExp:   this.expenseService.list({ page_size: 500 }),
    }).pipe(
      map(({ consolidated, homeCharts, evolution, openInvoices,
             sharedDebts, recentExpenses, allInstallmentExp }) => ({
        consolidated,
        evolution,
        openInvoices,
        sharedDebts,
        byCategory:        homeCharts.by_category,
        recentExpenses:    recentExpenses.results,
        installmentGroups: this._groupInstallments(allInstallmentExp.results),
      }))
    );
  }

  private _groupInstallments(expenses: Expense[]): InstallmentGroup[] {
    const today = new Date();
    today.setHours(0, 0, 0, 0);

    const installmentExpenses = expenses.filter(e =>
      /parcela\s+\d+\/\d+/i.test(e.description)
    );

    const groupMap = new Map<string, {
      name: string; totalInstallments: number; paidInstallments: number;
      amountPerInstallment: number; nextDate: string | null; expenses: Expense[];
    }>();

    for (const expense of installmentExpenses) {
      const match = expense.description.match(/^(.*?)[\s-]*parcela\s+(\d+)\/(\d+)/i);
      if (!match) continue;

      const baseName   = match[1].trim() || expense.description;
      const currentPart = +match[2];
      const totalParts  = +match[3];
      const key         = `${baseName}-${totalParts}`;
      const expDate     = new Date(expense.date + 'T00:00:00');
      const isPaid      = expDate <= today;

      const existing = groupMap.get(key);
      if (existing) {
        existing.expenses.push(expense);
        if (isPaid && currentPart > existing.paidInstallments) {
          existing.paidInstallments = currentPart;
        }
        // track next unpaid installment date
        if (!isPaid) {
          if (!existing.nextDate || expense.date < existing.nextDate) {
            existing.nextDate = expense.date;
          }
        }
      } else {
        groupMap.set(key, {
          name: baseName,
          totalInstallments: totalParts,
          paidInstallments: isPaid ? currentPart : 0,
          amountPerInstallment: Math.abs(expense.amount),
          nextDate: !isPaid ? expense.date : null,
          expenses: [expense],
        });
      }
    }

    const remaining = (g: { amountPerInstallment: number; paidInstallments: number; totalInstallments: number }) =>
      Math.round((g.totalInstallments - g.paidInstallments) * g.amountPerInstallment * 100) / 100;

    return Array.from(groupMap.values())
      .filter(g => g.paidInstallments < g.totalInstallments)   // apenas ativas
      .sort((a, b) => (a.nextDate ?? '').localeCompare(b.nextDate ?? ''))
      .map(g => ({
        name:                 g.name,
        totalInstallments:    g.totalInstallments,
        paidInstallments:     g.paidInstallments,
        amountPerInstallment: g.amountPerInstallment,
        totalAmount:          Math.round(g.totalInstallments * g.amountPerInstallment * 100) / 100,
        remainingAmount:      remaining(g),
        nextDate:             g.nextDate,
      }));
  }
}
