import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import { forkJoin } from 'rxjs';
import { CardService } from '../../core/services/card.service';
import { CategoryService } from '../../core/services/category.service';
import { ExpenseService } from '../../core/services/expense.service';
import { SharedDebtEntry, SharedDebtService } from '../../core/services/shared-debt.service';
import { CreditCard, Expense, ExpenseCategory, PaymentMethod } from '../../core/models';

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
  private router = inject(Router);

  readonly PAGE_SIZE = 20;
  readonly MONTHS = [
    { value: 1, label: 'Janeiro' }, { value: 2, label: 'Fevereiro' },
    { value: 3, label: 'Marco' }, { value: 4, label: 'Abril' },
    { value: 5, label: 'Maio' }, { value: 6, label: 'Junho' },
    { value: 7, label: 'Julho' }, { value: 8, label: 'Agosto' },
    { value: 9, label: 'Setembro' }, { value: 10, label: 'Outubro' },
    { value: 11, label: 'Novembro' }, { value: 12, label: 'Dezembro' },
  ];

  categories = signal<ExpenseCategory[]>([]);
  cards = signal<CreditCard[]>([]);

  filterMonth = signal<number | null>(null);
  filterYear = signal<number | null>(new Date().getFullYear());
  filterCategory = signal<number | null>(null);
  filterPayment = signal<PaymentMethod | null>(null);
  filterCard = signal<number | null>(null);
  filterStartDate = signal<string>('');
  filterEndDate = signal<string>('');
  filterSearch = signal<string>('');

  individualExpenses = signal<Expense[]>([]);
  sharedExpenses = signal<SharedDebtEntry[]>([]);
  individualLoading = signal(false);
  sharedLoading = signal(false);
  individualTotal = signal(0);
  sharedTotal = signal(0);
  individualPage = signal(1);
  sharedPage = signal(1);

  individualTotalPages = computed(() => Math.max(1, Math.ceil(this.individualTotal() / this.PAGE_SIZE)));
  sharedTotalPages = computed(() => Math.max(1, Math.ceil(this.sharedTotal() / this.PAGE_SIZE)));
  individualPageNumbers = computed(() => this.pageNumbers(this.individualTotalPages()));
  sharedPageNumbers = computed(() => this.pageNumbers(this.sharedTotalPages()));

  ngOnInit(): void {
    forkJoin({
      categories: this.categoryService.list(),
      cards: this.cardService.list(),
    }).subscribe({
      next: ({ categories, cards }) => {
        this.categories.set(categories);
        this.cards.set(cards);
      },
    });

    this.loadAll();
  }

  applyFilters(): void {
    this.individualPage.set(1);
    this.sharedPage.set(1);
    this.loadAll();
  }

  clearFilters(): void {
    this.filterMonth.set(null);
    this.filterYear.set(new Date().getFullYear());
    this.filterCategory.set(null);
    this.filterPayment.set(null);
    this.filterCard.set(null);
    this.filterStartDate.set('');
    this.filterEndDate.set('');
    this.filterSearch.set('');
    this.applyFilters();
  }

  goToIndividualPage(page: number): void {
    if (page < 1 || page > this.individualTotalPages()) return;
    this.individualPage.set(page);
    this.loadIndividual();
  }

  goToSharedPage(page: number): void {
    if (page < 1 || page > this.sharedTotalPages()) return;
    this.sharedPage.set(page);
    this.loadShared();
  }

  editIndividual(expense: Expense): void {
    this.router.navigate(['/expenses', expense.id, 'edit']);
  }

  deleteIndividual(expense: Expense): void {
    if (!confirm(`Excluir "${expense.description}"?`)) return;
    this.expenseService.delete(expense.id).subscribe({ next: () => this.loadIndividual() });
  }

  editShared(entry: SharedDebtEntry): void {
    this.router.navigate(['/shared-debts', entry.shared_debt], { queryParams: { edit_entry: entry.id } });
  }

  deleteShared(entry: SharedDebtEntry): void {
    if (!confirm(`Excluir "${entry.description}" do grupo "${entry.shared_debt_name}"?`)) return;
    this.sharedDebtService.deleteEntry(entry.id).subscribe({ next: () => this.loadShared() });
  }

  formatCurrency(value: number | string): string {
    return new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(Math.abs(Number(value)));
  }

  formatSignedCurrency(value: number | string): string {
    const amount = Number(value);
    const prefix = amount >= 0 ? '+' : '-';
    return `${prefix}${this.formatCurrency(amount)}`;
  }

  formatDate(value: string): string {
    const [year, month, day] = value.split('-');
    return `${day}/${month}/${year}`;
  }

  categoryName(expense: Expense): string {
    return expense.category?.name ?? this.categories().find(c => c.id === expense.category_id)?.name ?? 'Sem categoria';
  }

  cardName(cardId: number | null | undefined): string {
    if (!cardId) return '-';
    return this.cards().find(c => c.id === cardId)?.name ?? `Cartao #${cardId}`;
  }

  paymentLabel(method: PaymentMethod): string {
    return method === 'cartao' ? 'Cartao' : 'Dinheiro';
  }

  mySharedPortion(entry: SharedDebtEntry): number {
    return Number(entry.amount) / Math.max(Number(entry.participant_count) || 1, 1);
  }

  private loadAll(): void {
    this.loadIndividual();
    this.loadShared();
  }

  private loadIndividual(): void {
    this.individualLoading.set(true);
    this.expenseService.list({
      month: this.filterMonth() ?? undefined,
      year: this.filterYear() ?? undefined,
      category_id: this.filterCategory() ?? undefined,
      payment_method: this.filterPayment() ?? undefined,
      credit_card_id: this.filterCard() ?? undefined,
      start_date: this.filterStartDate() || undefined,
      end_date: this.filterEndDate() || undefined,
      search: this.filterSearch().trim() || undefined,
      page: this.individualPage(),
      page_size: this.PAGE_SIZE,
    }).subscribe({
      next: res => {
        this.individualExpenses.set(res.results);
        this.individualTotal.set(res.count);
        this.individualLoading.set(false);
      },
      error: () => this.individualLoading.set(false),
    });
  }

  private loadShared(): void {
    this.sharedLoading.set(true);
    this.sharedDebtService.listEntries({
      month: this.filterMonth() ?? undefined,
      year: this.filterYear() ?? undefined,
      category: this.filterCategory() ?? undefined,
      payment_method: this.filterPayment() ?? undefined,
      credit_card: this.filterCard() ?? undefined,
      start_date: this.filterStartDate() || undefined,
      end_date: this.filterEndDate() || undefined,
      page: this.sharedPage(),
      page_size: this.PAGE_SIZE,
    }).subscribe({
      next: res => {
        this.sharedExpenses.set(res.results);
        this.sharedTotal.set(res.count);
        this.sharedLoading.set(false);
      },
      error: () => this.sharedLoading.set(false),
    });
  }

  private pageNumbers(totalPages: number): number[] {
    return Array.from({ length: totalPages }, (_, index) => index + 1);
  }
}
