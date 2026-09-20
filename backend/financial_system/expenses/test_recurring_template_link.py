"""
Testes do vinculo Expense -> RecurringExpenseTemplate (recurring_template_id).

Antes deste vinculo a trava de duplicidade comparava a DESCRICAO da despesa
com a do template. Isso produzia tres defeitos, todos reproduzidos aqui:

  1. Falso positivo: um gasto manual com a mesma descricao fazia o gasto fixo
     nunca ser criado, e o retorno dizia "skipped" -- indistinguivel de
     "ja foi gerado".
  2. Falso negativo: renomear o template depois de gerar duplicava a despesa.
  3. Falso negativo: editar a descricao da despesa gerada duplicava.

Alem disso a origem da despesa (fixa x manual) nao era observavel pela API:
o front so conseguia adivinhar comparando textos.
"""
from datetime import date
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.test import TestCase

from cards.models import CreditCard
from catalog.models import ExpenseCategory
from expenses.behaviors import RecurringExpenseBehavior
from expenses.models import Expense, RecurringExpenseTemplate
from expenses.serializer import ExpenseSerializer


class RecurringTemplateLinkTest(TestCase):
    TENANT = "tenant-link-1"

    def setUp(self):
        self.category = ExpenseCategory.objects.create(
            tenant_id=self.TENANT, name="Assinaturas"
        )
        self.card = CreditCard.objects.create(
            tenant_id=self.TENANT, name="Itau Azul", closing_day=25, due_day=3
        )

    def _template(self, **overrides):
        data = dict(
            tenant_id=self.TENANT,
            description="Netflix",
            amount=Decimal("20.90"),
            day_of_month=3,
            payment_method="cartao",
            credit_card=self.card,
            category=self.category,
        )
        data.update(overrides)
        return RecurringExpenseTemplate.objects.create(**data)

    def _manual(self, description="Netflix", day=15, amount=Decimal("-20.90")):
        return Expense.objects.create(
            tenant_id=self.TENANT,
            category=self.category,
            description=description,
            quantity=1,
            amount=amount,
            date=date(2026, 9, day),
            payment_method="cartao",
            credit_card=self.card,
        )

    # -- vinculo ----------------------------------------------------------
    def test_despesa_gerada_aponta_para_o_template(self):
        tpl = self._template()

        RecurringExpenseBehavior(self.TENANT).generate_month(9, 2026)

        expense = Expense.objects.get(tenant_id=self.TENANT)
        self.assertEqual(expense.recurring_template_id, tpl.id)

    def test_despesa_manual_nao_aponta_para_template(self):
        self._manual()

        expense = Expense.objects.get(tenant_id=self.TENANT)
        self.assertIsNone(expense.recurring_template_id)

    # -- defeito 1: gasto manual homonimo bloqueava o gasto fixo ----------
    def test_gasto_manual_homonimo_nao_impede_a_geracao(self):
        self._template()
        self._manual()  # mesma descricao, lancado a mao

        response = RecurringExpenseBehavior(self.TENANT).generate_month(9, 2026)

        self.assertIn("Netflix", response.data["created"])
        self.assertEqual(Expense.objects.filter(tenant_id=self.TENANT).count(), 2)
        # a manual continua livre, sem vinculo
        self.assertEqual(
            Expense.objects.filter(recurring_template__isnull=True).count(), 1
        )

    # -- defeito 2: renomear o template duplicava ------------------------
    def test_renomear_template_apos_gerar_nao_duplica(self):
        tpl = self._template()
        RecurringExpenseBehavior(self.TENANT).generate_month(9, 2026)

        tpl.description = "Netflix Premium"
        tpl.save(update_fields=["description"])
        response = RecurringExpenseBehavior(self.TENANT).generate_month(9, 2026)

        self.assertEqual(Expense.objects.filter(tenant_id=self.TENANT).count(), 1)
        self.assertIn("Netflix Premium", response.data["skipped"])

    # -- defeito 3: editar a descricao da despesa duplicava --------------
    def test_editar_descricao_da_despesa_gerada_nao_duplica(self):
        self._template()
        RecurringExpenseBehavior(self.TENANT).generate_month(9, 2026)

        Expense.objects.filter(tenant_id=self.TENANT).update(description="Netflix (familia)")
        RecurringExpenseBehavior(self.TENANT).generate_month(9, 2026)

        self.assertEqual(Expense.objects.filter(tenant_id=self.TENANT).count(), 1)

    # -- a trava do banco -------------------------------------------------
    def test_banco_recusa_duas_despesas_do_mesmo_template_no_mesmo_mes(self):
        tpl = self._template()
        RecurringExpenseBehavior(self.TENANT).generate_month(9, 2026)

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Expense.objects.create(
                    tenant_id=self.TENANT,
                    category=self.category,
                    description="qualquer outra coisa",
                    quantity=1,
                    amount=Decimal("-20.90"),
                    date=date(2026, 9, 28),
                    payment_method="cartao",
                    credit_card=self.card,
                    recurring_template=tpl,
                )

    def test_banco_aceita_o_mesmo_template_em_meses_diferentes(self):
        self._template()

        RecurringExpenseBehavior(self.TENANT).generate_month(9, 2026)
        RecurringExpenseBehavior(self.TENANT).generate_month(10, 2026)

        self.assertEqual(Expense.objects.filter(tenant_id=self.TENANT).count(), 2)

    def test_constraint_nao_limita_despesas_manuais(self):
        """NULL nunca conflita: o usuario pode repetir gastos manuais a vontade."""
        self._manual(day=10)
        self._manual(day=20)

        self.assertEqual(Expense.objects.filter(tenant_id=self.TENANT).count(), 2)

    # -- historico sobrevive ao template ---------------------------------
    def test_apagar_template_preserva_a_despesa(self):
        tpl = self._template()
        RecurringExpenseBehavior(self.TENANT).generate_month(9, 2026)

        tpl.delete()

        expense = Expense.objects.get(tenant_id=self.TENANT)
        self.assertEqual(expense.amount, Decimal("-20.90"))
        self.assertIsNone(expense.recurring_template_id)

    def test_apagar_template_libera_o_mes_para_novo_template(self):
        tpl = self._template()
        RecurringExpenseBehavior(self.TENANT).generate_month(9, 2026)
        tpl.delete()

        self._template()
        RecurringExpenseBehavior(self.TENANT).generate_month(9, 2026)

        self.assertEqual(Expense.objects.filter(tenant_id=self.TENANT).count(), 2)

    # -- contrato da API --------------------------------------------------
    def test_serializer_marca_gasto_fixo_como_recurring(self):
        tpl = self._template()
        RecurringExpenseBehavior(self.TENANT).generate_month(9, 2026)

        data = ExpenseSerializer(Expense.objects.get(tenant_id=self.TENANT)).data

        self.assertTrue(data["is_recurring"])
        self.assertEqual(data["recurring_template_id"], tpl.id)

    def test_serializer_marca_gasto_manual_como_nao_recurring(self):
        self._manual()

        data = ExpenseSerializer(Expense.objects.get(tenant_id=self.TENANT)).data

        self.assertFalse(data["is_recurring"])
        self.assertIsNone(data["recurring_template_id"])

    def test_payload_do_cliente_nao_consegue_forjar_o_vinculo(self):
        """recurring_template e read-only: so o generate_month pode preencher."""
        tpl = self._template()

        serializer = ExpenseSerializer(data={
            "category_id": self.category.id,
            "description": "Tentativa",
            "quantity": 1,
            "amount": "-10.00",
            "date": "2026-09-09",
            "payment_method": "dinheiro",
            "recurring_template": tpl.id,
        })
        serializer.is_valid(raise_exception=True)

        self.assertNotIn("recurring_template", serializer.validated_data)


class RecurringTemplateTenantIsolationTest(TestCase):
    """Templates homonimos de tenants diferentes nao podem interferir."""

    A = "tenant-link-a"
    B = "tenant-link-b"

    def _setup_tenant(self, tenant, amount, day):
        category = ExpenseCategory.objects.create(tenant_id=tenant, name="Assinaturas")
        card = CreditCard.objects.create(
            tenant_id=tenant, name="Cartao", closing_day=25, due_day=3
        )
        return RecurringExpenseTemplate.objects.create(
            tenant_id=tenant,
            description="Netflix",
            amount=amount,
            day_of_month=day,
            payment_method="cartao",
            credit_card=card,
            category=category,
        )

    def test_dois_tenants_com_netflix_geram_cada_um_o_seu(self):
        tpl_a = self._setup_tenant(self.A, Decimal("44.90"), 27)
        tpl_b = self._setup_tenant(self.B, Decimal("20.90"), 3)

        RecurringExpenseBehavior(self.A).generate_month(9, 2026)
        RecurringExpenseBehavior(self.B).generate_month(9, 2026)

        self.assertEqual(
            Expense.objects.get(tenant_id=self.A).recurring_template_id, tpl_a.id
        )
        self.assertEqual(
            Expense.objects.get(tenant_id=self.B).recurring_template_id, tpl_b.id
        )
