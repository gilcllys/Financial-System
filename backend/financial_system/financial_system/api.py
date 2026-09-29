"""
Helpers HTTP pequenos usados pelos behaviors (evita repetir try/except
DoesNotExist + Response 404 em cada metodo).
"""
from rest_framework import status
from rest_framework.response import Response


def not_found(detail: str = 'Recurso não encontrado.') -> Response:
    return Response({'detail': detail}, status=status.HTTP_404_NOT_FOUND)


def get_or_404(queryset, detail: str = 'Recurso não encontrado.', **lookup):
    """(obj, None) se existir; (None, Response 404) caso contrario."""
    obj = queryset.filter(**lookup).first()
    if obj is None:
        return None, not_found(detail)
    return obj, None
