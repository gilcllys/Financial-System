from django.db.models import Count, Sum
from django.db.models.functions import ExtractMonth, ExtractYear
from rest_framework import status
from rest_framework.response import Response

from catalog.constants import _MONTH_NAMES
from savings.models import SavingsDeposit, SavingsGoal
from savings import serializer as ser


def goals_with_totals(tenant_id):
    """
    Cofrinhos do tenant com os agregados de aportes ja anotados.

    O annotate evita o N+1 que existiria ao deixar o serializer agregar
    cofrinho a cofrinho.
    """
    return (
        SavingsGoal.objects
        .filter(tenant_id=tenant_id)
        .annotate(
            deposits_total=Sum('deposits__amount'),
            deposits_qty=Count('deposits'),
        )
        .order_by('id')
    )


class SavingsSummaryBehavior:
    """Consolida os totais de cofrinhos e a evolucao mensal dos aportes."""

    def __init__(self, tenant_id: str):
        self.tenant_id = tenant_id

    def _grand_total(self) -> float:
        total = (
            SavingsDeposit.objects
            .filter(tenant_id=self.tenant_id)
            .aggregate(t=Sum('amount'))['t']
        )
        return float(total or 0)

    def _monthly_breakdown(self) -> list:
        """
        Totais por mes em ordem cronologica, com o acumulado corrente.

        Aportes negativos (retiradas) reduzem o acumulado, por isso a soma
        e feita em Python sobre linhas ja ordenadas, e nao via window function.
        """
        rows = (
            SavingsDeposit.objects
            .filter(tenant_id=self.tenant_id)
            .annotate(yr=ExtractYear('date'), mo=ExtractMonth('date'))
            .values('yr', 'mo')
            .annotate(total=Sum('amount'))
            .order_by('yr', 'mo')
        )

        accumulated = 0.0
        breakdown = []
        for row in rows:
            accumulated += float(row['total'])
            breakdown.append({
                'year': row['yr'],
                'month': row['mo'],
                'month_name': _MONTH_NAMES[row['mo']],
                'total': float(row['total']),
                'accumulated': round(accumulated, 2),
            })
        return breakdown

    def build(self) -> dict:
        goals = goals_with_totals(self.tenant_id)
        return {
            'goals': ser.SavingsGoalSerializer(goals, many=True).data,
            'grand_total': round(self._grand_total(), 2),
            'monthly_breakdown': self._monthly_breakdown(),
        }


class CreateGoalBehavior:
    """Cria um cofrinho ja vinculado ao tenant autenticado."""

    def __init__(self, tenant_id: str):
        self.tenant_id = tenant_id

    def create(self, data: dict) -> Response:
        s = ser.CreateGoalInputSerializer(data=data)
        s.is_valid(raise_exception=True)
        goal = SavingsGoal.objects.create(tenant_id=self.tenant_id, **s.validated_data)
        return Response(
            ser.SavingsGoalSerializer(goal).data,
            status=status.HTTP_201_CREATED,
        )


class CreateDepositBehavior:
    """Cria um aporte, garantindo que o cofrinho pertence ao tenant."""

    def __init__(self, tenant_id: str):
        self.tenant_id = tenant_id

    def create(self, data: dict) -> Response:
        s = ser.CreateDepositInputSerializer(data=data)
        s.is_valid(raise_exception=True)
        v = s.validated_data

        try:
            goal = SavingsGoal.objects.get(
                id=v['goal_id'], tenant_id=self.tenant_id)
        except SavingsGoal.DoesNotExist:
            return Response(
                {'detail': 'Cofrinho não encontrado.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        deposit = SavingsDeposit.objects.create(
            goal=goal,
            tenant_id=self.tenant_id,
            amount=v['amount'],
            date=v['date'],
            description=v.get('description', ''),
        )
        return Response(
            ser.SavingsDepositSerializer(deposit).data,
            status=status.HTTP_201_CREATED,
        )
