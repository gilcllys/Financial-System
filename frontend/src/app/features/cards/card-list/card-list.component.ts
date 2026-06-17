import { Component, OnInit, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { CardService } from '../../../core/services/card.service';
import { CreditCard } from '../../../core/models';

@Component({
  selector: 'app-card-list',
  standalone: true,
  imports: [RouterLink],
  templateUrl: './card-list.component.html',
  styleUrls: ['./card-list.component.scss'],
})
export class CardListComponent implements OnInit {
  private cardService = inject(CardService);

  cards = signal<CreditCard[]>([]);
  loading = signal(true);
  deletingId = signal<number | null>(null);

  ngOnInit(): void {
    this.load();
  }

  private load(): void {
    this.cardService.list().subscribe({
      next: data => { this.cards.set(data); this.loading.set(false); },
      error: () => this.loading.set(false),
    });
  }

  delete(card: CreditCard): void {
    if (!confirm(`Deseja excluir o cartão "${card.name}"?`)) return;
    this.deletingId.set(card.id);
    this.cardService.delete(card.id).subscribe({
      next: () => {
        this.cards.update(list => list.filter(c => c.id !== card.id));
        this.deletingId.set(null);
      },
      error: () => this.deletingId.set(null),
    });
  }
}
