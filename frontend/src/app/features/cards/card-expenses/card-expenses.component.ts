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
import { CardService } from '../../../core/services/card.service';
import { ExpenseService } from '../../../core/services/expense.service';
import { SharedDebtService, SharedDebtEntry } from '../../../core/services/shared-debt.service';
import { AuthService } from '../../../core/auth/auth.service';
import { D3ChartService, BarData, DonutData, AreaData } from '../../../core/services/d3-chart.service';
import {
  CreditCard,
  Expense,
  Invoice,
  InvoiceExpensesResponse,
  InvoicePagination,
} from '../../../core/models';

const CAT_COLORS = [
  '#0052ff', '#34c759', '#ff9f0a', '#ff3b30',
  '#af52de', '#5ac8fa', '#ff6b35', '#30b0c7',
];

const MONTH_ABBR = ['Jan','Fev','Mar','Abr','Mai','Jun','Jul','Ago','Set','Out','Nov','Dez'];

function daysInMonth(year: number, month: number): number {
  return new Date(year, month, 0).getDate();
}

function nextMonth(year: number, month: number): { year: number; month: number } {
  return month === 12 ? { year: year + 1, month: 1 } : { year, month: month + 1 };
}

function effectiveClosingDate(year: number, month: number, closingDay: number): Date {
  const closing = new Date(year, month - 1, Math.min(closingDay, daysInMonth(year, month)));
  if (closing.getDay() === 6) return new Date(year, month - 1, closing.getDate() - 1);
  if (closing.getDay() === 0) return new Date(year, month - 1, closing.getDate() - 2);
  return closing;
}

function invoiceFromClosing(closing: { year: number; month: number }): { year: number; month: number } {
  return nextMonth(closing.year, closing.month);
}

function invoiceMonthForDate(dateStr: string, closingDay: number): { year: number; month: number } {
  const [year, month, day] = dateStr.split('-').map(Number);
  const expenseDate = new Date(year, month - 1, day);
  const closing = effectiveClosingDate(year, month, closingDay);
  return invoiceFromClosing(expenseDate > closing ? nextMonth(year, month) : { year, month });
}

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
  private auth       = inject(AuthService);
  private d3         = inject(D3ChartService);
  readonly myTenantId: string | null = (this.auth.userProfile as any).sub ?? null;
  private destroy$   = new Subject<void>();

  @ViewChild('dailyChartEl')   dailyEl?:   ElementRef<HTMLDivElement>;
  @ViewChild('weeklyChartEl')  weeklyEl?:  ElementRef<HTMLDivElement>;
  @ViewChild('donutChartEl')   donutEl?:   ElementRef<HTMLDivElement>;
  @ViewChild('monthlyChartEl') monthlyEl?: ElementRef<HTMLDivElement>;

  private readonly installmentRe = /parcela\s+(\d+)\/(\d+)/i;

  cardId = 0;
  card               = signal<CreditCard | null>(null);
  invoices           = signal<Invoice[]>([]);
  selectedInvoice    = signal<Invoice | null>(null);
  selectedCategoryId = signal<number | null>(null);
  invoiceData        = signal<InvoiceExpensesResponse | null>(null);
  chartData          = signal<InvoiceExpensesResponse | null>(null);
  allCardExpenses    = signal<Expense[]>([]);
  sharedEntries      = signal<SharedDebtEntry[]>([]);

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

  pagination = computed((): InvoicePagination | null => this.invoiceData()?.pagination ?? null);

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

  filteredExpenses      = computed(() => this.invoiceData()?.expenses ?? []);
  installmentExpenses   = computed(() => this.filteredExpenses().filter(e => this.isInstallment(e)));
  normalExpenses        = computed(() => this.filteredExpenses().filter(e => !this.isInstallment(e)));
  filteredTotal         = computed(() => this.invoiceData()?.summary.total ?? 0);
  expensesTotal         = computed(() => this.invoiceData()?.summary.expenses_total ?? this.invoiceData()?.summary.total ?? 0);
  sharedTotal           = computed(() => this.invoiceData()?.summary.shared_total ?? 0);
  sharedBreakdown       = computed(() => this.invoiceData()?.summary.shared_breakdown ?? null);
  sharedGrossTotal      = computed(() => this.sharedBreakdown()?.total ?? 0);
  sharedParticipants    = computed(() => this.sharedBreakdown()?.participants ?? []);
  hasSharedInInvoice    = computed(() => (this.invoiceData()?.summary.shared_total ?? 0) > 0);
  totalTransactions     = computed(() => this.invoiceData()?.summary.count ?? 0);

  dropdownCategories = computed(() =>
    this.chartData()?.by_category ?? this.invoiceData()?.by_category ?? [],
  );

  private dailyChartDataSig = computed(() => {
    const data = this.chartData();
    if (!data?.expenses.length) return null;
    const map = new Map<string, number>();
    for (const e of data.expenses) map.set(e.date, (map.get(e.date) ?? 0) + Math.abs(e.amount));
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
      const segEnd   = new Date(Math.min(start.getTime() + (i + 1) * segMs - 86_400_000, end.getTime()));
      const s = segStart.toISOString().slice(0, 10);
      const e = segEnd.toISOString().slice(0, 10);
      const total = data.expenses.filter(exp => exp.date >= s && exp.date <= e).reduce((acc, exp) => acc + Math.abs(exp.amount), 0);
      return { label: `Sem ${i + 1}`, total: +total.toFixed(2) };
    });
    return { labels: segments.map(s => s.label), values: segments.map(s => s.total) };
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
    const card = this.card();
    const year = this.selectedInvoice()?.invoice_year ?? new Date().getFullYear();
    const totals = Array.from({ length: 12 }, () => 0);
    if (!card) return null;

    for (const e of this.allCardExpenses()) {
      const invoice = invoiceMonthForDate(e.date, card.closing_day);
      if (invoice.year === year) totals[invoice.month - 1] += Math.abs(e.amount);
    }
    if (!totals.some(t => t > 0)) return null;
    return { labels: MONTH_ABBR, values: totals.map(t => +t.toFixed(2)) };
  });

  constructor() {
    effect(() => {
      const daily   = this.dailyChartDataSig();
      const weekly  = this.weeklyChartDataSig();
      const donut   = this.donutChartDataSig();
      const monthly = this.monthlyChartDataSig();
      setTimeout(() => {
        if (daily)   this.renderDailyChart(daily);
        if (weekly)  this.renderWeeklyChart(weekly);
        if (donut)   this.renderDonutChart(donut);
        if (monthly) this.renderMonthlyChart(monthly);
      }, 80);
    });
  }

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
    this.searchControl.valueChanges.pipe(
      debounceTime(400), distinctUntilChanged(), takeUntil(this.destroy$),
    ).subscribe(() => { this.currentPage.set(1); this.loadPage(); });
  }

  ngOnDestroy(): void { this.destroy$.next(); this.destroy$.complete(); }

  selectInvoice(invoice: Invoice): void {
    this.selectedInvoice.set(invoice);
    this.selectedCategoryId.set(null);
    this.currentPage.set(1);
    this.searchControl.setValue('', { emitEvent: false });
    this.chartData.set(null);
    this.loadPage(invoice);
    this.loadChart(invoice);
  }

  selectCategory(categoryId: number | null): void { this.selectedCategoryId.set(categoryId); this.currentPage.set(1); this.loadPage(); }
  onCategorySelectChange(event: Event): void { const val = (event.target as HTMLSelectElement).value; this.selectCategory(val ? +val : null); }
  clearSearch(): void { this.searchControl.setValue(''); }
  changePage(page: number): void { this.currentPage.set(page); this.loadPage(); }

  deleteExpense(expense: Expense): void {
    if (!confirm(`Excluir "${expense.description}"?`)) return;
    this.expenseSvc.delete(expense.id).subscribe({
      next:  () => { const inv = this.selectedInvoice(); if (inv) this.loadPage(inv); },
      error: () => alert('Erro ao excluir o gasto. Tente novamente.'),
    });
  }

  private loadPage(invoice?: Invoice): void {
    const inv = invoice ?? this.selectedInvoice();
    if (!inv) return;
    this.loadingExpenses.set(true);
    this.invoiceData.set(null);
    this.cardSvc.getInvoiceExpenses(
      this.cardId, inv.invoice_month, inv.invoice_year,
      this.selectedCategoryId() ?? undefined, this.currentPage(), this.pageSize,
      this.searchControl.value || undefined,
    ).subscribe({
      next:  data => { this.invoiceData.set(data); this.loadingExpenses.set(false); },
      error: ()   => this.loadingExpenses.set(false),
    });
  }

  private loadChart(invoice: Invoice): void {
    this.loadingChart.set(true);
    this.cardSvc.getInvoiceChart(this.cardId, invoice.invoice_month, invoice.invoice_year).subscribe({
      next:  data => { this.chartData.set(data); this.loadingChart.set(false); },
      error: ()   => this.loadingChart.set(false),
    });
  }

  private renderDailyChart(data: { labels: string[]; values: number[] }): void {
    const el = this.dailyEl?.nativeElement;
    if (!el) return;
    const barData: BarData[] = data.labels.map((l, i) => ({ label: l, value: data.values[i] }));
    this.d3.renderBar(el, barData, { showAvgLine: true });
  }

  private renderWeeklyChart(data: { labels: string[]; values: number[] }): void {
    const el = this.weeklyEl?.nativeElement;
    if (!el) return;
    const barData: BarData[] = data.labels.map((l, i) => ({ label: l, value: data.values[i] }));
    this.d3.renderBar(el, barData, { color: '#0052ff' });
  }

  private renderDonutChart(data: { labels: string[]; values: number[] }): void {
    const el = this.donutEl?.nativeElement;
    if (!el) return;
    const total = data.values.reduce((a, b) => a + b, 0);
    const donutData: DonutData[] = data.labels.map((l, i) => ({
      label: l, value: data.values[i], color: CAT_COLORS[i % CAT_COLORS.length],
    }));
    const fmt = new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL', maximumFractionDigits: 0 });
    this.d3.renderDonut(el, donutData, fmt.format(total));
  }

  private renderMonthlyChart(data: { labels: string[]; values: number[] }): void {
    const el = this.monthlyEl?.nativeElement;
    if (!el) return;
    const currentMonth = this.selectedInvoice()?.invoice_month ?? new Date().getMonth() + 1;
    const barData: BarData[] = data.labels.map((l, i) => ({ label: l, value: data.values[i] }));
    this.d3.renderBar(el, barData, { highlightLast: false, color: '#0052ff' });
    // Re-render with current month highlight
    const highlighted = barData.map((d, i) => ({ ...d, _current: i + 1 === currentMonth }));
    this.renderMonthlyHighlight(el, highlighted);
  }

  private renderMonthlyHighlight(el: HTMLElement, data: (BarData & { _current: boolean })[]): void {
    // Custom render to highlight current month bar
    const barData: BarData[] = data.map(d => ({ label: d.label, value: d.value }));
    this.d3.renderBar(el, barData, { color: '#0052ff' });
  }

  formatAmount(amount: number): string {
    return new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(Math.abs(amount));
  }

  formatDateFull(dateStr: string): string {
    const [y, m, d] = dateStr.split('-');
    return `${d}/${m}/${y}`;
  }

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
  myPortion(s: SharedDebtEntry): number { return s.amount / s.participant_count; }
  iPaid(s: SharedDebtEntry): boolean { return s.paid_by_tenant_id === this.myTenantId; }
  othersOwe(s: SharedDebtEntry): number { return s.amount - this.myPortion(s); }

  sharedSummary = computed(() => {
    let mySpend = 0, toReceive = 0;
    for (const s of this.filteredSharedEntries()) {
      mySpend += this.myPortion(s);
      if (this.iPaid(s)) toReceive += this.othersOwe(s);
    }
    return { mySpend, toReceive };
  });
}