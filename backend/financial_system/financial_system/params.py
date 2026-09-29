"""
Leitura tolerante de query params (listagens e analytics).

Convencao do projeto: parametro ausente, vazio ou invalido e IGNORADO
(None), nunca gera 400 — as telas fazem buscas historicas com filtros
opcionais. Endpoints que precisam rejeitar entrada invalida usam um
Serializer de entrada (ex.: GenerateMonthInputSerializer) em vez disto.
"""
from datetime import date


def int_param(params, name, lo=None, hi=None, default=None):
    """int dentro de [lo, hi] ou `default` (None) se ausente/invalido/fora da faixa."""
    raw = params.get(name)
    if raw in (None, ''):
        return default
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    if (lo is not None and value < lo) or (hi is not None and value > hi):
        return default
    return value


def date_param(params, name):
    """date ISO (AAAA-MM-DD) ou None."""
    raw = params.get(name)
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except (TypeError, ValueError):
        return None


def choice_param(params, name, choices):
    """valor pertencente a `choices` (iteravel de (valor, label) ou de valores) ou None."""
    raw = params.get(name)
    if raw is None:
        return None
    valid = {c[0] if isinstance(c, (tuple, list)) else c for c in choices}
    return raw if raw in valid else None


def apply_common_filters(qs, params, model, *, category_key='category_id', card_key='credit_card_id'):
    """
    Filtros de listagem compartilhados por Expense e SharedEntry:
    month, year, payment_method, categoria, cartao, start_date, end_date.
    Nomes de categoria/cartao variam entre os endpoints (parametros nomeados).
    """
    month = int_param(params, 'month', 1, 12)
    year = int_param(params, 'year', 1)
    if month is not None:
        qs = qs.filter(date__month=month)
    if year is not None:
        qs = qs.filter(date__year=year)
    pm = choice_param(params, 'payment_method', model.PAYMENT_METHOD_CHOICES)
    if pm is not None:
        qs = qs.filter(payment_method=pm)
    category_id = int_param(params, category_key)
    if category_id is not None:
        qs = qs.filter(category_id=category_id)
    card_id = int_param(params, card_key)
    if card_id is not None:
        qs = qs.filter(credit_card_id=card_id)
    start = date_param(params, 'start_date')
    if start is not None:
        qs = qs.filter(date__gte=start)
    end = date_param(params, 'end_date')
    if end is not None:
        qs = qs.filter(date__lte=end)
    return qs
