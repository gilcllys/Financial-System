import { Component, OnInit, inject, signal, computed } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ExpenseService } from '../../core/services/expense.service';
import { CategoryService } from '../../core/services/category.service';
import { Expense, ExpenseCategory } from '../../core/models';

interface CategoryBreakdown {
  category: ExpenseCategory;
  total: number;
  count: number;
}

@Component({
  selector: 'app-reports',
  standalone: true,
  imports: [FormsModule],
  templateUrl: './reports.component.html',
  styleUrls: ['./reports.component.scss'],
})
export class ReportsComponent implements OnInit {
  private expenseService = inject(ExpenseService);
  private categoryService = inject(CategoryService);

  expenses = signal<Expense[]>([]);
  categories = signal<ExpenseCategory[]>([]);
  loading = signal(true);

  selectedMonth = signal(new Date().getMonth() + 1);
  selectedYear = signal(new Date().getFullYear());

  months = [
    { value: 1, label: 'Janeiro' }, { value: 2, label: 'Fevereiro' },
    { value: 3, label: 'Março' }, { value: 4, label: 'Abril' },
    { value: 5, label: 'Maio' }, { value: 6, label: 'Junho' },
    { value: 7, label: 'Julho' }, { value: 8, label: 'Agosto' },
    { value: 9, label: 'Setembro' }, { value: 10, label: 'Outubro' },
    { value: 11, label: 'Novembro' }, { value: 12, label: 'Dezembro' },
  ];

  years = Array.from({ length: 5 }, (_, i) => new Date().getFullYear() - 2 + i);

  filtered = computed(() => {
    return this.expenses().filter(e => {
      const d = new Date(e.date + 'T00:00:00');
      return d.getMonth() + 1 === this.selectedMonth() && d.getFullYear() === this.selectedYear();
    });
  });

  totalIncome = computed(() =>
    this.filtered().filter(e => e.amount > 0).reduce((s, e) => s + e.amount, 0)
  );

  totalExpenses = computed(() =>
    this.filtered().filter(e => e.amount < 0).reduce((s, e) => s + e.amount, 0)
  );

  balance = computed(() => this.totalIncome() + this.totalExpenses());

  breakdown = computed((): CategoryBreakdown[] => {
    const map = new Map<number, CategoryBreakdown>();
    for (const e of this.filtered()) {
      const cat = this.categories().find(c => c.id === e.category_id);
      if (!cat) continue;
      const existing = map.get(cat.id);
      if (existing) {
        existing.total += e.amount;
        existing.count++;
      } else {
        map.set(cat.id, { category: cat, total: e.amount, count: 1 });
      }
    }
    return Array.from(map.values()).sort((a, b) => a.total - b.total);
  });

  ngOnInit(): void {
    this.categoryService.list().subscribe({ next: cats => this.categories.set(cats) });
    this.expenseService.list({ page_size: 500 }).subscribe({
      next: res => { const data = res.results; this.expenses.set(data); this.loading.set(false); },
      error: () => this.loading.set(false),
    });
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

  monthLabel(): string {
    return this.months.find(m => m.value === this.selectedMonth())?.label ?? '';
  }
}
