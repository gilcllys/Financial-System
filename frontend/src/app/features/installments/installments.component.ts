import { Component, OnInit, inject, signal, computed } from '@angular/core';
import { RouterLink } from '@angular/router';
import { ExpenseService } from '../../core/services/expense.service';
import { Expense } from '../../core/models';

interface InstallmentGroup {
  name: string;
  totalInstallments: number;
  paidInstallments: number;
  amountPerInstallment: number;
  totalAmount: number;
  expenses: Expense[];
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

  expenses = signal<Expense[]>([]);
  loading = signal(true);
  showFinalizadas = signal(false);
  deletingGroup = signal<string | null>(null);

  // Group installment expenses: "Parcela X/Y - Name"
  installmentGroups = computed((): InstallmentGroup[] => {
    const today = new Date();
    today.setHours(0, 0, 0, 0);

    const installmentExpenses = this.expenses().filter(e =>
      /parcela\s+\d+\/\d+/i.test(e.description)
    );

    const groupMap = new Map<string, InstallmentGroup>();

    for (const expense of installmentExpenses) {
      const match = expense.description.match(/^(.*?)[\s-]*parcela\s+(\d+)\/(\d+)/i);
      if (!match) continue;

      const baseName = match[1].trim() || expense.description;
      const currentPart = +match[2];
      const totalParts = +match[3];
      const key = `${baseName}-${totalParts}`;

      // Parcela já paga = data da despesa <= hoje
      const expenseDate = new Date(expense.date + 'T00:00:00');
      const isPaid = expenseDate <= today;

      const existing = groupMap.get(key);
      if (existing) {
        existing.expenses.push(expense);
        // Conta apenas parcelas já ocorridas (date <= today)
        if (isPaid && currentPart > existing.paidInstallments) {
          existing.paidInstallments = currentPart;
        }
      } else {
        groupMap.set(key, {
          name: baseName,
          totalInstallments: totalParts,
          paidInstallments: isPaid ? currentPart : 0,
          amountPerInstallment: Math.abs(expense.amount),
          totalAmount: Math.abs(expense.amount) * totalParts,
          expenses: [expense],
        });
      }
    }

    return Array.from(groupMap.values()).sort((a, b) => a.name.localeCompare(b.name));
  });

  /** Groups with at least one remaining installment (not 100% paid). */
  activeGroups = computed((): InstallmentGroup[] =>
    this.installmentGroups().filter(g => g.paidInstallments < g.totalInstallments)
  );

  /** Groups where every installment has been paid. */
  finalizadasGroups = computed((): InstallmentGroup[] =>
    this.installmentGroups().filter(g => g.paidInstallments === g.totalInstallments)
  );

  ngOnInit(): void {
    this.fetchExpenses();
  }

  private fetchExpenses(): void {
    this.loading.set(true);
    this.expenseService.list({ page_size: 500 }).subscribe({
      next: res => { this.expenses.set(res.results); this.loading.set(false); },
      error: () => this.loading.set(false),
    });
  }

  deleteGroup(group: InstallmentGroup): void {
    if (!confirm(
      `Apagar todas as ${group.totalInstallments} parcelas de "${group.name}"? Esta ação não pode ser desfeita.`
    )) return;

    this.deletingGroup.set(group.name);
    this.expenseService.deleteInstallments(group.name, group.totalInstallments).subscribe({
      next: () => { this.deletingGroup.set(null); this.fetchExpenses(); },
      error: () => {
        alert('Erro ao apagar parcelas. Tente novamente.');
        this.deletingGroup.set(null);
      },
    });
  }

  toggleFinalizadas(): void {
    this.showFinalizadas.set(!this.showFinalizadas());
  }

  formatAmount(amount: number): string {
    return new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(amount);
  }

  progressPct(group: InstallmentGroup): number {
    return Math.round((group.paidInstallments / group.totalInstallments) * 100);
  }
}
