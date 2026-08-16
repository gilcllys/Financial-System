from rest_framework import serializers

from debts.models import SharedDebt, SharedDebtMember, SharedEntry, SharedRecurringTemplate


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
    paid_by_name = serializers.CharField(
        source='paid_by.display_name',
        read_only=True,
    )
    category_name = serializers.CharField(
        source='category.name',
        read_only=True,
        default=None,
    )
    shared_debt_name = serializers.CharField(
        source='shared_debt.name',
        read_only=True,
    )
    participant_count = serializers.SerializerMethodField()

    def get_participant_count(self, obj):
        return obj.participants.count()

    class Meta:
        model = SharedEntry
        fields = [
            'id',
            'shared_debt',
            'shared_debt_name',
            'paid_by',
            'paid_by_name',
            'description',
            'amount',
            'date',
            'payment_method',
            'credit_card',
            'category',
            'category_name',
            'participant_count',
            'created_by_tenant_id',
            'created_at',
        ]
        read_only_fields = ['id', 'created_by_tenant_id', 'created_at']


class SharedRecurringTemplateSerializer(serializers.ModelSerializer):
    paid_by_name = serializers.CharField(source='paid_by.display_name', read_only=True)
    category_name = serializers.CharField(source='category.name', read_only=True, default=None)

    class Meta:
        model = SharedRecurringTemplate
        fields = [
            'id', 'shared_debt', 'description', 'amount',
            'paid_by', 'paid_by_name', 'participant_ids',
            'payment_method', 'category', 'category_name',
            'day_of_month', 'is_active', 'created_at',
        ]
        read_only_fields = ['id', 'created_at']
