import {
  Component, OnInit, OnDestroy, AfterViewInit,
  inject, signal, computed, effect,
  ViewChild, ElementRef,
} from '@angular/core';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { ReactiveFormsModule, FormControl } from '@angular/forms';
import { debounceTime, distinctUntilChanged, Subject, takeUntil } from 'rxjs';
import { Chart, registerables } from 'chart.js';
import { CardService } from '../../../core/services/card.service';
import { ExpenseService } from '../../../core/services/expense.service';
import {
  CreditCard, Expense, Invoice,
  InvoiceExpensesResponse, InvoicePagination,
} from '../../../core/models';

Chart.register(...registerables);

const CAT_COLORS = [
  '#0052ff','#34c759','#ff9f0a','#ff3b30',
  '#af52de','#5ac8fa','#ff6b35','#30b0c7','#a2845e','#636366',
];

@Component({
  selector: 'app-card-expenses',
  standalone: true,
  imports: [RouterLink, ReactiveFormsModule],
  templateUrl: './card-expenses.component.html',
  styleUrls: ['./card-expenses.component.scss'],
})
export class CardExpensesComponent implements OnInit, OnDestroy, AfterViewInit {
  private route      = inject(ActivatedRoute);
  private cardSvc    = inject(CardService);
  private expenseSvc = inject(ExpenseService);
  private destroy$   = new Subject<void>();

  // ── Canvas refs ────────────────────────────────────────────────────────
  @ViewChild('dailyChartCanvas')  dailyCanvas!:  ElementRef<HTMLCanvasElement>;
  @ViewChild('weeklyChartCanvas') weeklyCanvas!: ElementRef<HTMLCanvasElement>;
  @ViewChild('donutChartCanvas')  donutCanvas!:  ElementRef<HTMLCanvasElement>;

  private dailyChart?:  Chart;
  private weeklyChart?: Chart;
  private donutChart?:  Chart;

  // ── State ──────────────────────────────────────────────────────────────
  cardId = 0;
  card              = signal<CreditCard | null>(null);
  invoices          = signal<Invoice[]>([]);
  selectedInvoice   = signal<Invoice | null>(null);
  selectedCategoryId= signal<number | null>(null);
  invoiceData       = signal<InvoiceExpensesResponse | null>(null);
  allExpenses       = signal<Expense[]>([]);   // full list for charts
  loadingInvoices   = signal(true);
  loadingExpenses   = signal(false);
  currentPage       = signal(1);
  readonly pageSize = 20;
  viewReady         = false;

  searchCtrl = new FormControl('');

  // ── Computed ───────────────────────────────────────────────────────────
  pagination = computed((): InvoicePagination | null =>
    this.invoiceData()?.pagination ?? null
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

  filteredExpenses    = computed(() => this.invoiceData()?.expenses ?? []);
  filteredTotal       = computed(() => this.invoiceData()?.summary.total ?? 0);
  totalTransactions   = computed(() => this.invoiceData()?.summary.count  ?? 0);

  // ── Chart data computed ────────────────────────────────────────────────
  dailyChartData = computed(() => {
    const exps = this.allExpenses();
    const inv  = this.selectedInvoice();
    if (!exps.length || !inv) return null;

    const map = new Map<string, number>();
    for (const e of exps) {
      const v = map.get(e.date) ?? 0;
      map.set(e.date, v + Math.abs(e.amount));
    }
    const sorted = [...map.entries()].sort(([a], [b]) => a.localeCompare(b));
    return {
      labels: sorted.map(([d]) => { const [, m, day] = d.split('-'); return `${day}/${m}`; }),
      values: sorted.map(([, v]) => +v.toFixed(2)),
    };
  });

  weeklyChartData = computed(() => {
    const exps = this.allExpenses();
    const inv  = this.selectedInvoice();
    if (!exps.length || !inv) return null;

    const start = new Date(inv.period_start + 'T00:00:00');
    const weeks = [0, 0, 0, 0];
    for (const e of exps) {
      const d    = new Date(e.date + 'T00:00:00');
      const diff = Math.floor((d.getTime() - start.getTime()) / 86400000);
      const w    = Math.min(3, Math.floor(diff / 7));
      if (w >= 0) weeks[w] += Math.abs(e.amount);
    }
    return {
      labels: ['Semana 1','Semana 2','Semana 3','Semana 4'],
      values: weeks.map(v => +v.toFixed(2)),
    };
  });

  donutChartData = computed(() => {
    const cats = this.invoiceData()?.by_category ?? [];
    if (!cats.length) return null;
    const top5  = cats.slice(0, 5);
    const other = cats.slice(5).reduce((s, c) => s + c.total, 0);
    const labels = [...top5.map(c => c.category_name), ...(other > 0 ? ['Outros'] : [])];
    const values = [...top5.map(c => c.total),          ...(other > 0 ? [+other.toFixed(2)] : [])];
    return { labels, values };
  });

  // ── Lifecycle ──────────────────────────────────────────────────────────
  constructor() {
    effect(() => {
      const daily  = this.dailyChartData();
      const weekly = this.weeklyChartData();
      const donut  = this.donutChartData();
      if (!this.viewReady) return;
      if (daily)  this.renderDailyChart(daily);
      if (weekly) this.renderWeeklyChart(weekly);
      if (donut)  this.renderDonutChart(donut);
    });
  }

  ngOnInit(): void {
    this.cardId = +this.route.snapshot.paramMap.get('id')!;
    this.cardSvc.get(this.cardId).subscribe({ next: c => this.card.set(c) });
    this.cardSvc.getInvoices(this.cardId).subscribe({
      next: invoices => {
        this.invoices.set(invoices);
        this.loadingInvoices.set(false);
        const current = invoices.find(i => i.is_current) ?? invoices[0];
        if (current) { this.selectedInvoice.set(current); this.loadAll(current); }
      },
      error: () => this.loadingInvoices.set(false),
    });

    this.searchCtrl.valueChanges.pipe(
      debounceTime(400),
      distinctUntilChanged(),
      takeUntil(this.destroy$),
    ).subscribe(() => { this.currentPage.set(1); this.loadPage(); });
  }

  ngAfterViewInit(): void {
    this.viewReady = true;
    const daily  = this.dailyChartData();
    const weekly = this.weeklyChartData();
    const donut  = this.donutChartData();
    if (daily)  this.renderDailyChart(daily);
    if (weekly) this.renderWeeklyChart(weekly);
    if (donut)  this.renderDonutChart(donut);
  }

  ngOnDestroy(): void {
    this.destroy$.next(); this.destroy$.complete();
    this.dailyChart?.destroy();
    this.weeklyChart?.destroy();
    this.donutChart?.destroy();
  }

  // ── Actions ────────────────────────────────────────────────────────────
  selectInvoice(invoice: Invoice): void {
    this.selectedInvoice.set(invoice);
    this.selectedCategoryId.set(null);
    this.currentPage.set(1);
    this.searchCtrl.setValue('', { emitEvent: false });
    this.loadAll(invoice);
  }

  selectCategory(categoryId: number | null): void {
    this.selectedCategoryId.set(categoryId);
    this.currentPage.set(1);
    this.loadPage();
  }

  changePage(page: number): void {
    this.currentPage.set(page);
    this.loadPage();
  }

  deleteExpense(expense: Expense): void {
    if (!confirm(`Excluir "${expense.description}"? Esta ação não pode ser desfeita.`)) return;
    this.expenseSvc.delete(expense.id).subscribe({
      next:  () => { const inv = this.selectedInvoice(); if (inv) this.loadAll(inv); },
      error: () => alert('Erro ao excluir o gasto. Tente novamente.'),
    });
  }

  clearSearch(): void {
    this.searchCtrl.setValue('');
  }

  // ── Data loading ───────────────────────────────────────────────────────
  private loadAll(invoice: Invoice): void {
    this.loadPage(invoice);
    // Carrega todos os gastos para os gráficos (sem paginação)
    this.cardSvc.getInvoiceExpenses(
      this.cardId, invoice.invoice_month, invoice.invoice_year,
      undefined, 1, 200,
    ).subscribe({ next: d => this.allExpenses.set(d.expenses) });
  }

  private loadPage(invoice?: Invoice): void {
    const inv = invoice ?? this.selectedInvoice();
    if (!inv) return;
    this.loadingExpenses.set(true);
    this.invoiceData.set(null);
    this.cardSvc.getInvoiceExpenses(
      this.cardId, inv.invoice_month, inv.invoice_year,
      this.selectedCategoryId() ?? undefined,
      this.currentPage(), this.pageSize,
      this.searchCtrl.value ?? undefined,
    ).subscribe({
      next:  data => { this.invoiceData.set(data); this.loadingExpenses.set(false); },
      error: ()   => this.loadingExpenses.set(false),
    });
  }

  // ── Chart rendering ────────────────────────────────────────────────────
  private renderDailyChart(data: { labels: string[]; values: number[] }): void {
    this.dailyChart?.destroy();
    if (!this.dailyCanvas) return;
    this.dailyChart = new Chart(this.dailyCanvas.nativeElement, {
      type: 'bar',
      data: {
        labels: data.labels,
        datasets: [{ label: 'R$', data: data.values,
          backgroundColor: '#0052ff33', borderColor: '#0052ff',
          borderWidth: 1.5, borderRadius: 4 }],
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { display: false },
          tooltip: { callbacks: { label: ctx => this.formatAmount(ctx.parsed.y ?? 0) } } },
        scales: {
          x: { grid: { display: false }, ticks: { font: { size: 11 } } },
          y: { grid: { color: '#f0f0f0' },
            ticks: { callback: v => 'R$' + Number(v).toLocaleString('pt-BR'), font: { size: 11 } } },
        },
      },
    });
  }

  private renderWeeklyChart(data: { labels: string[]; values: number[] }): void {
    this.weeklyChart?.destroy();
    if (!this.weeklyCanvas) return;
    this.weeklyChart = new Chart(this.weeklyCanvas.nativeElement, {
      type: 'bar',
      data: {
        labels: data.labels,
        datasets: [{ label: 'R$', data: data.values,
          backgroundColor: ['#0052ff','#3375ff','#6699ff','#99bbff'],
          borderRadius: 6 }],
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { display: false },
          tooltip: { callbacks: { label: ctx => this.formatAmount(ctx.parsed.y ?? 0) } } },
        scales: {
          x: { grid: { display: false } },
          y: { grid: { color: '#f0f0f0' },
            ticks: { callback: v => 'R$' + Number(v).toLocaleString('pt-BR'), font: { size: 11 } } },
        },
      },
    });
  }

  private renderDonutChart(data: { labels: string[]; values: number[] }): void {
    this.donutChart?.destroy();
    if (!this.donutCanvas) return;
    this.donutChart = new Chart(this.donutCanvas.nativeElement, {
      type: 'doughnut',
      data: {
        labels: data.labels,
        datasets: [{ data: data.values,
          backgroundColor: CAT_COLORS.slice(0, data.values.length),
          borderWidth: 2, borderColor: '#fff', hoverOffset: 6 }],
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        cutout: '65%',
        plugins: {
          legend: { position: 'right', labels: { font: { size: 12 }, padding: 12 } },
          tooltip: { callbacks: { label: ctx => {
            const v = ctx.parsed as number;
            const pct = ((v / data.values.reduce((a,b)=>a+b,0))*100).toFixed(1);
            return `${ctx.label}: ${this.formatAmount(v)} (${pct}%)`;
          }}},
        },
      },
    });
  }

  // ── Formatters ─────────────────────────────────────────────────────────
  formatAmount(amount: number): string {
    return new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(Math.abs(amount));
  }

  formatDate(dateStr: string): string {
    const [, m, d] = dateStr.split('-');
    return `${d}/${m}`;
  }

  formatDateFull(dateStr: string): string {
    const [y, m, d] = dateStr.split('-');
    return `${d}/${m}/${y}`;
  }

  roundPct(value: number): number { return Math.round(value); }

  catColor(index: number): string { return CAT_COLORS[index % CAT_COLORS.length]; }
}
