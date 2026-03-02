import { CommonModule } from '@angular/common';
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

export interface Transaction {
  id: number;
  description: string;
  category: string;
  paymentMethod: string;
  amount: number;
  date: string;
  type: 'income' | 'expense';
}

const transacoes: Transaction[] = [
  {
    id: 1,
    description: 'Salário Mensal',
    category: 'Renda',
    paymentMethod: 'Transferência Bancária',
    amount: 2600.0,
    date: '2023-10-24',
    type: 'income',
  },
  {
    id: 2,
    description: 'Supermercado',
    category: 'Alimentação',
    paymentMethod: 'Cartão de Crédito',
    amount: -75.5,
    date: '2023-10-25',
    type: 'expense',
  },
  {
    id: 3,
    description: 'Posto de Gasolina',
    category: 'Transporte',
    paymentMethod: 'Cartão de Débito',
    amount: -45.0,
    date: '2023-10-23',
    type: 'expense',
  },
  {
    id: 4,
    description: 'Conta de Internet',
    category: 'Utilidades',
    paymentMethod: 'Cartão de Crédito',
    amount: -60.0,
    date: '2023-10-22',
    type: 'expense',
  },
  {
    id: 5,
    description: 'Jantar com amigos',
    category: 'Entretenimento',
    paymentMethod: 'Cartão de Crédito',
    amount: -120.3,
    date: '2023-10-20',
    type: 'expense',
  },
  {
    id: 6,
    description: 'Pagamento de Aluguel',
    category: 'Moradia',
    paymentMethod: 'Transferência Bancária',
    amount: -1200.0,
    date: '2023-10-15',
    type: 'expense',
  },
];

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
export class TransactionsComponent {
  displayedColumns: string[] = [
    'date',
    'description',
    'category',
    'paymentMethod',
    'amount',
    'actions',
  ];
  dataSource = transacoes;

  // Filtros
  searchText = signal('');
  startDate: Date | null = null;
  endDate: Date | null = null;
  selectedCategory = signal('all');
  selectedPaymentMethod = signal('all');

  categories: FilterOption[] = [
    { value: 'all', label: 'Todas' },
    { value: 'income', label: 'Renda' },
    { value: 'groceries', label: 'Alimentação' },
    { value: 'transport', label: 'Transporte' },
    { value: 'utilities', label: 'Utilidades' },
    { value: 'entertainment', label: 'Entretenimento' },
    { value: 'rent', label: 'Moradia' },
  ];

  paymentMethods: FilterOption[] = [
    { value: 'all', label: 'Todos' },
    { value: 'credit', label: 'Cartão de Crédito' },
    { value: 'debit', label: 'Cartão de Débito' },
    { value: 'bank', label: 'Transferência Bancária' },
    { value: 'cash', label: 'Dinheiro' },
  ];

  private router = inject(Router);

  clearDateFilter() {
    this.startDate = null;
    this.endDate = null;
  }

  goToNewTransaction() {
    this.router.navigate(['/transactions/new']);
  }

  editTransaction(transaction: Transaction) {
    console.log('Editar transação:', transaction);
    // Implementar navegação para edição
  }

  deleteTransaction(transaction: Transaction) {
    console.log('Deletar transação:', transaction);
    // Implementar lógica de deleção
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
