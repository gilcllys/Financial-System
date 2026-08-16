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
    payment_method: ['dinheiro', Validators.required],
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

  chartTooltip = signal<{x:number; y:number; month:string; income:number; expense:number} | null>(null);

  constructor() {
    // Renderiza os gráficos assim que dashLoading vira false e o DOM é atualizado
    effect(() => {
      if (!this.dashLoading()) {
        const data = this.evolution();
        // Promise.resolve garante execução após o Angular atualizar o DOM (ViewChild disponível)
        Promise.resolve().then(() => {
          if (data.length > 0) this.renderCharts(data);
        });
      }
    });
  }

  // ── SVG Chart rendering ────────────────────────────────────────────────
  renderCharts(data: MonthlyAnalytics[]): void {
    if (!this.lineChartEl || !this.compChartEl) return;
    const WL=600,WC=380,H=240,PL=56,PR=16,PT=28,PB=34;
    const labels=data.map(d=>d.month_name.substring(0,3));
    const income=data.map(d=>d.income);
    const exp=data.map(d=>d.expenses);
    const cash=data.map(d=>d.cash_expenses);
    const card=data.map(d=>d.card_expenses);
    const shared=data.map(d=>d.shared_my_portion);
    this.lineChartEl.nativeElement.innerHTML = this.buildLineChart(labels,income,exp,WL,H,PL,PR,PT,PB);
    this.compChartEl.nativeElement.innerHTML = this.buildCompChart(labels,cash,card,shared,WC,H,PL,PR,PT,PB);
    this._attachLineTooltips();
  }

  private _attachLineTooltips(): void {
    const container = this.lineChartEl?.nativeElement;
    if (!container) return;
    container.querySelectorAll('.chart-hit').forEach(el => {
      el.addEventListener('mouseenter', (e: Event) => {
        const me = e as MouseEvent;
        const rect = container.getBoundingClientRect();
        const t = el as HTMLElement;
        this.chartTooltip.set({
          x: me.clientX - rect.left + 14,
          y: me.clientY - rect.top - 52,
          month: t.dataset['month']!,
          income: parseFloat(t.dataset['income']!),
          expense: parseFloat(t.dataset['expense']!),
        });
      });
      el.addEventListener('mouseleave', () => this.chartTooltip.set(null));
    });
  }

  private buildLineChart(labels:string[],income:number[],exp:number[],W:number,H:number,PL:number,PR:number,PT:number,PB:number):string {
    const n=labels.length;
    const maxV=Math.max(...income,...exp)*1.15||1;
    const totalW=W-PL-PR;
    const gap=totalW/(n-1);
    const sy=(v:number)=>PT+(1-Math.max(0,v)/maxV)*(H-PT-PB);
    const sx=(i:number)=>PL+i*gap;
    const fmt=(v:number)=>`R$ ${v.toLocaleString('pt-BR',{minimumFractionDigits:2})}`;
    let o='';
    o+=`<svg viewBox="0 0 ${W} ${H}" xmlns="http://www.w3.org/2000/svg" style="width:100%;height:${H}px;overflow:visible">`;
    o+=`<text x="${W/2}" y="${PT-10}" text-anchor="middle" font-size="11" fill="#6b7280" font-weight="600" font-family="inherit">Receita x Despesa</text>`;
    for(let s=0;s<=5;s++){
      const gv=maxV*s/5;const gy=sy(gv);
      o+=`<line x1="${PL}" y1="${gy.toFixed(1)}" x2="${W-PR}" y2="${gy.toFixed(1)}" stroke="#f3f4f6" stroke-width="1"/>`;
      const lbl=gv>=1000?`${(gv/1000).toFixed(gv%1000===0?0:1)}k`:gv.toFixed(0);
      o+=`<text x="${PL-6}" y="${(gy+4).toFixed(1)}" text-anchor="end" font-size="9" fill="#9ca3af" font-family="inherit">R$${lbl}</text>`;
    }
    const incomePts=income.map((_,i)=>`${sx(i).toFixed(1)},${sy(income[i]).toFixed(1)}`).join(' ');
    const baseY=sy(0).toFixed(1);
    o+=`<polygon points="${sx(0).toFixed(1)},${baseY} ${incomePts} ${sx(n-1).toFixed(1)},${baseY}" fill="#dcfce7" opacity="0.45"/>`;
    const expPts=exp.map((_,i)=>`${sx(i).toFixed(1)},${sy(exp[i]).toFixed(1)}`).join(' ');
    o+=`<polyline points="${expPts}" fill="none" stroke="#ef4444" stroke-width="2.5" stroke-linejoin="round" stroke-linecap="round"/>`;
    o+=`<polyline points="${incomePts}" fill="none" stroke="#16a34a" stroke-width="2.5" stroke-dasharray="6 3" stroke-linejoin="round" stroke-linecap="round"/>`;
    income.forEach((_,i)=>{
      if(income[i]===0&&exp[i]===0)return;
      o+=`<circle cx="${sx(i).toFixed(1)}" cy="${sy(income[i]).toFixed(1)}" r="3.5" fill="#16a34a" stroke="#fff" stroke-width="1.5"/>`;
      o+=`<circle cx="${sx(i).toFixed(1)}" cy="${sy(exp[i]).toFixed(1)}" r="3" fill="#ef4444" stroke="#fff" stroke-width="1.5"/>`;
      o+=`<circle class="chart-hit" cx="${sx(i).toFixed(1)}" cy="${(sy(income[i])+sy(exp[i]))/2}" r="14" fill="transparent" style="cursor:pointer" data-month="${labels[i]}" data-income="${income[i]}" data-expense="${exp[i]}"/>`;
    });
    labels.forEach((m,i)=>{
      const active=income[i]>0||exp[i]>0;
      o+=`<text x="${sx(i).toFixed(1)}" y="${H-6}" text-anchor="middle" font-size="10" fill="${active?'#6b7280':'#d1d5db'}" font-family="inherit">${m}</text>`;
    });
    o+=`</svg>`;
    return o;
  }

  private buildCompChart(labels:string[],cash:number[],card:number[],shared:number[],W:number,H:number,PL:number,PR:number,PT:number,PB:number):string {
    const n=labels.length;
    const totals=cash.map((_,i)=>cash[i]+card[i]+shared[i]);
    const maxV=Math.max(...totals)*1.2||1;
    const totalW=W-PL-PR;
    const gap=totalW/n;
    const barW=Math.min(gap*0.72,26);
    const bx=(i:number)=>PL+i*gap+gap/2-barW/2;
    const sy=(v:number)=>PT+(1-v/maxV)*(H-PT-PB);
    const baseY=sy(0);
    const fmt=(v:number)=>`R$ ${v.toLocaleString('pt-BR',{minimumFractionDigits:2})}`;
    let o='';
    o+=`<svg viewBox="0 0 ${W} ${H}" xmlns="http://www.w3.org/2000/svg" style="width:100%;height:${H}px;overflow:visible">`;
    o+=`<text x="${W/2}" y="${PT-10}" text-anchor="middle" font-size="11" fill="#6b7280" font-weight="600" font-family="inherit">Composição das Despesas</text>`;
    for(let s=0;s<=4;s++){
      const gv=maxV*s/4;const gy=sy(gv);
      o+=`<line x1="${PL}" y1="${gy.toFixed(1)}" x2="${W-PR}" y2="${gy.toFixed(1)}" stroke="#f3f4f6" stroke-width="1"/>`;
      const lbl=gv>=1000?`${(gv/1000).toFixed(1)}k`:gv.toFixed(0);
      o+=`<text x="${PL-4}" y="${(gy+4).toFixed(1)}" text-anchor="end" font-size="8" fill="#9ca3af" font-family="inherit">R$${lbl}</text>`;
    }
    for(let i=0;i<n;i++){
      const x=bx(i);const cx=x+barW/2;
      const h1=Math.max(0,baseY-sy(cash[i]));
      const h2=Math.max(0,baseY-sy(card[i]));
      const h3=Math.max(0,baseY-sy(shared[i]));
      const yc=baseY-h1;const yk=yc-h2;const ys=yk-h3;
      if(cash[i]>0){
        o+=`<rect x="${x.toFixed(1)}" y="${yc.toFixed(1)}" width="${barW.toFixed(1)}" height="${h1.toFixed(1)}" fill="#ef4444"/>`;
        if(h1>=14) o+=`<text x="${cx.toFixed(1)}" y="${(yc+h1/2+4).toFixed(1)}" text-anchor="middle" font-size="8" fill="#fff" font-weight="bold" font-family="inherit">${(cash[i]/1000).toFixed(1)}k</text>`;
      }
      if(card[i]>0){
        o+=`<rect x="${x.toFixed(1)}" y="${yk.toFixed(1)}" width="${barW.toFixed(1)}" height="${h2.toFixed(1)}" fill="#f97316"/>`;
        if(h2>=14) o+=`<text x="${cx.toFixed(1)}" y="${(yk+h2/2+4).toFixed(1)}" text-anchor="middle" font-size="8" fill="#fff" font-weight="bold" font-family="inherit">${(card[i]/1000).toFixed(1)}k</text>`;
      }
      if(shared[i]>0){
        o+=`<rect x="${x.toFixed(1)}" y="${ys.toFixed(1)}" width="${barW.toFixed(1)}" height="${h3.toFixed(1)}" fill="#fbbf24"/>`;
        if(h3>=14) o+=`<text x="${cx.toFixed(1)}" y="${(ys+h3/2+4).toFixed(1)}" text-anchor="middle" font-size="8" fill="#fff" font-weight="bold" font-family="inherit">${(shared[i]/1000).toFixed(1)}k</text>`;
      }
      if(totals[i]>0){
        const topY=Math.min(...[cash[i]>0?yc:9999,card[i]>0?yk:9999,shared[i]>0?ys:9999]);
        o+=`<text x="${cx.toFixed(1)}" y="${(topY-3).toFixed(1)}" text-anchor="middle" font-size="8" fill="#374151" font-weight="bold" font-family="inherit">${(totals[i]/1000).toFixed(1)}k</text>`;
      }
      const active=totals[i]>0;
      o+=`<text x="${cx.toFixed(1)}" y="${H-6}" text-anchor="middle" font-size="${active?10:9}" fill="${active?'#6b7280':'#d1d5db'}" font-family="inherit">${labels[i]}</text>`;
    }
    o+=`</svg>`;
    return o;
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
      payment_method: v.payment_method!,
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
