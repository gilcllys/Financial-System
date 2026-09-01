from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from savings.models import SavingsDeposit
from savings import serializer as ser
from savings.behaviors import (
    CreateDepositBehavior,
    CreateGoalBehavior,
    SavingsSummaryBehavior,
    goals_with_totals,
)


class SavingsGoalViewSet(viewsets.ModelViewSet):
    serializer_class = ser.SavingsGoalSerializer

    def get_queryset(self):
        return goals_with_totals(self.request.user.tenant_id)

    def create(self, request, *args, **kwargs):
        return CreateGoalBehavior(request.user.tenant_id).create(request.data)

    @action(detail=False, methods=['get'], url_path='summary')
    def summary(self, request):
        """GET /api/savings/goals/summary/ — totais por cofrinho + breakdown mensal."""
        return Response(SavingsSummaryBehavior(request.user.tenant_id).build())


class SavingsDepositViewSet(viewsets.ModelViewSet):
    serializer_class = ser.SavingsDepositSerializer

    def get_queryset(self):
        qs = SavingsDeposit.objects.filter(
            tenant_id=self.request.user.tenant_id
        ).select_related('goal').order_by('-date', '-id')
        goal_id = self.request.query_params.get('goal')
        if goal_id:
            qs = qs.filter(goal_id=goal_id)
        return qs

    def create(self, request, *args, **kwargs):
        return CreateDepositBehavior(request.user.tenant_id).create(request.data)
