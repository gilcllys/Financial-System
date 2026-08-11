from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from debts import custom_serializer, serializer
from debts.behaviors import (
    BalancesBehavior,
    CreateSharedDebtBehavior,
    CreateSharedEntryBehavior,
    InviteBehavior,
    JoinSharedDebtBehavior,
    PersonalSummaryBehavior,
    UpdateSharedEntryBehavior,
)
from debts.models import SharedDebt, SharedEntry


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


class SharedEntryViewSet(viewsets.ModelViewSet):
    serializer_class = serializer.SharedEntrySerializer
    queryset = SharedEntry.objects.all()

    def get_queryset(self):
        qs = (
            SharedEntry.objects
            .filter(shared_debt__members__tenant_id=self.request.user.tenant_id)
            .select_related('paid_by', 'shared_debt', 'credit_card')
            .distinct()
            .order_by('-date', '-id')
        )

        params = self.request.query_params

        raw_shared_debt = params.get('shared_debt')
        if raw_shared_debt is not None:
            try:
                qs = qs.filter(shared_debt_id=int(raw_shared_debt))
            except (ValueError, TypeError):
                pass

        raw_credit_card = params.get('credit_card')
        if raw_credit_card is not None:
            try:
                card_id = int(raw_credit_card)
                # Subseção "shared" da fatura do cartão: apenas entries que o
                # usuário atual pagou naquele cartão.
                qs = qs.filter(
                    credit_card_id=card_id,
                    paid_by__tenant_id=self.request.user.tenant_id,
                )
            except (ValueError, TypeError):
                pass

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
            raise PermissionDenied("O campo 'shared_debt' é obrigatório.")
        group = self._get_group_as_member(shared_debt_id)
        s = custom_serializer.CreateSharedEntryInputSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        return CreateSharedEntryBehavior(group, request.user, dict(s.validated_data)).run()

    def perform_destroy(self, instance):
        is_member = instance.shared_debt.members.filter(
            tenant_id=self.request.user.tenant_id,
        ).exists()
        if not is_member:
            raise PermissionDenied(
                "Você não tem permissão para excluir este recurso."
            )
        instance.delete()

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        entry = self.get_object()  # enforces membership via get_queryset() + 404
        # Explicit membership re-check (any member may edit).
        is_member = entry.shared_debt.members.filter(
            tenant_id=request.user.tenant_id,
        ).exists()
        if not is_member:
            raise PermissionDenied(
                "Você não tem permissão para editar esta despesa."
            )
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
