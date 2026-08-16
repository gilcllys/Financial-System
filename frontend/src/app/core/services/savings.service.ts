import { Injectable, inject } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';

export interface SavingsGoal {
  id: number;
  name: string;
  target_amount: number | null;
  color: string;
  icon: string;
  total_deposited: number;
  deposit_count: number;
  created_at: string;
}

export interface SavingsDeposit {
  id: number;
  goal: number;
  goal_name: string;
  amount: number;
  date: string;
  description: string;
  created_at: string;
}

export interface MonthlySavings {
  year: number;
  month: number;
  month_name: string;
  total: number;
  accumulated: number;
}

export interface SavingsSummary {
  goals: SavingsGoal[];
  grand_total: number;
  monthly_breakdown: MonthlySavings[];
}

export interface CreateGoalPayload {
  name: string;
  target_amount?: number | null;
  color?: string;
  icon?: string;
}

export interface CreateDepositPayload {
  goal_id: number;
  amount: number;
  date: string;
  description?: string;
}

@Injectable({ providedIn: 'root' })
export class SavingsService {
  private http = inject(HttpClient);
  private base = `${environment.apiBaseUrl}/api/savings`;

  getSummary(): Observable<SavingsSummary> {
    return this.http.get<SavingsSummary>(`${this.base}/goals/summary/`);
  }

  listGoals(): Observable<SavingsGoal[]> {
    return this.http.get<SavingsGoal[]>(`${this.base}/goals/`);
  }

  createGoal(payload: CreateGoalPayload): Observable<SavingsGoal> {
    return this.http.post<SavingsGoal>(`${this.base}/goals/`, payload);
  }

  updateGoal(id: number, payload: Partial<CreateGoalPayload>): Observable<SavingsGoal> {
    return this.http.patch<SavingsGoal>(`${this.base}/goals/${id}/`, payload);
  }

  deleteGoal(id: number): Observable<void> {
    return this.http.delete<void>(`${this.base}/goals/${id}/`);
  }

  listDeposits(goalId?: number): Observable<SavingsDeposit[]> {
    let params = new HttpParams();
    if (goalId != null) params = params.set('goal', goalId);
    return this.http.get<SavingsDeposit[]>(`${this.base}/deposits/`, { params });
  }

  createDeposit(payload: CreateDepositPayload): Observable<SavingsDeposit> {
    return this.http.post<SavingsDeposit>(`${this.base}/deposits/`, payload);
  }

  deleteDeposit(id: number): Observable<void> {
    return this.http.delete<void>(`${this.base}/deposits/${id}/`);
  }
}
