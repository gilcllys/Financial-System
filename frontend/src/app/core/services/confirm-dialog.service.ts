import { DOCUMENT } from '@angular/common';
import { Injectable, inject } from '@angular/core';

@Injectable({ providedIn: 'root' })
export class ConfirmDialogService {
  private document = inject(DOCUMENT);

  confirm(message: string, confirmLabel = 'Excluir'): Promise<boolean> {
    const doc = this.document;
    const previousFocus = doc.activeElement as HTMLElement | null;
    const backdrop = doc.createElement('div');
    backdrop.className = 'app-dialog-backdrop';
    const dialog = doc.createElement('section');
    dialog.className = 'app-confirm-dialog';
    dialog.setAttribute('role', 'alertdialog');
    dialog.setAttribute('aria-modal', 'true');
    dialog.setAttribute('aria-labelledby', 'app-confirm-title');
    dialog.setAttribute('aria-describedby', 'app-confirm-description');
    dialog.tabIndex = -1;

    const title = doc.createElement('h2');
    title.id = 'app-confirm-title';
    title.textContent = 'Confirmar ação';
    const description = doc.createElement('p');
    description.id = 'app-confirm-description';
    description.textContent = message;
    const actions = doc.createElement('div');
    actions.className = 'app-confirm-dialog__actions';
    const cancel = doc.createElement('button');
    cancel.type = 'button';
    cancel.className = 'btn btn--secondary';
    cancel.textContent = 'Cancelar';
    const confirm = doc.createElement('button');
    confirm.type = 'button';
    confirm.className = 'btn btn--danger';
    confirm.textContent = confirmLabel;
    actions.append(cancel, confirm);
    dialog.append(title, description, actions);
    backdrop.append(dialog);

    return new Promise(resolve => {
      let settled = false;
      const background = Array.from(doc.body.children)
        .filter((element): element is HTMLElement => element instanceof HTMLElement)
        .map(element => ({ element, inert: element.inert }));
      const finish = (accepted: boolean) => {
        if (settled) return;
        settled = true;
        doc.removeEventListener('keydown', onKeyDown, true);
        backdrop.remove();
        for (const entry of background) entry.element.inert = entry.inert;
        previousFocus?.focus?.();
        resolve(accepted);
      };
      const onKeyDown = (event: KeyboardEvent) => {
        if (event.key === 'Escape') {
          event.preventDefault();
          finish(false);
        } else if (event.key === 'Tab') {
          event.preventDefault();
          (doc.activeElement === cancel ? confirm : cancel).focus();
        }
      };
      cancel.addEventListener('click', () => finish(false));
      confirm.addEventListener('click', () => finish(true));
      backdrop.addEventListener('click', event => {
        if (event.target === backdrop) finish(false);
      });
      doc.addEventListener('keydown', onKeyDown, true);
      doc.body.append(backdrop);
      for (const entry of background) entry.element.inert = true;
      cancel.focus();
    });
  }
}
