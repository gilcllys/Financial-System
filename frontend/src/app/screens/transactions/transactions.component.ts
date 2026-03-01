import { Component, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatTableModule } from '@angular/material/table';
import { MatInputModule } from '@angular/material/input';
import { MatFormFieldModule } from '@angular/material/form-field';
import { FormsModule } from '@angular/forms';
import { MatSelectModule } from '@angular/material/select';
import { MatDatepickerModule } from '@angular/material/datepicker';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { Router } from '@angular/router';

export interface Transaction {
  id: number;
  name: string;
  value: number;
  statement: string;
  date: string;
  type: 'entrada' | 'saída';
}

const transacoes: Transaction[] = [
  {
    id: 1,
    name: 'Salário',
    value: 3500.0,
    statement: 'entrada',
    date: '2026-01-10',
    type: 'entrada',
  },
  {
    id: 2,
    name: 'Supermercado',
    value: -245.5,
    statement: 'saída',
    date: '2026-01-09',
    type: 'saída',
  },
  {
    id: 3,
    name: 'Aluguel',
    value: -1200.0,
    statement: 'saída',
    date: '2026-01-08',
    type: 'saída',
  },
  {
    id: 4,
    name: 'Freelance Design',
    value: 800.0,
    statement: 'entrada',
    date: '2026-01-07',
    type: 'entrada',
  },
  {
    id: 5,
    name: 'Conta de Luz',
    value: -189.75,
    statement: 'saída',
    date: '2026-01-06',
    type: 'saída',
  },
  {
    id: 6,
    name: 'Netflix',
    value: -39.9,
    statement: 'saída',
    date: '2026-01-05',
    type: 'saída',
  },
  {
    id: 7,
    name: 'Bônus Trabalho',
    value: 500.0,
    statement: 'entrada',
    date: '2026-01-04',
    type: 'entrada',
  },
  {
    id: 8,
    name: 'Restaurante',
    value: -125.3,
    statement: 'saída',
    date: '2026-01-03',
    type: 'saída',
  },
  {
    id: 9,
    name: 'Consultoria',
    value: 450.0,
    statement: 'entrada',
    date: '2026-01-02',
    type: 'entrada',
  },
  {
    id: 10,
    name: 'Combustível',
    value: -85.0,
    statement: 'saída',
    date: '2026-01-01',
    type: 'saída',
  },
];

interface TypeTransaction {
  value: string;
  viewValue: string;
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
  ],
  templateUrl: './transactions.component.html',
  styleUrl: './transactions.component.css',
  host: { style: 'display: contents' },
})
export class TransactionsComponent {
  displayedColumns: string[] = ['id', 'name', 'value', 'statement', 'date'];
  dataSource = transacoes;
  selectedValue: string;
  transaction_type: TypeTransaction[] = [
    { value: 'type-0', viewValue: 'Entrada' },
    { value: 'type-1', viewValue: 'Saída' },
  ];
  private router = inject(Router);

  constructor() {
    this.selectedValue = '';
  }

  goToNewTransaction() {
    this.router.navigate(['/transactions/new']);
  }
}
