import { Injectable } from '@angular/core';
import type { Observable } from 'rxjs';
import { map } from 'rxjs/operators';
import { Expense, ExpenseCategory } from '../models';
import { BaseService } from './baseservice.service';

export interface CreateExpensePayload {
  user_id: number;
  category_id: number;
  description: string;
  amount: number;
  date: string;
  quantity: number;
  is_installment: boolean;
  installments: number;
}

@Injectable({
  providedIn: 'root',
})
export class ExpenseService extends BaseService {
  getExpenses(): Observable<Expense[]> {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    return this.get<any[]>('/api/auth/cost/expense/').pipe(
      map((data) => data.map((item) => Expense.fromJson(item))),
    );
  }

  getCategories(): Observable<ExpenseCategory[]> {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    return this.get<any[]>('/api/auth/cost/expense_category/').pipe(
      map((data) => data.map((item) => ExpenseCategory.fromJson(item))),
    );
  }

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  createExpense(payload: CreateExpensePayload): Observable<any> {
    return this.post('/api/auth/cost/expense/create-expense/', payload);
  }
}
