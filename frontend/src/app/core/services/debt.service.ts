import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';

export interface VitoriaDebt {
  id: number;
  expense_id: number;
  is_paid: boolean;
  expense_description: string;
  expense_amount: number;
  expense_date: string;
  expense_category_name: string;
}

export interface VitoriaSummary {
  total_pending: number;
  total_paid: number;
  count_pending: number;
  count_paid: number;
}

@Injectable({ providedIn: 'root' })
export class DebtService {
  private http = inject(HttpClient);
  private base = `${environment.apiBaseUrl}/api/debts/vitoria-debts`;

  list(): Observable<VitoriaDebt[]> {
    return this.http.get<VitoriaDebt[]>(`${this.base}/`);
  }

  summary(): Observable<VitoriaSummary> {
    return this.http.get<VitoriaSummary>(`${this.base}/summary/`);
  }

  markPaid(id: number): Observable<any> {
    return this.http.post(`${this.base}/${id}/mark-paid/`, {});
  }
}
