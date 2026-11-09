import { Component, OnInit, inject, signal, computed } from '@angular/core';
import { ToastService } from '../../core/services/toast.service';
import { ConfirmDialogService } from '../../core/services/confirm-dialog.service';
import { RouterLink } from '@angular/router';
import { ExpenseService } from '../../core/services/expense.service';
import { InstallmentsService } from '../../core/services/installments.service';
import { SharedDebtService, SharedDebtEntry } from '../../core/services/shared-debt.service';
import { CreditCard, Expense } from '../../core/models';
import { invoiceForDate, isInvoiceClosed, InvoiceMonthRef } from '../../core/utils/invoice-cycle';

interface InstallmentGroup {
  name: string;
  cardId: number | null;
  cardName: string;
  totalInstallments: number;
  paidInstallments: number;
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
  paidInstallments: number;
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
export class InstallmentsComponent implements OnInit {
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
      const isPaid = this.isInstallmentClosed(expense.date, cardId);
      const displayDate = this.installmentDisplayDate(expense.date, cardId);

      const existing = groupMap.get(key);
      if (existing) {
        existing.expenses.push(expense);
        existing.totalAmount = Math.round((existing.totalAmount + Math.abs(expense.amount)) * 100) / 100;
        if (isPaid && currentPart > existing.paidInstallments) {
          existing.paidInstallments = currentPart;
        }
        if (!isPaid && (!existing.nextDate || displayDate < existing.nextDate)) {
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
          paidInstallments: isPaid ? currentPart : 0,
          amountPerInstallment: Math.abs(expense.amount),
          totalAmount: Math.abs(expense.amount) * totalParts,
          nextDate: !isPaid ? displayDate : null,
          expenses: [expense],
        });
      }
    }
    return Array.from(groupMap.values()).sort((a, b) => a.name.localeCompare(b.name));
  });

  activeGroups = computed((): InstallmentGroup[] =>
    this.installmentGroups().filter(g => g.paidInstallments < g.totalInstallments)
  );
  finalizadasGroups = computed((): InstallmentGroup[] =>
    this.installmentGroups().filter(g => g.paidInstallments === g.totalInstallments)
  );

  sharedInstallmentGroups = computed((): SharedInstallmentGroup[] => {
    const parceladas = this.sharedEntries().filter(e => e.total_installments > 1 && e.installment_group_id);
    const groupMap = new Map<string, SharedInstallmentGroup>();

    for (const entry of parceladas) {
      const gid = entry.installment_group_id!;
      const baseName = entry.description.replace(/\s*\(\d+\/\d+\)\s*$/, '').trim();
      const cardId = entry.credit_card ?? null;
      const isPaid = this.isInstallmentClosed(entry.date, cardId);
      const displayDate = this.installmentDisplayDate(entry.date, cardId);
      const card = cardId ? this.cardMap().get(cardId) : null;
      const cardName = (entry as any).credit_card_name ?? card?.name ?? '';

      const existing = groupMap.get(gid);
      if (existing) {
        existing.entries.push(entry);
        if (isPaid && entry.installment_number > existing.paidInstallments) {
          existing.paidInstallments = entry.installment_number;
        }
        if (!isPaid && (!existing.nextDate || displayDate < existing.nextDate)) {
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
          paidInstallments: isPaid ? entry.installment_number : 0,
          amountPerInstallment: entry.amount,
          myPortion: entry.amount / (entry.participant_count ?? 1),
          totalAmount: entry.amount * entry.total_installments,
          nextDate: !isPaid ? displayDate : null,
          entries: [entry],
        });
      }
    }
    return Array.from(groupMap.values()).sort((a, b) => a.name.localeCompare(b.name));
  });

  activeSharedGroups = computed((): SharedInstallmentGroup[] =>
    this.sharedInstallmentGroups().filter(g => g.paidInstallments < g.totalInstallments)
  );
  finalizadasSharedGroups = computed((): SharedInstallmentGroup[] =>
    this.sharedInstallmentGroups().filter(g => g.paidInstallments === g.totalInstallments)
  );

  sharedSections = computed((): SharedDebtInstallmentSection[] =>
    this.groupSharedByDebt(this.activeSharedGroups())
  );
  finalizadasSharedSections = computed((): SharedDebtInstallmentSection[] =>
    this.groupSharedByDebt(this.finalizadasSharedGroups())
  );

  // KPIs
  totalParcelasIndividuais = computed(() =>
    this.activeGroups().reduce((s, g) => s + g.amountPerInstallment, 0)
  );
  totalParcelasCompartilhadas = computed(() =>
    this.activeSharedGroups().reduce((s, g) => s + g.myPortion, 0)
  );
  maiorParcelaIndividual = computed(() =>
    Math.max(0, ...this.activeGroups().map(g => g.amountPerInstallment))
  );
  maiorParcelaCompartilhada = computed(() =>
    Math.max(0, ...this.activeSharedGroups().map(g => g.myPortion))
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

  formatAmount(amount: number): string {
    return new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(amount);
  }

  progressPct(group: { paidInstallments: number; totalInstallments: number }): number {
    return Math.round((group.paidInstallments / group.totalInstallments) * 100);
  }

  progressColor(pct: number): string {
    if (pct >= 75) return '#05b169';
    if (pct >= 40) return '#0052ff';
    return '#f4b000';
  }

  formatNextDate(dateStr: string | null): string {
    if (!dateStr) return '-';
    const [y, m] = dateStr.split('-');
    const months = ['Jan','Fev','Mar','Abr','Mai','Jun','Jul','Ago','Set','Out','Nov','Dez'];
    return `${months[+m-1]}/${y}`;
  }
}
