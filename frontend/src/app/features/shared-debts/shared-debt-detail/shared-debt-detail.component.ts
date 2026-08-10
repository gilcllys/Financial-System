import { Component, OnInit, inject, signal, computed } from '@angular/core';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { ReactiveFormsModule, FormBuilder, Validators } from '@angular/forms';
import { AuthService } from '../../../core/auth/auth.service';
import { CardService } from '../../../core/services/card.service';
import { CreditCard } from '../../../core/models';
import {
  SharedDebtService,
  SharedDebtGroup,
  SharedDebtMember,
  SharedDebtEntry,
  BalancesResponse,
} from '../../../core/services/shared-debt.service';

@Component({
  selector: 'app-shared-debt-detail',
  standalone: true,
  imports: [RouterLink, ReactiveFormsModule],
  templateUrl: './shared-debt-detail.component.html',
  styleUrls: ['./shared-debt-detail.component.scss'],
})
export class SharedDebtDetailComponent implements OnInit {
  private route = inject(ActivatedRoute);
  private svc = inject(SharedDebtService);
  private auth = inject(AuthService);
  private cardSvc = inject(CardService);
  private fb = inject(FormBuilder);

  private myTenantId = this.auth.userProfile.sub ?? null;

  groupId = 0;
  group = signal<SharedDebtGroup | null>(null);
  members = signal<SharedDebtMember[]>([]);
  entries = signal<SharedDebtEntry[]>([]);
  balances = signal<BalancesResponse | null>(null);
  cards = signal<CreditCard[]>([]);
  loading = signal(true);

  inviteUrl = signal<string | null>(null);
  inviting = signal(false);
  copied = signal(false);

  showEntryForm = signal(false);
  savingEntry = signal(false);
  entryError = signal('');

  // participants: track selected member ids (default = all)
  participantIds = signal<Set<number>>(new Set());

  form = this.fb.group({
    description: ['', [Validators.required, Validators.minLength(2)]],
    amount: [null as number | null, [Validators.required, Validators.min(0.01)]],
    date: [new Date().toISOString().split('T')[0], Validators.required],
    paid_by: [null as number | null, Validators.required],
    payment_method: ['dinheiro' as 'dinheiro' | 'cartao', Validators.required],
    credit_card_id: [null as number | null],
  });

  get isCartao(): boolean { return this.form.value.payment_method === 'cartao'; }

  /** True when the selected payer is me (only then show my credit cards). */
  get payerIsMe(): boolean {
    const paidBy = this.form.value.paid_by;
    if (paidBy == null) return false;
    const member = this.members().find(m => m.id === paidBy);
    return !!member && !!member.tenant_id && member.tenant_id === this.myTenantId;
  }

  ngOnInit(): void {
    this.groupId = +this.route.snapshot.paramMap.get('id')!;
    this.loadAll();
    this.cardSvc.list().subscribe({ next: c => this.cards.set(c) });
  }

  private loadAll(): void {
    this.loading.set(true);
    this.svc.getGroup(this.groupId).subscribe({ next: g => this.group.set(g) });
    this.svc.members(this.groupId).subscribe({
      next: m => {
        this.members.set(m);
        this.participantIds.set(new Set(m.map(x => x.id)));
        this.loading.set(false);
      },
      error: () => this.loading.set(false),
    });
    this.refreshEntriesAndBalances();
  }

  private refreshEntriesAndBalances(): void {
    this.svc.listEntries({ shared_debt: this.groupId }).subscribe({ next: e => this.entries.set(e) });
    this.svc.balances(this.groupId).subscribe({ next: b => this.balances.set(b) });
  }

  // ── Invite ──────────────────────────────────────────────────────────────
  invite(): void {
    this.inviting.set(true);
    this.copied.set(false);
    this.svc.createInvite(this.groupId).subscribe({
      next: res => {
        this.inviteUrl.set(window.location.origin + res.join_path);
        this.inviting.set(false);
      },
      error: () => this.inviting.set(false),
    });
  }

  copyInvite(): void {
    const url = this.inviteUrl();
    if (!url) return;
    navigator.clipboard?.writeText(url).then(() => {
      this.copied.set(true);
      setTimeout(() => this.copied.set(false), 2000);
    });
  }

  // ── Entry form ──────────────────────────────────────────────────────────
  toggleEntryForm(): void {
    this.showEntryForm.set(!this.showEntryForm());
    this.entryError.set('');
  }

  isParticipant(memberId: number): boolean {
    return this.participantIds().has(memberId);
  }

  toggleParticipant(memberId: number): void {
    this.participantIds.update(set => {
      const next = new Set(set);
      if (next.has(memberId)) next.delete(memberId); else next.add(memberId);
      return next;
    });
  }

  saveEntry(): void {
    if (this.form.invalid) { this.form.markAllAsTouched(); return; }
    const participants = [...this.participantIds()];
    if (participants.length === 0) {
      this.entryError.set('Selecione ao menos um participante.');
      return;
    }
    this.savingEntry.set(true);
    this.entryError.set('');
    const v = this.form.getRawValue();
    const allSelected = participants.length === this.members().length;
    this.svc.createEntry({
      shared_debt: this.groupId,
      description: v.description!,
      amount: Math.abs(v.amount!),
      date: v.date!,
      paid_by: v.paid_by!,
      participant_ids: allSelected ? undefined : participants,
      payment_method: v.payment_method!,
      credit_card_id: v.payment_method === 'cartao' && this.payerIsMe ? v.credit_card_id : null,
    }).subscribe({
      next: () => {
        this.savingEntry.set(false);
        this.showEntryForm.set(false);
        this.form.reset({
          description: '',
          amount: null,
          date: new Date().toISOString().split('T')[0],
          paid_by: null,
          payment_method: 'dinheiro',
          credit_card_id: null,
        });
        this.participantIds.set(new Set(this.members().map(m => m.id)));
        this.refreshEntriesAndBalances();
      },
      error: err => {
        this.savingEntry.set(false);
        this.entryError.set(err?.error?.detail ?? 'Erro ao salvar despesa. Tente novamente.');
      },
    });
  }

  deleteEntry(entry: SharedDebtEntry): void {
    if (!confirm(`Excluir "${entry.description}"?`)) return;
    this.svc.deleteEntry(entry.id).subscribe({
      next: () => this.refreshEntriesAndBalances(),
      error: () => alert('Erro ao excluir despesa.'),
    });
  }

  // ── Formatters ──────────────────────────────────────────────────────────
  formatCurrency(v: number): string {
    return new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(Math.abs(v));
  }

  formatDate(d: string): string {
    return d ? `${d.slice(8, 10)}/${d.slice(5, 7)}/${d.slice(0, 4)}` : '';
  }

  hasError(field: string): boolean {
    const c = this.form.get(field);
    return !!(c?.invalid && c?.touched);
  }
}
