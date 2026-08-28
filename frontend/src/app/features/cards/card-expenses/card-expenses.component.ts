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
import { ReactiveFormsModule, FormsModule, FormControl } from '@angular/forms';
import { Subject } from 'rxjs';
import { debounceTime, distinctUntilChanged, takeUntil } from 'rxjs/operators';
import { CardService } from '../../../core/services/card.service';
import { ExpenseService } from '../../../core/services/expense.service';
import { SharedDebtService, SharedDebtEntry } from '../../../core/services/shared-debt.service';
import { CategoryService } from '../../../core/services/category.service';
import { AuthService } from '../../../core/auth/auth.service';
import { D3ChartService, BarData, DonutData, AreaData } from '../../../core/services/d3-chart.service';
import {
  CreditCard,
  Expense,
  ExpenseCategory,
  Invoice,
  InvoiceExpensesResponse,
  InvoicePagination,
  InvoiceSharedParticipant,
} from '../../../core/models';

export interface SharedInvoiceGroup {
  group_id: number;
  group_name: string;
  total: number;
  participants: InvoiceSharedParticipant[];
  entries: SharedDebtEntry[];
  myPortionTotal: number;
}

/**
 * A single row in the unified "Gastos da Fatura" table, merging individual
 * expenses with shared-debt entries (shown at their full/integral amount,
 * since that is what was actually charged on the card).
 */
export interface CombinedExpenseRow {
  key: string;
  kind: 'individual' | 'compartilhado';
  description: string;
  categoryId: number | null;
  categoryName: string | null;
  date: string;
  amount: number;
  installmentBadge: string | null;
  groupName: string | null;
  expense: Expense | null;
  sharedEntry: SharedDebtEntry | null;
}

export interface EditSharedDraft {
  description: string;
  amount: number;
  date: string;
  category_id: number | null;
}

const CAT_COLORS = [
  '#0052ff', '#34c759', '#ff9f0a', '#ff3b30',
  '#af52de', '#5ac8fa', '#ff6b35', '#30b0c7',
];

const GROUP_COLORS = ['#05b169', '#ff9f0a', '#af52de', '#0052ff', '#ff3b30', '#5ac8fa'];

const MONTH_ABBR = ['Jan','Fev','Mar','Abr','Mai','Jun','Jul','Ago','Set','Out','Nov','Dez'];

function daysInMonth(year: number, month: number): number {
  return new Date(year, month, 0).getDate();
}

@Component({
  selector: 'app-card-expenses',
  standalone: true,
  imports: [RouterLink, ReactiveFormsModule, FormsModule],
  templateUrl: './card-expenses.component.html',
  styleUrls: ['./card-expenses.component.scss'],
})
export class CardExpensesComponent implements OnInit, OnDestroy {
  private route      = inject(ActivatedRoute);
  private cardSvc    = inject(CardService);
  private expenseSvc = inject(ExpenseService);
  private sharedSvc  = inject(SharedDebtService);
  private categorySvc = inject(CategoryService);
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
  allCategories      = signal<ExpenseCategory[]>([]);

  // Unified "Gastos da Fatura" table filters (all applied client-side).
  typeFilter      = signal<'all' | 'individual' | 'compartilhado'>('all');
  dateFromFilter  = signal<string>('');
  dateToFilter    = signal<string>('');

  // Inline edit state for shared-debt rows (edited directly on this screen).
  editingSharedId = signal<number | null>(null);
  editDraft       = signal<EditSharedDraft | null>(null);
  savingEdit      = signal(false);

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

  sharedGroups = computed((): SharedInvoiceGroup[] => {
    const entries = this.filteredSharedEntries();
    const breakdownGroups = this.invoiceData()?.summary.shared_breakdown?.groups ?? [];
    const map = new Map<number, SharedInvoiceGroup>();
    for (const e of entries) {
      let group = map.get(e.shared_debt);
      if (!group) {
        const bd = breakdownGroups.find(g => g.group_id === e.shared_debt);
        group = {
          group_id: e.shared_debt,
          group_name: e.shared_debt_name,
          total: bd?.total ?? 0,
          participants: bd?.participants ?? [],
          entries: [],
          myPortionTotal: 0,
        };
        map.set(e.shared_debt, group);
      }
      group.entries.push(e);
      group.myPortionTotal += this.myPortion(e);
    }
    return [...map.values()].sort((a, b) => a.group_name.localeCompare(b.group_name));
  });

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
  // Total real da fatura: individual + valor cheio dos grupos compartilhados (o banco cobra o valor integral,
  // a divisao com os demais participantes e apenas um controle a parte).
  invoiceGrandTotal     = computed(() => this.expensesTotal() + this.sharedGrossTotal());

  dropdownCategories = computed(() =>
    this.chartData()?.by_category ?? this.invoiceData()?.by_category ?? [],
  );

  /**
   * Unified rows for the "Gastos da Fatura" table: individual expenses (from
   * the unpaginated chart data, up to 200 per invoice) plus shared-debt
   * entries paid on this card within the invoice period, each shown at its
   * full/integral amount (what was actually charged), tagged with a
   * kind flag so the UI can tell them apart and filter by type.
   */
  combinedRows = computed((): CombinedExpenseRow[] => {
    const individual: CombinedExpenseRow[] = (this.chartData()?.expenses ?? []).map(e => ({
      key: `ind-${e.id}`,
      kind: 'individual' as const,
      description: e.description,
      categoryId: e.category?.id ?? null,
      categoryName: e.category?.name ?? null,
      date: e.date,
      amount: Math.abs(e.amount),
      installmentBadge: this.installmentBadge(e),
      groupName: null,
      expense: e,
      sharedEntry: null,
    }));
    const shared: CombinedExpenseRow[] = this.filteredSharedEntries().map(e => ({
      key: `shr-${e.id}`,
      kind: 'compartilhado' as const,
      description: e.description,
      categoryId: e.category,
      categoryName: e.category_name,
      date: e.date,
      amount: Math.abs(e.amount),
      installmentBadge: e.total_installments > 1 ? `${e.installment_number}/${e.total_installments}` : null,
      groupName: e.shared_debt_name,
      expense: null,
      sharedEntry: e,
    }));
    return [...individual, ...shared];
  });

  combinedFiltered = computed((): CombinedExpenseRow[] => {
    let rows = this.combinedRows();
    const type = this.typeFilter();
    if (type !== 'all') rows = rows.filter(r => r.kind === type);
    const search = this.searchControl.value?.trim().toLowerCase();
    if (search) rows = rows.filter(r => r.description.toLowerCase().includes(search));
    const catId = this.selectedCategoryId();
    if (catId != null) rows = rows.filter(r => r.categoryId === catId);
    const from = this.dateFromFilter();
    if (from) rows = rows.filter(r => r.date >= from);
    const to = this.dateToFilter();
    if (to) rows = rows.filter(r => r.date <= to);
    return [...rows].sort((a, b) => b.date.localeCompare(a.date) || a.description.localeCompare(b.description));
  });

  combinedFilteredCount = computed(() => this.combinedFiltered().length);
  combinedFilteredTotal = computed(() => this.combinedFiltered().reduce((sum, r) => sum + r.amount, 0));
  combinedTotalPages    = computed(() => Math.max(1, Math.ceil(this.combinedFilteredCount() / this.pageSize)));

  combinedPageRows = computed((): CombinedExpenseRow[] => {
    const page  = Math.min(this.currentPage(), this.combinedTotalPages());
    const start = (page - 1) * this.pageSize;
    return this.combinedFiltered().slice(start, start + this.pageSize);
  });

  combinedPageRange = computed((): number[] => {
    const total   = this.combinedTotalPages();
    const current = Math.min(this.currentPage(), total);
    const start   = Math.max(1, current - 2);
    const end     = Math.min(total, current + 2);
    return Array.from({ length: end - start + 1 }, (_, i) => start + i);
  });

  hasActiveFilters = computed(() =>
    !!this.searchControl.value || this.selectedCategoryId() != null ||
    this.typeFilter() !== 'all' || !!this.dateFromFilter() || !!this.dateToFilter()
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

  /** Legend entries for the "Top Categorias" donut chart, matching its slice colors. */
  donutLegend = computed(() => {
    const d = this.donutChartDataSig();
    if (!d) return [];
    return d.labels.map((label, i) => ({ label, value: d.values[i], color: this.catColor(i) }));
  });

  /**
   * Yearly chart. Expenses are bucketed using the invoice periods returned by
   * the API, which already apply the business-day closing rule (a closing day
   * falling on Sat/Sun is anticipated to the previous Friday). Never recompute
   * that rule here: the backend is the single source of truth.
   */
  monthlyChartDataSig = computed(() => {
    const periods = this.invoices();
    const year = this.selectedInvoice()?.invoice_year ?? new Date().getFullYear();
    if (!periods.length) return null;

    const totals = Array.from({ length: 12 }, () => 0);
    for (const e of this.allCardExpenses()) {
      const inv = periods.find(p => e.date >= p.period_start && e.date <= p.period_end);
      if (inv && inv.invoice_year === year) totals[inv.invoice_month - 1] += Math.abs(e.amount);
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
    this.categorySvc.list().subscribe({ next: cats => this.allCategories.set(cats) });
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
      next:  () => { const inv = this.selectedInvoice(); if (inv) { this.loadPage(inv); this.loadChart(inv); } },
      error: () => alert('Erro ao excluir o gasto. Tente novamente.'),
    });
  }

  // ─── Unified table filters (type / date range) ──────────────────────────
  onTypeFilterChange(event: Event): void {
    const val = (event.target as HTMLSelectElement).value as 'all' | 'individual' | 'compartilhado';
    this.typeFilter.set(val);
    this.currentPage.set(1);
  }
  onDateFromChange(event: Event): void {
    this.dateFromFilter.set((event.target as HTMLInputElement).value);
    this.currentPage.set(1);
  }
  onDateToChange(event: Event): void {
    this.dateToFilter.set((event.target as HTMLInputElement).value);
    this.currentPage.set(1);
  }
  clearAllFilters(): void {
    this.searchControl.setValue('');
    this.selectedCategoryId.set(null);
    this.typeFilter.set('all');
    this.dateFromFilter.set('');
    this.dateToFilter.set('');
    this.currentPage.set(1);
    this.loadPage();
  }

  // ─── Inline edit/delete for shared-debt rows (done directly on this screen) ──
  startEditShared(row: CombinedExpenseRow): void {
    const s = row.sharedEntry;
    if (!s) return;
    this.editingSharedId.set(s.id);
    this.editDraft.set({
      description: s.description,
      amount: Math.abs(s.amount),
      date: s.date,
      category_id: s.category,
    });
  }

  cancelEditShared(): void {
    this.editingSharedId.set(null);
    this.editDraft.set(null);
  }

  updateEditDraft(patch: Partial<EditSharedDraft>): void {
    const current = this.editDraft();
    if (!current) return;
    this.editDraft.set({ ...current, ...patch });
  }

  saveEditShared(): void {
    const id = this.editingSharedId();
    const draft = this.editDraft();
    if (id == null || !draft) return;
    this.savingEdit.set(true);
    this.sharedSvc.updateEntry(id, {
      description: draft.description,
      amount: draft.amount,
      date: draft.date,
      category_id: draft.category_id ?? undefined,
    }).subscribe({
      next: () => {
        this.savingEdit.set(false);
        this.editingSharedId.set(null);
        this.editDraft.set(null);
        this.reloadSharedEntries();
      },
      error: () => {
        this.savingEdit.set(false);
        alert('Erro ao salvar a alteracao. Tente novamente.');
      },
    });
  }

  deleteSharedEntry(row: CombinedExpenseRow): void {
    const s = row.sharedEntry;
    if (!s) return;
    if (!confirm(`Cancelar/excluir "${s.description}" (compartilhado)?`)) return;
    this.sharedSvc.deleteEntry(s.id).subscribe({
      next: () => this.reloadSharedEntries(),
      error: () => alert('Erro ao excluir o gasto compartilhado. Tente novamente.'),
    });
  }

  private reloadSharedEntries(): void {
    this.sharedSvc.listEntries({ credit_card: this.cardId }).subscribe({
      next: res => this.sharedEntries.set(res.results),
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
    this.d3.renderBar(el, barData, { showAvgLine: true, maxTicks: 8 });
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
  groupColor(index: number): string { return GROUP_COLORS[index % GROUP_COLORS.length]; }

  activeGroupId = signal<number | null>(null);

  activeGroup = computed((): SharedInvoiceGroup | null => {
    const groups = this.sharedGroups();
    if (!groups.length) return null;
    const id = this.activeGroupId();
    return groups.find(g => g.group_id === id) ?? groups[0];
  });

  activeGroupIndex = computed((): number => {
    const active = this.activeGroup();
    if (!active) return 0;
    return Math.max(0, this.sharedGroups().findIndex(g => g.group_id === active.group_id));
  });

  selectGroup(groupId: number): void { this.activeGroupId.set(groupId); }

  participantPct(amount: number, total: number): number {
    if (!total) return 0;
    return Math.round((Math.abs(amount) / Math.abs(total)) * 100);
  }

  initialOf(name: string): string { return (name || '?').trim().charAt(0).toUpperCase(); }

  /**
   * True when the effective closing date was anticipated because the nominal
   * closing_day fell on a weekend (backend rule: Sat/Sun -> previous Friday).
   */
  closingAnticipated = computed((): boolean => {
    const inv = this.selectedInvoice();
    const card = this.card();
    if (!inv || !card) return false;
    const [y, m] = inv.period_end.split('-').map(Number);
    const nominal = Math.min(card.closing_day, daysInMonth(y, m));
    return +inv.period_end.split('-')[2] !== nominal;
  });

  /** "Voce" (accented) for the current user, otherwise the member name. */
  displayName(p: InvoiceSharedParticipant): string {
    return p.is_current_user ? 'Voc\u00EA' : p.name;
  }
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
