from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.reverse import reverse
from rest_framework.routers import DefaultRouter

# Importe os roteadores dos seus módulos
from user_module.urls import router as user_router
from expenses_module.urls import router as expenses_router


# 1. Criamos um Roteador Central para unificar os módulos
main_router = DefaultRouter()
main_router.registry.extend(user_router.registry)
main_router.registry.extend(expenses_router.registry)


@api_view(['GET'])
@permission_classes([AllowAny])  # Aberta para o público
def api_root(request, format=None):
    # Começamos com as rotas que não estão nos ViewSets (Manuais)
    data = {
        'auth-register': reverse('register', request=request, format=format),
        'auth-login': reverse('login', request=request, format=format),
        'auth-logout': reverse('logout', request=request, format=format),
        'auth-token-refresh': reverse('token_refresh', request=request, format=format),
    }

    # Adicionamos dinamicamente TUDO que estiver registrado no main_router
    # O loop percorre o registry e monta os nomes (ex: expense-list)
    for prefix, viewset, basename in main_router.registry:
        data[f"module-{prefix}"] = reverse(f"{basename}-list",
                                           request=request, format=format)

    return Response(data)
