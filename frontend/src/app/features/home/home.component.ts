import {
  Component, OnInit, OnDestroy, AfterViewInit,
  ElementRef, ViewChild, inject, signal, computed, effect
} from '@angular/core';
import { ReactiveFormsModule, FormBuilder, Validators } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { CurrencyPipe, DatePipe, SlicePipe } from '@angular/common';
import { Subject, debounceTime, distinctUntilChanged, takeUntil } from 'rxjs';

import { HomeService, InstallmentGroup } from '../../core/services/home.service';
import { CategoryService } from '../../core/services/category.service';
import { AnalyticsService, MonthlyAnalytics, CategoryAnalytics, ConsolidatedSummary } from '../../core/services/analytics.service';
import { OpenInvoice, Expense, ExpenseCategory } from '../../core/models';
import { ExpenseService, RecurringExpenseTemplate, GenerateMonthResult } from '../../core/services/expense.service';
import * as d3 from 'd3';
import { SharedDebtService, SharedDebtHomeSummary, SharedDebtEntry } from '../../core/services/shared-debt.service';

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
  imports: [CurrencyPipe, ReactiveFormsModule, RouterLink, FormsModule, SlicePipe, DatePipe],
  templateUrl: './home.component.html',
  styleUrls: ['./home.component.scss'],
})
export class HomeComponent implements OnInit, OnDestroy, AfterViewInit {
  private homeService      = inject(HomeService);
  private expenseService   = inject(ExpenseService);
  private categoryService  = inject(CategoryService);
  private analyticsService = inject(AnalyticsService);
  private sharedDebtService = inject(SharedDebtService);
  private expSvc = inject(ExpenseService);
  private fb = inject(FormBuilder);

  recurringTemplates = signal<RecurringExpenseTemplate[]>([]);
  showRecurringSection = signal(false);
  showRecurringForm = signal(false);
  savingRecurring = signal(false);
  recurringError = signal('');
  generateResult = signal<GenerateMonthResult | null>(null);
  recurringForm = this.fb.group({
    description: ['', Validators.required],
    amount: [null as number | null, [Validators.required, Validators.min(0.01)]],
    day_of_month: [1, [Validators.required, Validators.min(1), Validators.max(28)]],
    payment_method: ['dinheiro' as 'dinheiro' | 'cartao', Validators.required],
    category_id: [null as number | null],
  });
  private destroy$         = new Subject<void>();
  private searchSubject    = new Subject<string>();

  // ── Dashboard state ──────────────────────────────────────────────────────
  dashLoading        = signal(true);
  consolidated       = signal<ConsolidatedSummary>(EMPTY_CONSOLIDATED);
  openInvoices       = signal<OpenInvoice[]>([]);
  sharedDebts        = signal<SharedDebtHomeSummary[]>([]);

  // ── Tabs "Todos os Gastos" ───────────────────────────────────────────────
  activeTab           = signal<'individual' | 'compartilhada'>('individual');
  sharedEntries       = signal<SharedDebtEntry[]>([]);
  sharedEntriesLoading = signal(false);
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
  // ponytail: this exists — soma my_portion de todos os grupos para o chip de resumo
  groupsNetBalance = computed(() =>
    this.sharedDebts().reduce((s, g) => s - g.my_portion, 0)
  );


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

  ngAfterViewInit(): void { }

  ngOnDestroy(): void {
    this.destroy$.next();
    this.destroy$.complete();
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
          this.evolution.set(data.evolution);
          this.dashLoading.set(false);
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

  onFilterChange(): void {
    this.currentPage.set(1);
    this.loadTable();
    if (this.activeTab() === 'compartilhada') this.loadSharedEntries();
    this.loadRecurringTemplates();
  }

  switchTab(tab: 'individual' | 'compartilhada'): void {
    this.activeTab.set(tab);
    if (tab === 'compartilhada' && this.sharedEntries().length === 0) {
      this.loadSharedEntries();
    }
  }

  loadSharedEntries(): void {
    this.sharedEntriesLoading.set(true);
    this.sharedDebtService.listEntries({ month: this.filterMonth(), year: this.filterYear() })
      .pipe(takeUntil(this.destroy$))
      .subscribe({
        next: res => { this.sharedEntries.set(res.results); this.sharedEntriesLoading.set(false); },
        error: () => this.sharedEntriesLoading.set(false),
      });
  }

  myPortion(entry: SharedDebtEntry): number {
    return entry.participant_count > 0 ? Number(entry.amount) / entry.participant_count : Number(entry.amount);
  }

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

  @ViewChild('lineChartEl') lineChartEl!: ElementRef<HTMLDivElement>;
  @ViewChild('compChartEl') compChartEl!: ElementRef<HTMLDivElement>;

  chartTooltip = signal<{cx:number; cy:number; month:string; income:number; expense:number} | null>(null);
  barTooltip = signal<{cx:number; cy:number; month:string; cash:number; card:number; shared:number; total:number} | null>(null);

  constructor() {
    effect(() => {
      const data = this.evolution();
      const loading = this.dashLoading();
      if (!loading && data && data.length > 0) {
        setTimeout(() => {
          this.renderCharts(data);
        }, 50);
      }
    });
  }

  // ?? SVG Chart rendering (D3) ??
  renderCharts(data: MonthlyAnalytics[]): void {
    if (!this.lineChartEl || !this.compChartEl) return;
    this.buildLineChartD3(data);
    this.buildCompChartD3(data);
  }

  private buildLineChartD3(data: MonthlyAnalytics[]): void {
    const el = this.lineChartEl.nativeElement;
    el.innerHTML = '';
    const margin = {top:28, right:20, bottom:35, left:60};
    const width = 600, height = 240;
    const innerW = width - margin.left - margin.right;
    const innerH = height - margin.top - margin.bottom;
    const labels = data.map(d => d.month_name.substring(0, 3));
    // Force numeric - DRF returns DecimalField as strings
    const numData = data.map(d => ({ ...d, income: Number(d.income), expenses: Number(d.expenses) }));

    const svg = d3.select(el).append('svg')
      .attr('viewBox', `0 0 ${width} ${height}`)
      .style('width','100%').style('height', `${height}px`).style('overflow','visible');

    svg.append('text').attr('x', width/2).attr('y', margin.top - 10)
      .attr('text-anchor','middle').attr('font-size','11').attr('fill','#6b7280')
      .attr('font-weight','600').attr('font-family','inherit').text('Receita x Despesa');

    const g = svg.append('g').attr('transform',`translate(${margin.left},${margin.top})`);

    const x = d3.scalePoint().domain(labels).range([0, innerW]);
    const maxY = Math.max(...data.map(d => Math.max(Number(d.income), Number(d.expenses)))) * 1.15 || 1;
    const y = d3.scaleLinear().domain([0, maxY]).range([innerH, 0]);

    g.append('g').attr('class','grid')
      .call(d3.axisLeft(y).ticks(5).tickSize(-innerW).tickFormat(()=>''))
      .call(gg => gg.select('.domain').remove())
      .call(gg => gg.selectAll('line').attr('stroke','#f3f4f6'));

    g.append('g').attr('transform',`translate(0,${innerH})`)
      .call(d3.axisBottom(x).tickSize(0))
      .call(gg => gg.select('.domain').remove())
      .call(gg => gg.selectAll('text').attr('fill','#6b7280').attr('font-size','10').attr('font-family','inherit'));

    g.append('g').call(d3.axisLeft(y).ticks(5).tickFormat((v:d3.NumberValue) => {
      const n = +v;
      return n >= 1000 ? `R$${(n/1000).toFixed(n%1000===0?0:1)}k` : `R$${n}`;
    }))
      .call(gg => gg.select('.domain').remove())
      .call(gg => gg.selectAll('text').attr('fill','#9ca3af').attr('font-size','9').attr('font-family','inherit'));

    const areaFn = d3.area<MonthlyAnalytics>()
      .x((_,i) => x(labels[i])!)
      .y0(innerH).y1(d => y(d.income));
    g.append('path').datum(data).attr('d', areaFn).attr('fill','#dcfce7').attr('opacity','0.45');

    const lineExp = d3.line<MonthlyAnalytics>().x((_,i)=>x(labels[i])!).y(d=>y(d.expenses));
    const lineInc = d3.line<MonthlyAnalytics>().x((_,i)=>x(labels[i])!).y(d=>y(d.income));

    g.append('path').datum(data).attr('d', lineExp)
      .attr('fill','none').attr('stroke','#ef4444').attr('stroke-width','2.5')
      .attr('stroke-linejoin','round').attr('stroke-linecap','round');
    g.append('path').datum(data).attr('d', lineInc)
      .attr('fill','none').attr('stroke','#16a34a').attr('stroke-width','2.5')
      .attr('stroke-dasharray','6 3').attr('stroke-linejoin','round').attr('stroke-linecap','round');

    data.forEach((d, i) => {
      if (Number(d.income) === 0 && Number(d.expenses) === 0) return;
      const cx = x(labels[i])!;
      g.append('circle').attr('cx',cx).attr('cy',y(Number(d.income))).attr('r',3.5)
        .attr('fill','#16a34a').attr('stroke','#fff').attr('stroke-width',1.5);
      g.append('circle').attr('cx',cx).attr('cy',y(Number(d.expenses))).attr('r',3.5)
        .attr('fill','#ef4444').attr('stroke','#fff').attr('stroke-width',1.5);
      g.append('circle').attr('cx',cx).attr('cy',(y(Number(d.income))+y(Number(d.expenses)))/2).attr('r',16)
        .attr('fill','transparent').style('cursor','pointer')
        .on('mousemove', (event: MouseEvent) => {
          this.chartTooltip.set({ cx: event.clientX+14, cy: event.clientY-90, month: labels[i], income: Number(d.income), expense: Number(d.expenses) });
        })
        .on('mouseleave', () => this.chartTooltip.set(null));
    });
  }

  private buildCompChartD3(data: MonthlyAnalytics[]): void {
    const el = this.compChartEl.nativeElement;
    el.innerHTML = '';
    const margin = {top:28, right:20, bottom:35, left:50};
    const width = 380, height = 240;
    const innerW = width - margin.left - margin.right;
    const innerH = height - margin.top - margin.bottom;
    const labels = data.map(d => d.month_name.substring(0, 3));

    const svg = d3.select(el).append('svg')
      .attr('viewBox', `0 0 ${width} ${height}`)
      .style('width','100%').style('height', `${height}px`).style('overflow','visible');

    svg.append('text').attr('x', width/2).attr('y', margin.top - 10)
      .attr('text-anchor','middle').attr('font-size','11').attr('fill','#6b7280')
      .attr('font-weight','600').attr('font-family','inherit').text('Composição das Despesas');

    const g = svg.append('g').attr('transform',`translate(${margin.left},${margin.top})`);

    type BarRow = { month: string; cash: number; card: number; shared: number };
    const rows: BarRow[] = data.map(d => ({
      month: d.month_name.substring(0,3),
      cash: Number(d.cash_expenses), card: Number(d.card_expenses), shared: Number(d.shared_my_portion)
    }));

    const stackFn = d3.stack<BarRow>().keys(['cash','card','shared']);
    const stacked = stackFn(rows);
    const colors: Record<string,string> = {cash:'#ef4444', card:'#f97316', shared:'#fbbf24'};

    const x = d3.scaleBand().domain(labels).range([0, innerW]).padding(0.3);
    const maxY = Math.max(...rows.map(r => r.cash+r.card+r.shared)) * 1.2 || 1;
    const y = d3.scaleLinear().domain([0, maxY]).range([innerH, 0]);

    g.append('g').attr('class','grid')
      .call(d3.axisLeft(y).ticks(4).tickSize(-innerW).tickFormat(()=>''))
      .call(gg => gg.select('.domain').remove())
      .call(gg => gg.selectAll('line').attr('stroke','#f3f4f6'));

    g.append('g').attr('transform',`translate(0,${innerH})`)
      .call(d3.axisBottom(x).tickSize(0))
      .call(gg => gg.select('.domain').remove())
      .call(gg => gg.selectAll('text').attr('fill','#6b7280').attr('font-size','10').attr('font-family','inherit'));

    g.append('g').call(d3.axisLeft(y).ticks(4).tickFormat((v:d3.NumberValue) => {
      const n = +v;
      return n >= 1000 ? `R$${(n/1000).toFixed(1)}k` : `R$${n}`;
    }))
      .call(gg => gg.select('.domain').remove())
      .call(gg => gg.selectAll('text').attr('fill','#9ca3af').attr('font-size','9').attr('font-family','inherit'));

    stacked.forEach(layer => {
      const key = layer.key as string;
      g.selectAll(null).data(layer).enter().append('rect')
        .attr('x', (_,i) => x(labels[i])!)
        .attr('y', (d:any) => y(d[1]))
        .attr('height', (d:any) => Math.max(0, y(d[0]) - y(d[1])))
        .attr('width', x.bandwidth())
        .attr('fill', colors[key]);
    });

    rows.forEach((r, i) => {
      const total = r.cash + r.card + r.shared;
      if (total === 0) return;
      g.append('rect')
        .attr('x', x(labels[i])!).attr('y', y(total))
        .attr('width', x.bandwidth()).attr('height', innerH - y(total))
        .attr('fill','transparent').style('cursor','pointer')
        .on('mousemove', (event: MouseEvent) => {
          this.barTooltip.set({ cx: event.clientX+14, cy: event.clientY-130, month: labels[i], cash: r.cash, card: r.card, shared: r.shared, total });
        })
        .on('mouseleave', () => this.barTooltip.set(null));
    });
  }

  fmtCur(v: number | string | null | undefined): string {
    const n = Number(v);
    if (isNaN(n)) return '—';
    return n.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL', minimumFractionDigits: 2 });
  }

  loadRecurringTemplates(): void {
    this.expSvc.listRecurringTemplates().subscribe({
      next: tpls => this.recurringTemplates.set(tpls),
    });
  }

  saveRecurring(): void {
    if (this.recurringForm.invalid) { this.recurringForm.markAllAsTouched(); return; }
    this.savingRecurring.set(true);
    const v = this.recurringForm.getRawValue();
    this.expSvc.createRecurringTemplate({
      description: v.description!,
      amount: v.amount!,
      day_of_month: v.day_of_month ?? 1,
      payment_method: v.payment_method! as 'dinheiro' | 'cartao',
      category_id: v.category_id,
    }).subscribe({
      next: () => {
        this.savingRecurring.set(false);
        this.showRecurringForm.set(false);
        this.recurringForm.reset({ description: '', amount: null, day_of_month: 1, payment_method: 'dinheiro', category_id: null });
        this.loadRecurringTemplates();
      },
      error: err => { this.savingRecurring.set(false); this.recurringError.set(err?.error?.detail ?? 'Erro.'); },
    });
  }

  deleteRecurring(id: number): void {
    this.expSvc.deleteRecurringTemplate(id).subscribe({ next: () => this.loadRecurringTemplates() });
  }

  toggleRecurring(id: number): void {
    this.expSvc.toggleRecurringTemplate(id).subscribe({ next: () => this.loadRecurringTemplates() });
  }

  generateCurrentMonth(): void {
    const now = new Date();
    this.expSvc.generateMonthRecurring(now.getMonth() + 1, now.getFullYear()).subscribe({
      next: res => { this.generateResult.set(res); this.loadDashboard(); },
    });
  }

}


