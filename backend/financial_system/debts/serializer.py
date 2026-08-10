from rest_framework import serializers

from debts.models import SharedDebt, SharedDebtMember, SharedEntry


class SharedDebtSerializer(serializers.ModelSerializer):
    class Meta:
        model = SharedDebt
        fields = [
            'id',
            'name',
            'owner_tenant_id',
            'created_at',
        ]
        read_only_fields = ['id', 'owner_tenant_id', 'created_at']


class SharedDebtMemberSerializer(serializers.ModelSerializer):
    class Meta:
        model = SharedDebtMember
        fields = [
            'id',
            'shared_debt',
            'tenant_id',
            'display_name',
            'email',
        ]
        read_only_fields = ['id', 'tenant_id']


class SharedEntrySerializer(serializers.ModelSerializer):
    # Helper de leitura: nome do membro que pagou (evita lookup extra no cliente)
    paid_by_name = serializers.CharField(
        source='paid_by.display_name',
        read_only=True,
    )

    class Meta:
        model = SharedEntry
        fields = [
            'id',
            'shared_debt',
            'paid_by',
            'paid_by_name',
            'description',
            'amount',
            'date',
            'payment_method',
            'credit_card',
            'created_by_tenant_id',
            'created_at',
        ]
        read_only_fields = ['id', 'created_by_tenant_id', 'created_at']
