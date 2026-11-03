from rest_framework import viewsets
from rest_framework.decorators import action

from cards import models, serializer
from cards.behaviors import (
    CreditCardInvoiceViewBehavior,
    InvoiceExpensesBehavior,
    InvoicesBehavior,
    OpenInvoicesBehavior,
)


class CreditCardViewSet(viewsets.ModelViewSet):
    serializer_class = serializer.CreditCardSerializer
    queryset = models.CreditCard.objects.all()

    def get_queryset(self):
        return models.CreditCard.objects.filter(tenant_id=self.request.user.tenant_id)

    def perform_create(self, serializer):
        serializer.save(tenant_id=self.request.user.tenant_id)

    def perform_update(self, serializer):
        """[SEC-A01] Defense-in-depth: garante que tenant_id não muda em updates."""
        serializer.save(tenant_id=self.request.user.tenant_id)

    @action(detail=True, methods=['get'], url_path='invoices')
    def invoices(self, request, pk=None):
        return InvoicesBehavior(self.get_object()).run()

    @action(detail=True, methods=['get'], url_path='invoice-expenses')
    def invoice_expenses(self, request, pk=None):
        query = serializer.InvoiceExpensesQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        params = query.validated_data
        return InvoiceExpensesBehavior(
            self.get_object(), params['invoice_month'], params['invoice_year'],
            category_id=params.get('category_id'), page=params['page'],
            page_size=params['page_size'], search=params.get('search'),
        ).run()

    @action(detail=True, methods=['get'], url_path='invoice-view')
    def invoice_view(self, request, pk=None):
        query = serializer.InvoiceViewQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        return CreditCardInvoiceViewBehavior(
            self.get_object(), request, query.validated_data,
        ).run()

    @action(detail=False, methods=['get'], url_path='open-invoices')
    def open_invoices(self, request):
        query = serializer.OpenInvoicesQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        return OpenInvoicesBehavior(
            request.user.tenant_id, **query.validated_data,
        ).run()
