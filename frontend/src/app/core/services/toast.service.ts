import { Injectable, signal } from '@angular/core';

export type ToastKind = 'success' | 'error' | 'warning' | 'info';

export interface Toast {
  id: number;
  kind: ToastKind;
  message: string;
}

/**
 * Extrai uma mensagem legível de um HttpErrorResponse.
 *
 * O backend responde em formatos diferentes conforme a camada que rejeitou:
 *  - behaviors  -> { success: false, message: "..." }
 *  - DRF field  -> { credit_card_id: ["Obrigatório quando..."] }
 *  - DRF detail -> { detail: "..." }
 */
export function apiErrorMessage(err: unknown, fallback: string): string {
  const body = (err as { error?: unknown })?.error;
  if (typeof body === 'string' && body.trim()) return body;
  if (!body || typeof body !== 'object') return fallback;

  const obj = body as Record<string, unknown>;
  for (const key of ['message', 'detail']) {
    const v = obj[key];
    if (typeof v === 'string' && v.trim()) return v;
  }

  // Erros de campo do DRF: pega a primeira mensagem disponível.
  for (const value of Object.values(obj)) {
    if (typeof value === 'string' && value.trim()) return value;
    if (Array.isArray(value) && typeof value[0] === 'string' && value[0].trim()) {
      return value[0];
    }
  }
  return fallback;
}

@Injectable({ providedIn: 'root' })
export class ToastService {
  private seq = 0;
  readonly toasts = signal<Toast[]>([]);

  show(message: string, kind: ToastKind = 'info', durationMs = 6000): void {
    const id = ++this.seq;
    this.toasts.update(list => [...list, { id, kind, message }]);
    if (durationMs > 0) {
      setTimeout(() => this.dismiss(id), durationMs);
    }
  }

  success(message: string, durationMs = 4000): void { this.show(message, 'success', durationMs); }
  error(message: string, durationMs = 7000): void { this.show(message, 'error', durationMs); }
  warning(message: string, durationMs = 6000): void { this.show(message, 'warning', durationMs); }

  /** Mostra o erro vindo da API, ou `fallback` se a resposta não trouxer mensagem. */
  apiError(err: unknown, fallback: string): string {
    const msg = apiErrorMessage(err, fallback);
    this.error(msg);
    return msg;
  }

  dismiss(id: number): void {
    this.toasts.update(list => list.filter(t => t.id !== id));
  }
}
