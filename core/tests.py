from decimal import Decimal
from datetime import date
from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APITestCase

from .models import (
    Producto, Cliente, Proveedor, PrecioCliente, Viaje, PuntoRecoleccion, LoteCarga,
    Entrega, DetalleEntrega, Factura, Configuracion,
    Calidad, Vehiculo, TipoServicio,
)


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


class ViajeApiTestCase(APITestCase):
    """Base con lo que casi todos los tests de flujo de negocio necesitan."""

    def setUp(self):
        self.usuario = User.objects.create_user(username='tester', password='clave123')
        self.client.force_authenticate(user=self.usuario)
        self.cliente = Cliente.objects.create(nombre='Cliente Test')
        self.producto = Producto.objects.create(nombre='Banano')
        self.proveedor = Proveedor.objects.create(nombre='Oscar', vereda='Alto Bélgica')
        PrecioCliente.objects.create(
            cliente=self.cliente, producto=self.producto, calidad=Calidad.PRIMERA, precio_kg=Decimal('2500.00'),
        )
        PrecioCliente.objects.create(
            cliente=self.cliente, producto=self.producto, calidad=Calidad.SEGUNDA, precio_kg=Decimal('1000.00'),
        )
        self.viaje = Viaje.objects.create(vehiculo=Vehiculo.TURBO)


class EstadoViajeGatingTests(ViajeApiTestCase):
    """Reglas A y B: paradas solo en RECOLECCION, entregas solo en TRANSITO."""

    def test_no_deja_crear_parada_si_el_viaje_ya_no_esta_en_recoleccion(self):
        self.client.post(f'/api/viajes/{self.viaje.id}/marcar-transito/')
        resp = self.client.post('/api/puntos-recoleccion/', {
            'viaje': str(self.viaje.id), 'proveedor': str(self.proveedor.id),
            'orden': 1, 'tipo_servicio': 'FLETE',
        })
        self.assertEqual(resp.status_code, 400)

    def test_si_deja_crear_parada_mientras_esta_en_recoleccion(self):
        resp = self.client.post('/api/puntos-recoleccion/', {
            'viaje': str(self.viaje.id), 'proveedor': str(self.proveedor.id),
            'orden': 1, 'tipo_servicio': 'FLETE',
        })
        self.assertEqual(resp.status_code, 201)

    def test_no_deja_crear_entrega_mientras_el_viaje_sigue_en_recoleccion(self):
        resp = self.client.post('/api/entregas/', {
            'viaje': str(self.viaje.id), 'cliente': str(self.cliente.id),
        })
        self.assertEqual(resp.status_code, 400)

    def test_si_deja_crear_entrega_una_vez_en_transito(self):
        self.client.post(f'/api/viajes/{self.viaje.id}/marcar-transito/')
        resp = self.client.post('/api/entregas/', {
            'viaje': str(self.viaje.id), 'cliente': str(self.cliente.id),
        })
        self.assertEqual(resp.status_code, 201)


class LoteCargaPrecioCompraTests(ViajeApiTestCase):
    def setUp(self):
        super().setUp()
        self.punto_compra = PuntoRecoleccion.objects.create(
            viaje=self.viaje, proveedor=self.proveedor, orden=1, tipo_servicio=TipoServicio.COMPRA,
        )
        self.punto_flete = PuntoRecoleccion.objects.create(
            viaje=self.viaje, proveedor=self.proveedor, orden=2, tipo_servicio=TipoServicio.FLETE,
        )

    def test_lote_en_parada_compra_exige_precio_compra_kg(self):
        resp = self.client.post('/api/lotes-carga/', {
            'punto_recoleccion': str(self.punto_compra.id), 'producto': str(self.producto.id),
            'calidad': '1RA', 'num_canastillas': 10, 'peso_recoleccion_kg': 200,
        })
        self.assertEqual(resp.status_code, 400)

    def test_lote_en_parada_compra_con_precio_si_pasa(self):
        resp = self.client.post('/api/lotes-carga/', {
            'punto_recoleccion': str(self.punto_compra.id), 'producto': str(self.producto.id),
            'calidad': '1RA', 'num_canastillas': 10, 'peso_recoleccion_kg': 200, 'precio_compra_kg': 1200,
        })
        self.assertEqual(resp.status_code, 201)

    def test_lote_en_parada_flete_no_exige_precio_compra_kg(self):
        resp = self.client.post('/api/lotes-carga/', {
            'punto_recoleccion': str(self.punto_flete.id), 'producto': str(self.producto.id),
            'calidad': '1RA', 'num_canastillas': 20, 'peso_recoleccion_kg': 400,
        })
        self.assertEqual(resp.status_code, 201)


class InventarioPorParadaTests(ViajeApiTestCase):
    """La regla más importante: disponible por PARADA + producto, con reclasificación permitida."""

    def setUp(self):
        super().setUp()
        self.punto = PuntoRecoleccion.objects.create(
            viaje=self.viaje, proveedor=self.proveedor, orden=1, tipo_servicio=TipoServicio.FLETE,
        )
        LoteCarga.objects.create(
            punto_recoleccion=self.punto, producto=self.producto, calidad=Calidad.PRIMERA,
            num_canastillas=20, peso_recoleccion_kg=Decimal('400.00'),
        )
        LoteCarga.objects.create(
            punto_recoleccion=self.punto, producto=self.producto, calidad=Calidad.SEGUNDA,
            num_canastillas=5, peso_recoleccion_kg=Decimal('100.00'),
        )
        self.client.post(f'/api/viajes/{self.viaje.id}/marcar-transito/')
        resp = self.client.post('/api/entregas/', {'viaje': str(self.viaje.id), 'cliente': str(self.cliente.id)})
        self.entrega_id = resp.data['id']

    def test_permite_reclasificar_sin_que_el_total_exceda_lo_recolectado(self):
        # Recogido: 400 primera + 100 segunda. Entregado: 300 primera + 200 segunda.
        # Distinto por calidad, IGUAL en total (500) — debe pasar.
        resp = self.client.post('/api/detalles-entrega/', {
            'entrega': str(self.entrega_id), 'punto_recoleccion': str(self.punto.id),
            'producto': str(self.producto.id), 'kg_primera_recibida': 300, 'kg_segunda_recibida': 200,
        })
        self.assertEqual(resp.status_code, 201)

    def test_rechaza_exceder_el_total_recolectado_en_esa_parada(self):
        resp = self.client.post('/api/detalles-entrega/', {
            'entrega': str(self.entrega_id), 'punto_recoleccion': str(self.punto.id),
            'producto': str(self.producto.id), 'kg_primera_recibida': 400, 'kg_segunda_recibida': 200,
        })
        self.assertEqual(resp.status_code, 400)

    def test_rechaza_parada_que_no_pertenece_al_viaje_de_la_entrega(self):
        otro_viaje = Viaje.objects.create(vehiculo=Vehiculo.CAMION)
        punto_de_otro_viaje = PuntoRecoleccion.objects.create(
            viaje=otro_viaje, proveedor=self.proveedor, orden=1, tipo_servicio=TipoServicio.FLETE,
        )
        resp = self.client.post('/api/detalles-entrega/', {
            'entrega': str(self.entrega_id), 'punto_recoleccion': str(punto_de_otro_viaje.id),
            'producto': str(self.producto.id), 'kg_primera_recibida': 50, 'kg_segunda_recibida': 0,
        })
        self.assertEqual(resp.status_code, 400)


class MargenFleteTests(ViajeApiTestCase):
    def setUp(self):
        super().setUp()
        Configuracion.objects.all().delete()  # fuerza el default del modelo (500.00) para el test

    def _crear_punto_y_lote(self, margen_flete_kg=None):
        datos = {
            'viaje': str(self.viaje.id), 'proveedor': str(self.proveedor.id),
            'orden': 1, 'tipo_servicio': 'FLETE',
        }
        if margen_flete_kg is not None:
            datos['margen_flete_kg'] = margen_flete_kg
        resp = self.client.post('/api/puntos-recoleccion/', datos)
        punto_id = resp.data['id']
        LoteCarga.objects.create(
            punto_recoleccion_id=punto_id, producto=self.producto, calidad=Calidad.PRIMERA,
            num_canastillas=20, peso_recoleccion_kg=Decimal('400.00'),
        )
        return str(punto_id)

    def test_usa_el_margen_configurado_por_defecto_si_la_parada_no_especifica_uno(self):
        punto_id = self._crear_punto_y_lote()
        self.client.post(f'/api/viajes/{self.viaje.id}/marcar-transito/')
        resp = self.client.post('/api/entregas/', {'viaje': str(self.viaje.id), 'cliente': str(self.cliente.id)})
        entrega_id = resp.data['id']

        resp = self.client.post('/api/detalles-entrega/', {
            'entrega': str(entrega_id), 'punto_recoleccion': punto_id,
            'producto': str(self.producto.id), 'kg_primera_recibida': 100, 'kg_segunda_recibida': 0,
        })
        self.assertEqual(Decimal(resp.data['margen_kg']), Decimal('500.00'))

    def test_usa_el_margen_acordado_en_la_parada_si_se_especifico(self):
        punto_id = self._crear_punto_y_lote(margen_flete_kg=300)
        self.client.post(f'/api/viajes/{self.viaje.id}/marcar-transito/')
        resp = self.client.post('/api/entregas/', {'viaje': str(self.viaje.id), 'cliente': str(self.cliente.id)})
        entrega_id = resp.data['id']

        resp = self.client.post('/api/detalles-entrega/', {
            'entrega': str(entrega_id), 'punto_recoleccion': punto_id,
            'producto': str(self.producto.id), 'kg_primera_recibida': 100, 'kg_segunda_recibida': 0,
        })
        self.assertEqual(Decimal(resp.data['margen_kg']), Decimal('300.00'))

    def test_subtotal_proveedor_es_none_en_compra(self):
        resp = self.client.post('/api/puntos-recoleccion/', {
            'viaje': str(self.viaje.id), 'proveedor': str(self.proveedor.id),
            'orden': 1, 'tipo_servicio': 'COMPRA',
        })
        punto_id = str(resp.data['id'])
        LoteCarga.objects.create(
            punto_recoleccion_id=punto_id, producto=self.producto, calidad=Calidad.PRIMERA,
            num_canastillas=10, peso_recoleccion_kg=Decimal('200.00'), precio_compra_kg=Decimal('1200.00'),
        )
        self.client.post(f'/api/viajes/{self.viaje.id}/marcar-transito/')
        resp = self.client.post('/api/entregas/', {'viaje': str(self.viaje.id), 'cliente': str(self.cliente.id)})
        entrega_id = resp.data['id']

        resp = self.client.post('/api/detalles-entrega/', {
            'entrega': str(entrega_id), 'punto_recoleccion': punto_id,
            'producto': str(self.producto.id), 'kg_primera_recibida': 100, 'kg_segunda_recibida': 0,
        })
        self.assertIsNone(resp.data['subtotal_proveedor'])


class CierreConMotivoTests(ViajeApiTestCase):
    def setUp(self):
        super().setUp()
        self.punto = PuntoRecoleccion.objects.create(
            viaje=self.viaje, proveedor=self.proveedor, orden=1, tipo_servicio=TipoServicio.FLETE,
        )
        LoteCarga.objects.create(
            punto_recoleccion=self.punto, producto=self.producto, calidad=Calidad.PRIMERA,
            num_canastillas=20, peso_recoleccion_kg=Decimal('400.00'),
        )
        self.client.post(f'/api/viajes/{self.viaje.id}/marcar-transito/')
        resp = self.client.post('/api/entregas/', {'viaje': str(self.viaje.id), 'cliente': str(self.cliente.id)})
        self.entrega_id = resp.data['id']

    def test_pide_motivo_si_queda_inventario_pendiente(self):
        self.client.post('/api/detalles-entrega/', {
            'entrega': str(self.entrega_id), 'punto_recoleccion': str(self.punto.id),
            'producto': str(self.producto.id), 'kg_primera_recibida': 100, 'kg_segunda_recibida': 0,
        })
        resp = self.client.post(f'/api/viajes/{self.viaje.id}/marcar-entregado/')
        self.assertEqual(resp.status_code, 400)
        self.assertTrue(resp.data['requiere_motivo'])

    def test_cierra_con_motivo_y_lo_guarda_en_observaciones(self):
        self.client.post('/api/detalles-entrega/', {
            'entrega': str(self.entrega_id), 'punto_recoleccion': str(self.punto.id),
            'producto': str(self.producto.id), 'kg_primera_recibida': 100, 'kg_segunda_recibida': 0,
        })
        resp = self.client.post(
            f'/api/viajes/{self.viaje.id}/marcar-entregado/',
            {'motivo_cierre': 'Fruta dañada, sobrante descartado'},
        )
        self.assertEqual(resp.status_code, 200)
        self.viaje.refresh_from_db()
        self.assertIn('Fruta dañada', self.viaje.observaciones)

    def test_cierra_directo_sin_pedir_motivo_si_no_queda_nada_pendiente(self):
        self.client.post('/api/detalles-entrega/', {
            'entrega': str(self.entrega_id), 'punto_recoleccion': str(self.punto.id),
            'producto': str(self.producto.id), 'kg_primera_recibida': 400, 'kg_segunda_recibida': 0,
        })
        resp = self.client.post(f'/api/viajes/{self.viaje.id}/marcar-entregado/')
        self.assertEqual(resp.status_code, 200)