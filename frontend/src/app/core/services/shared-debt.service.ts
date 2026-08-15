import { Injectable, inject } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';

// ─── Response shapes ──────────────────────────────────────────────────────────

export interface SharedDebtGroup {
  id: number;
  name: string;
  owner_tenant_id: string;
  created_at: string;
}

export interface SharedDebtMember {
  id: number;
  shared_debt: number;
  tenant_id: string | null;
  display_name: string;
  email: string | null;
}

export interface SharedDebtEntry {
  id: number;
  shared_debt: number;
  paid_by: number;
  paid_by_name: string;
  description: string;
  amount: number;
  date: string;
  payment_method: 'dinheiro' | 'cartao';
  credit_card: number | null;
  category: number | null;
  category_name: string | null;
  created_by_tenant_id: string;
  created_at: string;
}

export interface MemberBalance {
  member_id: number;
  display_name: string;
  tenant_id: string | null;
  paid: number;
  owed: number;
  balance: number;
}

export interface SettlementLine {
  from_member_id: number;
  from_name: string;
  to_member_id: number;
  to_name: string;
  amount: number;
}

export interface BalancesResponse {
  members: MemberBalance[];
  settlement: SettlementLine[];
}

export interface InviteResponse {
  invite_token: string;
  join_path: string;
}

export interface CreateGroupPayload {
  name: string;
  member_names?: string[];
}

export interface CreateEntryPayload {
  shared_debt: number;
  description: string;
  amount: number;
  date: string;
  paid_by: number;
  participant_ids?: number[];
  payment_method?: 'dinheiro' | 'cartao';
  credit_card_id?: number | null;
  category_id?: number | null;
}

export interface PersonalSummary {
  installments_remaining: { total: number; count: number };
  card_current_month: { total: number; count: number };
}

@Injectable({ providedIn: 'root' })
export class SharedDebtService {
  private http = inject(HttpClient);
  private base = `${environment.apiBaseUrl}/api/debts`;

  // ─── Groups ─────────────────────────────────────────────────────────────
  listGroups(): Observable<SharedDebtGroup[]> {
    return this.http.get<SharedDebtGroup[]>(`${this.base}/shared-debts/`);
  }

  getGroup(id: number): Observable<SharedDebtGroup> {
    return this.http.get<SharedDebtGroup>(`${this.base}/shared-debts/${id}/`);
  }

  createGroup(payload: CreateGroupPayload): Observable<SharedDebtGroup> {
    return this.http.post<SharedDebtGroup>(`${this.base}/shared-debts/`, payload);
  }

  deleteGroup(id: number): Observable<void> {
    return this.http.delete<void>(`${this.base}/shared-debts/${id}/`);
  }

  createInvite(id: number, expiresAt?: string | null): Observable<InviteResponse> {
    return this.http.post<InviteResponse>(`${this.base}/shared-debts/${id}/invite/`, {
      expires_at: expiresAt ?? null,
    });
  }

  join(token: string, displayName?: string): Observable<SharedDebtGroup> {
    return this.http.post<SharedDebtGroup>(`${this.base}/shared-debts/join/`, {
      token,
      display_name: displayName,
    });
  }

  members(id: number): Observable<SharedDebtMember[]> {
    return this.http.get<SharedDebtMember[]>(`${this.base}/shared-debts/${id}/members/`);
  }

  balances(id: number): Observable<BalancesResponse> {
    return this.http.get<BalancesResponse>(`${this.base}/shared-debts/${id}/balances/`);
  }

  // ─── Entries ────────────────────────────────────────────────────────────
  listEntries(params: { shared_debt?: number; credit_card?: number }): Observable<SharedDebtEntry[]> {
    let httpParams = new HttpParams();
    if (params.shared_debt != null) httpParams = httpParams.set('shared_debt', params.shared_debt);
    if (params.credit_card != null) httpParams = httpParams.set('credit_card', params.credit_card);
    return this.http.get<SharedDebtEntry[]>(`${this.base}/shared-entries/`, { params: httpParams });
  }

  createEntry(payload: CreateEntryPayload): Observable<SharedDebtEntry> {
    return this.http.post<SharedDebtEntry>(`${this.base}/shared-entries/`, payload);
  }

  updateEntry(id: number, payload: Partial<CreateEntryPayload>): Observable<SharedDebtEntry> {
    return this.http.patch<SharedDebtEntry>(`${this.base}/shared-entries/${id}/`, payload);
  }

  deleteEntry(id: number): Observable<void> {
    return this.http.delete<void>(`${this.base}/shared-entries/${id}/`);
  }

  // ─── Personal debts summary ─────────────────────────────────────────────
  personalSummary(): Observable<PersonalSummary> {
    return this.http.get<PersonalSummary>(`${this.base}/personal-summary/`);
  }
}
