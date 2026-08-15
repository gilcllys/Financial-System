import { Component, OnInit, inject, signal, computed } from '@angular/core';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { ReactiveFormsModule, FormBuilder, Validators } from '@angular/forms';
import { AuthService } from '../../../core/auth/auth.service';
import { CardService } from '../../../core/services/card.service';
import { CategoryService } from '../../../core/services/category.service';
import { ExpenseCategory } from '../../../core/models';
import { CreditCard } from '../../../core/models';
import {
  SharedDebtService,
  SharedDebtGroup,
  SharedDebtMember,
  SharedDebtEntry,
  BalancesResponse,
  MonthlyHistoryEntry,
  RecurringTemplate,
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
  private router = inject(Router);
  private svc = inject(SharedDebtService);
  private auth = inject(AuthService);
  private cardSvc = inject(CardService);
  private categorySvc = inject(CategoryService);
  private fb = inject(FormBuilder);

  private myTenantId = this.auth.userProfile.sub ?? null;

  groupId = 0;
  group = signal<SharedDebtGroup | null>(null);
  members = signal<SharedDebtMember[]>([]);
  entries = signal<SharedDebtEntry[]>([]);
  balances = signal<BalancesResponse | null>(null);
  cards = signal<CreditCard[]>([]);
  loading = signal(true);
  categories = signal<ExpenseCategory[]>([]);

  inviteUrl = signal<string | null>(null);
  inviting = signal(false);
  copied = signal(false);

  showEntryForm = signal(false);
  savingEntry = signal(false);
  entryError = signal('');
  editingEntryId = signal<number | null>(null);

  deletingGroup = signal(false);
  monthlyHistory = signal<MonthlyHistoryEntry[]>([]);
  recurringTemplates = signal<RecurringTemplate[]>([]);
  showRecurringForm = signal(false);
  savingRecurring = signal(false);
  recurringError = signal('');
  generatingMonth = signal(false);
  generateResult = signal<{ created: string[]; skipped: string[] } | null>(null);

  recurringForm = this.fb.group({
    description: ['', [Validators.required, Validators.minLength(2)]],
    amount: [null as number | null, [Validators.required, Validators.min(0.01)]],
    paid_by: [null as number | null, Validators.required],
    day_of_month: [1, [Validators.required, Validators.min(1), Validators.max(28)]],
    payment_method: ['dinheiro' as 'dinheiro' | 'cartao'],
    category_id: [null as number | null],
  });

  // participants: track selected member ids (default = all)
  participantIds = signal<Set<number>>(new Set());

  form = this.fb.group({
    description: ['', [Validators.required, Validators.minLength(2)]],
    amount: [null as number | null, [Validators.required, Validators.min(0.01)]],
    date: [new Date().toISOString().split('T')[0], Validators.required],
    paid_by: [null as number | null, Validators.required],
    payment_method: ['dinheiro' as 'dinheiro' | 'cartao', Validators.required],
    credit_card_id: [null as number | null],
    category_id: [null as number | null],
  });

  get isCartao(): boolean { return this.form.value.payment_method === 'cartao'; }

  /** True when the authenticated user is the group owner. */
  get isOwner(): boolean {
    return !!this.group() && this.group()!.owner_tenant_id === this.myTenantId;
  }

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
    this.categorySvc.list().subscribe({ next: cats => this.categories.set(cats) });
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
    this.loadMonthlyHistory();
    this.loadRecurringTemplates();
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
    this.editingEntryId.set(null);
    this.entryError.set('');
  }

  /** Open the form pre-filled for editing an existing entry.
   *  NOTE: The list endpoint does not return participant_ids, so we default
   *  to ALL members when editing. The user can uncheck before saving. */
  editEntry(entry: SharedDebtEntry): void {
    this.editingEntryId.set(entry.id);
    this.entryError.set('');
    this.form.reset({
      description: entry.description,
      amount: Math.abs(entry.amount),
      date: entry.date,
      paid_by: entry.paid_by,
      payment_method: entry.payment_method,
      credit_card_id: entry.credit_card ?? null,
      category_id: entry.category ?? null,
    });
    // Default all members as participants — editing re-sends all unless user unchecks.
    this.participantIds.set(new Set(this.members().map(m => m.id)));
    this.showEntryForm.set(true);
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
    const payload = {
      shared_debt: this.groupId,
      description: v.description!,
      amount: Math.abs(v.amount!),
      date: v.date!,
      paid_by: v.paid_by!,
      participant_ids: allSelected ? undefined : participants,
      payment_method: v.payment_method!,
      credit_card_id: v.payment_method === 'cartao' && this.payerIsMe ? v.credit_card_id : null,
      category_id: v.category_id ?? null,
    };

    const editId = this.editingEntryId();
    const request$ = editId != null
      ? this.svc.updateEntry(editId, payload)
      : this.svc.createEntry(payload);

    const resetForm = () => {
      this.savingEntry.set(false);
      this.editingEntryId.set(null);
      this.showEntryForm.set(false);
      this.form.reset({
        description: '',
        amount: null,
        date: new Date().toISOString().split('T')[0],
        paid_by: null,
        payment_method: 'dinheiro',
        credit_card_id: null,
        category_id: null,
      });
      this.participantIds.set(new Set(this.members().map(m => m.id)));
      this.refreshEntriesAndBalances();
    this.loadMonthlyHistory();
    this.loadRecurringTemplates();
    };

    request$.subscribe({
      next: () => resetForm(),
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

  // ── Group deletion (owner only) ─────────────────────────────────────────
  deleteGroup(): void {
    const name = this.group()?.name ?? 'este grupo';
    if (!confirm(`Excluir o grupo "${name}" e todas as despesas? Esta ação não pode ser desfeita.`)) return;
    this.deletingGroup.set(true);
    this.svc.deleteGroup(this.groupId).subscribe({
      next: () => this.router.navigate(['/shared-debts']),
      error: () => {
        this.deletingGroup.set(false);
        alert('Erro ao excluir grupo. Apenas o dono pode excluir.');
      },
    });
  }


  private loadMonthlyHistory(): void {
    this.svc.monthlyHistory(this.groupId).subscribe({
      next: h => this.monthlyHistory.set(h),
      error: () => {},
    });
  }

  private loadRecurringTemplates(): void {
    this.svc.listRecurringTemplates(this.groupId).subscribe({
      next: t => this.recurringTemplates.set(t),
      error: () => {},
    });
  }

  toggleRecurringForm(): void {
    this.showRecurringForm.set(!this.showRecurringForm());
    this.recurringError.set('');
  }

  saveRecurring(): void {
    if (this.recurringForm.invalid) { this.recurringForm.markAllAsTouched(); return; }
    this.savingRecurring.set(true);
    this.recurringError.set('');
    const v = this.recurringForm.getRawValue();
    const allMembers = this.members().map(m => m.id);
    this.svc.createRecurringTemplate(this.groupId, {
      description: v.description!,
      amount: v.amount!,
      paid_by: v.paid_by!,
      day_of_month: v.day_of_month ?? 1,
      payment_method: v.payment_method as 'dinheiro' | 'cartao',
      category_id: v.category_id,
      participant_ids: allMembers,
    }).subscribe({
      next: () => {
        this.savingRecurring.set(false);
        this.showRecurringForm.set(false);
        this.recurringForm.reset({ description: '', amount: null, paid_by: null, day_of_month: 1, payment_method: 'dinheiro', category_id: null });
        this.loadRecurringTemplates();
      },
      error: err => {
        this.savingRecurring.set(false);
        this.recurringError.set(err?.error?.detail ?? 'Erro ao salvar.');
      },
    });
  }

  deleteRecurring(tplId: number): void {
    if (!confirm('Excluir este gasto recorrente?')) return;
    this.svc.deleteRecurringTemplate(this.groupId, tplId).subscribe({
      next: () => this.loadRecurringTemplates(),
    });
  }

  toggleRecurring(tplId: number): void {
    this.svc.toggleRecurringTemplate(this.groupId, tplId).subscribe({
      next: () => this.loadRecurringTemplates(),
    });
  }

  generateMonth(): void {
    const now = new Date();
    this.generatingMonth.set(true);
    this.generateResult.set(null);
    this.svc.generateMonth(this.groupId, now.getMonth() + 1, now.getFullYear()).subscribe({
      next: r => { this.generatingMonth.set(false); this.generateResult.set(r); this.refreshEntriesAndBalances(); this.loadMonthlyHistory(); },
      error: () => { this.generatingMonth.set(false); },
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
