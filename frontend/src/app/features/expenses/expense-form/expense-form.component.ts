import { Component, OnInit, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { Router, ActivatedRoute, RouterLink } from '@angular/router';
import { ExpenseService } from '../../../core/services/expense.service';
import { CardService } from '../../../core/services/card.service';
import { CategoryService } from '../../../core/services/category.service';
import { CreditCard, ExpenseCategory } from '../../../core/models';

@Component({
  selector: 'app-expense-form',
  standalone: true,
  imports: [ReactiveFormsModule, RouterLink],
  templateUrl: './expense-form.component.html',
  styleUrls: ['./expense-form.component.scss'],
})
export class ExpenseFormComponent implements OnInit {
  private fb = inject(FormBuilder);
  private expenseService = inject(ExpenseService);
  private cardService = inject(CardService);
  private categoryService = inject(CategoryService);
  private router = inject(Router);
  private route = inject(ActivatedRoute);

  categories = signal<ExpenseCategory[]>([]);
  cards = signal<CreditCard[]>([]);
  loading = signal(false);
  saving = signal(false);
  errorMessage = signal('');
  isEdit = signal(false);
  editId = signal<number | null>(null);

  // true = receita (entrada), false = despesa (saída)
  isIncome = signal(false);

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
    this.loadSelects();
    this.setupConditionals();

    const id = this.route.snapshot.paramMap.get('id');
    if (id) {
      this.isEdit.set(true);
      this.editId.set(+id);
      this.loadExpense(+id);
    }
  }

  toggleType(income: boolean): void {
    this.isIncome.set(income);
  }

  private setupConditionals(): void {
    this.form.get('is_installment')!.valueChanges.subscribe(val => {
      const installmentsCtrl = this.form.get('installments')!;
      const quantityCtrl = this.form.get('quantity')!;
      if (val) {
        // Parcelado ativo: habilita parcelas, trava quantity em 1
        installmentsCtrl.enable();
        quantityCtrl.setValue(1);
        quantityCtrl.disable();
      } else {
        // Parcelado desativo: desabilita parcelas, libera quantity
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

  private loadSelects(): void {
    this.categoryService.list().subscribe({ next: cats => this.categories.set(cats) });
    this.cardService.list().subscribe({ next: cards => this.cards.set(cards) });
  }

  private loadExpense(id: number): void {
    this.loading.set(true);
    this.expenseService.get(id).subscribe({
      next: expense => {
        // Define o toggle baseado no sinal do amount
        this.isIncome.set(expense.amount >= 0);
        this.form.patchValue({
          description: expense.description?.replace(/^\[CASAL\]\s*/, '') ?? '',
          amount: Math.abs(expense.amount),
          date: expense.date,
          category_id: expense.category_id,
          payment_method: expense.payment_method,
          credit_card_id: expense.credit_card_id,
          quantity: expense.quantity,
        });
        this.loading.set(false);
      },
      error: () => {
        this.errorMessage.set('Erro ao carregar gasto.');
        this.loading.set(false);
      },
    });
  }

  submit(): void {
    if (this.form.invalid) { this.form.markAllAsTouched(); return; }
    this.saving.set(true);
    this.errorMessage.set('');

    const v = this.form.getRawValue();
    const absAmount = Math.abs(v.amount!);
    // Receita = positivo, Despesa = negativo
    const signedAmount = this.isIncome() ? absAmount : -absAmount;

    const payload = {
      category_id: v.category_id!,
      description: v.need_pay_vitoria ? `[CASAL] ${v.description!}` : v.description!,
      amount: signedAmount,
      date: v.date!,
      quantity: v.quantity!,
      payment_method: v.payment_method!,
      credit_card_id: v.payment_method === 'cartao' ? v.credit_card_id : null,
      is_installment: !!v.is_installment,
      installments: v.installments ?? 1,
      need_pay_vitoria: !!v.need_pay_vitoria,
    };

    const req$ = this.isEdit()
      ? this.expenseService.update(this.editId()!, payload)
      : this.expenseService.create(payload);

    req$.subscribe({
      next: () => this.router.navigate(['/expenses']),
      error: err => {
        this.saving.set(false);
        this.errorMessage.set(err?.error?.detail ?? 'Erro ao salvar gasto. Tente novamente.');
      },
    });
  }

  private todayStr(): string {
    return new Date().toISOString().split('T')[0];
  }

  hasError(field: string): boolean {
    const c = this.form.get(field);
    return !!(c?.invalid && c?.touched);
  }
}
