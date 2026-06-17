import { Component, OnInit, inject, signal, computed } from '@angular/core';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { CardService } from '../../../core/services/card.service';
import { ExpenseService } from '../../../core/services/expense.service';
import { CreditCard, Expense } from '../../../core/models';
import { DatePipe } from '@angular/common';

@Component({
  selector: 'app-card-expenses',
  standalone: true,
  imports: [RouterLink, DatePipe],
  templateUrl: './card-expenses.component.html',
  styleUrls: ['./card-expenses.component.scss'],
})
export class CardExpensesComponent implements OnInit {
  private route = inject(ActivatedRoute);
  private cardService = inject(CardService);
  private expenseService = inject(ExpenseService);

  card = signal<CreditCard | null>(null);
  expenses = signal<Expense[]>([]);
  loading = signal(true);

  total = computed(() =>
    this.expenses().reduce((sum, e) => sum + e.amount, 0)
  );

  ngOnInit(): void {
    const id = +this.route.snapshot.paramMap.get('id')!;
    this.cardService.get(id).subscribe({ next: c => this.card.set(c) });
    this.expenseService.listByCard(id).subscribe({
      next: data => { this.expenses.set(data); this.loading.set(false); },
      error: () => this.loading.set(false),
    });
  }

  formatAmount(amount: number): string {
    return new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(Math.abs(amount));
  }

  amountClass(amount: number): string {
    return amount >= 0 ? 'value-up' : 'value-down';
  }

  amountPrefix(amount: number): string {
    return amount >= 0 ? '+' : '-';
  }
}
