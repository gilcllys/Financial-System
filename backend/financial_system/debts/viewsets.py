
from rest_framework import viewsets
from rest_framework.pagination import PageNumberPagination
from rest_framework.decorators import action
from rest_framework.views import APIView

from debts import custom_serializer, serializer
from debts.behaviors import (
    BalancesBehavior,
    CreateSharedDebtBehavior,
    CreateSharedEntryBehavior,
    DeleteSharedDebtBehavior,
    DeleteSharedInstallmentsBehavior,
    HomeSummaryBehavior,
    InviteBehavior,
    JoinSharedDebtBehavior,
    MonthlyHistoryBehavior,
    PersonalSummaryBehavior,
    RecurringTemplateBehavior,
    SharedDebtMembersBehavior,
    SharedDebtScreenSummaryBehavior,
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
        s = custom_serializer.CreateSharedDebtInputSerializer(
            data=request.data)
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

    @action(detail=True, methods=['get'], url_path='screen-summary')
    def screen_summary(self, request, pk=None):
        group = self.get_object()
        query = custom_serializer.SharedDebtScreenQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        return SharedDebtScreenSummaryBehavior(
            group, request.user, query.validated_data, request,
        ).run()

    @action(detail=True, methods=['get'], url_path='monthly-history')
    def monthly_history(self, request, pk=None):
        """GET /api/debts/shared-debts/{id}/monthly-history/ — histórico mensal."""
        shared_debt = self.get_object()
        return MonthlyHistoryBehavior(shared_debt, request.user).run()

    @action(detail=True, methods=['get', 'post'], url_path='recurring-templates')
    def recurring_templates(self, request, pk=None):
        shared_debt = self.get_object()
        if request.method == 'GET':
            return RecurringTemplateBehavior(shared_debt, request.user, 'list').run()
        payload = custom_serializer.SharedRecurringTemplateInputSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        return RecurringTemplateBehavior(
            shared_debt, request.user, 'create', data=payload.validated_data,
        ).run()

    @action(detail=True, methods=['delete', 'patch'], url_path=r'recurring-templates/(?P<tpl_id>\d+)')
    def recurring_template_detail(self, request, pk=None, tpl_id=None):
        shared_debt = self.get_object()
        operation = 'delete' if request.method == 'DELETE' else 'toggle_active'
        return RecurringTemplateBehavior(
            shared_debt, request.user, operation, template_id=int(tpl_id),
        ).run()

    @action(detail=True, methods=['post'], url_path='generate-month')
    def generate_month(self, request, pk=None):
        shared_debt = self.get_object()
        payload = GenerateMonthInputSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        return RecurringTemplateBehavior(
            shared_debt, request.user, 'generate_month', **payload.validated_data,
        ).run()

    def perform_destroy(self, instance):
        DeleteSharedDebtBehavior(instance, self.request.user).run()

    @action(detail=True, methods=['get'], url_path='members')
    def members(self, request, pk=None):
        shared_debt = self.get_object()
        return SharedDebtMembersBehavior(shared_debt).run()

    @action(detail=True, methods=['get'], url_path='by-person')
    def by_person(self, request, pk=None):
        """
        Aba "Por pessoa": quanto cada membro deve, por fatura fechada
        (?mode=closed&month=&year=) ou previsão das faturas abertas (?mode=open).
        """
        shared_debt = self.get_object()  # já filtra por membership

        query = custom_serializer.ByPersonQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        return ByPersonBehavior(shared_debt, **query.validated_data).run()


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
            qs = qs.filter(credit_card_id=card_id,
                           paid_by__tenant_id=self.request.user.tenant_id)
        qs = apply_common_filters(
            qs, params, SharedEntry, category_key='category', card_key='__unused__')
        return qs

    def create(self, request, *args, **kwargs):
        payload = custom_serializer.SharedEntryCreateInputSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        return CreateSharedEntryBehavior(
            None, request.user, payload.validated_data,
        ).run()

    @action(detail=False, methods=['post'], url_path='delete-installments')
    def delete_installments(self, request):
        """
        POST shared-entries/delete-installments/ {installment_group_id}

        Remove, de forma atomica, todas as parcelas de um parcelamento
        compartilhado. Mesma regra de perform_destroy: qualquer membro do
        grupo pode excluir. Participantes caem em cascata (CASCADE).
        """
        payload = custom_serializer.DeleteSharedInstallmentsInputSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        return DeleteSharedInstallmentsBehavior(
            request.user.tenant_id, payload.validated_data['installment_group_id'],
        ).run()

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        # membership garantida por get_queryset() (404 se nao for membro)
        entry = self.get_object()
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
