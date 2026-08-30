import { TestBed } from '@angular/core/testing';
import { of, throwError } from 'rxjs';

import { RecurringExpensesComponent } from './recurring-expenses.component';
import { ExpenseService } from '../../core/services/expense.service';
import { CardService } from '../../core/services/card.service';
import { CategoryService } from '../../core/services/category.service';

/**
 * Testes de CARACTERIZACAO da tela de Gastos Fixos.
 *
 * Gravam o comportamento ATUAL. Servem de rede de seguranca para o refactor
 * SOLID/Clean Code: se quebrarem, a regra de negocio mudou.
 *
 * Cobrem os 3 bugs latentes que esta tela finalmente expoe na UI:
 *  - template de cartao sem cartao atribuido nao pode ser salvo nem gerado
 *  - o total mensal ignora templates pausados
 *  - amount chega como STRING do DRF e precisa ser normalizado antes de somar
 */

function template(over: Partial<any> = {}): any {
  return {
    id: 1,
    description: 'Netflix',
    amount: '20.90',            // DRF DecimalField devolve string
    day_of_month: 10,
    payment_method: 'dinheiro',
    credit_card: null,
    credit_card_name: null,
    category: 8,
    category_name: 'Assinaturas',
    is_active: true,
    ...over,
  };
}

describe('RecurringExpensesComponent [caracterizacao]', () => {
  let expSvc: any;

  function setup(templates: any[] = []) {
    expSvc = {
      listRecurringTemplates: jasmine.createSpy('list').and.returnValue(of(templates)),
      createRecurringTemplate: jasmine.createSpy('create').and.returnValue(of(template())),
      updateRecurringTemplate: jasmine.createSpy('update').and.returnValue(of(template())),
      deleteRecurringTemplate: jasmine.createSpy('delete').and.returnValue(of(null)),
      toggleRecurringTemplate: jasmine.createSpy('toggle').and.returnValue(of(template())),
      generateMonthRecurring: jasmine.createSpy('generate')
        .and.returnValue(of({ created: [], skipped: [], skipped_invalid: [] })),
    };

    TestBed.configureTestingModule({
      imports: [RecurringExpensesComponent],
      providers: [
        { provide: ExpenseService, useValue: expSvc },
        { provide: CardService, useValue: { list: () => of([{ id: 1, name: 'Itau Azul' }]) } },
        { provide: CategoryService, useValue: { list: () => of([{ id: 8, name: 'Assinaturas' }]) } },
      ],
    });

    const fixture = TestBed.createComponent(RecurringExpensesComponent);
    fixture.detectChanges();
    return fixture.componentInstance;
  }

  it('carrega os templates ao iniciar', () => {
    const c = setup([template()]);
    expect(expSvc.listRecurringTemplates).toHaveBeenCalled();
    expect(c.templates().length).toBe(1);
  });

  it('soma o total mensal tratando amount como string', () => {
    const c = setup([template({ id: 1, amount: '20.90' }), template({ id: 2, amount: '55.10' })]);
    // string concatenada daria '20.9055.10'; o esperado e a soma numerica
    expect(c.monthlyTotal()).toBeCloseTo(76.0, 2);
  });

  it('ignora templates pausados no total mensal', () => {
    const c = setup([
      template({ id: 1, amount: '100.00', is_active: true }),
      template({ id: 2, amount: '999.00', is_active: false }),
    ]);
    expect(c.monthlyTotal()).toBeCloseTo(100.0, 2);
    expect(c.activeTemplates().length).toBe(1);
  });

  it('separa o total entre cartao e dinheiro', () => {
    const c = setup([
      template({ id: 1, amount: '30.00', payment_method: 'cartao', credit_card: 1 }),
      template({ id: 2, amount: '70.00', payment_method: 'dinheiro' }),
    ]);
    expect(c.cardTotal()).toBeCloseTo(30.0, 2);
    expect(c.cashTotal()).toBeCloseTo(70.0, 2);
  });

  it('soma valores negativos pelo modulo', () => {
    // o backend guarda despesa como negativa; a tela mostra o custo, nao o sinal
    const c = setup([template({ amount: '-20.90' })]);
    expect(c.monthlyTotal()).toBeCloseTo(20.9, 2);
  });

  it('sinaliza template de cartao sem cartao atribuido', () => {
    const c = setup([
      template({ id: 1, payment_method: 'cartao', credit_card: null }),
      template({ id: 2, payment_method: 'cartao', credit_card: 1 }),
      template({ id: 3, payment_method: 'dinheiro' }),
    ]);
    expect(c.invalidTemplates().length).toBe(1);
    expect(c.invalidTemplates()[0].id).toBe(1);
  });

  it('bloqueia o salvamento de cartao sem cartao selecionado', () => {
    const c = setup();
    c.openCreate();
    c.form.patchValue({
      description: 'Spotify', amount: 21.9, day_of_month: 5,
      payment_method: 'cartao', credit_card_id: null,
    });
    c.save();
    expect(expSvc.createRecurringTemplate).not.toHaveBeenCalled();
    expect(c.error()).toContain('cartao');
  });

  it('nao envia credit_card_id quando o pagamento e em dinheiro', () => {
    const c = setup();
    c.openCreate();
    c.form.patchValue({
      description: 'Aluguel', amount: 1200, day_of_month: 5,
      payment_method: 'dinheiro', credit_card_id: 1,
    });
    c.save();
    expect(expSvc.createRecurringTemplate).toHaveBeenCalled();
    expect(expSvc.createRecurringTemplate.calls.mostRecent().args[0].credit_card_id).toBeNull();
  });

  it('nao envia o formulario invalido', () => {
    const c = setup();
    c.openCreate();
    c.save(); // descricao e valor vazios
    expect(expSvc.createRecurringTemplate).not.toHaveBeenCalled();
  });

  it('openEdit carrega o template e save chama update, nao create', () => {
    const c = setup([template({ id: 7, description: 'TIM', amount: '59.90' })]);
    c.openEdit(c.templates()[0]);
    expect(c.editingId()).toBe(7);
    expect(c.form.value.description).toBe('TIM');
    expect(c.form.value.amount).toBeCloseTo(59.9, 2);

    c.save();
    expect(expSvc.updateRecurringTemplate).toHaveBeenCalled();
    expect(expSvc.createRecurringTemplate).not.toHaveBeenCalled();
    expect(expSvc.updateRecurringTemplate.calls.mostRecent().args[0]).toBe(7);
  });

  it('openCreate limpa o modo de edicao', () => {
    const c = setup([template({ id: 7 })]);
    c.openEdit(c.templates()[0]);
    c.openCreate();
    expect(c.editingId()).toBeNull();
    expect(c.form.value.description).toBe('');
  });

  it('gera os lancamentos do mes selecionado', () => {
    const c = setup([template()]);
    c.generate();
    expect(expSvc.generateMonthRecurring)
      .toHaveBeenCalledWith(c.targetMonth(), c.targetYear());
  });

  it('shiftMonth atravessa a virada do ano', () => {
    const c = setup();
    c.targetMonth.set(12);
    c.targetYear.set(2026);
    c.shiftMonth(1);
    expect(c.targetMonth()).toBe(1);
    expect(c.targetYear()).toBe(2027);

    c.shiftMonth(-1);
    expect(c.targetMonth()).toBe(12);
    expect(c.targetYear()).toBe(2026);
  });

  it('expoe skipped_invalid no resultado da geracao', () => {
    const c = setup([template()]);
    expSvc.generateMonthRecurring.and.returnValue(
      of({ created: ['Netflix'], skipped: ['TIM'], skipped_invalid: ['Spotify'] })
    );
    c.generate();
    expect(c.generateResult()?.skipped_invalid).toEqual(['Spotify']);
    expect(c.generating()).toBeFalse();
  });

  it('recarrega a lista apos pausar e apos excluir', () => {
    const c = setup([template()]);
    expSvc.listRecurringTemplates.calls.reset();

    c.toggle(c.templates()[0]);
    expect(expSvc.toggleRecurringTemplate).toHaveBeenCalled();
    expect(expSvc.listRecurringTemplates).toHaveBeenCalled();

    spyOn(window, 'confirm').and.returnValue(true);
    c.remove(c.templates()[0]);
    expect(expSvc.deleteRecurringTemplate).toHaveBeenCalled();
  });

  it('nao exclui quando o usuario cancela a confirmacao', () => {
    const c = setup([template()]);
    spyOn(window, 'confirm').and.returnValue(false);
    c.remove(c.templates()[0]);
    expect(expSvc.deleteRecurringTemplate).not.toHaveBeenCalled();
  });

  it('mostra o erro do backend quando o salvamento falha', () => {
    const c = setup();
    expSvc.createRecurringTemplate.and.returnValue(
      throwError(() => ({ error: { detail: 'Descricao ja existe.' } }))
    );
    c.openCreate();
    c.form.patchValue({ description: 'Netflix', amount: 20.9, day_of_month: 1, payment_method: 'dinheiro' });
    c.save();
    expect(c.error()).toBe('Descricao ja existe.');
    expect(c.saving()).toBeFalse();
  });
});
