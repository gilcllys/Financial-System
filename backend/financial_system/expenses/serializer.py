from rest_framework import serializers
from expenses.models import Expense


class ExpenseSerializer(serializers.ModelSerializer):
    class Meta:
        model = Expense
        fields = '__all__'


class CreateExpenseInputSerializer(serializers.Serializer):
    category_id = serializers.IntegerField(required=True, allow_null=False)
    description = serializers.CharField(required=True, allow_null=False, max_length=255)
    amount = serializers.DecimalField(required=True, allow_null=False, max_digits=10, decimal_places=2)
    date = serializers.DateField(required=True, allow_null=False)
    quantity = serializers.IntegerField(required=False, default=1)
    payment_method = serializers.ChoiceField(choices=['dinheiro', 'cartao'], required=False, default='dinheiro')
    credit_card_id = serializers.IntegerField(required=False, allow_null=True, default=None)
    is_installment = serializers.BooleanField(required=False, default=False)
    installments = serializers.IntegerField(required=False, default=1)
    need_pay_vitoria = serializers.BooleanField(required=False, default=False)
