from decimal import Decimal
from django.db.models import Sum, F
from rest_framework import serializers
from .models import (
    LiquidacionProveedor, Producto, Proveedor, Cliente, PrecioCliente,
    Viaje, PuntoRecoleccion, LoteCarga,
    Entrega, DetalleEntrega, Factura, Configuracion,
    TipoServicio, Calidad, EstadoViaje,
)


class ProductoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Producto
        fields = ['id', 'nombre', 'activo', 'creado_en']


class ProveedorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Proveedor
        fields = [
            'id', 'nombre', 'vereda', 'municipio', 'telefono',
            'tipo_servicio_habitual', 'activo', 'notas',
        ]


class ClienteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Cliente
        fields = [
            'id', 'nombre', 'ciudad', 'direccion', 'telefono',
            'nit_cedula', 'activo', 'notas',
        ]


class PrecioClienteSerializer(serializers.ModelSerializer):
    class Meta:
        model = PrecioCliente
        fields = [
            'id', 'cliente', 'producto', 'calidad',
            'precio_kg', 'vigente_desde', 'creado_en',
        ]


class ConfiguracionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Configuracion
        fields = ['id', 'margen_flete_kg_defecto']

class ViajeSerializer(serializers.ModelSerializer):
    total_recolectado_kg = serializers.SerializerMethodField()
    total_entregado = serializers.SerializerMethodField()

    class Meta:
        model = Viaje
        fields = [
            'id', 'fecha_salida', 'vehiculo', 'estado', 'observaciones',
            'creado_en', 'actualizado_en',
            'total_recolectado_kg', 'total_entregado',
        ]

    def get_total_recolectado_kg(self, obj):
        total = LoteCarga.objects.filter(
            punto_recoleccion__viaje=obj
        ).aggregate(t=Sum('peso_recoleccion_kg'))['t']
        return total or 0

    def get_total_entregado(self, obj):
        total = DetalleEntrega.objects.filter(
            entrega__viaje=obj
        ).aggregate(t=Sum('subtotal'))['t']
        return str(total or Decimal('0.00'))


class PuntoRecoleccionSerializer(serializers.ModelSerializer):
    class Meta:
        model = PuntoRecoleccion
        fields = ['id', 'viaje', 'proveedor', 'orden', 'tipo_servicio', 'margen_flete_kg']

    def validate_viaje(self, viaje):
        if self.instance is None and viaje.estado != EstadoViaje.RECOLECCION:
            raise serializers.ValidationError(
                'Solo se pueden agregar paradas mientras el viaje está en recolección.'
            )
        return viaje


class LoteCargaSerializer(serializers.ModelSerializer):
    peso_promedio_canastilla = serializers.ReadOnlyField()

    class Meta:
        model = LoteCarga
        fields = [
            'id', 'punto_recoleccion', 'producto', 'calidad',
            'num_canastillas', 'peso_recoleccion_kg', 'precio_compra_kg',
            'peso_promedio_canastilla',
        ]

    def validate_num_canastillas(self, value):
        if value <= 0:
            raise serializers.ValidationError('Debe ser mayor a 0.')
        return value

    def validate_peso_recoleccion_kg(self, value):
        if value <= 0:
            raise serializers.ValidationError('El peso debe ser mayor a 0.')
        return value
    
    def validate(self, data):
        punto = data.get('punto_recoleccion', getattr(self.instance, 'punto_recoleccion', None))
        precio = data.get('precio_compra_kg', getattr(self.instance, 'precio_compra_kg', None))
        if punto and punto.tipo_servicio == TipoServicio.COMPRA and not precio:
            raise serializers.ValidationError(
                {'precio_compra_kg': 'Se requiere el precio de compra cuando la parada es tipo COMPRA.'}
            )
        return data


class EntregaSerializer(serializers.ModelSerializer):
    total = serializers.ReadOnlyField()
    factura_id = serializers.SerializerMethodField()

    class Meta:
        model = Entrega
        fields = ['id', 'viaje', 'cliente', 'fecha_entrega', 'estado_pago', 'notas', 'creado_en', 'total', 'factura_id']

    def get_factura_id(self, obj):
        try:
            return str(obj.factura.id)
        except Entrega.factura.RelatedObjectDoesNotExist:
            return None

    def validate_viaje(self, viaje):
        if self.instance is None and viaje.estado != EstadoViaje.TRANSITO:
            raise serializers.ValidationError(
                'Solo se pueden registrar entregas mientras el viaje está en tránsito.'
            )
        return viaje


class FacturaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Factura
        fields = ['id', 'entrega', 'numero_factura', 'fecha_emision', 'total', 'notas', 'pdf_url', 'creado_en']
        read_only_fields = ['numero_factura', 'fecha_emision', 'total']


class DetalleEntregaSerializer(serializers.ModelSerializer):
    """Para LEER — muestra todo, incluidos precios, margen y lo que le corresponde al proveedor."""
    subtotal_proveedor = serializers.ReadOnlyField()

    class Meta:
        model = DetalleEntrega
        fields = [
            'id', 'entrega', 'punto_recoleccion', 'producto',
            'kg_primera_recibida', 'kg_segunda_recibida',
            'precio_primera_kg', 'precio_segunda_kg', 'subtotal',
            'margen_kg', 'subtotal_proveedor',
        ]
        read_only_fields = ['precio_primera_kg', 'precio_segunda_kg', 'subtotal']


class DetalleEntregaCreateSerializer(serializers.ModelSerializer):
    """
    Para CREAR — el cliente manda parada de origen, producto y kilos.
    Los precios se buscan internamente en PrecioCliente.precio_vigente().
    El disponible se controla por PARADA + producto (no por viaje completo),
    para atribuir correctamente el pago a cada proveedor. El margen toma
    el valor configurado por defecto si no se manda uno explícito.
    """
    class Meta:
        model = DetalleEntrega
        fields = [
            'id', 'entrega', 'punto_recoleccion', 'producto',
            'kg_primera_recibida', 'kg_segunda_recibida', 'margen_kg',
            'precio_primera_kg', 'precio_segunda_kg', 'subtotal', 'subtotal_proveedor',
        ]
        read_only_fields = ['precio_primera_kg', 'precio_segunda_kg', 'subtotal', 'subtotal_proveedor']
        extra_kwargs = {
            'margen_kg': {'required': False},
            'punto_recoleccion': {'required': True, 'allow_null': False},
        }

    def validate(self, data):
        kg_primera = data.get('kg_primera_recibida', Decimal('0'))
        kg_segunda = data.get('kg_segunda_recibida', Decimal('0'))

        if kg_primera < 0 or kg_segunda < 0:
            raise serializers.ValidationError('Los kilogramos no pueden ser negativos.')
        if kg_primera == 0 and kg_segunda == 0:
            raise serializers.ValidationError('Debe ingresar al menos kg de primera o de segunda.')

        entrega = data['entrega']
        punto = data['punto_recoleccion']
        producto = data['producto']

        if punto.viaje_id != entrega.viaje_id:
            raise serializers.ValidationError('La parada seleccionada no pertenece al viaje de esta entrega.')

        total_solicitado = kg_primera + kg_segunda
        recolectado = LoteCarga.objects.filter(
            punto_recoleccion=punto, producto=producto
        ).aggregate(t=Sum('peso_recoleccion_kg'))['t'] or Decimal('0')
        ya_entregado = DetalleEntrega.objects.filter(
            punto_recoleccion=punto, producto=producto
        ).aggregate(t=Sum(F('kg_primera_recibida') + F('kg_segunda_recibida')))['t'] or Decimal('0')
        disponible = recolectado - ya_entregado

        if total_solicitado > disponible:
            raise serializers.ValidationError(
                f'Solo quedan {disponible} kg disponibles de {producto.nombre} de esta parada.'
            )

        if kg_primera > 0:
            precio = PrecioCliente.precio_vigente(entrega.cliente_id, producto.id, Calidad.PRIMERA)
            if not precio:
                raise serializers.ValidationError(f'No hay precio de PRIMERA configurado para {entrega.cliente} y {producto}.')
            data['precio_primera_kg'] = precio.precio_kg
        else:
            data['precio_primera_kg'] = Decimal('0.00')

        if kg_segunda > 0:
            precio = PrecioCliente.precio_vigente(entrega.cliente_id, producto.id, Calidad.SEGUNDA)
            if not precio:
                raise serializers.ValidationError(f'No hay precio de SEGUNDA configurado para {entrega.cliente} y {producto}.')
            data['precio_segunda_kg'] = precio.precio_kg
        else:
            data['precio_segunda_kg'] = Decimal('0.00')

        if punto.tipo_servicio == TipoServicio.FLETE:
                        if data.get('margen_kg') is None:
                            data['margen_kg'] = punto.margen_flete_kg or Configuracion.obtener().margen_flete_kg_defecto
        else:
            data['margen_kg'] = Decimal('0.00')

        return data

class LiquidacionProveedorSerializer(serializers.ModelSerializer):
    class Meta:
        model = LiquidacionProveedor
        fields = ['id', 'viaje', 'proveedor', 'numero_liquidacion', 'fecha_emision', 'estado_pago', 'total', 'notas', 'creado_en']
        read_only_fields = ['numero_liquidacion', 'fecha_emision', 'total']