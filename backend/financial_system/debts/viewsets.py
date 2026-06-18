from django.db.models import Count, Q, Sum
from django.db.models.functions import Abs
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from debts import models, serializer


class VitoriaDebtViewSet(viewsets.ModelViewSet):
    serializer_class = serializer.VitoriaDebtSerializer
    queryset = models.VitoriaDebt.objects.all()

    def get_queryset(self):
        return (
            models.VitoriaDebt.objects
            .filter(tenant_id=self.request.user.tenant_id)
            # select_related evita N+1 ao acessar expense e category inline
            .select_related('expense', 'expense__category')
            .order_by('-id')
        )

    def perform_create(self, serializer):
        """
        Injeta tenant_id e valida ownership da Expense vinculada.

        [SEC-A01] IDOR: sem esta validação, um usuário poderia criar uma dívida
        apontando para a Expense de outro tenant (o PrimaryKeyRelatedField aceita
        qualquer ID válido do banco por padrão).
        """
        expense = serializer.validated_data.get('expense')
        if expense and expense.tenant_id != self.request.user.tenant_id:
            raise PermissionDenied(
                "A despesa vinculada não pertence ao usuário autenticado."
            )
        serializer.save(tenant_id=self.request.user.tenant_id)

    def perform_update(self, serializer):
        """[SEC-A01] Defense-in-depth: garante ownership também em updates."""
        expense = serializer.validated_data.get('expense')
        if expense and expense.tenant_id != self.request.user.tenant_id:
            raise PermissionDenied(
                "A despesa vinculada não pertence ao usuário autenticado."
            )
        serializer.save(tenant_id=self.request.user.tenant_id)

    # ------------------------------------------------------------------
    # Analytics / helpers
    # ------------------------------------------------------------------

    @action(detail=False, methods=['get'], url_path='summary')
    def perform_destroy(self, instance):
        if instance.tenant_id != self.request.user.tenant_id:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Você não tem permissão para excluir este recurso.")
        instance.delete()

    def summary(self, request):
        """
        GET /api/debts/vitoria-debts/summary/

        Retorna totais consolidados de dívidas pendentes e pagas do tenant.

        Response:
          {
            "total_pending": 450.00,
            "total_paid":    120.00,
            "count_pending": 5,
            "count_paid":    2
          }
        """
        qs = models.VitoriaDebt.objects.filter(
            tenant_id=request.user.tenant_id,
        ).select_related('expense')

        agg = qs.aggregate(
            total_pending=Sum(
                Abs('expense__amount'),
                filter=Q(is_paid=False),
            ),
            total_paid=Sum(
                Abs('expense__amount'),
                filter=Q(is_paid=True),
            ),
            count_pending=Count('id', filter=Q(is_paid=False)),
            count_paid=Count('id', filter=Q(is_paid=True)),
        )

        data = {
            'total_pending': round(float(agg['total_pending'] or 0), 2),
            'total_paid': round(float(agg['total_paid'] or 0), 2),
            'count_pending': agg['count_pending'],
            'count_paid': agg['count_paid'],
        }

        return Response(data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='mark-paid')
    def mark_paid(self, request, pk=None):
        """
        POST /api/debts/vitoria-debts/{id}/mark-paid/

        Marca uma dívida específica do tenant como paga.
        Não requer body na requisição.

        Response:
          { "success": true, "message": "Dívida marcada como paga" }
        """
        debt = self.get_object()  # já filtra por tenant via get_queryset
        debt.is_paid = True
        debt.save(update_fields=['is_paid'])

        return Response(
            {'success': True, 'message': 'Dívida marcada como paga'},
            status=status.HTTP_200_OK,
        )
