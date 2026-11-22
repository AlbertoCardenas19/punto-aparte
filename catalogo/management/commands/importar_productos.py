import csv
import unicodedata
from collections import Counter
from decimal import Decimal
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from catalogo.models import Producto


class Command(BaseCommand):
    help = "Simula o importa productos del Excel sin sobrescribir datos existentes."
    SUGERENCIAS = str.maketrans({"\x84": "Ñ", "\x87": "á", "\x92": "í", "\x97": "ó", "\x83": "É", "ç": "Á", "ê": "Í", "î": "Ó"})

    def add_arguments(self, parser):
        parser.add_argument("archivo", type=Path)
        parser.add_argument("--aplicar", action="store_true")
        parser.add_argument("--reporte", type=Path)

    def handle(self, *args, **options):
        try:
            from openpyxl import load_workbook
        except ImportError as error:
            raise CommandError("Instala las dependencias de requirements.txt") from error
        archivo = Path(options["archivo"])
        if not archivo.is_file():
            raise CommandError(f"No existe el archivo: {archivo}")
        libro = load_workbook(archivo, read_only=True, data_only=True)
        hoja = libro.active
        filas = list(hoja.values)
        columnas = ["Id", "Ref.", "Título / Nombre", "Precio unitario total", "Código de barras"]
        indices = {nombre: filas[0].index(nombre) for nombre in columnas}

        def codigo(valor):
            if valor is None or valor == "":
                return None
            if isinstance(valor, str):
                return valor.strip() or None
            if isinstance(valor, int) and not isinstance(valor, bool):
                return str(valor)
            # Los decimales y la notación científica no se reinterpretan.
            return None

        codigos = Counter(codigo(f[indices["Código de barras"]]) for f in filas[1:])
        reporte = []
        with transaction.atomic():
            for numero, fila in enumerate(filas[1:], 2):
                nombre = fila[indices["Título / Nombre"]]
                precio = fila[indices["Precio unitario total"]]
                bruto = fila[indices["Código de barras"]]
                barra = codigo(bruto)
                origen = fila[indices["Id"]] or fila[indices["Ref."]]
                referencia = f"lista-productos:{origen}" if origen is not None else None
                estado, detalle = "creado", ""
                if bruto not in (None, "") and barra is None:
                    estado, detalle = "pendiente", "Código ambiguo"
                elif barra and codigos[barra] > 1:
                    estado, detalle = "pendiente", "Código repetido en Excel"
                elif not isinstance(nombre, str) or not nombre.strip():
                    estado, detalle = "pendiente", "Nombre vacío"
                elif any(unicodedata.category(c) == "Cc" or c in "?�ÃÂçîêË¼" for c in nombre):
                    estado, detalle = "pendiente", "Nombre dañado; requiere revisión"
                elif not isinstance(precio, int) or isinstance(precio, bool) or precio < 0:
                    estado, detalle = "pendiente", "Precio ambiguo"
                elif not referencia:
                    estado, detalle = "pendiente", "Sin identificador de procedencia"
                elif Producto.objects.filter(referencia_importacion=referencia).exists():
                    estado, detalle = "omitido", "Ya importado"
                elif barra and Producto.objects.filter(codigo_barras=barra).exists():
                    estado, detalle = "omitido", "Código existente en base"
                elif options["aplicar"]:
                    Producto.objects.create(nombre=nombre.strip(), precio=precio,
                                           codigo_barras=barra, referencia_importacion=referencia,
                                           stock=0, marca="")
                propuesta = nombre.translate(self.SUGERENCIAS) if isinstance(nombre, str) else ""
                if propuesta == nombre or any(c in propuesta for c in "?�ÃÂË¼"):
                    propuesta = ""
                reporte.append({"fila": numero, "estado": estado, "detalle": detalle,
                                "nombre": nombre, "propuesta": propuesta,
                                "codigo": barra or "", "referencia": referencia or ""})
            if not options["aplicar"]:
                transaction.set_rollback(True)
        libro.close()
        if options["reporte"]:
            with Path(options["reporte"]).open("w", newline="", encoding="utf-8-sig") as salida:
                escritor = csv.DictWriter(salida, fieldnames=reporte[0].keys())
                escritor.writeheader()
                escritor.writerows(reporte)
        conteo = Counter(item["estado"] for item in reporte)
        self.stdout.write(f"Modo: {'aplicación' if options['aplicar'] else 'simulación'}. "
                          f"Creados: {conteo['creado']}; omitidos: {conteo['omitido']}; "
                          f"pendientes: {conteo['pendiente']}")
        for item in reporte:
            if item["estado"] == "pendiente":
                self.stdout.write(f"Fila {item['fila']}: {item['detalle']}: {item['nombre']}")
