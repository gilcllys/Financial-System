from decimal import Decimal
from types import SimpleNamespace

from django.test import SimpleTestCase, TestCase

from debts.behaviors import (
    BalancesBehavior,
    CreateSharedDebtBehavior,
    CreateSharedEntryBehavior,
    InviteBehavior,
    JoinSharedDebtBehavior,
    UpdateSharedEntryBehavior,
    _round2,
    _split_installments,
    _strip_installment_suffix,
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
            due_day=10,
            closing_day=1,
            last_four_digits='1234',
        )
        resp = CreateSharedEntryBehavior(
            self.group, self.user, self._data(credit_card_id=card.id)
        ).run()
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(SharedEntry.objects.count(), 0)


class SplitInstallmentsTests(SimpleTestCase):
    """Regressao: cada parcela recebia o valor CHEIO em vez da fracao."""

    def test_divides_total_across_installments(self):
        # Caso real: "Milhas Livelo" R$ 511,56 em 4x deve dar 127,89 por parcela.
        self.assertEqual(
            _split_installments(Decimal('511.56'), 4),
            [Decimal('127.89')] * 4,
        )

    def test_sum_of_installments_equals_total(self):
        for total, n in [('100.00', 3), ('0.05', 3), ('10.00', 7), ('999.99', 6)]:
            parts = _split_installments(Decimal(total), n)
            self.assertEqual(len(parts), n)
            self.assertEqual(sum(parts), Decimal(total), f'{total} em {n}x')

    def test_residual_cents_go_to_first_installments(self):
        self.assertEqual(
            _split_installments(Decimal('100.00'), 3),
            [Decimal('33.34'), Decimal('33.33'), Decimal('33.33')],
        )

    def test_single_installment_returns_full_amount(self):
        self.assertEqual(_split_installments(Decimal('127.89'), 1), [Decimal('127.89')])


class StripInstallmentSuffixTests(SimpleTestCase):
    """Regressao: descricao acumulava sufixos ao reparcelar uma parcela."""

    def test_removes_suffix(self):
        self.assertEqual(_strip_installment_suffix('Milhas Livelo (1/4)'), 'Milhas Livelo')

    def test_removes_repeated_suffixes(self):
        self.assertEqual(_strip_installment_suffix('Milhas Livelo (1/4) (1/4)'), 'Milhas Livelo')

    def test_keeps_description_without_suffix(self):
        self.assertEqual(_strip_installment_suffix('Jantar'), 'Jantar')

    def test_does_not_touch_parentheses_in_the_middle(self):
        self.assertEqual(_strip_installment_suffix('Pizza (meio a meio)'), 'Pizza (meio a meio)')


class SharedEntryInstallmentCreationTests(TestCase):
    """Parcelamento de despesa compartilhada ponta a ponta."""

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
            'description': 'Milhas Livelo',
            'amount': Decimal('511.56'),
            'date': __import__('datetime').date(2026, 8, 17),
            'paid_by': self.m1.id,
            'participant_ids': [],
            'payment_method': 'dinheiro',
            'credit_card_id': None,
            'category_id': None,
        }
        data.update(overrides)
        return data

    def test_installments_split_the_total(self):
        resp = CreateSharedEntryBehavior(
            self.group, self.user, self._data(total_installments_input=4)
        ).run()
        self.assertEqual(resp.status_code, 201)

        entries = SharedEntry.objects.order_by('installment_number')
        self.assertEqual(entries.count(), 4)
        # Cada parcela = fracao, e a soma = total da compra.
        for e in entries:
            self.assertEqual(e.amount, Decimal('127.89'))
        self.assertEqual(sum(e.amount for e in entries), Decimal('511.56'))

    def test_installments_share_group_id_and_numbering(self):
        CreateSharedEntryBehavior(
            self.group, self.user, self._data(total_installments_input=4)
        ).run()
        entries = list(SharedEntry.objects.order_by('installment_number'))
        gids = {e.installment_group_id for e in entries}
        self.assertEqual(len(gids), 1)
        self.assertIsNotNone(entries[0].installment_group_id)
        self.assertEqual([e.installment_number for e in entries], [1, 2, 3, 4])
        self.assertTrue(all(e.total_installments == 4 for e in entries))
        self.assertEqual(entries[0].description, 'Milhas Livelo (1/4)')

    def test_single_installment_keeps_full_amount_and_no_group(self):
        CreateSharedEntryBehavior(self.group, self.user, self._data()).run()
        entry = SharedEntry.objects.get()
        self.assertEqual(entry.amount, Decimal('511.56'))
        self.assertIsNone(entry.installment_group_id)
        self.assertEqual(entry.description, 'Milhas Livelo')


class SharedEntryCardValidationTests(TestCase):
    """cartao sem credit_card_id deixa o lancamento invisivel na fatura."""

    def setUp(self):
        self.user = _make_user(tenant_id='owner-1')
        self.group = SharedDebt.objects.create(name='G', owner_tenant_id='owner-1')
        self.me = SharedDebtMember.objects.create(
            shared_debt=self.group, tenant_id='owner-1', display_name='Owner'
        )
        self.other = SharedDebtMember.objects.create(
            shared_debt=self.group, tenant_id=None, display_name='Bob'
        )

    def _data(self, **overrides):
        data = {
            'description': 'Compra',
            'amount': Decimal('50.00'),
            'date': __import__('datetime').date(2026, 8, 17),
            'paid_by': self.me.id,
            'participant_ids': [],
            'payment_method': 'dinheiro',
            'credit_card_id': None,
            'category_id': None,
        }
        data.update(overrides)
        return data

    def test_cartao_without_card_is_rejected(self):
        resp = CreateSharedEntryBehavior(
            self.group, self.user, self._data(payment_method='cartao')
        ).run()
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(SharedEntry.objects.count(), 0)

    def test_cartao_without_card_allowed_when_someone_else_paid(self):
        # Cartao de terceiro nao esta cadastrado neste tenant: nao exigimos.
        resp = CreateSharedEntryBehavior(
            self.group, self.user,
            self._data(payment_method='cartao', paid_by=self.other.id),
        ).run()
        self.assertEqual(resp.status_code, 201)

    def test_dinheiro_is_unaffected(self):
        resp = CreateSharedEntryBehavior(self.group, self.user, self._data()).run()
        self.assertEqual(resp.status_code, 201)


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
        self.category = ExpenseCategory.objects.create(
            tenant_id='pers-1',
            name='Geral',
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


# ---------------------------------------------------------------------------
# Regression tests: SharedDebt DELETE endpoint (bug: HTTP 500 ProtectedError)
# ---------------------------------------------------------------------------

class SharedDebtDeleteEndpointTests(TestCase):
    """
    Regression: deleting a SharedDebt group that has entries used to return
    HTTP 500 because SharedEntry.paid_by has on_delete=PROTECT pointing to
    SharedDebtMember. The fix (perform_destroy) deletes entries first.
    """

    def _principal(self, sub, email='x@x.com', given_name='User', family_name='X'):
        from financial_system.authentication import KeycloakPrincipal
        return KeycloakPrincipal({'sub': sub, 'email': email,
                                  'given_name': given_name, 'family_name': family_name})

    def _make_client(self, principal):
        from rest_framework.test import APIClient
        client = APIClient()
        client.force_authenticate(user=principal)
        return client

    def setUp(self):
        self.owner = self._principal('owner-1', email='owner@e.com', given_name='Owner')
        self.other = self._principal('other-2', email='other@e.com', given_name='Other')
        self.owner_client = self._make_client(self.owner)
        self.other_client = self._make_client(self.other)

        # Create a group as owner.
        resp = self.owner_client.post('/api/debts/shared-debts/', {
            'name': 'Viagem', 'member_names': []
        }, format='json')
        self.assertEqual(resp.status_code, 201, resp.data)
        self.group_id = resp.data['id']

        # Add an entry (this is what used to trigger ProtectedError on delete).
        group = SharedDebt.objects.get(id=self.group_id)
        owner_member = group.members.get(tenant_id='owner-1')
        resp_entry = self.owner_client.post('/api/debts/shared-entries/', {
            'shared_debt': self.group_id,
            'description': 'Jantar',
            'amount': '60.00',
            'date': '2026-01-01',
            'paid_by': owner_member.id,
            'participant_ids': [],
            'payment_method': 'dinheiro',
            'credit_card_id': None,
        }, format='json')
        self.assertEqual(resp_entry.status_code, 201, resp_entry.data)

    def test_owner_can_delete_group_with_entries_returns_204(self):
        """Bug regression: must return 204, not 500 (ProtectedError)."""
        resp = self.owner_client.delete(f'/api/debts/shared-debts/{self.group_id}/')
        self.assertEqual(resp.status_code, 204)
        self.assertFalse(SharedDebt.objects.filter(id=self.group_id).exists())
        # Entries and members must also be gone.
        self.assertEqual(SharedEntry.objects.filter(shared_debt_id=self.group_id).count(), 0)
        self.assertEqual(SharedDebtMember.objects.filter(shared_debt_id=self.group_id).count(), 0)

    def test_non_owner_member_delete_returns_403_group_intact(self):
        """A member who is not the owner must receive 403 and the group must survive."""
        # Let the other user join the group first.
        invite_resp = self.owner_client.post(
            f'/api/debts/shared-debts/{self.group_id}/invite/', {'expires_at': None}, format='json'
        )
        self.assertEqual(invite_resp.status_code, 201)
        token = invite_resp.data['invite_token']

        join_resp = self.other_client.post('/api/debts/shared-debts/join/', {
            'token': token, 'display_name': ''
        }, format='json')
        self.assertEqual(join_resp.status_code, 200)

        # Non-owner attempts to delete.
        resp = self.other_client.delete(f'/api/debts/shared-debts/{self.group_id}/')
        self.assertEqual(resp.status_code, 403)
        self.assertTrue(SharedDebt.objects.filter(id=self.group_id).exists())


# ---------------------------------------------------------------------------
# Regression tests: SharedEntry UPDATE endpoint (PUT / PATCH)
# ---------------------------------------------------------------------------

class SharedEntryUpdateEndpointTests(TestCase):
    """
    Tests for UpdateSharedEntryBehavior + SharedEntryViewSet.update().

    Any member of the group can perform PUT or PATCH on an entry.
    """

    def _principal(self, sub, email='x@x.com', given_name='User', family_name='X'):
        from financial_system.authentication import KeycloakPrincipal
        return KeycloakPrincipal({
            'sub': sub, 'email': email,
            'given_name': given_name, 'family_name': family_name,
        })

    def _client(self, principal):
        from rest_framework.test import APIClient
        c = APIClient()
        c.force_authenticate(user=principal)
        return c

    def setUp(self):
        # Owner and non-owner member principals.
        self.owner_p = self._principal('owner-u', email='owner@e.com', given_name='Owner')
        self.member_p = self._principal('member-u', email='member@e.com', given_name='Member')
        self.outsider_p = self._principal('outsider', email='out@e.com', given_name='Out')

        self.owner_c = self._client(self.owner_p)
        self.member_c = self._client(self.member_p)
        self.outsider_c = self._client(self.outsider_p)

        # Create group as owner.
        resp = self.owner_c.post('/api/debts/shared-debts/', {'name': 'Trip', 'member_names': []}, format='json')
        self.assertEqual(resp.status_code, 201)
        self.group_id = resp.data['id']

        # Invite + join the member.
        inv = self.owner_c.post(f'/api/debts/shared-debts/{self.group_id}/invite/', {'expires_at': None}, format='json')
        self.assertEqual(inv.status_code, 201)
        join = self.member_c.post('/api/debts/shared-debts/join/', {'token': inv.data['invite_token'], 'display_name': ''}, format='json')
        self.assertEqual(join.status_code, 200)

        group = SharedDebt.objects.get(id=self.group_id)
        self.owner_member = group.members.get(tenant_id='owner-u')
        self.member_member = group.members.get(tenant_id='member-u')

        # Create an initial entry (paid by owner, all members participate).
        resp_e = self.owner_c.post('/api/debts/shared-entries/', {
            'shared_debt': self.group_id,
            'description': 'Dinner',
            'amount': '100.00',
            'date': '2026-01-01',
            'paid_by': self.owner_member.id,
            'participant_ids': [],
            'payment_method': 'dinheiro',
            'credit_card_id': None,
        }, format='json')
        self.assertEqual(resp_e.status_code, 201)
        self.entry_id = resp_e.data['id']

    def _put_payload(self, **overrides):
        data = {
            'shared_debt': self.group_id,
            'description': 'Dinner Updated',
            'amount': '120.00',
            'date': '2026-01-02',
            'paid_by': self.owner_member.id,
            'participant_ids': [],
            'payment_method': 'dinheiro',
            'credit_card_id': None,
        }
        data.update(overrides)
        return data

    # --- Happy path: non-owner member can PUT ---
    def test_non_owner_member_can_put_entry(self):
        payload = self._put_payload(description='Updated by member', amount='150.00', paid_by=self.member_member.id)
        resp = self.member_c.put(f'/api/debts/shared-entries/{self.entry_id}/', payload, format='json')
        self.assertEqual(resp.status_code, 200, resp.data)
        entry = SharedEntry.objects.get(id=self.entry_id)
        self.assertEqual(entry.description, 'Updated by member')
        self.assertEqual(entry.amount, Decimal('150.00'))
        self.assertEqual(entry.paid_by_id, self.member_member.id)

    # --- Happy path: owner can PUT ---
    def test_owner_can_put_entry(self):
        payload = self._put_payload(amount='200.00')
        resp = self.owner_c.put(f'/api/debts/shared-entries/{self.entry_id}/', payload, format='json')
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual(SharedEntry.objects.get(id=self.entry_id).amount, Decimal('200.00'))

    # --- Happy path: PATCH a single field ---
    def test_member_can_patch_description(self):
        resp = self.member_c.patch(f'/api/debts/shared-entries/{self.entry_id}/', {'description': 'Patched!'}, format='json')
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual(SharedEntry.objects.get(id=self.entry_id).description, 'Patched!')

    def test_member_can_patch_amount(self):
        resp = self.member_c.patch(f'/api/debts/shared-entries/{self.entry_id}/', {'amount': '77.00'}, format='json')
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual(SharedEntry.objects.get(id=self.entry_id).amount, Decimal('77.00'))

    # --- PATCH without participant_ids leaves participants unchanged ---
    def test_patch_without_participant_ids_preserves_participants(self):
        before = set(SharedEntryParticipant.objects.filter(entry_id=self.entry_id).values_list('member_id', flat=True))
        resp = self.member_c.patch(f'/api/debts/shared-entries/{self.entry_id}/', {'amount': '88.00'}, format='json')
        self.assertEqual(resp.status_code, 200)
        after = set(SharedEntryParticipant.objects.filter(entry_id=self.entry_id).values_list('member_id', flat=True))
        self.assertEqual(before, after)

    # --- PUT with explicit participant_ids re-syncs participants ---
    def test_put_resyncs_participants(self):
        payload = self._put_payload(participant_ids=[self.owner_member.id])
        resp = self.owner_c.put(f'/api/debts/shared-entries/{self.entry_id}/', payload, format='json')
        self.assertEqual(resp.status_code, 200)
        pids = set(SharedEntryParticipant.objects.filter(entry_id=self.entry_id).values_list('member_id', flat=True))
        self.assertEqual(pids, {self.owner_member.id})

    # --- Validation: paid_by non-member → 400 ---
    def test_put_paid_by_non_member_returns_400(self):
        payload = self._put_payload(paid_by=99999)
        resp = self.owner_c.put(f'/api/debts/shared-entries/{self.entry_id}/', payload, format='json')
        self.assertEqual(resp.status_code, 400)

    # --- Validation: participant_ids with non-member → 400 ---
    def test_put_participant_non_member_returns_400(self):
        payload = self._put_payload(participant_ids=[99999])
        resp = self.owner_c.put(f'/api/debts/shared-entries/{self.entry_id}/', payload, format='json')
        self.assertEqual(resp.status_code, 400)

    # --- Auth: non-member gets 403/404 ---
    def test_non_member_update_returns_403_or_404(self):
        payload = self._put_payload()
        resp = self.outsider_c.put(f'/api/debts/shared-entries/{self.entry_id}/', payload, format='json')
        self.assertIn(resp.status_code, [403, 404])

    # --- IDOR: credit_card of another tenant → 400 ---
    def test_credit_card_idor_on_update(self):
        from cards.models import CreditCard
        card = CreditCard.objects.create(
            tenant_id='evil-tenant',
            name='Evil Card',
            due_day=5,
            closing_day=1,
            last_four_digits='9999',
        )
        payload = self._put_payload(payment_method='cartao', credit_card_id=card.id)
        resp = self.owner_c.put(f'/api/debts/shared-entries/{self.entry_id}/', payload, format='json')
        self.assertEqual(resp.status_code, 400)
        # Entry must remain unchanged.
        self.assertEqual(SharedEntry.objects.get(id=self.entry_id).credit_card_id, None)

    # --- Business rule: payment_method='dinheiro' clears credit_card ---
    def test_switching_to_dinheiro_clears_credit_card(self):
        from cards.models import CreditCard
        card = CreditCard.objects.create(
            tenant_id='owner-u',
            name='My Card',
            due_day=10,
            closing_day=1,
            last_four_digits='1111',
        )
        # First set cartao.
        payload = self._put_payload(payment_method='cartao', credit_card_id=card.id)
        resp = self.owner_c.put(f'/api/debts/shared-entries/{self.entry_id}/', payload, format='json')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(SharedEntry.objects.get(id=self.entry_id).credit_card_id, card.id)

        # Then switch back to dinheiro.
        payload2 = self._put_payload(payment_method='dinheiro', credit_card_id=card.id)
        resp2 = self.owner_c.put(f'/api/debts/shared-entries/{self.entry_id}/', payload2, format='json')
        self.assertEqual(resp2.status_code, 200)
        self.assertIsNone(SharedEntry.objects.get(id=self.entry_id).credit_card_id)

    # --- Entry amount/participants persist correctly (balance regression) ---
    def test_entry_persists_after_update(self):
        payload = self._put_payload(amount='300.00', participant_ids=[self.member_member.id])
        resp = self.owner_c.put(f'/api/debts/shared-entries/{self.entry_id}/', payload, format='json')
        self.assertEqual(resp.status_code, 200)
        entry = SharedEntry.objects.get(id=self.entry_id)
        self.assertEqual(entry.amount, Decimal('300.00'))
        pids = set(SharedEntryParticipant.objects.filter(entry=entry).values_list('member_id', flat=True))
        self.assertEqual(pids, {self.member_member.id})


# ---------------------------------------------------------------------------
# [SEC-A01] IDOR de categoria + N+1 do participant_count
# ---------------------------------------------------------------------------

class SharedEntryCategoryOwnershipTests(TestCase):
    """
    A categoria de um lancamento precisa ser do proprio tenant ou global.

    O cartao ja tinha essa guarda; a categoria nao tinha. Como o
    SharedEntrySerializer expoe `category_name`, apontar para a categoria de
    outro tenant vazava o nome dela.
    """

    def setUp(self):
        from catalog.models import ExpenseCategory

        self.user = _make_user(tenant_id='owner-1')
        self.group = SharedDebt.objects.create(name='G', owner_tenant_id='owner-1')
        self.me = SharedDebtMember.objects.create(
            shared_debt=self.group, tenant_id='owner-1', display_name='Owner'
        )
        self.minha = ExpenseCategory.objects.create(
            tenant_id='owner-1', name='Minha')
        self.global_ = ExpenseCategory.objects.create(
            tenant_id='system', name='Global')
        self.alheia = ExpenseCategory.objects.create(
            tenant_id='outro-tenant', name='Alheia')

    def _data(self, **overrides):
        data = {
            'description': 'Compra',
            'amount': Decimal('50.00'),
            'date': __import__('datetime').date(2026, 8, 17),
            'paid_by': self.me.id,
            'participant_ids': [],
            'payment_method': 'dinheiro',
            'credit_card_id': None,
            'category_id': None,
        }
        data.update(overrides)
        return data

    def test_categoria_propria_e_aceita(self):
        resp = CreateSharedEntryBehavior(
            self.group, self.user, self._data(category_id=self.minha.id)
        ).run()
        self.assertEqual(resp.status_code, 201)

    def test_categoria_global_e_aceita(self):
        resp = CreateSharedEntryBehavior(
            self.group, self.user, self._data(category_id=self.global_.id)
        ).run()
        self.assertEqual(resp.status_code, 201)

    def test_categoria_de_outro_tenant_e_rejeitada(self):
        resp = CreateSharedEntryBehavior(
            self.group, self.user, self._data(category_id=self.alheia.id)
        ).run()
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(SharedEntry.objects.count(), 0)

    def test_sem_categoria_continua_valido(self):
        resp = CreateSharedEntryBehavior(self.group, self.user, self._data()).run()
        self.assertEqual(resp.status_code, 201)

    def test_update_para_categoria_de_outro_tenant_e_rejeitado(self):
        CreateSharedEntryBehavior(
            self.group, self.user, self._data(category_id=self.minha.id)
        ).run()
        entry = SharedEntry.objects.get()

        resp = UpdateSharedEntryBehavior(
            entry, self.user, {'category_id': self.alheia.id}, partial=True
        ).run()

        self.assertEqual(resp.status_code, 400)
        entry.refresh_from_db()
        self.assertEqual(entry.category_id, self.minha.id)

    def test_update_para_categoria_propria_funciona(self):
        CreateSharedEntryBehavior(self.group, self.user, self._data()).run()
        entry = SharedEntry.objects.get()

        resp = UpdateSharedEntryBehavior(
            entry, self.user, {'category_id': self.minha.id}, partial=True
        ).run()

        self.assertEqual(resp.status_code, 200)
        entry.refresh_from_db()
        self.assertEqual(entry.category_id, self.minha.id)


class SharedEntryListQueryCountTests(TestCase):
    """
    Trava de regressao do N+1: get_participant_count lia participants e
    members por linha. Sem prefetch, o custo cresce com o numero de itens.
    """

    def setUp(self):
        from rest_framework.test import APIClient

        self.group = SharedDebt.objects.create(name='G', owner_tenant_id='owner-1')
        self.me = SharedDebtMember.objects.create(
            shared_debt=self.group, tenant_id='owner-1', display_name='Owner'
        )
        for i in range(5):
            SharedEntry.objects.create(
                shared_debt=self.group,
                paid_by=self.me,
                description=f'Compra {i}',
                amount=Decimal('10.00'),
                date=__import__('datetime').date(2026, 8, 17),
                created_by_tenant_id='owner-1',
            )

        from financial_system.authentication import KeycloakPrincipal
        self.client = APIClient()
        self.client.force_authenticate(user=KeycloakPrincipal({
            'sub': 'owner-1', 'email': 'o@example.com',
            'given_name': 'O', 'family_name': 'W',
        }))

    def test_numero_de_queries_nao_cresce_com_a_quantidade_de_lancamentos(self):
        # 4 = count da paginacao + entries + prefetch de participants +
        # prefetch de members. Sem o prefetch seriam 2 queries extras por
        # linha, ou seja 12 com os 5 lancamentos deste cenario.
        with self.assertNumQueries(4):
            resp = self.client.get('/api/debts/shared-entries/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['count'], 5)