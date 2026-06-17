from rest_framework import serializers
from supermarket.models import SupermarketExpense, SupermarketExpenseItem


class SupermarketExpenseItemSerializer(serializers.ModelSerializer):
    unit_price = serializers.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        model = SupermarketExpenseItem
        fields = '__all__'
        read_only_fields = ['tenant_id']


class SupermarketExpenseSerializer(serializers.ModelSerializer):
    items = SupermarketExpenseItemSerializer(many=True, read_only=True)
    total = serializers.SerializerMethodField()

    class Meta:
        model = SupermarketExpense
        fields = '__all__'
        read_only_fields = ['tenant_id']

    def get_total(self, obj):
        return float(sum(item.unit_price * item.quantity for item in obj.items.all()))
