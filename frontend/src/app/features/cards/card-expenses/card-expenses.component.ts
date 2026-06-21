import { Component, OnInit, inject, signal, computed } from '@angular/core';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { CardService } from '../../../core/services/card.service';
import { ExpenseService } from '../../../core/services/expense.service';
import { CreditCard, Expense, Invoice, InvoiceCategoryBreakdown, InvoiceExpensesResponse } from '../../../core/models';
import { DatePipe, DecimalPipe } from '@angular/common';
import { FormsModule } from '@angular/forms';

@Component({
  selector: 'app-card-expenses',
  standalone: true,
  imports: [RouterLink, DatePipe, DecimalPipe, FormsModule],
  templateUrl: './card-expenses.component.html',
  styleUrls: ['./card-expenses.component.scss'],
})
export class CardExpensesComponent implements OnInit {
  private route = inject(ActivatedRoute);
  private cardService = inject(CardService);

  cardId = 0;
  card = signal<CreditCard | null>(null);
  invoices = signal<Invoice[]>([]);
  selectedInvoice = signal<Invoice | null>(null);
  selectedCategoryId = signal<number | null>(null);

  invoiceData = signal<InvoiceExpensesResponse | null>(null);
  loadingInvoices = signal(true);
  loadingExpenses = signal(false);

  /** Name of the currently active category filter, derived from breakdown data. */
  selectedCategoryName = computed(() => {
    const catId = this.selectedCategoryId();
    const data = this.invoiceData();
    if (!catId || !data) return null;
    return data.by_category.find(c => c.category_id === catId)?.category_name ?? null;
  });

  /** Filtered expenses (client-side category filter). */
  filteredExpenses = computed(() => {
    const data = this.invoiceData();
    const catId = this.selectedCategoryId();
    if (!data) return [];
    if (!catId) return data.expenses;
    return data.expenses.filter(e => e.category_id === catId);
  });

  filteredTotal = computed(() =>
    this.filteredExpenses().reduce((sum, e) => sum + Math.abs(e.amount), 0)
  );

  ngOnInit(): void {
    this.cardId = +this.route.snapshot.paramMap.get('id')!;
    this.cardService.get(this.cardId).subscribe({ next: c => this.card.set(c) });
    this.cardService.getInvoices(this.cardId).subscribe({
      next: invoices => {
        this.invoices.set(invoices);
        this.loadingInvoices.set(false);
        const current = invoices.find(i => i.is_current) ?? invoices[0];
        if (current) {
          this.selectedInvoice.set(current);
          this.loadInvoiceExpenses(current);
        }
      },
      error: () => this.loadingInvoices.set(false),
    });
  }

  selectInvoice(invoice: Invoice): void {
    this.selectedInvoice.set(invoice);
    this.selectedCategoryId.set(null);
    this.loadInvoiceExpenses(invoice);
  }

  selectCategory(categoryId: number | null): void {
    this.selectedCategoryId.set(categoryId);
  }

  private expenseService = inject(ExpenseService);

  private loadInvoiceExpenses(invoice: Invoice): void {
    this.loadingExpenses.set(true);
    this.invoiceData.set(null);
    this.cardService.getInvoiceExpenses(
      this.cardId,
      invoice.invoice_month,
      invoice.invoice_year
    ).subscribe({
      next: data => {
        this.invoiceData.set(data);
        this.loadingExpenses.set(false);
      },
      error: () => this.loadingExpenses.set(false),
    });
  }

  deleteExpense(expense: Expense): void {
    if (!confirm(`Excluir "${expense.description}"? Esta ação não pode ser desfeita.`)) return;
    this.expenseService.delete(expense.id).subscribe({
      next: () => {
        const inv = this.selectedInvoice();
        if (inv) this.loadInvoiceExpenses(inv);
      },
      error: () => alert('Erro ao excluir o gasto. Tente novamente.'),
    });
  }

  formatAmount(amount: number): string {
    return new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(Math.abs(amount));
  }

  formatDate(dateStr: string): string {
    const [y, m, d] = dateStr.split('-');
    return `${d}/${m}/${y}`;
  }

  roundPct(value: number): number {
    return Math.round(value);
  }
}
