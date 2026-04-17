from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.reverse import reverse
from rest_framework.routers import DefaultRouter

from expenses_module.urls import router as expenses_router

main_router = DefaultRouter()
main_router.registry.extend(expenses_router.registry)


@api_view(['GET'])
@permission_classes([AllowAny])
def api_root(request, format=None):
    data = {}
    for prefix, viewset, basename in main_router.registry:
        data[f"module-{prefix}"] = reverse(
            f"{basename}-list", request=request, format=format
        )
    return Response(data)
