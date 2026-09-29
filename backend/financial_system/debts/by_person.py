"""
Aba "Por pessoa" de um grupo compartilhado: quanto cada membro deve, por fatura.

Duas visões:
  - closed: faturas que FECHARAM no mês selecionado (uma linha por cartão de
    cada membro) + gastos em dinheiro do mês. É o que pode ser cobrado.
  - open:   faturas ainda abertas de cada cartão (previsão; sem acerto).

Só entram lançamentos com `date` dentro de [period_start, period_end] da
fatura correspondente — o mesmo range usado na tela do cartão.
"""
import calendar
from datetime import date
from decimal import Decimal

from rest_framework import status
from rest_framework.response import Response

from cards.behaviors import _compute_invoice_period, _current_invoice_month
from cards.models import CreditCard
from catalog.constants import _MONTH_NAMES
from debts.behaviors import BalancesBehavior
from financial_system.money import round2 as _round2, to_float as _f
from debts.models import SharedDebt, SharedEntry

_SHORT_MONTHS = ['', 'Jan', 'Fev', 'Mar', 'Abr', 'Mai', 'Jun', 'Jul', 'Ago', 'Set', 'Out', 'Nov', 'Dez']


def _next_month(month, year):
    return (1, year + 1) if month == 12 else (month + 1, year)



class ByPersonBehavior:
    """GET /api/debts/shared-debts/{id}/by-person/?mode=closed|open&month=&year="""

    def __init__(self, shared_debt: SharedDebt, mode: str, month: int | None, year: int | None,
                 today: date | None = None):
        self.shared_debt = shared_debt
        self.mode = 'open' if mode == 'open' else 'closed'
        self.today = today or date.today()
        self.month = month or self.today.month
        self.year = year or self.today.year

    # ── helpers ────────────────────────────────────────────────────────────
    def _shares(self, entry, member_ids):
        """{member_id: parte} — rateio igual entre participantes (ou todos)."""
        participants = [p.member_id for p in entry.participants.all()] or list(member_ids)
        part = Decimal(entry.amount) / Decimal(len(participants))
        return {mid: part for mid in participants}

    def _entry_payload(self, entry, shares):
        return {
            'id': entry.id,
            'description': entry.description,
            'date': entry.date.isoformat(),
            'amount': _f(entry.amount),
            'paid_by': entry.paid_by_id,
            'paid_by_name': entry.paid_by.display_name,
            'participant_ids': list(shares.keys()),
            'shares': {mid: _f(v) for mid, v in shares.items()},
            'installment_number': entry.installment_number,
            'total_installments': entry.total_installments,
        }

    def _block(self, entries, member_ids, payer_id, **meta):
        shares_total = {mid: Decimal('0') for mid in member_ids}
        total = Decimal('0')
        rows = []
        for e in entries:
            shares = self._shares(e, member_ids)
            total += Decimal(e.amount)
            for mid, v in shares.items():
                shares_total[mid] = shares_total.get(mid, Decimal('0')) + v
            rows.append(self._entry_payload(e, shares))
        return {
            **meta,
            'payer_member_id': payer_id,
            'total': _f(total),
            'shares': {mid: _f(v) for mid, v in shares_total.items()},
            'entries': rows,
        }, total, shares_total

    def _invoice_for(self, card):
        """(inv_month, inv_year, start, end, due, is_closed) da fatura relevante ao modo."""
        if self.mode == 'open':
            inv_month, inv_year = _current_invoice_month(card)
        else:
            # A fatura que FECHA no mês M é a fatura nomeada M+1.
            inv_month, inv_year = _next_month(self.month, self.year)
        start, end, due = _compute_invoice_period(card, inv_month, inv_year)
        return inv_month, inv_year, start, end, due, end < self.today

    # ── run ────────────────────────────────────────────────────────────────
    def run(self) -> Response:
        members = list(self.shared_debt.members.all().order_by('id'))
        members_by_id = {m.id: m for m in members}
        member_ids = [m.id for m in members]
        member_by_tenant = {m.tenant_id: m for m in members if m.tenant_id}

        base_qs = (
            SharedEntry.objects
            .filter(shared_debt=self.shared_debt)
            .select_related('paid_by', 'credit_card')
            .prefetch_related('participants')
        )

        # Cartões dos membros já usados neste grupo (evita listar cartão nunca usado).
        used_card_ids = set(base_qs.exclude(credit_card=None).values_list('credit_card_id', flat=True))
        cards = list(
            CreditCard.objects
            .filter(id__in=used_card_ids, tenant_id__in=member_by_tenant.keys())
            .order_by('tenant_id', 'id')
        )

        blocks = []
        share = {mid: Decimal('0') for mid in member_ids}
        paid = {mid: Decimal('0') for mid in member_ids}
        outside_count, outside_total = 0, Decimal('0')
        next_closing = None

        for card in cards:
            owner = member_by_tenant[card.tenant_id]
            inv_month, inv_year, start, end, due, is_closed = self._invoice_for(card)
            if self.mode == 'closed' and not is_closed:
                continue
            entries = list(base_qs.filter(credit_card=card, date__gte=start, date__lte=end).order_by('date', 'id'))
            if self.mode == 'closed' and not entries:
                continue
            block, total, shares_total = self._block(
                entries, member_ids, owner.id,
                kind='card', card_id=card.id, card_name=card.name, last_four_digits=card.last_four_digits,
                owner_member_id=owner.id, owner_name=owner.display_name,
                invoice_month=inv_month, invoice_year=inv_year,
                invoice_name=f'{_SHORT_MONTHS[inv_month]}/{inv_year}',
                period_start=start.isoformat(), period_end=end.isoformat(), due_date=due.isoformat(),
                status='closed' if is_closed else 'open',
                days_to_close=(end - self.today).days,
            )
            blocks.append(block)
            paid[owner.id] += total
            for mid, v in shares_total.items():
                share[mid] += v
            if self.mode == 'open' and (next_closing is None or end < next_closing[1]):
                next_closing = (card, end)

            if self.mode == 'closed':
                # O que já está na fatura ABERTA deste cartão fica fora desta conta.
                o_month, o_year = _current_invoice_month(card)
                o_start, o_end, _ = _compute_invoice_period(card, o_month, o_year)
                if o_start > end:
                    open_qs = base_qs.filter(credit_card=card, date__gte=o_start, date__lte=o_end)
                    outside_count += open_qs.count()
                    outside_total += sum((Decimal(e.amount) for e in open_qs), Decimal('0'))

        if self.mode == 'closed':
            # Dinheiro / sem cartão cadastrado: conta no mês em que foi pago.
            _, last_day = calendar.monthrange(self.year, self.month)
            cash_entries = list(
                base_qs.filter(credit_card=None, date__gte=date(self.year, self.month, 1),
                               date__lte=date(self.year, self.month, last_day))
                .order_by('date', 'id')
            )
            if cash_entries:
                block, total, shares_total = self._block(cash_entries, member_ids, None, kind='cash', status='closed')
                blocks.append(block)
                for e in cash_entries:
                    paid[e.paid_by_id] = paid.get(e.paid_by_id, Decimal('0')) + Decimal(e.amount)
                for mid, v in shares_total.items():
                    share[mid] += v

        balance = {mid: _round2(paid[mid] - share[mid]) for mid in member_ids}
        settlement = BalancesBehavior._settlement(dict(balance), members_by_id)

        payload = {
            'mode': self.mode,
            'month': self.month,
            'year': self.year,
            'month_name': f'{_MONTH_NAMES[self.month]} {self.year}',
            'today': self.today.isoformat(),
            'members': [
                {'id': m.id, 'display_name': m.display_name, 'tenant_id': m.tenant_id}
                for m in members
            ],
            'blocks': blocks,
            'totals': {
                'grand_total': _f(sum(share.values(), Decimal('0'))),
                'share': {mid: _f(v) for mid, v in share.items()},
                'paid': {mid: _f(v) for mid, v in paid.items()},
                'balance': {mid: float(v) for mid, v in balance.items()},
            },
            'settlement': settlement,
        }
        if self.mode == 'closed':
            payload['outside'] = {'count': outside_count, 'total': _f(outside_total)}
        else:
            payload['next_closing'] = (
                {'card_name': next_closing[0].name, 'last_four_digits': next_closing[0].last_four_digits,
                 'date': next_closing[1].isoformat()}
                if next_closing else None
            )
        return Response(payload, status=status.HTTP_200_OK)