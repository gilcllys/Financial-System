from decimal import Decimal
from django.db.models import Sum
from rest_framework import serializers
from savings.models import SavingsGoal, SavingsDeposit


def _validate_amount_not_zero(value):
    """Regra compartilhada entre criacao e edicao de aporte."""
    if value == Decimal('0'):
        raise serializers.ValidationError('Valor não pode ser zero.')
    return value


def _validate_target_amount_not_negative(value):
    """Meta pode ser nula ou zero (sem meta definida), mas nunca negativa."""
    if value is not None and value < Decimal('0'):
        raise serializers.ValidationError('Meta não pode ser negativa.')
    return value


class SavingsGoalSerializer(serializers.ModelSerializer):
    total_deposited = serializers.SerializerMethodField()
    deposit_count = serializers.SerializerMethodField()

    def get_total_deposited(self, obj):
        """Usa o agregado anotado no queryset quando disponivel (evita N+1)."""
        annotated = getattr(obj, 'deposits_total', None)
        if annotated is not None:
            return float(annotated)
        result = obj.deposits.aggregate(total=Sum('amount'))['total']
        return float(result or 0)

    def get_deposit_count(self, obj):
        """Usa o agregado anotado no queryset quando disponivel (evita N+1)."""
        annotated = getattr(obj, 'deposits_qty', None)
        if annotated is not None:
            return annotated
        return obj.deposits.count()

    class Meta:
        model = SavingsGoal
        fields = ['id', 'name', 'target_amount', 'color', 'icon',
                  'total_deposited', 'deposit_count', 'created_at']
        read_only_fields = ['id', 'created_at']

    def validate_target_amount(self, value):
        return _validate_target_amount_not_negative(value)


class SavingsDepositSerializer(serializers.ModelSerializer):
    goal_name = serializers.CharField(source='goal.name', read_only=True)

    class Meta:
        model = SavingsDeposit
        fields = ['id', 'goal', 'goal_name', 'amount', 'date', 'description', 'created_at']
        read_only_fields = ['id', 'created_at']

    def get_fields(self):
        """
        Restringe o campo `goal` aos cofrinhos do tenant autenticado.

        Sem isso o ModelSerializer usa SavingsGoal.objects.all() e permite,
        via PATCH, repontar um aporte proprio para o cofrinho de OUTRO tenant.
        """
        fields = super().get_fields()
        request = self.context.get('request')
        tenant_id = getattr(getattr(request, 'user', None), 'tenant_id', None)
        if tenant_id is not None:
            fields['goal'].queryset = SavingsGoal.objects.filter(tenant_id=tenant_id)
        else:
            fields['goal'].queryset = SavingsGoal.objects.none()
        return fields

    def validate_amount(self, value):
        return _validate_amount_not_zero(value)


class CreateGoalInputSerializer(serializers.Serializer):
    name = serializers.CharField(required=True, max_length=120)
    target_amount = serializers.DecimalField(
        required=False, allow_null=True, default=None, max_digits=12, decimal_places=2)
    color = serializers.CharField(required=False, default='#6366f1', max_length=7)
    icon = serializers.CharField(required=False, default='🐷', max_length=10)

    def validate_target_amount(self, value):
        return _validate_target_amount_not_negative(value)


class CreateDepositInputSerializer(serializers.Serializer):
    goal_id = serializers.IntegerField(required=True)
    amount = serializers.DecimalField(
        required=True, max_digits=12, decimal_places=2)
    date = serializers.DateField(required=True)
    description = serializers.CharField(required=False, default='', allow_blank=True, max_length=255)

    def validate_amount(self, value):
        return _validate_amount_not_zero(value)
