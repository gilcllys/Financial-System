import * as d3 from 'd3';
import { Component, OnInit, inject, signal, computed, ElementRef, ViewChild, effect } from '@angular/core';
import { SlicePipe } from '@angular/common';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { forkJoin } from 'rxjs';
import { ReactiveFormsModule, FormsModule, FormBuilder, Validators } from '@angular/forms';
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
  PaginatedResponse,
} from '../../../core/services/shared-debt.service';


interface DraftSharedEntry {
  localId: number;
  description: string;
  amount: number;
  date: string;
  paid_by: number;
  paid_by_name: string;
  participant_ids: number[];
  payment_method: 'dinheiro' | 'cartao';
  category_id: number | null;
  category_name: string | null;
}

@Component({
  selector: 'app-shared-debt-detail',
  standalone: true,
  imports: [RouterLink, ReactiveFormsModule, FormsModule, SlicePipe],
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

  // ── Filtros e paginação ─────────────────────────────────────────────────
  readonly PAGE_SIZE = 20;
  filterMonth = signal<number | null>(null);
  filterCategory = signal<number | null>(null);
  currentPage = signal(1);
  totalCount = signal(0);
  private openedEntryFromQuery = false;
  totalPages = computed(() => Math.max(1, Math.ceil(this.totalCount() / this.PAGE_SIZE)));
  pageNumbers = computed(() => Array.from({ length: this.totalPages() }, (_, i) => i + 1));
  cards = signal<CreditCard[]>([]);
  loading = signal(true);

  readonly pieColors = ['#3b82f6','#f59e0b','#10b981','#ef4444','#8b5cf6','#06b6d4','#f97316','#84cc16','#ec4899'];
  @ViewChild('pieChartEl') pieChartEl?: ElementRef<HTMLDivElement>;
  pieTooltip = signal<{cx:number; cy:number; name:string; total:number; pct:number}|null>(null);


  categoryBreakdown = computed(() => {
    const map = new Map<string, number>();
    for (const e of this.entries()) {
      const key = e.category_name ?? 'Sem categoria';
      map.set(key, (map.get(key) ?? 0) + Number(e.amount));
    }
    return Array.from(map.entries())
      .map(([name, total]) => ({ name, total }))
      .sort((a, b) => b.total - a.total);
  });

  formatCurrencyPie(value: number): string {
    return new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(value);
  }

  renderPieChart(): void {
    const data = this.categoryBreakdown();
    const el = this.pieChartEl?.nativeElement;
    if (!el || data.length === 0) return;
    el.innerHTML = '';

    const W = 200, H = 200, R = 80, r = 32;
    const total = data.reduce((s, d) => s + d.total, 0);
    const svg = d3.select(el).append('svg')
      .attr('viewBox', `0 0 ${W} ${H}`)
      .style('width','160px').style('height','160px').style('flex-shrink','0');

    const g = svg.append('g').attr('transform',`translate(${W/2},${H/2})`);

    const pie = d3.pie<{name:string;total:number}>().value(d => d.total).sort(null);
    const arc = d3.arc<d3.PieArcDatum<{name:string;total:number}>>().innerRadius(r).outerRadius(R);
    const arcHover = d3.arc<d3.PieArcDatum<{name:string;total:number}>>().innerRadius(r).outerRadius(R+6);

    const arcs = pie(data);
    const tooltip = this.pieTooltip;

    g.selectAll('path')
      .data(arcs)
      .enter().append('path')
      .attr('d', arc as any)
      .attr('fill', (_, i) => this.pieColors[i % this.pieColors.length])
      .attr('stroke', '#fff')
      .attr('stroke-width', 2)
      .style('cursor','pointer')
      .on('mousemove', (event: MouseEvent, d: any) => {
        tooltip.set({ cx: event.clientX+14, cy: event.clientY-100, name: d.data.name, total: d.data.total, pct: Math.round(d.data.total/total*100) });
      })
      .on('mouseleave', () => tooltip.set(null));

    // Center label
    g.append('text').attr('text-anchor','middle').attr('dy','0.35em')
      .attr('font-size','10').attr('fill','#6b7280').attr('font-family','inherit')
      .text(`${data.length} cat.`);
  }
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

  // ── Batch de gastos compartilhados ───────────────────────────────────────
  showBatchSection = signal(false);
  batchDrafts = signal<DraftSharedEntry[]>([]);
  savingBatch = signal(false);
  batchError = signal('');
  batchSaveProgress = signal(0);
  private batchNextId = 1;

  batchForm = this.fb.group({
    description: ['', [Validators.required, Validators.minLength(2)]],
    amount: [null as number | null, [Validators.required, Validators.min(0.01)]],
    date: [new Date().toISOString().split('T')[0], Validators.required],
    paid_by: [null as number | null, Validators.required],
    category_id: [null as number | null],
    payment_method: ['dinheiro' as 'dinheiro' | 'cartao'],
  });
  batchParticipantIds = signal<Set<number>>(new Set());
  get batchTotal(): number { return this.batchDrafts().reduce((s, d) => s + d.amount, 0); }
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
    total_installments_input: [1 as number, [Validators.min(1), Validators.max(120)]],
  });

  isParcelado = signal(false);

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

  /** True when tenantId belongs to the authenticated user. */
  isMe(tenantId: string | null): boolean {
    return !!tenantId && tenantId === this.myTenantId;
  }

  constructor() {
    effect(() => {
      const data = this.categoryBreakdown();
      if (data.length > 0) {
        Promise.resolve().then(() => this.renderPieChart());
      }
    });
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
        this.batchParticipantIds.set(new Set(m.map(x => x.id)));
        this.openEntryFromQuery();
        this.loading.set(false);
      },
      error: () => this.loading.set(false),
    });
    this.refreshEntriesAndBalances();
    this.loadMonthlyHistory();
    this.loadRecurringTemplates();
  }

  private refreshEntriesAndBalances(resetPage = false): void {
    if (resetPage) this.currentPage.set(1);
    this.svc.listEntries({
      shared_debt: this.groupId,
      month: this.filterMonth() ?? undefined,
      category: this.filterCategory() ?? undefined,
      page: this.currentPage(),
    }).subscribe({
      next: (res: PaginatedResponse<SharedDebtEntry>) => {
        this.entries.set(res.results);
        this.totalCount.set(res.count);
        this.openEntryFromQuery();
      }
    });
    this.svc.balances(this.groupId).subscribe({ next: b => this.balances.set(b) });
  }

  private openEntryFromQuery(): void {
    if (this.openedEntryFromQuery || this.members().length === 0) return;
    const rawEntryId = this.route.snapshot.queryParamMap.get('edit_entry');
    if (!rawEntryId) return;
    const entryId = Number(rawEntryId);
    if (!Number.isFinite(entryId)) return;

    const entry = this.entries().find(e => e.id === entryId);
    if (!entry) return;

    this.openedEntryFromQuery = true;
    this.activeTab.set('entries');
    this.editEntry(entry);
  }

  applyFilter(): void { this.refreshEntriesAndBalances(true); }

  clearFilters(): void {
    this.filterMonth.set(null);
    this.filterCategory.set(null);
    this.refreshEntriesAndBalances(true);
  }

  goToPage(page: number): void {
    if (page < 1 || page > this.totalPages()) return;
    this.currentPage.set(page);
    this.refreshEntriesAndBalances();
  }

  readonly MONTHS = [
    { value: 1, label: 'Janeiro' }, { value: 2, label: 'Fevereiro' },
    { value: 3, label: 'Março' },   { value: 4, label: 'Abril' },
    { value: 5, label: 'Maio' },    { value: 6, label: 'Junho' },
    { value: 7, label: 'Julho' },   { value: 8, label: 'Agosto' },
    { value: 9, label: 'Setembro' },{ value: 10, label: 'Outubro' },
    { value: 11, label: 'Novembro' },{ value: 12, label: 'Dezembro' },
  ];

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
      total_installments_input: this.isParcelado() ? (v.total_installments_input ?? 2) : 1,
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
        total_installments_input: 1,
      });
      this.isParcelado.set(false);
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

  togglePaid(entry: SharedDebtEntry): void {
    const nextPaid = !entry.paid;
    this.svc.updateEntry(entry.id, { paid: nextPaid }).subscribe({
      next: () => this.refreshEntriesAndBalances(),
      error: () => alert('Erro ao atualizar status de pagamento.'),
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


  // ── Batch methods ─────────────────────────────────────────────────────────
  toggleBatchSection(): void { this.showBatchSection.set(!this.showBatchSection()); }

  isBatchParticipant(id: number): boolean { return this.batchParticipantIds().has(id); }

  toggleBatchParticipant(id: number): void {
    this.batchParticipantIds.update(s => {
      const n = new Set(s);
      n.has(id) ? n.delete(id) : n.add(id);
      return n;
    });
  }

  addToBatch(): void {
    if (this.batchForm.invalid) { this.batchForm.markAllAsTouched(); return; }
    const parts = [...this.batchParticipantIds()];
    if (parts.length === 0) { this.batchError.set('Selecione ao menos um participante.'); return; }
    const v = this.batchForm.getRawValue();
    const paidByMember = this.members().find(m => m.id === v.paid_by);
    const cat = this.categories().find(c => c.id === v.category_id);
    this.batchDrafts.update(list => [...list, {
      localId: this.batchNextId++,
      description: v.description!,
      amount: Math.abs(v.amount!),
      date: v.date!,
      paid_by: v.paid_by!,
      paid_by_name: paidByMember?.display_name ?? '',
      participant_ids: parts,
      payment_method: v.payment_method as 'dinheiro' | 'cartao',
      category_id: v.category_id,
      category_name: cat?.name ?? null,
    }]);
    this.batchError.set('');
    this.batchForm.reset({
      description: '', amount: null, date: v.date!, paid_by: v.paid_by,
      category_id: null, payment_method: 'dinheiro',
    });
    this.batchParticipantIds.set(new Set(this.members().map(m => m.id)));
  }

  removeBatchDraft(localId: number): void {
    this.batchDrafts.update(list => list.filter(d => d.localId !== localId));
  }

  saveAllBatch(): void {
    if (this.batchDrafts().length === 0 || this.savingBatch()) return;
    this.savingBatch.set(true);
    this.batchSaveProgress.set(0);
    this.batchError.set('');

    const drafts = this.batchDrafts();
    let completed = 0;

    const requests = drafts.map(d =>
      this.svc.createEntry({
        shared_debt: this.groupId,
        description: d.description,
        amount: d.amount,
        date: d.date,
        paid_by: d.paid_by,
        participant_ids: d.participant_ids.length === this.members().length ? undefined : d.participant_ids,
        payment_method: d.payment_method,
        category_id: d.category_id,
      })
    );

    forkJoin(requests).subscribe({
      next: () => {
        this.savingBatch.set(false);
        this.batchDrafts.set([]);
        this.showBatchSection.set(false);
        this.refreshEntriesAndBalances();
        this.loadMonthlyHistory();
      },
      error: err => {
        this.savingBatch.set(false);
        this.batchError.set(err?.error?.detail ?? 'Erro ao salvar alguns gastos.');
      },
    });
  }
  // ── Tab & Installment view ──────────────────────────────────────────────
  activeTab = signal<'entries' | 'installments' | 'byPerson'>('entries');

  installmentGroups = computed(() => {
    const all = this.entries();
    const myId = this.myTenantId;
    // Group by installment_group_id (non-null) or by description for same total_installments
    const map = new Map<string, SharedDebtEntry[]>();
    for (const e of all) {
      if (e.total_installments <= 1) continue;
      const key = e.installment_group_id ?? `${e.description}__${e.total_installments}`;
      if (!map.has(key)) map.set(key, []);
      map.get(key)!.push(e);
    }

    const MONTH_NAMES = ['Jan','Fev','Mar','Abr','Mai','Jun','Jul','Ago','Set','Out','Nov','Dez'];
    const now = new Date();

    return [...map.entries()].map(([groupId, entries]) => {
      entries.sort((a, b) => a.installment_number - b.installment_number);
      const first = entries[0];
      const last = entries[entries.length - 1];
      const total = first.total_installments;
      const paid = entries.filter(e => new Date(e.date) <= now).length;
      const progressPct = Math.round((paid / total) * 100);
      const paidBy = first.paid_by_name;
      const participantCount = first.participant_count;
      const installmentAmount = first.amount;
      const myPortionPerInstallment = installmentAmount / (participantCount || 1);
      const totalAmount = installmentAmount * total;
      const myTotalPortion = myPortionPerInstallment * total;
      const myPaidPortion = myPortionPerInstallment * paid;
      const remaining = myTotalPortion - myPaidPortion;

      // Status
      const lastEntry = entries[entries.length - 1];
      const lastDate = new Date(lastEntry.date);
      let status = 'Em andamento';
      if (paid >= total) status = 'Concluído';
      else if (lastDate < now && paid < total) status = 'Atrasada';

      const startD = new Date(first.date);
      const endD = new Date(last.date);
      const startMonth = `${MONTH_NAMES[startD.getMonth()]}/${startD.getFullYear()}`;
      const endMonth = `${MONTH_NAMES[endD.getMonth()]}/${endD.getFullYear()}`;

      return {
        groupId,
        description: first.description,
        total,
        paid,
        progressPct,
        status,
        paidByName: paidBy,
        participantCount,
        installmentAmount,
        myPortionPerInstallment,
        totalAmount,
        myTotalPortion,
        remaining,
        startMonth,
        endMonth,
        entries,
        expanded: false,
      };
    });
  });

  myPortion(e: SharedDebtEntry): number {
    return e.amount / (e.participant_count || 1);
  }

  isPaid(e: SharedDebtEntry): boolean {
    return new Date(e.date) <= new Date();
  }

  formatMonthYear(d: string): string {
    if (!d) return '';
    const MONTH_NAMES = ['Jan','Fev','Mar','Abr','Mai','Jun','Jul','Ago','Set','Out','Nov','Dez'];
    const dt = new Date(d + 'T00:00:00');
    return `${MONTH_NAMES[dt.getMonth()]}/${dt.getFullYear()}`;
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

  // ── Per-person view ─────────────────────────────────────────────────────
  perPerson = computed(() => {
    const members = this.members();
    const allEntries = this.entries();
    const catColors = ['#0052ff','#05b169','#cf202f','#f4b000','#7c828a','#30b0c7','#ff6b35'];

    return members.map(member => {
      const paidEntries = allEntries.filter(e => e.paid_by === member.id);
      const totalSpent = paidEntries.reduce((s, e) => s + e.amount, 0);

      let catIdx = 0;
      const catMap = new Map<string, { name: string; total: number; color: string }>();
      for (const e of paidEntries) {
        const key = e.category_name ?? 'Sem categoria';
        if (!catMap.has(key)) catMap.set(key, { name: key, total: 0, color: catColors[catIdx++ % catColors.length] });
        catMap.get(key)!.total += e.amount / (e.participant_count || 1);
      }

      const myPortion = paidEntries.reduce((s, e) => s + (e.amount / (e.participant_count || 1)), 0);
      const bal = this.balances();
      const settlement = bal?.settlement.find(s => s.from_member_id === member.id);
      const owes = settlement?.amount ?? 0;

      return {
        member,
        isMe: member.tenant_id === this.myTenantId,
        totalSpent,
        myPortion,
        owes,
        entries: paidEntries,
        categorySummary: Array.from(catMap.values()),
      };
    });
  });

  initials(name: string): string {
    return (name ?? '?').split(' ').slice(0, 2).map((w: string) => w[0]).join('').toUpperCase();
  }

  catColors = ['#0052ff','#05b169','#cf202f','#f4b000','#7c828a','#30b0c7','#ff6b35'];
  catColor(i: number): string { return this.catColors[i % this.catColors.length]; }
}
