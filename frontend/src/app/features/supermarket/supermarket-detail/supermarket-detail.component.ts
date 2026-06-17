import { Component, OnInit, inject, signal, computed } from '@angular/core';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { SlicePipe } from '@angular/common';
import { SupermarketService } from '../../../core/services/supermarket.service';
import { SupermarketExpense, SupermarketExpenseItem } from '../../../core/models';

@Component({
  selector: 'app-supermarket-detail',
  standalone: true,
  imports: [RouterLink, ReactiveFormsModule, SlicePipe],
  templateUrl: './supermarket-detail.component.html',
  styleUrls: ['./supermarket-detail.component.scss'],
})
export class SupermarketDetailComponent implements OnInit {
  private route = inject(ActivatedRoute);
  private service = inject(SupermarketService);
  private fb = inject(FormBuilder);

  expense = signal<SupermarketExpense | null>(null);
  loading = signal(true);
  addingItem = signal(false);
  deletingItemId = signal<number | null>(null);
  errorMessage = signal('');
  successMessage = signal('');

  /** Total calculado localmente para refletir adições/remoções imediatas */
  localTotal = computed(() => {
    const e = this.expense();
    if (!e) return 0;
    return e.items.reduce((sum, item) => sum + item.quantity * item.unit_price, 0);
  });

  itemForm = this.fb.group({
    description: ['', [Validators.required, Validators.minLength(2)]],
    quantity: [1, [Validators.required, Validators.min(1)]],
    unit_price: [null as number | null, [Validators.required, Validators.min(0.01)]],
  });

  ngOnInit(): void {
    const id = +(this.route.snapshot.paramMap.get('id') ?? 0);
    this.loadExpense(id);
  }

  loadExpense(id: number): void {
    this.loading.set(true);
    this.errorMessage.set('');
    this.service.get(id).subscribe({
      next: expense => {
        this.expense.set(expense);
        this.loading.set(false);
      },
      error: () => {
        this.errorMessage.set('Erro ao carregar compra. Tente novamente.');
        this.loading.set(false);
      },
    });
  }

  addItem(): void {
    if (this.itemForm.invalid) { this.itemForm.markAllAsTouched(); return; }
    const expense = this.expense();
    if (!expense) return;

    this.addingItem.set(true);
    this.errorMessage.set('');

    const v = this.itemForm.getRawValue();
    const payload = {
      supermarket_expense: expense.id,
      description: v.description!,
      quantity: v.quantity!,
      unit_price: v.unit_price!,
    };

    this.service.createItem(payload).subscribe({
      next: newItem => {
        this.expense.update(e => e ? { ...e, items: [...e.items, newItem] } : e);
        this.itemForm.reset({ description: '', quantity: 1, unit_price: null });
        this.addingItem.set(false);
        this.showSuccess('Item adicionado com sucesso!');
      },
      error: err => {
        this.addingItem.set(false);
        this.errorMessage.set(err?.error?.detail ?? 'Erro ao adicionar item. Tente novamente.');
      },
    });
  }

  deleteItem(item: SupermarketExpenseItem): void {
    if (!confirm(`Deseja remover "${item.description}"?`)) return;
    this.deletingItemId.set(item.id);
    this.errorMessage.set('');

    this.service.deleteItem(item.id).subscribe({
      next: () => {
        this.expense.update(e => e ? { ...e, items: e.items.filter(i => i.id !== item.id) } : e);
        this.deletingItemId.set(null);
      },
      error: () => {
        this.errorMessage.set('Erro ao remover item. Tente novamente.');
        this.deletingItemId.set(null);
      },
    });
  }

  itemSubtotal(item: SupermarketExpenseItem): number {
    return item.quantity * item.unit_price;
  }

  formatCurrency(value: number): string {
    return new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(value);
  }

  formatDate(date: string): string {
    if (!date || date.length < 10) return date;
    return `${date.slice(8, 10)}/${date.slice(5, 7)}/${date.slice(0, 4)}`;
  }

  hasItemError(field: string): boolean {
    const c = this.itemForm.get(field);
    return !!(c?.invalid && c?.touched);
  }

  private showSuccess(msg: string): void {
    this.successMessage.set(msg);
    setTimeout(() => this.successMessage.set(''), 3000);
  }
}
