import {
  Component, OnInit, OnDestroy,
  inject, signal, computed
} from '@angular/core';
import { RouterLink, ActivatedRoute } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { Subject, debounceTime, distinctUntilChanged, takeUntil } from 'rxjs';
import { ExpenseService } from '../../../core/services/expense.service';
import { CategoryService } from '../../../core/services/category.service';
import { SlicePipe } from '@angular/common';
import { Expense, ExpenseCategory, PaymentMethod } from '../../../core/models';
const MONTH_NAMES = [
  'Janeiro','Fevereiro','Março','Abril','Maio','Junho',
  'Julho','Agosto','Setembro','Outubro','Novembro','Dezembro'
];

@Component({
  selector: 'app-expense-list',
  standalone: true,
  imports: [RouterLink, FormsModule, SlicePipe],
  templateUrl: './expense-list.component.html',
  styleUrls: ['./expense-list.component.scss'],
})
export class ExpenseListComponent implements OnInit, OnDestroy {
  private expenseService = inject(ExpenseService);
  private categoryService = inject(CategoryService);
  private route = inject(ActivatedRoute);

  historyMode = false;
  uncategorizedMode = false;
  private destroy$ = new Subject<void>();
  private searchSubject = new Subject<string>();
  expenses = signal<Expense[]>([]);
  categories = signal<ExpenseCategory[]>([]);
  loading = signal(true);
  deletingId = signal<number | null>(null);

  // Paginação
  totalCount = signal(0);
  currentPage = signal(1);
  pageSize = 20;

  // Filtros
  filterMonth = signal(0);
  filterYear = signal(new Date().getFullYear());
  filterCategory = signal<number | ''>('');
  filterPayment = signal<PaymentMethod | ''>('dinheiro');
  searchTerm = signal('');

  // Mês atual para exibição
  readonly currentMonthName = MONTH_NAMES[new Date().getMonth()];
  readonly currentYear = new Date().getFullYear();

  totalPages = computed(() => Math.ceil(this.totalCount() / this.pageSize));
  pageNumbers = computed(() => Array.from({ length: this.totalPages() }, (_, i) => i + 1));

  totalIncome = computed(() =>
    this.expenses().filter(e => e.amount > 0).reduce((s, e) => s + e.amount, 0)
  );
  totalExpenses = computed(() =>
    this.expenses().filter(e => e.amount < 0).reduce((s, e) => s + e.amount, 0)
  );
  balance = computed(() => this.totalIncome() + this.totalExpenses());

  months = MONTH_NAMES.map((label, i) => ({ value: i + 1, label }));
  years = Array.from({ length: 5 }, (_, i) => new Date().getFullYear() - 2 + i);

  ngOnInit(): void {
    this.historyMode = !!this.route.snapshot.data['historyMode'];
    this.uncategorizedMode = !!this.route.snapshot.data['uncategorizedMode'];

    if (this.uncategorizedMode) {
      this.filterCategory.set(11);
    } else if (!this.historyMode) {
      this.filterMonth.set(new Date().getMonth() + 1);
    }

    this.categoryService.list().subscribe({ next: cats => this.categories.set(cats) });

    this.searchSubject.pipe(
      debounceTime(400),
      distinctUntilChanged(),
      takeUntil(this.destroy$)
    ).subscribe(() => {
      this.currentPage.set(1);
      this.loadExpenses();
    });

    this.loadExpenses();
  }

  ngOnDestroy(): void {
    this.destroy$.next();
    this.destroy$.complete();
  }

  loadExpenses(): void {
    this.loading.set(true);
    this.expenseService.list({
      month: this.filterMonth() || undefined,
      year: this.filterYear() || undefined,
      category_id: this.filterCategory() ? +this.filterCategory() : undefined,
      payment_method: this.filterPayment() || undefined,
      search: this.searchTerm() || undefined,
      page: this.currentPage(),
      page_size: this.pageSize,
    }).subscribe({
      next: res => {
        this.expenses.set(res.results);
        this.totalCount.set(res.count);
        this.loading.set(false);
      },
      error: () => this.loading.set(false),
    });
  }

  onFilterChange(): void {
    this.currentPage.set(1);
    this.loadExpenses();
  }

  onSearchInput(value: string): void {
    this.searchTerm.set(value);
    this.searchSubject.next(value);
  }

  goToPage(page: number): void {
    if (page < 1 || page > this.totalPages()) return;
    this.currentPage.set(page);
    this.loadExpenses();
  }

  delete(id: number): void {
    if (!confirm('Deseja excluir este gasto?')) return;
    this.deletingId.set(id);
    this.expenseService.delete(id).subscribe({
      next: () => {
        this.expenses.update(list => list.filter(e => e.id !== id));
        this.totalCount.update(c => c - 1);
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

  amountClass(amount: number): string { return amount >= 0 ? 'value-up' : 'value-down'; }
  amountPrefix(amount: number): string { return amount >= 0 ? '+' : '-'; }
}
