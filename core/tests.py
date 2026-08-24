from decimal import Decimal
from datetime import date
from django.test import TestCase

from .models import (
    Producto, Cliente, PrecioCliente, Viaje, Entrega, DetalleEntrega, Factura,
    Calidad, Vehiculo,
)
from .serializers import DetalleEntregaCreateSerializer


class PrecioClienteTests(TestCase):
    def setUp(self):
        self.cliente = Cliente.objects.create(nombre='Cliente Test')
        self.producto = Producto.objects.create(nombre='Banano')

    def test_precio_vigente_retorna_el_mas_reciente(self):
        PrecioCliente.objects.create(
            cliente=self.cliente, producto=self.producto, calidad=Calidad.PRIMERA,
            precio_kg=Decimal('2000.00'), vigente_desde=date(2026, 1, 1),
        )
        PrecioCliente.objects.create(
            cliente=self.cliente, producto=self.producto, calidad=Calidad.PRIMERA,
            precio_kg=Decimal('2500.00'), vigente_desde=date(2026, 6, 1),
        )
        vigente = PrecioCliente.precio_vigente(self.cliente.id, self.producto.id, Calidad.PRIMERA)
        self.assertEqual(vigente.precio_kg, Decimal('2500.00'))

    def test_precio_vigente_none_si_no_existe(self):
        vigente = PrecioCliente.precio_vigente(self.cliente.id, self.producto.id, Calidad.SEGUNDA)
        self.assertIsNone(vigente)


class DetalleEntregaSubtotalTests(TestCase):
    def setUp(self):
        self.cliente = Cliente.objects.create(nombre='Cliente Test')
        self.producto = Producto.objects.create(nombre='Banano')
        self.viaje = Viaje.objects.create(vehiculo=Vehiculo.TURBO)
        self.entrega = Entrega.objects.create(viaje=self.viaje, cliente=self.cliente)

    def test_subtotal_se_calcula_con_ambas_calidades(self):
        detalle = DetalleEntrega.objects.create(
            entrega=self.entrega, producto=self.producto,
            kg_primera_recibida=Decimal('100'), kg_segunda_recibida=Decimal('50'),
            precio_primera_kg=Decimal('2500.00'), precio_segunda_kg=Decimal('1500.00'),
        )
        # 100*2500 + 50*1500 = 250000 + 75000
        self.assertEqual(detalle.subtotal, Decimal('325000.00'))

    def test_subtotal_se_recalcula_al_editar_y_guardar(self):
        detalle = DetalleEntrega.objects.create(
            entrega=self.entrega, producto=self.producto,
            kg_primera_recibida=Decimal('10'), kg_segunda_recibida=Decimal('0'),
            precio_primera_kg=Decimal('2000.00'), precio_segunda_kg=Decimal('0'),
        )
        self.assertEqual(detalle.subtotal, Decimal('20000.00'))
        detalle.kg_primera_recibida = Decimal('20')
        detalle.save()
        self.assertEqual(detalle.subtotal, Decimal('40000.00'))


class DetalleEntregaCreateSerializerTests(TestCase):
    """El 'guardia de la ventana': snapshot de precio automático desde la API."""

    def setUp(self):
        self.cliente = Cliente.objects.create(nombre='Cliente Test')
        self.producto = Producto.objects.create(nombre='Banano')
        self.viaje = Viaje.objects.create(vehiculo=Vehiculo.TURBO)
        self.entrega = Entrega.objects.create(viaje=self.viaje, cliente=self.cliente)
        PrecioCliente.objects.create(
            cliente=self.cliente, producto=self.producto, calidad=Calidad.PRIMERA,
            precio_kg=Decimal('2500.00'),
        )

    def test_toma_el_precio_vigente_automaticamente(self):
        data = {
            'entrega': self.entrega.id, 'producto': self.producto.id,
            'kg_primera_recibida': 100, 'kg_segunda_recibida': 0,
        }
        serializer = DetalleEntregaCreateSerializer(data=data)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data['precio_primera_kg'], Decimal('2500.00'))

    def test_rechaza_kilos_negativos(self):
        data = {
            'entrega': self.entrega.id, 'producto': self.producto.id,
            'kg_primera_recibida': -10, 'kg_segunda_recibida': 0,
        }
        serializer = DetalleEntregaCreateSerializer(data=data)
        self.assertFalse(serializer.is_valid())

    def test_rechaza_si_no_hay_precio_configurado_para_esa_calidad(self):
        # Solo existe precio de PRIMERA en el setUp — pedimos SEGUNDA a propósito.
        data = {
            'entrega': self.entrega.id, 'producto': self.producto.id,
            'kg_primera_recibida': 0, 'kg_segunda_recibida': 30,
        }
        serializer = DetalleEntregaCreateSerializer(data=data)
        self.assertFalse(serializer.is_valid())


class FacturaTests(TestCase):
    def setUp(self):
        self.cliente = Cliente.objects.create(nombre='Cliente Test')
        self.producto = Producto.objects.create(nombre='Banano')
        self.viaje = Viaje.objects.create(vehiculo=Vehiculo.TURBO)
        self.entrega = Entrega.objects.create(viaje=self.viaje, cliente=self.cliente)
        DetalleEntrega.objects.create(
            entrega=self.entrega, producto=self.producto,
            kg_primera_recibida=Decimal('100'), kg_segunda_recibida=Decimal('0'),
            precio_primera_kg=Decimal('2500.00'), precio_segunda_kg=Decimal('0'),
        )

    def test_genera_numero_y_total_automaticamente(self):
        factura = Factura.objects.create(entrega=self.entrega)
        self.assertTrue(factura.numero_factura.startswith(f'FAC-{date.today().year}-'))
        self.assertEqual(factura.total, Decimal('250000.00'))

    def test_numeros_consecutivos_no_se_repiten(self):
        entrega2 = Entrega.objects.create(viaje=self.viaje, cliente=self.cliente)
        DetalleEntrega.objects.create(
            entrega=entrega2, producto=self.producto,
            kg_primera_recibida=Decimal('10'), kg_segunda_recibida=Decimal('0'),
            precio_primera_kg=Decimal('1000.00'), precio_segunda_kg=Decimal('0'),
        )
        f1 = Factura.objects.create(entrega=self.entrega)
        f2 = Factura.objects.create(entrega=entrega2)
        self.assertNotEqual(f1.numero_factura, f2.numero_factura)