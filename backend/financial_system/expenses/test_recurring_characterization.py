"""
Testes de caracterizacao do gasto fixo individual (RecurringExpenseTemplate).

Cobrem dois defeitos encontrados em producao:
  1. generate_month copiava o sinal cru do template. Como o serializer de
     entrada exige amount >= 0.01, o gasto fixo era materializado como
     receita (amount positivo), inflando o saldo.
  2. Template legado com payment_method='cartao' e credit_card sem valor
     gerava Expense orfa: marcada como cartao, invisivel em qualquer fatura.
"""
from datetime import date
from decimal import Decimal

from django.test import TestCase

from cards.models import CreditCard
from catalog.models import ExpenseCategory
from expenses.behaviors import RecurringExpenseBehavior
from expenses.models import Expense, RecurringExpenseTemplate


class RecurringExpenseCharacterizationTest(TestCase):
    TENANT = "tenant-recurring-1"
    OTHER_TENANT = "tenant-recurring-2"

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

    # -- bug 1: sinal -----------------------------------------------------
    def test_generate_month_materializa_gasto_fixo_como_despesa(self):
        """Template positivo deve virar Expense NEGATIVA (despesa)."""
        self._template()

        RecurringExpenseBehavior(self.TENANT).generate_month(9, 2026)

        expense = Expense.objects.get(tenant_id=self.TENANT, description="Netflix")
        self.assertEqual(expense.amount, Decimal("-20.90"))

    def test_template_ja_negativo_nao_inverte_para_receita(self):
        """amount negativo no template continua despesa (nao vira receita)."""
        self._template(amount=Decimal("-20.90"))

        RecurringExpenseBehavior(self.TENANT).generate_month(9, 2026)

        expense = Expense.objects.get(tenant_id=self.TENANT, description="Netflix")
        self.assertEqual(expense.amount, Decimal("-20.90"))

    # -- bug 2: cartao orfao ----------------------------------------------
    def test_template_cartao_sem_cartao_nao_gera_despesa_orfa(self):
        """Template legado cartao/NULL nao pode virar Expense invisivel."""
        self._template(payment_method="cartao", credit_card=None)

        response = RecurringExpenseBehavior(self.TENANT).generate_month(9, 2026)

        self.assertFalse(
            Expense.objects.filter(
                tenant_id=self.TENANT, payment_method="cartao", credit_card__isnull=True
            ).exists(),
            "gerou despesa de cartao sem cartao: invisivel em qualquer fatura",
        )
        self.assertIn("Netflix", response.data.get("skipped_invalid", []))
        self.assertNotIn("Netflix", response.data["created"])

    def test_template_dinheiro_sem_cartao_e_valido(self):
        """dinheiro sem cartao e o caso normal, nao pode ser bloqueado."""
        self._template(payment_method="dinheiro", credit_card=None)

        response = RecurringExpenseBehavior(self.TENANT).generate_month(9, 2026)

        expense = Expense.objects.get(tenant_id=self.TENANT, description="Netflix")
        self.assertEqual(expense.amount, Decimal("-20.90"))
        self.assertIsNone(expense.credit_card_id)
        self.assertIn("Netflix", response.data["created"])

    # -- comportamento preservado -----------------------------------------
    def test_preserva_cartao_categoria_e_data(self):
        self._template(day_of_month=5)

        RecurringExpenseBehavior(self.TENANT).generate_month(9, 2026)

        expense = Expense.objects.get(tenant_id=self.TENANT, description="Netflix")
        self.assertEqual(expense.credit_card_id, self.card.id)
        self.assertEqual(expense.category_id, self.category.id)
        self.assertEqual(expense.date, date(2026, 9, 5))
        self.assertEqual(expense.payment_method, "cartao")
        self.assertEqual(expense.quantity, 1)

    def test_nao_duplica_quando_ja_existe_no_mes(self):
        self._template()
        RecurringExpenseBehavior(self.TENANT).generate_month(9, 2026)

        response = RecurringExpenseBehavior(self.TENANT).generate_month(9, 2026)

        self.assertEqual(
            Expense.objects.filter(tenant_id=self.TENANT, description="Netflix").count(), 1
        )
        self.assertIn("Netflix", response.data["skipped"])

    def test_template_inativo_nao_gera(self):
        self._template(is_active=False)

        RecurringExpenseBehavior(self.TENANT).generate_month(9, 2026)

        self.assertFalse(Expense.objects.filter(tenant_id=self.TENANT).exists())

    def test_dia_29_a_31_cai_no_ultimo_dia_do_mes(self):
        self._template(day_of_month=28)
        RecurringExpenseTemplate.objects.filter(tenant_id=self.TENANT).update(day_of_month=31)

        RecurringExpenseBehavior(self.TENANT).generate_month(2, 2026)

        expense = Expense.objects.get(tenant_id=self.TENANT, description="Netflix")
        self.assertEqual(expense.date, date(2026, 2, 28))

    def test_nao_vaza_template_de_outro_tenant(self):
        self._template()

        RecurringExpenseBehavior(self.OTHER_TENANT).generate_month(9, 2026)

        self.assertFalse(Expense.objects.filter(tenant_id=self.OTHER_TENANT).exists())
