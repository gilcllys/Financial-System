from rest_framework import serializers
from supermarket.models import SupermarketExpense, SupermarketExpenseItem


class SupermarketExpenseItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = SupermarketExpenseItem
        fields = '__all__'


class SupermarketExpenseSerializer(serializers.ModelSerializer):
    items = SupermarketExpenseItemSerializer(many=True, read_only=True)

    class Meta:
        model = SupermarketExpense
        fields = '__all__'
