import os
import time
import asyncio
import logging
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


# =========================================================
# CONFIGURATION
# =========================================================

TOKEN = os.getenv("TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

MODEL = "gemini-3.5-flash-lite"

GEMINI_URL = (
    f"https://generativelanguage.googleapis.com/v1beta/"
    f"models/{MODEL}:generateContent"
)

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
# LANGUAGE DETECTION
# =========================================================

def detect_language(text):

    # -----------------------------------------------------
    # Myanmar
    # -----------------------------------------------------

    if any(
        "\u1000" <= char <= "\u109f"
        for char in text
    ):
        return "myanmar"

    # -----------------------------------------------------
    # Chinese
    # -----------------------------------------------------

    chinese_count = sum(
        1
        for char in text
        if "\u4e00" <= char <= "\u9fff"
    )

    if chinese_count >= 2:
        return "chinese"

    # -----------------------------------------------------
    # Spanish
    # -----------------------------------------------------

    spanish_chars = (
        "áéíóúüñ"
        "ÁÉÍÓÚÜÑ"
        "¿¡"
    )

    if any(
        char in spanish_chars
        for char in text
    ):
        return "spanish"

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
        "también",
        "gracias",
        "hola",
    }

    words = set(
        text.lower().split()
    )

    if words.intersection(
        spanish_words
    ):
        return "spanish"

    # -----------------------------------------------------
    # Default = English / Other
    # -----------------------------------------------------

    return "english"


# =========================================================
# BUILD PROMPT
# =========================================================

def build_prompt(text, language):

    if language == "myanmar":

        return f"""
You are a professional translation assistant.

Translate the original Burmese text into:

1. Professional formal Venezuelan Spanish
2. Natural English
3. Natural Simplified Chinese

Rules:
- Preserve the exact original meaning.
- Keep the wording close to the original.
- Do not rewrite the message.
- Do not add information.
- Do not remove information.
- Do not summarize.
- Do not explain.
- Keep names, numbers, dates and money amounts unchanged.
- Spanish must sound natural and professional for Venezuela.

Return ONLY this format:

SPANISH:
[translation]

ENGLISH:
[translation]

CHINESE:
[translation]

Original text:
{text}
"""

    if language == "chinese":

        return f"""
You are a professional translation assistant.

Translate the original Chinese text into:

1. Professional formal Venezuelan Spanish
2. Concise natural Burmese
3. Natural English

Rules:
- Preserve the exact original meaning.
- Keep the wording close to the original.
- Do not rewrite the message.
- Do not add information.
- Do not remove information.
- Do not summarize.
- Do not explain.
- Keep names, numbers, dates and money amounts unchanged.
- Spanish must sound natural and professional for Venezuela.

Return ONLY this format:

SPANISH:
[translation]

MYANMAR:
[translation]

ENGLISH:
[translation]

Original text:
{text}
"""

    return f"""
You are a professional translation assistant.

Translate the original text into:

1. Professional formal Venezuelan Spanish
2. Concise natural Burmese
3. Natural Simplified Chinese

Rules:
- Preserve the exact original meaning.
- Keep the wording close to the original.
- Do not rewrite the message.
- Do not add information.
- Do not remove information.
- Do not summarize.
- Do not explain.
- Keep names, numbers, dates and money amounts unchanged.
- Spanish must sound natural and professional for Venezuela.

Return ONLY this format:

SPANISH:
[translation]

MYANMAR:
[translation]

CHINESE:
[translation]

Original text:
{text}
"""


# =========================================================
# GEMINI TRANSLATION
# =========================================================

def gemini_translate(text):

    if not GEMINI_API_KEY:

        raise RuntimeError(
            "GEMINI_API_KEY is missing"
        )

    language = detect_language(
        text
    )

    prompt = build_prompt(
        text,
        language
    )

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
            "maxOutputTokens": 1200
        }
    }

    # =====================================================
    # REQUEST
    # =====================================================

    max_attempts = 2

    for attempt in range(
        max_attempts
    ):

        try:

            logger.info(
                "Gemini request %s/%s",
                attempt + 1,
                max_attempts
            )

            response = requests.post(
                GEMINI_URL,
                headers=headers,
                json=data,

                # Connection timeout = 10 sec
                # Read timeout = 40 sec
                timeout=(10, 40)
            )

            status = response.status_code

            logger.info(
                "Gemini HTTP status: %s",
                status
            )

            # =================================================
            # SUCCESS
            # =================================================

            if status == 200:

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

                if not parts:

                    raise RuntimeError(
                        "Gemini returned no text"
                    )

                answer = parts[0].get(
                    "text",
                    ""
                ).strip()

                if not answer:

                    raise RuntimeError(
                        "Gemini returned empty text"
                    )

                logger.info(
                    "Translation successful"
                )

                return answer

            # =================================================
            # TEMPORARY SERVER ERROR
            # =================================================

            if status in (
                500,
                502,
                503,
                504
            ):

                logger.warning(
                    "Temporary Gemini error: %s",
                    status
                )

                logger.warning(
                    "Response: %s",
                    response.text[:500]
                )

                if attempt < max_attempts - 1:

                    logger.info(
                        "Retrying once..."
                    )

                    # Only wait 1.5 seconds
                    time.sleep(1.5)

                    continue

            # =================================================
            # RATE LIMIT
            # =================================================

            if status == 429:

                logger.warning(
                    "Gemini rate limit / quota"
                )

                if attempt < max_attempts - 1:

                    time.sleep(2)

                    continue

            # =================================================
            # OTHER ERROR
            # =================================================

            logger.error(
                "Gemini API error: %s",
                response.text[:1000]
            )

            raise RuntimeError(
                f"Gemini API error {status}"
            )

        except requests.exceptions.ConnectTimeout:

            logger.warning(
                "Gemini connection timeout"
            )

            if attempt < max_attempts - 1:

                time.sleep(1)

                continue

            raise RuntimeError(
                "Gemini connection timeout"
            )

        except requests.exceptions.ReadTimeout:

            logger.warning(
                "Gemini response timeout"
            )

            if attempt < max_attempts - 1:

                logger.info(
                    "Retrying after timeout..."
                )

                time.sleep(1)

                continue

            raise RuntimeError(
                "Gemini response timeout"
            )

        except requests.exceptions.RequestException as error:

            logger.warning(
                "Gemini connection error: %s",
                error
            )

            if attempt < max_attempts - 1:

                time.sleep(1)

                continue

            raise RuntimeError(
                "Could not connect to Gemini"
            )

    raise RuntimeError(
        "Gemini unavailable"
    )


# =========================================================
# /START COMMAND
# =========================================================

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not update.message:
        return

    await update.message.reply_text(
        "မင်္ဂလာပါ 👋\n"
        "Translation Bot မှ ကြိုဆိုပါတယ်။\n\n"

        "🇲🇲 မြန်မာစာ → 🇻🇪 Spanish + 🇬🇧 English + 🇨🇳 Chinese\n"
        "🇪🇸 Spanish → 🇻🇪 Spanish + 🇲🇲 Myanmar + 🇨🇳 Chinese\n"
        "🇬🇧 English → 🇻🇪 Spanish + 🇲🇲 Myanmar + 🇨🇳 Chinese\n"
        "🇨🇳 Chinese → 🇻🇪 Spanish + 🇲🇲 Myanmar + 🇬🇧 English\n\n"

        "ဘာသာပြန်လိုသောစာကို ပို့ပါ။"
    )


# =========================================================
# TRANSLATION HANDLER
# =========================================================

async def translate_text(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not update.message:
        return

    if not update.message.text:
        return

    text = update.message.text.strip()

    if not text:
        return

    # =====================================================
    # TEXT LENGTH
    # =====================================================

    if len(text) > MAX_TEXT_LENGTH:

        await update.message.reply_text(
            "စာအရမ်းရှည်နေပါတယ်။\n"
            "5000 characters အောက်နဲ့ ပြန်ပို့ပေးပါ။"
        )

        return

    # =====================================================
    # PROCESSING MESSAGE
    # =====================================================

    processing = await update.message.reply_text(
        "⏳ ဘာသာပြန်နေပါတယ်..."
    )

    try:

        # Run Gemini without blocking Telegram
        result = await asyncio.to_thread(
            gemini_translate,
            text
        )

        # =================================================
        # SEND RESULT
        # =================================================

        await processing.edit_text(
            result
        )

    except Exception as error:

        logger.exception(
            "Translation failed: %s",
            error
        )

        try:

            await processing.edit_text(
                "❌ ဘာသာပြန်ရာမှာ ပြဿနာတစ်ခု ဖြစ်သွားပါတယ်။\n"
                "ခဏနေရင် ပြန်စမ်းကြည့်ပါ။"
            )

        except Exception:

            await update.message.reply_text(
                "❌ ဘာသာပြန်ရာမှာ ပြဿနာတစ်ခု ဖြစ်သွားပါတယ်။"
            )


# =========================================================
# RENDER HEALTH CHECK
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
        (
            "0.0.0.0",
            port
        ),
        HealthCheckHandler
    )

    logger.info(
        "Health server running on port %s",
        port
    )

    server.serve_forever()


# =========================================================
# MAIN
# =========================================================

def main():

    # =====================================================
    # CHECK TOKEN
    # =====================================================

    if not TOKEN:

        raise RuntimeError(
            "TOKEN environment variable is missing"
        )

    # =====================================================
    # CHECK GEMINI KEY
    # =====================================================

    if not GEMINI_API_KEY:

        raise RuntimeError(
            "GEMINI_API_KEY environment variable is missing"
        )

    logger.info(
        "Environment variables loaded successfully"
    )

    logger.info(
        "Gemini model: %s",
        MODEL
    )

    # =====================================================
    # START HEALTH SERVER
    # =====================================================

    health_thread = threading.Thread(
        target=run_health_server,
        daemon=True
    )

    health_thread.start()

    # =====================================================
    # TELEGRAM APPLICATION
    # =====================================================

    app = (
        ApplicationBuilder()
        .token(TOKEN)
        .build()
    )

    # =====================================================
    # /START
    # =====================================================

    app.add_handler(
        CommandHandler(
            "start",
            start
        )
    )

    # =====================================================
    # TEXT MESSAGES
    # =====================================================

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            translate_text
        )
    )

    # =====================================================
    # START BOT
    # =====================================================

    logger.info(
        "Telegram Translation Bot started"
    )

    app.run_polling(
        drop_pending_updates=True
    )


# =========================================================
# RUN
# =========================================================

if __name__ == "__main__":
    main()
