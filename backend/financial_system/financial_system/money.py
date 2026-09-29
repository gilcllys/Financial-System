"""
Aritmetica monetaria compartilhada por expenses, debts, cards e analytics.

Tudo que envolve Decimal com 2 casas, conversao para float na API e rateio
de parcelas vive aqui — antes havia copias em expenses/behaviors.py e
debts/behaviors.py (e ~35 `round(float(x or 0), 2)` espalhados).
"""
import re
from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP

TWO_PLACES = Decimal('0.01')


def round2(value) -> Decimal:
    """Decimal com 2 casas, arredondamento comercial (HALF_UP)."""
    return Decimal(value).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def to_float(value) -> float:
    """Valor monetario para a API: None/0 -> 0.0, Decimal -> float com 2 casas."""
    if value is None:
        return 0.0
    return float(round2(Decimal(str(value))))


def split_installments(total_amount, installments: int) -> list[Decimal]:
    """
    Divide um valor total em N parcelas com 2 casas decimais.

    Os centavos residuais sao distribuidos nas primeiras parcelas, garantindo
    que a soma seja exatamente o total. Funciona sobre o valor absoluto porque
    ROUND_DOWN trunca em direcao ao zero; o sinal e reaplicado no fim.
    Ex.: 100.00 em 3 -> [33.34, 33.33, 33.33]
    """
    total = round2(Decimal(str(total_amount)))
    if installments < 2:
        return [total]
    sign = -1 if total < 0 else 1
    magnitude = abs(total)
    base = (magnitude / installments).quantize(TWO_PLACES, rounding=ROUND_DOWN)
    amounts = [base] * installments
    residual_cents = int((magnitude - base * installments) / TWO_PLACES)
    for i in range(residual_cents):
        amounts[i] += TWO_PLACES
    return [a * sign for a in amounts]


def strip_suffix(description: str, pattern: re.Pattern) -> str:
    """Remove um sufixo repetivel (ex.: de parcela) do fim da descricao."""
    if not description:
        return description
    return pattern.sub('', description).strip()
