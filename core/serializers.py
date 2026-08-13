from decimal import Decimal
from django.db.models import Sum
from rest_framework import serializers
from .models import (
    Producto, Proveedor, Cliente, PrecioCliente,
    Viaje, PuntoRecoleccion, LoteCarga,
    Entrega, DetalleEntrega, Factura,
    TipoServicio, Calidad,
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
        fields = ['id', 'viaje', 'proveedor', 'orden', 'tipo_servicio', 'precio_flete_kg']

    def validate(self, data):
        # Durante un PATCH parcial, 'data' solo trae los campos que cambiaron.
        # Por eso, si un campo no viene en 'data', hay que rescatarlo del
        # objeto ya existente (self.instance) — si no, esta validación
        # se rompería en cualquier actualización parcial.
        tipo = data.get('tipo_servicio', getattr(self.instance, 'tipo_servicio', None))
        precio = data.get('precio_flete_kg', getattr(self.instance, 'precio_flete_kg', None))

        if tipo == TipoServicio.FLETE and not precio:
            raise serializers.ValidationError(
                {'precio_flete_kg': 'Se requiere cuando el tipo de servicio es FLETE.'}
            )
        if tipo == TipoServicio.COMPRA:
            data['precio_flete_kg'] = None
        return data


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

class EntregaSerializer(serializers.ModelSerializer):
    total = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = Entrega
        fields = ['id', 'viaje', 'cliente', 'fecha_entrega', 'estado_pago', 'notas', 'creado_en', 'total']


class FacturaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Factura
        fields = ['id', 'entrega', 'numero_factura', 'fecha_emision', 'total', 'notas', 'pdf_url', 'creado_en']
        read_only_fields = ['numero_factura', 'fecha_emision', 'total']

class DetalleEntregaSerializer(serializers.ModelSerializer):
    """Para LEER — muestra todo, incluidos los precios ya calculados."""
    class Meta:
        model = DetalleEntrega
        fields = [
            'id', 'entrega', 'producto',
            'kg_primera_recibida', 'kg_segunda_recibida',
            'precio_primera_kg', 'precio_segunda_kg', 'subtotal',
        ]
        read_only_fields = ['precio_primera_kg', 'precio_segunda_kg', 'subtotal']


class DetalleEntregaCreateSerializer(serializers.ModelSerializer):
    """
    Para CREAR — el cliente solo manda producto y kilos.
    Los precios se buscan internamente en PrecioCliente.precio_vigente().
    """
    class Meta:
        model = DetalleEntrega
        fields = ['id', 'entrega', 'producto', 'kg_primera_recibida', 'kg_segunda_recibida']

    def validate(self, data):
        kg_primera = data.get('kg_primera_recibida', Decimal('0'))
        kg_segunda = data.get('kg_segunda_recibida', Decimal('0'))

        if kg_primera < 0 or kg_segunda < 0:
            raise serializers.ValidationError('Los kilogramos no pueden ser negativos.')
        if kg_primera == 0 and kg_segunda == 0:
            raise serializers.ValidationError('Debe ingresar al menos kg de primera o de segunda.')

        entrega = data['entrega']
        producto = data['producto']

        if kg_primera > 0:
            precio = PrecioCliente.precio_vigente(entrega.cliente_id, producto.id, Calidad.PRIMERA)
            if not precio:
                raise serializers.ValidationError(
                    f'No hay precio de PRIMERA configurado para {entrega.cliente} y {producto}.'
                )
            data['precio_primera_kg'] = precio.precio_kg
        else:
            data['precio_primera_kg'] = Decimal('0.00')

        if kg_segunda > 0:
            precio = PrecioCliente.precio_vigente(entrega.cliente_id, producto.id, Calidad.SEGUNDA)
            if not precio:
                raise serializers.ValidationError(
                    f'No hay precio de SEGUNDA configurado para {entrega.cliente} y {producto}.'
                )
            data['precio_segunda_kg'] = precio.precio_kg
        else:
            data['precio_segunda_kg'] = Decimal('0.00')

        return data