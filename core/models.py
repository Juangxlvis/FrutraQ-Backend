import uuid
from django.db import models
from decimal import Decimal
from datetime import date
from django.core.exceptions import ValidationError


class Calidad(models.TextChoices):
    PRIMERA = '1RA', 'Primera'
    SEGUNDA = '2DA', 'Segunda'


class TipoServicio(models.TextChoices):
    COMPRA = 'COMPRA', 'Compra de mercancía'
    FLETE = 'FLETE', 'Servicio de flete'


class EstadoViaje(models.TextChoices):
    RECOLECCION = 'RECOLECCION', 'En recolección'
    TRANSITO = 'TRANSITO', 'En tránsito'
    ENTREGADO = 'ENTREGADO', 'Entregado'
    CANCELADO = 'CANCELADO', 'Cancelado'


class Vehiculo(models.TextChoices):
    TURBO = 'TURBO', 'Turbo'
    CAMION = 'CAMION', 'Camión'


class EstadoPago(models.TextChoices):
    PENDIENTE = 'PENDIENTE', 'Pendiente'
    PAGADO = 'PAGADO', 'Pagado'


class Configuracion(models.Model):
    margen_flete_kg_defecto = models.DecimalField(
        max_digits=8, decimal_places=2, default=Decimal('500.00'),
        help_text='Margen por kg que se precarga en entregas de paradas tipo FLETE.'
    )
    nombre_negocio = models.CharField(max_length=150, blank=True, default='FrutraQ')
    telefono_contacto = models.CharField(max_length=20, blank=True)

    class Meta:
        verbose_name = 'Configuración general'
        verbose_name_plural = 'Configuración general'

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def obtener(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def __str__(self):
        return 'Configuración general'

class Producto(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    nombre = models.CharField(max_length=100)
    activo = models.BooleanField(default=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['nombre']

    def __str__(self):
        return self.nombre


class Proveedor(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    nombre = models.CharField(max_length=150)
    vereda = models.CharField(max_length=150)
    municipio = models.CharField(max_length=100, default='Armenia')
    telefono = models.CharField(max_length=20, blank=True)
    tipo_servicio_habitual = models.CharField(
        max_length=10, choices=TipoServicio.choices, default=TipoServicio.COMPRA
    )
    activo = models.BooleanField(default=True)
    notas = models.TextField(blank=True)

    class Meta:
        ordering = ['nombre']

    def __str__(self):
        return f"{self.nombre} — {self.vereda}"


class Cliente(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    nombre = models.CharField(max_length=150)
    ciudad = models.CharField(max_length=100, default='Bogotá')
    direccion = models.CharField(max_length=200, blank=True)
    telefono = models.CharField(max_length=20, blank=True)
    nit_cedula = models.CharField(max_length=30, blank=True)
    activo = models.BooleanField(default=True)
    notas = models.TextField(blank=True)

    class Meta:
        ordering = ['nombre']

    def __str__(self):
        return self.nombre


class PrecioCliente(models.Model):
    """
    Precio por kg para una combinación cliente + producto + calidad.
    Para actualizar un precio NO se edita el registro existente,
    se inserta uno nuevo con vigente_desde = hoy. Así se conserva el historial.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    cliente = models.ForeignKey(Cliente, on_delete=models.CASCADE, related_name='precios')
    producto = models.ForeignKey(Producto, on_delete=models.CASCADE)
    calidad = models.CharField(max_length=3, choices=Calidad.choices)
    precio_kg = models.DecimalField(max_digits=10, decimal_places=2)
    vigente_desde = models.DateField(default=date.today)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-vigente_desde']

    @classmethod
    def precio_vigente(cls, cliente_id, producto_id, calidad):
        """Retorna el precio más reciente para la combinación dada."""
        return cls.objects.filter(
            cliente_id=cliente_id, producto_id=producto_id, calidad=calidad
        ).order_by('-vigente_desde').first()

    def __str__(self):
        return f"{self.cliente} — {self.producto} ({self.calidad}): ${self.precio_kg}"


class Viaje(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    fecha_salida = models.DateField(default=date.today)
    vehiculo = models.CharField(max_length=10, choices=Vehiculo.choices)
    estado = models.CharField(
        max_length=15, choices=EstadoViaje.choices, default=EstadoViaje.RECOLECCION
    )
    observaciones = models.TextField(blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-fecha_salida', '-creado_en']

    def __str__(self):
        return f"Viaje {self.fecha_salida} — {self.get_vehiculo_display()}"


class PuntoRecoleccion(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    viaje = models.ForeignKey(Viaje, on_delete=models.CASCADE, related_name='puntos')
    proveedor = models.ForeignKey(Proveedor, on_delete=models.PROTECT)
    orden = models.PositiveSmallIntegerField()
    tipo_servicio = models.CharField(max_length=10, choices=TipoServicio.choices)
    margen_flete_kg = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True,
        help_text='Margen acordado por kg cuando el tipo es FLETE. Si queda vacío, se usa el valor por defecto de Configuración al momento de entregar.'
    )

    class Meta:
        ordering = ['orden']
        unique_together = [('viaje', 'orden')]

    def __str__(self):
        return f"{self.viaje} · parada {self.orden} · {self.proveedor}"
    
class LoteCarga(models.Model):
    """
    Grupo de canastillas del mismo producto y calidad en un punto de recolección.
    El peso aquí es SOLO REFERENCIA del transportador — nunca determina pagos.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    punto_recoleccion = models.ForeignKey(PuntoRecoleccion, on_delete=models.CASCADE, related_name='lotes')
    producto = models.ForeignKey(Producto, on_delete=models.PROTECT)
    calidad = models.CharField(max_length=3, choices=Calidad.choices)
    num_canastillas = models.PositiveSmallIntegerField()
    peso_recoleccion_kg = models.DecimalField(max_digits=8, decimal_places=2)
    precio_compra_kg = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)

    @property
    def peso_promedio_canastilla(self):
        if self.num_canastillas > 0:
            return round(self.peso_recoleccion_kg / self.num_canastillas, 2)
        return Decimal('0')

    def clean(self):
        if self.num_canastillas <= 0:
            raise ValidationError('El número de canastillas debe ser mayor a 0.')
        if self.peso_recoleccion_kg <= 0:
            raise ValidationError('El peso debe ser mayor a 0.')

    def __str__(self):
        return f"{self.producto} · {self.calidad} · {self.num_canastillas} canastillas"


class Entrega(models.Model):
    """Entrega de fruta a un cliente en destino (Bogotá)."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    viaje = models.ForeignKey(Viaje, on_delete=models.CASCADE, related_name='entregas')
    cliente = models.ForeignKey(Cliente, on_delete=models.PROTECT)
    fecha_entrega = models.DateField(default=date.today)
    estado_pago = models.CharField(
        max_length=10, choices=EstadoPago.choices, default=EstadoPago.PENDIENTE
    )
    notas = models.TextField(blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    @property
    def total(self):
        from django.db.models import Sum
        return self.detalles.aggregate(total=Sum('subtotal'))['total'] or Decimal('0.00')

    def __str__(self):
        return f"Entrega {self.cliente} — {self.fecha_entrega}"


class DetalleEntrega(models.Model):
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    entrega = models.ForeignKey(Entrega, on_delete=models.CASCADE, related_name='detalles')
    punto_recoleccion = models.ForeignKey(
        PuntoRecoleccion, on_delete=models.PROTECT, related_name='detalles_entrega',
        null=True,  # nulo solo por compatibilidad con registros creados antes de este cambio
    )
    producto = models.ForeignKey(Producto, on_delete=models.PROTECT)

    kg_primera_recibida = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal('0.00'))
    kg_segunda_recibida = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal('0.00'))

    # Snapshot — NO son ForeignKey a PrecioCliente
    precio_primera_kg = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'), blank=True)
    precio_segunda_kg = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'), blank=True)

    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))

    # Ganancia por kg del transportador — solo aplica en paradas tipo COMPRA (0 en FLETE)
    margen_kg = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal('0.00'), blank=True)

    def save(self, *args, **kwargs):
        self.subtotal = (
            self.kg_primera_recibida * self.precio_primera_kg +
            self.kg_segunda_recibida * self.precio_segunda_kg
        )
        super().save(*args, **kwargs)

    @property
    def subtotal_proveedor(self):
        """
        Cuánto se le paga al proveedor por esta línea — solo aplica en
        paradas FLETE, donde la tajada del transportador se descuenta
        recién al momento de la entrega (no se sabe antes). En COMPRA,
        el proveedor ya cobró un precio fijo en la recolección
        (LoteCarga.precio_compra_kg) — no depende de esta línea.
        """
        if not self.punto_recoleccion_id or self.punto_recoleccion.tipo_servicio != TipoServicio.FLETE:
            return None
        total_kg = self.kg_primera_recibida + self.kg_segunda_recibida
        return self.subtotal - (self.margen_kg * total_kg)

    def clean(self):
        if self.kg_primera_recibida < 0 or self.kg_segunda_recibida < 0:
            raise ValidationError('Los kilogramos no pueden ser negativos.')
        if self.kg_primera_recibida == 0 and self.kg_segunda_recibida == 0:
            raise ValidationError('Debe ingresar al menos kg de primera o de segunda.')
        if self.kg_primera_recibida > 0 and self.precio_primera_kg <= 0:
            raise ValidationError('Se requiere un precio de primera válido si hay kg de primera.')
        if self.kg_segunda_recibida > 0 and self.precio_segunda_kg <= 0:
            raise ValidationError('Se requiere un precio de segunda válido si hay kg de segunda.')
        if self.punto_recoleccion_id and self.entrega_id:
            if self.punto_recoleccion.viaje_id != self.entrega.viaje_id:
                raise ValidationError('La parada debe pertenecer al mismo viaje que la entrega.')

    def __str__(self):
        return f"{self.producto} — subtotal ${self.subtotal}"


class Factura(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    entrega = models.OneToOneField(Entrega, on_delete=models.CASCADE, related_name='factura')
    numero_factura = models.CharField(max_length=20, unique=True, blank=True)
    fecha_emision = models.DateField(auto_now_add=True)
    total = models.DecimalField(max_digits=12, decimal_places=2, blank=True)
    notas = models.TextField(blank=True)
    pdf_url = models.CharField(max_length=500, blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.numero_factura:
            self.numero_factura = self._generar_numero()
        if not self.total:
            self.total = self.entrega.total
        super().save(*args, **kwargs)

    class Meta:
        ordering = ['-fecha_emision', '-creado_en']

    @staticmethod
    def _generar_numero():
        anio = date.today().year
        ultimo = Factura.objects.filter(numero_factura__startswith=f'FAC-{anio}-').count()
        return f'FAC-{anio}-{str(ultimo + 1).zfill(4)}'

    def __str__(self):
        return self.numero_factura

class LiquidacionProveedor(models.Model):
    """
    Liquidación de lo que se le debe a un proveedor por UN viaje completo —
    agrega todas sus paradas de ese viaje (FLETE y/o COMPRA) en un solo total.
    Es el equivalente de Factura, pero mirando hacia el proveedor, no el cliente.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    viaje = models.ForeignKey(Viaje, on_delete=models.CASCADE, related_name='liquidaciones')
    proveedor = models.ForeignKey(Proveedor, on_delete=models.PROTECT)
    numero_liquidacion = models.CharField(max_length=20, unique=True, blank=True)
    fecha_emision = models.DateField(auto_now_add=True)
    estado_pago = models.CharField(max_length=10, choices=EstadoPago.choices, default=EstadoPago.PENDIENTE)
    total = models.DecimalField(max_digits=12, decimal_places=2, blank=True, default=Decimal('0.00'))
    notas = models.TextField(blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [('viaje', 'proveedor')]
        ordering = ['-fecha_emision', '-creado_en']

    def save(self, *args, **kwargs):
        if not self.numero_liquidacion:
            self.numero_liquidacion = self._generar_numero()
        if not self.total:
            self.total = self._calcular_total()
        super().save(*args, **kwargs)

    def _calcular_total(self):
        from django.db.models import Sum, F
        total = Decimal('0.00')
        paradas = PuntoRecoleccion.objects.filter(viaje=self.viaje, proveedor=self.proveedor)
        for punto in paradas:
            if punto.tipo_servicio == TipoServicio.FLETE:
                agregado = DetalleEntrega.objects.filter(punto_recoleccion=punto).aggregate(
                    t=Sum(F('subtotal') - F('margen_kg') * (F('kg_primera_recibida') + F('kg_segunda_recibida')))
                )['t']
            else:
                agregado = LoteCarga.objects.filter(punto_recoleccion=punto).aggregate(
                    t=Sum(F('precio_compra_kg') * F('peso_recoleccion_kg'))
                )['t']
            total += agregado or Decimal('0.00')
        return total.quantize(Decimal('0.01'))

    @staticmethod
    def _generar_numero():
        anio = date.today().year
        ultimo = LiquidacionProveedor.objects.filter(numero_liquidacion__startswith=f'LIQ-{anio}-').count()
        return f'LIQ-{anio}-{str(ultimo + 1).zfill(4)}'

    def __str__(self):
        return self.numero_liquidacion