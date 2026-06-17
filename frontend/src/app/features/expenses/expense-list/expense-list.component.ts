import { Component, OnInit, inject, signal, computed } from '@angular/core';
import { RouterLink } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { ExpenseService } from '../../../core/services/expense.service';
import { CategoryService } from '../../../core/services/category.service';
import { Expense, ExpenseCategory, PaymentMethod } from '../../../core/models';
import { CurrencyPipe, DatePipe } from '@angular/common';

@Component({
  selector: 'app-expense-list',
  standalone: true,
  imports: [RouterLink, FormsModule, CurrencyPipe, DatePipe],
  templateUrl: './expense-list.component.html',
  styleUrls: ['./expense-list.component.scss'],
})
export class ExpenseListComponent implements OnInit {
  private expenseService = inject(ExpenseService);
  private categoryService = inject(CategoryService);

  expenses = signal<Expense[]>([]);
  categories = signal<ExpenseCategory[]>([]);
  loading = signal(true);
  deletingId = signal<number | null>(null);

  // Filters
  filterMonth = signal(new Date().getMonth() + 1);
  filterYear = signal(new Date().getFullYear());
  filterCategory = signal<number | ''>('');
  filterPayment = signal<PaymentMethod | ''>('');

  filteredExpenses = computed(() => {
    return this.expenses().filter(e => {
      const d = new Date(e.date + 'T00:00:00');
      const monthMatch = d.getMonth() + 1 === this.filterMonth();
      const yearMatch = d.getFullYear() === this.filterYear();
      const catMatch = !this.filterCategory() || e.category_id === +this.filterCategory();
      const payMatch = !this.filterPayment() || e.payment_method === this.filterPayment();
      return monthMatch && yearMatch && catMatch && payMatch;
    });
  });

  totalIncome = computed(() =>
    this.filteredExpenses().filter(e => e.amount > 0).reduce((s, e) => s + e.amount, 0)
  );

  totalExpenses = computed(() =>
    this.filteredExpenses().filter(e => e.amount < 0).reduce((s, e) => s + e.amount, 0)
  );

  balance = computed(() => this.totalIncome() + this.totalExpenses());

  months = [
    { value: 1, label: 'Janeiro' }, { value: 2, label: 'Fevereiro' },
    { value: 3, label: 'Março' }, { value: 4, label: 'Abril' },
    { value: 5, label: 'Maio' }, { value: 6, label: 'Junho' },
    { value: 7, label: 'Julho' }, { value: 8, label: 'Agosto' },
    { value: 9, label: 'Setembro' }, { value: 10, label: 'Outubro' },
    { value: 11, label: 'Novembro' }, { value: 12, label: 'Dezembro' },
  ];

  years = Array.from({ length: 5 }, (_, i) => new Date().getFullYear() - 2 + i);

  ngOnInit(): void {
    this.loadAll();
  }

  private loadAll(): void {
    this.loading.set(true);
    this.categoryService.list().subscribe({ next: cats => this.categories.set(cats) });
    this.expenseService.list().subscribe({
      next: data => { this.expenses.set(data); this.loading.set(false); },
      error: () => this.loading.set(false),
    });
  }

  delete(id: number): void {
    if (!confirm('Deseja excluir este gasto?')) return;
    this.deletingId.set(id);
    this.expenseService.delete(id).subscribe({
      next: () => {
        this.expenses.update(list => list.filter(e => e.id !== id));
        this.deletingId.set(null);
      },
      error: () => this.deletingId.set(null),
    });
  }

  categoryName(id: number): string {
    return this.categories().find(c => c.id === id)?.name ?? '—';
  }

  formatAmount(amount: number): string {
    return new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(Math.abs(amount));
  }

  amountClass(amount: number): string {
    return amount >= 0 ? 'value-up' : 'value-down';
  }

  amountPrefix(amount: number): string {
    return amount >= 0 ? '+' : '-';
  }
}
