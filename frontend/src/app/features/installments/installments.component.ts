import { Component, OnDestroy, OnInit, inject, signal, computed } from '@angular/core';
import { ToastService } from '../../core/services/toast.service';
import { ConfirmDialogService } from '../../core/services/confirm-dialog.service';
import { RouterLink } from '@angular/router';
import { ExpenseService } from '../../core/services/expense.service';
import { InstallmentsService } from '../../core/services/installments.service';
import { SharedDebtService, SharedDebtEntry } from '../../core/services/shared-debt.service';
import { CreditCard, Expense } from '../../core/models';
import { invoiceForDate, isInvoiceClosed, InvoiceMonthRef } from '../../core/utils/invoice-cycle';

interface InstallmentProgress {
  currentInstallment: number;
  paidInstallments: number;
  remainingInstallments: number;
  progressPercent: number;
  complete: boolean;
}

interface InstallmentGroup {
  name: string;
  cardId: number | null;
  cardName: string;
  totalInstallments: number;
  startMonthIndex: number;
  currentInstallment: number;
  paidInstallments: number;
  remainingInstallments: number;
  progressPercent: number;
  complete: boolean;
  amountPerInstallment: number;
  totalAmount: number;
  nextDate: string | null;
  expenses: Expense[];
}

interface SharedInstallmentGroup {
  installment_group_id: string;
  name: string;
  cardId: number | null;
  cardName: string;
  shared_debt_id: number;
  shared_debt_name: string;
  totalInstallments: number;
  startMonthIndex: number;
  currentInstallment: number;
  paidInstallments: number;
  remainingInstallments: number;
  progressPercent: number;
  complete: boolean;
  amountPerInstallment: number;
  myPortion: number;
  totalAmount: number;
  nextDate: string | null;
  entries: SharedDebtEntry[];
}

interface SharedDebtInstallmentSection {
  shared_debt_id: number;
  shared_debt_name: string;
  groups: SharedInstallmentGroup[];
  totalMyPortion: number;
  largestMyPortion: number;
}

@Component({
  selector: 'app-installments',
  standalone: true,
  imports: [RouterLink],
  templateUrl: './installments.component.html',
  styleUrls: ['./installments.component.scss'],
})
export class InstallmentsComponent implements OnDestroy, OnInit {
  private toast = inject(ToastService);
  private confirmDialog = inject(ConfirmDialogService);
  private expenseService = inject(ExpenseService);
  private sharedDebtService = inject(SharedDebtService);
  private installmentsService = inject(InstallmentsService);

  expenses = signal<Expense[]>([]);
  sharedEntries = signal<SharedDebtEntry[]>([]);
  cards = signal<CreditCard[]>([]);
  loading = signal(true);
  loadingShared = signal(true);
  loadingCards = signal(true);
  showFinalizadas = signal(false);
  showFinalizadasShared = signal(false);
  deletingGroup = signal<string | null>(null);
  deletingSharedGroup = signal<string | null>(null);
  activeInstallmentTab = signal<'individual' | 'shared'>('individual');
  private currentDate = signal(new Date());
  private monthRefreshTimer: ReturnType<typeof setTimeout> | null = null;

  private cardMap = computed(() => new Map(this.cards().map(card => [card.id, card])));

  private getExpenseCardId(expense: Expense): number | null {
    return expense.credit_card_id ?? (expense as any).credit_card ?? null;
  }

  private installmentInvoice(date: string, cardId: number | null): InvoiceMonthRef | null {
    const card = cardId ? this.cardMap().get(cardId) : null;
    return card ? invoiceForDate(date, card.closing_day) : null;
  }

  private isInstallmentClosed(date: string, cardId: number | null): boolean {
    const invoice = this.installmentInvoice(date, cardId);
    const card = cardId ? this.cardMap().get(cardId) : null;
    if (!invoice || !card) {
      const today = new Date();
      today.setHours(0, 0, 0, 0);
      const [year, month, day] = date.split('-').map(Number);
      return new Date(year, month - 1, day) <= today;
    }
    return isInvoiceClosed(date, card.closing_day);
  }

  private installmentDisplayDate(date: string, cardId: number | null): string {
    return this.installmentInvoice(date, cardId)?.displayDate ?? date;
  }

  private calendarMonthIndex(date: Date): number {
    return date.getFullYear() * 12 + date.getMonth();
  }

  private installmentStartMonthIndex(date: string, installmentNumber: number): number {
    const [year, month] = date.split('-').map(Number);
    return year * 12 + month - 1 - (installmentNumber - 1);
  }

  private isInstallmentPaidByDueDate(date: string, cardId: number | null): boolean {
    const now = this.currentDate();
    const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    const card = cardId ? this.cardMap().get(cardId) : null;
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

  private isSharedInstallmentPaid(entry: SharedDebtEntry): boolean {
    return entry.invoice_paid ?? this.isInstallmentPaidByDueDate(entry.date, entry.credit_card ?? null);
  }

  private progressAtMonth(startMonthIndex: number, totalInstallments: number, paidInstallments: number): InstallmentProgress {
    const elapsedMonths = this.calendarMonthIndex(this.currentDate()) - startMonthIndex + 1;
    const currentInstallment = Math.min(totalInstallments, Math.max(0, elapsedMonths));
    const settled = Math.min(totalInstallments, Math.max(0, paidInstallments));
    const remainingInstallments = totalInstallments - settled;

    return {
      currentInstallment,
      paidInstallments: settled,
      remainingInstallments,
      progressPercent: Math.round((settled / totalInstallments) * 100),
      complete: settled === totalInstallments,
    };
  }

  installmentPositionLabel(group: InstallmentGroup | SharedInstallmentGroup): string {
    if (group.currentInstallment === 0) {
      return `Começa em ${this.formatMonthIndex(group.startMonthIndex)}`;
    }
    return `Parcela atual ${group.currentInstallment} de ${group.totalInstallments}`;
  }

  installmentPaymentLabel(group: InstallmentGroup | SharedInstallmentGroup): string {
    return `${group.paidInstallments} de ${group.totalInstallments} vencimentos considerados pagos · ${group.remainingInstallments} restantes`;
  }

  private formatMonthIndex(monthIndex: number): string {
    const year = Math.floor(monthIndex / 12);
    const month = ((monthIndex % 12) + 12) % 12;
    const months = ['Jan', 'Fev', 'Mar', 'Abr', 'Mai', 'Jun', 'Jul', 'Ago', 'Set', 'Out', 'Nov', 'Dez'];
    return `${months[month]}/${year}`;
  }

  private scheduleMonthRefresh(): void {
    const now = new Date();
    const nextDay = new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1, 0, 0, 1);
    this.monthRefreshTimer = setTimeout(() => {
      this.currentDate.set(new Date());
      this.scheduleMonthRefresh();
    }, nextDay.getTime() - now.getTime());
  }


  installmentGroups = computed((): InstallmentGroup[] => {
    const installmentExpenses = this.expenses().filter(e => /parcela\s+\d+\/\d+/i.test(e.description));
    const groupMap = new Map<string, InstallmentGroup>();

    for (const expense of installmentExpenses) {
      const match = expense.description.match(/^(.*?)[\s-]*parcela\s+(\d+)\/(\d+)/i);
      if (!match) continue;
      const baseName = match[1].trim() || expense.description;
      const currentPart = +match[2];
      const totalParts = +match[3];
      const cardId = this.getExpenseCardId(expense);
      const key = `${baseName}-${totalParts}-${cardId ?? 'none'}`;
      const startMonthIndex = this.installmentStartMonthIndex(expense.date, currentPart);
      const displayDate = this.installmentDisplayDate(expense.date, cardId);

      const existing = groupMap.get(key);
      if (existing) {
        existing.expenses.push(expense);
        existing.totalAmount = Math.round((existing.totalAmount + Math.abs(expense.amount)) * 100) / 100;
        existing.startMonthIndex = Math.min(existing.startMonthIndex, startMonthIndex);
        if (!this.isInstallmentPaidByDueDate(expense.date, cardId) && (!existing.nextDate || displayDate < existing.nextDate)) {
          existing.nextDate = displayDate;
        }
      } else {
        const card = cardId ? this.cardMap().get(cardId) : null;
        const cardName = (expense as any).credit_card_name ?? (expense as any).card_name ?? card?.name ?? '';
        groupMap.set(key, {
          name: baseName,
          cardId,
          cardName,
          totalInstallments: totalParts,
          startMonthIndex,
          currentInstallment: 0,
          paidInstallments: 0,
          remainingInstallments: totalParts,
          progressPercent: 0,
          complete: false,
          amountPerInstallment: Math.abs(expense.amount),
          totalAmount: Math.abs(expense.amount) * totalParts,
          nextDate: !this.isInstallmentPaidByDueDate(expense.date, cardId) ? displayDate : null,
          expenses: [expense],
        });
      }
    }
    return Array.from(groupMap.values())
      .map(group => ({
        ...group,
        ...this.progressAtMonth(
          group.startMonthIndex,
          group.totalInstallments,
          group.expenses.filter(expense => this.isInstallmentPaidByDueDate(expense.date, group.cardId)).length,
        ),
      }))
      .sort((a, b) => a.name.localeCompare(b.name));
  });

  activeGroups = computed((): InstallmentGroup[] =>
    this.installmentGroups().filter(g => !g.complete)
  );
  finalizadasGroups = computed((): InstallmentGroup[] =>
    this.installmentGroups().filter(g => g.complete)
  );

  sharedInstallmentGroups = computed((): SharedInstallmentGroup[] => {
    const parceladas = this.sharedEntries().filter(e => e.total_installments > 1 && e.installment_group_id);
    const groupMap = new Map<string, SharedInstallmentGroup>();

    for (const entry of parceladas) {
      const gid = entry.installment_group_id!;
      const baseName = entry.description.replace(/\s*\(\d+\/\d+\)\s*$/, '').trim();
      const cardId = entry.credit_card ?? null;
      const startMonthIndex = this.installmentStartMonthIndex(entry.date, entry.installment_number);
      const displayDate = this.installmentDisplayDate(entry.date, cardId);
      const card = cardId ? this.cardMap().get(cardId) : null;
      const cardName = (entry as any).credit_card_name ?? card?.name ?? '';

      const existing = groupMap.get(gid);
      if (existing) {
        existing.entries.push(entry);
        existing.startMonthIndex = Math.min(existing.startMonthIndex, startMonthIndex);
        if (!this.isSharedInstallmentPaid(entry) && (!existing.nextDate || displayDate < existing.nextDate)) {
          existing.nextDate = displayDate;
        }
      } else {
        groupMap.set(gid, {
          installment_group_id: gid,
          name: baseName,
          cardId,
          cardName,
          shared_debt_id: entry.shared_debt,
          shared_debt_name: entry.shared_debt_name,
          totalInstallments: entry.total_installments,
          startMonthIndex,
          currentInstallment: 0,
          paidInstallments: 0,
          remainingInstallments: entry.total_installments,
          progressPercent: 0,
          complete: false,
          amountPerInstallment: entry.amount,
          myPortion: entry.amount / (entry.participant_count ?? 1),
          totalAmount: entry.amount * entry.total_installments,
          nextDate: !this.isSharedInstallmentPaid(entry) ? displayDate : null,
          entries: [entry],
        });
      }
    }
    return Array.from(groupMap.values())
      .map(group => ({
        ...group,
        ...this.progressAtMonth(
          group.startMonthIndex,
          group.totalInstallments,
          group.entries.filter(entry => this.isSharedInstallmentPaid(entry)).length,
        ),
      }))
      .sort((a, b) => a.name.localeCompare(b.name));
  });

  activeSharedGroups = computed((): SharedInstallmentGroup[] =>
    this.sharedInstallmentGroups().filter(g => !g.complete)
  );
  finalizadasSharedGroups = computed((): SharedInstallmentGroup[] =>
    this.sharedInstallmentGroups().filter(g => g.complete)
  );

  sharedSections = computed((): SharedDebtInstallmentSection[] =>
    this.groupSharedByDebt(this.activeSharedGroups())
  );
  finalizadasSharedSections = computed((): SharedDebtInstallmentSection[] =>
    this.groupSharedByDebt(this.finalizadasSharedGroups())
  );

  totalParcelasIndividuais = computed(() =>
    Math.round(this.activeGroups().reduce((sum, group) => sum + group.amountPerInstallment, 0) * 100) / 100
  );
  totalParcelasCompartilhadas = computed(() =>
    Math.round(this.activeSharedGroups().reduce((sum, group) => sum + group.myPortion, 0) * 100) / 100
  );
  monthlyInstallmentCommitment = computed(() =>
    Math.round((this.totalParcelasIndividuais() + this.totalParcelasCompartilhadas()) * 100) / 100
  );

  private groupSharedByDebt(groups: SharedInstallmentGroup[]): SharedDebtInstallmentSection[] {
    const sections = new Map<number, SharedDebtInstallmentSection>();
    for (const group of groups) {
      const section = sections.get(group.shared_debt_id);
      if (section) {
        section.groups.push(group);
        section.totalMyPortion += group.myPortion;
        section.largestMyPortion = Math.max(section.largestMyPortion, group.myPortion);
      } else {
        sections.set(group.shared_debt_id, {
          shared_debt_id: group.shared_debt_id,
          shared_debt_name: group.shared_debt_name,
          groups: [group],
          totalMyPortion: group.myPortion,
          largestMyPortion: group.myPortion,
        });
      }
    }
    return Array.from(sections.values())
      .map(section => ({
        ...section,
        totalMyPortion: +section.totalMyPortion.toFixed(2),
        largestMyPortion: +section.largestMyPortion.toFixed(2),
        groups: section.groups.sort((a, b) => a.name.localeCompare(b.name)),
      }))
      .sort((a, b) => a.shared_debt_name.localeCompare(b.shared_debt_name));
  }

  ngOnInit(): void {
    this.loadOverview();
    this.scheduleMonthRefresh();
  }

  ngOnDestroy(): void {
    if (this.monthRefreshTimer) clearTimeout(this.monthRefreshTimer);
  }

  private loadOverview(): void {
    this.loading.set(true);
    this.loadingShared.set(true);
    this.loadingCards.set(true);
    this.installmentsService.load().subscribe({
      next: overview => {
        this.expenses.set(overview.expenses);
        this.sharedEntries.set(overview.shared_entries);
        this.cards.set(overview.cards);
        this.loading.set(false);
        this.loadingShared.set(false);
        this.loadingCards.set(false);
      },
      error: () => {
        this.loading.set(false);
        this.loadingShared.set(false);
        this.loadingCards.set(false);
      },
    });
  }

  private fetchExpenses(): void { this.loadOverview(); }
  private fetchSharedEntries(): void { this.loadOverview(); }

  installmentKey(group: InstallmentGroup): string { return `${group.name}:${group.cardId ?? 'none'}`; }

  futureExpenses(group: InstallmentGroup): Expense[] {
    return group.expenses.filter(expense => !this.isInstallmentClosed(expense.date, group.cardId));
  }

  async deleteGroup(group: InstallmentGroup): Promise<void> {
    const key = this.installmentKey(group);
    const ids = group.expenses.map(expense => expense.id);
    if (!(await this.confirmDialog.confirm(`Apagar as ${ids.length} parcelas de "${group.name}" deste grupo?`))) return;
    this.deletingGroup.set(key);
    this.expenseService.deleteInstallments(group.name, group.totalInstallments, ids).subscribe({
      next: () => { this.deletingGroup.set(null); this.fetchExpenses(); },
      error: () => { this.toast.error('Erro ao apagar parcelas.'); this.deletingGroup.set(null); },
    });
  }

  async cancelFutureInstallments(group: InstallmentGroup): Promise<void> {
    const futureIds = this.futureExpenses(group).map(expense => expense.id);
    if (!futureIds.length) return;
    if (!(await this.confirmDialog.confirm(`Cancelar ${futureIds.length} parcelas futuras de "${group.name}"? Parcelas já fechadas serão preservadas.`, 'Cancelar parcelas futuras'))) return;
    const key = this.installmentKey(group);
    this.deletingGroup.set(key);
    this.expenseService.deleteInstallments(group.name, group.totalInstallments, futureIds).subscribe({
      next: () => { this.deletingGroup.set(null); this.fetchExpenses(); },
      error: () => { this.toast.error('Erro ao cancelar parcelas futuras.'); this.deletingGroup.set(null); },
    });
  }

  async deleteSharedGroup(group: SharedInstallmentGroup): Promise<void> {
    if (!(await this.confirmDialog.confirm(`Apagar todas as ${group.totalInstallments} parcelas de "${group.name}" do grupo ${group.shared_debt_name}? Isso afeta todos os membros.`))) return;
    this.deletingSharedGroup.set(group.installment_group_id);
    this.sharedDebtService.deleteInstallments(group.installment_group_id).subscribe({
      next: () => { this.deletingSharedGroup.set(null); this.fetchSharedEntries(); },
      error: () => { this.toast.error('Erro ao apagar parcelas compartilhadas.'); this.deletingSharedGroup.set(null); },
    });
  }

  toggleFinalizadas(): void { this.showFinalizadas.set(!this.showFinalizadas()); }
  toggleFinalizadasShared(): void { this.showFinalizadasShared.set(!this.showFinalizadasShared()); }

  selectInstallmentTab(tab: 'individual' | 'shared'): void {
    this.activeInstallmentTab.set(tab);
  }

  formatAmount(amount: number): string {
    return new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(amount);
  }

  formatNextDate(dateStr: string | null): string {
    if (!dateStr) return '-';
    const [y, m] = dateStr.split('-');
    const months = ['Jan','Fev','Mar','Abr','Mai','Jun','Jul','Ago','Set','Out','Nov','Dez'];
    return `${months[+m-1]}/${y}`;
  }
}
