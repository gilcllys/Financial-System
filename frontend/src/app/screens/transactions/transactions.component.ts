import { CommonModule } from '@angular/common';
import type { OnInit } from '@angular/core';
import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatDatepickerModule } from '@angular/material/datepicker';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatPaginatorModule } from '@angular/material/paginator';
import { MatSelectModule } from '@angular/material/select';
import { MatTableModule } from '@angular/material/table';
import { MatTooltipModule } from '@angular/material/tooltip';
import { Router } from '@angular/router';
import type { Expense } from '../../models';
import { ExpenseService } from '../../services/expense.service';

export interface Transaction {
  id: number;
  description: string;
  category: string;
  amount: number;
  date: string;
  type: 'income' | 'expense';
}

interface FilterOption {
  value: string;
  label: string;
}

@Component({
  selector: 'app-transactions',
  standalone: true,
  imports: [
    CommonModule,
    MatTableModule,
    FormsModule,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule,
    MatDatepickerModule,
    MatIconModule,
    MatButtonModule,
    MatPaginatorModule,
    MatTooltipModule,
  ],
  templateUrl: './transactions.component.html',
  styleUrl: './transactions.component.css',
  host: { style: 'display: contents' },
})
export class TransactionsComponent implements OnInit {
  displayedColumns: string[] = [
    'date',
    'description',
    'category',
    'amount',
    'actions',
  ];
  dataSource: Transaction[] = [];

  // Filtros
  searchText = signal('');
  startDate: Date | null = null;
  endDate: Date | null = null;
  selectedCategory = signal('all');

  categories: FilterOption[] = [{ value: 'all', label: 'Todas' }];

  private router = inject(Router);
  private expenseService = inject(ExpenseService);

  ngOnInit(): void {
    this.loadExpenses();
    this.loadCategories();
  }

  private loadExpenses(): void {
    this.expenseService.getExpenses().subscribe({
      next: (expenses: Expense[]) => {
        this.dataSource = expenses.map((e) => ({
          id: e.id,
          description: e.description,
          category: e.category?.name || `Cat. ${e.categoryId}`,
          amount: e.amount,
          date:
            e.date instanceof Date
              ? e.date.toISOString().split('T')[0]
              : String(e.date),
          type: e.amount >= 0 ? ('income' as const) : ('expense' as const),
        }));
      },
      error: (err) => console.error('Erro ao carregar transações:', err),
    });
  }

  private loadCategories(): void {
    this.expenseService.getCategories().subscribe({
      next: (cats) => {
        this.categories = [
          { value: 'all', label: 'Todas' },
          ...cats.map((c) => ({ value: String(c.id), label: c.name })),
        ];
      },
      error: (err) => console.error('Erro ao carregar categorias:', err),
    });
  }

  clearDateFilter() {
    this.startDate = null;
    this.endDate = null;
  }

  goToNewTransaction() {
    this.router.navigate(['/transactions/new']);
  }

  editTransaction(transaction: Transaction) {
    console.log('Editar transação:', transaction);
  }

  deleteTransaction(transaction: Transaction) {
    console.log('Deletar transação:', transaction);
  }

  formatAmount(amount: number): string {
    const formatted = Math.abs(amount).toLocaleString('pt-BR', {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    });
    return amount >= 0 ? `+R$${formatted}` : `-R$${formatted}`;
  }

  isIncome(amount: number): boolean {
    return amount >= 0;
  }
}
