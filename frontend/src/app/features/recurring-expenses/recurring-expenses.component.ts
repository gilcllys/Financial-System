import { Component, OnInit, inject, signal, computed } from '@angular/core';
import { RouterLink } from '@angular/router';
import { ReactiveFormsModule, FormBuilder, Validators } from '@angular/forms';

import { ExpenseService, RecurringExpenseTemplate, GenerateMonthResult } from '../../core/services/expense.service';
import { CardService } from '../../core/services/card.service';
import { CategoryService } from '../../core/services/category.service';
import { CreditCard, ExpenseCategory } from '../../core/models';

const MONTH_NAMES = [
  '', 'Janeiro', 'Fevereiro', 'Mar\u00e7o', 'Abril', 'Maio', 'Junho',
  'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro',
];

@Component({
  selector: 'app-recurring-expenses',
  standalone: true,
  imports: [ReactiveFormsModule, RouterLink],
  templateUrl: './recurring-expenses.component.html',
  styleUrl: './recurring-expenses.component.scss',
})
export class RecurringExpensesComponent implements OnInit {
  private expenseService = inject(ExpenseService);
  private cardService = inject(CardService);
  private categoryService = inject(CategoryService);
  private fb = inject(FormBuilder);

  templates = signal<RecurringExpenseTemplate[]>([]);
  creditCards = signal<CreditCard[]>([]);
  categories = signal<ExpenseCategory[]>([]);

  loading = signal(false);
  saving = signal(false);
  generating = signal(false);
  error = signal('');
  showForm = signal(false);
  editingId = signal<number | null>(null);
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

  /** cartao => credit_card_id obrigatorio, espelhando a regra do backend. */
  get isCartao(): boolean {
    return this.form.value.payment_method === 'cartao';
  }

  activeTemplates = computed(() => this.templates().filter(t => t.is_active));

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
    this.cardService.list().subscribe({ next: cards => this.creditCards.set(cards) });
    this.categoryService.list().subscribe({ next: cats => this.categories.set(cats) });
  }

  load(): void {
    this.loading.set(true);
    this.expenseService.listRecurringTemplates().subscribe({
      next: tpls => { this.templates.set(tpls); this.loading.set(false); },
      error: () => { this.error.set('Nao foi possivel carregar os gastos fixos.'); this.loading.set(false); },
    });
  }

  openCreate(): void {
    this.editingId.set(null);
    this.error.set('');
    this.form.reset({
      description: '', amount: null, day_of_month: 1,
      payment_method: 'dinheiro', credit_card_id: null, category_id: null,
    });
    this.showForm.set(true);
  }

  openEdit(t: RecurringExpenseTemplate): void {
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

  toggle(t: RecurringExpenseTemplate): void {
    this.expenseService.toggleRecurringTemplate(t.id).subscribe({ next: () => this.load() });
  }

  remove(t: RecurringExpenseTemplate): void {
    if (!confirm(`Excluir o gasto fixo \"${t.description}\"? Os lancamentos ja gerados nao sao afetados.`)) return;
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
