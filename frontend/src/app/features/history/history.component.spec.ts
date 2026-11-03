import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { of } from 'rxjs';
import axe from 'axe-core';

import { HistoryComponent } from './history.component';
import { CardService } from '../../core/services/card.service';
import { CategoryService } from '../../core/services/category.service';
import { ExpenseService } from '../../core/services/expense.service';
import { SharedDebtService } from '../../core/services/shared-debt.service';

/**
 * O selo "Fixo" distingue, na listagem, a despesa gerada por um gasto fixo da
 * lancada a mao. A origem vem do backend (is_recurring); o front nao adivinha
 * pela descricao -- era exatamente essa inferencia que causava os bugs de
 * duplicidade do gasto fixo.
 */
function expense(over: Partial<any> = {}): any {
  return {
    id: 1, description: 'Netflix', amount: -20.9, date: '2026-09-03',
    category_id: 10, category_name: 'Assinaturas', payment_method: 'cartao',
    credit_card_id: 1, quantity: 1, tenant_id: 't1',
    created_at: '2026-09-01', updated_at: '2026-09-01',
    recurring_template_id: null, is_recurring: false, ...over,
  };
}

describe('HistoryComponent - selo de gasto fixo', () => {
  function setup(expenses: any[]) {
    TestBed.configureTestingModule({
      imports: [HistoryComponent],
      providers: [
        provideRouter([]),
        {
          provide: ExpenseService,
          useValue: { history: () => of({
            results: expenses.map(item => ({ ...item, type: 'individual', group_id: null,
              group_name: null, paid_by_name: null, installment_number: null,
              total_installments: null, card_name: null })),
            count: expenses.length, next: null, previous: null,
            totals: { count: expenses.length, income: 0, expenses: 0, net: 0 },
          }) },
        },
        { provide: SharedDebtService, useValue: { listEntries: () => of({ results: [], count: 0 }) } },
        { provide: CategoryService, useValue: { list: () => of([]) } },
        { provide: CardService, useValue: { list: () => of([]) } },
      ],
    });

    const fixture = TestBed.createComponent(HistoryComponent);
    fixture.detectChanges();
    return fixture;
  }

  function badges(fixture: any): HTMLElement[] {
    return Array.from(fixture.nativeElement.querySelectorAll('.recurring-badge'));
  }

  it('marca com "Fixo" a despesa gerada por um template', () => {
    const fixture = setup([expense({ is_recurring: true, recurring_template_id: 6 })]);

    const found = badges(fixture);
    expect(found.length).toBe(1);
    expect(found[0].textContent?.trim()).toBe('Fixo');
  });

  it('nao marca a despesa lancada manualmente', () => {
    const fixture = setup([expense({ is_recurring: false, recurring_template_id: null })]);

    expect(badges(fixture).length).toBe(0);
  });

  it('marca apenas as fixas quando a lista mistura as duas origens', () => {
    const fixture = setup([
      expense({ id: 1, description: 'Netflix', is_recurring: true, recurring_template_id: 6 }),
      expense({ id: 2, description: 'Mercado', is_recurring: false }),
      expense({ id: 3, description: 'Spotify', is_recurring: true, recurring_template_id: 7 }),
    ]);

    expect(badges(fixture).length).toBe(2);
  });

  it('nao marca nada quando o backend ainda nao envia is_recurring', () => {
    const semCampo = expense();
    delete semCampo.is_recurring;
    delete semCampo.recurring_template_id;

    const fixture = setup([semCampo]);

    expect(badges(fixture).length).toBe(0);
  });

  it('nao usa a descricao para inferir a origem', () => {
    // Gasto manual homonimo de um gasto fixo: nao pode ganhar o selo.
    const fixture = setup([
      expense({ id: 1, description: 'Netflix', is_recurring: true, recurring_template_id: 6 }),
      expense({ id: 2, description: 'Netflix', is_recurring: false, recurring_template_id: null }),
    ]);

    expect(badges(fixture).length).toBe(1);
  });

  it('nao tem violações WCAG A/AA detectáveis pelo axe na lista', async () => {
    const fixture = setup([expense({ is_recurring: true, recurring_template_id: 6 })]);
    await fixture.whenStable();

    const result = await axe.run(fixture.nativeElement, {
      runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'] },
    });

    const violations = result.violations.map(violation => ({
      id: violation.id,
      nodes: violation.nodes.map(node => ({ target: node.target, summary: node.failureSummary })),
    }));
    expect(violations).withContext(JSON.stringify(violations)).toEqual([]);
  });
});
