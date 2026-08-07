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


class Producto(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    nombre = models.CharField(max_length=100)
    activo = models.BooleanField(default=True)
    creado_en = models.DateTimeField(auto_now_add=True)

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

    def __str__(self):
        return f"Viaje {self.fecha_salida} — {self.get_vehiculo_display()}"


class PuntoRecoleccion(models.Model):
    """Una parada del viaje donde se recoge fruta de un proveedor."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    viaje = models.ForeignKey(Viaje, on_delete=models.CASCADE, related_name='puntos')
    proveedor = models.ForeignKey(Proveedor, on_delete=models.PROTECT)
    orden = models.PositiveSmallIntegerField()
    tipo_servicio = models.CharField(max_length=10, choices=TipoServicio.choices)
    precio_flete_kg = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True
    )

    class Meta:
        ordering = ['orden']
        unique_together = [('viaje', 'orden')]

    def clean(self):
        if self.tipo_servicio == TipoServicio.FLETE and not self.precio_flete_kg:
            raise ValidationError('Se requiere precio_flete_kg cuando el tipo es FLETE.')
        if self.tipo_servicio == TipoServicio.COMPRA:
            self.precio_flete_kg = None

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