from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError

from .models import (
    Producto, Proveedor, Cliente, PrecioCliente,
    Viaje, PuntoRecoleccion, LoteCarga,
    Entrega, DetalleEntrega, Factura,
    EstadoViaje, EstadoPago,
)
from .serializers import (
    ProductoSerializer, ProveedorSerializer, ClienteSerializer, PrecioClienteSerializer,
    ViajeSerializer, PuntoRecoleccionSerializer, LoteCargaSerializer,
    EntregaSerializer, DetalleEntregaSerializer, DetalleEntregaCreateSerializer,
    FacturaSerializer,
)


class ProductoViewSet(viewsets.ModelViewSet):
    queryset = Producto.objects.all()
    serializer_class = ProductoSerializer
    filterset_fields = ['activo']


class ProveedorViewSet(viewsets.ModelViewSet):
    queryset = Proveedor.objects.all()
    serializer_class = ProveedorSerializer
    filterset_fields = ['activo', 'tipo_servicio_habitual']


class ClienteViewSet(viewsets.ModelViewSet):
    queryset = Cliente.objects.all()
    serializer_class = ClienteSerializer
    filterset_fields = ['activo']


class PrecioClienteViewSet(viewsets.ModelViewSet):
    queryset = PrecioCliente.objects.all()
    serializer_class = PrecioClienteSerializer
    filterset_fields = ['cliente', 'producto']


class ViajeViewSet(viewsets.ModelViewSet):
    queryset = Viaje.objects.all()
    serializer_class = ViajeSerializer
    filterset_fields = ['estado', 'vehiculo']

    # Grafo de transiciones válidas — el paso 9 pendiente, cerrado aquí.
    TRANSICIONES_VALIDAS = {
        EstadoViaje.RECOLECCION: [EstadoViaje.TRANSITO, EstadoViaje.CANCELADO],
        EstadoViaje.TRANSITO: [EstadoViaje.ENTREGADO, EstadoViaje.CANCELADO],
        EstadoViaje.ENTREGADO: [],
        EstadoViaje.CANCELADO: [],
    }

    def _cambiar_estado(self, viaje, nuevo_estado):
        permitidos = self.TRANSICIONES_VALIDAS.get(viaje.estado, [])
        if nuevo_estado not in permitidos:
            raise ValidationError(
                f'No se puede pasar de "{viaje.get_estado_display()}" a "{EstadoViaje(nuevo_estado).label}".'
            )
        viaje.estado = nuevo_estado
        viaje.save(update_fields=['estado', 'actualizado_en'])

    @action(detail=True, methods=['post'], url_path='marcar-transito')
    def marcar_transito(self, request, pk=None):
        viaje = self.get_object()
        self._cambiar_estado(viaje, EstadoViaje.TRANSITO)
        return Response(self.get_serializer(viaje).data)

    @action(detail=True, methods=['post'], url_path='marcar-entregado')
    def marcar_entregado(self, request, pk=None):
        viaje = self.get_object()
        self._cambiar_estado(viaje, EstadoViaje.ENTREGADO)
        return Response(self.get_serializer(viaje).data)

    @action(detail=True, methods=['post'])
    def cancelar(self, request, pk=None):
        viaje = self.get_object()
        self._cambiar_estado(viaje, EstadoViaje.CANCELADO)
        return Response(self.get_serializer(viaje).data)

    @action(detail=True, methods=['get'])
    def puntos(self, request, pk=None):
        viaje = self.get_object()
        data = PuntoRecoleccionSerializer(viaje.puntos.all(), many=True).data
        return Response(data)

    @action(detail=True, methods=['get'])
    def entregas(self, request, pk=None):
        viaje = self.get_object()
        data = EntregaSerializer(viaje.entregas.all(), many=True).data
        return Response(data)


class PuntoRecoleccionViewSet(viewsets.ModelViewSet):
    queryset = PuntoRecoleccion.objects.all()
    serializer_class = PuntoRecoleccionSerializer
    filterset_fields = ['viaje', 'proveedor', 'tipo_servicio']

    @action(detail=True, methods=['get'])
    def lotes(self, request, pk=None):
        punto = self.get_object()
        data = LoteCargaSerializer(punto.lotes.all(), many=True).data
        return Response(data)


class LoteCargaViewSet(viewsets.ModelViewSet):
    queryset = LoteCarga.objects.all()
    serializer_class = LoteCargaSerializer
    filterset_fields = ['punto_recoleccion', 'producto', 'calidad']


class EntregaViewSet(viewsets.ModelViewSet):
    queryset = Entrega.objects.all()
    serializer_class = EntregaSerializer
    filterset_fields = ['viaje', 'cliente', 'estado_pago']

    @action(detail=True, methods=['get'])
    def detalles(self, request, pk=None):
        entrega = self.get_object()
        data = DetalleEntregaSerializer(entrega.detalles.all(), many=True).data
        return Response(data)


class DetalleEntregaViewSet(viewsets.ModelViewSet):
    queryset = DetalleEntrega.objects.all()
    filterset_fields = ['entrega', 'producto']

    def get_serializer_class(self):
        if self.action == 'create':
            return DetalleEntregaCreateSerializer
        return DetalleEntregaSerializer


class FacturaViewSet(viewsets.ModelViewSet):
    queryset = Factura.objects.all()
    serializer_class = FacturaSerializer
    filterset_fields = ['entrega', 'numero_factura']

    @action(detail=True, methods=['post'], url_path='marcar-pagado')
    def marcar_pagado(self, request, pk=None):
        factura = self.get_object()
        factura.entrega.estado_pago = EstadoPago.PAGADO
        factura.entrega.save(update_fields=['estado_pago'])
        return Response(FacturaSerializer(factura).data)