import { Component, OnInit, inject, signal, computed } from '@angular/core';
import { ConfirmDialogService } from '../../core/services/confirm-dialog.service';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { ReactiveFormsModule, FormBuilder, Validators } from '@angular/forms';
import { forkJoin } from 'rxjs';
import { map } from 'rxjs/operators';

import { ExpenseService, RecurringExpenseTemplate, GenerateMonthResult } from '../../core/services/expense.service';
import { CardService } from '../../core/services/card.service';
import { CategoryService } from '../../core/services/category.service';
import { CreditCard, ExpenseCategory } from '../../core/models';
import { AuthService } from '../../core/auth/auth.service';
import { SharedDebtService, SharedDebtGroup, SharedDebtMember, RecurringTemplate } from '../../core/services/shared-debt.service';

const MONTH_NAMES = [
  '', 'Janeiro', 'Fevereiro', 'Mar\u00e7o', 'Abril', 'Maio', 'Junho',
  'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro',
];

type SharedRecurringTemplate = RecurringTemplate & { shared_debt_name: string };

@Component({
  selector: 'app-recurring-expenses',
  standalone: true,
  imports: [ReactiveFormsModule, RouterLink],
  templateUrl: './recurring-expenses.component.html',
  styleUrl: './recurring-expenses.component.scss',
})
export class RecurringExpensesComponent implements OnInit {
  private confirmDialog = inject(ConfirmDialogService);
  private expenseService = inject(ExpenseService);
  private sharedDebtService = inject(SharedDebtService);
  private cardService = inject(CardService);
  private categoryService = inject(CategoryService);
  private auth = inject(AuthService);
  private route = inject(ActivatedRoute);
  private fb = inject(FormBuilder);
  readonly currentTenantId = this.auth.userProfile.sub;

  templates = signal<RecurringExpenseTemplate[]>([]);
  sharedGroups = signal<SharedDebtGroup[]>([]);
  sharedTemplates = signal<SharedRecurringTemplate[]>([]);
  sharedMembersByGroup = signal<Map<number, SharedDebtMember[]>>(new Map());
  sharedMembers = signal<SharedDebtMember[]>([]);
  sharedParticipantIds = signal<Set<number>>(new Set());
  creditCards = signal<CreditCard[]>([]);
  categories = signal<ExpenseCategory[]>([]);

  loading = signal(false);
  loadingShared = signal(false);
  sharedLoadError = signal('');
  saving = signal(false);
  savingShared = signal(false);
  generating = signal(false);
  error = signal('');
  showForm = signal(false);
  editingId = signal<number | null>(null);
  expenseType = signal<'individual' | 'shared'>('individual');
  selectedSharedGroupId = signal<number | null>(null);
  generateResult = signal<GenerateMonthResult | null>(null);

  private now = new Date();
  targetMonth = signal(this.now.getMonth() + 1);
  targetYear = signal(this.now.getFullYear());

  form = this.fb.group({
    description: ['', Validators.required],
    amount: [null as number | null, [Validators.required, Validators.min(0.01)]],
    day_of_month: [1, [Validators.required, Validators.min(1), Validators.max(28)]],
    payment_method: ['dinheiro' as 'dinheiro' | 'cartao', Validators.required],
    credit_card_id: [null as number | null],
    category_id: [null as number | null],
  });

  sharedForm = this.fb.group({
    shared_debt: [null as number | null, Validators.required],
    description: ['', [Validators.required, Validators.minLength(2)]],
    amount: [null as number | null, [Validators.required, Validators.min(0.01)]],
    day_of_month: [1, [Validators.required, Validators.min(1), Validators.max(28)]],
    payment_method: ['dinheiro' as 'dinheiro' | 'cartao', Validators.required],
    credit_card_id: [null as number | null],
    category_id: [null as number | null],
    paid_by: [null as number | null, Validators.required],
  });

  /** cartao => credit_card_id obrigatorio, espelhando a regra do backend. */
  get isCartao(): boolean {
    return this.form.value.payment_method === 'cartao';
  }

  get sharedIsCartao(): boolean { return this.sharedForm.value.payment_method === 'cartao'; }

  get sharedPayerIsMe(): boolean {
    const payerId = this.sharedForm.value.paid_by;
    const member = this.sharedMembers().find(item => item.id === payerId);
    return !!member?.tenant_id && member.tenant_id === this.auth.userProfile.sub;
  }

  activeTemplates = computed(() => this.templates().filter(t => t.is_active));
  activeSharedTemplates = computed(() => this.sharedTemplates().filter(t => t.is_active));

  /** Custo fixo mensal: so os ativos entram, pausados nao geram lancamento. */
  monthlyTotal = computed(() =>
    this.activeTemplates().reduce((sum, t) => sum + Math.abs(Number(t.amount)), 0)
  );

  cardTotal = computed(() =>
    this.activeTemplates()
      .filter(t => t.payment_method === 'cartao')
      .reduce((sum, t) => sum + Math.abs(Number(t.amount)), 0)
  );

  cashTotal = computed(() =>
    this.activeTemplates()
      .filter(t => t.payment_method === 'dinheiro')
      .reduce((sum, t) => sum + Math.abs(Number(t.amount)), 0)
  );

  sharedMyMonthlyTotal = computed(() => this.activeSharedTemplates().reduce((sum, template) => {
    const myMember = this.sharedMembersByGroup().get(template.shared_debt)
      ?.find(member => member.tenant_id === this.auth.userProfile.sub);
    if (!myMember || !template.participant_ids.includes(myMember.id)) return sum;
    return sum + Math.abs(Number(template.amount)) / Math.max(template.participant_ids.length, 1);
  }, 0));

  /** Templates que o backend vai recusar: cartao sem cartao atribuido. */
  invalidTemplates = computed(() =>
    this.templates().filter(t => t.payment_method === 'cartao' && t.credit_card === null)
  );

  targetLabel = computed(() => `${MONTH_NAMES[this.targetMonth()]} ${this.targetYear()}`);

  /**
   * O app nao registra locale data, entao CurrencyPipe com 'pt-BR' quebra em runtime.
   * toLocaleString usa Intl do proprio browser. Mesma convencao do home.
   */
  fmtCur(v: number | string | null | undefined): string {
    const n = Number(v);
    if (isNaN(n)) return '\u2014';
    return n.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL', minimumFractionDigits: 2 });
  }

  absAmount(t: RecurringExpenseTemplate): number {
    return Math.abs(Number(t.amount));
  }

  ngOnInit(): void {
    this.load();
    this.loadShared();
    this.cardService.list().subscribe({ next: cards => this.creditCards.set(cards) });
    this.categoryService.list().subscribe({ next: cats => this.categories.set(cats) });

    const initialType = this.route.snapshot.queryParamMap.get('type');
    const groupId = Number(this.route.snapshot.queryParamMap.get('group')) || null;
    if (initialType === 'shared') this.openCreate('shared', groupId);
  }

  load(): void {
    this.loading.set(true);
    this.expenseService.listRecurringTemplates().subscribe({
      next: tpls => { this.templates.set(tpls); this.loading.set(false); },
      error: () => { this.error.set('Nao foi possivel carregar os gastos fixos.'); this.loading.set(false); },
    });
  }

  loadShared(): void {
    this.loadingShared.set(true);
    this.sharedLoadError.set('');
    this.sharedDebtService.listGroups().subscribe({
      next: groups => {
        this.sharedGroups.set(groups);
        if (groups.length === 0) {
          this.sharedTemplates.set([]);
          this.sharedMembersByGroup.set(new Map());
          this.loadingShared.set(false);
          return;
        }
        forkJoin(groups.map(group => forkJoin({
          templates: this.sharedDebtService.listRecurringTemplates(group.id),
          members: this.sharedDebtService.members(group.id),
        }).pipe(map(data => ({ group, ...data }))))).subscribe({
          next: results => {
            const membersByGroup = new Map<number, SharedDebtMember[]>();
            const templates = results.flatMap(({ group, members, templates }) => {
              membersByGroup.set(group.id, members);
              return templates.map(template => ({ ...template, shared_debt_name: group.name }));
            });
            this.sharedMembersByGroup.set(membersByGroup);
            this.sharedTemplates.set(templates);
            this.loadingShared.set(false);
          },
          error: () => {
            this.sharedLoadError.set('Não foi possível carregar os gastos fixos compartilhados. Tente novamente.');
            this.loadingShared.set(false);
          },
        });
      },
      error: () => {
        this.sharedLoadError.set('Não foi possível carregar seus grupos compartilhados. Tente novamente.');
        this.loadingShared.set(false);
      },
    });
  }

  openCreate(type: 'individual' | 'shared' = 'individual', groupId: number | null = null): void {
    this.expenseType.set(type);
    this.editingId.set(null);
    this.error.set('');
    this.form.reset({
      description: '', amount: null, day_of_month: 1,
      payment_method: 'dinheiro', credit_card_id: null, category_id: null,
    });
    const selectedGroup = groupId ?? (this.sharedGroups().length === 1 ? this.sharedGroups()[0].id : null);
    this.sharedForm.reset({
      shared_debt: selectedGroup,
      description: '', amount: null, day_of_month: 1,
      payment_method: 'dinheiro', credit_card_id: null, category_id: null, paid_by: null,
    });
    this.selectedSharedGroupId.set(selectedGroup);
    if (selectedGroup) this.onSharedGroupChange(selectedGroup);
    this.showForm.set(true);
  }

  openEdit(t: RecurringExpenseTemplate): void {
    this.expenseType.set('individual');
    this.editingId.set(t.id);
    this.error.set('');
    this.form.reset({
      description: t.description,
      amount: Math.abs(Number(t.amount)),
      day_of_month: t.day_of_month,
      payment_method: t.payment_method,
      credit_card_id: t.credit_card,
      category_id: t.category,
    });
    this.showForm.set(true);
  }

  closeForm(): void {
    this.showForm.set(false);
    this.editingId.set(null);
    this.error.set('');
  }

  save(): void {
    if (this.expenseType() === 'shared') { this.saveShared(); return; }
    if (this.form.invalid) { this.form.markAllAsTouched(); return; }
    if (this.isCartao && !this.form.value.credit_card_id) {
      this.error.set('Selecione o cartao para um gasto fixo pago no cartao.');
      return;
    }
    this.error.set('');
    this.saving.set(true);

    const v = this.form.getRawValue();
    const payload = {
      description: v.description!,
      amount: v.amount!,
      day_of_month: v.day_of_month ?? 1,
      payment_method: v.payment_method!,
      credit_card_id: v.payment_method === 'cartao' ? v.credit_card_id : null,
      category_id: v.category_id,
    };

    const id = this.editingId();
    const request$ = id === null
      ? this.expenseService.createRecurringTemplate(payload)
      : this.expenseService.updateRecurringTemplate(id, payload);

    request$.subscribe({
      next: () => { this.saving.set(false); this.closeForm(); this.load(); },
      error: err => {
        this.saving.set(false);
        this.error.set(err?.error?.detail ?? 'Nao foi possivel salvar o gasto fixo.');
      },
    });
  }

  selectType(type: 'individual' | 'shared'): void {
    if (this.editingId() !== null) return;
    this.expenseType.set(type);
    this.error.set('');
  }

  onSharedGroupChange(value: number | string | null): void {
    const groupId = Number(value) || null;
    this.selectedSharedGroupId.set(groupId);
    this.sharedMembers.set([]);
    this.sharedParticipantIds.set(new Set());
    this.sharedForm.patchValue({ paid_by: null, credit_card_id: null });
    if (!groupId) return;

    const cached = this.sharedMembersByGroup().get(groupId);
    if (cached) {
      this.applySharedMembers(cached);
      return;
    }
    this.sharedDebtService.members(groupId).subscribe({
      next: members => {
        if (this.selectedSharedGroupId() !== groupId) return;
        const nextMap = new Map(this.sharedMembersByGroup());
        nextMap.set(groupId, members);
        this.sharedMembersByGroup.set(nextMap);
        this.applySharedMembers(members);
      },
      error: () => this.error.set('Não foi possível carregar os participantes deste grupo.'),
    });
  }

  private applySharedMembers(members: SharedDebtMember[]): void {
    this.sharedMembers.set(members);
    this.sharedParticipantIds.set(new Set(members.map(member => member.id)));
    const myMember = members.find(member => member.tenant_id === this.auth.userProfile.sub);
    this.sharedForm.patchValue({ paid_by: myMember?.id ?? members[0]?.id ?? null });
  }

  isSharedParticipant(memberId: number): boolean { return this.sharedParticipantIds().has(memberId); }

  toggleSharedParticipant(memberId: number): void {
    this.sharedParticipantIds.update(current => {
      const next = new Set(current);
      if (next.has(memberId)) next.delete(memberId); else next.add(memberId);
      return next;
    });
  }

  saveShared(): void {
    if (this.sharedForm.invalid) { this.sharedForm.markAllAsTouched(); return; }
    if (this.sharedParticipantIds().size === 0) {
      this.error.set('Selecione ao menos um participante.');
      return;
    }
    if (this.sharedIsCartao && this.sharedPayerIsMe && !this.sharedForm.value.credit_card_id) {
      this.error.set('Selecione o cartão usado por você.');
      return;
    }
    this.error.set('');
    this.savingShared.set(true);
    const value = this.sharedForm.getRawValue();
    const groupId = value.shared_debt!;
    this.sharedDebtService.createRecurringTemplate(groupId, {
      description: value.description!,
      amount: value.amount!,
      paid_by: value.paid_by!,
      participant_ids: [...this.sharedParticipantIds()],
      payment_method: value.payment_method!,
      credit_card_id: value.payment_method === 'cartao' ? value.credit_card_id : null,
      category_id: value.category_id,
      day_of_month: value.day_of_month ?? 1,
    }).subscribe({
      next: () => {
        this.savingShared.set(false);
        this.closeForm();
        this.loadShared();
      },
      error: err => {
        this.savingShared.set(false);
        this.error.set(err?.error?.detail ?? 'Não foi possível salvar o gasto fixo compartilhado.');
      },
    });
  }

  sharedCardName(template: SharedRecurringTemplate): string {
    if (template.payment_method !== 'cartao') return 'Dinheiro';
    const card = this.creditCards().find(item => item.id === template.credit_card_id);
    return template.credit_card_name ?? card?.name ?? 'Cartão de outro participante';
  }

  sharedMyPortion(template: SharedRecurringTemplate): number | null {
    const myMember = this.sharedMembersByGroup().get(template.shared_debt)
      ?.find(member => member.tenant_id === this.auth.userProfile.sub);
    if (!myMember || !template.participant_ids.includes(myMember.id)) return null;
    return Math.abs(Number(template.amount)) / Math.max(template.participant_ids.length, 1);
  }

  toggleShared(template: SharedRecurringTemplate): void {
    this.sharedDebtService.toggleRecurringTemplate(template.shared_debt, template.id).subscribe({ next: () => this.loadShared() });
  }

  async removeShared(template: SharedRecurringTemplate): Promise<void> {
    if (!(await this.confirmDialog.confirm(`Excluir o gasto fixo compartilhado "${template.description}" do grupo "${template.shared_debt_name}"? Os lançamentos já criados não serão afetados.`))) return;
    this.sharedDebtService.deleteRecurringTemplate(template.shared_debt, template.id).subscribe({ next: () => this.loadShared() });
  }

  toggle(t: RecurringExpenseTemplate): void {
    this.expenseService.toggleRecurringTemplate(t.id).subscribe({ next: () => this.load() });
  }

  async remove(t: RecurringExpenseTemplate): Promise<void> {
    if (!(await this.confirmDialog.confirm(`Excluir o gasto fixo \"${t.description}\"? Os lancamentos ja gerados nao sao afetados.`))) return;
    this.expenseService.deleteRecurringTemplate(t.id).subscribe({ next: () => this.load() });
  }

  shiftMonth(delta: number): void {
    let m = this.targetMonth() + delta;
    let y = this.targetYear();
    if (m < 1) { m = 12; y -= 1; }
    if (m > 12) { m = 1; y += 1; }
    this.targetMonth.set(m);
    this.targetYear.set(y);
    this.generateResult.set(null);
  }

  /**
   * Materializa os templates ativos como despesas reais do mes escolhido.
   * A partir daqui eles aparecem no Historico e, se tiverem cartao, na fatura.
   */
  generate(): void {
    this.generating.set(true);
    this.generateResult.set(null);
    this.expenseService.generateMonthRecurring(this.targetMonth(), this.targetYear()).subscribe({
      next: res => { this.generateResult.set(res); this.generating.set(false); },
      error: err => {
        this.generating.set(false);
        this.error.set(err?.error?.detail ?? 'Nao foi possivel gerar os lancamentos.');
      },
    });
  }
}
