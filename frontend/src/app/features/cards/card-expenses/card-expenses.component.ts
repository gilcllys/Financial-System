import {
  Component,
  OnInit,
  OnDestroy,
  inject,
  signal,
  computed,
  effect,
  ViewChild,
  ElementRef,
} from '@angular/core';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { ReactiveFormsModule, FormControl } from '@angular/forms';
import { Subject } from 'rxjs';
import { debounceTime, distinctUntilChanged, takeUntil } from 'rxjs/operators';
import { Chart, registerables } from 'chart.js';
import { CardService } from '../../../core/services/card.service';
import { ExpenseService } from '../../../core/services/expense.service';
import { SharedDebtService, SharedDebtEntry } from '../../../core/services/shared-debt.service';
import {
  CreditCard,
  Expense,
  Invoice,
  InvoiceExpensesResponse,
  InvoicePagination,
} from '../../../core/models';

Chart.register(...registerables);

const CAT_COLORS = [
  '#0052ff', '#34c759', '#ff9f0a', '#ff3b30',
  '#af52de', '#5ac8fa', '#ff6b35', '#30b0c7',
];

const MONTH_ABBR = ['Jan','Fev','Mar','Abr','Mai','Jun','Jul','Ago','Set','Out','Nov','Dez'];

@Component({
  selector: 'app-card-expenses',
  standalone: true,
  imports: [RouterLink, ReactiveFormsModule],
  templateUrl: './card-expenses.component.html',
  styleUrls: ['./card-expenses.component.scss'],
})
export class CardExpensesComponent implements OnInit, OnDestroy {
  private route      = inject(ActivatedRoute);
  private cardSvc    = inject(CardService);
  private expenseSvc = inject(ExpenseService);
  private sharedSvc  = inject(SharedDebtService);
  private destroy$   = new Subject<void>();

  // â”€â”€ Canvas refs (static:false â€” canvases live inside @if blocks) â”€â”€â”€â”€â”€â”€
  @ViewChild('dailyChartCanvas')  dailyCanvas?:  ElementRef<HTMLCanvasElement>;
  @ViewChild('weeklyChartCanvas') weeklyCanvas?: ElementRef<HTMLCanvasElement>;
  @ViewChild('donutChartCanvas')  donutCanvas?:  ElementRef<HTMLCanvasElement>;
  @ViewChild('monthlyChartCanvas') monthlyCanvas?: ElementRef<HTMLCanvasElement>;

  private dailyChart?:  Chart;
  private weeklyChart?: Chart;
  private donutChart?:  Chart;
  private monthlyChart?: Chart;
  private readonly installmentRe = /parcela\s+(\d+)\/(\d+)/i;

  // â”€â”€ State signals â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
  cardId = 0;
  card               = signal<CreditCard | null>(null);
  invoices           = signal<Invoice[]>([]);
  selectedInvoice    = signal<Invoice | null>(null);
  selectedCategoryId = signal<number | null>(null);
  invoiceData        = signal<InvoiceExpensesResponse | null>(null);
  /** Full invoice snapshot (page_size=200, no filters) â€” used for charts. */
  chartData          = signal<InvoiceExpensesResponse | null>(null);
  allCardExpenses    = signal<Expense[]>([]);
  sharedEntries      = signal<SharedDebtEntry[]>([]);

  /** Shared entries filtradas pelo periodo da fatura selecionada (igual a despesas pessoais). */
  filteredSharedEntries = computed((): SharedDebtEntry[] => {
    const inv = this.selectedInvoice();
    if (!inv) return [];
    return this.sharedEntries().filter(e => e.date >= inv.period_start && e.date <= inv.period_end);
  });

  sharedInstallments = computed((): SharedDebtEntry[] =>
    this.filteredSharedEntries().filter(e => e.total_installments > 1)
  );

  sharedNormal = computed((): SharedDebtEntry[] =>
    this.filteredSharedEntries().filter(e => e.total_installments === 1)
  );
  loadingInvoices    = signal(true);
  loadingExpenses    = signal(false);
  loadingChart       = signal(false);
  currentPage        = signal(1);
  readonly pageSize  = 20;

  searchControl = new FormControl<string>('', { nonNullable: true });

  // â”€â”€ Computed â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
  pagination = computed((): InvoicePagination | null =>
    this.invoiceData()?.pagination ?? null,
  );

  pageRange = computed((): number[] => {
    const p = this.pagination();
    if (!p) return [];
    const total   = p.total_pages;
    const current = this.currentPage();
    const start   = Math.max(1, current - 2);
    const end     = Math.min(total, current + 2);
    return Array.from({ length: end - start + 1 }, (_, i) => start + i);
  });

  selectedCategoryName = computed(() => {
    const catId = this.selectedCategoryId();
    const data  = this.invoiceData();
    if (!catId || !data) return null;
    return data.by_category.find(c => c.category_id === catId)?.category_name ?? null;
  });

  filteredExpenses  = computed(() => this.invoiceData()?.expenses ?? []);
  installmentExpenses = computed(() => this.filteredExpenses().filter(e => this.isInstallment(e)));
  normalExpenses = computed(() => this.filteredExpenses().filter(e => !this.isInstallment(e)));
  filteredTotal     = computed(() => this.invoiceData()?.summary.total ?? 0);
  totalTransactions = computed(() => this.invoiceData()?.summary.count  ?? 0);

  /**
   * Category list for the dropdown â€” always unfiltered (uses chartData when
   * available, falls back to invoiceData which may be filtered).
   */
  dropdownCategories = computed(() =>
    this.chartData()?.by_category ?? this.invoiceData()?.by_category ?? [],
  );

  // â”€â”€ Chart data: computed from the 200-expense chartData snapshot â”€â”€â”€â”€â”€â”€â”€
  private dailyChartDataSig = computed(() => {
    const data = this.chartData();
    if (!data?.expenses.length) return null;
    const map = new Map<string, number>();
    for (const e of data.expenses) {
      map.set(e.date, (map.get(e.date) ?? 0) + Math.abs(e.amount));
    }
    const sorted = [...map.entries()].sort(([a], [b]) => a.localeCompare(b));
    return {
      labels: sorted.map(([d]) => { const [, m, day] = d.split('-'); return `${day}/${m}`; }),
      values: sorted.map(([, v]) => +v.toFixed(2)),
    };
  });

  private weeklyChartDataSig = computed(() => {
    const data = this.chartData();
    if (!data?.expenses.length) return null;
    const start = new Date(data.period_start + 'T00:00:00');
    const end   = new Date(data.period_end   + 'T00:00:00');
    const totalMs = end.getTime() - start.getTime() + 86_400_000;
    const segMs   = Math.ceil(totalMs / 4);
    const segments = Array.from({ length: 4 }, (_, i) => {
      const segStart = new Date(start.getTime() + i * segMs);
      const segEnd   = new Date(Math.min(
        start.getTime() + (i + 1) * segMs - 86_400_000,
        end.getTime(),
      ));
      const s = segStart.toISOString().slice(0, 10);
      const e = segEnd.toISOString().slice(0, 10);
      const total = data.expenses
        .filter(exp => exp.date >= s && exp.date <= e)
        .reduce((acc, exp) => acc + Math.abs(exp.amount), 0);
      return { label: `Sem ${i + 1}`, total: +total.toFixed(2) };
    });
    return {
      labels: segments.map(s => s.label),
      values: segments.map(s => s.total),
    };
  });

  private donutChartDataSig = computed(() => {
    const cats = this.chartData()?.by_category ?? [];
    if (!cats.length) return null;
    const top5  = cats.slice(0, 5);
    const other = cats.slice(5).reduce((s, c) => s + Math.abs(c.total), 0);
    return {
      labels: [...top5.map(c => c.category_name), ...(other > 0 ? ['Outros'] : [])],
      values: [...top5.map(c => +Math.abs(c.total).toFixed(2)), ...(other > 0 ? [+other.toFixed(2)] : [])],
    };
  });

  monthlyChartDataSig = computed(() => {
    const year = this.selectedInvoice()?.invoice_year ?? new Date().getFullYear();
    const totals = Array.from({ length: 12 }, () => 0);
    for (const e of this.allCardExpenses()) {
      const [expenseYear, expenseMonth] = e.date.split('-').map(Number);
      if (expenseYear === year && expenseMonth >= 1 && expenseMonth <= 12) {
        totals[expenseMonth - 1] += Math.abs(e.amount);
      }
    }
    if (!totals.some(total => total > 0)) return null;
    return {
      labels: MONTH_ABBR,
      values: totals.map(total => +total.toFixed(2)),
    };
  });

  // â”€â”€ Constructor: effect redraws charts whenever chartData changes â”€â”€â”€â”€â”€â”€
  constructor() {
    effect(() => {
      const daily  = this.dailyChartDataSig();
      const weekly = this.weeklyChartDataSig();
      const donut  = this.donutChartDataSig();
      const monthly = this.monthlyChartDataSig();
      if (!daily) { this.dailyChart?.destroy(); this.dailyChart = undefined; }
      if (!weekly) { this.weeklyChart?.destroy(); this.weeklyChart = undefined; }
      if (!donut) { this.donutChart?.destroy(); this.donutChart = undefined; }
      if (!monthly) { this.monthlyChart?.destroy(); this.monthlyChart = undefined; }
      if (!daily && !weekly && !donut && !monthly) {
        return;
      }
      // setTimeout(50): lets @if(chartData()) re-render the canvases before we paint
      setTimeout(() => {
        if (daily)  this.renderDailyChart(daily);
        if (weekly) this.renderWeeklyChart(weekly);
        if (donut)  this.renderDonutChart(donut);
        if (monthly) this.renderMonthlyChart(monthly);
      }, 50);
    });
  }

  // â”€â”€ Lifecycle â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
  ngOnInit(): void {
    this.cardId = +this.route.snapshot.paramMap.get('id')!;
    this.cardSvc.get(this.cardId).subscribe({ next: c => this.card.set(c) });
    this.cardSvc.getAllCardExpenses(this.cardId).subscribe({ next: e => this.allCardExpenses.set(e) });
    this.sharedSvc.listEntries({ credit_card: this.cardId }).subscribe({ next: res => this.sharedEntries.set(res.results) });
    this.cardSvc.getInvoices(this.cardId).subscribe({
      next: invoices => {
        this.invoices.set(invoices);
        this.loadingInvoices.set(false);
        const current = invoices.find(i => i.is_current) ?? invoices[0];
        if (current) {
          this.selectedInvoice.set(current);
          this.loadPage(current);
          this.loadChart(current);
        }
      },
      error: () => this.loadingInvoices.set(false),
    });

    // Debounced search â€” resets page 1, reloads expenses only (not charts)
    this.searchControl.valueChanges.pipe(
      debounceTime(400),
      distinctUntilChanged(),
      takeUntil(this.destroy$),
    ).subscribe(() => {
      this.currentPage.set(1);
      this.loadPage();
    });
  }

  ngOnDestroy(): void {
    this.destroy$.next();
    this.destroy$.complete();
    this.dailyChart?.destroy();
    this.weeklyChart?.destroy();
    this.donutChart?.destroy();
    this.monthlyChart?.destroy();
  }

  // â”€â”€ User actions â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
  selectInvoice(invoice: Invoice): void {
    this.selectedInvoice.set(invoice);
    this.selectedCategoryId.set(null);
    this.currentPage.set(1);
    this.searchControl.setValue('', { emitEvent: false });
    this.chartData.set(null);   // clears charts immediately; effect destroys instances
    this.loadPage(invoice);
    this.loadChart(invoice);
  }

  selectCategory(categoryId: number | null): void {
    this.selectedCategoryId.set(categoryId);
    this.currentPage.set(1);
    this.loadPage();
  }

  onCategorySelectChange(event: Event): void {
    const val = (event.target as HTMLSelectElement).value;
    this.selectCategory(val ? +val : null);
  }

  clearSearch(): void {
    this.searchControl.setValue('');
  }

  changePage(page: number): void {
    this.currentPage.set(page);
    this.loadPage();
  }

  deleteExpense(expense: Expense): void {
    if (!confirm(`Excluir "${expense.description}"? Esta aÃ§Ã£o nÃ£o pode ser desfeita.`)) return;
    this.expenseSvc.delete(expense.id).subscribe({
      next:  () => { const inv = this.selectedInvoice(); if (inv) this.loadPage(inv); },
      error: () => alert('Erro ao excluir o gasto. Tente novamente.'),
    });
  }

  // â”€â”€ Data loading â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
  private loadPage(invoice?: Invoice): void {
    const inv = invoice ?? this.selectedInvoice();
    if (!inv) return;
    this.loadingExpenses.set(true);
    this.invoiceData.set(null);
    this.cardSvc.getInvoiceExpenses(
      this.cardId,
      inv.invoice_month,
      inv.invoice_year,
      this.selectedCategoryId() ?? undefined,
      this.currentPage(),
      this.pageSize,
      this.searchControl.value || undefined,
    ).subscribe({
      next:  data => { this.invoiceData.set(data); this.loadingExpenses.set(false); },
      error: ()   => this.loadingExpenses.set(false),
    });
  }

  /** Fetches up to 200 expenses (no filters) for chart aggregation. */
  private loadChart(invoice: Invoice): void {
    this.loadingChart.set(true);
    this.cardSvc.getInvoiceChart(
      this.cardId,
      invoice.invoice_month,
      invoice.invoice_year,
    ).subscribe({
      next:  data => { this.chartData.set(data); this.loadingChart.set(false); },
      error: ()   => this.loadingChart.set(false),
    });
  }

  // â”€â”€ Chart rendering â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
  private renderDailyChart(data: { labels: string[]; values: number[] }): void {
    this.dailyChart?.destroy();
    const canvas = this.dailyCanvas?.nativeElement;
    if (!canvas) return;
    this.dailyChart = new Chart(canvas, {
      type: 'bar',
      data: {
        labels: data.labels,
        datasets: [{
          label: 'Gastos (R$)',
          data: data.values,
          backgroundColor: 'rgba(0,82,255,0.70)',
          borderRadius: 5,
          borderSkipped: false,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: { callbacks: { label: ctx => ` ${this.formatAmount(ctx.parsed.y ?? 0)}` } },
        },
        scales: {
          x: { grid: { display: false }, ticks: { font: { size: 11 } } },
          y: {
            beginAtZero: true,
            grid: { color: 'rgba(0,0,0,0.05)' },
            ticks: {
              font: { size: 11 },
              callback: v => new Intl.NumberFormat('pt-BR', {
                style: 'currency', currency: 'BRL', maximumFractionDigits: 0,
              }).format(+v),
            },
          },
        },
      },
    });
  }

  private renderWeeklyChart(data: { labels: string[]; values: number[] }): void {
    this.weeklyChart?.destroy();
    const canvas = this.weeklyCanvas?.nativeElement;
    if (!canvas) return;
    this.weeklyChart = new Chart(canvas, {
      type: 'bar',
      data: {
        labels: data.labels,
        datasets: [{
          label: 'Gastos (R$)',
          data: data.values,
          backgroundColor: [
            'rgba(0,82,255,0.85)', 'rgba(0,82,255,0.65)',
            'rgba(0,82,255,0.45)', 'rgba(0,82,255,0.28)',
          ],
          borderRadius: 5,
          borderSkipped: false,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: { callbacks: { label: ctx => ` ${this.formatAmount(ctx.parsed.y ?? 0)}` } },
        },
        scales: {
          x: { grid: { display: false } },
          y: {
            beginAtZero: true,
            grid: { color: 'rgba(0,0,0,0.05)' },
            ticks: {
              font: { size: 11 },
              callback: v => new Intl.NumberFormat('pt-BR', {
                style: 'currency', currency: 'BRL', maximumFractionDigits: 0,
              }).format(+v),
            },
          },
        },
      },
    });
  }

  private renderDonutChart(data: { labels: string[]; values: number[] }): void {
    this.donutChart?.destroy();
    const canvas = this.donutCanvas?.nativeElement;
    if (!canvas) return;
    const total = data.values.reduce((a, b) => a + b, 0);
    this.donutChart = new Chart(canvas, {
      type: 'doughnut',
      data: {
        labels: data.labels,
        datasets: [{
          data: data.values,
          backgroundColor: CAT_COLORS.slice(0, data.values.length),
          borderWidth: 2,
          borderColor: '#ffffff',
          hoverOffset: 6,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        cutout: '65%',
        plugins: {
          legend: { position: 'right', labels: { font: { size: 12 }, padding: 12, boxWidth: 12 } },
          tooltip: {
            callbacks: {
              label: ctx => {
                const v   = ctx.parsed as number;
                const pct = total > 0 ? ((v / total) * 100).toFixed(1) : '0';
                return ` ${this.formatAmount(v)} (${pct}%)`;
              },
            },
          },
        },
      },
    });
  }

  private renderMonthlyChart(data: { labels: string[]; values: number[] }): void {
    this.monthlyChart?.destroy();
    const canvas = this.monthlyCanvas?.nativeElement;
    if (!canvas) return;
    this.monthlyChart = new Chart(canvas, {
      type: 'bar',
      data: {
        labels: data.labels,
        datasets: [{
          label: 'Gastos (R$)',
          data: data.values,
          backgroundColor: 'rgba(0,82,255,0.70)',
          borderRadius: 5,
          borderSkipped: false,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: { callbacks: { label: ctx => ` ${this.formatAmount(ctx.parsed.y ?? 0)}` } },
        },
        scales: {
          x: { grid: { display: false }, ticks: { font: { size: 11 } } },
          y: {
            beginAtZero: true,
            grid: { color: 'rgba(0,0,0,0.05)' },
            ticks: {
              font: { size: 11 },
              callback: v => new Intl.NumberFormat('pt-BR', {
                style: 'currency', currency: 'BRL', maximumFractionDigits: 0,
              }).format(+v),
            },
          },
        },
      },
    });
  }

  // â”€â”€ Formatters â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
  formatAmount(amount: number): string {
    return new Intl.NumberFormat('pt-BR', {
      style: 'currency', currency: 'BRL',
    }).format(Math.abs(amount));
  }

  /** dd/MM/yyyy for period labels */
  formatDateFull(dateStr: string): string {
    const [y, m, d] = dateStr.split('-');
    return `${d}/${m}/${y}`;
  }

  /** dd/MM for compact table dates */
  formatDate(dateStr: string): string {
    const [, m, d] = dateStr.split('-');
    return `${d}/${m}`;
  }

  roundPct(value: number): number { return Math.round(value); }

  isInstallment(e: Expense): boolean { return this.installmentRe.test(e.description); }

  installmentBadge(e: Expense): string | null {
    const m = this.installmentRe.exec(e.description);
    return m ? `${m[1]}/${m[2]}` : null;
  }

  catColor(index: number): string { return CAT_COLORS[index % CAT_COLORS.length]; }
}
