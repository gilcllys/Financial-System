import { Component, OnInit, inject, signal, computed } from '@angular/core';
import { DebtService, VitoriaDebt, VitoriaSummary } from '../../core/services/debt.service';

@Component({
  selector: 'app-vitoria',
  standalone: true,
  imports: [],
  templateUrl: './vitoria.component.html',
  styleUrls: ['./vitoria.component.scss'],
})
export class VitoriaComponent implements OnInit {
  private debtService = inject(DebtService);

  debts = signal<VitoriaDebt[]>([]);
  summary = signal<VitoriaSummary | null>(null);
  loading = signal(true);
  markingId = signal<number | null>(null);
  showPaid = signal(false);

  pendingDebts = computed(() => this.debts().filter(d => !d.is_paid));
  paidDebts    = computed(() => this.debts().filter(d => d.is_paid));
  visibleDebts = computed(() => this.showPaid() ? this.debts() : this.pendingDebts());

  ngOnInit(): void { this.loadAll(); }

  private loadAll(): void {
    this.loading.set(true);
    let done = 0;
    const check = () => { if (++done === 2) this.loading.set(false); };

    this.debtService.list().subscribe({ next: d => { this.debts.set(d); check(); }, error: check });
    this.debtService.summary().subscribe({ next: s => { this.summary.set(s); check(); }, error: check });
  }

  markPaid(debt: VitoriaDebt): void {
    if (!confirm(`Marcar "${debt.expense_description}" como pago?`)) return;
    this.markingId.set(debt.id);
    this.debtService.markPaid(debt.id).subscribe({
      next: () => {
        this.debts.update(list => list.map(d => d.id === debt.id ? { ...d, is_paid: true } : d));
        this.summary.update(s => s ? {
          ...s,
          total_pending: s.total_pending - Math.abs(debt.expense_amount),
          total_paid:    s.total_paid   + Math.abs(debt.expense_amount),
          count_pending: s.count_pending - 1,
          count_paid:    s.count_paid   + 1,
        } : s);
        this.markingId.set(null);
      },
      error: () => this.markingId.set(null),
    });
  }

  formatCurrency(v: number): string {
    return new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(Math.abs(v));
  }

  formatDate(d: string): string {
    return d ? `${d.slice(8,10)}/${d.slice(5,7)}/${d.slice(0,4)}` : '';
  }
}
