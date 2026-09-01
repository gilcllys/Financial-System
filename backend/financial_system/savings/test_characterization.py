"""
Testes de CARACTERIZACAO do app `savings` (cofrinhos / metas de investimento).

O app nasceu sem nenhum teste e sem `behaviors.py`, ficando fora do padrao do
resto do projeto (viewsets = HTTP fino, behaviors = regra de negocio). Estes
testes gravam o comportamento ATUAL, nao o ideal -- inclusive divergencias
conhecidas, marcadas com o prefixo `test_COMPORTAMENTO_ATUAL_`.

Servem de rede de seguranca para uma futura extracao de `savings/viewsets.py`
para `savings/behaviors.py`. Se algum destes testes quebrar durante um refactor,
a regra de negocio mudou -- investigue antes de ajustar a expectativa.
"""

from datetime import date
from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APIClient

from savings.models import SavingsDeposit, SavingsGoal


class SavingsCharacterizationBase(TestCase):
    """Base com um tenant autenticado, um tenant vizinho e helpers de criacao."""

    TENANT = 'tenant-savings-1'
    OTHER_TENANT = 'tenant-savings-2'

    GOALS_URL = '/api/savings/goals/'
    DEPOSITS_URL = '/api/savings/deposits/'

    def _principal(self, sub):
        from financial_system.authentication import KeycloakPrincipal
        return KeycloakPrincipal({
            'sub': sub, 'email': f'{sub}@example.com',
            'given_name': 'Teste', 'family_name': 'Caracterizacao',
        })

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(user=self._principal(self.TENANT))

    def _goal(self, name='Viagem', tenant=None, **overrides):
        data = dict(tenant_id=tenant or self.TENANT, name=name)
        data.update(overrides)
        return SavingsGoal.objects.create(**data)

    def _deposit(self, goal, amount='100.00', on_date=None, tenant=None, description=''):
        return SavingsDeposit.objects.create(
            goal=goal,
            tenant_id=tenant or goal.tenant_id,
            amount=Decimal(amount),
            date=on_date or date(2026, 3, 10),
            description=description,
        )


# ---------------------------------------------------------------------------
# SavingsGoalViewSet -- list / retrieve
# ---------------------------------------------------------------------------

class SavingsGoalListCharacterizationTests(SavingsCharacterizationBase):

    def test_lista_vazia_quando_o_tenant_nao_tem_cofrinho(self):
        resp = self.client.get(self.GOALS_URL)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(list(resp.data), [])

    def test_contrato_de_chaves_do_serializer(self):
        self._goal()
        resp = self.client.get(self.GOALS_URL)
        self.assertEqual(
            set(resp.data[0].keys()),
            {'id', 'name', 'target_amount', 'color', 'icon',
             'total_deposited', 'deposit_count', 'created_at'},
        )

    def test_lista_ordenada_por_id_crescente(self):
        self._goal('Carro')
        self._goal('Casa')
        self._goal('Aposentadoria')

        resp = self.client.get(self.GOALS_URL)

        self.assertEqual([g['name'] for g in resp.data],
                         ['Carro', 'Casa', 'Aposentadoria'])

    def test_nao_lista_cofrinho_de_outro_tenant(self):
        self._goal('Meu cofrinho')
        self._goal('Cofrinho alheio', tenant=self.OTHER_TENANT)

        resp = self.client.get(self.GOALS_URL)

        self.assertEqual([g['name'] for g in resp.data], ['Meu cofrinho'])

    def test_total_deposited_e_deposit_count_agregam_os_aportes(self):
        goal = self._goal()
        self._deposit(goal, '100.00')
        self._deposit(goal, '250.50')

        resp = self.client.get(self.GOALS_URL)

        self.assertEqual(resp.data[0]['total_deposited'], 350.5)
        self.assertEqual(resp.data[0]['deposit_count'], 2)

    def test_retirada_negativa_reduz_o_total_depositado(self):
        goal = self._goal()
        self._deposit(goal, '300.00')
        self._deposit(goal, '-100.00')

        resp = self.client.get(self.GOALS_URL)

        self.assertEqual(resp.data[0]['total_deposited'], 200.0)
        self.assertEqual(resp.data[0]['deposit_count'], 2)

    def test_total_deposited_e_zero_quando_nao_ha_aporte(self):
        self._goal()
        resp = self.client.get(self.GOALS_URL)
        self.assertEqual(resp.data[0]['total_deposited'], 0)
        self.assertEqual(resp.data[0]['deposit_count'], 0)

    def test_retrieve_de_cofrinho_de_outro_tenant_retorna_404(self):
        alheio = self._goal('Cofrinho alheio', tenant=self.OTHER_TENANT)
        resp = self.client.get(f'{self.GOALS_URL}{alheio.id}/')
        self.assertEqual(resp.status_code, 404)


# ---------------------------------------------------------------------------
# SavingsGoalViewSet -- create
# ---------------------------------------------------------------------------

class SavingsGoalCreateCharacterizationTests(SavingsCharacterizationBase):

    def test_cria_cofrinho_com_defaults_de_cor_e_icone(self):
        resp = self.client.post(self.GOALS_URL, {'name': 'Viagem'}, format='json')

        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.data['name'], 'Viagem')
        self.assertEqual(resp.data['color'], '#6366f1')
        self.assertEqual(resp.data['icon'], '\U0001F437')
        self.assertIsNone(resp.data['target_amount'])
        self.assertEqual(resp.data['total_deposited'], 0)

    def test_cria_cofrinho_com_meta_cor_e_icone_informados(self):
        resp = self.client.post(self.GOALS_URL, {
            'name': 'Carro', 'target_amount': '15000.00',
            'color': '#ff0000', 'icon': '\U0001F697',
        }, format='json')

        self.assertEqual(resp.status_code, 201)
        self.assertEqual(Decimal(resp.data['target_amount']), Decimal('15000.00'))
        self.assertEqual(resp.data['color'], '#ff0000')

    def test_cofrinho_criado_recebe_o_tenant_do_usuario_autenticado(self):
        self.client.post(self.GOALS_URL, {'name': 'Viagem'}, format='json')
        goal = SavingsGoal.objects.get(name='Viagem')
        self.assertEqual(goal.tenant_id, self.TENANT)

    def test_COMPORTAMENTO_ATUAL_tenant_id_enviado_no_payload_e_ignorado(self):
        """O input serializer nao declara `tenant_id`, entao o campo e descartado."""
        resp = self.client.post(self.GOALS_URL, {
            'name': 'Injecao', 'tenant_id': self.OTHER_TENANT,
        }, format='json')

        self.assertEqual(resp.status_code, 201)
        self.assertEqual(SavingsGoal.objects.get(name='Injecao').tenant_id, self.TENANT)

    def test_nome_obrigatorio_retorna_400(self):
        resp = self.client.post(self.GOALS_URL, {}, format='json')
        self.assertEqual(resp.status_code, 400)
        self.assertIn('name', resp.data)

    def test_nome_vazio_retorna_400(self):
        resp = self.client.post(self.GOALS_URL, {'name': ''}, format='json')
        self.assertEqual(resp.status_code, 400)

    def test_nome_acima_de_120_caracteres_retorna_400(self):
        resp = self.client.post(self.GOALS_URL, {'name': 'x' * 121}, format='json')
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(SavingsGoal.objects.count(), 0)

    def test_target_amount_invalido_retorna_400(self):
        resp = self.client.post(self.GOALS_URL,
                                {'name': 'Viagem', 'target_amount': 'abc'},
                                format='json')
        self.assertEqual(resp.status_code, 400)
        self.assertIn('target_amount', resp.data)

    def test_target_amount_nulo_e_aceito_como_sem_meta(self):
        resp = self.client.post(self.GOALS_URL,
                                {'name': 'Sem meta', 'target_amount': None},
                                format='json')
        self.assertEqual(resp.status_code, 201)
        self.assertIsNone(SavingsGoal.objects.get(name='Sem meta').target_amount)

    def test_COMPORTAMENTO_ATUAL_target_amount_negativo_e_aceito(self):
        """Nao ha validacao de meta negativa hoje -- gravado para nao mudar por acidente."""
        resp = self.client.post(self.GOALS_URL,
                                {'name': 'Meta negativa', 'target_amount': '-50.00'},
                                format='json')
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(
            SavingsGoal.objects.get(name='Meta negativa').target_amount,
            Decimal('-50.00'),
        )


# ---------------------------------------------------------------------------
# SavingsGoalViewSet -- update / destroy
# ---------------------------------------------------------------------------

class SavingsGoalUpdateDeleteCharacterizationTests(SavingsCharacterizationBase):

    def test_patch_altera_nome_do_cofrinho(self):
        goal = self._goal('Antigo')

        resp = self.client.patch(f'{self.GOALS_URL}{goal.id}/',
                                 {'name': 'Novo'}, format='json')

        self.assertEqual(resp.status_code, 200)
        goal.refresh_from_db()
        self.assertEqual(goal.name, 'Novo')

    def test_patch_em_cofrinho_de_outro_tenant_retorna_404(self):
        alheio = self._goal('Alheio', tenant=self.OTHER_TENANT)

        resp = self.client.patch(f'{self.GOALS_URL}{alheio.id}/',
                                 {'name': 'Sequestrado'}, format='json')

        self.assertEqual(resp.status_code, 404)
        alheio.refresh_from_db()
        self.assertEqual(alheio.name, 'Alheio')

    def test_put_exige_nome(self):
        goal = self._goal()
        resp = self.client.put(f'{self.GOALS_URL}{goal.id}/', {}, format='json')
        self.assertEqual(resp.status_code, 400)

    def test_delete_remove_o_cofrinho_e_retorna_204(self):
        goal = self._goal()
        resp = self.client.delete(f'{self.GOALS_URL}{goal.id}/')
        self.assertEqual(resp.status_code, 204)
        self.assertFalse(SavingsGoal.objects.filter(id=goal.id).exists())

    def test_delete_apaga_os_aportes_em_cascata(self):
        goal = self._goal()
        self._deposit(goal, '100.00')

        self.client.delete(f'{self.GOALS_URL}{goal.id}/')

        self.assertEqual(SavingsDeposit.objects.count(), 0)

    def test_COMPORTAMENTO_ATUAL_delete_de_outro_tenant_retorna_404_e_nao_403(self):
        """
        `destroy` tem uma checagem explicita que devolveria 403, mas ela e codigo
        morto: `get_object()` ja filtra por tenant no queryset e levanta 404 antes.
        """
        alheio = self._goal('Alheio', tenant=self.OTHER_TENANT)

        resp = self.client.delete(f'{self.GOALS_URL}{alheio.id}/')

        self.assertEqual(resp.status_code, 404)
        self.assertTrue(SavingsGoal.objects.filter(id=alheio.id).exists())


# ---------------------------------------------------------------------------
# SavingsGoalViewSet -- @action summary
# ---------------------------------------------------------------------------

class SavingsSummaryCharacterizationTests(SavingsCharacterizationBase):

    SUMMARY_URL = '/api/savings/goals/summary/'

    def test_contrato_de_chaves_da_resposta(self):
        resp = self.client.get(self.SUMMARY_URL)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(set(resp.data.keys()),
                         {'goals', 'grand_total', 'monthly_breakdown'})

    def test_resumo_vazio_retorna_total_zero_e_breakdown_vazio(self):
        resp = self.client.get(self.SUMMARY_URL)
        self.assertEqual(list(resp.data['goals']), [])
        self.assertEqual(resp.data['grand_total'], 0)
        self.assertEqual(resp.data['monthly_breakdown'], [])

    def test_grand_total_soma_todos_os_cofrinhos_do_tenant(self):
        a = self._goal('Viagem')
        b = self._goal('Carro')
        self._deposit(a, '100.00')
        self._deposit(b, '250.50')

        resp = self.client.get(self.SUMMARY_URL)

        self.assertEqual(resp.data['grand_total'], 350.5)
        self.assertEqual(len(resp.data['goals']), 2)

    def test_grand_total_ignora_aportes_de_outro_tenant(self):
        meu = self._goal('Viagem')
        self._deposit(meu, '100.00')
        alheio = self._goal('Alheio', tenant=self.OTHER_TENANT)
        self._deposit(alheio, '999.00')

        resp = self.client.get(self.SUMMARY_URL)

        self.assertEqual(resp.data['grand_total'], 100.0)
        self.assertEqual([g['name'] for g in resp.data['goals']], ['Viagem'])

    def test_monthly_breakdown_agrupa_por_mes_com_nome_em_portugues(self):
        goal = self._goal()
        self._deposit(goal, '100.00', date(2026, 3, 5))
        self._deposit(goal, '50.00', date(2026, 3, 20))

        resp = self.client.get(self.SUMMARY_URL)
        linha = resp.data['monthly_breakdown'][0]

        self.assertEqual(len(resp.data['monthly_breakdown']), 1)
        self.assertEqual(linha['year'], 2026)
        self.assertEqual(linha['month'], 3)
        self.assertEqual(linha['month_name'], 'Mar\u00e7o')
        self.assertEqual(linha['total'], 150.0)
        self.assertEqual(linha['accumulated'], 150.0)

    def test_monthly_breakdown_ordenado_cronologicamente_e_acumulado(self):
        goal = self._goal()
        self._deposit(goal, '50.00', date(2026, 2, 1))
        self._deposit(goal, '100.00', date(2026, 1, 15))
        self._deposit(goal, '25.00', date(2025, 12, 31))

        resp = self.client.get(self.SUMMARY_URL)
        linhas = resp.data['monthly_breakdown']

        self.assertEqual([(l['year'], l['month']) for l in linhas],
                         [(2025, 12), (2026, 1), (2026, 2)])
        self.assertEqual([l['total'] for l in linhas], [25.0, 100.0, 50.0])
        self.assertEqual([l['accumulated'] for l in linhas], [25.0, 125.0, 175.0])

    def test_retirada_negativa_reduz_o_acumulado(self):
        goal = self._goal()
        self._deposit(goal, '100.00', date(2026, 1, 10))
        self._deposit(goal, '-30.00', date(2026, 2, 10))

        resp = self.client.get(self.SUMMARY_URL)
        linhas = resp.data['monthly_breakdown']

        self.assertEqual([l['total'] for l in linhas], [100.0, -30.0])
        self.assertEqual([l['accumulated'] for l in linhas], [100.0, 70.0])
        self.assertEqual(resp.data['grand_total'], 70.0)


# ---------------------------------------------------------------------------
# SavingsDepositViewSet -- list
# ---------------------------------------------------------------------------

class SavingsDepositListCharacterizationTests(SavingsCharacterizationBase):

    def test_contrato_de_chaves_do_serializer(self):
        goal = self._goal()
        self._deposit(goal)

        resp = self.client.get(self.DEPOSITS_URL)

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(
            set(resp.data[0].keys()),
            {'id', 'goal', 'goal_name', 'amount', 'date', 'description', 'created_at'},
        )
        self.assertEqual(resp.data[0]['goal_name'], goal.name)

    def test_nao_lista_aporte_de_outro_tenant(self):
        meu = self._goal('Viagem')
        self._deposit(meu, '100.00', description='meu aporte')
        alheio = self._goal('Alheio', tenant=self.OTHER_TENANT)
        self._deposit(alheio, '999.00', description='aporte alheio')

        resp = self.client.get(self.DEPOSITS_URL)

        self.assertEqual([d['description'] for d in resp.data], ['meu aporte'])

    def test_ordena_por_data_decrescente_e_depois_id_decrescente(self):
        goal = self._goal()
        antigo = self._deposit(goal, '10.00', date(2026, 1, 1))
        mesmo_dia_1 = self._deposit(goal, '20.00', date(2026, 5, 1))
        mesmo_dia_2 = self._deposit(goal, '30.00', date(2026, 5, 1))

        resp = self.client.get(self.DEPOSITS_URL)

        self.assertEqual([d['id'] for d in resp.data],
                         [mesmo_dia_2.id, mesmo_dia_1.id, antigo.id])

    def test_filtra_por_cofrinho_via_query_param_goal(self):
        a = self._goal('Viagem')
        b = self._goal('Carro')
        self._deposit(a, '100.00', description='da viagem')
        self._deposit(b, '200.00', description='do carro')

        resp = self.client.get(f'{self.DEPOSITS_URL}?goal={a.id}')

        self.assertEqual([d['description'] for d in resp.data], ['da viagem'])

    def test_filtro_por_cofrinho_de_outro_tenant_retorna_vazio(self):
        alheio = self._goal('Alheio', tenant=self.OTHER_TENANT)
        self._deposit(alheio, '999.00')

        resp = self.client.get(f'{self.DEPOSITS_URL}?goal={alheio.id}')

        self.assertEqual(list(resp.data), [])

    def test_retrieve_de_aporte_de_outro_tenant_retorna_404(self):
        alheio = self._goal('Alheio', tenant=self.OTHER_TENANT)
        deposito = self._deposit(alheio, '999.00')

        resp = self.client.get(f'{self.DEPOSITS_URL}{deposito.id}/')

        self.assertEqual(resp.status_code, 404)


# ---------------------------------------------------------------------------
# SavingsDepositViewSet -- create
# ---------------------------------------------------------------------------

class SavingsDepositCreateCharacterizationTests(SavingsCharacterizationBase):

    def test_cria_aporte_positivo(self):
        goal = self._goal()

        resp = self.client.post(self.DEPOSITS_URL, {
            'goal_id': goal.id, 'amount': '150.00',
            'date': '2026-03-10', 'description': 'Salario',
        }, format='json')

        self.assertEqual(resp.status_code, 201)
        self.assertEqual(Decimal(resp.data['amount']), Decimal('150.00'))
        self.assertEqual(resp.data['goal'], goal.id)
        self.assertEqual(resp.data['goal_name'], goal.name)
        self.assertEqual(resp.data['date'], '2026-03-10')

    def test_aporte_criado_recebe_o_tenant_do_usuario_autenticado(self):
        goal = self._goal()

        self.client.post(self.DEPOSITS_URL, {
            'goal_id': goal.id, 'amount': '150.00', 'date': '2026-03-10',
        }, format='json')

        self.assertEqual(SavingsDeposit.objects.get().tenant_id, self.TENANT)

    def test_valor_negativo_e_aceito_como_retirada(self):
        goal = self._goal()

        resp = self.client.post(self.DEPOSITS_URL, {
            'goal_id': goal.id, 'amount': '-40.00', 'date': '2026-03-10',
        }, format='json')

        self.assertEqual(resp.status_code, 201)
        self.assertEqual(SavingsDeposit.objects.get().amount, Decimal('-40.00'))

    def test_valor_zero_e_rejeitado_com_mensagem_especifica(self):
        goal = self._goal()

        resp = self.client.post(self.DEPOSITS_URL, {
            'goal_id': goal.id, 'amount': '0', 'date': '2026-03-10',
        }, format='json')

        self.assertEqual(resp.status_code, 400)
        self.assertEqual([str(m) for m in resp.data['amount']],
                         ['Valor n\u00e3o pode ser zero.'])
        self.assertEqual(SavingsDeposit.objects.count(), 0)

    def test_descricao_e_opcional_e_default_string_vazia(self):
        goal = self._goal()

        resp = self.client.post(self.DEPOSITS_URL, {
            'goal_id': goal.id, 'amount': '10.00', 'date': '2026-03-10',
        }, format='json')

        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.data['description'], '')

    def test_campos_obrigatorios_ausentes_retornam_400(self):
        resp = self.client.post(self.DEPOSITS_URL, {}, format='json')

        self.assertEqual(resp.status_code, 400)
        self.assertEqual(set(resp.data.keys()), {'goal_id', 'amount', 'date'})

    def test_data_invalida_retorna_400(self):
        goal = self._goal()

        resp = self.client.post(self.DEPOSITS_URL, {
            'goal_id': goal.id, 'amount': '10.00', 'date': '30/02/2026',
        }, format='json')

        self.assertEqual(resp.status_code, 400)
        self.assertIn('date', resp.data)

    def test_cofrinho_inexistente_retorna_404_com_detalhe(self):
        resp = self.client.post(self.DEPOSITS_URL, {
            'goal_id': 999999, 'amount': '10.00', 'date': '2026-03-10',
        }, format='json')

        self.assertEqual(resp.status_code, 404)
        self.assertEqual(resp.data['detail'], 'Cofrinho n\u00e3o encontrado.')

    def test_aporte_em_cofrinho_de_outro_tenant_retorna_404(self):
        alheio = self._goal('Alheio', tenant=self.OTHER_TENANT)

        resp = self.client.post(self.DEPOSITS_URL, {
            'goal_id': alheio.id, 'amount': '10.00', 'date': '2026-03-10',
        }, format='json')

        self.assertEqual(resp.status_code, 404)
        self.assertEqual(resp.data['detail'], 'Cofrinho n\u00e3o encontrado.')
        self.assertEqual(SavingsDeposit.objects.count(), 0)


# ---------------------------------------------------------------------------
# SavingsDepositViewSet -- update / destroy
# ---------------------------------------------------------------------------

class SavingsDepositUpdateDeleteCharacterizationTests(SavingsCharacterizationBase):

    def test_patch_altera_valor_do_aporte(self):
        goal = self._goal()
        deposito = self._deposit(goal, '100.00')

        resp = self.client.patch(f'{self.DEPOSITS_URL}{deposito.id}/',
                                 {'amount': '175.00'}, format='json')

        self.assertEqual(resp.status_code, 200)
        deposito.refresh_from_db()
        self.assertEqual(deposito.amount, Decimal('175.00'))

    def test_COMPORTAMENTO_ATUAL_patch_aceita_valor_zero(self):
        """
        `update` usa o ModelSerializer, que NAO tem a regra `validate_amount`
        do serializer de entrada -- entao 0 passa no PATCH mas nao no POST.
        """
        goal = self._goal()
        deposito = self._deposit(goal, '100.00')

        resp = self.client.patch(f'{self.DEPOSITS_URL}{deposito.id}/',
                                 {'amount': '0.00'}, format='json')

        self.assertEqual(resp.status_code, 200)
        deposito.refresh_from_db()
        self.assertEqual(deposito.amount, Decimal('0.00'))

    def test_patch_nao_permite_apontar_para_cofrinho_de_outro_tenant(self):
        """
        O campo `goal` do serializer e restrito aos cofrinhos do tenant
        autenticado, entao apontar para cofrinho alheio e rejeitado com 400
        e o aporte permanece no cofrinho original.
        """
        meu = self._goal('Viagem')
        alheio = self._goal('Alheio', tenant=self.OTHER_TENANT)
        deposito = self._deposit(meu, '100.00')

        resp = self.client.patch(f'{self.DEPOSITS_URL}{deposito.id}/',
                                 {'goal': alheio.id}, format='json')

        self.assertEqual(resp.status_code, 400)
        self.assertIn('goal', resp.data)
        deposito.refresh_from_db()
        self.assertEqual(deposito.goal_id, meu.id)
        self.assertEqual(deposito.tenant_id, self.TENANT)

    def test_patch_permite_mover_aporte_entre_cofrinhos_do_proprio_tenant(self):
        """Movimentacao legitima entre cofrinhos proprios continua funcionando."""
        origem = self._goal('Viagem')
        destino = self._goal('Reserva')
        deposito = self._deposit(origem, '100.00')

        resp = self.client.patch(f'{self.DEPOSITS_URL}{deposito.id}/',
                                 {'goal': destino.id}, format='json')

        self.assertEqual(resp.status_code, 200)
        deposito.refresh_from_db()
        self.assertEqual(deposito.goal_id, destino.id)

    def test_patch_em_aporte_de_outro_tenant_retorna_404(self):
        alheio = self._goal('Alheio', tenant=self.OTHER_TENANT)
        deposito = self._deposit(alheio, '999.00')

        resp = self.client.patch(f'{self.DEPOSITS_URL}{deposito.id}/',
                                 {'amount': '1.00'}, format='json')

        self.assertEqual(resp.status_code, 404)
        deposito.refresh_from_db()
        self.assertEqual(deposito.amount, Decimal('999.00'))

    def test_delete_remove_o_aporte_e_retorna_204(self):
        goal = self._goal()
        deposito = self._deposit(goal, '100.00')

        resp = self.client.delete(f'{self.DEPOSITS_URL}{deposito.id}/')

        self.assertEqual(resp.status_code, 204)
        self.assertEqual(SavingsDeposit.objects.count(), 0)

    def test_delete_do_aporte_nao_remove_o_cofrinho(self):
        goal = self._goal()
        deposito = self._deposit(goal, '100.00')

        self.client.delete(f'{self.DEPOSITS_URL}{deposito.id}/')

        self.assertTrue(SavingsGoal.objects.filter(id=goal.id).exists())

    def test_COMPORTAMENTO_ATUAL_delete_de_outro_tenant_retorna_404_e_nao_403(self):
        """Mesma situacao de SavingsGoalViewSet.destroy: o 403 e codigo morto."""
        alheio = self._goal('Alheio', tenant=self.OTHER_TENANT)
        deposito = self._deposit(alheio, '999.00')

        resp = self.client.delete(f'{self.DEPOSITS_URL}{deposito.id}/')

        self.assertEqual(resp.status_code, 404)
        self.assertTrue(SavingsDeposit.objects.filter(id=deposito.id).exists())


# ---------------------------------------------------------------------------
# Autenticacao
# ---------------------------------------------------------------------------

class SavingsAuthCharacterizationTests(SavingsCharacterizationBase):

    def test_COMPORTAMENTO_ATUAL_endpoints_sem_token_retornam_403_e_nao_401(self):
        """
        `KeycloakAuthentication.authenticate` devolve None quando nao ha header
        `Authorization`, e a classe nao implementa `authenticate_header` -- entao
        o DRF responde 403 (sem challenge) em vez de 401.
        """
        anonimo = APIClient()

        for url in (self.GOALS_URL, self.DEPOSITS_URL, '/api/savings/goals/summary/'):
            with self.subTest(url=url):
                self.assertEqual(anonimo.get(url).status_code, 403)

    def test_endpoints_de_escrita_tambem_sao_protegidos(self):
        anonimo = APIClient()

        resp = anonimo.post(self.GOALS_URL, {'name': 'Invasor'}, format='json')

        self.assertEqual(resp.status_code, 403)
        self.assertEqual(SavingsGoal.objects.count(), 0)
