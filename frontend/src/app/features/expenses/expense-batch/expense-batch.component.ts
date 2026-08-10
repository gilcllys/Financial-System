import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { SlicePipe } from '@angular/common';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import { ExpenseService } from '../../../core/services/expense.service';
import { CardService } from '../../../core/services/card.service';
import { CategoryService } from '../../../core/services/category.service';
import { CreditCard, CreateExpensePayload, ExpenseCategory } from '../../../core/models';

interface DraftExpense {
  localId: number;
  isIncome: boolean;
  description: string;
  amount: number;
  date: string;
  category_id: number;
  category_name: string;
  payment_method: 'dinheiro' | 'cartao';
  credit_card_id: number | null;
  is_installment: boolean;
  installments: number;
  need_pay_vitoria: boolean;
}

@Component({
  selector: 'app-expense-batch',
  standalone: true,
  imports: [ReactiveFormsModule, RouterLink, SlicePipe],
  templateUrl: './expense-batch.component.html',
  styleUrls: ['./expense-batch.component.scss'],
})
export class ExpenseBatchComponent implements OnInit {
  private fb = inject(FormBuilder);
  private expenseService = inject(ExpenseService);
  private cardService = inject(CardService);
  private categoryService = inject(CategoryService);
  private router = inject(Router);

  categories = signal<ExpenseCategory[]>([]);
  cards = signal<CreditCard[]>([]);
  drafts = signal<DraftExpense[]>([]);
  saving = signal(false);
  errorMessage = signal('');
  isIncome = signal(false);

  private nextId = 1;

  signedSum = computed(() =>
    this.drafts().reduce((acc, d) => acc + (d.isIncome ? Math.abs(d.amount) : -Math.abs(d.amount)), 0)
  );

  form = this.fb.group({
    description: ['', [Validators.required, Validators.minLength(2)]],
    amount: [null as number | null, [Validators.required, Validators.min(0.01)]],
    date: [this.todayStr(), Validators.required],
    category_id: [null as number | null, Validators.required],
    payment_method: ['dinheiro' as 'dinheiro' | 'cartao', Validators.required],
    credit_card_id: [null as number | null],
    is_installment: [false],
    installments: [{ value: 1, disabled: true }, [Validators.min(2), Validators.max(60)]],
    quantity: [1, [Validators.required, Validators.min(1)]],
    need_pay_vitoria: [false],
  });

  get isCartao(): boolean { return this.form.value.payment_method === 'cartao'; }
  get isInstallment(): boolean { return !!this.form.value.is_installment; }

  ngOnInit(): void {
    this.categoryService.list().subscribe({ next: cats => this.categories.set(cats) });
    this.cardService.list().subscribe({ next: cards => this.cards.set(cards) });
    this.setupConditionals();
  }

  toggleType(income: boolean): void { this.isIncome.set(income); }

  private setupConditionals(): void {
    this.form.get('is_installment')!.valueChanges.subscribe(val => {
      const installmentsCtrl = this.form.get('installments')!;
      const quantityCtrl = this.form.get('quantity')!;
      if (val) {
        installmentsCtrl.enable();
        quantityCtrl.setValue(1);
        quantityCtrl.disable();
      } else {
        installmentsCtrl.disable();
        installmentsCtrl.setValue(1);
        quantityCtrl.enable();
      }
    });

    this.form.get('payment_method')!.valueChanges.subscribe(val => {
      const ctrl = this.form.get('credit_card_id')!;
      if (val === 'cartao') { ctrl.setValidators(Validators.required); }
      else { ctrl.clearValidators(); ctrl.setValue(null); }
      ctrl.updateValueAndValidity();
    });
  }

  addToList(): void {
    if (this.form.invalid) { this.form.markAllAsTouched(); return; }
    const v = this.form.getRawValue();
    const catName = this.categories().find(c => c.id === v.category_id)?.name ?? '';
    this.drafts.update(list => [...list, {
      localId: this.nextId++,
      isIncome: this.isIncome(),
      description: v.description!,
      amount: Math.abs(v.amount!),
      date: v.date!,
      category_id: v.category_id!,
      category_name: catName,
      payment_method: v.payment_method!,
      credit_card_id: v.payment_method === 'cartao' ? v.credit_card_id : null,
      is_installment: !!v.is_installment,
      installments: v.installments ?? 1,
      need_pay_vitoria: !!v.need_pay_vitoria,
    }]);
    // Reset, mantendo data e método por conveniência
    const keepDate = v.date!;
    const keepMethod = v.payment_method!;
    this.form.reset({ date: keepDate, payment_method: keepMethod, quantity: 1, is_installment: false, installments: 1, need_pay_vitoria: false });
  }

  edit(d: DraftExpense): void {
    this.remove(d.localId);
    this.isIncome.set(d.isIncome);
    this.form.patchValue({
      description: d.description,
      amount: d.amount,
      date: d.date,
      category_id: d.category_id,
      payment_method: d.payment_method,
      credit_card_id: d.credit_card_id,
      is_installment: d.is_installment,
      installments: d.installments,
      need_pay_vitoria: d.need_pay_vitoria,
    });
  }

  duplicate(d: DraftExpense): void {
    this.drafts.update(list => [...list, { ...d, localId: this.nextId++ }]);
  }

  remove(localId: number): void {
    this.drafts.update(list => list.filter(d => d.localId !== localId));
  }

  saveAll(): void {
    if (this.drafts().length === 0 || this.saving()) { return; }
    this.saving.set(true);
    this.errorMessage.set('');

    const items: CreateExpensePayload[] = this.drafts().map(d => {
      const signed = d.isIncome ? Math.abs(d.amount) : -Math.abs(d.amount);
      return {
        category_id: d.category_id,
        description: d.need_pay_vitoria ? `[CASAL] ${d.description}` : d.description,
        amount: signed,
        date: d.date,
        quantity: 1,
        payment_method: d.payment_method,
        credit_card_id: d.payment_method === 'cartao' ? d.credit_card_id : null,
        is_installment: d.is_installment,
        installments: d.installments,
        need_pay_vitoria: d.need_pay_vitoria,
      };
    });

    this.expenseService.bulkCreate(items).subscribe({
      next: () => this.router.navigate(['/expenses']),
      error: err => {
        this.saving.set(false);
        this.errorMessage.set(err?.error?.message ?? err?.error?.detail ?? 'Erro ao salvar gastos. Tente novamente.');
      },
    });
  }

  formatAmount(amount: number): string {
    return new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(Math.abs(amount));
  }
  amountClass(amount: number): string { return amount >= 0 ? 'value-up' : 'value-down'; }
  amountPrefix(amount: number): string { return amount >= 0 ? '+' : '-'; }
  draftAmount(d: DraftExpense): number { return d.isIncome ? Math.abs(d.amount) : -Math.abs(d.amount); }

  private todayStr(): string { return new Date().toISOString().split('T')[0]; }

  hasError(field: string): boolean {
    const c = this.form.get(field);
    return !!(c?.invalid && c?.touched);
  }
}
