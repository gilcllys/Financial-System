
from django.db import transaction

from rest_framework import viewsets
from rest_framework.pagination import PageNumberPagination
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from debts import custom_serializer, serializer
from debts.behaviors import (
    BalancesBehavior,
    CreateSharedDebtBehavior,
    CreateSharedEntryBehavior,
    HomeSummaryBehavior,
    InviteBehavior,
    JoinSharedDebtBehavior,
    MonthlyHistoryBehavior,
    PersonalSummaryBehavior,
    RecurringTemplateBehavior,
    UpdateSharedEntryBehavior,
)
from debts.by_person import ByPersonBehavior
from debts.models import SharedDebt, SharedEntry
from expenses.serializer import GenerateMonthInputSerializer
from financial_system.params import apply_common_filters, int_param


class SharedDebtViewSet(viewsets.ModelViewSet):
    serializer_class = serializer.SharedDebtSerializer
    queryset = SharedDebt.objects.all()

    def get_queryset(self):
        # ACESSO por participação (membership), não por posse.
        return (
            SharedDebt.objects
            .filter(members__tenant_id=self.request.user.tenant_id)
            .distinct()
            .order_by('-id')
        )

    def create(self, request, *args, **kwargs):
        s = custom_serializer.CreateSharedDebtInputSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        return CreateSharedDebtBehavior(dict(s.validated_data), request.user).run()

    @action(detail=True, methods=['post'], url_path='invite')
    def invite(self, request, pk=None):
        shared_debt = self.get_object()  # já filtra por membership
        s = custom_serializer.InviteInputSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        return InviteBehavior(shared_debt, request.user, dict(s.validated_data)).run()

    @action(detail=False, methods=['post'], url_path='join')
    def join(self, request):
        # NÃO restringe por get_queryset: o usuário ainda não é membro.
        # O grupo é resolvido pelo token de convite dentro do behavior.
        s = custom_serializer.JoinSharedDebtInputSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        return JoinSharedDebtBehavior(dict(s.validated_data), request.user).run()

    @action(detail=True, methods=['get'], url_path='balances')
    def balances(self, request, pk=None):
        shared_debt = self.get_object()
        return BalancesBehavior(shared_debt).run()


    @action(detail=False, methods=['get'], url_path='home-summary')
    def home_summary(self, request):
        """GET /api/debts/shared-debts/home-summary/ — grupos com total e minha parte."""
        return HomeSummaryBehavior(request.user).run()

    @action(detail=True, methods=['get'], url_path='monthly-history')
    def monthly_history(self, request, pk=None):
        """GET /api/debts/shared-debts/{id}/monthly-history/ — histórico mensal."""
        shared_debt = self.get_object()
        return MonthlyHistoryBehavior(shared_debt, request.user).run()

    @action(detail=True, methods=['get', 'post'], url_path='recurring-templates')
    def recurring_templates(self, request, pk=None):
        """GET/POST /api/debts/shared-debts/{id}/recurring-templates/"""
        shared_debt = self.get_object()
        behavior = RecurringTemplateBehavior(shared_debt, request.user)
        if request.method == 'GET':
            return behavior.list()
        s = custom_serializer.SharedRecurringTemplateInputSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        return behavior.create(dict(s.validated_data))

    @action(detail=True, methods=['delete', 'patch'], url_path=r'recurring-templates/(?P<tpl_id>\d+)')
    def recurring_template_detail(self, request, pk=None, tpl_id=None):
        """DELETE/PATCH /api/debts/shared-debts/{id}/recurring-templates/{tpl_id}/"""
        shared_debt = self.get_object()
        behavior = RecurringTemplateBehavior(shared_debt, request.user)
        if request.method == 'DELETE':
            return behavior.delete(int(tpl_id))
        return behavior.toggle_active(int(tpl_id))

    @action(detail=True, methods=['post'], url_path='generate-month')
    def generate_month(self, request, pk=None):
        """POST /api/debts/shared-debts/{id}/generate-month/ body: {month, year}"""
        shared_debt = self.get_object()
        s = GenerateMonthInputSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        return RecurringTemplateBehavior(shared_debt, request.user).generate_month(**s.validated_data)

    def perform_destroy(self, instance):
        # Only the group owner may delete the group.
        if instance.owner_tenant_id != self.request.user.tenant_id:
            raise PermissionDenied("Apenas o criador do grupo pode excluí-lo.")

        # Entries must be deleted BEFORE the group's members are cascaded.
        # SharedEntry.paid_by has on_delete=PROTECT pointing to SharedDebtMember.
        # If we deleted the group directly, Django would collect members for CASCADE
        # while simultaneously seeing that SharedEntry still references them via
        # paid_by (PROTECT), raising ProtectedError (HTTP 500).
        # Deleting entries first (which also cascades SharedEntryParticipant) removes
        # that PROTECT reference, allowing the group — and then its members — to be
        # deleted cleanly.
        instance.entries.all().delete()
        instance.delete()

    @action(detail=True, methods=['get'], url_path='members')
    def members(self, request, pk=None):
        shared_debt = self.get_object()
        members_qs = shared_debt.members.all().order_by('id')
        data = serializer.SharedDebtMemberSerializer(members_qs, many=True).data
        return Response(data)

    @action(detail=True, methods=['get'], url_path='by-person')
    def by_person(self, request, pk=None):
        """
        Aba "Por pessoa": quanto cada membro deve, por fatura fechada
        (?mode=closed&month=&year=) ou previsão das faturas abertas (?mode=open).
        """
        shared_debt = self.get_object()  # já filtra por membership

        return ByPersonBehavior(
            shared_debt,
            mode=request.query_params.get('mode', 'closed'),
            month=int_param(request.query_params, 'month', 1, 12),
            year=int_param(request.query_params, 'year', 2000, 2100),
        ).run()


class SharedEntryPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


class SharedEntryViewSet(viewsets.ModelViewSet):
    serializer_class = serializer.SharedEntrySerializer
    queryset = SharedEntry.objects.all()
    pagination_class = SharedEntryPagination

    def get_queryset(self):
        qs = (
            SharedEntry.objects
            .filter(shared_debt__members__tenant_id=self.request.user.tenant_id)
            .select_related('paid_by', 'shared_debt', 'credit_card')
            # participants e members alimentam get_participant_count no
            # serializer; sem prefetch cada linha da pagina custava 2 queries.
            .prefetch_related('participants', 'shared_debt__members')
            .distinct()
            .order_by('-date', '-id')
        )

        params = self.request.query_params
        shared_debt_id = int_param(params, 'shared_debt')
        if shared_debt_id is not None:
            qs = qs.filter(shared_debt_id=shared_debt_id)
        # Subsecao "shared" da fatura do cartao: apenas entries que o usuario
        # atual pagou naquele cartao (por isso o cartao nao entra no filtro comum).
        card_id = int_param(params, 'credit_card')
        if card_id is not None:
            qs = qs.filter(credit_card_id=card_id, paid_by__tenant_id=self.request.user.tenant_id)
        qs = apply_common_filters(qs, params, SharedEntry, category_key='category', card_key='__unused__')
        return qs

    def _get_group_as_member(self, shared_debt_id):
        """Carrega o grupo garantindo que o usuário é membro (else 403)."""
        group = (
            SharedDebt.objects
            .filter(
                id=shared_debt_id,
                members__tenant_id=self.request.user.tenant_id,
            )
            .distinct()
            .first()
        )
        if group is None:
            raise PermissionDenied(
                "Você não é membro deste grupo de dívida compartilhada."
            )
        return group

    def create(self, request, *args, **kwargs):
        shared_debt_id = request.data.get('shared_debt')
        if not shared_debt_id:
            raise ValidationError({'shared_debt': ['Este campo é obrigatório.']})
        group = self._get_group_as_member(shared_debt_id)
        s = custom_serializer.CreateSharedEntryInputSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        return CreateSharedEntryBehavior(group, request.user, dict(s.validated_data)).run()

    @action(detail=False, methods=['post'], url_path='delete-installments')
    def delete_installments(self, request):
        """
        POST shared-entries/delete-installments/ {installment_group_id}

        Remove, de forma atomica, todas as parcelas de um parcelamento
        compartilhado. Mesma regra de perform_destroy: qualquer membro do
        grupo pode excluir. Participantes caem em cascata (CASCADE).
        """
        s = custom_serializer.DeleteSharedInstallmentsInputSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        group_id = s.validated_data['installment_group_id']
        qs = SharedEntry.objects.filter(
            installment_group_id=group_id,
            shared_debt__members__tenant_id=request.user.tenant_id,
        ).distinct()
        if not qs.exists():
            return Response(
                {'detail': 'Nenhuma parcela encontrada para este parcelamento.'},
                status=404,
            )
        ids = list(qs.values_list('id', flat=True))
        with transaction.atomic():
            # delete() retorna o total incluindo cascatas (participantes);
            # reportamos apenas as parcelas removidas.
            _, per_model = SharedEntry.objects.filter(id__in=ids).delete()
        deleted = per_model.get('debts.SharedEntry', 0)
        return Response({'deleted': deleted, 'installment_group_id': str(group_id)}, status=200)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        entry = self.get_object()  # membership garantida por get_queryset() (404 se nao for membro)
        s = custom_serializer.CreateSharedEntryInputSerializer(
            data=request.data, partial=partial
        )
        s.is_valid(raise_exception=True)
        return UpdateSharedEntryBehavior(entry, request.user, dict(s.validated_data), partial=partial).run()


class PersonalSummaryView(APIView):
    """
    GET /api/debts/personal-summary/

    Alimenta o bloco "Dívidas Pessoais" do frontend com os agregados
    pessoais do usuário autenticado. Thin: delega ao behavior.
    """

    def get(self, request):
        return PersonalSummaryBehavior(request.user).run()
