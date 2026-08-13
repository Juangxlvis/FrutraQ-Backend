from rest_framework.routers import DefaultRouter
from .views import (
    ProductoViewSet, ProveedorViewSet, ClienteViewSet, PrecioClienteViewSet,
    ViajeViewSet, PuntoRecoleccionViewSet, LoteCargaViewSet,
    EntregaViewSet, DetalleEntregaViewSet, FacturaViewSet,
)

router = DefaultRouter()
router.register('productos', ProductoViewSet)
router.register('proveedores', ProveedorViewSet)
router.register('clientes', ClienteViewSet)
router.register('precios-cliente', PrecioClienteViewSet)
router.register('viajes', ViajeViewSet)
router.register('puntos-recoleccion', PuntoRecoleccionViewSet)
router.register('lotes-carga', LoteCargaViewSet)
router.register('entregas', EntregaViewSet)
router.register('detalles-entrega', DetalleEntregaViewSet)
router.register('facturas', FacturaViewSet)

urlpatterns = router.urls