"""
Telegram Bot — FacturAI
Recibe un PDF y devuelve el Excel extraído.
Misma lógica que el endpoint /extract de la web.
"""
import os
import logging
import asyncio

import httpx
import anthropic

from extract import pdf_to_page_images, extract_invoice_from_page, sort_and_renumber_rows, create_invoice_excel

logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_API       = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
ANTHROPIC_API_KEY  = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL       = os.getenv("ANTHROPIC_MODEL", "claude-opus-4-5")


# ── Telegram helpers ───────────────────────────────────────────────────────────
async def tg_send(chat_id: int, text: str):
    async with httpx.AsyncClient() as client:
        await client.post(f"{TELEGRAM_API}/sendMessage",
                          json={"chat_id": chat_id, "text": text}, timeout=15)

async def tg_send_action(chat_id: int, action: str = "upload_document"):
    async with httpx.AsyncClient() as client:
        await client.post(f"{TELEGRAM_API}/sendChatAction",
                          json={"chat_id": chat_id, "action": action}, timeout=5)

async def tg_send_document(chat_id: int, filename: str, data: bytes):
    async with httpx.AsyncClient() as client:
        await client.post(
            f"{TELEGRAM_API}/sendDocument",
            data={"chat_id": chat_id},
            files={"document": (filename, data,
                   "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            timeout=60,
        )

async def tg_download_file(file_id: str) -> bytes:
    async with httpx.AsyncClient() as client:
        r1   = await client.get(f"{TELEGRAM_API}/getFile?file_id={file_id}", timeout=10)
        path = r1.json()["result"]["file_path"]
        r2   = await client.get(
            f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{path}", timeout=60)
        return r2.content


# ── Procesamiento de updates ───────────────────────────────────────────────────
async def process_update(update: dict):
    message = update.get("message") or update.get("edited_message")
    if not message:
        return

    chat_id  = message["chat"]["id"]
    document = message.get("document")
    text     = message.get("text", "").strip()

    # Comando /start o mensaje de texto → instrucciones
    if text:
        await tg_send(chat_id,
            "📄 Envíame un PDF con facturas o tickets y te devuelvo el Excel contable listo para descargar.")
        return

    # Sin PDF adjunto
    if not document:
        await tg_send(chat_id, "Por favor envía un archivo PDF.")
        return

    # Validar que sea PDF
    mime = document.get("mime_type", "")
    if mime != "application/pdf":
        await tg_send(chat_id, "El archivo debe ser un PDF.")
        return

    await tg_send_action(chat_id, "upload_document")
    await tg_send(chat_id, "⏳ Procesando tu PDF... puede tardar unos segundos.")

    try:
        # 1. Descargar PDF
        pdf_bytes = await tg_download_file(document["file_id"])

        # 2. Convertir páginas a imágenes
        page_images = await asyncio.to_thread(pdf_to_page_images, pdf_bytes)
        if not page_images:
            await tg_send(chat_id, "❌ No se pudo leer el PDF. Asegúrate de que no esté protegido.")
            return

        # 3. Extraer con Claude (mismo proceso que la web)
        claude_client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
        rows = []
        for idx, page_b64 in enumerate(page_images, start=1):
            row = await extract_invoice_from_page(claude_client, page_b64, idx, CLAUDE_MODEL)
            rows.append(row)

        # 4. Ordenar y numerar
        rows = sort_and_renumber_rows(rows)

        # 5. Generar Excel
        excel_bytes = create_invoice_excel(rows)

        # 6. Enviar Excel
        from datetime import datetime
        filename = f"Facturas_{datetime.now().strftime('%m%Y')}.xlsx"
        await tg_send_document(chat_id, filename, excel_bytes)

        completas = sum(1 for r in rows if r.get("estado") == "COMPLETA")
        await tg_send(chat_id,
            f"✅ {len(rows)} página(s) procesada(s) — {completas} completa(s).")

    except Exception as e:
        logger.error(f"Error procesando PDF en bot: {e}", exc_info=True)
        await tg_send(chat_id, "❌ Ocurrió un error procesando el PDF. Intenta nuevamente.")
