import re
from decimal import Decimal
import uuid
from dateutil.relativedelta import relativedelta
from django.db import transaction
from django.db.models import Count, Sum
from django.db.models.functions import Abs
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response
from cards.models import CreditCard
from catalog.constants import _MONTH_NAMES
from catalog.models import ExpenseCategory
from debts.models import (
    SharedDebt,
    SharedDebtInvite,
    SharedDebtMember,
    SharedEntry,
    SharedEntryParticipant,
)
from debts.serializer import (
    SharedDebtSerializer,
    SharedEntrySerializer,
)
from expenses.models import Expense
# Epsilon usado no algoritmo de acerto (settlement) — valores abaixo disso são
# tratados como "quitados".
_SETTLEMENT_EPSILON = Decimal('0.01')
from financial_system.money import round2 as _round2, to_float, split_installments as _split_installments, strip_suffix

# Sufixo de parcela das compartilhadas: " (X/Y)", um ou mais, no fim da string.
_INSTALLMENT_SUFFIX_RE = re.compile(r'(?:\s*\(\d+\s*/\s*\d+\))+\s*$')


def _strip_installment_suffix(description: str) -> str:
    """Remove ' (X/Y)' do fim; evita acumular sufixos ao reparcelar uma entrada."""
    return strip_suffix(description, _INSTALLMENT_SUFFIX_RE)


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
                {'detail': 'Convite inválido.'},
                status=status.HTTP_404_NOT_FOUND,
            )
        if invite.expires_at is not None and invite.expires_at < timezone.now():
            return Response(
                {'detail': 'Convite expirado.'},
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


def _category_available_to_tenant(category_id, tenant_id) -> bool:
    """
    True quando a categoria pode ser usada por este tenant.
    Mesmo criterio do get_queryset do catalog: vale a categoria do proprio
    tenant ou uma global ('system'). Sem esta checagem daria para apontar o
    lancamento para a categoria de outro tenant, cujo nome vaza pelo campo
    `category_name` do SharedEntrySerializer.
    """
    return ExpenseCategory.objects.filter(
        id=category_id,
        tenant_id__in=['system', tenant_id],
    ).exists()


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


class EntryRuleError(ValueError):
    """Regra de negocio de lancamento compartilhado violada (vira 400 {'detail'})."""


def _bad_request(exc: EntryRuleError) -> Response:
    return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)


def validate_entry_rules(shared_debt, user, data: dict, *, current=None, partial=False) -> dict:
    """
    Regras comuns a criar/editar SharedEntry e a criar SharedRecurringTemplate.

    Recebe `data` ja tipado pelo serializer de entrada e devolve os campos
    resolvidos: paid_by_id, participant_ids (None = manter os atuais em PATCH),
    payment_method, credit_card_id, category_id. Levanta EntryRuleError.

    `current` e a entry existente (update); `partial` e o PATCH, onde campos
    ausentes herdam o valor atual em vez do default.
    """
    member_ids = set(shared_debt.members.values_list('id', flat=True))

    def pick(key, default):
        return data.get(key, getattr(current, key) if (partial and current is not None) else default)

    paid_by_id = data.get('paid_by', current.paid_by_id if (partial and current is not None) else None)
    if paid_by_id is None:
        raise EntryRuleError('O campo paid_by é obrigatório.')
    if paid_by_id not in member_ids:
        raise EntryRuleError('paid_by não é membro deste grupo.')

    raw_participants = data.get('participant_ids') or None      # [] == ausente
    if raw_participants is not None:
        participant_ids = list(dict.fromkeys(raw_participants))
        if any(pid not in member_ids for pid in participant_ids):
            raise EntryRuleError('participant_ids contém membros de fora do grupo.')
    elif partial and current is not None:
        participant_ids = None                                   # PATCH: mantem os atuais
    else:
        participant_ids = list(member_ids)                       # default: todos
    if participant_ids is not None and not participant_ids:
        raise EntryRuleError('Grupo sem participantes válidos.')

    payment_method = pick('payment_method', 'dinheiro')
    credit_card_id = pick('credit_card_id', None)
    # cartao exigido so quando quem pagou foi o proprio usuario (cartao de
    # terceiro nao esta cadastrado neste tenant).
    if payment_method == 'cartao' and credit_card_id is None and _payer_belongs_to_tenant(paid_by_id, user.tenant_id):
        raise EntryRuleError('credit_card_id é obrigatório quando payment_method é "cartao".')
    # [SEC-A01] IDOR: checa o cartao ANTES de limpar por 'dinheiro', senao uma
    # tentativa de usar cartao de outro tenant passaria despercebida.
    if credit_card_id is not None and not CreditCard.objects.filter(id=credit_card_id, tenant_id=user.tenant_id).exists():
        raise EntryRuleError('O cartão informado não pertence ao usuário autenticado.')
    if payment_method == 'dinheiro':
        credit_card_id = None

    category_id = pick('category_id', None)
    if category_id is not None and not _category_available_to_tenant(category_id, user.tenant_id):
        raise EntryRuleError('A categoria informada não pertence ao usuário autenticado.')

    return {
        'paid_by_id': paid_by_id,
        'participant_ids': participant_ids,
        'payment_method': payment_method,
        'credit_card_id': credit_card_id,
        'category_id': category_id,
    }


class CreateSharedEntryBehavior:
    """Cria uma despesa compartilhada (e suas parcelas) com participantes em rateio igual."""

    def __init__(self, shared_debt: SharedDebt, user, data: dict):
        self.shared_debt = shared_debt
        self.user = user
        self.data = data

    def run(self) -> Response:
        data = self.data
        try:
            rules = validate_entry_rules(self.shared_debt, self.user, data)
        except EntryRuleError as exc:
            return _bad_request(exc)

        total = int(data.get('total_installments_input', 1) or 1)
        group_id = uuid.uuid4() if total > 1 else None
        # O valor informado e o TOTAL da compra: cada parcela recebe sua fracao.
        installment_amounts = _split_installments(data['amount'], total)
        base_description = _strip_installment_suffix(data['description'])
        with transaction.atomic():
            entries = []
            for i in range(total):
                entry = SharedEntry.objects.create(
                    shared_debt=self.shared_debt,
                    paid_by_id=rules['paid_by_id'],
                    description=f"{base_description} ({i + 1}/{total})" if total > 1 else base_description,
                    amount=installment_amounts[i],
                    date=data['date'] + relativedelta(months=i) if total > 1 else data['date'],
                    payment_method=rules['payment_method'],
                    credit_card_id=rules['credit_card_id'],
                    category_id=rules['category_id'],
                    created_by_tenant_id=self.user.tenant_id,
                    installment_group_id=group_id,
                    total_installments=total,
                    installment_number=i + 1,
                    paid=bool(data.get('paid', False)),
                )
                SharedEntryParticipant.objects.bulk_create(
                    [SharedEntryParticipant(entry=entry, member_id=mid) for mid in rules['participant_ids']]
                )
                entries.append(entry)
        return Response(SharedEntrySerializer(entries[0]).data, status=status.HTTP_201_CREATED)


class UpdateSharedEntryBehavior:
    """
    Atualiza uma despesa compartilhada e ressincroniza participantes.

    Mesmas regras do create (validate_entry_rules). PUT sem participant_ids
    usa todos os membros; PATCH sem participant_ids mantem os atuais.
    """

    def __init__(self, entry: SharedEntry, user, data: dict, partial: bool = False):
        self.entry = entry
        self.user = user
        self.data = data
        self.partial = partial

    def run(self) -> Response:
        entry, data = self.entry, self.data
        try:
            rules = validate_entry_rules(entry.shared_debt, self.user, data, current=entry, partial=self.partial)
        except EntryRuleError as exc:
            return _bad_request(exc)

        with transaction.atomic():
            for field in ('description', 'amount', 'date'):
                if field in data or not self.partial:
                    setattr(entry, field, data.get(field, getattr(entry, field)))
            entry.paid_by_id = rules['paid_by_id']
            entry.payment_method = rules['payment_method']
            entry.credit_card_id = rules['credit_card_id']
            if 'category_id' in data or not self.partial:
                entry.category_id = rules['category_id']
            if 'paid' in data:
                entry.paid = data['paid']
            entry.save()
            if rules['participant_ids'] is not None:
                entry.participants.all().delete()
                SharedEntryParticipant.objects.bulk_create(
                    [SharedEntryParticipant(entry=entry, member_id=mid) for mid in rules['participant_ids']]
                )
        return Response(SharedEntrySerializer(entry).data, status=status.HTTP_200_OK)


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
            share = entry.share_per_participant()
            for pid in entry.participant_ids():
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
                'paid': to_float(paid[m.id]),
                'owed': to_float(owed[m.id]),
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
                    'amount': to_float(transfer),
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
                'total': to_float(installments['total']),
                'count': installments['count'] or 0,
            },
            'card_current_month': {
                'total': to_float(card['total']),
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
                if my_member_id is not None:
                    my_portion += entry.share_of(my_member_id)
            members_names = [m.display_name for m in g.members.all()]
            result.append({
                'id': g.id,
                'name': g.name,
                'members': members_names,
                'total_amount': to_float(total_amount),
                'my_portion': to_float(my_portion),
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
                buckets[key]['my_portion'] += entry.share_of(my_member_id)
        result = [
            {
                'year': year,
                'month': month,
                'month_name': _MONTH_NAMES[month],
                'total': to_float(data['total']),
                'my_portion': to_float(data['my_portion']),
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
        """`data` ja validado por SharedRecurringTemplateInputSerializer."""
        from debts.models import SharedRecurringTemplate
        from debts.serializer import SharedRecurringTemplateSerializer
        try:
            rules = validate_entry_rules(self.shared_debt, self.user, data)
        except EntryRuleError as exc:
            return _bad_request(exc)
        tpl = SharedRecurringTemplate.objects.create(
            shared_debt=self.shared_debt,
            description=data['description'],
            amount=data['amount'],
            paid_by_id=rules['paid_by_id'],
            participant_ids=rules['participant_ids'],
            payment_method=rules['payment_method'],
            category_id=rules['category_id'],
            day_of_month=data.get('day_of_month', 1),
            is_active=data.get('is_active', True),
        )
        return Response(SharedRecurringTemplateSerializer(tpl).data, status=status.HTTP_201_CREATED)

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