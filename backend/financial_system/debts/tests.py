from decimal import Decimal
from types import SimpleNamespace

from django.test import SimpleTestCase, TestCase

from debts.behaviors import (
    BalancesBehavior,
    CreateSharedDebtBehavior,
    CreateSharedEntryBehavior,
    InviteBehavior,
    JoinSharedDebtBehavior,
    _round2,
)
from debts.models import (
    SharedDebt,
    SharedDebtInvite,
    SharedDebtMember,
    SharedEntry,
    SharedEntryParticipant,
)


def _make_user(tenant_id='tenant-a', first_name='Alice', last_name='A', email='alice@example.com'):
    """Lightweight KeycloakPrincipal double."""
    return SimpleNamespace(
        tenant_id=tenant_id,
        first_name=first_name,
        last_name=last_name,
        email=email,
    )


# ---------------------------------------------------------------------------
# Pure-logic tests: settlement algorithm (no DB)
# ---------------------------------------------------------------------------

class SettlementAlgorithmTests(SimpleTestCase):
    def _run(self, balances):
        members_by_id = {mid: SimpleNamespace(display_name=f'M{mid}') for mid in balances}
        bal = {mid: _round2(Decimal(str(v))) for mid, v in balances.items()}
        return BalancesBehavior._settlement(bal, members_by_id)

    def test_empty_when_all_zero(self):
        self.assertEqual(self._run({1: 0, 2: 0}), [])

    def test_simple_two_member_transfer(self):
        # Member 1 is owed 50, member 2 owes 50.
        result = self._run({1: 50, 2: -50})
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['from_member_id'], 2)
        self.assertEqual(result[0]['to_member_id'], 1)
        self.assertEqual(result[0]['amount'], 50.0)

    def test_minimal_transfers_multi_member(self):
        # 1 creditor (+100), 2 debtors (-60, -40) → exactly 2 transfers.
        result = self._run({1: 100, 2: -60, 3: -40})
        self.assertEqual(len(result), 2)
        total = sum(t['amount'] for t in result)
        self.assertAlmostEqual(total, 100.0, places=2)
        # All transfers flow into the creditor (member 1).
        self.assertTrue(all(t['to_member_id'] == 1 for t in result))

    def test_epsilon_ignores_tiny_residuals(self):
        # Sub-cent imbalance must not generate a transfer.
        self.assertEqual(self._run({1: 0.005, 2: -0.005}), [])


class RoundHelperTests(SimpleTestCase):
    def test_round2_half_up(self):
        self.assertEqual(_round2(Decimal('1.005')), Decimal('1.01'))
        self.assertEqual(_round2(Decimal('1.004')), Decimal('1.00'))


# ---------------------------------------------------------------------------
# DB-backed integration tests for behaviors
# ---------------------------------------------------------------------------

class CreateSharedDebtBehaviorTests(TestCase):
    def test_creates_group_with_owner_and_named_members(self):
        user = _make_user()
        resp = CreateSharedDebtBehavior(
            {'name': 'Trip', 'member_names': ['Bob', 'Carol']}, user
        ).run()

        self.assertEqual(resp.status_code, 201)
        group = SharedDebt.objects.get(id=resp.data['id'])
        self.assertEqual(group.owner_tenant_id, 'tenant-a')

        members = list(group.members.order_by('id'))
        self.assertEqual(len(members), 3)
        # Owner has tenant_id set, named slots do not.
        owner = members[0]
        self.assertEqual(owner.tenant_id, 'tenant-a')
        self.assertEqual(owner.display_name, 'Alice')
        self.assertIsNone(members[1].tenant_id)
        self.assertEqual({members[1].display_name, members[2].display_name}, {'Bob', 'Carol'})

    def test_owner_display_name_falls_back_to_email(self):
        user = _make_user(first_name='', email='noname@example.com')
        resp = CreateSharedDebtBehavior({'name': 'Solo'}, user).run()
        owner = SharedDebt.objects.get(id=resp.data['id']).members.first()
        self.assertEqual(owner.display_name, 'noname@example.com')


class JoinSharedDebtBehaviorTests(TestCase):
    def setUp(self):
        self.owner = _make_user(tenant_id='owner-1', first_name='Owner')
        resp = CreateSharedDebtBehavior({'name': 'Group'}, self.owner).run()
        self.group = SharedDebt.objects.get(id=resp.data['id'])

    def _invite(self, expires_at=None):
        return SharedDebtInvite.objects.create(
            shared_debt=self.group,
            expires_at=expires_at,
            created_by_tenant_id=self.owner.tenant_id,
        )

    def test_new_user_joins(self):
        invite = self._invite()
        joiner = _make_user(tenant_id='joiner-2', first_name='Joiner')
        resp = JoinSharedDebtBehavior(
            {'token': invite.token, 'display_name': ''}, joiner
        ).run()

        self.assertEqual(resp.status_code, 200)
        self.assertTrue(
            self.group.members.filter(tenant_id='joiner-2', display_name='Joiner').exists()
        )

    def test_invalid_token_returns_404(self):
        import uuid
        resp = JoinSharedDebtBehavior(
            {'token': uuid.uuid4(), 'display_name': ''}, _make_user('x')
        ).run()
        self.assertEqual(resp.status_code, 404)

    def test_expired_invite_returns_400(self):
        from django.utils import timezone
        from datetime import timedelta
        invite = self._invite(expires_at=timezone.now() - timedelta(days=1))
        resp = JoinSharedDebtBehavior(
            {'token': invite.token, 'display_name': ''}, _make_user('late-3')
        ).run()
        self.assertEqual(resp.status_code, 400)

    def test_already_member_does_not_duplicate(self):
        invite = self._invite()
        # Owner joins their own group again.
        resp = JoinSharedDebtBehavior(
            {'token': invite.token, 'display_name': ''}, self.owner
        ).run()
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(
            self.group.members.filter(tenant_id='owner-1').count(), 1
        )


class InviteBehaviorTests(TestCase):
    def test_invite_returns_token_and_join_path(self):
        owner = _make_user(tenant_id='owner-1')
        group = SharedDebt.objects.create(name='G', owner_tenant_id='owner-1')
        SharedDebtMember.objects.create(shared_debt=group, tenant_id='owner-1', display_name='O')
        resp = InviteBehavior(group, owner, {'expires_at': None}).run()
        self.assertEqual(resp.status_code, 201)
        token = resp.data['invite_token']
        self.assertTrue(SharedDebtInvite.objects.filter(token=token).exists())
        self.assertEqual(resp.data['join_path'], f'/shared-debts/join/{token}')


class CreateSharedEntryBehaviorTests(TestCase):
    def setUp(self):
        self.user = _make_user(tenant_id='owner-1')
        self.group = SharedDebt.objects.create(name='G', owner_tenant_id='owner-1')
        self.m1 = SharedDebtMember.objects.create(
            shared_debt=self.group, tenant_id='owner-1', display_name='Owner'
        )
        self.m2 = SharedDebtMember.objects.create(
            shared_debt=self.group, tenant_id=None, display_name='Bob'
        )

    def _data(self, **overrides):
        data = {
            'description': 'Dinner',
            'amount': Decimal('100.00'),
            'date': '2026-01-01',
            'paid_by': self.m1.id,
            'participant_ids': [],
            'payment_method': 'dinheiro',
            'credit_card_id': None,
        }
        data.update(overrides)
        return data

    def test_happy_path_splits_among_all(self):
        resp = CreateSharedEntryBehavior(self.group, self.user, self._data()).run()
        self.assertEqual(resp.status_code, 201)
        entry = SharedEntry.objects.get(id=resp.data['id'])
        self.assertEqual(entry.created_by_tenant_id, 'owner-1')
        self.assertEqual(
            SharedEntryParticipant.objects.filter(entry=entry).count(), 2
        )

    def test_explicit_participants(self):
        resp = CreateSharedEntryBehavior(
            self.group, self.user, self._data(participant_ids=[self.m1.id])
        ).run()
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(
            SharedEntryParticipant.objects.filter(entry_id=resp.data['id']).count(), 1
        )

    def test_paid_by_outside_group_rejected(self):
        resp = CreateSharedEntryBehavior(
            self.group, self.user, self._data(paid_by=99999)
        ).run()
        self.assertEqual(resp.status_code, 400)

    def test_participant_outside_group_rejected(self):
        resp = CreateSharedEntryBehavior(
            self.group, self.user, self._data(participant_ids=[99999])
        ).run()
        self.assertEqual(resp.status_code, 400)

    def test_credit_card_idor_guard(self):
        from cards.models import CreditCard
        # Card belongs to a DIFFERENT tenant.
        card = CreditCard.objects.create(
            tenant_id='someone-else',
            name='Nubank',
            due_date=10,
            best_purchase_date=1,
            last_four_digits='1234',
        )
        resp = CreateSharedEntryBehavior(
            self.group, self.user, self._data(credit_card_id=card.id)
        ).run()
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(SharedEntry.objects.count(), 0)


class BalancesBehaviorTests(TestCase):
    def test_end_to_end_balances_and_settlement(self):
        user = _make_user(tenant_id='owner-1')
        group = SharedDebt.objects.create(name='G', owner_tenant_id='owner-1')
        alice = SharedDebtMember.objects.create(
            shared_debt=group, tenant_id='owner-1', display_name='Alice'
        )
        bob = SharedDebtMember.objects.create(
            shared_debt=group, tenant_id=None, display_name='Bob'
        )
        # Alice paid 100, split equally → each owes 50. Bob owes Alice 50.
        CreateSharedEntryBehavior(group, user, {
            'description': 'Dinner',
            'amount': Decimal('100.00'),
            'date': '2026-01-01',
            'paid_by': alice.id,
            'participant_ids': [],
            'payment_method': 'dinheiro',
            'credit_card_id': None,
        }).run()

        resp = BalancesBehavior(group).run()
        self.assertEqual(resp.status_code, 200)
        members = {m['member_id']: m for m in resp.data['members']}
        self.assertEqual(members[alice.id]['balance'], 50.0)
        self.assertEqual(members[bob.id]['balance'], -50.0)

        settlement = resp.data['settlement']
        self.assertEqual(len(settlement), 1)
        self.assertEqual(settlement[0]['from_member_id'], bob.id)
        self.assertEqual(settlement[0]['to_member_id'], alice.id)
        self.assertEqual(settlement[0]['amount'], 50.0)


class PersonalSummaryBehaviorTests(TestCase):
    def setUp(self):
        from datetime import timedelta
        from django.utils import timezone
        from catalog.models import ExpenseCategory
        from expenses.models import Expense

        self.Expense = Expense
        self.user = _make_user(tenant_id='pers-1')
        self.today = timezone.localdate()
        self.category = ExpenseCategory.objects.first() or ExpenseCategory.objects.create(
            name='Geral'
        )

        def _mk(description, amount, date, payment_method='dinheiro'):
            return Expense.objects.create(
                tenant_id='pers-1',
                category=self.category,
                description=description,
                quantity=1,
                amount=amount,
                date=date,
                payment_method=payment_method,
            )

        # Future installment → counted in installments_remaining.
        _mk('Celular - Parcela 3/10', -100, self.today + timedelta(days=5))
        # Past installment → excluded from installments_remaining.
        _mk('Notebook - Parcela 2/6', -200, self.today - timedelta(days=5))
        # Current-month card expense → counted in card_current_month.
        _mk('Mercado', -50, self.today, payment_method='cartao')
        # Current-month dinheiro expense → excluded from card_current_month.
        _mk('Padaria', -30, self.today, payment_method='dinheiro')
        # Other tenant's data → never counted.
        Expense.objects.create(
            tenant_id='other-tenant',
            category=self.category,
            description='Outro - Parcela 1/2',
            quantity=1,
            amount=-999,
            date=self.today + timedelta(days=1),
            payment_method='cartao',
        )

    def test_personal_summary_aggregates(self):
        from debts.behaviors import PersonalSummaryBehavior

        resp = PersonalSummaryBehavior(self.user).run()
        self.assertEqual(resp.status_code, 200)

        data = resp.data
        # Only the future installment (abs 100) counts.
        self.assertEqual(data['installments_remaining']['count'], 1)
        self.assertEqual(data['installments_remaining']['total'], 100.0)
        # Only the current-month card expense (abs 50) counts.
        self.assertEqual(data['card_current_month']['count'], 1)
        self.assertEqual(data['card_current_month']['total'], 50.0)

    def test_empty_tenant_returns_zeroes(self):
        from debts.behaviors import PersonalSummaryBehavior

        resp = PersonalSummaryBehavior(_make_user(tenant_id='no-data')).run()
        self.assertEqual(resp.data, {
            'installments_remaining': {'total': 0.0, 'count': 0},
            'card_current_month': {'total': 0.0, 'count': 0},
        })
