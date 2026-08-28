import { Component, inject } from '@angular/core';
import { ToastService } from '../../core/services/toast.service';

@Component({
  selector: 'app-toast',
  standalone: true,
  template: `
    <div class="toast-stack" role="region" aria-label="Notificações">
      @for (t of toastSvc.toasts(); track t.id) {
        <div class="toast toast--{{ t.kind }}" role="alert" aria-live="assertive">
          <span class="toast__icon" aria-hidden="true">
            @switch (t.kind) {
              @case ('success') { &#10003; }
              @case ('error') { &#33; }
              @case ('warning') { &#9888; }
              @default { &#105; }
            }
          </span>
          <span class="toast__msg">{{ t.message }}</span>
          <button type="button" class="toast__close" aria-label="Fechar"
                  (click)="toastSvc.dismiss(t.id)">&times;</button>
        </div>
      }
    </div>
  `,
  styles: [`
    .toast-stack {
      position: fixed;
      top: 16px;
      right: 16px;
      z-index: 9999;
      display: flex;
      flex-direction: column;
      gap: 10px;
      max-width: min(420px, calc(100vw - 32px));
      pointer-events: none;
    }
    .toast {
      pointer-events: auto;
      display: flex;
      align-items: flex-start;
      gap: 10px;
      padding: 12px 14px;
      border-radius: 10px;
      background: #1f2937;
      color: #f9fafb;
      box-shadow: 0 8px 24px rgba(0, 0, 0, .28);
      border-left: 4px solid #6b7280;
      font-size: 14px;
      line-height: 1.45;
      animation: toast-in .18s ease-out;
    }
    .toast--success { border-left-color: #10b981; }
    .toast--error   { border-left-color: #ef4444; }
    .toast--warning { border-left-color: #f59e0b; }
    .toast--info    { border-left-color: #3b82f6; }
    .toast__icon {
      flex: 0 0 auto;
      font-weight: 700;
      line-height: 1.45;
    }
    .toast__msg { flex: 1 1 auto; }
    .toast__close {
      flex: 0 0 auto;
      background: none;
      border: none;
      color: inherit;
      opacity: .65;
      font-size: 18px;
      line-height: 1;
      cursor: pointer;
      padding: 0 2px;
    }
    .toast__close:hover { opacity: 1; }
    @keyframes toast-in {
      from { opacity: 0; transform: translateX(12px); }
      to   { opacity: 1; transform: translateX(0); }
    }
    @media (prefers-reduced-motion: reduce) {
      .toast { animation: none; }
    }
  `],
})
export class ToastComponent {
  readonly toastSvc = inject(ToastService);
}
