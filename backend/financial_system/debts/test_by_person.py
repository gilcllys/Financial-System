"""
Aba "Por pessoa": cenário do protótipo (Gil e Vitória) — cada fatura fechada
vira um bloco, só com lançamentos dentro do período; dinheiro em bloco
separado; saldo = pagou − parte; acerto entre membros.
"""
from datetime import date
from decimal import Decimal

from django.test import TestCase

from cards.models import CreditCard
from debts.by_person import ByPersonBehavior
from debts.models import SharedDebt, SharedDebtMember, SharedEntry, SharedEntryParticipant

GIL, VI = 'tenant-gil', 'tenant-vi'
TODAY = date(2026, 9, 28)


class ByPersonBehaviorTests(TestCase):
    def setUp(self):
        self.group = SharedDebt.objects.create(name='Casa', owner_tenant_id=GIL)
        self.gil = SharedDebtMember.objects.create(shared_debt=self.group, tenant_id=GIL, display_name='Gil')
        self.vi = SharedDebtMember.objects.create(shared_debt=self.group, tenant_id=VI, display_name='Vitória')
        # Fecham no dia 21 / 24 (Set/2026 => faturas Out/2026: 22/08–21/09 e 25/08–24/09)
        self.nubank = CreditCard.objects.create(tenant_id=GIL, name='Nubank', closing_day=21, due_day=25, last_four_digits='1234')
        self.inter = CreditCard.objects.create(tenant_id=VI, name='Inter', closing_day=24, due_day=5, last_four_digits='9012')

    def _entry(self, desc, amount, day, paid_by, card=None, parts=None, month=9):
        e = SharedEntry.objects.create(
            shared_debt=self.group, paid_by=paid_by, description=desc, amount=Decimal(amount),
            date=date(2026, month, day), payment_method='cartao' if card else 'dinheiro',
            credit_card=card, created_by_tenant_id=paid_by.tenant_id,
        )
        for m in (parts or [self.gil, self.vi]):
            SharedEntryParticipant.objects.create(entry=e, member=m)
        return e

    def _run(self, mode='closed', month=9, year=2026):
        return ByPersonBehavior(self.group, mode, month, year, today=TODAY).run().data

    def _block(self, data, kind, card=None):
        return next(b for b in data['blocks'] if b['kind'] == kind and (card is None or b['card_id'] == card.id))

    # ── closed ──────────────────────────────────────────────────────────────
    def test_closed_blocks_only_include_entries_inside_invoice_period(self):
        self._entry('Mercado', '200.00', 12, self.gil, self.nubank)          # dentro (22/08–21/09)
        self._entry('Fora, já na próxima', '999.00', 22, self.gil, self.nubank)  # 22/09: fatura aberta
        self._entry('Antes do período', '999.00', 21, self.gil, self.nubank, month=8)  # 21/08: fatura anterior

        data = self._run()
        nb = self._block(data, 'card', self.nubank)

        self.assertEqual(nb['period_start'], '2026-08-22')
        self.assertEqual(nb['period_end'], '2026-09-21')
        self.assertEqual(nb['status'], 'closed')
        self.assertEqual(nb['total'], 200.00)
        self.assertEqual([e['description'] for e in nb['entries']], ['Mercado'])
        self.assertEqual(data['outside'], {'count': 1, 'total': 999.00})

    def test_closed_shares_paid_balance_and_settlement(self):
        # Prototipo: Gil consome 700 / paga 820; Vitória 800 / 680 => Vitória paga 120 ao Gil
        self._entry('Supermercado', '200.00', 12, self.gil, self.nubank)
        self._entry('Farmácia', '100.00', 15, self.gil, self.nubank)
        self._entry('Passagem', '300.00', 3, self.gil, self.nubank, parts=[self.vi])
        self._entry('Luz', '100.00', 8, self.gil, self.nubank)
        self._entry('Móveis', '400.00', 2, self.vi, self.inter)
        self._entry('Jantar', '200.00', 20, self.vi, self.inter, parts=[self.gil])
        self._entry('Feira', '80.00', 14, self.vi)          # dinheiro
        self._entry('Gás', '120.00', 10, self.gil)          # dinheiro

        data = self._run()
        t = data['totals']
        g, v = self.gil.id, self.vi.id

        self.assertEqual(t['share'], {g: 700.00, v: 800.00})
        self.assertEqual(t['paid'], {g: 820.00, v: 680.00})
        self.assertEqual(t['balance'], {g: 120.00, v: -120.00})
        self.assertEqual(t['grand_total'], 1500.00)
        self.assertEqual(data['settlement'], [
            {'from_member_id': v, 'from_name': 'Vitória', 'to_member_id': g, 'to_name': 'Gil', 'amount': 120.00},
        ])
        cash = self._block(data, 'cash')
        self.assertEqual(cash['total'], 200.00)
        self.assertEqual(cash['shares'], {g: 100.00, v: 100.00})
        self.assertEqual([b['kind'] for b in data['blocks']], ['card', 'card', 'cash'])

    def test_closed_skips_card_whose_invoice_has_not_closed_yet(self):
        # Hoje 28/09: fatura que fecha em 30/09 ainda está aberta
        late = CreditCard.objects.create(tenant_id=GIL, name='Itaú', closing_day=30, due_day=10, last_four_digits='5678')
        self._entry('Ainda aberta', '50.00', 10, self.gil, late)

        data = self._run()

        self.assertEqual(data['blocks'], [])
        self.assertEqual(data['totals']['grand_total'], 0.0)

    def test_closed_cash_only_counts_selected_month(self):
        self._entry('Feira set', '80.00', 14, self.vi)
        self._entry('Feira ago', '999.00', 14, self.vi, month=8)

        cash = self._block(self._run(), 'cash')

        self.assertEqual(cash['total'], 80.00)

    # ── open ────────────────────────────────────────────────────────────────
    def test_open_shows_current_invoice_with_empty_state_and_no_cash(self):
        self._entry('Uber', '45.00', 28, self.gil, self.nubank)   # 28/09: fatura aberta 22/09–21/10
        self._entry('Mercado antigo', '200.00', 12, self.gil, self.nubank)  # já fechou: fora
        self._entry('Móveis', '400.00', 2, self.vi, self.inter)  # garante que o Inter é um cartão "usado"
        self._entry('Feira', '80.00', 14, self.vi)                # dinheiro: não aparece em open

        data = self._run(mode='open')
        nb = self._block(data, 'card', self.nubank)
        it = self._block(data, 'card', self.inter)

        self.assertEqual(nb['status'], 'open')
        self.assertEqual((nb['period_start'], nb['period_end']), ('2026-09-22', '2026-10-21'))
        self.assertEqual(nb['days_to_close'], 23)
        self.assertEqual(nb['total'], 45.00)
        self.assertEqual(it['total'], 0.0)
        self.assertEqual(it['entries'], [])
        self.assertFalse(any(b['kind'] == 'cash' for b in data['blocks']))
        self.assertEqual(data['totals']['balance'], {self.gil.id: 22.50, self.vi.id: -22.50})
        self.assertEqual(data['next_closing']['card_name'], 'Nubank')
        self.assertEqual(data['next_closing']['date'], '2026-10-21')