"""
Telegram Bot — integrado en el backend de FacturAI.
Webhook mode: recibe updates en POST /telegram/webhook
"""
import os
import json
import logging
import time
import tempfile

import httpx
import gspread
from gtts import gTTS
from openai import OpenAI
from google.oauth2.service_account import Credentials

logger = logging.getLogger(__name__)

# ── Configuración ──────────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_API       = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
ASSISTANT_ID       = os.getenv("ASSISTANT_ID", "asst_ilU2IP5JDpIdIhPGFPoomhRN")
SPREADSHEET_NAME   = "Whitelist"
CREDENTIALS_PATH   = "/tmp/google_credentials.json"

# ── Cliente OpenAI ─────────────────────────────────────────────────────────────
_openai_client: OpenAI | None = None

def get_openai():
    global _openai_client
    if _openai_client is None:
        api_key = os.getenv("OPENAI_API_KEY", "")
        if not api_key:
            raise RuntimeError("Falta OPENAI_API_KEY")
        _openai_client = OpenAI(api_key=api_key)
    return _openai_client


# ── Google Credentials ─────────────────────────────────────────────────────────
def _setup_credentials():
    """Escribe el JSON de Google desde env var a /tmp."""
    if os.path.exists(CREDENTIALS_PATH):
        return
    creds_json = os.getenv("GOOGLE_CREDENTIALS_JSON", "")
    if creds_json:
        with open(CREDENTIALS_PATH, "w") as f:
            f.write(creds_json)
        logger.info("✅ Google credentials escritas en /tmp")
    else:
        # Fallback: copiar desde ruta local si existe (desarrollo)
        local = os.path.join(os.path.dirname(__file__), "..", "credentials.json")
        if os.path.exists(local):
            import shutil
            shutil.copy(local, CREDENTIALS_PATH)
        else:
            logger.warning("⚠️  GOOGLE_CREDENTIALS_JSON no configurado — validación por email no disponible")


def get_sheet():
    _setup_credentials()
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_file(CREDENTIALS_PATH, scopes=scope)
    gc    = gspread.authorize(creds)
    sheet = gc.open(SPREADSHEET_NAME).sheet1
    return sheet


# ── Estado en memoria ──────────────────────────────────────────────────────────
# (se resetea con cada redeploy — suficiente para el uso actual)
validated_users: dict[int, str] = {}
user_threads:    dict[int, str] = {}
waiting_email:   set[int]       = set()


# ── Telegram helpers ───────────────────────────────────────────────────────────
async def tg_send(chat_id: int, text: str):
    async with httpx.AsyncClient() as client:
        await client.post(
            f"{TELEGRAM_API}/sendMessage",
            json={"chat_id": chat_id, "text": text},
            timeout=15,
        )

async def tg_send_action(chat_id: int, action: str = "typing"):
    async with httpx.AsyncClient() as client:
        await client.post(
            f"{TELEGRAM_API}/sendChatAction",
            json={"chat_id": chat_id, "action": action},
            timeout=5,
        )

async def tg_send_voice(chat_id: int, audio_path: str):
    async with httpx.AsyncClient() as client:
        with open(audio_path, "rb") as f:
            await client.post(
                f"{TELEGRAM_API}/sendVoice",
                data={"chat_id": chat_id},
                files={"voice": f},
                timeout=30,
            )

async def tg_get_file_path(file_id: str) -> str:
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{TELEGRAM_API}/getFile?file_id={file_id}", timeout=10)
        return resp.json()["result"]["file_path"]

async def tg_download_file(file_path: str) -> bytes:
    url = f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{file_path}"
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, timeout=30)
        return resp.content


# ── OpenAI Assistant helper ────────────────────────────────────────────────────
def ask_assistant(thread_id: str, user_message: str) -> str:
    oai = get_openai()
    oai.beta.threads.messages.create(
        thread_id=thread_id, role="user", content=user_message
    )
    run = oai.beta.threads.runs.create(
        thread_id=thread_id, assistant_id=ASSISTANT_ID
    )
    while True:
        run = oai.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run.id)
        if run.status == "completed":
            msgs = oai.beta.threads.messages.list(thread_id=thread_id)
            return next(
                (m.content[0].text.value for m in msgs.data if m.role == "assistant"),
                "No pude generar una respuesta.",
            )
        if run.status in ("failed", "cancelled", "expired"):
            return "Hubo un error al procesar tu solicitud."
        time.sleep(1)


def get_or_create_thread(chat_id: int) -> str:
    if chat_id not in user_threads:
        oai = get_openai()
        thread = oai.beta.threads.create()
        user_threads[chat_id] = thread.id
    return user_threads[chat_id]


# ── Procesamiento de updates ───────────────────────────────────────────────────
async def process_update(update: dict):
    """Punto de entrada principal para cada update de Telegram."""
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
            sheet  = get_sheet()
            emails = [e.lower() for e in sheet.col_values(3)[1:]]
            if text.lower() in emails:
                row = emails.index(text.lower()) + 2
                sheet.update_cell(row, 6, username)
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
            thread_id = get_or_create_thread(chat_id)
            reply     = ask_assistant(thread_id, text)
            await tg_send(chat_id, reply)
        except Exception as e:
            logger.error(f"Error procesando texto: {e}")
            await tg_send(chat_id, "Hubo un error. Intenta nuevamente.")

    # Nota de voz → Whisper → OpenAI Assistant → gTTS
    if voice:
        await tg_send_action(chat_id, "record_voice")
        try:
            file_path   = await tg_get_file_path(voice["file_id"])
            voice_bytes = await tg_download_file(file_path)

            with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
                tmp.write(voice_bytes)
                tmp_path = tmp.name

            oai = get_openai()
            with open(tmp_path, "rb") as af:
                transcription = oai.audio.transcriptions.create(model="whisper-1", file=af)

            thread = oai.beta.threads.create()
            oai.beta.threads.messages.create(
                thread_id=thread.id, role="user", content=transcription.text
            )
            run = oai.beta.threads.runs.create(
                thread_id=thread.id, assistant_id=ASSISTANT_ID
            )
            while True:
                run = oai.beta.threads.runs.retrieve(thread_id=thread.id, run_id=run.id)
                if run.status == "completed":
                    msgs   = oai.beta.threads.messages.list(thread_id=thread.id)
                    reply  = next(
                        (m.content[0].text.value for m in msgs.data if m.role == "assistant"),
                        "No pude generar una respuesta.",
                    )
                    break
                if run.status in ("failed", "cancelled", "expired"):
                    reply = "Error procesando tu nota de voz."
                    break
                time.sleep(1)

            tts       = gTTS(reply, lang="es")
            audio_out = tempfile.mktemp(suffix=".mp3")
            tts.save(audio_out)
            await tg_send_voice(chat_id, audio_out)

        except Exception as e:
            logger.error(f"Error procesando voz: {e}")
            await tg_send(chat_id, "No pude procesar la nota de voz. Intenta nuevamente.")
