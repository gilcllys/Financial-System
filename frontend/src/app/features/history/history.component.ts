import { Component, OnInit, OnDestroy, inject, signal, computed } from '@angular/core';
import { RouterLink } from '@angular/router';
import { SlicePipe, UpperCasePipe } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Subject, debounceTime, distinctUntilChanged, takeUntil } from 'rxjs';
import { ExpenseService } from '../../core/services/expense.service';
import { CategoryService } from '../../core/services/category.service';
import { Expense, ExpenseCategory } from '../../core/models';

interface MonthGroup {
  label: string;
  year: number;
  month: number;
  expenses: Expense[];
  income: number;
  expenses_total: number;
  balance: number;
  collapsed: boolean;
}

const CAT_COLORS = ['#0052ff','#f4b000','#05b169','#cf202f','#af52de','#5ac8fa'];
const TOP_CAT_COLORS = ['#0052ff','#f4b000','#05b169','#cf202f','#af52de'];

@Component({
  selector: 'app-history',
  standalone: true,
  imports: [RouterLink, FormsModule, SlicePipe, UpperCasePipe],
  templateUrl: './history.component.html',
  styleUrls: ['./history.component.scss'],
})
export class HistoryComponent implements OnInit, OnDestroy {
  private expenseService = inject(ExpenseService);
  private categoryService = inject(CategoryService);
  private destroy$ = new Subject<void>();
  private searchSubject = new Subject<string>();

  readonly currentYear = new Date().getFullYear();
  readonly years = Array.from({ length: 5 }, (_, i) => this.currentYear - 4 + i);
  readonly months = [
    'Janeiro','Fevereiro','Março','Abril','Maio','Junho',
    'Julho','Agosto','Setembro','Outubro','Novembro','Dezembro'
  ].map((label, i) => ({ value: i + 1, label }));

  filterFromMonth = signal(1);
  filterFromYear  = signal(this.currentYear - 1);
  filterToMonth   = signal(new Date().getMonth() + 1);
  filterToYear    = signal(this.currentYear);
  filterCategory  = signal<number | ''>('');
  filterPayment   = signal('');
  searchTerm      = signal('');

  loading    = signal(false);
  allItems   = signal<Expense[]>([]);
  categories = signal<ExpenseCategory[]>([]);

  monthGroups = computed<MonthGroup[]>(() => {
    const groups = new Map<string, Expense[]>();
    for (const e of this.allItems()) {
      const key = e.date.substring(0, 7);
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key)!.push(e);
    }
    const NAMES = ['Janeiro','Fevereiro','Março','Abril','Maio','Junho',
                   'Julho','Agosto','Setembro','Outubro','Novembro','Dezembro'];
    return [...groups.entries()]
      .sort(([a], [b]) => b.localeCompare(a))
      .map(([key, exps]) => {
        const [year, month] = key.split('-').map(Number);
        const income = exps.filter(e => e.amount > 0).reduce((s, e) => s + e.amount, 0);
        const expenses_total = exps.filter(e => e.amount < 0).reduce((s, e) => s + Math.abs(e.amount), 0);
        return { label: `${NAMES[month - 1]} ${year}`, year, month, expenses: exps,
                 income, expenses_total, balance: income - expenses_total, collapsed: false };
      });
  });

  totalIncome   = computed(() => this.allItems().filter(e => e.amount > 0).reduce((s, e) => s + e.amount, 0));
  totalExpenses = computed(() => this.allItems().filter(e => e.amount < 0).reduce((s, e) => s + Math.abs(e.amount), 0));
  periodBalance = computed(() => this.totalIncome() - this.totalExpenses());
  cashExpenses  = computed(() => this.allItems().filter(e => e.amount < 0 && e.payment_method === 'dinheiro').reduce((s, e) => s + Math.abs(e.amount), 0));
  cardExpenses  = computed(() => this.allItems().filter(e => e.amount < 0 && e.payment_method === 'cartao').reduce((s, e) => s + Math.abs(e.amount), 0));
  sharedExpenses = computed(() => 0); // placeholder — shared via debt module

  topCategories = computed(() => {
    const map = new Map<string, number>();
    for (const e of this.allItems().filter(e => e.amount < 0)) {
      const name = this.categoryName(e.category_id);
      map.set(name, (map.get(name) ?? 0) + Math.abs(e.amount));
    }
    const total = this.totalExpenses() || 1;
    return [...map.entries()]
      .sort(([, a], [, b]) => b - a)
      .slice(0, 5)
      .map(([name, value]) => ({ name, value, pct: Math.round((value / total) * 100) }));
  });

  ngOnInit(): void {
    this.categoryService.list().subscribe({ next: c => this.categories.set(c) });
    this.searchSubject.pipe(debounceTime(400), distinctUntilChanged(), takeUntil(this.destroy$))
      .subscribe(() => { this.load(); });
    this.load();
  }

  ngOnDestroy(): void { this.destroy$.next(); this.destroy$.complete(); }

  onFilterChange(): void { this.load(); }
  onSearch(v: string): void { this.searchTerm.set(v); this.searchSubject.next(v); }
  clearFilters(): void { this.filterCategory.set(''); this.filterPayment.set(''); this.load(); }

  exportCsv(): void {
    const rows = [['Descrição','Categoria','Pagamento','Data','Valor']];
    for (const e of this.allItems()) {
      rows.push([e.description, this.categoryName(e.category_id),
                 e.payment_method, e.date, String(e.amount)]);
    }
    const csv = rows.map(r => r.join(';')).join('\n');
    const a = document.createElement('a');
    a.href = 'data:text/csv;charset=utf-8,' + encodeURIComponent(csv);
    a.download = `historico-${new Date().toISOString().slice(0,10)}.csv`;
    a.click();
  }

  private load(): void {
    this.loading.set(true);
    const requests: Array<{ month: number; year: number }> = [];
    let y = this.filterFromYear(), m = this.filterFromMonth();
    const toY = this.filterToYear(), toM = this.filterToMonth();
    while (y < toY || (y === toY && m <= toM)) {
      requests.push({ month: m, year: y });
      m++; if (m > 12) { m = 1; y++; }
      if (requests.length > 24) break;
    }
    if (requests.length === 0) { this.allItems.set([]); this.loading.set(false); return; }

    let loaded = 0;
    const all: Expense[] = [];
    requests.forEach(({ month, year }) => {
      this.expenseService.list({
        month, year,
        category_id: this.filterCategory() || undefined,
        payment_method: (this.filterPayment() || undefined) as 'dinheiro' | 'cartao' | undefined,
        search: this.searchTerm() || undefined,
        page_size: 200,
      }).pipe(takeUntil(this.destroy$)).subscribe({
        next: res => {
          all.push(...res.results);
          loaded++;
          if (loaded === requests.length) {
            all.sort((a, b) => b.date.localeCompare(a.date));
            this.allItems.set(all);
            this.loading.set(false);
          }
        },
        error: () => { loaded++; if (loaded === requests.length) this.loading.set(false); },
      });
    });
  }

  toggleMonth(group: MonthGroup): void { group.collapsed = !group.collapsed; }

  formatCurrency(v: number): string {
    return new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(Math.abs(v));
  }

  amountClass(amount: number): string { return amount >= 0 ? 'value-up mono' : 'value-down mono'; }
  amountPrefix(amount: number): string { return amount >= 0 ? '+' : '-'; }

  categoryName(id: number | null): string {
    if (!id) return 'Sem categoria';
    return this.categories().find(c => c.id === id)?.name ?? '—';
  }

  catColor(categoryId: number | null): string {
    if (!categoryId) return '#ccc';
    const idx = categoryId % CAT_COLORS.length;
    return CAT_COLORS[idx];
  }

  topCatColor(index: number): string {
    return TOP_CAT_COLORS[index % TOP_CAT_COLORS.length];
  }
}