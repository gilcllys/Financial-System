from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from cards import models, serializer
from cards.behaviors import InvoiceExpensesBehavior, InvoicesBehavior


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

    def perform_destroy(self, instance):
        if instance.tenant_id != self.request.user.tenant_id:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Você não tem permissão para excluir este recurso.")
        instance.delete()

    # ------------------------------------------------------------------
    # Invoice actions
    # ------------------------------------------------------------------

    @action(detail=True, methods=['get'], url_path='invoices')
    def invoices(self, request, pk=None):
        """GET /api/cards/credit-cards/{id}/invoices/"""
        card = self._get_card_or_404(pk, request.user.tenant_id)
        if isinstance(card, Response):
            return card
        return InvoicesBehavior(card).run()

    @action(detail=True, methods=['get'], url_path='invoice-expenses')
    def invoice_expenses(self, request, pk=None):
        """
        GET /api/cards/credit-cards/{id}/invoice-expenses/
            ?invoice_month=7&invoice_year=2026[&category_id=1]
        """
        card = self._get_card_or_404(pk, request.user.tenant_id)
        if isinstance(card, Response):
            return card

        invoice_month, err = self._parse_int_param(
            request.query_params.get('invoice_month'),
            'invoice_month', required=True, min_val=1, max_val=12,
        )
        if err:
            return err

        invoice_year, err = self._parse_int_param(
            request.query_params.get('invoice_year'),
            'invoice_year', required=True, min_val=1,
        )
        if err:
            return err

        category_id, err = self._parse_int_param(
            request.query_params.get('category_id'),
            'category_id', required=False,
        )
        if err:
            return err

        page, err = self._parse_int_param(
            request.query_params.get('page'), 'page', required=False, min_val=1,
        )
        if err:
            return err
        page_size, err = self._parse_int_param(
            request.query_params.get('page_size'), 'page_size', required=False, min_val=1, max_val=100,
        )
        if err:
            return err

        return InvoiceExpensesBehavior(
            card, invoice_month, invoice_year, category_id,
            page=page or 1, page_size=page_size or 20,
        ).run()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_card_or_404(self, pk, tenant_id):
        try:
            return models.CreditCard.objects.get(pk=pk, tenant_id=tenant_id)
        except models.CreditCard.DoesNotExist:
            return Response({'detail': 'Cartão não encontrado.'}, status=status.HTTP_404_NOT_FOUND)

    @staticmethod
    def _parse_int_param(raw, name, *, required=False, min_val=None, max_val=None):
        """Retorna (value, None) em sucesso ou (None, Response) em erro."""
        if raw is None:
            if required:
                return None, Response(
                    {'detail': f'{name} é obrigatório.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            return None, None
        try:
            value = int(raw)
        except (ValueError, TypeError):
            return None, Response(
                {'detail': f'{name} deve ser um inteiro.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if min_val is not None and value < min_val:
            return None, Response(
                {'detail': f'{name} deve ser >= {min_val}.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if max_val is not None and value > max_val:
            return None, Response(
                {'detail': f'{name} deve ser <= {max_val}.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return value, None
