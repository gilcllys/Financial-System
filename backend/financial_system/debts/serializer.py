from rest_framework import serializers

from debts.models import SharedDebt, SharedDebtMember, SharedEntry, SharedRecurringTemplate


class SharedDebtSerializer(serializers.ModelSerializer):
    class Meta:
        model = SharedDebt
        fields = ['id', 'name', 'owner_tenant_id', 'created_at']
        read_only_fields = ['id', 'owner_tenant_id', 'created_at']


class SharedDebtMemberSerializer(serializers.ModelSerializer):
    class Meta:
        model = SharedDebtMember
        fields = ['id', 'shared_debt', 'tenant_id', 'display_name', 'email']
        read_only_fields = ['id', 'tenant_id']


class SharedEntrySerializer(serializers.ModelSerializer):
    paid_by_name = serializers.CharField(source='paid_by.display_name', read_only=True)
    paid_by_tenant_id = serializers.CharField(source='paid_by.tenant_id', read_only=True, default=None)
    category_name = serializers.CharField(source='category.name', read_only=True, default=None)
    shared_debt_name = serializers.CharField(source='shared_debt.name', read_only=True)
    participant_count = serializers.SerializerMethodField()
    credit_card_name = serializers.SerializerMethodField()

    def get_participant_count(self, obj):
        count = obj.participants.count()
        if count == 0:
            count = obj.shared_debt.members.count()
        return max(count, 1)

    def get_credit_card_name(self, obj):
        # So exibe o nome do cartao para o proprio pagador
        request = self.context.get('request')
        if not request or not obj.credit_card_id:
            return None
        my_tenant = getattr(request.user, 'tenant_id', None)
        if obj.paid_by.tenant_id == my_tenant:
            return obj.credit_card.name if obj.credit_card else None
        return None

    class Meta:
        model = SharedEntry
        fields = [
            'id',
            'shared_debt',
            'shared_debt_name',
            'paid_by',
            'paid_by_name',
            'paid_by_tenant_id',
            'description',
            'amount',
            'date',
            'payment_method',
            'credit_card',
            'credit_card_name',
            'category',
            'category_name',
            'participant_count',
            'installment_group_id',
            'total_installments',
            'installment_number',
            'created_by_tenant_id',
            'created_at',
        ]
        read_only_fields = [
            'id', 'created_by_tenant_id', 'created_at',
            'installment_group_id', 'total_installments', 'installment_number',
        ]


class SharedRecurringTemplateSerializer(serializers.ModelSerializer):
    paid_by_name = serializers.CharField(source='paid_by.display_name', read_only=True)
    paid_by_tenant_id = serializers.CharField(source='paid_by.tenant_id', read_only=True, default=None)
    category_name = serializers.CharField(source='category.name', read_only=True, default=None)

    class Meta:
        model = SharedRecurringTemplate
        fields = [
            'id', 'shared_debt', 'description', 'amount',
            'paid_by', 'paid_by_name',
            'paid_by_tenant_id', 'participant_ids',
            'payment_method', 'category', 'category_name',
            'day_of_month', 'is_active', 'created_at',
        ]
        read_only_fields = ['id', 'created_at']

