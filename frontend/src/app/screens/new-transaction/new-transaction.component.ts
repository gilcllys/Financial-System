import { CommonModule, isPlatformBrowser } from '@angular/common';
import type { OnInit } from '@angular/core';
import { Component, inject, PLATFORM_ID, signal } from '@angular/core';
import {
  FormControl,
  FormGroup,
  ReactiveFormsModule,
  Validators,
} from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatNativeDateModule } from '@angular/material/core';
import { MatDatepickerModule } from '@angular/material/datepicker';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSelectModule } from '@angular/material/select';
import { MatSlideToggleModule } from '@angular/material/slide-toggle';
import { Router } from '@angular/router';
import { ToastrService } from 'ngx-toastr';
import type { ExpenseCategory } from '../../models';
import { ExpenseService } from '../../services/expense.service';

@Component({
  selector: 'app-new-transaction',
  standalone: true,
  imports: [
    CommonModule,
    ReactiveFormsModule,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule,
    MatDatepickerModule,
    MatNativeDateModule,
    MatProgressSpinnerModule,
    MatIconModule,
    MatButtonModule,
    MatSlideToggleModule,
  ],
  templateUrl: './new-transaction.component.html',
  styleUrl: './new-transaction.component.css',
})
export class NewTransactionComponent implements OnInit {
  private expenseService = inject(ExpenseService);
  private toastr = inject(ToastrService);
  private router = inject(Router);
  private platformId = inject(PLATFORM_ID);

  transactionForm!: FormGroup;
  transactionType = signal<'expense' | 'income'>('expense');
  categories = signal<ExpenseCategory[]>([]);
  isLoading = signal(false);

  ngOnInit(): void {
    this.transactionForm = new FormGroup({
      description: new FormControl('', [Validators.required]),
      amount: new FormControl(null, [
        Validators.required,
        Validators.min(0.01),
      ]),
      categoryId: new FormControl(null, [Validators.required]),
      date: new FormControl(new Date(), [Validators.required]),
      quantity: new FormControl(1, [Validators.required, Validators.min(1)]),
      isInstallment: new FormControl(false),
      installments: new FormControl(1),
    });

    this.loadCategories();
  }

  setType(type: 'expense' | 'income'): void {
    this.transactionType.set(type);
  }

  private loadCategories(): void {
    this.expenseService.getCategories().subscribe({
      next: (categories) => this.categories.set(categories),
      error: (err) => {
        console.error('Erro ao carregar categorias:', err);
        this.toastr.error('Erro ao carregar categorias.', 'Erro');
      },
    });
  }

  private getUserId(): number | null {
    if (!isPlatformBrowser(this.platformId)) {
      return null;
    }
    const userStr = localStorage.getItem('user');
    if (!userStr) {
      return null;
    }
    try {
      const user = JSON.parse(userStr);
      return user.id ?? null;
    } catch {
      return null;
    }
  }

  onSubmit(): void {
    if (this.transactionForm.invalid) {
      this.toastr.error('Preencha todos os campos obrigatórios.', 'Erro');
      return;
    }

    const userId = this.getUserId();
    if (!userId) {
      this.toastr.error('Usuário não autenticado.', 'Erro');
      return;
    }

    this.isLoading.set(true);

    const {
      description,
      amount,
      categoryId,
      date,
      quantity,
      isInstallment,
      installments,
    } = this.transactionForm.value;

    const finalAmount =
      this.transactionType() === 'expense'
        ? -Math.abs(amount)
        : Math.abs(amount);
    const dateStr =
      date instanceof Date ? date.toISOString().split('T')[0] : date;

    this.expenseService
      .createExpense({
        user_id: userId,
        category_id: categoryId,
        description,
        amount: finalAmount,
        date: dateStr,
        quantity: quantity || 1,
        is_installment: isInstallment || false,
        installments: isInstallment ? installments || 1 : 1,
      })
      .subscribe({
        next: () => {
          this.isLoading.set(false);
          this.toastr.success('Transação criada com sucesso!', 'Sucesso');
          this.router.navigate(['/transactions']);
        },
        error: (error) => {
          this.isLoading.set(false);
          const errorMessage =
            error.error?.detail ||
            error.error?.message ||
            'Erro ao criar transação.';
          this.toastr.error(errorMessage, 'Erro');
          console.error('Erro ao criar transação:', error);
        },
      });
  }

  goBack(): void {
    this.router.navigate(['/transactions']);
  }
}
