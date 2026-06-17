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

  // Group installment expenses: "Parcela X/Y - Name"
  installmentGroups = computed((): InstallmentGroup[] => {
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

      const existing = groupMap.get(key);
      if (existing) {
        existing.expenses.push(expense);
        if (currentPart > existing.paidInstallments) {
          existing.paidInstallments = currentPart;
        }
      } else {
        groupMap.set(key, {
          name: baseName,
          totalInstallments: totalParts,
          paidInstallments: currentPart,
          amountPerInstallment: Math.abs(expense.amount),
          totalAmount: Math.abs(expense.amount) * totalParts,
          expenses: [expense],
        });
      }
    }

    return Array.from(groupMap.values()).sort((a, b) => a.name.localeCompare(b.name));
  });

  ngOnInit(): void {
    this.expenseService.list({ page_size: 500 }).subscribe({
      next: res => { const data = res.results; this.expenses.set(data); this.loading.set(false); },
      error: () => this.loading.set(false),
    });
  }

  formatAmount(amount: number): string {
    return new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(amount);
  }

  progressPct(group: InstallmentGroup): number {
    return Math.round((group.paidInstallments / group.totalInstallments) * 100);
  }
}
