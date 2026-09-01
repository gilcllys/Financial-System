from django.db.models import Sum
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from savings.models import SavingsDeposit, SavingsGoal
from catalog.constants import _MONTH_NAMES
from savings import serializer as ser

class SavingsGoalViewSet(viewsets.ModelViewSet):
    serializer_class = ser.SavingsGoalSerializer

    def get_queryset(self):
        return SavingsGoal.objects.filter(
            tenant_id=self.request.user.tenant_id
        ).prefetch_related('deposits').order_by('id')

    def perform_create(self, serializer_obj):
        serializer_obj.save(tenant_id=self.request.user.tenant_id)

    def create(self, request, *args, **kwargs):
        s = ser.CreateGoalInputSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        goal = SavingsGoal.objects.create(
            tenant_id=request.user.tenant_id, **s.validated_data)
        return Response(ser.SavingsGoalSerializer(goal).data, status=status.HTTP_201_CREATED)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.tenant_id != request.user.tenant_id:
            return Response(status=status.HTTP_403_FORBIDDEN)
        instance.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=False, methods=['get'], url_path='summary')
    def summary(self, request):
        """GET /api/savings/goals/summary/ — totais por cofrinho + breakdown mensal."""
        tenant = request.user.tenant_id
        goals = SavingsGoal.objects.filter(tenant_id=tenant).prefetch_related('deposits')
        grand_total = float(
            SavingsDeposit.objects.filter(tenant_id=tenant)
            .aggregate(t=Sum('amount'))['t'] or 0
        )

        # Monthly breakdown with accumulated
        from django.db.models.functions import ExtractYear, ExtractMonth
        rows = (
            SavingsDeposit.objects
            .filter(tenant_id=tenant)
            .annotate(yr=ExtractYear('date'), mo=ExtractMonth('date'))
            .values('yr', 'mo')
            .annotate(total=Sum('amount'))
            .order_by('yr', 'mo')
        )
        accumulated = 0.0
        monthly_breakdown = []
        for row in rows:
            accumulated += float(row['total'])
            monthly_breakdown.append({
                'year': row['yr'],
                'month': row['mo'],
                'month_name': _MONTH_NAMES[row['mo']],
                'total': float(row['total']),
                'accumulated': round(accumulated, 2),
            })

        return Response({
            'goals': ser.SavingsGoalSerializer(goals, many=True).data,
            'grand_total': round(grand_total, 2),
            'monthly_breakdown': monthly_breakdown,
        })


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
        s = ser.CreateDepositInputSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data
        # Verify goal belongs to tenant
        try:
            goal = SavingsGoal.objects.get(id=v['goal_id'], tenant_id=request.user.tenant_id)
        except SavingsGoal.DoesNotExist:
            return Response({'detail': 'Cofrinho não encontrado.'}, status=status.HTTP_404_NOT_FOUND)
        deposit = SavingsDeposit.objects.create(
            goal=goal,
            tenant_id=request.user.tenant_id,
            amount=v['amount'],
            date=v['date'],
            description=v.get('description', ''),
        )
        return Response(ser.SavingsDepositSerializer(deposit).data, status=status.HTTP_201_CREATED)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.tenant_id != request.user.tenant_id:
            return Response(status=status.HTTP_403_FORBIDDEN)
        instance.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
