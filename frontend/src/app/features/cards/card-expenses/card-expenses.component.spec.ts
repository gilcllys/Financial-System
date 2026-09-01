import { TestBed } from '@angular/core/testing';
import { ActivatedRoute } from '@angular/router';
import { of } from 'rxjs';

import { CardExpensesComponent } from './card-expenses.component';
import { CardService } from '../../../core/services/card.service';
import { ExpenseService } from '../../../core/services/expense.service';
import { SharedDebtService } from '../../../core/services/shared-debt.service';
import { CategoryService } from '../../../core/services/category.service';
import { AuthService } from '../../../core/auth/auth.service';
import { D3ChartService } from '../../../core/services/d3-chart.service';

/**
 * Testes de CARACTERIZACAO.
 *
 * Estes testes gravam o comportamento ATUAL do componente, nao o comportamento
 * ideal. Servem de rede de seguranca para a refatoracao SOLID/Clean Code:
 * se algum deles quebrar durante o refactor, a regra de negocio mudou.
 *
 * Nao alterar as expectativas sem antes confirmar que a mudanca e intencional.
 */

function invoice(over: Partial<any> = {}): any {
  return {
    month: 9, year: 2026, label: 'Setembro/2026',
    period_start: '2026-07-23', period_end: '2026-08-21',
    due_date: '2026-09-05', is_current: true, is_future: false, ...over,
  };
}

function expense(over: Partial<any> = {}): any {
  return {
    id: 1, description: 'Compra', amount: -100, date: '2026-08-01',
    category: 10, category_id: 10, category_name: 'Diversos',
    credit_card: 1, ...over,
  };
}

function sharedEntry(over: Partial<any> = {}): any {
  return {
    id: 1, description: 'Rateio', amount: -50, date: '2026-08-02',
    category: 3, category_name: 'Lazer', shared_debt_name: 'Casa',
    installment_number: 1, total_installments: 1,
    credit_card: 1, participants: [], ...over,
  };
}

/** Payload de /invoice-expenses com os totais que o backend devolve. */
function invoiceData(over: Partial<any> = {}): any {
  return {
    expenses: [],
    by_category: [],
    pagination: { page: 1, page_size: 20, total: 0, total_pages: 1 },
    summary: {
      total: 0, expenses_total: 0, shared_total: 0, count: 0,
      shared_breakdown: { total: 0, participants: [] },
    },
    ...over,
  };
}

describe('CardExpensesComponent [caracterizacao]', () => {
  let cardSvc: any;
  let sharedSvc: any;

  function setup(opts: {
    invoiceData?: any; chartExpenses?: any[]; sharedEntries?: any[];
    sharedEntriesFake?: (params: any) => any;
    userProfile?: { name?: string; email?: string; sub?: string };
  } = {}) {
    cardSvc = {
      get: jasmine.createSpy('get').and.returnValue(of({ id: 1, name: 'Bradesco' })),
      getAllCardExpenses: jasmine.createSpy('getAllCardExpenses').and.returnValue(of([])),
      getInvoices: jasmine.createSpy('getInvoices').and.returnValue(of([invoice()])),
      getInvoiceExpenses: jasmine.createSpy('getInvoiceExpenses')
        .and.returnValue(of(opts.invoiceData ?? invoiceData())),
      getInvoiceChart: jasmine.createSpy('getInvoiceChart').and.returnValue(
        of({
          expenses: opts.chartExpenses ?? [],
          by_category: [],
          period_start: '2026-07-23',
          period_end: '2026-08-21',
        }),
      ),
    };
    sharedSvc = {
      listEntries: jasmine.createSpy('listEntries').and.callFake((params: any) =>
        opts.sharedEntriesFake
          ? opts.sharedEntriesFake(params)
          : of({
              results: opts.sharedEntries ?? [],
              count: (opts.sharedEntries ?? []).length,
              next: null,
              previous: null,
            }),
      ),
      updateEntry: jasmine.createSpy('updateEntry').and.returnValue(of({})),
      deleteEntry: jasmine.createSpy('deleteEntry').and.returnValue(of(null)),
    };

    TestBed.configureTestingModule({
      imports: [CardExpensesComponent],
      providers: [
        { provide: ActivatedRoute, useValue: { snapshot: { paramMap: { get: () => '1' } } } },
        { provide: CardService, useValue: cardSvc },
        { provide: SharedDebtService, useValue: sharedSvc },
        { provide: ExpenseService, useValue: { delete: () => of(null) } },
        { provide: CategoryService, useValue: { list: () => of([]) } },
        { provide: AuthService, useValue: { userProfile: opts.userProfile ?? { sub: 'tenant-1' } } },
        {
          provide: D3ChartService,
          useValue: {
            renderBarChart: () => {}, renderDonutChart: () => {},
            renderAreaChart: () => {}, renderLineChart: () => {},
          },
        },
      ],
    });

    const fixture = TestBed.createComponent(CardExpensesComponent);
    fixture.detectChanges();
    return fixture;
  }

  describe('invoiceGrandTotal', () => {
    it('soma gastos individuais + valor CHEIO dos compartilhados (nao a sua parte)', () => {
      const f = setup({
        invoiceData: invoiceData({
          summary: {
            total: 3514.9, expenses_total: 1000, shared_total: 500, count: 2,
            shared_breakdown: { total: 4013.33, participants: [] },
          },
        }),
      });
      const c = f.componentInstance;

      // Regra: o banco cobra o valor integral da compra compartilhada.
      expect(c.invoiceGrandTotal()).toBe(1000 + 4013.33);

      // Contraste explicito: NAO e o summary.total do backend.
      expect(c.invoiceGrandTotal()).not.toBe(c.filteredTotal());
    });

    it('usa summary.total como fallback quando expenses_total nao vem', () => {
      const f = setup({
        invoiceData: invoiceData({
          summary: {
            total: 777, shared_total: 0, count: 1,
            shared_breakdown: { total: 0, participants: [] },
          },
        }),
      });
      expect(f.componentInstance.expensesTotal()).toBe(777);
    });
  });

  describe('myTenantId', () => {
    it('usa o sub do perfil quando presente', () => {
      const c = setup().componentInstance;
      expect(c.myTenantId).toBe('tenant-1');
      expect(c.iPaid(sharedEntry({ paid_by_tenant_id: 'tenant-1' }))).toBeTrue();
    });

    it('vira null (sem quebrar) quando o perfil nao tem sub', () => {
      const c = setup({ userProfile: {} }).componentInstance;
      expect(c.myTenantId).toBeNull();
      // Nao pode dar match acidental com uma entrada sem dono.
      expect(c.iPaid(sharedEntry({ paid_by_tenant_id: 'tenant-1' }))).toBeFalse();
    });
  });

  describe('busca na tabela (regressao do PR #123)', () => {
    it('filtra as linhas ao escrever no campo de busca', () => {
      const f = setup({
        chartExpenses: [
          expense({ id: 1, description: 'Padaria do Joao' }),
          expense({ id: 2, description: '[CREDITO] - Pagamento a maior' }),
          expense({ id: 3, description: 'Posto Shell' }),
        ],
      });
      const c = f.componentInstance;
      expect(c.combinedFiltered().length).toBe(3);

      c.searchControl.setValue('credito');
      f.detectChanges();

      // Antes do fix, computed() nao rastreava FormControl e isto continuava 3.
      expect(c.combinedFiltered().length).toBe(1);
      expect(c.combinedFiltered()[0].description).toContain('[CREDITO]');
    });

    it('a busca e case-insensitive e ignora espacos nas pontas', () => {
      const f = setup({
        chartExpenses: [
          expense({ id: 1, description: 'Padaria do Joao' }),
          expense({ id: 2, description: 'Posto Shell' }),
        ],
      });
      const c = f.componentInstance;
      c.searchControl.setValue('  PADARIA  ');
      f.detectChanges();
      expect(c.combinedFiltered().length).toBe(1);
      expect(c.combinedFiltered()[0].description).toBe('Padaria do Joao');
    });

    it('marca hasActiveFilters quando ha busca', () => {
      const f = setup({ chartExpenses: [expense()] });
      const c = f.componentInstance;
      expect(c.hasActiveFilters()).toBeFalse();
      c.searchControl.setValue('x');
      f.detectChanges();
      expect(c.hasActiveFilters()).toBeTrue();
    });

    it('NAO refaz a chamada ao servidor ao buscar (o card de total nao pode mudar)', () => {
      const f = setup({ chartExpenses: [expense()] });
      const chamadasAntes = cardSvc.getInvoiceExpenses.calls.count();
      f.componentInstance.searchControl.setValue('padaria');
      f.detectChanges();
      expect(cardSvc.getInvoiceExpenses.calls.count()).toBe(chamadasAntes);
    });
  });

  describe('combinedRows', () => {
    it('mostra individuais e compartilhados com valor absoluto', () => {
      const f = setup({
        chartExpenses: [expense({ id: 1, amount: -100 })],
        sharedEntries: [sharedEntry({ id: 2, amount: -50 })],
      });
      const rows = f.componentInstance.combinedRows();
      expect(rows.length).toBe(2);
      expect(rows.map((r: any) => r.amount)).toEqual([100, 50]);
      expect(rows.map((r: any) => r.kind)).toEqual(['individual', 'compartilhado']);
    });

    it('COMPORTAMENTO ATUAL: credito (valor positivo) aparece como positivo, sem distincao', () => {
      // Caracterizacao de uma limitacao conhecida: o lancamento de credito
      // "[CREDITO] - Pagamento a maior fatura anterior" e exibido igual a um gasto.
      const f = setup({ chartExpenses: [expense({ id: 1, amount: 41.61, description: '[CREDITO]' })] });
      const row = f.componentInstance.combinedRows()[0];
      expect(row.amount).toBe(41.61);
      expect(row.kind).toBe('individual');
    });
  });

  describe('paginacao da tabela combinada', () => {
    it('pagina de 20 em 20 e reseta para a pagina 1 ao buscar', () => {
      const many = Array.from({ length: 45 }, (_, i) =>
        expense({ id: i + 1, description: `Gasto ${i + 1}` }),
      );
      const f = setup({ chartExpenses: many });
      const c = f.componentInstance;

      expect(c.combinedTotalPages()).toBe(3);
      expect(c.combinedPageRows().length).toBe(20);

      c.changePage(3);
      f.detectChanges();
      expect(c.combinedPageRows().length).toBe(5);

      c.searchControl.setValue('Gasto 1');
      f.detectChanges();
      expect(c.currentPage()).toBe(1);
    });
  });
  describe('sharedEntries: carregamento pelo periodo da fatura (bug do corte silencioso de paginacao)', () => {
    it('busca por start_date/end_date do periodo da invoice selecionada, sem depender de month/year', () => {
      setup({ sharedEntries: [sharedEntry({ id: 1 })] });
      const params = sharedSvc.listEntries.calls.mostRecent().args[0];
      expect(params.credit_card).toBe(1);
      expect(params.start_date).toBe('2026-07-23');
      expect(params.end_date).toBe('2026-08-21');
      expect(params.month).toBeUndefined();
      expect(params.year).toBeUndefined();
    });

    it('busca TODAS as paginas do periodo, sem perder lancamentos antigos empurrados para a pagina 2', () => {
      const newer = sharedEntry({ id: 45, date: '2026-08-17', description: 'Milhas Livelo' });
      const older = sharedEntry({ id: 10, date: '2026-07-24', description: 'Pet Love do Pitoco' });

      const f = setup({
        sharedEntriesFake: (params: any) =>
          of((params.page ?? 1) === 1
            ? { results: [newer], count: 2, next: 'http://x/shared-entries/?page=2', previous: null }
            : { results: [older], count: 2, next: null, previous: null }),
      });

      const descriptions = f.componentInstance.filteredSharedEntries()
        .map((e: any) => e.description).sort();
      expect(descriptions).toEqual(['Milhas Livelo', 'Pet Love do Pitoco']);
    });

    it('recarrega pelo periodo da fatura (nao lista tudo) apos excluir um compartilhado', () => {
      const f = setup({ sharedEntries: [] });
      sharedSvc.listEntries.calls.reset();
      spyOn(window, 'confirm').and.returnValue(true);

      f.componentInstance.deleteSharedEntry({
        sharedEntry: sharedEntry({ id: 99, description: 'Teste' }),
      } as any);

      const params = sharedSvc.listEntries.calls.mostRecent().args[0];
      expect(params.start_date).toBe('2026-07-23');
      expect(params.end_date).toBe('2026-08-21');
    });

    it('ao trocar de fatura (selectInvoice), busca os compartilhados do novo periodo', () => {
      const f = setup({ sharedEntries: [] });
      sharedSvc.listEntries.calls.reset();

      f.componentInstance.selectInvoice(
        invoice({ invoice_month: 8, invoice_year: 2026, period_start: '2026-06-23', period_end: '2026-07-22' }),
      );

      const params = sharedSvc.listEntries.calls.mostRecent().args[0];
      expect(params.start_date).toBe('2026-06-23');
      expect(params.end_date).toBe('2026-07-22');
    });
  });
});

