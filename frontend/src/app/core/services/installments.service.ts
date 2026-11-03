import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';
import { CreditCard, Expense } from '../models';
import { SharedDebtEntry } from './shared-debt.service';

export interface InstallmentsOverview {
  expenses: Expense[];
  shared_entries: SharedDebtEntry[];
  cards: CreditCard[];
}

@Injectable({ providedIn: 'root' })
export class InstallmentsService {
  private http = inject(HttpClient);

  load(): Observable<InstallmentsOverview> {
    return this.http.get<InstallmentsOverview>(`${environment.apiBaseUrl}/api/dashboard/installments/`);
  }
}
