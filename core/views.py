from decimal import Decimal
from django.db.models import Sum, F
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError

from .models import (
    LiquidacionProveedor, Producto, Proveedor, Cliente, PrecioCliente,
    Viaje, PuntoRecoleccion, LoteCarga,
    Entrega, DetalleEntrega, Factura, Configuracion,
    EstadoViaje, EstadoPago, TipoServicio, Calidad,
)

from .serializers import (
    DetalleEntregaUpdateSerializer, LiquidacionProveedorSerializer, ProductoSerializer, ProveedorSerializer, ClienteSerializer, PrecioClienteSerializer,
    ConfiguracionSerializer,
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


class ConfiguracionViewSet(viewsets.ModelViewSet):
    queryset = Configuracion.objects.all()
    serializer_class = ConfiguracionSerializer


class ViajeViewSet(viewsets.ModelViewSet):
    queryset = Viaje.objects.all()
    serializer_class = ViajeSerializer
    filterset_fields = ['estado', 'vehiculo']

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

    def _calcular_inventario(self, viaje):
        Q2 = Decimal('0.01')
        lotes = LoteCarga.objects.filter(punto_recoleccion__viaje=viaje)
        detalles = DetalleEntrega.objects.filter(punto_recoleccion__viaje=viaje).select_related('punto_recoleccion')

        recolectado = {}
        recolectado_primera = {}
        recolectado_segunda = {}
        pagado_compra = {}
        for lote in lotes:
            clave = (str(lote.punto_recoleccion_id), str(lote.producto_id))
            recolectado[clave] = recolectado.get(clave, Decimal('0')) + lote.peso_recoleccion_kg
            if lote.calidad == Calidad.PRIMERA:
                recolectado_primera[clave] = recolectado_primera.get(clave, Decimal('0')) + lote.peso_recoleccion_kg
            else:
                recolectado_segunda[clave] = recolectado_segunda.get(clave, Decimal('0')) + lote.peso_recoleccion_kg
            if lote.precio_compra_kg:
                pagado_compra[clave] = pagado_compra.get(clave, Decimal('0')) + (lote.precio_compra_kg * lote.peso_recoleccion_kg)

        entregado_kg, entregado_primera, entregado_segunda = {}, {}, {}
        cobrado_cliente, pagado_flete = {}, {}
        for d in detalles:
            clave = (str(d.punto_recoleccion_id), str(d.producto_id))
            total_kg = d.kg_primera_recibida + d.kg_segunda_recibida
            entregado_kg[clave] = entregado_kg.get(clave, Decimal('0')) + total_kg
            entregado_primera[clave] = entregado_primera.get(clave, Decimal('0')) + d.kg_primera_recibida
            entregado_segunda[clave] = entregado_segunda.get(clave, Decimal('0')) + d.kg_segunda_recibida
            cobrado_cliente[clave] = cobrado_cliente.get(clave, Decimal('0')) + d.subtotal
            if d.subtotal_proveedor is not None:
                pagado_flete[clave] = pagado_flete.get(clave, Decimal('0')) + d.subtotal_proveedor

        puntos_meta = {str(p.id): p for p in PuntoRecoleccion.objects.filter(viaje=viaje).select_related('proveedor')}
        claves = set(recolectado) | set(entregado_kg)
        productos_map = {str(p.id): p.nombre for p in Producto.objects.filter(id__in={c[1] for c in claves})}

        detalle_por_proveedor = []
        resumen_global = {}

        for punto_id, producto_id in claves:
            punto = puntos_meta.get(punto_id)
            rec = recolectado.get((punto_id, producto_id), Decimal('0'))
            ent = entregado_kg.get((punto_id, producto_id), Decimal('0'))
            cobrado = cobrado_cliente.get((punto_id, producto_id), Decimal('0'))

            if punto and punto.tipo_servicio == TipoServicio.COMPRA:
                pagado = pagado_compra.get((punto_id, producto_id))
            elif punto and punto.tipo_servicio == TipoServicio.FLETE:
                pagado = pagado_flete.get((punto_id, producto_id))
            else:
                pagado = None

            if pagado is not None:
                pagado = pagado.quantize(Q2)
            ganancia = (cobrado - pagado).quantize(Q2) if pagado is not None else None
            tarifa_efectiva = (pagado / rec).quantize(Q2) if (pagado is not None and rec > 0) else None

            detalle_por_proveedor.append({
                'punto_recoleccion_id': punto_id,
                'proveedor_id': str(punto.proveedor_id) if punto else None,
                'proveedor_nombre': punto.proveedor.nombre if punto else '?',
                'tipo_servicio': punto.tipo_servicio if punto else None,
                'producto_id': producto_id,
                'producto_nombre': productos_map.get(producto_id, '?'),
                'recolectado_kg': str(rec),
                'recolectado_primera_kg': str(recolectado_primera.get((punto_id, producto_id), Decimal('0'))),
                'recolectado_segunda_kg': str(recolectado_segunda.get((punto_id, producto_id), Decimal('0'))),
                'entregado_kg': str(ent),
                'entregado_primera_kg': str(entregado_primera.get((punto_id, producto_id), Decimal('0'))),
                'entregado_segunda_kg': str(entregado_segunda.get((punto_id, producto_id), Decimal('0'))),
                'disponible_kg': str(rec - ent),
                'cobrado_cliente': str(cobrado),
                'pagado_proveedor': str(pagado) if pagado is not None else None,
                'ganancia_transportador': str(ganancia) if ganancia is not None else None,
                'margen_flete_kg': str(punto.margen_flete_kg) if (punto and punto.margen_flete_kg is not None) else None,
                'tarifa_efectiva_kg': str(tarifa_efectiva) if tarifa_efectiva is not None else None,
            })

            acumulado = resumen_global.setdefault(producto_id, {
                'producto_nombre': productos_map.get(producto_id, '?'),
                'recolectado': Decimal('0'), 'entregado': Decimal('0'),
            })
            acumulado['recolectado'] += rec
            acumulado['entregado'] += ent

        resumen = [
            {
                'producto_id': pid, 'producto_nombre': v['producto_nombre'],
                'recolectado_kg': str(v['recolectado']), 'entregado_kg': str(v['entregado']),
                'disponible_kg': str(v['recolectado'] - v['entregado']),
            }
            for pid, v in resumen_global.items()
        ]

        resumen_proveedor = {}
        for linea in detalle_por_proveedor:
            pid = linea['proveedor_id']
            if pid is None:
                continue
            acc = resumen_proveedor.setdefault(pid, {
                'proveedor_nombre': linea['proveedor_nombre'],
                'recolectado_kg': Decimal('0'), 'entregado_kg': Decimal('0'),
                'cobrado_cliente': Decimal('0'), 'pagado_proveedor': Decimal('0'),
            })
            acc['recolectado_kg'] += Decimal(linea['recolectado_kg'])
            acc['entregado_kg'] += Decimal(linea['entregado_kg'])
            acc['cobrado_cliente'] += Decimal(linea['cobrado_cliente'])
            if linea['pagado_proveedor'] is not None:
                acc['pagado_proveedor'] += Decimal(linea['pagado_proveedor'])

        liquidaciones = {str(l.proveedor_id): l for l in LiquidacionProveedor.objects.filter(viaje=viaje)}
        resumen_por_proveedor = [
            {
                'proveedor_id': pid,
                'proveedor_nombre': acc['proveedor_nombre'],
                'recolectado_kg': str(acc['recolectado_kg']),
                'entregado_kg': str(acc['entregado_kg']),
                'cobrado_cliente': str(acc['cobrado_cliente'].quantize(Q2)),
                'pagado_proveedor': str(acc['pagado_proveedor'].quantize(Q2)),
                'ganancia_transportador': str((acc['cobrado_cliente'] - acc['pagado_proveedor']).quantize(Q2)),
                'liquidacion_id': str(liquidaciones[pid].id) if pid in liquidaciones else None,
                'liquidacion_numero': liquidaciones[pid].numero_liquidacion if pid in liquidaciones else None,
                'liquidacion_estado': liquidaciones[pid].estado_pago if pid in liquidaciones else None,
            }
            for pid, acc in resumen_proveedor.items()
        ]

        return {
            'detalle_por_proveedor': detalle_por_proveedor,
            'resumen_global': resumen,
            'resumen_por_proveedor': resumen_por_proveedor,
        }
    
    @action(detail=True, methods=['get'])
    def inventario(self, request, pk=None):
        viaje = self.get_object()
        return Response(self._calcular_inventario(viaje))

    @action(detail=True, methods=['post'], url_path='marcar-transito')
    def marcar_transito(self, request, pk=None):
        viaje = self.get_object()
        self._cambiar_estado(viaje, EstadoViaje.TRANSITO)
        return Response(self.get_serializer(viaje).data)

    @action(detail=True, methods=['post'], url_path='marcar-entregado')
    def marcar_entregado(self, request, pk=None):
        viaje = self.get_object()
        inventario = self._calcular_inventario(viaje)
        pendientes = [item for item in inventario['detalle_por_proveedor'] if Decimal(item['disponible_kg']) > 0]

        if pendientes:
            motivo = request.data.get('motivo_cierre', '').strip()
            if not motivo:
                return Response(
                    {
                        'requiere_motivo': True,
                        'inventario_pendiente': pendientes,
                        'detail': 'Queda inventario sin entregar. Debes justificar antes de cerrar el viaje.',
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            nota = f'[Cierre con inventario pendiente] {motivo}'
            viaje.observaciones = f'{viaje.observaciones}\n{nota}'.strip() if viaje.observaciones else nota
            viaje.save(update_fields=['observaciones'])

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
    filterset_fields = ['entrega', 'punto_recoleccion', 'producto']

    def get_serializer_class(self):
        if self.action == 'create':
            return DetalleEntregaCreateSerializer
        if self.action in ('update', 'partial_update'):
            return DetalleEntregaUpdateSerializer
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

class LiquidacionProveedorViewSet(viewsets.ModelViewSet):
    queryset = LiquidacionProveedor.objects.all()
    serializer_class = LiquidacionProveedorSerializer
    filterset_fields = ['viaje', 'proveedor', 'estado_pago']

    @action(detail=True, methods=['post'], url_path='marcar-pagado')
    def marcar_pagado(self, request, pk=None):
        liquidacion = self.get_object()
        liquidacion.estado_pago = EstadoPago.PAGADO
        liquidacion.save(update_fields=['estado_pago'])
        return Response(LiquidacionProveedorSerializer(liquidacion).data)