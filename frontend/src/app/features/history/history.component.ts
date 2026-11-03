import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import { CardService } from '../../core/services/card.service';
import { CategoryService } from '../../core/services/category.service';
import { ConfirmDialogService } from '../../core/services/confirm-dialog.service';
import { ExpenseService, HistoryEntry, HistoryTotals } from '../../core/services/expense.service';
import { SharedDebtService } from '../../core/services/shared-debt.service';
import { ToastService } from '../../core/services/toast.service';
import { CreditCard, ExpenseCategory, PaymentMethod } from '../../core/models';

const EMPTY_TOTALS: HistoryTotals = { count: 0, income: 0, expenses: 0, net: 0 };

@Component({
  selector: 'app-history',
  standalone: true,
  imports: [FormsModule, RouterLink],
  templateUrl: './history.component.html',
  styleUrls: ['./history.component.scss'],
})
export class HistoryComponent implements OnInit {
  private expenseService = inject(ExpenseService);
  private sharedDebtService = inject(SharedDebtService);
  private categoryService = inject(CategoryService);
  private cardService = inject(CardService);
  private confirmDialog = inject(ConfirmDialogService);
  private toast = inject(ToastService);
  private router = inject(Router);

  readonly PAGE_SIZE = 20;
  readonly MONTHS = [
    { value: 1, label: 'Janeiro' }, { value: 2, label: 'Fevereiro' },
    { value: 3, label: 'Março' }, { value: 4, label: 'Abril' },
    { value: 5, label: 'Maio' }, { value: 6, label: 'Junho' },
    { value: 7, label: 'Julho' }, { value: 8, label: 'Agosto' },
    { value: 9, label: 'Setembro' }, { value: 10, label: 'Outubro' },
    { value: 11, label: 'Novembro' }, { value: 12, label: 'Dezembro' },
  ];

  categories = signal<ExpenseCategory[]>([]);
  cards = signal<CreditCard[]>([]);
  entries = signal<HistoryEntry[]>([]);
  loading = signal(false);
  error = signal(false);
  totals = signal<HistoryTotals>(EMPTY_TOTALS);
  page = signal(1);
  selected = signal<Set<number>>(new Set());
  savingCategory = signal(false);

  filterMonth = signal<number | null>(null);
  filterYear = signal<number | null>(new Date().getFullYear());
  filterCategory = signal<number | null>(null);
  filterPayment = signal<PaymentMethod | null>(null);
  filterCard = signal<number | null>(null);
  filterStartDate = signal('');
  filterEndDate = signal('');
  filterSearch = signal('');
  minAmount = signal('');
  maxAmount = signal('');
  includeFuture = signal(false);
  entryType = signal<'all' | 'individual' | 'shared'>('all');
  bulkCategory = signal<number | null>(null);

  totalPages = computed(() => Math.max(1, Math.ceil(this.totals().count / this.PAGE_SIZE)));
  selectedIndividualEntries = computed(() => this.entries().filter(entry =>
    entry.type === 'individual' && this.selected().has(entry.id)
  ));
  bulkCategories = computed(() => {
    const selected = this.selectedIndividualEntries();
    if (!selected.length) return [];
    const kind = selected[0].amount >= 0 ? 'receita' : 'despesa';
    if (selected.some(entry => (entry.amount >= 0 ? 'receita' : 'despesa') !== kind)) return [];
    return this.categories().filter(category => (category.kind ?? 'despesa') === kind);
  });

  ngOnInit(): void {
    this.categoryService.list().subscribe({ next: categories => this.categories.set(categories) });
    this.cardService.list().subscribe({ next: cards => this.cards.set(cards) });
    this.load();
  }

  private filters(): Record<string, string | number | boolean | null | undefined> {
    return {
      month: this.filterMonth() ?? undefined,
      year: this.filterYear() ?? undefined,
      category_id: this.filterCategory() ?? undefined,
      payment_method: this.filterPayment() ?? undefined,
      credit_card_id: this.filterCard() ?? undefined,
      start_date: this.filterStartDate() || undefined,
      end_date: this.filterEndDate() || undefined,
      search: this.filterSearch().trim() || undefined,
      min_amount: this.minAmount() || undefined,
      max_amount: this.maxAmount() || undefined,
      include_future: this.includeFuture(),
      type: this.entryType() === 'all' ? undefined : this.entryType(),
    };
  }

  load(): void {
    this.loading.set(true);
    this.error.set(false);
    this.expenseService.history({ ...this.filters(), page: this.page(), page_size: this.PAGE_SIZE }).subscribe({
      next: response => {
        this.entries.set(response.results);
        this.totals.set(response.totals);
        this.selected.set(new Set());
        this.loading.set(false);
      },
      error: () => { this.error.set(true); this.loading.set(false); },
    });
  }

  applyFilters(): void { this.page.set(1); this.load(); }
  clearFilters(): void {
    this.filterMonth.set(null); this.filterYear.set(new Date().getFullYear());
    this.filterCategory.set(null); this.filterPayment.set(null); this.filterCard.set(null);
    this.filterStartDate.set(''); this.filterEndDate.set(''); this.filterSearch.set('');
    this.minAmount.set(''); this.maxAmount.set(''); this.includeFuture.set(false); this.entryType.set('all');
    this.applyFilters();
  }
  goToPage(page: number): void {
    if (page < 1 || page > this.totalPages()) return;
    this.page.set(page); this.load();
  }

  isSelected(entry: HistoryEntry): boolean { return entry.type === 'individual' && this.selected().has(entry.id); }
  toggleSelected(entry: HistoryEntry): void {
    if (entry.type !== 'individual') return;
    this.selected.update(current => {
      const next = new Set(current);
      next.has(entry.id) ? next.delete(entry.id) : next.add(entry.id);
      return next;
    });
  }
  selectVisible(): void {
    const visible = this.entries().filter(entry => entry.type === 'individual');
    this.selected.update(current => {
      const next = new Set(current);
      const allSelected = visible.length > 0 && visible.every(entry => next.has(entry.id));
      for (const entry of visible) allSelected ? next.delete(entry.id) : next.add(entry.id);
      return next;
    });
  }
  async updateCategory(): Promise<void> {
    const ids = this.selectedIndividualEntries().map(entry => entry.id);
    const categoryId = this.bulkCategory();
    if (!ids.length || !categoryId) return;
    this.savingCategory.set(true);
    this.expenseService.updateHistoryCategories(ids, categoryId).subscribe({
      next: result => { this.toast.success(`${result.updated} lançamentos atualizados.`); this.savingCategory.set(false); this.bulkCategory.set(null); this.load(); },
      error: err => { this.toast.apiError(err, 'Não foi possível atualizar as categorias.'); this.savingCategory.set(false); },
    });
  }
  exportCsv(): void {
    this.expenseService.downloadHistoryCsv(this.filters()).subscribe({
      next: blob => {
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url; link.download = 'historico.csv'; link.click(); URL.revokeObjectURL(url);
      },
      error: err => this.toast.apiError(err, 'Não foi possível exportar o histórico.'),
    });
  }
  edit(entry: HistoryEntry): void {
    if (entry.type === 'individual') this.router.navigate(['/expenses', entry.id, 'edit']);
    else if (entry.group_id) this.router.navigate(['/shared-debts', entry.group_id], { queryParams: { edit_entry: entry.id } });
  }
  async delete(entry: HistoryEntry): Promise<void> {
    if (!(await this.confirmDialog.confirm(`Excluir “${entry.description}”${entry.type === 'shared' ? ` do grupo ${entry.group_name}` : ''}?`))) return;
    const request = entry.type === 'individual'
      ? this.expenseService.delete(entry.id)
      : this.sharedDebtService.deleteEntry(entry.id);
    request.subscribe({
      next: () => { this.toast.success('Lançamento excluído.'); this.load(); },
      error: err => this.toast.apiError(err, 'Não foi possível excluir o lançamento.'),
    });
  }
  cardName(entry: HistoryEntry): string {
    if (!entry.credit_card_id) return '—';
    return entry.card_name ?? `Cartão de ${entry.paid_by_name ?? 'outro membro'}`;
  }
  ownPortion(entry: HistoryEntry): number {
    if (entry.type === 'shared') return Math.abs(entry.own_portion ?? (Math.abs(entry.amount) / Math.max(entry.participant_count ?? 1, 1)));
    return Math.abs(entry.amount);
  }
  formatCurrency(value: number): string {
    const sign = value > 0 ? '+' : value < 0 ? '−' : '';
    return `${sign}${new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(Math.abs(value))}`;
  }
  formatDate(value: string): string {
    const [year, month, day] = value.split('-');
    return `${day}/${month}/${year}`;
  }
}
