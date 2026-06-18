from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.reverse import reverse
from rest_framework.routers import DefaultRouter


def _build_main_router():
    """
    Lazily imports each domain router so that this module can be imported
    even before all apps are fully initialised (e.g. during startapp).
    """
    from catalog.urls import router as catalog_router
    from cards.urls import router as cards_router
    from expenses.urls import router as expenses_router
    from debts.urls import router as debts_router
    from supermarket.urls import router as supermarket_router

    router = DefaultRouter()
    for r in (catalog_router, cards_router, expenses_router, debts_router, supermarket_router):
        router.registry.extend(r.registry)
    return router


@api_view(['GET'])
@permission_classes([AllowAny])
def api_root(request, format=None):
    main_router = _build_main_router()
    data = {}
    for prefix, viewset, basename in main_router.registry:
        data[f"module-{prefix}"] = reverse(
            f"{basename}-list", request=request, format=format
        )
    return Response(data)
