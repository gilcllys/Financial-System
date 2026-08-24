import { Component, OnInit, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { SlicePipe } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ExpenseService } from '../../core/services/expense.service';
import { CategoryService } from '../../core/services/category.service';
import { Expense, ExpenseCategory } from '../../core/models';

@Component({
  selector: 'app-uncategorized',
  standalone: true,
  imports: [RouterLink, FormsModule, SlicePipe],
  template: `
    <div class="page-header">
      <div>
        <h1 class="page-header__title">⚠️ Sem Categoria</h1>
        <p class="page-header__subtitle">{{ items().length }} lançamentos sem categoria</p>
      </div>
    </div>

    @if (loading()) {
      <div class="loading-state"><div class="spinner"></div><p>Carregando...</p></div>
    } @else if (items().length === 0) {
      <div class="empty-state">
        <div class="empty-state__icon">✅</div>
        <p class="empty-state__title">Tudo categorizado!</p>
        <p class="empty-state__text">Todos os seus lançamentos têm categoria.</p>
      </div>
    } @else {
      <div class="data-table-wrapper">
        <table class="data-table" aria-label="Lançamentos sem categoria">
          <thead>
            <tr>
              <th>Descrição</th>
              <th>Data</th>
              <th class="text-right">Valor</th>
              <th>Categorizar</th>
            </tr>
          </thead>
          <tbody>
            @for (e of items(); track e.id) {
              <tr>
                <td>{{ e.description }}</td>
                <td class="mono text-muted">{{ e.date | slice:8:10 }}/{{ e.date | slice:5:7 }}</td>
                <td class="text-right mono" [class.value-up]="e.amount >= 0" [class.value-down]="e.amount < 0">
                  {{ e.amount >= 0 ? '+' : '-' }}{{ fmt(e.amount) }}
                </td>
                <td>
                  <select class="form-select form-select--sm"
                    (change)="categorize(e, $any($event.target).value)"
                    aria-label="Selecionar categoria para {{ e.description }}">
                    <option value="">Selecionar…</option>
                    @for (c of categories(); track c.id) {
                      <option [value]="c.id">{{ c.name }}</option>
                    }
                  </select>
                </td>
              </tr>
            }
          </tbody>
        </table>
      </div>
    }
  `,
})
export class UncategorizedComponent implements OnInit {
  private expenseService = inject(ExpenseService);
  private categoryService = inject(CategoryService);

  items      = signal<Expense[]>([]);
  categories = signal<ExpenseCategory[]>([]);
  loading    = signal(true);

  ngOnInit(): void {
    this.categoryService.list().subscribe({ next: c => this.categories.set(c) });
    this.load();
  }

  private load(): void {
    this.loading.set(true);
    // ponytail: reuse list() — filter client-side for uncategorized
    this.expenseService.list({ page_size: 200 }).subscribe({
      next: res => {
        this.items.set(res.results.filter(e => !e.category_id));
        this.loading.set(false);
      },
      error: () => this.loading.set(false),
    });
  }

  categorize(expense: Expense, categoryId: string): void {
    if (!categoryId) return;
    this.expenseService.update(expense.id, { ...expense, category_id: +categoryId } as any).subscribe({
      next: () => this.items.update(list => list.filter(e => e.id !== expense.id)),
    });
  }

  fmt(v: number): string {
    return new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(Math.abs(v));
  }
}

