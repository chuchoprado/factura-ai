"""
Telegram Bot — integrado en el backend de FacturAI.
Webhook mode: POST /telegram/webhook
Usa anthropic (ya en requirements) y httpx (ya en requirements).
"""
import os
import logging
import tempfile

import httpx
import anthropic

logger = logging.getLogger(__name__)

# ── Configuración ──────────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_API       = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
ANTHROPIC_API_KEY  = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL       = os.getenv("ANTHROPIC_MODEL", "claude-opus-4-5")

SYSTEM_PROMPT = (
    "Eres un asistente administrativo experto. "
    "Ayudas con contabilidad, facturas, gestión empresarial y consultas generales. "
    "Responde siempre en español, de forma clara y concisa."
)

# ── Historial de conversación por usuario (en memoria) ────────────────────────
# { chat_id: [{"role": "user"|"assistant", "content": "..."}] }
conversations: dict[int, list] = {}


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


# ── Claude helper ──────────────────────────────────────────────────────────────
async def ask_claude(chat_id: int, user_message: str) -> str:
    """Envía mensaje a Claude manteniendo historial por usuario."""
    if chat_id not in conversations:
        conversations[chat_id] = []

    conversations[chat_id].append({"role": "user", "content": user_message})

    # Limitar historial a últimos 20 mensajes para no exceder tokens
    history = conversations[chat_id][-20:]

    client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
    response = await client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=history,
    )

    reply = response.content[0].text
    conversations[chat_id].append({"role": "assistant", "content": reply})
    return reply


# ── Procesamiento de updates ───────────────────────────────────────────────────
async def process_update(update: dict):
    message = update.get("message") or update.get("edited_message")
    if not message:
        return

    chat_id  = message["chat"]["id"]
    text     = message.get("text", "").strip()
    voice    = message.get("voice")
    username = message.get("from", {}).get("first_name", "")

    # /start
    if text.lower() == "/start":
        conversations.pop(chat_id, None)  # reset historial
        await tg_send(chat_id, f"¡Hola{' ' + username if username else ''}! Soy tu asistente administrativo con IA. ¿En qué puedo ayudarte?")
        return

    # Mensaje de texto → Claude
    if text:
        await tg_send_action(chat_id, "typing")
        try:
            reply = await ask_claude(chat_id, text)
            await tg_send(chat_id, reply)
        except Exception as e:
            logger.error(f"Error procesando texto: {e}")
            await tg_send(chat_id, "Hubo un error al procesar tu mensaje. Intenta nuevamente.")

    # Nota de voz → texto → Claude
    if voice:
        await tg_send_action(chat_id, "typing")
        try:
            file_path   = await tg_get_file_path(voice["file_id"])
            voice_bytes = await tg_download_file(file_path)

            # Transcribir con Whisper via OpenAI (si hay clave) o indicar que no hay soporte
            openai_key = os.getenv("OPENAI_API_KEY", "")
            if openai_key:
                async with httpx.AsyncClient() as client:
                    resp = await client.post(
                        "https://api.openai.com/v1/audio/transcriptions",
                        headers={"Authorization": f"Bearer {openai_key}"},
                        files={"file": ("voice.ogg", voice_bytes, "audio/ogg")},
                        data={"model": "whisper-1"},
                        timeout=30,
                    )
                    transcribed = resp.json().get("text", "")
                if transcribed:
                    reply = await ask_claude(chat_id, transcribed)
                    await tg_send(chat_id, f"🎤 _{transcribed}_\n\n{reply}")
                else:
                    await tg_send(chat_id, "No pude transcribir el audio.")
            else:
                await tg_send(chat_id, "Las notas de voz no están disponibles en este momento. Por favor escribe tu mensaje.")
        except Exception as e:
            logger.error(f"Error procesando voz: {e}")
            await tg_send(chat_id, "No pude procesar la nota de voz.")
