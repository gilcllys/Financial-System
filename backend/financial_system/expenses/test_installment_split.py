"""
Testes do rateio de parcelas (_split_installments).

O contrato documentado da funcao e: "os centavos residuais sao distribuidos
nas primeiras parcelas, garantindo que a soma das parcelas seja exatamente
igual ao total". Isso valia apenas para valores positivos.

Como despesa em Expense.amount e sempre NEGATIVA, todo parcelamento real
caia no ramo quebrado: ROUND_DOWN trunca em direcao ao zero e o laco de
distribuicao (range de um residual negativo) nunca executa. O resultado era
uma serie que somava menos que a compra.
"""
from decimal import Decimal

from django.test import TestCase

from expenses.behaviors import _split_installments


class SplitInstallmentsTest(TestCase):
    def test_soma_das_parcelas_bate_com_o_total_negativo(self):
        """Despesa parcelada: 1853,00 em 3x nao pode perder centavos."""
        parcelas = _split_installments(Decimal("-1853.00"), 3)

        self.assertEqual(sum(parcelas), Decimal("-1853.00"))

    def test_residual_negativo_vai_para_as_primeiras_parcelas(self):
        parcelas = _split_installments(Decimal("-1853.00"), 3)

        self.assertEqual(
            parcelas, [Decimal("-617.67"), Decimal("-617.67"), Decimal("-617.66")]
        )

    def test_duas_parcelas_com_residual_negativo(self):
        parcelas = _split_installments(Decimal("-192.31"), 2)

        self.assertEqual(parcelas, [Decimal("-96.16"), Decimal("-96.15")])
        self.assertEqual(sum(parcelas), Decimal("-192.31"))

    def test_divisao_exata_negativa_nao_muda(self):
        parcelas = _split_installments(Decimal("-488.08"), 2)

        self.assertEqual(parcelas, [Decimal("-244.04"), Decimal("-244.04")])

    def test_cem_reais_em_tres_vezes_negativo(self):
        """Caso classico: 100,00 em 3x = 33,34 + 33,33 + 33,33."""
        parcelas = _split_installments(Decimal("-100.00"), 3)

        self.assertEqual(
            parcelas, [Decimal("-33.34"), Decimal("-33.33"), Decimal("-33.33")]
        )
        self.assertEqual(sum(parcelas), Decimal("-100.00"))

    # -- comportamento positivo preservado --------------------------------
    def test_positivo_continua_igual(self):
        self.assertEqual(
            _split_installments(Decimal("1853.00"), 3),
            [Decimal("617.67"), Decimal("617.67"), Decimal("617.66")],
        )
        self.assertEqual(
            _split_installments(Decimal("100.00"), 3),
            [Decimal("33.34"), Decimal("33.33"), Decimal("33.33")],
        )

    def test_parcela_unica_devolve_o_total(self):
        self.assertEqual(_split_installments(Decimal("-50.00"), 1), [Decimal("-50.00")])

    def test_aceita_float_e_string(self):
        self.assertEqual(sum(_split_installments(-100.00, 3)), Decimal("-100.00"))
        self.assertEqual(sum(_split_installments("-100.00", 3)), Decimal("-100.00"))
