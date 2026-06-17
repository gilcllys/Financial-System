import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';
import { CreditCard, CreateCreditCardPayload } from '../models';

@Injectable({ providedIn: 'root' })
export class CardService {
  private http = inject(HttpClient);
  private base = `${environment.apiBaseUrl}/api/cards`;

  list(): Observable<CreditCard[]> {
    return this.http.get<CreditCard[]>(`${this.base}/`);
  }

  get(id: number): Observable<CreditCard> {
    return this.http.get<CreditCard>(`${this.base}/${id}/`);
  }

  create(payload: CreateCreditCardPayload): Observable<CreditCard> {
    return this.http.post<CreditCard>(`${this.base}/`, payload);
  }

  update(id: number, payload: Partial<CreateCreditCardPayload>): Observable<CreditCard> {
    return this.http.put<CreditCard>(`${this.base}/${id}/`, payload);
  }

  delete(id: number): Observable<void> {
    return this.http.delete<void>(`${this.base}/${id}/`);
  }
}
