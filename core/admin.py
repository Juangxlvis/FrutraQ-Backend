from django.contrib import admin
from .models import Producto, Proveedor, Cliente

admin.site.register(Producto)
admin.site.register(Proveedor)
admin.site.register(Cliente)