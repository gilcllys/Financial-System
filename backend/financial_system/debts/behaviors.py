from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction
from django.db.models import Count, Sum
from django.db.models.functions import Abs
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response

from cards.models import CreditCard
from debts.models import (
    SharedDebt,
    SharedDebtInvite,
    SharedDebtMember,
    SharedEntry,
    SharedEntryParticipant,
)
from debts.serializer import (
    SharedDebtMemberSerializer,
    SharedDebtSerializer,
    SharedEntrySerializer,
)
from expenses.models import Expense

# Epsilon usado no algoritmo de acerto (settlement) — valores abaixo disso são
# tratados como "quitados".
_SETTLEMENT_EPSILON = Decimal('0.01')
_TWO_PLACES = Decimal('0.01')


def _round2(value: Decimal) -> Decimal:
    return Decimal(value).quantize(_TWO_PLACES, rounding=ROUND_HALF_UP)


class CreateSharedDebtBehavior:
    """Cria um grupo de dívida compartilhada com o dono como primeiro membro."""

    def __init__(self, data: dict, user):
        self.name = data.get('name')
        self.member_names = data.get('member_names') or []
        self.user = user

    @transaction.atomic
    def run(self) -> Response:
        shared_debt = SharedDebt.objects.create(
            name=self.name,
            owner_tenant_id=self.user.tenant_id,
        )
        SharedDebtMember.objects.create(
            shared_debt=shared_debt,
            tenant_id=self.user.tenant_id,
            display_name=self.user.first_name or self.user.email,
            email=self.user.email or None,
        )
        for member_name in self.member_names:
            SharedDebtMember.objects.create(
                shared_debt=shared_debt,
                tenant_id=None,
                display_name=member_name,
            )
        return Response(
            SharedDebtSerializer(shared_debt).data,
            status=status.HTTP_201_CREATED,
        )


class InviteBehavior:
    """Gera um convite (link) para entrar em um grupo."""

    def __init__(self, shared_debt: SharedDebt, user, data: dict):
        self.shared_debt = shared_debt
        self.user = user
        self.expires_at = data.get('expires_at')

    def run(self) -> Response:
        invite = SharedDebtInvite.objects.create(
            shared_debt=self.shared_debt,
            expires_at=self.expires_at,
            created_by_tenant_id=self.user.tenant_id,
        )
        return Response(
            {
                'invite_token': str(invite.token),
                'join_path': f'/shared-debts/join/{invite.token}',
            },
            status=status.HTTP_201_CREATED,
        )


class JoinSharedDebtBehavior:
    """Adiciona o usuário autenticado a um grupo via token de convite."""

    def __init__(self, data: dict, user):
        self.token = data.get('token')
        self.display_name = data.get('display_name')
        self.user = user

    @transaction.atomic
    def run(self) -> Response:
        try:
            invite = SharedDebtInvite.objects.select_related('shared_debt').get(
                token=self.token,
            )
        except SharedDebtInvite.DoesNotExist:
            return Response(
                {'success': False, 'message': 'Convite inválido.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        if invite.expires_at is not None and invite.expires_at < timezone.now():
            return Response(
                {'success': False, 'message': 'Convite expirado.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        shared_debt = invite.shared_debt

        # Usuário já é membro → apenas retorna o grupo.
        already_member = SharedDebtMember.objects.filter(
            shared_debt=shared_debt,
            tenant_id=self.user.tenant_id,
        ).exists()
        if not already_member:
            display_name = (
                self.display_name
                or self.user.first_name
                or self.user.email
            )
            SharedDebtMember.objects.create(
                shared_debt=shared_debt,
                tenant_id=self.user.tenant_id,
                display_name=display_name,
                email=self.user.email or None,
            )

        return Response(
            SharedDebtSerializer(shared_debt).data,
            status=status.HTTP_200_OK,
        )


class CreateSharedEntryBehavior:
    """Cria uma despesa compartilhada e seus participantes (rateio igual)."""

    def __init__(self, shared_debt: SharedDebt, user, data: dict):
        self.shared_debt = shared_debt
        self.user = user
        self.description = data.get('description')
        self.amount = data.get('amount')
        self.date = data.get('date')
        self.paid_by_id = data.get('paid_by')
        self.participant_ids = data.get('participant_ids') or []
        self.payment_method = data.get('payment_method', 'dinheiro')
        self.credit_card_id = data.get('credit_card_id')

    def _member_ids(self):
        return set(
            self.shared_debt.members.values_list('id', flat=True)
        )

    def run(self) -> Response:
        member_ids = self._member_ids()

        # paid_by precisa ser membro deste grupo.
        if self.paid_by_id not in member_ids:
            return Response(
                {'success': False, 'message': 'paid_by não é membro deste grupo.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # participant_ids (se informados) precisam pertencer ao grupo.
        if self.participant_ids:
            participant_ids = list(dict.fromkeys(self.participant_ids))
            invalid = [pid for pid in participant_ids if pid not in member_ids]
            if invalid:
                return Response(
                    {
                        'success': False,
                        'message': 'participant_ids contém membros de fora do grupo.',
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
        else:
            participant_ids = list(member_ids)

        if not participant_ids:
            return Response(
                {'success': False, 'message': 'Grupo sem participantes válidos.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # [SEC-A01] IDOR: cartão precisa pertencer ao tenant autenticado.
        if self.credit_card_id is not None:
            owns_card = CreditCard.objects.filter(
                id=self.credit_card_id,
                tenant_id=self.user.tenant_id,
            ).exists()
            if not owns_card:
                return Response(
                    {
                        'success': False,
                        'message': 'O cartão informado não pertence ao usuário autenticado.',
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

        with transaction.atomic():
            entry = SharedEntry.objects.create(
                shared_debt=self.shared_debt,
                paid_by_id=self.paid_by_id,
                description=self.description,
                amount=self.amount,
                date=self.date,
                payment_method=self.payment_method,
                credit_card_id=self.credit_card_id,
                created_by_tenant_id=self.user.tenant_id,
            )
            SharedEntryParticipant.objects.bulk_create(
                [
                    SharedEntryParticipant(entry=entry, member_id=member_id)
                    for member_id in participant_ids
                ]
            )

        return Response(
            SharedEntrySerializer(entry).data,
            status=status.HTTP_201_CREATED,
        )


class BalancesBehavior:
    """Calcula saldos por membro e o plano de acerto (quem paga quem)."""

    def __init__(self, shared_debt: SharedDebt):
        self.shared_debt = shared_debt

    def run(self) -> Response:
        members = list(self.shared_debt.members.all())
        members_by_id = {m.id: m for m in members}

        paid = {m.id: Decimal('0') for m in members}
        owed = {m.id: Decimal('0') for m in members}

        # Evita N+1: carrega entries com seus participantes de uma vez.
        entries = (
            self.shared_debt.entries
            .prefetch_related('participants')
            .all()
        )
        for entry in entries:
            paid[entry.paid_by_id] = paid.get(entry.paid_by_id, Decimal('0')) + entry.amount
            participant_ids = [p.member_id for p in entry.participants.all()]
            if not participant_ids:
                continue
            share = entry.amount / Decimal(len(participant_ids))
            for pid in participant_ids:
                owed[pid] = owed.get(pid, Decimal('0')) + share

        balance = {
            m.id: _round2(paid[m.id] - owed[m.id])
            for m in members
        }

        members_payload = [
            {
                'member_id': m.id,
                'display_name': m.display_name,
                'tenant_id': m.tenant_id,
                'paid': float(_round2(paid[m.id])),
                'owed': float(_round2(owed[m.id])),
                'balance': float(balance[m.id]),
            }
            for m in members
        ]

        settlement = self._settlement(balance, members_by_id)

        return Response(
            {'members': members_payload, 'settlement': settlement},
            status=status.HTTP_200_OK,
        )

    @staticmethod
    def _settlement(balance: dict, members_by_id: dict):
        """Acerto guloso com mínimo de transferências."""
        creditors = [
            [mid, bal] for mid, bal in balance.items() if bal > _SETTLEMENT_EPSILON
        ]
        debtors = [
            [mid, -bal] for mid, bal in balance.items() if bal < -_SETTLEMENT_EPSILON
        ]

        settlement = []
        while creditors and debtors:
            creditors.sort(key=lambda x: x[1], reverse=True)
            debtors.sort(key=lambda x: x[1], reverse=True)

            creditor = creditors[0]
            debtor = debtors[0]
            transfer = min(creditor[1], debtor[1])

            settlement.append(
                {
                    'from_member_id': debtor[0],
                    'from_name': members_by_id[debtor[0]].display_name,
                    'to_member_id': creditor[0],
                    'to_name': members_by_id[creditor[0]].display_name,
                    'amount': float(_round2(transfer)),
                }
            )

            creditor[1] -= transfer
            debtor[1] -= transfer

            if creditor[1] <= _SETTLEMENT_EPSILON:
                creditors.pop(0)
            if debtor[1] <= _SETTLEMENT_EPSILON:
                debtors.pop(0)

        return settlement


class PersonalSummaryBehavior:
    """
    Agrega as "Dívidas Pessoais" do usuário autenticado (sem tabelas novas):

      - installments_remaining: parcelas futuras ainda devidas
        (descrição casa 'parcela N/N' e date >= hoje).
      - card_current_month: gastos no cartão dentro do mês/ano corrente
        (proxy da fatura atual).

    Ambos os agregados são escopados por tenant_id e usam Abs() para lidar
    com a convenção de sinal das despesas.
    """

    # Padrão do formato gerado por CreateExpenseBehavior ("... Parcela X/Y").
    _INSTALLMENT_REGEX = r'parcela\s+\d+/\d+'

    def __init__(self, user):
        self.user = user

    def run(self) -> Response:
        today = timezone.localdate()

        installments = (
            Expense.objects
            .filter(
                tenant_id=self.user.tenant_id,
                description__iregex=self._INSTALLMENT_REGEX,
                date__gte=today,
            )
            .aggregate(total=Sum(Abs('amount')), count=Count('id'))
        )

        card = (
            Expense.objects
            .filter(
                tenant_id=self.user.tenant_id,
                payment_method='cartao',
                date__year=today.year,
                date__month=today.month,
            )
            .aggregate(total=Sum(Abs('amount')), count=Count('id'))
        )

        data = {
            'installments_remaining': {
                'total': round(float(installments['total'] or 0), 2),
                'count': installments['count'] or 0,
            },
            'card_current_month': {
                'total': round(float(card['total'] or 0), 2),
                'count': card['count'] or 0,
            },
        }
        return Response(data, status=status.HTTP_200_OK)
