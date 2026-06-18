import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { map } from 'rxjs/operators';
import { environment } from '../../../environments/environment';
import {
  SupermarketExpense,
  SupermarketExpenseItem,
  CreateSupermarketExpensePayload,
  CreateSupermarketItemPayload,
  PaginatedResponse,
} from '../models';

function normalizeItem(raw: any): SupermarketExpenseItem {
  return {
    ...raw,
    unit_price: parseFloat(raw.unit_price),
    quantity: +raw.quantity,
  };
}

function normalizeExpense(raw: any): SupermarketExpense {
  return {
    ...raw,
    total: parseFloat(raw.total ?? '0'),
    items: (raw.items ?? []).map(normalizeItem),
  };
}

@Injectable({ providedIn: 'root' })
export class SupermarketService {
  private http = inject(HttpClient);
  private base = `${environment.apiBaseUrl}/api/supermarket/supermarket-expenses`;
  private itemBase = `${environment.apiBaseUrl}/api/supermarket/supermarket-expense-items`;

  // ── Expenses ──────────────────────────────────────────────────────────────

  list(): Observable<SupermarketExpense[]> {
    return this.http
      .get<any>(`${this.base}/`)
      .pipe(
        map(res => {
          // suporta resposta paginada ou array simples
          const arr = Array.isArray(res) ? res : res.results ?? [];
          return arr.map(normalizeExpense);
        })
      );
  }

  get(id: number): Observable<SupermarketExpense> {
    return this.http
      .get<any>(`${this.base}/${id}/`)
      .pipe(map(normalizeExpense));
  }

  create(payload: CreateSupermarketExpensePayload): Observable<SupermarketExpense> {
    return this.http
      .post<any>(`${this.base}/`, payload)
      .pipe(map(normalizeExpense));
  }

  update(id: number, payload: Partial<CreateSupermarketExpensePayload>): Observable<SupermarketExpense> {
    return this.http
      .put<any>(`${this.base}/${id}/`, payload)
      .pipe(map(normalizeExpense));
  }

  delete(id: number): Observable<void> {
    return this.http.delete<void>(`${this.base}/${id}/`);
  }

  // ── Items ─────────────────────────────────────────────────────────────────

  createItem(payload: CreateSupermarketItemPayload): Observable<SupermarketExpenseItem> {
    return this.http
      .post<any>(`${this.itemBase}/`, payload)
      .pipe(map(normalizeItem));
  }

  updateItem(id: number, payload: Partial<CreateSupermarketItemPayload>): Observable<SupermarketExpenseItem> {
    return this.http
      .put<any>(`${this.itemBase}/${id}/`, payload)
      .pipe(map(normalizeItem));
  }

  deleteItem(id: number): Observable<void> {
    return this.http.delete<void>(`${this.itemBase}/${id}/`);
  }
}
