import os
import logging
import asyncio
import threading
import requests

from http.server import HTTPServer, BaseHTTPRequestHandler

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)


# ============================================================
# CONFIG
# ============================================================

TOKEN = os.getenv("TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

MODEL = os.getenv("OPENAI_MODEL", "gpt-5.6-luna")

OPENAI_URL = "https://api.openai.com/v1/responses"

MAX_TEXT_LENGTH = 5000


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)

logger = logging.getLogger("translation_bot")


# ============================================================
# CHECK ENVIRONMENT
# ============================================================

if not TOKEN:
    raise RuntimeError("TOKEN is not configured.")

if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY is not configured.")


# ============================================================
# LANGUAGE DETECTION
# ============================================================

def detect_language(text: str) -> str:

    # Myanmar
    if any("\u1000" <= c <= "\u109F" for c in text):
        return "my"

    # Spanish characters
    if any(c in text for c in "áéíóúüñÁÉÍÓÚÜÑ¿¡"):
        return "es"

    # Common Spanish words
    spanish_words = {
        "que",
        "para",
        "porque",
        "como",
        "cuando",
        "donde",
        "tengo",
        "tiene",
        "quiero",
        "puedo",
        "puede",
        "está",
        "estoy",
        "esta",
        "gracias",
        "buenos",
        "buenas",
        "dinero",
        "trabajo",
        "persona",
        "usted",
        "ustedes",
    }

    words = set(text.lower().split())

    if words.intersection(spanish_words):
        return "es"

    return "en"


# ============================================================
# OPENAI TRANSLATION
# ============================================================

def openai_translate(
    text: str,
    target_language: str,
    style: str = "normal",
) -> str:

    if not text.strip():
        return ""

    if target_language == "Venezuelan Spanish":

        instructions = """
You are a professional Venezuelan Spanish translator.

Translate the user's text into natural Venezuelan Spanish.

STRICT RULES:
- Preserve the original meaning exactly.
- Do not rewrite the message.
- Do not summarize.
- Do not add information.
- Do not remove information.
- Do not change names.
- Do not change numbers.
- Do not change dates.
- Do not change money amounts.
- Do not change usernames, URLs or codes.
- Preserve the original tone and intention.
- Use natural Venezuelan Spanish.
- Avoid unnecessary slang.
- For business/work messages, use professional and clear Venezuelan Spanish.
- Return ONLY the translation.
"""

    elif target_language == "Burmese":

        instructions = """
You are a professional Burmese translator.

Translate the user's text into clear, natural Burmese.

STRICT RULES:
- Preserve the original meaning exactly.
- Do not rewrite the message.
- Do not summarize.
- Do not add information.
- Do not remove information.
- Do not change names.
- Do not change numbers.
- Do not change dates.
- Do not change money amounts.
- Preserve URLs and usernames.
- Keep the translation concise and easy to understand.
- Return ONLY the translation.
"""

    elif target_language == "English":

        instructions = """
You are a professional English translator.

Translate the user's text into clear, natural English.

STRICT RULES:
- Preserve the original meaning exactly.
- Do not rewrite.
- Do not summarize.
- Do not add information.
- Do not remove information.
- Preserve names, numbers, dates, amounts and URLs.
- Return ONLY the translation.
"""

    else:
        raise ValueError("Unsupported target language.")

    payload = {
        "model": MODEL,
        "instructions": instructions,
        "input": text,
        "max_output_tokens": 2000,
    }

    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }

    response = requests.post(
        OPENAI_URL,
        headers=headers,
        json=payload,
        timeout=60,
    )

    if response.status_code != 200:

        logger.error(
            "OpenAI API %s: %s",
            response.status_code,
            response.text[:1000],
        )

        raise RuntimeError(
            f"OpenAI API error: {response.status_code}"
        )

    data = response.json()

    result = data.get("output_text")

    if not result:
        logger.error("No output_text returned: %s", data)
        raise RuntimeError("Empty translation returned.")

    return result.strip()


# ============================================================
# TRANSLATION FUNCTIONS
# ============================================================

def to_spanish(text: str) -> str:

    return openai_translate(
        text,
        "Venezuelan Spanish",
    )


def to_myanmar(text: str) -> str:

    return openai_translate(
        text,
        "Burmese",
    )


def to_english(text: str) -> str:

    return openai_translate(
        text,
        "English",
    )


# ============================================================
# /START
# ============================================================

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    message = (
        "မင်္ဂလာပါ 👋\n\n"
        "Telegram Translation Bot မှ ကြိုဆိုပါတယ်။\n\n"
        "🇲🇲 မြန်မာစာ\n"
        "→ 🇻🇪 Venezuelan Spanish\n"
        "→ 🇬🇧 English\n\n"
        "🇪🇸 Spanish\n"
        "→ 🇲🇲 မြန်မာဘာသာ\n\n"
        "🇬🇧 English\n"
        "→ 🇪🇸 Spanish\n"
        "→ 🇲🇲 မြန်မာဘာသာ\n\n"
        "စာပို့လိုက်ပါ။ အလိုအလျောက် ဘာသာပြန်ပေးပါမယ်။"
    )

    await update.message.reply_text(message)


# ============================================================
# TRANSLATE MESSAGE
# ============================================================

async def translate_text(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    if not update.message:
        return

    text = (update.message.text or "").strip()

    if not text:
        return

    # Prevent extremely large requests
    if len(text) > MAX_TEXT_LENGTH:

        await update.message.reply_text(
            f"စာအရှည်က အများဆုံး {MAX_TEXT_LENGTH} characters "
            "အထိသာ လက်ခံပါတယ်။"
        )

        return

    # Temporary message
    status_message = await update.message.reply_text(
        "⏳ ဘာသာပြန်နေပါတယ်..."
    )

    try:

        language = detect_language(text)

        loop = asyncio.get_running_loop()

        # ====================================================
        # MYANMAR
        # ====================================================

        if language == "my":

            spanish_future = loop.run_in_executor(
                None,
                to_spanish,
                text,
            )

            english_future = loop.run_in_executor(
                None,
                to_english,
                text,
            )

            spanish, english = await asyncio.gather(
                spanish_future,
                english_future,
            )

            result = (
                "🇻🇪 Venezuelan Spanish\n"
                "━━━━━━━━━━━━━━━━\n"
                f"{spanish}\n\n"
                "🇬🇧 English\n"
                "━━━━━━━━━━━━━━━━\n"
                f"{english}"
            )

        # ====================================================
        # SPANISH
        # ====================================================

        elif language == "es":

            myanmar = await loop.run_in_executor(
                None,
                to_myanmar,
                text,
            )

            result = (
                "🇲🇲 မြန်မာဘာသာပြန်\n"
                "━━━━━━━━━━━━━━━━\n"
                f"{myanmar}"
            )

        # ====================================================
        # ENGLISH
        # ====================================================

        else:

            spanish_future = loop.run_in_executor(
                None,
                to_spanish,
                text,
            )

            myanmar_future = loop.run_in_executor(
                None,
                to_myanmar,
                text,
            )

            spanish, myanmar = await asyncio.gather(
                spanish_future,
                myanmar_future,
            )

            result = (
                "🇻🇪 Spanish\n"
                "━━━━━━━━━━━━━━━━\n"
                f"{spanish}\n\n"
                "🇲🇲 မြန်မာဘာသာပြန်\n"
                "━━━━━━━━━━━━━━━━\n"
                f"{myanmar}"
            )

        # Delete "translating..."
        try:
            await status_message.delete()
        except Exception:
            pass

        # Telegram message limit protection
        if len(result) <= 4000:

            await update.message.reply_text(result)

        else:

            # Split long result
            for i in range(0, len(result), 4000):

                await update.message.reply_text(
                    result[i:i + 4000]
                )

    except Exception as e:

        logger.exception(
            "Translation failed: %s",
            e,
        )

        try:
            await status_message.edit_text(
                "❌ ဘာသာပြန်ရာတွင် အမှားဖြစ်နေပါတယ်။ "
                "ခဏအကြာတွင် ထပ်မံကြိုးစားပါ။"
            )
        except Exception:
            pass


# ============================================================
# HEALTH CHECK FOR RENDER
# ============================================================

class HealthCheckHandler(BaseHTTPRequestHandler):

    def do_GET(self):

        self.send_response(200)

        self.send_header(
            "Content-Type",
            "text/plain",
        )

        self.end_headers()

        self.wfile.write(b"OK")

    def log_message(self, format, *args):
        return


def run_health_server():

    port = int(
        os.getenv("PORT", "10000")
    )

    server = HTTPServer(
        ("0.0.0.0", port),
        HealthCheckHandler,
    )

    logger.info(
        "Health server running on port %s",
        port,
    )

    server.serve_forever()


# ============================================================
# MAIN
# ============================================================

def main():

    # Render health server
    threading.Thread(
        target=run_health_server,
        daemon=True,
    ).start()

    app = (
        ApplicationBuilder()
        .token(TOKEN)
        .concurrent_updates(True)
        .build()
    )

    app.add_handler(
        CommandHandler(
            "start",
            start,
        )
    )

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            translate_text,
        )
    )

    logger.info(
        "Translation bot started."
    )

    app.run_polling(
        drop_pending_updates=True
    )


if __name__ == "__main__":
    main()
