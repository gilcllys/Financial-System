"""
POST /api/debts/shared-entries/delete-installments/

Remove todas as parcelas de um parcelamento compartilhado de uma vez.
Mesma regra do DELETE individual: qualquer membro do grupo pode excluir.
"""
import uuid
from datetime import date
from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APIClient

from debts.models import SharedDebt, SharedDebtMember, SharedEntry, SharedEntryParticipant

URL = '/api/debts/shared-entries/delete-installments/'


class DeleteSharedInstallmentsTests(TestCase):
    def _client(self, sub):
        from financial_system.authentication import KeycloakPrincipal
        c = APIClient()
        c.force_authenticate(user=KeycloakPrincipal({
            'sub': sub, 'email': f'{sub}@e.com', 'given_name': sub, 'family_name': 'X'}))
        return c

    def setUp(self):
        self.group = SharedDebt.objects.create(name='Casal', owner_tenant_id='gil')
        self.gil = SharedDebtMember.objects.create(shared_debt=self.group, tenant_id='gil', display_name='Gil')
        self.vi = SharedDebtMember.objects.create(shared_debt=self.group, tenant_id='vi', display_name='Vi')
        self.gid = uuid.uuid4()
        for n in (1, 2, 3):
            e = SharedEntry.objects.create(
                shared_debt=self.group, paid_by=self.gil, description=f'Passagem {n}/3',
                amount=Decimal('122.69'), date=date(2026, 8 + n, 14), payment_method='cartao',
                created_by_tenant_id='gil', installment_group_id=self.gid,
                total_installments=3, installment_number=n,
            )
            SharedEntryParticipant.objects.create(entry=e, member=self.vi)
        # parcelamento de outro grupo nao pode ser afetado
        other = SharedDebt.objects.create(name='Outro', owner_tenant_id='zed')
        zed = SharedDebtMember.objects.create(shared_debt=other, tenant_id='zed', display_name='Zed')
        self.other_gid = uuid.uuid4()
        SharedEntry.objects.create(
            shared_debt=other, paid_by=zed, description='X 1/2', amount=Decimal('10'), date=date(2026, 9, 1),
            created_by_tenant_id='zed', installment_group_id=self.other_gid, total_installments=2, installment_number=1,
        )

    def test_member_deletes_all_installments_atomically(self):
        resp = self._client('vi').post(URL, {'installment_group_id': str(self.gid)}, format='json')

        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual(resp.data['deleted'], 3)
        self.assertFalse(SharedEntry.objects.filter(installment_group_id=self.gid).exists())
        self.assertFalse(SharedEntryParticipant.objects.filter(entry__installment_group_id=self.gid).exists())
        self.assertEqual(SharedEntry.objects.filter(installment_group_id=self.other_gid).count(), 1)

    def test_non_member_gets_404_and_nothing_is_deleted(self):
        resp = self._client('zed').post(URL, {'installment_group_id': str(self.gid)}, format='json')

        self.assertEqual(resp.status_code, 404)
        self.assertEqual(SharedEntry.objects.filter(installment_group_id=self.gid).count(), 3)

    def test_invalid_uuid_is_400(self):
        resp = self._client('gil').post(URL, {'installment_group_id': 'nope'}, format='json')

        self.assertEqual(resp.status_code, 400)
