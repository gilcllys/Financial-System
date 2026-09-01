"""
Testes de CARACTERIZACAO do app `supermarket` (compras de mercado e itens).

O app nasceu sem nenhum teste. Estes testes gravam o comportamento ATUAL,
nao o ideal -- divergencias conhecidas ficam marcadas com o prefixo
`test_COMPORTAMENTO_ATUAL_`.

Ponto sensivel coberto aqui: `SupermarketExpenseItem` aponta para um
`SupermarketExpense` pai, e o viewset valida a posse desse pai
(`_assert_parent_ownership`). Sem essa guarda seria possivel pendurar itens
na compra de outro tenant -- por isso ha teste para criacao E edicao.
"""

from datetime import date
from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APIClient

from supermarket.models import SupermarketExpense, SupermarketExpenseItem


class SupermarketCharacterizationBase(TestCase):
    TENANT = 'tenant-super-1'
    OTHER_TENANT = 'tenant-super-2'

    EXPENSES_URL = '/api/supermarket/supermarket-expenses/'
    ITEMS_URL = '/api/supermarket/supermarket-expense-items/'

    def _principal(self, sub):
        from financial_system.authentication import KeycloakPrincipal
        return KeycloakPrincipal({
            'sub': sub, 'email': f'{sub}@example.com',
            'given_name': 'Teste', 'family_name': 'Caracterizacao',
        })

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(user=self._principal(self.TENANT))

    def _expense(self, store='Mercado Bom', tenant=None, on_date=None):
        return SupermarketExpense.objects.create(
            tenant_id=tenant or self.TENANT,
            store_name=store,
            date=on_date or date(2026, 3, 10),
        )

    def _item(self, expense, description='Arroz', quantity=2,
              unit_price='10.00', tenant=None):
        return SupermarketExpenseItem.objects.create(
            tenant_id=tenant or expense.tenant_id,
            supermarket_expense=expense,
            description=description,
            quantity=quantity,
            unit_price=Decimal(unit_price),
        )


class SupermarketExpenseListCharacterizationTests(SupermarketCharacterizationBase):

    def test_lista_apenas_compras_do_proprio_tenant(self):
        self._expense('Minha')
        self._expense('Alheia', tenant=self.OTHER_TENANT)

        resp = self.client.get(self.EXPENSES_URL)

        self.assertEqual(resp.status_code, 200)
        self.assertEqual([e['store_name'] for e in resp.data], ['Minha'])

    def test_retrieve_de_compra_de_outro_tenant_retorna_404(self):
        alheia = self._expense('Alheia', tenant=self.OTHER_TENANT)
        resp = self.client.get(f'{self.EXPENSES_URL}{alheia.id}/')
        self.assertEqual(resp.status_code, 404)

    def test_total_soma_preco_unitario_vezes_quantidade(self):
        compra = self._expense()
        self._item(compra, 'Arroz', quantity=2, unit_price='10.00')
        self._item(compra, 'Feijao', quantity=3, unit_price='5.50')

        resp = self.client.get(f'{self.EXPENSES_URL}{compra.id}/')

        self.assertEqual(resp.data['total'], 36.5)
        self.assertEqual(len(resp.data['items']), 2)

    def test_total_e_zero_quando_nao_ha_itens(self):
        compra = self._expense()
        resp = self.client.get(f'{self.EXPENSES_URL}{compra.id}/')
        self.assertEqual(resp.data['total'], 0.0)


class SupermarketExpenseWriteCharacterizationTests(SupermarketCharacterizationBase):

    def test_create_injeta_tenant_do_autenticado(self):
        resp = self.client.post(
            self.EXPENSES_URL,
            {'store_name': 'Nova', 'date': '2026-03-10'},
            format='json',
        )
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(
            SupermarketExpense.objects.get(id=resp.data['id']).tenant_id,
            self.TENANT,
        )

    def test_tenant_id_enviado_no_payload_e_ignorado(self):
        resp = self.client.post(
            self.EXPENSES_URL,
            {'store_name': 'Nova', 'date': '2026-03-10',
             'tenant_id': self.OTHER_TENANT},
            format='json',
        )
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(
            SupermarketExpense.objects.get(id=resp.data['id']).tenant_id,
            self.TENANT,
        )

    def test_delete_de_compra_de_outro_tenant_retorna_404(self):
        alheia = self._expense('Alheia', tenant=self.OTHER_TENANT)
        resp = self.client.delete(f'{self.EXPENSES_URL}{alheia.id}/')
        self.assertEqual(resp.status_code, 404)
        self.assertTrue(SupermarketExpense.objects.filter(id=alheia.id).exists())

    def test_delete_da_propria_compra_remove_os_itens_em_cascata(self):
        compra = self._expense()
        self._item(compra)

        resp = self.client.delete(f'{self.EXPENSES_URL}{compra.id}/')

        self.assertEqual(resp.status_code, 204)
        self.assertFalse(
            SupermarketExpenseItem.objects.filter(
                supermarket_expense_id=compra.id).exists())


class SupermarketItemCharacterizationTests(SupermarketCharacterizationBase):

    def test_lista_apenas_itens_do_proprio_tenant(self):
        minha = self._expense()
        alheia = self._expense('Alheia', tenant=self.OTHER_TENANT)
        self._item(minha, 'Arroz')
        self._item(alheia, 'Cafe')

        resp = self.client.get(self.ITEMS_URL)

        self.assertEqual([i['description'] for i in resp.data], ['Arroz'])

    def test_create_de_item_na_propria_compra_funciona(self):
        compra = self._expense()

        resp = self.client.post(
            self.ITEMS_URL,
            {'supermarket_expense': compra.id, 'description': 'Arroz',
             'quantity': 2, 'unit_price': '10.00'},
            format='json',
        )

        self.assertEqual(resp.status_code, 201)
        self.assertEqual(
            SupermarketExpenseItem.objects.get(id=resp.data['id']).tenant_id,
            self.TENANT,
        )

    def test_create_de_item_em_compra_de_outro_tenant_retorna_403(self):
        """Guarda de IDOR: sem ela daria para pendurar item na compra alheia."""
        alheia = self._expense('Alheia', tenant=self.OTHER_TENANT)

        resp = self.client.post(
            self.ITEMS_URL,
            {'supermarket_expense': alheia.id, 'description': 'Invasor',
             'quantity': 1, 'unit_price': '1.00'},
            format='json',
        )

        self.assertEqual(resp.status_code, 403)
        self.assertFalse(
            SupermarketExpenseItem.objects.filter(description='Invasor').exists())

    def test_update_apontando_para_compra_de_outro_tenant_retorna_403(self):
        """Mesma guarda de IDOR, agora no caminho de edicao."""
        compra = self._expense()
        item = self._item(compra, 'Arroz')
        alheia = self._expense('Alheia', tenant=self.OTHER_TENANT)

        resp = self.client.patch(
            f'{self.ITEMS_URL}{item.id}/',
            {'supermarket_expense': alheia.id},
            format='json',
        )

        self.assertEqual(resp.status_code, 403)
        item.refresh_from_db()
        self.assertEqual(item.supermarket_expense_id, compra.id)

    def test_delete_de_item_de_outro_tenant_retorna_404(self):
        alheia = self._expense('Alheia', tenant=self.OTHER_TENANT)
        item = self._item(alheia, 'Cafe')

        resp = self.client.delete(f'{self.ITEMS_URL}{item.id}/')

        self.assertEqual(resp.status_code, 404)
        self.assertTrue(SupermarketExpenseItem.objects.filter(id=item.id).exists())

    def test_delete_do_proprio_item_funciona(self):
        compra = self._expense()
        item = self._item(compra)

        resp = self.client.delete(f'{self.ITEMS_URL}{item.id}/')

        self.assertEqual(resp.status_code, 204)
        self.assertFalse(SupermarketExpenseItem.objects.filter(id=item.id).exists())
