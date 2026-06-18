import { Component, OnInit, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { SlicePipe, CurrencyPipe } from '@angular/common';
import { SupermarketService } from '../../../core/services/supermarket.service';
import { SupermarketExpense } from '../../../core/models';

@Component({
  selector: 'app-supermarket-list',
  standalone: true,
  imports: [RouterLink, SlicePipe],
  templateUrl: './supermarket-list.component.html',
  styleUrls: ['./supermarket-list.component.scss'],
})
export class SupermarketListComponent implements OnInit {
  private service = inject(SupermarketService);

  expenses = signal<SupermarketExpense[]>([]);
  loading = signal(true);
  deletingId = signal<number | null>(null);
  errorMessage = signal('');

  ngOnInit(): void {
    this.load();
  }

  load(): void {
    this.loading.set(true);
    this.errorMessage.set('');
    this.service.list().subscribe({
      next: list => {
        this.expenses.set(list);
        this.loading.set(false);
      },
      error: () => {
        this.errorMessage.set('Erro ao carregar compras. Tente novamente.');
        this.loading.set(false);
      },
    });
  }

  delete(expense: SupermarketExpense): void {
    if (!confirm(`Deseja excluir a compra em "${expense.store_name}"? Esta ação não pode ser desfeita.`)) return;
    this.deletingId.set(expense.id);
    this.service.delete(expense.id).subscribe({
      next: () => {
        this.expenses.update(list => list.filter(e => e.id !== expense.id));
        this.deletingId.set(null);
      },
      error: () => {
        this.errorMessage.set('Erro ao excluir compra. Tente novamente.');
        this.deletingId.set(null);
      },
    });
  }

  formatDate(date: string): string {
    // "2026-06-17" → "17/06/2026"
    if (!date || date.length < 10) return date;
    return `${date.slice(8, 10)}/${date.slice(5, 7)}/${date.slice(0, 4)}`;
  }

  formatCurrency(value: number): string {
    return new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(value);
  }
}
