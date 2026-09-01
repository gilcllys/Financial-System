"""
Testes de CARACTERIZACAO para os endpoints de analytics de ExpenseViewSet.

Estes testes gravam o comportamento ATUAL, nao o ideal. Existem para servir de
rede de seguranca durante a refatoracao (SOLID / Clean Code) de
`expenses/viewsets.py`, hoje com ~2.500 linhas e sem cobertura nestes endpoints.

Se algum destes testes quebrar durante um refactor, a regra de negocio mudou --
investigue antes de ajustar a expectativa.
"""

from datetime import date

from django.test import TestCase
from rest_framework.test import APIClient

from catalog.models import ExpenseCategory
from expenses import models as expense_models


class AnalyticsCharacterizationBase(TestCase):
    """Base com um tenant autenticado e helpers de criacao."""

    TENANT = 'tenant-caracterizacao'

    def _principal(self, sub):
        from financial_system.authentication import KeycloakPrincipal
        return KeycloakPrincipal({
            'sub': sub, 'email': f'{sub}@example.com',
            'given_name': 'Teste', 'family_name': 'Caracterizacao',
        })

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(user=self._principal(self.TENANT))

        self.cat_lazer = ExpenseCategory.objects.create(tenant_id='system', name='Lazer')
        self.cat_mercado = ExpenseCategory.objects.create(tenant_id='system', name='Supermercado')

        self.card = self._make_card('Bradesco', closing_day=21, due_day=5)

    def _make_card(self, name, closing_day=21, due_day=5):
        from cards.models import CreditCard
        return CreditCard.objects.create(
            tenant_id=self.TENANT, name=name,
            closing_day=closing_day, due_day=due_day, last_four_digits='1234',
        )

    def _expense(self, description, amount, on_date, category=None,
                 payment_method='dinheiro', credit_card=None):
        return expense_models.Expense.objects.create(
            tenant_id=self.TENANT,
            description=description,
            amount=amount,
            date=on_date,
            category=category or self.cat_lazer,
            payment_method=payment_method,
            credit_card=credit_card,
            quantity=1,
        )


class AnalyticsMonthlyCharacterizationTests(AnalyticsCharacterizationBase):

    def test_retorna_sempre_os_12_meses_mesmo_sem_lancamentos(self):
        resp = self.client.get('/api/expenses/expenses/analytics/monthly/?year=2026')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data), 12)
        self.assertEqual([m['month'] for m in resp.data], list(range(1, 13)))

    def test_separa_receita_de_despesa_e_calcula_saldo(self):
        self._expense('Salario', '5000.00', date(2026, 3, 1))
        self._expense('Cinema', '-100.00', date(2026, 3, 10))

        resp = self.client.get('/api/expenses/expenses/analytics/monthly/?year=2026')
        marco = resp.data[2]

        self.assertEqual(marco['month_name'], 'Mar\u00e7o')
        self.assertEqual(marco['income'], 5000.0)
        self.assertEqual(marco['expenses'], 100.0)
        self.assertEqual(marco['balance'], 4900.0)
        self.assertEqual(marco['count'], 2)

    def test_separa_gasto_em_dinheiro_de_gasto_no_cartao(self):
        self._expense('Feira', '-200.00', date(2026, 5, 4), payment_method='dinheiro')
        self._expense('Streaming', '-50.00', date(2026, 5, 6),
                      payment_method='cartao', credit_card=self.card)

        resp = self.client.get('/api/expenses/expenses/analytics/monthly/?year=2026')
        maio = resp.data[4]

        self.assertEqual(maio['cash_expenses'], 200.0)
        self.assertEqual(maio['card_expenses'], 50.0)
        self.assertEqual(maio['expenses'], 250.0)

    def test_ano_invalido_cai_para_o_ano_corrente_sem_erro(self):
        resp = self.client.get('/api/expenses/expenses/analytics/monthly/?year=abc')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data), 12)

    def test_nao_vaza_dados_de_outro_tenant(self):
        expense_models.Expense.objects.create(
            tenant_id='outro-tenant', description='Nao e meu', amount='-999.00',
            date=date(2026, 3, 5), category=self.cat_lazer,
            payment_method='dinheiro', quantity=1,
        )
        resp = self.client.get('/api/expenses/expenses/analytics/monthly/?year=2026')
        self.assertEqual(resp.data[2]['expenses'], 0.0)


class AnalyticsByCategoryCharacterizationTests(AnalyticsCharacterizationBase):

    def test_agrupa_apenas_despesas_e_ignora_receitas(self):
        self._expense('Salario', '5000.00', date(2026, 3, 1))
        self._expense('Cinema', '-100.00', date(2026, 3, 10), category=self.cat_lazer)

        resp = self.client.get('/api/expenses/expenses/analytics/by-category/?year=2026&month=3')

        self.assertEqual(len(resp.data), 1)
        self.assertEqual(resp.data[0]['category_name'], 'Lazer')
        self.assertEqual(resp.data[0]['total'], 100.0)
        self.assertEqual(resp.data[0]['percentage'], 100.0)

    def test_ordena_por_total_decrescente_e_calcula_percentual(self):
        self._expense('Feira', '-300.00', date(2026, 3, 2), category=self.cat_mercado)
        self._expense('Cinema', '-100.00', date(2026, 3, 3), category=self.cat_lazer)

        resp = self.client.get('/api/expenses/expenses/analytics/by-category/?year=2026&month=3')

        self.assertEqual([c['category_name'] for c in resp.data], ['Supermercado', 'Lazer'])
        self.assertEqual(resp.data[0]['percentage'], 75.0)
        self.assertEqual(resp.data[1]['percentage'], 25.0)

    def test_mes_fora_do_intervalo_e_ignorado_em_vez_de_dar_erro(self):
        self._expense('Cinema', '-100.00', date(2026, 3, 10))
        resp = self.client.get('/api/expenses/expenses/analytics/by-category/?year=2026&month=99')
        self.assertEqual(resp.status_code, 200)


class AnalyticsDailyCharacterizationTests(AnalyticsCharacterizationBase):

    def test_retorna_todos_os_dias_do_mes(self):
        resp = self.client.get('/api/expenses/expenses/analytics/daily/?year=2026&month=3')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data), 31)
        self.assertEqual(resp.data[0]['date'], '2026-03-01')

    def test_daily_exclui_receita_do_total(self):
        """
        A receita nao entra no grafico de gastos diarios.

        Antes este teste era
        `test_COMPORTAMENTO_ATUAL_daily_soma_receita_junto_com_despesa` e
        gravava a receita virando pico de gasto. Agora bate com o criterio da
        chave `daily` de /home-charts/ -- ver
        HomeChartsCharacterizationTests.test_daily_do_home_exclui_receita.
        """
        self._expense('Salario', '5000.00', date(2026, 3, 1))
        self._expense('Cinema', '-100.00', date(2026, 3, 2))

        resp = self.client.get('/api/expenses/expenses/analytics/daily/?year=2026&month=3')

        self.assertEqual(resp.data[0]['total'], 0.0)
        self.assertEqual(resp.data[0]['count'], 0)
        self.assertEqual(resp.data[1]['total'], 100.0)

    def test_daily_bate_com_o_daily_do_home_charts(self):
        """Trava de regressao: as duas telas nao podem divergir de novo."""
        self._expense('Salario', '5000.00', date(2026, 3, 1))
        self._expense('Cinema', '-100.00', date(2026, 3, 2))
        self._expense('Mercado', '-250.00', date(2026, 3, 5))

        daily = self.client.get(
            '/api/expenses/expenses/analytics/daily/?year=2026&month=3').data
        home = self.client.get(
            '/api/expenses/expenses/home-charts/?year=2026&month=3').data['daily']

        self.assertEqual(
            [d['total'] for d in daily],
            [h['total'] for h in home],
        )


class AnalyticsByCardCharacterizationTests(AnalyticsCharacterizationBase):

    def test_lista_vazia_quando_nao_ha_gasto_no_cartao(self):
        self._expense('Feira', '-200.00', date(2026, 3, 4), payment_method='dinheiro')
        resp = self.client.get('/api/expenses/expenses/analytics/by-card/?year=2026&month=3')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(list(resp.data), [])

    def test_agrupa_gastos_por_cartao(self):
        self._expense('Streaming', '-50.00', date(2026, 3, 6),
                      payment_method='cartao', credit_card=self.card)
        resp = self.client.get('/api/expenses/expenses/analytics/by-card/?year=2026&month=3')
        self.assertEqual(len(resp.data), 1)
        self.assertEqual(resp.data[0]['total'], 50.0)


class ConsolidatedSummaryCharacterizationTests(AnalyticsCharacterizationBase):

    EXPECTED_KEYS = {
        'month', 'year', 'income', 'cash_expenses', 'cash_count',
        'card_invoices', 'card_invoices_count', 'card_invoices_detail',
        'shared_my_portion', 'shared_count', 'total_expenses', 'balance',
    }

    def test_contrato_de_chaves_da_resposta(self):
        resp = self.client.get('/api/expenses/expenses/consolidated-summary/?year=2026&month=3')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(set(resp.data.keys()), self.EXPECTED_KEYS)

    def test_balanco_e_receita_menos_despesa_total(self):
        self._expense('Salario', '5000.00', date(2026, 3, 1))
        self._expense('Cinema', '-100.00', date(2026, 3, 10))

        resp = self.client.get('/api/expenses/expenses/consolidated-summary/?year=2026&month=3')

        self.assertEqual(resp.data['income'], 5000.0)
        self.assertEqual(resp.data['cash_expenses'], 100.0)
        self.assertEqual(resp.data['total_expenses'], 100.0)
        self.assertEqual(resp.data['balance'], 4900.0)

    def test_gasto_no_cartao_nao_entra_como_dinheiro(self):
        self._expense('Streaming', '-50.00', date(2026, 3, 6),
                      payment_method='cartao', credit_card=self.card)
        resp = self.client.get('/api/expenses/expenses/consolidated-summary/?year=2026&month=3')
        self.assertEqual(resp.data['cash_expenses'], 0.0)
        self.assertEqual(resp.data['cash_count'], 0)


class HomeChartsCharacterizationTests(AnalyticsCharacterizationBase):

    EXPECTED_KEYS = {'month', 'year', 'summary', 'by_category', 'daily', 'weekly'}

    def test_contrato_de_chaves_da_resposta(self):
        resp = self.client.get('/api/expenses/expenses/home-charts/?year=2026&month=3')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(set(resp.data.keys()), self.EXPECTED_KEYS)
        self.assertEqual(set(resp.data['summary'].keys()),
                         {'income', 'expenses', 'balance', 'count'})

    def test_daily_do_home_exclui_receita(self):
        """Mesmo criterio de /analytics/daily/ desde a correcao da divergencia."""
        self._expense('Salario', '5000.00', date(2026, 3, 1))
        self._expense('Cinema', '-100.00', date(2026, 3, 2))

        resp = self.client.get('/api/expenses/expenses/home-charts/?year=2026&month=3')

        self.assertEqual(resp.data['daily'][0]['total'], 0.0)
        self.assertEqual(resp.data['daily'][1]['total'], 100.0)
        self.assertEqual(resp.data['summary']['income'], 5000.0)
        self.assertEqual(resp.data['summary']['expenses'], 100.0)

    def test_weekly_divide_o_mes_em_semanas(self):
        self._expense('Cinema', '-100.00', date(2026, 3, 10))
        resp = self.client.get('/api/expenses/expenses/home-charts/?year=2026&month=3')
        weekly = resp.data['weekly']
        self.assertTrue(len(weekly) >= 4)
        self.assertEqual(sum(w['total'] for w in weekly), 100.0)
