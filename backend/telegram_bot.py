"""
Telegram Bot — integrado en el backend de FacturAI.
Webhook mode: POST /telegram/webhook
Usa solo httpx (ya en requirements) y python-jose (ya en requirements).
Sin paquetes nuevos.
"""
import os
import json
import logging
import time
import tempfile
import math

import httpx
from jose import jwt as jose_jwt

logger = logging.getLogger(__name__)

# ── Configuración ──────────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_API       = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
OPENAI_API_KEY     = os.getenv("OPENAI_API_KEY", "")
ASSISTANT_ID       = os.getenv("ASSISTANT_ID", "asst_ilU2IP5JDpIdIhPGFPoomhRN")
SPREADSHEET_NAME   = "Whitelist"
CREDENTIALS_PATH   = "/tmp/google_credentials.json"

OPENAI_HEADERS = {
    "Authorization": f"Bearer {OPENAI_API_KEY}",
    "Content-Type":  "application/json",
    "OpenAI-Beta":   "assistants=v2",
}


# ── Google credentials desde env var ──────────────────────────────────────────
def _setup_credentials():
    if os.path.exists(CREDENTIALS_PATH):
        return True
    creds_json = os.getenv("GOOGLE_CREDENTIALS_JSON", "")
    if creds_json:
        with open(CREDENTIALS_PATH, "w") as f:
            f.write(creds_json)
        return True
    local = os.path.join(os.path.dirname(__file__), "..", "credentials.json")
    if os.path.exists(local):
        import shutil
        shutil.copy(local, CREDENTIALS_PATH)
        return True
    return False


def _google_access_token() -> str:
    """Obtiene un access token de Google usando service account JWT."""
    with open(CREDENTIALS_PATH) as f:
        sa = json.load(f)

    now = int(time.time())
    claims = {
        "iss":   sa["client_email"],
        "scope": "https://www.googleapis.com/auth/spreadsheets",
        "aud":   "https://oauth2.googleapis.com/token",
        "iat":   now,
        "exp":   now + 3600,
    }
    signed = jose_jwt.encode(claims, sa["private_key"], algorithm="RS256")

    import urllib.request, urllib.parse
    data = urllib.parse.urlencode({
        "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
        "assertion":  signed,
    }).encode()
    req = urllib.request.Request(
        "https://oauth2.googleapis.com/token",
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        result = json.loads(resp.read())
    return result["access_token"]


def _get_whitelist_emails() -> list[str]:
    """Devuelve lista de emails de la columna C de la hoja Whitelist."""
    if not _setup_credentials():
        return []
    token = _google_access_token()

    # Buscar spreadsheet por nombre
    search_url = "https://www.googleapis.com/drive/v3/files"
    params = f"?q=name%3D'{SPREADSHEET_NAME}'%20and%20mimeType%3D'application%2Fvnd.google-apps.spreadsheet'&fields=files(id)"
    import urllib.request
    req = urllib.request.Request(
        search_url + params,
        headers={"Authorization": f"Bearer {token}"},
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        files = json.loads(resp.read()).get("files", [])
    if not files:
        logger.error("Spreadsheet 'Whitelist' no encontrado")
        return []

    spreadsheet_id = files[0]["id"]
    sheet_url = f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}/values/Sheet1!C2:C"
    req2 = urllib.request.Request(
        sheet_url,
        headers={"Authorization": f"Bearer {token}"},
    )
    with urllib.request.urlopen(req2, timeout=10) as resp:
        values = json.loads(resp.read()).get("values", [])
    return [row[0].lower() for row in values if row]


# ── Estado en memoria ──────────────────────────────────────────────────────────
validated_users: dict[int, str] = {}
user_threads:    dict[int, str] = {}
waiting_email:   set[int]       = set()


# ── Telegram helpers ───────────────────────────────────────────────────────────
async def tg_send(chat_id: int, text: str):
    async with httpx.AsyncClient() as client:
        await client.post(
            f"{TELEGRAM_API}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"},
            timeout=15,
        )

async def tg_send_action(chat_id: int, action: str = "typing"):
    async with httpx.AsyncClient() as client:
        await client.post(
            f"{TELEGRAM_API}/sendChatAction",
            json={"chat_id": chat_id, "action": action},
            timeout=5,
        )

async def tg_get_file_path(file_id: str) -> str:
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{TELEGRAM_API}/getFile?file_id={file_id}", timeout=10)
        return resp.json()["result"]["file_path"]

async def tg_download_file(file_path: str) -> bytes:
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{file_path}",
            timeout=30,
        )
        return resp.content


# ── OpenAI Assistant via httpx ─────────────────────────────────────────────────
async def openai_create_thread() -> str:
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://api.openai.com/v1/threads",
            headers=OPENAI_HEADERS,
            json={},
            timeout=15,
        )
        return resp.json()["id"]

async def openai_ask(thread_id: str, user_message: str) -> str:
    async with httpx.AsyncClient() as client:
        # Add message
        await client.post(
            f"https://api.openai.com/v1/threads/{thread_id}/messages",
            headers=OPENAI_HEADERS,
            json={"role": "user", "content": user_message},
            timeout=15,
        )
        # Create run
        run_resp = await client.post(
            f"https://api.openai.com/v1/threads/{thread_id}/runs",
            headers=OPENAI_HEADERS,
            json={"assistant_id": ASSISTANT_ID},
            timeout=15,
        )
        run_id = run_resp.json()["id"]

        # Poll until done
        for _ in range(60):
            await _async_sleep(1)
            status_resp = await client.get(
                f"https://api.openai.com/v1/threads/{thread_id}/runs/{run_id}",
                headers=OPENAI_HEADERS,
                timeout=15,
            )
            status = status_resp.json().get("status")
            if status == "completed":
                msgs_resp = await client.get(
                    f"https://api.openai.com/v1/threads/{thread_id}/messages",
                    headers=OPENAI_HEADERS,
                    timeout=15,
                )
                msgs = msgs_resp.json().get("data", [])
                return next(
                    (m["content"][0]["text"]["value"] for m in msgs if m["role"] == "assistant"),
                    "No pude generar una respuesta.",
                )
            if status in ("failed", "cancelled", "expired"):
                return "Hubo un error al procesar tu solicitud."
    return "Tiempo de espera agotado."

async def openai_transcribe(audio_bytes: bytes, filename: str = "voice.ogg") -> str:
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://api.openai.com/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
            files={"file": (filename, audio_bytes, "audio/ogg")},
            data={"model": "whisper-1"},
            timeout=30,
        )
        return resp.json().get("text", "")

async def _async_sleep(seconds: float):
    import asyncio
    await asyncio.sleep(seconds)

async def get_or_create_thread(chat_id: int) -> str:
    if chat_id not in user_threads:
        user_threads[chat_id] = await openai_create_thread()
    return user_threads[chat_id]


# ── Procesamiento de updates ───────────────────────────────────────────────────
async def process_update(update: dict):
    message = update.get("message") or update.get("edited_message")
    if not message:
        return

    chat_id  = message["chat"]["id"]
    text     = message.get("text", "").strip()
    voice    = message.get("voice")
    username = message.get("from", {}).get("username", f"user_{chat_id}")

    # /start
    if text.lower() in ("/start",):
        if chat_id in validated_users:
            await tg_send(chat_id, "✅ Ya estás validado. Puedes escribirme.")
        else:
            waiting_email.add(chat_id)
            await tg_send(chat_id, "Por favor, proporciona tu email para validar el acceso:")
        return

    # Esperando email
    if chat_id in waiting_email and text:
        try:
            emails = _get_whitelist_emails()
            if text.lower() in emails:
                validated_users[chat_id] = text.lower()
                waiting_email.discard(chat_id)
                await tg_send(chat_id, f"✅ Acceso concedido. ¡Bienvenido, {username}!")
            else:
                await tg_send(chat_id, "❌ Email no válido. Inténtalo nuevamente.")
        except Exception as e:
            logger.error(f"Error validando email: {e}")
            await tg_send(chat_id, "❌ Error al validar. Intenta más tarde.")
        return

    # Sin validar
    if chat_id not in validated_users:
        waiting_email.add(chat_id)
        await tg_send(chat_id, "Por favor, proporciona tu email para validar el acceso:")
        return

    # Mensaje de texto → OpenAI Assistant
    if text:
        await tg_send_action(chat_id, "typing")
        try:
            thread_id = await get_or_create_thread(chat_id)
            reply     = await openai_ask(thread_id, text)
            await tg_send(chat_id, reply)
        except Exception as e:
            logger.error(f"Error procesando texto: {e}")
            await tg_send(chat_id, "Hubo un error. Intenta nuevamente.")

    # Nota de voz → Whisper → texto → OpenAI Assistant → respuesta texto
    if voice:
        await tg_send_action(chat_id, "typing")
        try:
            file_path   = await tg_get_file_path(voice["file_id"])
            voice_bytes = await tg_download_file(file_path)
            transcribed = await openai_transcribe(voice_bytes)
            if not transcribed:
                await tg_send(chat_id, "No pude transcribir el audio.")
                return
            thread_id = await get_or_create_thread(chat_id)
            reply     = await openai_ask(thread_id, transcribed)
            await tg_send(chat_id, f"🎤 _{transcribed}_\n\n{reply}")
        except Exception as e:
            logger.error(f"Error procesando voz: {e}")
            await tg_send(chat_id, "No pude procesar la nota de voz.")
