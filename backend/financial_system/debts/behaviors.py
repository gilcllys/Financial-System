import re
from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP

import uuid
from dateutil.relativedelta import relativedelta
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


# Sufixo de parcela das compartilhadas: " (X/Y)", um ou mais, no fim da string.
_INSTALLMENT_SUFFIX_RE = re.compile(r'(?:\s*\(\d+\s*/\s*\d+\))+\s*$')


def _strip_installment_suffix(description: str) -> str:
    """
    Remove o sufixo " (X/Y)" do fim da descrição.

    Evita acumular sufixos ("Item (1/4) (1/4)") caso uma entrada já parcelada
    seja reparcelada, o que quebraria o agrupamento na tela de Parcelas.
    """
    if not description:
        return description
    return _INSTALLMENT_SUFFIX_RE.sub('', description).strip()


def _split_installments(total_amount, installments: int) -> list:
    """
    Divide um valor total em N parcelas com 2 casas decimais.

    Os centavos residuais da divisao sao distribuidos nas primeiras parcelas,
    garantindo que a soma das parcelas seja exatamente igual ao total.
    Ex.: 100.00 em 3 -> [33.34, 33.33, 33.33]
    """
    total = _round2(Decimal(str(total_amount)))
    if installments < 2:
        return [total]

    # Espelha expenses._split_installments: o rateio so e correto sobre o valor
    # absoluto, pois ROUND_DOWN trunca em direcao ao zero e o residual de um
    # total negativo sai negativo, anulando o laco de distribuicao.
    sign = -1 if total < 0 else 1
    magnitude = abs(total)

    base = (magnitude / installments).quantize(_TWO_PLACES, rounding=ROUND_DOWN)
    amounts = [base] * installments

    residual_cents = int((magnitude - base * installments) / _TWO_PLACES)
    for i in range(residual_cents):
        amounts[i] += _TWO_PLACES

    return [a * sign for a in amounts]


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


def _payer_belongs_to_tenant(paid_by_id, tenant_id) -> bool:
    """
    True quando quem pagou é o próprio usuário autenticado.

    Só nesse caso exigimos credit_card_id: se outro membro pagou com o cartão
    dele, esse cartão não está (nem deve estar) cadastrado neste tenant.
    """
    return SharedDebtMember.objects.filter(
        id=paid_by_id,
        tenant_id=tenant_id,
    ).exists()


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
        self.category_id = data.get('category_id')
        self.total_installments = int(data.get('total_installments_input', 1) or 1)

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

        # payment_method='cartao' exige cartão vinculado quando quem pagou foi o
        # próprio usuário, senão o lançamento fica invisível em qualquer fatura.
        if (
            self.payment_method == 'cartao'
            and self.credit_card_id is None
            and _payer_belongs_to_tenant(self.paid_by_id, self.user.tenant_id)
        ):
            return Response(
                {
                    'success': False,
                    'message': 'credit_card_id é obrigatório quando payment_method é "cartao".',
                },
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

        # payment_method='dinheiro' nunca carrega cartão. Limpamos só aqui, após o
        # guard de IDOR: limpar antes esconderia uma tentativa de usar cartão
        # de outro tenant.
        if self.payment_method == 'dinheiro':
            self.credit_card_id = None

        total = self.total_installments
        group_id = uuid.uuid4() if total > 1 else None
        # O valor informado é o TOTAL da compra: cada parcela recebe apenas a
        # sua fração, nunca o valor cheio.
        installment_amounts = _split_installments(self.amount, total)
        base_description = _strip_installment_suffix(self.description)

        with transaction.atomic():
            entries = []
            for i in range(total):
                entry_date = self.date + relativedelta(months=i) if total > 1 else self.date
                desc = f"{base_description} ({i + 1}/{total})" if total > 1 else base_description
                entry = SharedEntry.objects.create(
                    shared_debt=self.shared_debt,
                    paid_by_id=self.paid_by_id,
                    description=desc,
                    amount=installment_amounts[i],
                    date=entry_date,
                    payment_method=self.payment_method,
                    credit_card_id=self.credit_card_id,
                    category_id=self.category_id,
                    created_by_tenant_id=self.user.tenant_id,
                    installment_group_id=group_id,
                    total_installments=total,
                    installment_number=i + 1,
                )
                SharedEntryParticipant.objects.bulk_create(
                    [
                        SharedEntryParticipant(entry=entry, member_id=member_id)
                        for member_id in participant_ids
                    ]
                )
                entries.append(entry)

        return Response(
            SharedEntrySerializer(entries[0]).data,
            status=status.HTTP_201_CREATED,
        )


class UpdateSharedEntryBehavior:
    """
    Atualiza uma despesa compartilhada existente e ressincroniza participantes.

    Regras idênticas ao create:
    - paid_by precisa ser membro do grupo da entrada (shared_debt imutável).
    - participant_ids (se fornecidos) precisam pertencer ao grupo.
    - Para PUT (partial=False) sem participant_ids → usa todos os membros.
    - Para PATCH (partial=True) sem participant_ids → mantém participantes atuais.
    - credit_card_id (se informado e não-nulo) deve pertencer ao tenant autenticado.
    - payment_method='dinheiro' força credit_card a null.
    """

    def __init__(self, entry: SharedEntry, user, data: dict, partial: bool = False):
        self.entry = entry
        self.user = user
        self.data = data
        self.partial = partial

    def _member_ids(self):
        return set(self.entry.shared_debt.members.values_list('id', flat=True))

    def run(self) -> Response:
        entry = self.entry
        data = self.data
        member_ids = self._member_ids()

        # -- paid_by validation --
        paid_by_id = data.get('paid_by', entry.paid_by_id if self.partial else None)
        if paid_by_id is None:
            return Response(
                {'success': False, 'message': 'O campo paid_by é obrigatório.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if paid_by_id not in member_ids:
            return Response(
                {'success': False, 'message': 'paid_by não é membro deste grupo.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # -- participant_ids validation / resolution --
        # An empty list is treated the same as "not provided":
        # - PUT  → default to all members of the group.
        # - PATCH → keep the existing participant set unchanged.
        raw_participants = data.get('participant_ids') or None  # [] → None
        if raw_participants is not None:
            participant_ids = list(dict.fromkeys(raw_participants))
            invalid = [pid for pid in participant_ids if pid not in member_ids]
            if invalid:
                return Response(
                    {
                        'success': False,
                        'message': 'participant_ids contém membros de fora do grupo.',
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            replace_participants = True
        elif self.partial:
            # PATCH without participant_ids → keep existing participants unchanged.
            participant_ids = None
            replace_participants = False
        else:
            # Full PUT without participant_ids → default to all members.
            participant_ids = list(member_ids)
            replace_participants = True

        if replace_participants and not participant_ids:
            return Response(
                {'success': False, 'message': 'Grupo sem participantes válidos.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # -- payment_method / credit_card --
        payment_method = data.get(
            'payment_method', entry.payment_method if self.partial else 'dinheiro'
        )
        credit_card_id = data.get('credit_card_id', entry.credit_card_id if self.partial else None)

        # payment_method='dinheiro' clears credit_card.
        if payment_method == 'dinheiro':
            credit_card_id = None

        # payment_method='cartao' exige cartão vinculado quando quem pagou foi o
        # próprio usuário (cartão de terceiro não existe neste tenant).
        if (
            payment_method == 'cartao'
            and credit_card_id is None
            and _payer_belongs_to_tenant(paid_by_id, self.user.tenant_id)
        ):
            return Response(
                {
                    'success': False,
                    'message': 'credit_card_id é obrigatório quando payment_method é "cartao".',
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # [SEC-A01] IDOR guard.
        if credit_card_id is not None:
            owns_card = CreditCard.objects.filter(
                id=credit_card_id,
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
            # Update scalar fields.
            if 'description' in data or not self.partial:
                entry.description = data.get('description', entry.description)
            if 'amount' in data or not self.partial:
                entry.amount = data.get('amount', entry.amount)
            if 'date' in data or not self.partial:
                entry.date = data.get('date', entry.date)
            entry.paid_by_id = paid_by_id
            entry.payment_method = payment_method
            entry.credit_card_id = credit_card_id
            if 'category_id' in data or not self.partial:
                entry.category_id = data.get('category_id', entry.category_id if self.partial else None)
            if 'paid' in data:
                entry.paid = data['paid']
            entry.save()

            # Re-sync participants only when requested.
            if replace_participants:
                entry.participants.all().delete()
                SharedEntryParticipant.objects.bulk_create(
                    [
                        SharedEntryParticipant(entry=entry, member_id=mid)
                        for mid in participant_ids
                    ]
                )

        return Response(
            SharedEntrySerializer(entry).data,
            status=status.HTTP_200_OK,
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


# ─────────────────────────────────────────────────────────────────────────────
# Home Summary: todos os grupos do usuário com total e minha parte (sem N+1)
# ─────────────────────────────────────────────────────────────────────────────
class HomeSummaryBehavior:
    """
    GET /api/debts/shared-debts/home-summary/

    Retorna lista de grupos com:
      - total_amount   : soma de todos os SharedEntry do grupo
      - my_portion     : minha parte proporcional (participações)
      - members        : lista de display_name dos membros (para avatares)
    """

    def __init__(self, user):
        self.user = user

    def run(self) -> Response:
        from debts.models import SharedDebt, SharedDebtMember, SharedEntry, SharedEntryParticipant

        # Grupos nos quais sou membro
        groups = list(
            SharedDebt.objects
            .filter(members__tenant_id=self.user.tenant_id)
            .distinct()
            .prefetch_related('members', 'entries__participants')
            .order_by('-id')
        )

        my_member_ids_by_group = {}
        for g in groups:
            for m in g.members.all():
                if m.tenant_id == self.user.tenant_id:
                    my_member_ids_by_group[g.id] = m.id

        result = []
        for g in groups:
            my_member_id = my_member_ids_by_group.get(g.id)
            total_amount = Decimal('0')
            my_portion = Decimal('0')

            for entry in g.entries.all():
                total_amount += entry.amount
                participants = [p.member_id for p in entry.participants.all()]
                if participants and my_member_id in participants:
                    my_portion += entry.amount / Decimal(len(participants))

            members_names = [m.display_name for m in g.members.all()]

            result.append({
                'id': g.id,
                'name': g.name,
                'members': members_names,
                'total_amount': round(float(total_amount), 2),
                'my_portion': round(float(my_portion), 2),
                'entry_count': g.entries.count(),
            })

        return Response(result, status=status.HTTP_200_OK)


# ─────────────────────────────────────────────────────────────────────────────
# Monthly History: histórico mensal de um grupo
# ─────────────────────────────────────────────────────────────────────────────
class MonthlyHistoryBehavior:
    """
    GET /api/debts/shared-debts/{id}/monthly-history/

    Retorna lista de {year, month, month_name, total, my_portion, entry_count}
    ordenada do mais recente ao mais antigo.
    """

    _MONTH_NAMES = ['','Janeiro','Fevereiro','Março','Abril','Maio','Junho',
                    'Julho','Agosto','Setembro','Outubro','Novembro','Dezembro']

    def __init__(self, shared_debt, user):
        self.shared_debt = shared_debt
        self.user = user

    def run(self) -> Response:
        # Descobrir meu member_id neste grupo
        my_member = self.shared_debt.members.filter(
            tenant_id=self.user.tenant_id
        ).first()
        my_member_id = my_member.id if my_member else None

        entries = (
            self.shared_debt.entries
            .prefetch_related('participants')
            .order_by('-date')
        )

        # Agregar por (year, month)
        buckets: dict = {}
        for entry in entries:
            key = (entry.date.year, entry.date.month)
            if key not in buckets:
                buckets[key] = {'total': Decimal('0'), 'my_portion': Decimal('0'), 'count': 0}
            buckets[key]['total'] += entry.amount
            buckets[key]['count'] += 1
            if my_member_id is not None:
                participants = [p.member_id for p in entry.participants.all()]
                if participants and my_member_id in participants:
                    buckets[key]['my_portion'] += entry.amount / Decimal(len(participants))

        result = [
            {
                'year': year,
                'month': month,
                'month_name': self._MONTH_NAMES[month],
                'total': round(float(data['total']), 2),
                'my_portion': round(float(data['my_portion']), 2),
                'entry_count': data['count'],
            }
            for (year, month), data in sorted(buckets.items(), reverse=True)
        ]
        return Response(result, status=status.HTTP_200_OK)


# ─────────────────────────────────────────────────────────────────────────────
# Recurring Templates CRUD + generate_month
# ─────────────────────────────────────────────────────────────────────────────
class RecurringTemplateBehavior:
    """Cria, lista e materializa templates recorrentes de um grupo."""

    def __init__(self, shared_debt, user):
        self.shared_debt = shared_debt
        self.user = user

    def list(self) -> Response:
        from debts.models import SharedRecurringTemplate
        from debts.serializer import SharedRecurringTemplateSerializer
        qs = SharedRecurringTemplate.objects.filter(
            shared_debt=self.shared_debt
        ).select_related('paid_by', 'category').order_by('id')
        return Response(
            SharedRecurringTemplateSerializer(qs, many=True).data,
            status=status.HTTP_200_OK,
        )

    def create(self, data: dict) -> Response:
        from debts.models import SharedDebtMember, SharedRecurringTemplate
        from debts.serializer import SharedRecurringTemplateSerializer

        member_ids = set(self.shared_debt.members.values_list('id', flat=True))

        paid_by_id = data.get('paid_by')
        if paid_by_id not in member_ids:
            return Response({'detail': 'paid_by não é membro do grupo.'},
                            status=status.HTTP_400_BAD_REQUEST)

        participant_ids = data.get('participant_ids') or list(member_ids)
        invalid = [p for p in participant_ids if p not in member_ids]
        if invalid:
            return Response({'detail': 'participant_ids inválidos.'},
                            status=status.HTTP_400_BAD_REQUEST)

        day = int(data.get('day_of_month', 1))
        if not (1 <= day <= 28):
            return Response({'detail': 'day_of_month deve ser entre 1 e 28.'},
                            status=status.HTTP_400_BAD_REQUEST)

        tpl = SharedRecurringTemplate.objects.create(
            shared_debt=self.shared_debt,
            description=data['description'],
            amount=data['amount'],
            paid_by_id=paid_by_id,
            participant_ids=participant_ids,
            payment_method=data.get('payment_method', 'dinheiro'),
            category_id=data.get('category_id'),
            day_of_month=day,
            is_active=data.get('is_active', True),
        )
        return Response(
            SharedRecurringTemplateSerializer(tpl).data,
            status=status.HTTP_201_CREATED,
        )

    def toggle_active(self, template_id: int) -> Response:
        from debts.models import SharedRecurringTemplate
        from debts.serializer import SharedRecurringTemplateSerializer
        try:
            tpl = SharedRecurringTemplate.objects.get(
                id=template_id, shared_debt=self.shared_debt
            )
        except SharedRecurringTemplate.DoesNotExist:
            return Response({'detail': 'Template não encontrado.'}, status=status.HTTP_404_NOT_FOUND)
        tpl.is_active = not tpl.is_active
        tpl.save(update_fields=['is_active', 'updated_at'])
        return Response(SharedRecurringTemplateSerializer(tpl).data, status=status.HTTP_200_OK)

    def delete(self, template_id: int) -> Response:
        from debts.models import SharedRecurringTemplate
        try:
            tpl = SharedRecurringTemplate.objects.get(
                id=template_id, shared_debt=self.shared_debt
            )
        except SharedRecurringTemplate.DoesNotExist:
            return Response({'detail': 'Template não encontrado.'}, status=status.HTTP_404_NOT_FOUND)
        tpl.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    def generate_month(self, month: int, year: int) -> Response:
        """
        Materializa todos os templates ativos para o mês/ano informado.
        Cria um SharedEntry apenas se ainda não existir um com a mesma
        descrição e data naquele mês (idempotente).
        """
        import calendar as cal_mod
        from datetime import date as date_cls
        from debts.models import SharedRecurringTemplate

        templates = SharedRecurringTemplate.objects.filter(
            shared_debt=self.shared_debt, is_active=True
        )
        created = []
        skipped = []

        for tpl in templates:
            # Usar day_of_month, respeitando o último dia do mês
            last_day = cal_mod.monthrange(year, month)[1]
            day = min(tpl.day_of_month, last_day)
            entry_date = date_cls(year, month, day)

            # Idempotência: não duplica se já existir mesma descrição + mês
            already = self.shared_debt.entries.filter(
                description=tpl.description,
                date__year=year,
                date__month=month,
            ).exists()

            if already:
                skipped.append(tpl.description)
                continue

            with transaction.atomic():
                entry = SharedEntry.objects.create(
                    shared_debt=self.shared_debt,
                    paid_by_id=tpl.paid_by_id,
                    description=tpl.description,
                    amount=tpl.amount,
                    date=entry_date,
                    payment_method=tpl.payment_method,
                    category_id=tpl.category_id,
                    created_by_tenant_id=self.user.tenant_id,
                )
                SharedEntryParticipant.objects.bulk_create([
                    SharedEntryParticipant(entry=entry, member_id=mid)
                    for mid in tpl.participant_ids
                ])
            created.append(tpl.description)

        return Response(
            {'created': created, 'skipped': skipped},
            status=status.HTTP_200_OK,
        )
