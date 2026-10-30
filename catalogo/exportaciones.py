import csv
import io
import textwrap
import zipfile
from html import escape

from django.http import HttpResponse
from django.utils import timezone


ENCABEZADOS = (
    "Fecha",
    "Producto",
    "Tipo",
    "Unidades",
    "Stock anterior",
    "Stock nuevo",
    "Motivo",
    "Usuario",
)


def _filas(movimientos):
    for movimiento in movimientos:
        usuario = movimiento.usuario.get_full_name().strip()
        yield (
            timezone.localtime(movimiento.fecha).strftime("%d/%m/%Y %H:%M"),
            movimiento.producto.nombre,
            movimiento.get_tipo_display(),
            movimiento.cantidad,
            movimiento.stock_anterior,
            movimiento.stock_nuevo,
            movimiento.motivo,
            usuario or movimiento.usuario.username,
        )


def _texto_seguro(valor):
    texto = str(valor or "")
    if texto.startswith(("=", "+", "-", "@")):
        return f"'{texto}"
    return texto


def _exportar_csv(filas):
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = (
        'attachment; filename="movimientos_stock.csv"'
    )
    response.write("\ufeff")
    writer = csv.writer(response, delimiter=";")
    writer.writerow(ENCABEZADOS)
    for fila in filas:
        writer.writerow([_texto_seguro(valor) for valor in fila])
    return response


def _celda_xlsx(referencia, valor, estilo=0):
    if isinstance(valor, int):
        return f'<c r="{referencia}" s="{estilo}"><v>{valor}</v></c>'
    texto = escape(_texto_seguro(valor))
    return (
        f'<c r="{referencia}" s="{estilo}" t="inlineStr">'
        f'<is><t xml:space="preserve">{texto}</t></is></c>'
    )


def _exportar_xlsx(filas):
    letras = "ABCDEFGH"
    filas_xml = []
    encabezado = "".join(
        _celda_xlsx(f"{letra}1", valor, 1)
        for letra, valor in zip(letras, ENCABEZADOS)
    )
    filas_xml.append(f'<row r="1">{encabezado}</row>')
    numero_fila = 2
    for numero_fila, fila in enumerate(filas, start=2):
        celdas = "".join(
            _celda_xlsx(f"{letra}{numero_fila}", valor)
            for letra, valor in zip(letras, fila)
        )
        filas_xml.append(f'<row r="{numero_fila}">{celdas}</row>')

    hoja = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>
  <cols><col min="1" max="1" width="19" customWidth="1"/><col min="2" max="2" width="30" customWidth="1"/><col min="3" max="3" width="13" customWidth="1"/><col min="4" max="6" width="14" customWidth="1"/><col min="7" max="7" width="40" customWidth="1"/><col min="8" max="8" width="24" customWidth="1"/></cols>
  <sheetData>{''.join(filas_xml)}</sheetData>
  <autoFilter ref="A1:H{max(numero_fila, 1)}"/>
</worksheet>'''
    archivos = {
        "[Content_Types].xml": '''<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/></Types>''',
        "_rels/.rels": '''<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>''',
        "xl/workbook.xml": '''<?xml version="1.0" encoding="UTF-8"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Movimientos de stock" sheetId="1" r:id="rId1"/></sheets></workbook>''',
        "xl/_rels/workbook.xml.rels": '''<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>''',
        "xl/styles.xml": '''<?xml version="1.0" encoding="UTF-8"?><styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><fonts count="2"><font><sz val="11"/><name val="Calibri"/></font><font><b/><sz val="11"/><name val="Calibri"/></font></fonts><fills count="2"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill></fills><borders count="1"><border/></borders><cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs><cellXfs count="2"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/><xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/></cellXfs></styleSheet>''',
        "xl/worksheets/sheet1.xml": hoja,
    }
    contenido = io.BytesIO()
    with zipfile.ZipFile(contenido, "w", zipfile.ZIP_DEFLATED) as archivo:
        for nombre, texto in archivos.items():
            archivo.writestr(nombre, texto)
    response = HttpResponse(
        contenido.getvalue(),
        content_type=(
            "application/vnd.openxmlformats-officedocument."
            "spreadsheetml.sheet"
        ),
    )
    response["Content-Disposition"] = (
        'attachment; filename="movimientos_stock.xlsx"'
    )
    return response


def _pdf_escapar(texto):
    return str(texto).replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _lineas_pdf(filas):
    anchos = (16, 24, 10, 7, 8, 8, 30, 18)
    yield " ".join(
        str(valor)[:ancho].ljust(ancho)
        for valor, ancho in zip(ENCABEZADOS, anchos)
    )
    yield "-" * (sum(anchos) + len(anchos) - 1)
    for fila in filas:
        columnas = [
            textwrap.wrap(str(valor), width=ancho) or [""]
            for valor, ancho in zip(fila, anchos)
        ]
        for indice in range(max(map(len, columnas))):
            yield " ".join(
                (columna[indice] if indice < len(columna) else "").ljust(ancho)
                for columna, ancho in zip(columnas, anchos)
            )
        yield ""


def _crear_pdf(paginas):
    objetos = [b"", b"", b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier >>"]
    referencias_paginas = []
    for lineas in paginas:
        comandos = ["BT", "/F1 7 Tf", "30 558 Td"]
        for indice, linea in enumerate(lineas):
            if indice:
                comandos.append("0 -10 Td")
            comandos.append(f"({_pdf_escapar(linea)}) Tj")
        comandos.append("ET")
        stream = "\n".join(comandos).encode("cp1252", errors="replace")
        pagina_numero = len(objetos) + 1
        contenido_numero = pagina_numero + 1
        referencias_paginas.append(pagina_numero)
        objetos.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 842 595] /Resources << /Font << /F1 3 0 R >> >> /Contents {contenido_numero} 0 R >>".encode()
        )
        objetos.append(
            f"<< /Length {len(stream)} >>\nstream\n".encode()
            + stream
            + b"\nendstream"
        )
    objetos[0] = b"<< /Type /Catalog /Pages 2 0 R >>"
    hijos = " ".join(f"{numero} 0 R" for numero in referencias_paginas)
    objetos[1] = (
        f"<< /Type /Pages /Kids [{hijos}] /Count {len(referencias_paginas)} >>"
        .encode()
    )

    documento = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for numero, objeto in enumerate(objetos, start=1):
        offsets.append(len(documento))
        documento.extend(f"{numero} 0 obj\n".encode())
        documento.extend(objeto)
        documento.extend(b"\nendobj\n")
    inicio_xref = len(documento)
    documento.extend(f"xref\n0 {len(objetos) + 1}\n".encode())
    documento.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        documento.extend(f"{offset:010d} 00000 n \n".encode())
    documento.extend(
        f"trailer\n<< /Size {len(objetos) + 1} /Root 1 0 R >>\nstartxref\n{inicio_xref}\n%%EOF".encode()
    )
    return bytes(documento)


def _exportar_pdf(filas):
    lineas = list(_lineas_pdf(filas))
    paginas = []
    encabezado = ["PUNTO APARTE - MOVIMIENTOS DE STOCK", ""]
    encabezado_tabla = lineas[:2]
    detalle = lineas[2:]
    if detalle:
        for inicio in range(0, len(detalle), 44):
            paginas.append(
                encabezado + encabezado_tabla + detalle[inicio:inicio + 44]
            )
    else:
        paginas = [encabezado + ["No hay movimientos para exportar."]]
    response = HttpResponse(
        _crear_pdf(paginas),
        content_type="application/pdf",
    )
    response["Content-Disposition"] = (
        'attachment; filename="movimientos_stock.pdf"'
    )
    return response


def exportar_movimientos(movimientos, formato):
    filas = list(_filas(movimientos))
    if formato == "csv":
        return _exportar_csv(filas)
    if formato == "xlsx":
        return _exportar_xlsx(filas)
    return _exportar_pdf(filas)
