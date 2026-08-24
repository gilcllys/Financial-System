import { Injectable, inject } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';

// Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬ Response shapes Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬

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
  shared_debt_name: string;
  paid_by: number;
  paid_by_name: string;
  paid_by_tenant_id: string | null;
  description: string;
  amount: number;
  date: string;
  payment_method: 'dinheiro' | 'cartao';
  credit_card: number | null;
  credit_card_name: string | null;
  category: number | null;
  category_name: string | null;
  participant_count: number;
  installment_group_id: string | null;
  total_installments: number;
  installment_number: number;
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
  total_installments_input?: number;
}

export interface PersonalSummary {
  installments_remaining: { total: number; count: number };
  card_current_month: { total: number; count: number };
}


export interface SharedDebtHomeSummary {
  id: number;
  name: string;
  members: string[];
  total_amount: number;
  my_portion: number;
  entry_count: number;
}

export interface MonthlyHistoryEntry {
  year: number;
  month: number;
  month_name: string;
  total: number;
  my_portion: number;
  entry_count: number;
}

export interface RecurringTemplate {
  id: number;
  shared_debt: number;
  description: string;
  amount: number;
  paid_by: number;
  paid_by_name: string;
  paid_by_tenant_id: string | null;
  participant_ids: number[];
  payment_method: 'dinheiro' | 'cartao';
  category: number | null;
  category_name: string | null;
  day_of_month: number;
  is_active: boolean;
  created_at: string;
}

export interface CreateRecurringTemplatePayload {
  description: string;
  amount: number;
  paid_by: number;
  participant_ids?: number[];
  payment_method?: 'dinheiro' | 'cartao';
  category_id?: number | null;
  day_of_month?: number;
}

export interface PaginatedResponse<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

@Injectable({ providedIn: 'root' })
export class SharedDebtService {
  private http = inject(HttpClient);
  private base = `${environment.apiBaseUrl}/api/debts`;

  // Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬ Groups Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬
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

  // Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬ Entries Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬
  listEntries(params: {
    shared_debt?: number;
    credit_card?: number;
    month?: number;
    year?: number;
    category?: number | null;
    page?: number;
    page_size?: number;
  }): Observable<PaginatedResponse<SharedDebtEntry>> {
    let httpParams = new HttpParams();
    if (params.shared_debt != null) httpParams = httpParams.set('shared_debt', params.shared_debt);
    if (params.credit_card != null) httpParams = httpParams.set('credit_card', params.credit_card);
    if (params.month  != null)      httpParams = httpParams.set('month', params.month);
    if (params.year   != null)      httpParams = httpParams.set('year',  params.year);
    if (params.category != null)    httpParams = httpParams.set('category', params.category);
    if (params.page   != null)      httpParams = httpParams.set('page', params.page);
    if (params.page_size != null)   httpParams = httpParams.set('page_size', params.page_size);
    return this.http.get<PaginatedResponse<SharedDebtEntry>>(`${this.base}/shared-entries/`, { params: httpParams });
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

  // Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬ Personal debts summary Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬
  personalSummary(): Observable<PersonalSummary> {
    return this.http.get<PersonalSummary>(`${this.base}/personal-summary/`);
  }

  homeSummary(): Observable<SharedDebtHomeSummary[]> {
    return this.http.get<SharedDebtHomeSummary[]>(`${this.base}/shared-debts/home-summary/`);
  }

  monthlyHistory(id: number): Observable<MonthlyHistoryEntry[]> {
    return this.http.get<MonthlyHistoryEntry[]>(`${this.base}/shared-debts/${id}/monthly-history/`);
  }

  listRecurringTemplates(id: number): Observable<RecurringTemplate[]> {
    return this.http.get<RecurringTemplate[]>(`${this.base}/shared-debts/${id}/recurring-templates/`);
  }

  createRecurringTemplate(id: number, payload: CreateRecurringTemplatePayload): Observable<RecurringTemplate> {
    return this.http.post<RecurringTemplate>(`${this.base}/shared-debts/${id}/recurring-templates/`, payload);
  }

  deleteRecurringTemplate(groupId: number, tplId: number): Observable<void> {
    return this.http.delete<void>(`${this.base}/shared-debts/${groupId}/recurring-templates/${tplId}/`);
  }

  toggleRecurringTemplate(groupId: number, tplId: number): Observable<RecurringTemplate> {
    return this.http.patch<RecurringTemplate>(`${this.base}/shared-debts/${groupId}/recurring-templates/${tplId}/`, {});
  }

  generateMonth(groupId: number, month: number, year: number): Observable<{ created: string[]; skipped: string[] }> {
    return this.http.post<{ created: string[]; skipped: string[] }>(
      `${this.base}/shared-debts/${groupId}/generate-month/`, { month, year }
    );
  }
}

