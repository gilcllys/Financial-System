import { Injectable, inject } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable, map, forkJoin, of, switchMap, catchError } from 'rxjs';
import { environment } from '../../../environments/environment';
import { OpenInvoice, Expense, CreditCard, ExpenseCategory } from '../models';
import { invoiceForDate } from '../utils/invoice-cycle';
import { MonthlyAnalytics, CategoryAnalytics, ConsolidatedSummary } from './analytics.service';
import { BalancesResponse, PaginatedResponse, SharedDebtEntry, SharedDebtHomeSummary, SharedDebtService } from './shared-debt.service';
import { ExpenseService, HistoryEntry, RecurringExpenseTemplate } from './expense.service';
import { InstallmentsService } from './installments.service';

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
  expensePage: PaginatedResponse<Expense>;
  installmentGroups: InstallmentGroup[];
  categories: ExpenseCategory[];
  recurringTemplates: RecurringExpenseTemplate[];
  generatedRecurringTemplateIds: number[];
  compositionEntries: HistoryEntry[] | null;
  sharedBalances: { group: SharedDebtHomeSummary; balances: BalancesResponse | null }[];
  sharedInstallmentCount: number | null;
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
  private sharedDebtService = inject(SharedDebtService);
  private installmentsService = inject(InstallmentsService);
  private expenseService = inject(ExpenseService);

  load(month: number, year: number): Observable<HomeSummary> {
    const params = new HttpParams().set('month', month).set('year', year);
    return this.http.get<HomeDashboardPayload>(`${environment.apiBaseUrl}/api/dashboard/home/`, { params }).pipe(
      switchMap(data => {
        const monthStart = `${year}-${String(month).padStart(2, '0')}-01`;
        const monthEnd = `${year}-${String(month).padStart(2, '0')}-${String(new Date(year, month, 0).getDate()).padStart(2, '0')}`;
        const rangeStart = [monthStart, ...data.open_invoices.map(invoice => invoice.period_start)].sort()[0];
        const rangeEnd = [monthEnd, ...data.open_invoices.map(invoice => invoice.period_end)].sort().at(-1)!;
        const compositionEntries$ = this.expenseService.historyAll({
          start_date: rangeStart,
          end_date: rangeEnd,
          include_future: true,
        }).pipe(catchError(() => of(null)));
        const balanceRequests = data.shared_debts.map(group =>
          this.sharedDebtService.balances(group.id).pipe(
            map(balances => ({ group, balances })),
            catchError(() => of({ group, balances: null }))
          )
        );
        return forkJoin([
          balanceRequests.length ? forkJoin(balanceRequests) : of([]),
          this.installmentsService.load().pipe(catchError(() => of(null))),
          compositionEntries$,
        ]).pipe(map(([results, installmentData, compositionEntries]) => ({
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
          compositionEntries,
          sharedBalances: results,
          sharedInstallmentCount: installmentData
            ? this.countActiveSharedInstallments(installmentData.shared_entries, data.cards)
            : null,
        })));
      })
    );
  }

  private countActiveSharedInstallments(entries: SharedDebtEntry[], cards: CreditCard[]): number {
    const cardById = new Map(cards.map(card => [card.id, card]));
    const groups = new Map<string, boolean>();
    for (const entry of entries) {
      if (entry.total_installments <= 1 || !entry.installment_group_id) continue;
      const card = entry.credit_card ? cardById.get(entry.credit_card) : undefined;
      const paidByDueDate = entry.invoice_paid ?? this.isDueDateReached(entry.date, card);
      groups.set(entry.installment_group_id, (groups.get(entry.installment_group_id) ?? false) || !paidByDueDate);
    }
    return [...groups.values()].filter(Boolean).length;
  }

  private isDueDateReached(date: string, card?: CreditCard): boolean {
    const now = new Date();
    const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    if (!card) {
      const [year, month, day] = date.split('-').map(Number);
      return new Date(year, month - 1, day) <= today;
    }

    const invoice = invoiceForDate(date, card.closing_day);
    const dueDate = new Date(
      invoice.year,
      invoice.month - 1,
      Math.min(card.due_day, new Date(invoice.year, invoice.month, 0).getDate()),
    );
    return dueDate <= today;
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
      const paidByDueDate = this.isDueDateReached(expense.date, card);
      const amount = Math.abs(Number(expense.amount));
      const group = groups.get(key) ?? {
        name, totalInstallments: totalParts, paidInstallments: 0,
        amountPerInstallment: amount, totalAmount: 0, remainingAmount: 0, nextDate: null,
      };
      group.totalAmount = Math.round((group.totalAmount + amount) * 100) / 100;
      if (paidByDueDate) group.paidInstallments = Math.max(group.paidInstallments, part);
      else {
        group.remainingAmount = Math.round((group.remainingAmount + amount) * 100) / 100;
        const displayDate = invoice?.displayDate ?? expense.date;
        if (!group.nextDate || displayDate < group.nextDate) group.nextDate = displayDate;
      }
      groups.set(key, group);
    }

    return Array.from(groups.values())
      .filter(group => group.paidInstallments < group.totalInstallments)
      .sort((a, b) => (a.nextDate ?? '').localeCompare(b.nextDate ?? ''));
  }
}
