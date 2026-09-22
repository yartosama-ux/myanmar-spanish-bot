import os
import time
import asyncio
import logging
import threading
import requests

from http.server import HTTPServer, BaseHTTPRequestHandler

from requests.adapters import HTTPAdapter
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)


# =========================================================
# CONFIG
# =========================================================

TOKEN = os.getenv("TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Fast Gemini model
MODEL = "gemini-3.1-flash-lite"

GEMINI_URL = (
    f"https://generativelanguage.googleapis.com/v1beta/"
    f"models/{MODEL}:generateContent"
)

# Telegram message limit protection
MAX_TEXT_LENGTH = 5000


# =========================================================
# LOGGING
# =========================================================

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)

logger = logging.getLogger("translation_bot")


# =========================================================
# HTTP SESSION
# Reuse connections = less connection overhead
# =========================================================

session = requests.Session()

adapter = HTTPAdapter(
    pool_connections=20,
    pool_maxsize=20,
    max_retries=0,
)

session.mount("https://", adapter)


# =========================================================
# LANGUAGE DETECTION
# =========================================================

def detect_language(text: str) -> str:

    # Burmese
    if any("\u1000" <= char <= "\u109f" for char in text):
        return "myanmar"

    # Chinese
    chinese_count = sum(
        1 for char in text
        if "\u4e00" <= char <= "\u9fff"
    )

    if chinese_count >= 2:
        return "chinese"

    # Spanish special characters
    spanish_chars = "áéíóúüñÁÉÍÓÚÜÑ¿¡"

    if any(char in spanish_chars for char in text):
        return "spanish"

    # Common Spanish words
    spanish_words = {
        "que",
        "para",
        "como",
        "por",
        "una",
        "uno",
        "los",
        "las",
        "del",
        "con",
        "esta",
        "está",
        "tengo",
        "quiero",
        "puedo",
        "dinero",
        "porque",
        "pero",
        "usted",
        "ustedes",
        "gracias",
        "hola",
        "también",
        "tambien",
        "esto",
        "eso",
        "cuando",
        "cómo",
        "dónde",
        "donde",
        "hacer",
        "tiene",
        "tienen",
    }

    words = set(
        word.lower().strip(".,!?¿¡")
        for word in text.split()
    )

    if words.intersection(spanish_words):
        return "spanish"

    # Default = English
    return "english"


# =========================================================
# PROMPT
# Only produce ONE translation
# =========================================================

def build_prompt(text: str, language: str) -> str:

    if language == "spanish":

        return f"""
Translate the following Spanish text into Burmese.

Requirements:
- Preserve the exact original meaning.
- Translate accurately and naturally into Burmese.
- Do not add information.
- Do not remove information.
- Do not explain.
- Do not summarize.
- Keep names, numbers, dates, amounts and important details unchanged.
- Return ONLY the Burmese translation.

Spanish:
{text}
"""

    # Myanmar / English / Chinese -> Venezuelan Spanish

    return f"""
Translate the following text into professional Venezuelan Spanish.

Requirements:
- Write as a professional manager communicating with a client or colleague.
- Use natural, clear and professional Venezuelan Spanish.
- Preserve the exact original meaning.
- Stay close to the original wording and intention.
- Do not add information.
- Do not remove information.
- Do not explain.
- Do not summarize.
- Keep names, numbers, dates, amounts and important details unchanged.
- Return ONLY the Spanish translation.

Source language: {language}

Text:
{text}
"""


# =========================================================
# GEMINI TRANSLATION
# =========================================================

def gemini_translate(text: str) -> str:

    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY is missing")

    language = detect_language(text)

    prompt = build_prompt(text, language)

    headers = {
        "x-goog-api-key": GEMINI_API_KEY,
        "Content-Type": "application/json",
    }

    data = {
        "contents": [
            {
                "parts": [
                    {
                        "text": prompt
                    }
                ]
            }
        ],

        "generationConfig": {
            # Keep response reasonably short
            "maxOutputTokens": 1000,

            # Fastest practical thinking level
            "thinkingConfig": {
                "thinkingLevel": "minimal"
            }
        }
    }

    # Only one retry for temporary server problems
    max_attempts = 2

    for attempt in range(max_attempts):

        try:

            start_time = time.time()

            response = session.post(
                GEMINI_URL,
                headers=headers,
                json=data,
                timeout=(5, 30),
            )

            elapsed = round(
                time.time() - start_time,
                2
            )

            logger.info(
                "Gemini response: %s | %.2fs | language=%s",
                response.status_code,
                elapsed,
                language,
            )

            # -------------------------------------------------
            # SUCCESS
            # -------------------------------------------------

            if response.status_code == 200:

                result = response.json()

                candidates = result.get(
                    "candidates",
                    []
                )

                if not candidates:
                    raise RuntimeError(
                        "Gemini returned no candidates"
                    )

                content = candidates[0].get(
                    "content",
                    {}
                )

                parts = content.get(
                    "parts",
                    []
                )

                answer_parts = []

                for part in parts:

                    # Ignore thought parts if returned
                    if part.get("thought"):
                        continue

                    part_text = part.get(
                        "text",
                        ""
                    )

                    if part_text:
                        answer_parts.append(
                            part_text
                        )

                answer = "".join(
                    answer_parts
                ).strip()

                if not answer:
                    raise RuntimeError(
                        "Gemini returned empty response"
                    )

                return answer

            # -------------------------------------------------
            # TEMPORARY SERVER ERRORS
            # -------------------------------------------------

            if response.status_code in (
                500,
                502,
                503,
                504,
            ):

                if attempt < max_attempts - 1:

                    logger.warning(
                        "Gemini temporary error %s. Retrying...",
                        response.status_code,
                    )

                    time.sleep(0.7)
                    continue

            # -------------------------------------------------
            # RATE LIMIT
            # -------------------------------------------------

            if response.status_code == 429:

                if attempt < max_attempts - 1:

                    logger.warning(
                        "Gemini rate limited. Retrying..."
                    )

                    time.sleep(1)
                    continue

            # -------------------------------------------------
            # OTHER ERROR
            # -------------------------------------------------

            try:
                error_data = response.json()
                logger.error(
                    "Gemini error: %s",
                    error_data,
                )
            except Exception:
                logger.error(
                    "Gemini error text: %s",
                    response.text[:500],
                )

            raise RuntimeError(
                f"Gemini API error {response.status_code}"
            )

        # -----------------------------------------------------
        # TIMEOUT
        # -----------------------------------------------------

        except requests.exceptions.ReadTimeout:

            logger.warning(
                "Gemini read timeout"
            )

            if attempt < max_attempts - 1:
                time.sleep(0.7)
                continue

            raise RuntimeError(
                "Gemini response timeout"
            )

        # -----------------------------------------------------
        # CONNECTION TIMEOUT
        # -----------------------------------------------------

        except requests.exceptions.ConnectTimeout:

            logger.warning(
                "Gemini connection timeout"
            )

            if attempt < max_attempts - 1:
                time.sleep(0.7)
                continue

            raise RuntimeError(
                "Gemini connection timeout"
            )

        # -----------------------------------------------------
        # CONNECTION ERROR
        # -----------------------------------------------------

        except requests.exceptions.RequestException as error:

            logger.warning(
                "Gemini connection error: %s",
                error,
            )

            if attempt < max_attempts - 1:
                time.sleep(0.7)
                continue

            raise RuntimeError(
                "Gemini connection failed"
            )

    raise RuntimeError(
        "Gemini unavailable"
    )


# =========================================================
# /START
# =========================================================

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    if not update.message:
        return

    await update.message.reply_text(
        "မင်္ဂလာပါ 👋\n\n"
        "Translation Bot မှ ကြိုဆိုပါတယ်။\n\n"

        "🇲🇲 မြန်မာ → 🇻🇪 Spanish\n"
        "🇬🇧 English → 🇻🇪 Spanish\n"
        "🇨🇳 Chinese → 🇻🇪 Spanish\n"
        "🇪🇸 Spanish → 🇲🇲 မြန်မာ\n\n"

        "မြန်မာ / English / Chinese ပို့ပါက "
        "Professional Venezuelan Spanish ဖြင့် ပြန်ပေးပါမယ်။\n\n"

        "Spanish ပို့ပါက "
        "အဓိပ္ပာယ်တိကျသော မြန်မာဘာသာဖြင့် ပြန်ပေးပါမယ်။"
    )


# =========================================================
# TRANSLATION HANDLER
# =========================================================

async def translate_text(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    if not update.message:
        return

    if not update.message.text:
        return

    text = update.message.text.strip()

    if not text:
        return

    # -------------------------------------------------------
    # Length check
    # -------------------------------------------------------

    if len(text) > MAX_TEXT_LENGTH:

        await update.message.reply_text(
            "❌ စာအရမ်းရှည်နေပါတယ်။\n\n"
            "5000 characters အောက်နဲ့ "
            "ခွဲပြီး ပို့ပေးပါ။"
        )

        return

    # -------------------------------------------------------
    # Show processing message
    # -------------------------------------------------------

    processing = await update.message.reply_text(
        "⚡ ဘာသာပြန်နေပါတယ်..."
    )

    try:

        # Gemini request runs outside Telegram event loop
        result = await asyncio.to_thread(
            gemini_translate,
            text,
        )

        # Replace processing message
        await processing.edit_text(
            result
        )

    except Exception as error:

        logger.exception(
            "Translation failed: %s",
            error,
        )

        try:

            await processing.edit_text(
                "❌ ဘာသာပြန်ရာမှာ ပြဿနာဖြစ်သွားပါတယ်။\n"
                "ခဏနေရင် ပြန်စမ်းကြည့်ပါ။"
            )

        except Exception:

            await update.message.reply_text(
                "❌ ဘာသာပြန်ရာမှာ ပြဿနာဖြစ်သွားပါတယ်။"
            )


# =========================================================
# HEALTH CHECK SERVER
# Render အတွက်
# =========================================================

class HealthCheckHandler(
    BaseHTTPRequestHandler
):

    def do_GET(self):

        self.send_response(200)

        self.send_header(
            "Content-Type",
            "text/plain; charset=utf-8"
        )

        self.end_headers()

        self.wfile.write(
            b"Telegram Translation Bot is running."
        )

    def log_message(
        self,
        format,
        *args
    ):
        return


def run_health_server():

    port = int(
        os.getenv(
            "PORT",
            "10000"
        )
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


# =========================================================
# MAIN
# =========================================================

def main():

    # -------------------------------------------------------
    # Environment check
    # -------------------------------------------------------

    if not TOKEN:
        raise RuntimeError(
            "TOKEN environment variable is missing"
        )

    if not GEMINI_API_KEY:
        raise RuntimeError(
            "GEMINI_API_KEY environment variable is missing"
        )

    logger.info(
        "Environment variables loaded"
    )

    logger.info(
        "Gemini model: %s",
        MODEL,
    )

    # -------------------------------------------------------
    # Render health server
    # -------------------------------------------------------

    health_thread = threading.Thread(
        target=run_health_server,
        daemon=True,
    )

    health_thread.start()

    # -------------------------------------------------------
    # Telegram application
    # -------------------------------------------------------

    app = (
        ApplicationBuilder()
        .token(TOKEN)
        .concurrent_updates(8)
        .build()
    )

    # Commands
    app.add_handler(
        CommandHandler(
            "start",
            start,
        )
    )

    # Text translation
    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            translate_text,
        )
    )

    logger.info(
        "Telegram Translation Bot started"
    )

    # Start bot
    app.run_polling(
        drop_pending_updates=True
    )


# =========================================================
# RUN
# =========================================================

if __name__ == "__main__":
    main()
