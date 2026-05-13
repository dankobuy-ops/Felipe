from app.models.datos import Cliente, Vehiculo, Inmueble
from app.models.gestion import Registro, Cotizacion, Poliza, Cuota, Siniestro
from app.models.operaciones import Ramo, Compania, Producto
from app.models.configuracion import Usuario, ValorUF, Parametro

__all__ = [
    "Cliente", "Vehiculo", "Inmueble",
    "Registro", "Cotizacion", "Poliza", "Cuota", "Siniestro",
    "Ramo", "Compania", "Producto",
    "Usuario", "ValorUF", "Parametro",
]
