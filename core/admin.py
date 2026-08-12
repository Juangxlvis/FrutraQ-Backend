from django.contrib import admin
from .models import (
    Producto, Proveedor, Cliente, PrecioCliente,
    Viaje, PuntoRecoleccion, LoteCarga,
    Entrega, DetalleEntrega, Factura,
)

admin.site.register(Producto)
admin.site.register(Proveedor)
admin.site.register(Cliente)
admin.site.register(PrecioCliente)
admin.site.register(Viaje)
admin.site.register(PuntoRecoleccion)
admin.site.register(LoteCarga)
admin.site.register(Entrega)
admin.site.register(DetalleEntrega)
admin.site.register(Factura)