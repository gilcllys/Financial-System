"""
Testes da migration de backfill (0005_backfill_recurring_template).

O backfill e a peca de maior risco da mudanca: ele roda uma unica vez, em
producao, dentro do deploy. Se ligar duas despesas do mesmo template ao mesmo
mes, a constraint da 0006 falha e o deploy quebra no meio. Se ligar de menos,
o proximo generate_month duplica os gastos fixos do mes.

Os cenarios abaixo sao os que existem de fato no banco de producao.
"""
from datetime import date, timedelta
from decimal import Decimal
from importlib import import_module

from django.apps import apps as global_apps
from django.test import TestCase
from django.utils import timezone

from cards.models import CreditCard
from catalog.models import ExpenseCategory
from expenses.models import Expense, RecurringExpenseTemplate

# O nome do modulo comeca com digito, entao nao da para usar "import" normal.
backfill = import_module('expenses.migrations.0005_backfill_recurring_template')


class BackfillRecurringTemplateTest(TestCase):
    TENANT = "tenant-backfill"

    def setUp(self):
        self.category = ExpenseCategory.objects.create(
            tenant_id=self.TENANT, name="Assinaturas"
        )
        self.card = CreditCard.objects.create(
            tenant_id=self.TENANT, name="Itau Azul", closing_day=25, due_day=3
        )
        self.agora = timezone.now()

    def _template(self, description, amount, day, criado_em=None, tenant=None):
        tpl = RecurringExpenseTemplate.objects.create(
            tenant_id=tenant or self.TENANT,
            description=description,
            amount=Decimal(amount),
            day_of_month=day,
            payment_method="cartao",
            credit_card=self.card,
            category=self.category,
        )
        if criado_em is not None:
            RecurringExpenseTemplate.objects.filter(id=tpl.id).update(created_at=criado_em)
            tpl.refresh_from_db()
        return tpl

    def _expense(self, description, amount, quando, criado_em=None, tenant=None):
        exp = Expense.objects.create(
            tenant_id=tenant or self.TENANT,
            category=self.category,
            description=description,
            quantity=1,
            amount=Decimal(amount),
            date=quando,
            payment_method="cartao",
            credit_card=self.card,
        )
        if criado_em is not None:
            Expense.objects.filter(id=exp.id).update(created_at=criado_em)
            exp.refresh_from_db()
        return exp

    def _rodar(self):
        backfill.ligar_historico(global_apps, None)

    # -- caso simples -----------------------------------------------------
    def test_liga_uma_despesa_por_mes(self):
        tpl = self._template("Spotify", "23.90", 18, criado_em=self.agora - timedelta(days=90))
        e1 = self._expense("Spotify", "-23.90", date(2026, 8, 18))
        e2 = self._expense("Spotify", "-23.90", date(2026, 9, 18))

        self._rodar()

        e1.refresh_from_db(); e2.refresh_from_db()
        self.assertEqual(e1.recurring_template_id, tpl.id)
        self.assertEqual(e2.recurring_template_id, tpl.id)

    # -- conta variavel: o valor mudou, mas continua sendo o mesmo gasto --
    def test_liga_mesmo_quando_o_valor_diverge_do_template(self):
        """Producao: 'Conta da Vivo' template R$41,00 x despesa real R$41,90."""
        tpl = self._template("Conta da Vivo", "41.00", 1, criado_em=self.agora - timedelta(days=90))
        exp = self._expense("Conta da Vivo", "-41.90", date(2026, 8, 17))

        self._rodar()

        exp.refresh_from_db()
        self.assertEqual(exp.recurring_template_id, tpl.id)

    # -- despesa anterior ao template e manual ----------------------------
    def test_nao_liga_despesa_criada_antes_do_template_existir(self):
        """Producao: Netflix de 07/07 e anterior ao template criado em 28/08."""
        criacao_tpl = self.agora - timedelta(days=30)
        tpl = self._template("Netflix", "20.90", 3, criado_em=criacao_tpl)
        antiga = self._expense(
            "Netflix", "-20.90", date(2026, 7, 7), criado_em=criacao_tpl - timedelta(days=50)
        )
        nova = self._expense("Netflix", "-20.90", date(2026, 8, 3), criado_em=criacao_tpl)

        self._rodar()

        antiga.refresh_from_db(); nova.refresh_from_db()
        self.assertIsNone(antiga.recurring_template_id)
        self.assertEqual(nova.recurring_template_id, tpl.id)

    def test_tolera_despesa_criada_milissegundos_antes_do_template(self):
        """Ao criar um template o sistema ja materializa o mes na mesma transacao."""
        criacao_tpl = self.agora - timedelta(days=10)
        tpl = self._template("TIM", "71.00", 5, criado_em=criacao_tpl)
        exp = self._expense(
            "TIM", "-71.00", date(2026, 8, 5),
            criado_em=criacao_tpl - timedelta(milliseconds=40),
        )

        self._rodar()

        exp.refresh_from_db()
        self.assertEqual(exp.recurring_template_id, tpl.id)

    # -- a garantia que protege a constraint da 0006 ----------------------
    def test_nunca_liga_duas_despesas_ao_mesmo_template_no_mesmo_mes(self):
        tpl = self._template("Aluguel", "1800.00", 25, criado_em=self.agora - timedelta(days=90))
        certa = self._expense("Aluguel", "-1800.00", date(2026, 8, 25))
        outra = self._expense("Aluguel", "-1800.00", date(2026, 8, 3))

        self._rodar()

        certa.refresh_from_db(); outra.refresh_from_db()
        # o dia mais proximo do day_of_month vence; a outra fica manual
        self.assertEqual(certa.recurring_template_id, tpl.id)
        self.assertIsNone(outra.recurring_template_id)

    def test_desempate_prefere_valor_identico_ao_do_template(self):
        tpl = self._template("Aluguel", "1800.00", 25, criado_em=self.agora - timedelta(days=90))
        valor_certo = self._expense("Aluguel", "-1800.00", date(2026, 8, 20))
        valor_errado = self._expense("Aluguel", "-999.00", date(2026, 8, 25))

        self._rodar()

        valor_certo.refresh_from_db(); valor_errado.refresh_from_db()
        self.assertEqual(valor_certo.recurring_template_id, tpl.id)
        self.assertIsNone(valor_errado.recurring_template_id)

    # -- isolamento entre tenants ----------------------------------------
    def test_nao_liga_despesa_de_outro_tenant(self):
        outro = "tenant-backfill-2"
        ExpenseCategory.objects.create(tenant_id=outro, name="Assinaturas")
        self._template("Netflix", "20.90", 3, criado_em=self.agora - timedelta(days=90))
        alheia = self._expense("Netflix", "-20.90", date(2026, 9, 3), tenant=outro)

        self._rodar()

        alheia.refresh_from_db()
        self.assertIsNone(alheia.recurring_template_id)

    # -- idempotencia e reversao ------------------------------------------
    def test_rodar_duas_vezes_nao_muda_nada(self):
        tpl = self._template("Spotify", "23.90", 18, criado_em=self.agora - timedelta(days=90))
        exp = self._expense("Spotify", "-23.90", date(2026, 9, 18))

        self._rodar()
        self._rodar()

        exp.refresh_from_db()
        self.assertEqual(exp.recurring_template_id, tpl.id)
        self.assertEqual(Expense.objects.filter(recurring_template=tpl).count(), 1)

    def test_reversao_desfaz_todos_os_vinculos(self):
        self._template("Spotify", "23.90", 18, criado_em=self.agora - timedelta(days=90))
        exp = self._expense("Spotify", "-23.90", date(2026, 9, 18))
        self._rodar()

        backfill.desligar_historico(global_apps, None)

        exp.refresh_from_db()
        self.assertIsNone(exp.recurring_template_id)

    # -- o backfill nao pode mexer em dinheiro ----------------------------
    def test_backfill_nao_altera_valores_nem_datas(self):
        self._template("Conta da Vivo", "41.00", 1, criado_em=self.agora - timedelta(days=90))
        exp = self._expense("Conta da Vivo", "-41.90", date(2026, 8, 17))
        antes = (exp.amount, exp.date, exp.credit_card_id, exp.category_id, exp.quantity)

        self._rodar()

        exp.refresh_from_db()
        depois = (exp.amount, exp.date, exp.credit_card_id, exp.category_id, exp.quantity)
        self.assertEqual(antes, depois)

    def test_soma_do_saldo_permanece_identica(self):
        self._template("Spotify", "23.90", 18, criado_em=self.agora - timedelta(days=90))
        self._expense("Spotify", "-23.90", date(2026, 9, 18))
        self._expense("Mercado", "-150.00", date(2026, 9, 10))
        total_antes = sum(e.amount for e in Expense.objects.all())

        self._rodar()

        total_depois = sum(e.amount for e in Expense.objects.all())
        self.assertEqual(total_antes, total_depois)
        self.assertEqual(Expense.objects.count(), 2)
