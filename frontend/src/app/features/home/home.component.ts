import {
  Component, OnInit, OnDestroy, AfterViewInit,
  ElementRef, ViewChild, inject, signal, computed
} from '@angular/core';
import { RouterLink } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { DatePipe, SlicePipe } from '@angular/common';
import { Subject, debounceTime, distinctUntilChanged, takeUntil } from 'rxjs';
import { Chart, registerables } from 'chart.js';

import { HomeService, InstallmentGroup } from '../../core/services/home.service';
import { ExpenseService } from '../../core/services/expense.service';
import { CategoryService } from '../../core/services/category.service';
import { AnalyticsService, MonthlyAnalytics, CategoryAnalytics, ConsolidatedSummary } from '../../core/services/analytics.service';
import { OpenInvoice, Expense, ExpenseCategory } from '../../core/models';
import { SharedDebtHomeSummary } from '../../core/services/shared-debt.service';

Chart.register(...registerables);

const MONTH_NAMES = [
  'Janeiro','Fevereiro','Março','Abril','Maio','Junho',
  'Julho','Agosto','Setembro','Outubro','Novembro','Dezembro'
];

const EMPTY_CONSOLIDATED: ConsolidatedSummary = {
  month: 0, year: 0,
  income: 0, cash_expenses: 0, cash_count: 0,
  card_invoices: 0, card_invoices_count: 0, card_invoices_detail: [],
  shared_my_portion: 0, shared_count: 0,
  total_expenses: 0, balance: 0,
};

@Component({
  selector: 'app-home',
  standalone: true,
  imports: [RouterLink, FormsModule, SlicePipe, DatePipe],
  templateUrl: './home.component.html',
  styleUrls: ['./home.component.scss'],
})
export class HomeComponent implements OnInit, OnDestroy, AfterViewInit {
  @ViewChild('evolutionChart') chartCanvas!: ElementRef<HTMLCanvasElement>;

  private homeService      = inject(HomeService);
  private expenseService   = inject(ExpenseService);
  private categoryService  = inject(CategoryService);
  private analyticsService = inject(AnalyticsService);
  private destroy$         = new Subject<void>();
  private searchSubject    = new Subject<string>();

  // ── Dashboard state ──────────────────────────────────────────────────────
  dashLoading        = signal(true);
  consolidated       = signal<ConsolidatedSummary>(EMPTY_CONSOLIDATED);
  openInvoices       = signal<OpenInvoice[]>([]);
  sharedDebts        = signal<SharedDebtHomeSummary[]>([]);
  byCategory         = signal<CategoryAnalytics[]>([]);
  evolution          = signal<MonthlyAnalytics[]>([]);
  installmentGroups  = signal<InstallmentGroup[]>([]);

  // ── Filter / table state ─────────────────────────────────────────────────
  tableLoading   = signal(true);
  expenses       = signal<Expense[]>([]);
  categories     = signal<ExpenseCategory[]>([]);
  deletingId     = signal<number | null>(null);
  totalCount     = signal(0);
  currentPage    = signal(1);
  pageSize       = 20;

  filterMonth    = signal(new Date().getMonth() + 1);
  filterYear     = signal(new Date().getFullYear());
  filterCategory = signal<number | ''>('');
  searchTerm     = signal('');

  // ── Constants ────────────────────────────────────────────────────────────
  readonly months = MONTH_NAMES.map((label, i) => ({ value: i + 1, label }));
  readonly years  = Array.from({ length: 5 }, (_, i) => new Date().getFullYear() - 2 + i);
  readonly Math   = Math;

  get currentMonthName() { return MONTH_NAMES[this.filterMonth() - 1]; }
  get currentYear()      { return this.filterYear(); }

  totalPages    = computed(() => Math.ceil(this.totalCount() / this.pageSize));
  pageNumbers   = computed(() => Array.from({ length: this.totalPages() }, (_, i) => i + 1));
  totalInvoices = computed(() => this.openInvoices().reduce((s, i) => s + i.total, 0));
  maxCategory   = computed(() => Math.max(...this.byCategory().map(c => c.total), 1));

  /** Parcelas ativas (ainda não quitadas) — máximo 4 no preview */
  activeInstallments = computed(() =>
    this.installmentGroups().filter(g => g.paidInstallments < g.totalInstallments).slice(0, 4)
  );

  totalRemainingInstallments = computed(() =>
    this.installmentGroups().reduce((s, g) => s + g.remainingAmount, 0)
  );

  // ── Chart ────────────────────────────────────────────────────────────────
  private chart: Chart | null = null;
  private pendingChartData: MonthlyAnalytics[] | null = null;

  // ────────────────────────────────────────────────────────────────────────
  ngOnInit(): void {
    this.categoryService.list().subscribe({ next: cats => this.categories.set(cats) });

    this.searchSubject.pipe(
      debounceTime(400),
      distinctUntilChanged(),
      takeUntil(this.destroy$)
    ).subscribe(() => { this.currentPage.set(1); this.loadTable(); });

    this.loadDashboard();
    this.loadTable();
  }

  ngAfterViewInit(): void {
    this.initChart([]);
    if (this.pendingChartData) {
      this.updateChart(this.pendingChartData);
      this.pendingChartData = null;
    }
  }

  ngOnDestroy(): void {
    this.destroy$.next();
    this.destroy$.complete();
    this.chart?.destroy();
  }

  // ── Dashboard load ────────────────────────────────────────────────────────
  private loadDashboard(): void {
    this.dashLoading.set(true);
    this.homeService.load(this.filterMonth(), this.filterYear())
      .pipe(takeUntil(this.destroy$))
      .subscribe({
        next: data => {
          this.consolidated.set(data.consolidated);
          this.openInvoices.set(data.openInvoices);
          this.sharedDebts.set(data.sharedDebts);
          this.byCategory.set(data.byCategory);
          this.installmentGroups.set(data.installmentGroups);
          this.dashLoading.set(false);
          if (this.chart) this.updateChart(data.evolution);
          else this.pendingChartData = data.evolution;
        },
        error: () => this.dashLoading.set(false),
      });
  }

  // ── Table + KPIs load (recarrega ao mudar filtro) ─────────────────────────
  loadTable(): void {
    this.tableLoading.set(true);
    this.expenseService.list({
      month:       this.filterMonth() || undefined,
      year:        this.filterYear()  || undefined,
      category_id: this.filterCategory() ? +this.filterCategory() : undefined,
      search:      this.searchTerm() || undefined,
      page:        this.currentPage(),
      page_size:   this.pageSize,
    }).pipe(takeUntil(this.destroy$))
      .subscribe({
        next: res => {
          this.expenses.set(res.results);
          this.totalCount.set(res.count);
          this.tableLoading.set(false);
        },
        error: () => this.tableLoading.set(false),
      });

    // KPIs consolidados: recarrega ao trocar mês/ano
    this.analyticsService.consolidatedSummary(this.filterMonth(), this.filterYear())
      .pipe(takeUntil(this.destroy$))
      .subscribe({ next: data => this.consolidated.set(data) });

    // Categorias: recarrega ao trocar mês/ano
    this.analyticsService.homeCharts(this.filterMonth(), this.filterYear())
      .pipe(takeUntil(this.destroy$))
      .subscribe({ next: data => this.byCategory.set(data.by_category) });
  }

  onFilterChange(): void { this.currentPage.set(1); this.loadTable(); }

  onSearchInput(value: string): void {
    this.searchTerm.set(value);
    this.searchSubject.next(value);
  }

  goToPage(page: number): void {
    if (page < 1 || page > this.totalPages()) return;
    this.currentPage.set(page);
    this.loadTable();
  }

  delete(id: number): void {
    if (!confirm('Deseja excluir este gasto?')) return;
    this.deletingId.set(id);
    this.expenseService.delete(id).subscribe({
      next: () => {
        this.expenses.update(list => list.filter(e => e.id !== id));
        this.totalCount.update(c => c - 1);
        this.deletingId.set(null);
        this.loadTable();
      },
      error: () => this.deletingId.set(null),
    });
  }

  // ── Helpers ──────────────────────────────────────────────────────────────
  categoryName(id: number): string {
    return this.categories().find(c => c.id === id)?.name ?? '—';
  }

  formatCurrency(value: number): string {
    return new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(Math.abs(value));
  }

  amountClass(amount: number): string  { return amount >= 0 ? 'value--up' : 'value--down'; }
  amountPrefix(amount: number): string { return amount >= 0 ? '+' : '-'; }

  categoryBarWidth(total: number): string {
    return `${Math.min((total / this.maxCategory()) * 100, 100)}%`;
  }

  progressPct(g: InstallmentGroup): number {
    return Math.round((g.paidInstallments / g.totalInstallments) * 100);
  }

  daysLabel(days: number): string {
    if (days < 0) return 'Fechada';
    if (days === 0) return 'Fecha hoje';
    if (days === 1) return 'Fecha amanhã';
    return `Fecha em ${days} dias`;
  }

  daysClass(days: number): string {
    if (days <= 3) return 'badge--red';
    if (days <= 7) return 'badge--yellow';
    return 'badge--green';
  }

  // ── Chart ────────────────────────────────────────────────────────────────
  private initChart(data: MonthlyAnalytics[]): void {
    const ctx = this.chartCanvas?.nativeElement?.getContext('2d');
    if (!ctx) return;
    this.chart = new Chart(ctx, {
      type: 'line',
      data: {
        labels: data.map(d => d.month_name.substring(0, 3)),
        datasets: [
          {
            label: 'Receitas',
            data: data.map(d => d.income),
            borderColor: '#10b981', backgroundColor: 'rgba(16,185,129,0.08)',
            tension: 0.4, fill: true, pointRadius: 4, pointBackgroundColor: '#10b981', borderWidth: 2.5,
          },
          {
            label: 'Despesas',
            data: data.map(d => Math.abs(d.expenses)),
            borderColor: '#ef4444', backgroundColor: 'rgba(239,68,68,0.06)',
            tension: 0.4, fill: true, pointRadius: 4, pointBackgroundColor: '#ef4444', borderWidth: 2.5,
          },
          {
            label: 'Saldo',
            data: data.map(d => d.balance),
            borderColor: '#2563eb', backgroundColor: 'rgba(37,99,235,0.06)',
            tension: 0.4, fill: false, pointRadius: 4, pointBackgroundColor: '#2563eb',
            borderWidth: 2.5, borderDash: [5, 3],
          },
        ],
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: ctx => ' R$ ' + (ctx.raw as number).toLocaleString('pt-BR', { minimumFractionDigits: 2 }),
            },
          },
        },
        scales: {
          y: {
            grid: { color: '#f3f4f6' },
            ticks: { callback: v => `R$ ${(+v / 1000).toFixed(0)}k`, font: { size: 11 } },
            border: { display: false },
          },
          x: {
            grid: { display: false },
            ticks: { font: { size: 11 } },
            border: { display: false },
          },
        },
      },
    });
  }

  private updateChart(data: MonthlyAnalytics[]): void {
    if (!this.chart) { this.initChart(data); return; }
    this.chart.data.labels = data.map(d => d.month_name.substring(0, 3));
    this.chart.data.datasets[0].data = data.map(d => d.income);
    this.chart.data.datasets[1].data = data.map(d => Math.abs(d.expenses));
    this.chart.data.datasets[2].data = data.map(d => d.balance);
    this.chart.update();
  }
}
