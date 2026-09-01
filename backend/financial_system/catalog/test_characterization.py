"""
Testes de CARACTERIZACAO do app `catalog` (categorias de despesa).

O app nasceu sem nenhum teste. Estes testes gravam o comportamento ATUAL,
nao o ideal -- divergencias conhecidas ficam marcadas com o prefixo
`test_COMPORTAMENTO_ATUAL_`.

Particularidade deste app: existem categorias GLOBAIS com `tenant_id='system'`
(criadas pela migration 0002), visiveis para todos os tenants. Isso torna o
`get_queryset` mais permissivo que o dos outros apps e muda o significado dos
guards de escrita -- por isso a cobertura abaixo insiste nesse cenario.
"""

from django.test import TestCase
from rest_framework.test import APIClient

from catalog.models import ExpenseCategory


class CatalogCharacterizationBase(TestCase):
    TENANT = 'tenant-catalog-1'
    OTHER_TENANT = 'tenant-catalog-2'
    SYSTEM = 'system'

    URL = '/api/catalog/categories/'

    def _principal(self, sub):
        from financial_system.authentication import KeycloakPrincipal
        return KeycloakPrincipal({
            'sub': sub, 'email': f'{sub}@example.com',
            'given_name': 'Teste', 'family_name': 'Caracterizacao',
        })

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(user=self._principal(self.TENANT))
        # A migration 0002 popula categorias 'system'; os testes rodam sobre um
        # banco ja migrado, entao removemos tudo para controlar o cenario.
        ExpenseCategory.objects.all().delete()

    def _category(self, name='Mercado', tenant=None):
        return ExpenseCategory.objects.create(
            tenant_id=tenant or self.TENANT, name=name)


class CatalogListCharacterizationTests(CatalogCharacterizationBase):

    def test_lista_categorias_do_proprio_tenant(self):
        self._category('Mercado')
        resp = self.client.get(self.URL)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual([c['name'] for c in resp.data], ['Mercado'])

    def test_lista_inclui_categorias_do_sistema(self):
        self._category('Global', tenant=self.SYSTEM)
        resp = self.client.get(self.URL)
        self.assertEqual([c['name'] for c in resp.data], ['Global'])

    def test_lista_nao_inclui_categoria_de_outro_tenant(self):
        self._category('Alheia', tenant=self.OTHER_TENANT)
        resp = self.client.get(self.URL)
        self.assertEqual(list(resp.data), [])

    def test_retrieve_de_categoria_de_outro_tenant_retorna_404(self):
        alheia = self._category('Alheia', tenant=self.OTHER_TENANT)
        resp = self.client.get(f'{self.URL}{alheia.id}/')
        self.assertEqual(resp.status_code, 404)

    def test_retrieve_de_categoria_do_sistema_retorna_200(self):
        sistema = self._category('Global', tenant=self.SYSTEM)
        resp = self.client.get(f'{self.URL}{sistema.id}/')
        self.assertEqual(resp.status_code, 200)


class CatalogCreateCharacterizationTests(CatalogCharacterizationBase):

    def test_create_injeta_tenant_do_autenticado(self):
        resp = self.client.post(self.URL, {'name': 'Nova'}, format='json')
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(
            ExpenseCategory.objects.get(id=resp.data['id']).tenant_id,
            self.TENANT,
        )

    def test_tenant_id_enviado_no_payload_e_ignorado(self):
        resp = self.client.post(
            self.URL,
            {'name': 'Nova', 'tenant_id': self.OTHER_TENANT},
            format='json',
        )
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(
            ExpenseCategory.objects.get(id=resp.data['id']).tenant_id,
            self.TENANT,
        )


class CatalogUpdateCharacterizationTests(CatalogCharacterizationBase):

    def test_update_da_propria_categoria_funciona(self):
        cat = self._category('Antiga')
        resp = self.client.patch(
            f'{self.URL}{cat.id}/', {'name': 'Nova'}, format='json')
        self.assertEqual(resp.status_code, 200)
        cat.refresh_from_db()
        self.assertEqual(cat.name, 'Nova')
        self.assertEqual(cat.tenant_id, self.TENANT)

    def test_update_de_categoria_de_outro_tenant_retorna_404(self):
        alheia = self._category('Alheia', tenant=self.OTHER_TENANT)
        resp = self.client.patch(
            f'{self.URL}{alheia.id}/', {'name': 'Invadida'}, format='json')
        self.assertEqual(resp.status_code, 404)
        alheia.refresh_from_db()
        self.assertEqual(alheia.name, 'Alheia')

    def test_COMPORTAMENTO_ATUAL_update_de_categoria_do_sistema_a_sequestra(self):
        """
        DIVERGENCIA (impacto entre tenants): o PATCH numa categoria 'system'
        e aceito e o `perform_update` grava `tenant_id` do autenticado.

        A categoria global vira propriedade de quem editou e DESAPARECE para
        todos os outros tenants. O `perform_destroy` protege o delete, mas nao
        existe guarda equivalente no update.

        Teste grava o comportamento atual de proposito. Ver PR de correcao.
        """
        sistema = self._category('Global', tenant=self.SYSTEM)

        resp = self.client.patch(
            f'{self.URL}{sistema.id}/', {'name': 'Sequestrada'}, format='json')

        self.assertEqual(resp.status_code, 200)
        sistema.refresh_from_db()
        self.assertEqual(sistema.tenant_id, self.TENANT)
        self.assertEqual(sistema.name, 'Sequestrada')


class CatalogDeleteCharacterizationTests(CatalogCharacterizationBase):

    def test_delete_da_propria_categoria_funciona(self):
        cat = self._category('Descartavel')
        resp = self.client.delete(f'{self.URL}{cat.id}/')
        self.assertEqual(resp.status_code, 204)
        self.assertFalse(ExpenseCategory.objects.filter(id=cat.id).exists())

    def test_delete_de_categoria_do_sistema_retorna_403(self):
        """
        Guarda REAL (nao e codigo morto): a categoria 'system' esta dentro do
        get_queryset, entao `get_object()` a encontra e o `perform_destroy`
        precisa barrar explicitamente.
        """
        sistema = self._category('Global', tenant=self.SYSTEM)
        resp = self.client.delete(f'{self.URL}{sistema.id}/')
        self.assertEqual(resp.status_code, 403)
        self.assertTrue(ExpenseCategory.objects.filter(id=sistema.id).exists())

    def test_delete_de_categoria_de_outro_tenant_retorna_404(self):
        alheia = self._category('Alheia', tenant=self.OTHER_TENANT)
        resp = self.client.delete(f'{self.URL}{alheia.id}/')
        self.assertEqual(resp.status_code, 404)
        self.assertTrue(ExpenseCategory.objects.filter(id=alheia.id).exists())
