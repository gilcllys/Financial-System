import { Injectable, inject } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable, map } from 'rxjs';
import { environment } from '../../../environments/environment';
import { OpenInvoice, Expense, CreditCard, ExpenseCategory } from '../models';
import { invoiceForDate, isInvoiceClosed } from '../utils/invoice-cycle';
import { MonthlyAnalytics, CategoryAnalytics, ConsolidatedSummary } from './analytics.service';
import { PaginatedResponse, SharedDebtHomeSummary } from './shared-debt.service';
import { RecurringExpenseTemplate } from './expense.service';

export interface InstallmentGroup {
  name: string;
  totalInstallments: number;
  closedInstallments: number;
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
  expensePage: PaginatedResponse<Expense>;
  installmentGroups: InstallmentGroup[];
  categories: ExpenseCategory[];
  recurringTemplates: RecurringExpenseTemplate[];
  generatedRecurringTemplateIds: number[];
}

interface HomeDashboardPayload {
  consolidated: ConsolidatedSummary;
  home_charts: { by_category: CategoryAnalytics[] };
  evolution: MonthlyAnalytics[];
  open_invoices: OpenInvoice[];
  shared_debts: SharedDebtHomeSummary[];
  expenses: PaginatedResponse<Expense>;
  installment_expenses: Expense[];
  cards: CreditCard[];
  categories: ExpenseCategory[];
  recurring_templates: RecurringExpenseTemplate[];
  generated_recurring_template_ids: number[];
}

@Injectable({ providedIn: 'root' })
export class HomeService {
  private http = inject(HttpClient);

  load(month: number, year: number): Observable<HomeSummary> {
    const params = new HttpParams().set('month', month).set('year', year);
    return this.http.get<HomeDashboardPayload>(`${environment.apiBaseUrl}/api/dashboard/home/`, { params }).pipe(
      map(data => ({
        consolidated: data.consolidated,
        evolution: data.evolution,
        openInvoices: data.open_invoices,
        sharedDebts: data.shared_debts,
        byCategory: data.home_charts.by_category,
        recentExpenses: data.expenses.results.slice(0, 5),
        expensePage: data.expenses,
        installmentGroups: this.groupInstallments(data.installment_expenses, data.cards),
        categories: data.categories,
        recurringTemplates: data.recurring_templates,
        generatedRecurringTemplateIds: data.generated_recurring_template_ids ?? [],
      }))
    );
  }

  private groupInstallments(expenses: Expense[], cards: CreditCard[]): InstallmentGroup[] {
    const cardById = new Map(cards.map(card => [card.id, card]));
    const groups = new Map<string, InstallmentGroup>();

    for (const expense of expenses) {
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
      const amount = Math.abs(Number(expense.amount));
      const group = groups.get(key) ?? {
        name, totalInstallments: totalParts, closedInstallments: 0,
        amountPerInstallment: amount, totalAmount: 0, remainingAmount: 0, nextDate: null,
      };
      group.totalAmount = Math.round((group.totalAmount + amount) * 100) / 100;
      if (closed) group.closedInstallments = Math.max(group.closedInstallments, part);
      else {
        group.remainingAmount = Math.round((group.remainingAmount + amount) * 100) / 100;
        const displayDate = invoice?.displayDate ?? expense.date;
        if (!group.nextDate || displayDate < group.nextDate) group.nextDate = displayDate;
      }
      groups.set(key, group);
    }

    return Array.from(groups.values())
      .filter(group => group.closedInstallments < group.totalInstallments)
      .sort((a, b) => (a.nextDate ?? '').localeCompare(b.nextDate ?? ''));
  }
}
