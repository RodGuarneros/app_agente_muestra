# make docs

from pathlib import Path

docs = {
    "delivery_policy.txt": """
Urban Click es una app móvil de retail commerce enfocada en compras rápidas desde smartphone.
La entrega estándar tarda entre 24 y 48 horas en zonas metropolitanas.
Las órdenes con store pickup pueden estar listas el mismo día, dependiendo del inventario.
El envío gratis aplica en productos seleccionados o en compras mayores al umbral promocional.
""".strip(),

    "returns_policy.txt": """
Los clientes pueden solicitar devoluciones dentro de los primeros 15 días naturales.
Los accesorios sellados deben devolverse sin señales de uso.
Los smartphones y tablets deben entregarse con caja, accesorios y comprobante digital.
Las devoluciones aprobadas se reembolsan al método de pago original.
""".strip(),

    "app_features.txt": """
La app móvil permite explorar productos, comparar precios, revisar promociones y rastrear pedidos.
Los usuarios pueden pagar con tarjeta, transferencia o contra entrega en pedidos elegibles.
La experiencia está diseñada primero para móvil, con navegación simple y confirmaciones rápidas.
""".strip(),

    "customer_support.txt": """
El soporte ayuda con problemas de pago, devoluciones, seguimiento y disponibilidad de productos.
Los pedidos cancelados pueden deberse a falta de stock o validación fallida del pago.
Si un producto no está disponible, el sistema puede sugerir alternativas relacionadas.
""".strip(),
}

docs_dir = Path("docs")
docs_dir.mkdir(exist_ok=True)

for filename, content in docs.items():
    (docs_dir / filename).write_text(content, encoding="utf-8")

print("Documentos sintéticos creados en ./docs")