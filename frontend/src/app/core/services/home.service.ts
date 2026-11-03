import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { forkJoin, Observable } from 'rxjs';
import { map } from 'rxjs/operators';
import { environment } from '../../../environments/environment';
import { OpenInvoice, Expense, CreditCard } from '../models';
import { invoiceForDate, isInvoiceClosed } from '../utils/invoice-cycle';
import { AnalyticsService, MonthlyAnalytics, CategoryAnalytics, ConsolidatedSummary } from './analytics.service';
import { SharedDebtService, SharedDebtHomeSummary } from './shared-debt.service';
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
  sharedDebts: SharedDebtHomeSummary[];
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
      consolidated:        this.analytics.consolidatedSummary(month, year, month, year),
      homeCharts:          this.analytics.homeCharts(month, year),
      evolution:           this.analytics.monthly(year),
      openInvoices:        this.http.get<OpenInvoice[]>(`${this.cardsBase}/open-invoices/?closing_month=${month}&closing_year=${year}`),
      sharedDebts:         this.sharedDebt.homeSummary(),
      recentExpenses:      this.expenseService.list({ month, year, page: 1, page_size: 5 }),
      allInstallmentExp:   this.expenseService.listAll(),
      cards:               this.http.get<CreditCard[]>(`${this.cardsBase}/`),
    }).pipe(
      map(({ consolidated, homeCharts, evolution, openInvoices,
             sharedDebts, recentExpenses, allInstallmentExp, cards }) => ({
        consolidated,
        evolution,
        openInvoices,
        sharedDebts,
        byCategory:        homeCharts.by_category,
        recentExpenses:    recentExpenses.results,
        installmentGroups: this._groupInstallments(allInstallmentExp, cards),
      }))
    );
  }

  private _groupInstallments(expenses: Expense[], cards: CreditCard[]): InstallmentGroup[] {
    const cardById = new Map(cards.map(card => [card.id, card]));
    const installmentExpenses = expenses.filter(e => /parcela\s+\d+\/\d+/i.test(e.description));
    const groups = new Map<string, { name: string; totalInstallments: number; paidInstallments: number; amountPerInstallment: number; totalAmount: number; remainingAmount: number; nextDate: string | null }>();

    for (const expense of installmentExpenses) {
      const match = expense.description.match(/^(.*?)[\s-]*parcela\s+(\d+)\/(\d+)/i);
      if (!match) continue;
      const name = match[1].trim() || expense.description;
      const part = Number(match[2]);
      const totalParts = Number(match[3]);
      const cardId = expense.credit_card_id ?? (expense as any).credit_card ?? null;
      const card = cardId ? cardById.get(cardId) : undefined;
      const key = `${name}-${totalParts}-${cardId ?? 'none'}`;
      const invoice = card ? invoiceForDate(expense.date, card.closing_day) : null;
      const closed = card ? isInvoiceClosed(expense.date, card.closing_day) : expense.date < new Date().toISOString().slice(0, 10);
      const displayDate = invoice?.displayDate ?? expense.date;
      const group = groups.get(key) ?? {
        name, totalInstallments: totalParts, paidInstallments: 0,
        amountPerInstallment: Math.abs(Number(expense.amount)), totalAmount: 0,
        remainingAmount: 0, nextDate: null,
      };
      group.totalAmount = Math.round((group.totalAmount + Math.abs(Number(expense.amount))) * 100) / 100;
      if (closed) group.paidInstallments = Math.max(group.paidInstallments, part);
      else {
        group.remainingAmount = Math.round((group.remainingAmount + Math.abs(Number(expense.amount))) * 100) / 100;
        if (!group.nextDate || displayDate < group.nextDate) group.nextDate = displayDate;
      }
      groups.set(key, group);
    }

    return Array.from(groups.values())
      .filter(group => group.paidInstallments < group.totalInstallments)
      .sort((a, b) => (a.nextDate ?? '').localeCompare(b.nextDate ?? ''));
  }
}
