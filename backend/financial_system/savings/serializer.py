from decimal import Decimal
from rest_framework import serializers
from savings.models import SavingsGoal, SavingsDeposit


class SavingsGoalSerializer(serializers.ModelSerializer):
    total_deposited = serializers.SerializerMethodField()
    deposit_count = serializers.SerializerMethodField()

    def get_total_deposited(self, obj):
        from django.db.models import Sum
        result = obj.deposits.aggregate(total=Sum('amount'))['total']
        return float(result or 0)

    def get_deposit_count(self, obj):
        return obj.deposits.count()

    class Meta:
        model = SavingsGoal
        fields = ['id', 'name', 'target_amount', 'color', 'icon',
                  'total_deposited', 'deposit_count', 'created_at']
        read_only_fields = ['id', 'created_at']


class SavingsDepositSerializer(serializers.ModelSerializer):
    goal_name = serializers.CharField(source='goal.name', read_only=True)

    class Meta:
        model = SavingsDeposit
        fields = ['id', 'goal', 'goal_name', 'amount', 'date', 'description', 'created_at']
        read_only_fields = ['id', 'created_at']


class CreateGoalInputSerializer(serializers.Serializer):
    name = serializers.CharField(required=True, max_length=120)
    target_amount = serializers.DecimalField(
        required=False, allow_null=True, default=None, max_digits=12, decimal_places=2)
    color = serializers.CharField(required=False, default='#6366f1', max_length=7)
    icon = serializers.CharField(required=False, default='🐷', max_length=10)


class CreateDepositInputSerializer(serializers.Serializer):
    goal_id = serializers.IntegerField(required=True)
    amount = serializers.DecimalField(
        required=True, max_digits=12, decimal_places=2)
    date = serializers.DateField(required=True)
    description = serializers.CharField(required=False, default='', allow_blank=True, max_length=255)

    def validate_amount(self, value):
        if value == Decimal('0'):
            raise serializers.ValidationError('Valor não pode ser zero.')
        return value
