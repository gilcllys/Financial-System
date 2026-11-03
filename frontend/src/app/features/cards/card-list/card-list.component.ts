import { Component, OnInit, inject, signal, computed } from '@angular/core';
import { ConfirmDialogService } from '../../../core/services/confirm-dialog.service';
import { RouterLink } from '@angular/router';
import { CardService } from '../../../core/services/card.service';
import { CreditCard, Expense, Invoice, InvoiceExpensesResponse } from '../../../core/models';

const MONTH_NAMES = ['Janeiro','Fevereiro','Março','Abril','Maio','Junho',
                     'Julho','Agosto','Setembro','Outubro','Novembro','Dezembro'];

@Component({
  selector: 'app-card-list',
  standalone: true,
  imports: [RouterLink],
  templateUrl: './card-list.component.html',
  styleUrls: ['./card-list.component.scss'],
})
export class CardListComponent implements OnInit {
  private confirmDialog = inject(ConfirmDialogService);
  private cardSvc = inject(CardService);

  cards        = signal<CreditCard[]>([]);
  loading      = signal(true);
  deletingId   = signal<number | null>(null);

  // selected card + inline invoice
  selectedCardId   = signal<number | null>(null);
  selectedCard     = computed(() => this.cards().find(c => c.id === this.selectedCardId()) ?? null);
  invoiceMonth     = signal(new Date().getMonth() + 1);
  invoiceYear      = signal(new Date().getFullYear());
  invoiceExpenses  = signal<Expense[]>([]);
  invoiceTotals    = signal<Record<number, number>>({});
  loadingInvoice   = signal(false);

  // context menu
  menuCard = signal<CreditCard | null>(null);
  menuX    = signal(0);
  menuY    = signal(0);

  currentMonthLabel = computed(() =>
    `${MONTH_NAMES[this.invoiceMonth() - 1]} ${this.invoiceYear()}`
  );

  invoiceTotal = computed(() =>
    this.invoiceExpenses().reduce((s, e) => s + Number(e.amount), 0)
  );
  totalInvoices = computed(() => Object.values(this.invoiceTotals()).reduce((total, amount) => total + amount, 0));

  private readonly installmentRe = /parcela\s+(\d+)\/(\d+)/i;

  ngOnInit(): void {
    this.load();
  }

  private load(): void {
    this.cardSvc.list().subscribe({
      next: cards => {
        this.cards.set(cards);
        this.loading.set(false);
        if (cards.length > 0) {
          this.selectCard(cards[0], true);
        }
      },
      error: () => this.loading.set(false),
    });
  }

  private loadAllTotals(cards: CreditCard[]): void {
    const m = this.invoiceMonth(), y = this.invoiceYear();
    cards.forEach(card => {
      this.cardSvc.getInvoiceExpenses(card.id, m, y, undefined, 1, 200).subscribe({
        next: res => {
          this.invoiceTotals.update(t => ({ ...t, [card.id]: this.grossTotal(res) }));
        },
      });
    });
  }

  /** Valor bruto da fatura (o que o banco cobra): individual + valor cheio do compartilhado. */
  private grossTotal(res: InvoiceExpensesResponse): number {
    const s = res.summary;
    return (s.expenses_total ?? s.total) + (s.shared_breakdown?.total ?? 0);
  }

  selectCard(card: CreditCard, useCurrentInvoice = false): void {
    this.selectedCardId.set(card.id);
    if (!useCurrentInvoice) {
      this.loadInvoice();
      return;
    }

    this.cardSvc.getInvoices(card.id).subscribe({
      next: invoices => {
        const current = invoices.find(invoice => invoice.is_current) ?? invoices[0];
        if (current) {
          this.invoiceMonth.set(current.invoice_month);
          this.invoiceYear.set(current.invoice_year);
        }
        this.loadInvoice();
        this.loadAllTotals(this.cards());
      },
      error: () => this.loadInvoice(),
    });
  }

  private loadInvoice(): void {
    const id = this.selectedCardId();
    if (!id) return;
    this.loadingInvoice.set(true);
    this.cardSvc.getInvoiceExpenses(id, this.invoiceMonth(), this.invoiceYear(), undefined, 1, 50).subscribe({
      next: res => {
        this.invoiceExpenses.set(res.expenses);
        this.invoiceTotals.update(t => ({ ...t, [id]: this.grossTotal(res) }));
        this.loadingInvoice.set(false);
      },
      error: () => this.loadingInvoice.set(false),
    });
  }

  prevMonth(): void {
    let m = this.invoiceMonth() - 1, y = this.invoiceYear();
    if (m < 1) { m = 12; y--; }
    this.invoiceMonth.set(m); this.invoiceYear.set(y);
    this.loadInvoice();
    this.loadAllTotals(this.cards());
  }

  nextMonth(): void {
    let m = this.invoiceMonth() + 1, y = this.invoiceYear();
    if (m > 12) { m = 1; y++; }
    this.invoiceMonth.set(m); this.invoiceYear.set(y);
    this.loadInvoice();
    this.loadAllTotals(this.cards());
  }

  
  getInstallmentBadge(e: Expense): { text: string; isBadge: boolean } {
    const m = /\b(\d+)\/(\d+)\b/i.exec(e.description) || /parcela\s+(\d+)\/(\d+)/i.exec(e.description);
    if (m) {
      if (m[1] === '1' && m[2] === '1') return { text: 'Parcela ?nica', isBadge: true };
      return { text: `${m[1]}/${m[2]}`, isBadge: true };
    }
    const desc = e.description.toLowerCase();
    if (desc.includes('fixa') || desc.includes('assinatura') || (e as any).is_recurring) {
      return { text: 'Fixa', isBadge: true };
    }
    if (desc.includes('?nica') || desc.includes('unica')) {
      return { text: 'Parcela ?nica', isBadge: true };
    }
    if (e.quantity === 1 && !(e as any).is_installment) {
      return { text: 'Parcela ?nica', isBadge: true };
    }
    return { text: '-', isBadge: false };
  }


  openMenu(event: MouseEvent, card: CreditCard): void {
    event.stopPropagation();
    this.menuCard.set(card);
    this.menuX.set(event.clientX - 120);
    this.menuY.set(event.clientY + 8);
  }

  closeMenu(): void { this.menuCard.set(null); }

  async deleteFromMenu(): Promise<void> {
    const card = this.menuCard();
    if (!card || !(await this.confirmDialog.confirm(`Deseja excluir o cartão "${card.name}"?`))) return;
    this.closeMenu();
    this.deletingId.set(card.id);
    this.cardSvc.delete(card.id).subscribe({
      next: () => {
        this.cards.update(list => list.filter(c => c.id !== card.id));
        if (this.selectedCardId() === card.id) {
          const remaining = this.cards();
          if (remaining.length) this.selectCard(remaining[0]);
          else this.selectedCardId.set(null);
        }
        this.deletingId.set(null);
      },
      error: () => this.deletingId.set(null),
    });
  }

  installmentBadge(e: Expense): string | null {
    const m = this.installmentRe.exec(e.description);
    return m ? `Parcela ${m[1]}/${m[2]}` : null;
  }

  formatAmount(v: number): string {
    return new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(v ?? 0);
  }

  formatDate(iso: string): string {
    const [y, m, d] = iso.split('-');
    return `${d}/${m}/${y}`;
  }
}
