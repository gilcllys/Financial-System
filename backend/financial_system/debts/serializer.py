from rest_framework import serializers
from debts.models import VitoriaDebt


class VitoriaDebtSerializer(serializers.ModelSerializer):
    class Meta:
        model = VitoriaDebt
        fields = '__all__'
