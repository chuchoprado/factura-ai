"""
Extracción PDF → Excel con Claude Vision — FacturAI Backend
Lógica central reutilizada del bot de Telegram.
"""
import re
import os
import json
import base64
import logging
import tempfile
from datetime import datetime
from typing import Any, Dict, List, Optional

import fitz  # PyMuPDF
import anthropic
from openpyxl import Workbook
from openpyxl.styles import PatternFill, Font, Alignment, Border, Side
from openpyxl.utils import get_column_letter

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# UTILIDADES
# ─────────────────────────────────────────────

def safe_float(value: Any) -> Optional[float]:
    """
    Parsea importes en cualquier formato europeo/americano.
    Ejemplos válidos: 1.234,56 | 1,234.56 | 1234.56 | 1234,56 | 1.234 | €12,50
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return round(float(value), 2)

    text = str(value).strip()
    if not text:
        return None

    # Limpiar símbolos de moneda y espacios
    text = re.sub(r'[€$£\s]', '', text)
    text = re.sub(r'(EUR|eur|Eur)', '', text)

    # Formato europeo: 1.234,56 o 1.234 (punto = miles, coma = decimal)
    if re.match(r'^\d{1,3}(\.\d{3})+(,\d+)?$', text):
        text = text.replace('.', '').replace(',', '.')

    # Formato con solo coma decimal: 1234,56
    elif re.match(r'^\d+,\d{1,2}$', text):
        text = text.replace(',', '.')

    # Formato americano: 1,234.56
    elif re.match(r'^\d{1,3}(,\d{3})+(\.\d+)?$', text):
        text = text.replace(',', '')

    # Si queda algo raro, eliminar todo menos dígitos y punto
    else:
        text = re.sub(r'[^\d.]', '', text)

    try:
        result = round(float(text), 2)
        # Sanidad: descartar valores imposibles (> 1 millón en factura normal)
        return result if 0 < result < 1_000_000 else None
    except Exception:
        return None


def parse_date_to_iso(date_text: Any) -> Optional[str]:
    if not date_text:
        return None
    raw = str(date_text).strip()
    patterns = [
        "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y",
        "%d.%m.%Y", "%Y/%m/%d", "%d-%m-%y", "%d/%m/%y",
    ]
    for fmt in patterns:
        try:
            return datetime.strptime(raw, fmt).strftime("%d-%m-%Y")
        except Exception:
            pass
    match = re.search(r"(\d{2})[\/\-.](\d{2})[\/\-.](\d{4})", raw)
    if match:
        d, m, y = match.groups()
        try:
            return datetime(int(y), int(m), int(d)).strftime("%d-%m-%Y")
        except Exception:
            return None
    return None


def normalize_estado(value: Any) -> str:
    text = str(value or "").strip().upper()
    mapping = {
        "COMPLETA": "COMPLETA", "OK": "COMPLETA", "COMPLETE": "COMPLETA",
        "VERIFICAR_DATOS": "VERIFICAR_DATOS", "VERIFICAR": "VERIFICAR_DATOS",
        "REVISAR": "VERIFICAR_DATOS", "PENDIENTE_REVISION": "PENDIENTE_REVISION",
        "PENDIENTE": "PENDIENTE_REVISION", "NO_PROCESABLE": "PENDIENTE_REVISION",
    }
    return mapping.get(text, "PENDIENTE_REVISION")


def build_fallback_row(page_num: int, reason: str) -> Dict[str, Any]:
    return {
        "numero_factura": None, "pagina": page_num,
        "fecha_literal": None, "fecha_iso": None,
        "total_eur": None, "iva_pct": 10,
        "base_eur": None, "cuota_eur": None,
        "estado": "PENDIENTE_REVISION",
        "observaciones": reason[:250] if reason else "No procesable",
    }


def normalize_row(row: Dict[str, Any], page_num: int) -> Dict[str, Any]:
    normalized = {
        "numero_factura": row.get("numero_factura"),
        "pagina": row.get("pagina") if row.get("pagina") is not None else page_num,
        "fecha_literal": row.get("fecha_literal"),
        "fecha_iso": parse_date_to_iso(row.get("fecha_iso") or row.get("fecha_literal")),
        "total_eur": safe_float(row.get("total_eur")),
        "iva_pct": 10,
        "base_eur": None,
        "cuota_eur": None,
        "estado": normalize_estado(row.get("estado")),
        "observaciones": str(row.get("observaciones") or "OK").strip(),
    }
    if normalized["total_eur"] is not None:
        base  = round(normalized["total_eur"] / 1.10, 2)
        cuota = round(normalized["total_eur"] - base, 2)
        normalized["base_eur"]  = base
        normalized["cuota_eur"] = cuota
    if not normalized["fecha_iso"] and normalized["estado"] == "COMPLETA":
        normalized["estado"] = "VERIFICAR_DATOS"
        if normalized["observaciones"] == "OK":
            normalized["observaciones"] = "Falta fecha confiable"
    if normalized["total_eur"] is None and normalized["estado"] == "COMPLETA":
        normalized["estado"] = "VERIFICAR_DATOS"
        if normalized["observaciones"] == "OK":
            normalized["observaciones"] = "Falta total confiable"
    if normalized["fecha_iso"] is None and normalized["total_eur"] is None and normalized["estado"] != "PENDIENTE_REVISION":
        normalized["estado"] = "PENDIENTE_REVISION"
    return normalized


def sort_and_renumber_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    def sort_key(item: Dict[str, Any]):
        date_iso = item.get("fecha_iso")
        if date_iso:
            try:
                parts = date_iso.split("-")
                sortable = f"{parts[2]}-{parts[1]}-{parts[0]}" if len(parts) == 3 and len(parts[2]) == 4 else date_iso
            except Exception:
                sortable = date_iso
            return (0, sortable, item.get("pagina") or 0)
        return (1, "9999-99-99", item.get("pagina") or 0)
    rows_sorted = sorted(rows, key=sort_key)
    for idx, row in enumerate(rows_sorted, start=1):
        row["numero_factura"] = f"Z-{idx}"
    return rows_sorted


# ─────────────────────────────────────────────
# CLAUDE VISION
# ─────────────────────────────────────────────

async def extract_invoice_from_page(
    client: anthropic.AsyncAnthropic,
    page_b64: str,
    page_num: int,
    model: str = "claude-opus-4-5",
) -> Dict[str, Any]:
    system_prompt = """Eres un contable experto en extracción de datos de facturas y tickets españoles.

TAREA: Analizar la imagen y extraer datos de la factura/ticket visible.

REGLAS ESTRICTAS:
1. Extrae SIEMPRE el total si hay cualquier número visible que parezca un importe final.
2. El total es el importe MÁS GRANDE que aparezca como "Total", "TOTAL", "Importe total", "A pagar", "Total a pagar" o el número final del documento.
3. NO confundas Base Imponible o Subtotal con el Total — el Total incluye IVA.
4. Para la fecha: busca cualquier campo con "Fecha", "Date", "Emitida", o un patrón DD/MM/YYYY, DD-MM-YYYY, YYYY-MM-DD.
5. Los números en España usan punto para miles y coma para decimales: 1.234,56 € = 1234.56
6. Devuelve total_eur SIEMPRE como número decimal sin símbolos: 1234.56 (NO "1.234,56 €")
7. Si ves fecha Y total → estado: "COMPLETA"
8. Si ves solo uno de los dos → estado: "VERIFICAR_DATOS"
9. Si la página está en blanco o no es una factura → estado: "PENDIENTE_REVISION"

FORMATO DE RESPUESTA: JSON puro, sin markdown, sin explicaciones.

{
  "numero_factura": "<número de factura visible o null>",
  "pagina": <número de página>,
  "fecha_literal": "<fecha tal como aparece en el documento o null>",
  "fecha_iso": "<DD-MM-YYYY o null>",
  "total_eur": <número decimal SIN símbolos, ej: 125.50>,
  "iva_pct": <porcentaje IVA como número, ej: 21>,
  "base_eur": null,
  "cuota_eur": null,
  "estado": "COMPLETA" | "VERIFICAR_DATOS" | "PENDIENTE_REVISION",
  "observaciones": "<descripción breve de qué contiene la página>"
}"""

    user_prompt = (
        f"Página {page_num} del PDF. "
        "Extrae fecha de emisión y total final (con IVA incluido). "
        "Si el documento es una factura o ticket con importes visibles, DEBES extraer el total. "
        "Responde SOLO con el JSON, sin ningún texto adicional."
    )
    try:
        response = await client.messages.create(
            model=model,
            max_tokens=1024,
            system=system_prompt,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": page_b64}},
                    {"type": "text", "text": user_prompt},
                ],
            }],
        )
        raw_text = response.content[0].text.strip()
        raw_text = re.sub(r"^```(?:json)?\s*", "", raw_text)
        raw_text = re.sub(r"\s*```$", "", raw_text).strip()
        if not raw_text:
            return build_fallback_row(page_num, "Sin respuesta del modelo")
        parsed = json.loads(raw_text)
        if not isinstance(parsed, dict):
            return build_fallback_row(page_num, "Respuesta JSON inválida")
        parsed["pagina"] = page_num
        normalized = normalize_row(parsed, page_num)
        if normalized["fecha_iso"] is None and normalized["total_eur"] is None and normalized["observaciones"] in ("", "OK"):
            normalized["estado"]        = "PENDIENTE_REVISION"
            normalized["observaciones"] = "No se pudo extraer fecha ni total"
        return normalized
    except json.JSONDecodeError as e:
        logger.error(f"Error JSON página {page_num}: {e}")
        return build_fallback_row(page_num, f"Error parseando JSON en página {page_num}")
    except Exception as e:
        logger.error(f"Error extrayendo página {page_num}: {e}", exc_info=True)
        return build_fallback_row(page_num, f"Error inesperado en página {page_num}")


def pdf_to_page_images(pdf_bytes: bytes, dpi: int = 300) -> List[str]:
    """Convierte un PDF (bytes) en lista de imágenes base64 PNG."""
    doc  = fitz.open(stream=pdf_bytes, filetype="pdf")
    zoom = dpi / 72.0
    mat  = fitz.Matrix(zoom, zoom)
    pages_b64 = []
    for page_index in range(len(doc)):
        page      = doc.load_page(page_index)
        pix       = page.get_pixmap(matrix=mat, alpha=False)
        png_bytes = pix.tobytes("png")
        pages_b64.append(base64.b64encode(png_bytes).decode("utf-8"))
    doc.close()
    return pages_b64


# ─────────────────────────────────────────────
# EXCEL
# ─────────────────────────────────────────────

def create_invoice_excel(rows: List[Dict[str, Any]]) -> bytes:
    """Genera el Excel y devuelve los bytes (no escribe en disco)."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Facturas"

    header_fill = PatternFill(fill_type="solid", fgColor="1F3864")
    alt_fill    = PatternFill(fill_type="solid", fgColor="EBF0FA")
    total_fill  = PatternFill(fill_type="solid", fgColor="D9E1F2")
    white_font  = Font(color="FFFFFF", bold=True, name="Arial", size=10)
    bold_font   = Font(bold=True, name="Arial", size=10)
    base_font   = Font(name="Arial", size=10)
    thin_border = Border(
        left=Side(style="thin", color="B8CCE4"), right=Side(style="thin", color="B8CCE4"),
        top=Side(style="thin", color="B8CCE4"),  bottom=Side(style="thin", color="B8CCE4"),
    )
    med_border = Border(
        left=Side(style="medium", color="1F3864"), right=Side(style="medium", color="1F3864"),
        top=Side(style="medium", color="1F3864"),  bottom=Side(style="medium", color="1F3864"),
    )

    headers = ["N° Factura", "Página", "Fecha Literal", "Fecha ISO", "Total €",
               "IVA %", "Base €", "Cuota IVA €", "Estado", "Observaciones"]
    for col_idx, header in enumerate(headers, 1):
        cell            = ws.cell(row=1, column=col_idx, value=header)
        cell.fill       = header_fill
        cell.font       = white_font
        cell.alignment  = Alignment(horizontal="center", vertical="center")
        cell.border     = med_border
    ws.row_dimensions[1].height = 32

    for row_idx, row in enumerate(rows, start=2):
        ws.append([
            row.get("numero_factura"), row.get("pagina"), row.get("fecha_literal"),
            row.get("fecha_iso"), row.get("total_eur"), row.get("iva_pct"),
            row.get("base_eur"), row.get("cuota_eur"), row.get("estado"), row.get("observaciones"),
        ])
        fila_fill = alt_fill if row_idx % 2 == 0 else PatternFill(fill_type="solid", fgColor="FFFFFF")
        for col_idx in range(1, 11):
            cell        = ws.cell(row=row_idx, column=col_idx)
            cell.border = thin_border
            cell.font   = base_font
            cell.fill   = fila_fill

        estado_cell = ws.cell(row=row_idx, column=9)
        estado      = str(row.get("estado") or "")
        if estado == "COMPLETA":
            estado_cell.fill = PatternFill(fill_type="solid", fgColor="C6EFCE")
            estado_cell.font = Font(color="375623", bold=True, name="Arial", size=10)
        elif estado == "VERIFICAR_DATOS":
            estado_cell.fill = PatternFill(fill_type="solid", fgColor="FFEB9C")
            estado_cell.font = Font(color="9C5700", bold=True, name="Arial", size=10)
        elif estado == "PENDIENTE_REVISION":
            estado_cell.fill = PatternFill(fill_type="solid", fgColor="FFC7CE")
            estado_cell.font = Font(color="9C0006", bold=True, name="Arial", size=10)
        estado_cell.alignment = Alignment(horizontal="center", vertical="center")

        for col in [5, 7, 8]:
            c = ws.cell(row=row_idx, column=col)
            c.number_format = '#,##0.00 €'
            c.alignment     = Alignment(horizontal="right")
        ws.cell(row=row_idx, column=2).alignment  = Alignment(horizontal="center")
        ws.cell(row=row_idx, column=4).alignment  = Alignment(horizontal="center")
        ws.cell(row=row_idx, column=6).alignment  = Alignment(horizontal="center")
        ws.cell(row=row_idx, column=10).alignment = Alignment(wrap_text=True, vertical="top")

    total_row = len(rows) + 2
    ws.cell(row=total_row, column=1, value="TOTALES").font = bold_font
    for col in range(1, 11):
        c = ws.cell(row=total_row, column=col)
        c.fill = total_fill; c.border = med_border; c.font = bold_font
    for col in [5, 7, 8]:
        col_letter = get_column_letter(col)
        c = ws.cell(row=total_row, column=col)
        c.value         = f"=SUM({col_letter}2:{col_letter}{total_row - 1})"
        c.number_format = '#,##0.00 €'
        c.alignment     = Alignment(horizontal="right")

    ws.auto_filter.ref = f"A1:{get_column_letter(len(headers))}1"
    ws.freeze_panes    = "A2"
    widths = [14, 8, 18, 14, 12, 8, 12, 14, 22, 55]
    for idx, width in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(idx)].width = width

    # Hoja resumen
    ws2 = wb.create_sheet("Resumen")
    total_paginas = len(rows)
    completas  = sum(1 for r in rows if r.get("estado") == "COMPLETA")
    verificar  = sum(1 for r in rows if r.get("estado") == "VERIFICAR_DATOS")
    pendientes = sum(1 for r in rows if r.get("estado") == "PENDIENTE_REVISION")
    pct        = round((completas / total_paginas) * 100, 2) if total_paginas else 0.0

    if pendientes >= max(2, total_paginas // 2):
        estado_general, estado_color = "PROBLEMAS_MULTIPLES", "FFC7CE"
    elif verificar > 0 or pendientes > 0:
        estado_general, estado_color = "REQUIERE_REVISION", "FFEB9C"
    else:
        estado_general, estado_color = "EXITOSO", "C6EFCE"

    ws2.merge_cells("A1:B1")
    ws2["A1"] = "Resumen de extracción"
    ws2["A1"].fill      = header_fill
    ws2["A1"].font      = white_font
    ws2["A1"].alignment = Alignment(horizontal="center", vertical="center")
    ws2.row_dimensions[1].height = 28

    alt_fill2 = PatternFill(fill_type="solid", fgColor="EBF0FA")
    thin2     = Border(
        left=Side(style="thin", color="B8CCE4"), right=Side(style="thin", color="B8CCE4"),
        top=Side(style="thin", color="B8CCE4"),  bottom=Side(style="thin", color="B8CCE4"),
    )
    summary_rows = [
        ("Total páginas", total_paginas), ("Completas", completas),
        ("Verificar datos", verificar), ("Pendientes", pendientes),
        ("% Completas", f"{pct}%"), ("Estado general", estado_general),
    ]
    for idx, (label, value) in enumerate(summary_rows, start=2):
        c1 = ws2.cell(row=idx, column=1, value=label)
        c2 = ws2.cell(row=idx, column=2, value=value)
        fill = alt_fill2 if idx % 2 == 0 else PatternFill(fill_type="solid", fgColor="FFFFFF")
        for c in [c1, c2]:
            c.border = thin2; c.fill = fill; c.font = base_font
        c1.font = Font(bold=True, name="Arial", size=10)

    ws2.cell(row=7, column=2).fill = PatternFill(fill_type="solid", fgColor=estado_color)
    ws2.column_dimensions["A"].width = 32
    ws2.column_dimensions["B"].width = 22

    # Devolver bytes en lugar de guardar en disco
    import io
    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer.read()
