import { Component, OnInit, inject, signal, computed } from '@angular/core';
import { RouterLink } from '@angular/router';
import { ExpenseService } from '../../core/services/expense.service';
import { SharedDebtService, SharedDebtEntry } from '../../core/services/shared-debt.service';
import { Expense } from '../../core/models';

interface InstallmentGroup {
  name: string;
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

@Component({
  selector: 'app-installments',
  standalone: true,
  imports: [RouterLink],
  templateUrl: './installments.component.html',
  styleUrls: ['./installments.component.scss'],
})
export class InstallmentsComponent implements OnInit {
  private expenseService = inject(ExpenseService);
  private sharedDebtService = inject(SharedDebtService);

  expenses = signal<Expense[]>([]);
  sharedEntries = signal<SharedDebtEntry[]>([]);
  loading = signal(true);
  loadingShared = signal(true);
  showFinalizadas = signal(false);
  showFinalizadasShared = signal(false);
  deletingGroup = signal<string | null>(null);

  installmentGroups = computed((): InstallmentGroup[] => {
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const installmentExpenses = this.expenses().filter(e => /parcela\s+\d+\/\d+/i.test(e.description));
    const groupMap = new Map<string, InstallmentGroup>();

    for (const expense of installmentExpenses) {
      const match = expense.description.match(/^(.*?)[\s-]*parcela\s+(\d+)\/(\d+)/i);
      if (!match) continue;
      const baseName = match[1].trim() || expense.description;
      const currentPart = +match[2];
      const totalParts = +match[3];
      const key = `${baseName}-${totalParts}`;
      const expenseDate = new Date(expense.date + 'T00:00:00');
      const isPaid = expenseDate <= today;

      const existing = groupMap.get(key);
      if (existing) {
        existing.expenses.push(expense);
        if (isPaid && currentPart > existing.paidInstallments) {
          existing.paidInstallments = currentPart;
        }
        // Proxima parcela = menor data futura
        if (!isPaid) {
          if (!existing.nextDate || expense.date < existing.nextDate) existing.nextDate = expense.date;
        }
      } else {
        const cardName = (expense as any).credit_card_name ?? (expense as any).card_name ?? '';
        groupMap.set(key, {
          name: baseName,
          cardName,
          totalInstallments: totalParts,
          paidInstallments: isPaid ? currentPart : 0,
          amountPerInstallment: Math.abs(expense.amount),
          totalAmount: Math.abs(expense.amount) * totalParts,
          nextDate: !isPaid ? expense.date : null,
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
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const parceladas = this.sharedEntries().filter(e => e.total_installments > 1 && e.installment_group_id);
    const groupMap = new Map<string, SharedInstallmentGroup>();

    for (const entry of parceladas) {
      const gid = entry.installment_group_id!;
      const baseName = entry.description.replace(/\s*\(\d+\/\d+\)\s*$/, '').trim();
      const entryDate = new Date(entry.date + 'T00:00:00');
      const isPaid = entryDate <= today;
      const cardName = (entry as any).credit_card_name ?? '';

      const existing = groupMap.get(gid);
      if (existing) {
        existing.entries.push(entry);
        if (isPaid && entry.installment_number > existing.paidInstallments) {
          existing.paidInstallments = entry.installment_number;
        }
        if (!isPaid && (!existing.nextDate || entry.date < existing.nextDate)) {
          existing.nextDate = entry.date;
        }
      } else {
        groupMap.set(gid, {
          installment_group_id: gid,
          name: baseName,
          cardName,
          shared_debt_id: entry.shared_debt,
          shared_debt_name: entry.shared_debt_name,
          totalInstallments: entry.total_installments,
          paidInstallments: isPaid ? entry.installment_number : 0,
          amountPerInstallment: entry.amount,
          myPortion: entry.amount / (entry.participant_count ?? 1),
          totalAmount: entry.amount * entry.total_installments,
          nextDate: !isPaid ? entry.date : null,
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

  // KPIs
  totalComprometido = computed(() =>
    this.activeGroups().reduce((s, g) => s + g.amountPerInstallment * (g.totalInstallments - g.paidInstallments), 0)
  );
  parcelaEsteMes = computed(() =>
    this.activeGroups().reduce((s, g) => s + g.amountPerInstallment, 0) +
    this.activeSharedGroups().reduce((s, g) => s + g.myPortion, 0)
  );
  quitamEm30Dias = computed(() => {
    const limit = new Date();
    limit.setDate(limit.getDate() + 30);
    return this.activeGroups().filter(g => {
      const remaining = g.totalInstallments - g.paidInstallments;
      return remaining <= 3;
    }).length;
  });
  maiorParcela = computed(() =>
    Math.max(0, ...this.activeGroups().map(g => g.amountPerInstallment))
  );

  ngOnInit(): void {
    this.fetchExpenses();
    this.fetchSharedEntries();
  }

  private fetchExpenses(): void {
    this.loading.set(true);
    this.expenseService.list({ page_size: 500 }).subscribe({
      next: res => { this.expenses.set(res.results); this.loading.set(false); },
      error: () => this.loading.set(false),
    });
  }

  private fetchSharedEntries(): void {
    this.loadingShared.set(true);
    this.sharedDebtService.listEntries({ page_size: 500 }).subscribe({
      next: res => { this.sharedEntries.set(res.results); this.loadingShared.set(false); },
      error: () => this.loadingShared.set(false),
    });
  }

  deleteGroup(group: InstallmentGroup): void {
    if (!confirm(`Apagar todas as ${group.totalInstallments} parcelas de "${group.name}"?`)) return;
    this.deletingGroup.set(group.name);
    this.expenseService.deleteInstallments(group.name, group.totalInstallments).subscribe({
      next: () => { this.deletingGroup.set(null); this.fetchExpenses(); },
      error: () => { alert('Erro ao apagar parcelas.'); this.deletingGroup.set(null); },
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
    const [y, m, d] = dateStr.split('-');
    const months = ['Jan','Fev','Mar','Abr','Mai','Jun','Jul','Ago','Set','Out','Nov','Dez'];
    return `${months[+m-1]}/${y}`;
  }
}