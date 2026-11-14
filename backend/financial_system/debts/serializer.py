from datetime import date

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
    participant_ids = serializers.SerializerMethodField()
    credit_card_name = serializers.SerializerMethodField()
    recurring_template_id = serializers.IntegerField(read_only=True, allow_null=True)
    is_recurrent = serializers.BooleanField(read_only=True)
    invoice_paid = serializers.SerializerMethodField()

    def get_participant_count(self, obj):
        return len(obj.participant_ids()) or 1

    def get_participant_ids(self, obj):
        return obj.participant_ids()

    def get_credit_card_name(self, obj):
        # So exibe o nome do cartao para o proprio pagador
        request = self.context.get('request')
        if not request or not obj.credit_card_id:
            return None
        my_tenant = getattr(request.user, 'tenant_id', None)
        if obj.paid_by.tenant_id == my_tenant:
            return obj.credit_card.name if obj.credit_card else None
        return None

    @staticmethod
    def invoice_paid_by_due_date(obj, today=None):
        """Infer card-fatura payment from its due date, without changing reimbursement."""
        if obj.payment_method != 'cartao' or not obj.credit_card:
            return False

        from cards.behaviors import _effective_closing_date, compute_invoice_period, shift_month

        closing_month, closing_year = obj.date.month, obj.date.year
        if obj.date > _effective_closing_date(closing_year, closing_month, obj.credit_card.closing_day):
            closing_month, closing_year = shift_month(closing_month, closing_year, 1)
        invoice_month, invoice_year = shift_month(closing_month, closing_year, 1)
        _, _, due_date = compute_invoice_period(obj.credit_card, invoice_month, invoice_year)
        return due_date <= (today or date.today())

    def get_invoice_paid(self, obj):
        return self.invoice_paid_by_due_date(obj)

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
            'participant_ids',
            'installment_group_id',
            'total_installments',
            'installment_number',
            'paid',
            'invoice_paid',
            'recurring_template_id',
            'is_recurrent',
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
    credit_card_id = serializers.IntegerField(read_only=True, allow_null=True)
    credit_card_name = serializers.CharField(source='credit_card.name', read_only=True, allow_null=True)

    class Meta:
        model = SharedRecurringTemplate
        fields = [
            'id', 'shared_debt', 'description', 'amount',
            'paid_by', 'paid_by_name',
            'paid_by_tenant_id', 'participant_ids',
            'payment_method', 'credit_card_id', 'credit_card_name', 'category', 'category_name',
            'day_of_month', 'is_active', 'created_at',
        ]
        read_only_fields = ['id', 'created_at']

