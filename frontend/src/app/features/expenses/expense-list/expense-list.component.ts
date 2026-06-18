import {
  Component, OnInit, OnDestroy, AfterViewInit,
  inject, signal, computed, ViewChild, ElementRef
} from '@angular/core';
import { RouterLink, ActivatedRoute } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { Subject, debounceTime, distinctUntilChanged, takeUntil } from 'rxjs';
import { ExpenseService } from '../../../core/services/expense.service';
import { CategoryService } from '../../../core/services/category.service';
import { AnalyticsService, HomeCharts } from '../../../core/services/analytics.service';
import { SlicePipe } from '@angular/common';
import { Expense, ExpenseCategory, PaymentMethod } from '../../../core/models';
import { Chart, registerables } from 'chart.js';

Chart.register(...registerables);

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
export class ExpenseListComponent implements OnInit, OnDestroy, AfterViewInit {
  private expenseService = inject(ExpenseService);
  private categoryService = inject(CategoryService);
  private analyticsService = inject(AnalyticsService);
  private route = inject(ActivatedRoute);

  historyMode = false;
  uncategorizedMode = false;
  private destroy$ = new Subject<void>();
  private searchSubject = new Subject<string>();
  private chartsReady = false;
  private dataReady = false;

  // Chart refs
  @ViewChild('categoryChart') categoryChartRef!: ElementRef<HTMLCanvasElement>;
  @ViewChild('dailyChart')    dailyChartRef!: ElementRef<HTMLCanvasElement>;
  @ViewChild('weeklyChart')   weeklyChartRef!: ElementRef<HTMLCanvasElement>;
  private charts: Chart[] = [];

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
  filterPayment = signal<PaymentMethod | ''>('');
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

  ngAfterViewInit(): void {
    this.chartsReady = true;
    if (this.dataReady && !this.historyMode && !this.uncategorizedMode) {
      this.renderCharts();
    }
  }

  ngOnDestroy(): void {
    this.charts.forEach(c => c.destroy());
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
        if (!this.historyMode && !this.uncategorizedMode) {
          this.dataReady = true;
          if (this.chartsReady) this.renderCharts();
        }
      },
      error: () => this.loading.set(false),
    });
  }

  private renderCharts(): void {
    this.charts.forEach(c => c.destroy());
    this.charts = [];

    const month = this.filterMonth() || new Date().getMonth() + 1;
    const year = this.filterYear();

    // Uma única chamada ao backend — endpoint otimizado home-charts
    this.analyticsService.homeCharts(month, year).subscribe(data => {
      // 1) Por categoria (doughnut)
      if (this.categoryChartRef && data.by_category.length) {
        const ctx = this.categoryChartRef.nativeElement.getContext('2d')!;
        this.charts.push(new Chart(ctx, {
          type: 'doughnut',
          data: {
            labels: data.by_category.map(d => d.category_name),
            datasets: [{
              data: data.by_category.map(d => d.total),
              backgroundColor: ['#0052FF','#1DB954','#FF6B35','#9B59B6','#E74C3C','#F39C12','#1ABC9C','#3498DB','#E67E22','#2ECC71','#E91E63','#607D8B'],
            }]
          },
          options: {
            responsive: true, maintainAspectRatio: false,
            plugins: { legend: { position: 'right', labels: { font: { size: 11 } } } }
          }
        }));
      }

      // 2) Gasto diário (bar)
      if (this.dailyChartRef) {
        const activeDays = data.daily.filter(d => d.total > 0);
        const ctx = this.dailyChartRef.nativeElement.getContext('2d')!;
        this.charts.push(new Chart(ctx, {
          type: 'bar',
          data: {
            labels: activeDays.map(d => `Dia ${d.day}`),
            datasets: [{
              label: 'Gasto (R$)',
              data: activeDays.map(d => d.total),
              backgroundColor: '#0052FF88',
              borderColor: '#0052FF',
              borderWidth: 1,
            }]
          },
          options: {
            responsive: true, maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            scales: { y: { beginAtZero: true, ticks: { callback: (v: any) => `R$${v}` } } }
          }
        }));
      }

      // 3) Gasto por semana (line)
      if (this.weeklyChartRef) {
        const ctx = this.weeklyChartRef.nativeElement.getContext('2d')!;
        this.charts.push(new Chart(ctx, {
          type: 'line',
          data: {
            labels: data.weekly.map(w => w.label),
            datasets: [{
              label: 'Gasto (R$)',
              data: data.weekly.map(w => w.total),
              borderColor: '#0052FF',
              backgroundColor: '#0052FF22',
              fill: true,
              tension: 0.4,
              pointRadius: 5,
              pointBackgroundColor: '#0052FF',
            }]
          },
          options: {
            responsive: true, maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            scales: { y: { beginAtZero: true, ticks: { callback: (v: any) => `R$${v}` } } }
          }
        }));
      }
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
