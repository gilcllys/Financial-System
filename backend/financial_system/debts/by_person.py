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

from cards.behaviors import compute_invoice_period, current_invoice_month, shift_month
from cards.models import CreditCard
from catalog.constants import _MONTH_NAMES, SHORT_MONTH_NAMES as _SHORT_MONTHS
from debts.behaviors import BalancesBehavior
from financial_system.money import round2 as _round2, to_float as _f
from debts.models import SharedDebt, SharedEntry





class ByPersonBehavior:
    """GET /api/debts/shared-debts/{id}/by-person/?mode=closed|open&month=&year="""

    def __init__(self, shared_debt: SharedDebt, mode: str = 'closed', month: int | None = None, year: int | None = None,
                 today: date | None = None):
        self.shared_debt = shared_debt
        self.mode = 'open' if mode == 'open' else 'closed'
        self.today = today or date.today()
        self.month = month or self.today.month
        self.year = year or self.today.year

    # ── helpers ────────────────────────────────────────────────────────────
    def _shares(self, entry, member_ids):
        """{member_id: parte} — rateio igual entre participantes (ou todos)."""
        part = entry.share_per_participant()
        return {mid: part for mid in entry.participant_ids()}

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
            inv_month, inv_year = current_invoice_month(card, self.today)
        else:
            # A fatura que FECHA no mês M é a fatura nomeada M+1.
            inv_month, inv_year = shift_month(self.month, self.year, 1)
        start, end, due = compute_invoice_period(card, inv_month, inv_year)
        return inv_month, inv_year, start, end, due, end < self.today

    # ── run ────────────────────────────────────────────────────────────────
    def run(self) -> Response:
        context = self._load_context()
        self._add_card_blocks(context)
        self._add_cash_block(context)
        return self._build_response(context)

    def _load_context(self):
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
        return {
            'members': members,
            'members_by_id': members_by_id,
            'member_ids': member_ids,
            'member_by_tenant': member_by_tenant,
            'base_queryset': base_qs,
            'cards': cards,
            'blocks': [],
            'share': {mid: Decimal('0') for mid in member_ids},
            'paid': {mid: Decimal('0') for mid in member_ids},
            'outside_count': 0,
            'outside_total': Decimal('0'),
            'next_closing': None,
        }

    def _add_card_blocks(self, context):
        for card in context['cards']:
            base_qs = context['base_queryset']
            member_ids = context['member_ids']
            member_by_tenant = context['member_by_tenant']
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
            context['blocks'].append(block)
            context['paid'][owner.id] += total
            for mid, v in shares_total.items():
                context['share'][mid] += v
            if self.mode == 'open' and (
                context['next_closing'] is None or end < context['next_closing'][1]
            ):
                context['next_closing'] = (card, end)

            if self.mode == 'closed':
                # O que já está na fatura ABERTA deste cartão fica fora desta conta.
                o_month, o_year = current_invoice_month(card, self.today)
                o_start, o_end, _ = compute_invoice_period(card, o_month, o_year)
                if o_start > end:
                    open_qs = base_qs.filter(credit_card=card, date__gte=o_start, date__lte=o_end)
                    context['outside_count'] += open_qs.count()
                    context['outside_total'] += sum(
                        (Decimal(e.amount) for e in open_qs), Decimal('0'),
                    )

    def _add_cash_block(self, context):
        if self.mode == 'closed':
            # Dinheiro / sem cartão cadastrado: conta no mês em que foi pago.
            _, last_day = calendar.monthrange(self.year, self.month)
            cash_entries = list(
                context['base_queryset'].filter(
                    credit_card=None,
                    date__gte=date(self.year, self.month, 1),
                    date__lte=date(self.year, self.month, last_day),
                )
                .order_by('date', 'id')
            )
            if cash_entries:
                block, total, shares_total = self._block(
                    cash_entries, context['member_ids'], None,
                    kind='cash', status='closed',
                )
                context['blocks'].append(block)
                for e in cash_entries:
                    context['paid'][e.paid_by_id] = (
                        context['paid'].get(e.paid_by_id, Decimal('0')) + Decimal(e.amount)
                    )
                for mid, v in shares_total.items():
                    context['share'][mid] += v

    def _build_response(self, context):
        members = context['members']
        member_ids = context['member_ids']
        share = context['share']
        paid = context['paid']
        balance = {mid: _round2(paid[mid] - share[mid]) for mid in member_ids}
        settlement = BalancesBehavior._settlement(dict(balance), context['members_by_id'])

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
            'blocks': context['blocks'],
            'totals': {
                'grand_total': _f(sum(share.values(), Decimal('0'))),
                'share': {mid: _f(v) for mid, v in share.items()},
                'paid': {mid: _f(v) for mid, v in paid.items()},
                'balance': {mid: float(v) for mid, v in balance.items()},
            },
            'settlement': settlement,
        }
        if self.mode == 'closed':
            payload['outside'] = {
                'count': context['outside_count'],
                'total': _f(context['outside_total']),
            }
        else:
            payload['next_closing'] = (
                {
                    'card_name': context['next_closing'][0].name,
                    'last_four_digits': context['next_closing'][0].last_four_digits,
                    'date': context['next_closing'][1].isoformat(),
                }
                if context['next_closing'] else None
            )
        return Response(payload, status=status.HTTP_200_OK)
