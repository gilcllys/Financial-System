import { Component, OnInit, inject, signal, computed } from '@angular/core';
import { RouterLink } from '@angular/router';
import { DecimalPipe } from '@angular/common';
import { CardService } from '../../../core/services/card.service';
import { CreditCard, Expense, Invoice } from '../../../core/models';

const CARD_GRADIENTS = [
  'background: linear-gradient(135deg, #1a2a4a 0%, #2d4a7a 100%)',  // dark blue - Itau
  'background: linear-gradient(135deg, #6b21a8 0%, #9333ea 100%)',  // purple - Nubank
  'background: linear-gradient(135deg, #7f1d1d 0%, #b91c1c 100%)',  // dark red - Bradesco
  'background: linear-gradient(135deg, #d97706 0%, #f59e0b 100%)',  // orange - Inter
  'background: linear-gradient(135deg, #065f46 0%, #059669 100%)',  // green
  'background: linear-gradient(135deg, #1e3a5f 0%, #2563eb 100%)',  // blue
];

const MONTH_NAMES = ['Janeiro','Fevereiro','Março','Abril','Maio','Junho',
                     'Julho','Agosto','Setembro','Outubro','Novembro','Dezembro'];

@Component({
  selector: 'app-card-list',
  standalone: true,
  imports: [RouterLink, DecimalPipe],
  templateUrl: './card-list.component.html',
  styleUrls: ['./card-list.component.scss'],
})
export class CardListComponent implements OnInit {
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
    this.invoiceExpenses().reduce((s, e) => s + e.amount, 0)
  );

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
          this.selectCard(cards[0]);
          this.loadAllTotals(cards);
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
          this.invoiceTotals.update(t => ({ ...t, [card.id]: res.summary.total }));
        },
      });
    });
  }

  selectCard(card: CreditCard): void {
    this.selectedCardId.set(card.id);
    this.loadInvoice();
  }

  private loadInvoice(): void {
    const id = this.selectedCardId();
    if (!id) return;
    this.loadingInvoice.set(true);
    this.cardSvc.getInvoiceExpenses(id, this.invoiceMonth(), this.invoiceYear(), undefined, 1, 50).subscribe({
      next: res => {
        this.invoiceExpenses.set(res.expenses);
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
  }

  nextMonth(): void {
    let m = this.invoiceMonth() + 1, y = this.invoiceYear();
    if (m > 12) { m = 1; y++; }
    this.invoiceMonth.set(m); this.invoiceYear.set(y);
    this.loadInvoice();
  }

  cardGradient(index: number): string {
    return CARD_GRADIENTS[index % CARD_GRADIENTS.length];
  }

  openMenu(event: MouseEvent, card: CreditCard): void {
    event.stopPropagation();
    this.menuCard.set(card);
    this.menuX.set(event.clientX - 120);
    this.menuY.set(event.clientY + 8);
  }

  closeMenu(): void { this.menuCard.set(null); }

  deleteFromMenu(): void {
    const card = this.menuCard();
    if (!card || !confirm(`Deseja excluir o cartão "${card.name}"?`)) return;
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