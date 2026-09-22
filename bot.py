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
# CONFIG
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

    # Myanmar
    if any(
        "\u1000" <= char <= "\u109f"
        for char in text
    ):
        return "myanmar"

    # Chinese
    chinese_count = sum(
        1
        for char in text
        if "\u4e00" <= char <= "\u9fff"
    )

    if chinese_count >= 2:
        return "chinese"

    # Spanish
    spanish_chars = "áéíóúüñÁÉÍÓÚÜÑ¿¡"

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
    }

    words = set(
        text.lower().split()
    )

    if words.intersection(spanish_words):
        return "spanish"

    return "english"


# =========================================================
# PROMPT
# =========================================================

def build_prompt(text, language):

    if language == "myanmar":

        return f"""
Translate this Burmese text.

Return:
SPANISH: Professional formal Venezuelan Spanish
ENGLISH: Natural English
CHINESE: Natural Simplified Chinese

Rules:
- Preserve meaning exactly.
- Keep wording close to original.
- Do not add information.
- Do not remove information.
- Do not explain.
- Keep names, numbers and amounts unchanged.

Original:
{text}

Format exactly:

SPANISH:
...

ENGLISH:
...

CHINESE:
...
"""

    if language == "chinese":

        return f"""
Translate this Chinese text.

Return:
SPANISH: Professional formal Venezuelan Spanish
MYANMAR: Concise natural Burmese
ENGLISH: Natural English

Rules:
- Preserve meaning exactly.
- Keep wording close to original.
- Do not add information.
- Do not remove information.
- Do not explain.
- Keep names, numbers and amounts unchanged.

Original:
{text}

Format exactly:

SPANISH:
...

MYANMAR:
...

ENGLISH:
...
"""

    return f"""
Translate this text.

Return:
SPANISH: Professional formal Venezuelan Spanish
MYANMAR: Concise natural Burmese
CHINESE: Natural Simplified Chinese

Rules:
- Preserve meaning exactly.
- Keep wording close to original.
- Do not add information.
- Do not remove information.
- Do not explain.
- Keep names, numbers and amounts unchanged.

Original:
{text}

Format exactly:

SPANISH:
...

MYANMAR:
...

CHINESE:
...
"""


# =========================================================
# GEMINI API
# =========================================================

def gemini_translate(text):

    if not GEMINI_API_KEY:
        raise RuntimeError(
            "GEMINI_API_KEY is missing"
        )

    language = detect_language(text)

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
    # FAST REQUEST
    # =====================================================

    for attempt in range(3):

        try:

            logger.info(
                "Gemini request %s/3",
                attempt + 1
            )

            response = requests.post(
                GEMINI_URL,
                headers=headers,
                json=data,
                timeout=25
            )

            status = response.status_code

            logger.info(
                "Gemini status: %s",
                status
            )

            # -------------------------------------------------
            # SUCCESS
            # -------------------------------------------------

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

                return answer

            # -------------------------------------------------
            # RETRY ONLY TEMPORARY ERRORS
            # -------------------------------------------------

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

                if attempt < 2:

                    # Fast retry
                    time.sleep(
                        1.5 * (attempt + 1)
                    )

                    continue

            # -------------------------------------------------
            # RATE LIMIT
            # -------------------------------------------------

            if status == 429:

                logger.warning(
                    "Gemini rate limit"
                )

                if attempt < 2:

                    time.sleep(2)

                    continue

            # -------------------------------------------------
            # OTHER ERROR
            # -------------------------------------------------

            logger.error(
                "Gemini error: %s",
                response.text[:1000]
            )

            raise RuntimeError(
                f"Gemini API error {status}"
            )

        except requests.RequestException as error:

            logger.warning(
                "Connection error: %s",
                error
            )

            if attempt < 2:

                time.sleep(1)

                continue

            raise RuntimeError(
                "Gemini connection failed"
            )

    raise RuntimeError(
        "Gemini unavailable"
    )


# =========================================================
# START COMMAND
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

    text = update.message.text

    if not text:
        return

    text = text.strip()

    if not text:
        return

    # -----------------------------------------------------
    # LENGTH CHECK
    # -----------------------------------------------------

    if len(text) > MAX_TEXT_LENGTH:

        await update.message.reply_text(
            "စာအရမ်းရှည်နေပါတယ်။\n"
            "5000 characters အောက်နဲ့ ပြန်ပို့ပေးပါ။"
        )

        return

    # -----------------------------------------------------
    # FAST PROCESSING MESSAGE
    # -----------------------------------------------------

    processing = await update.message.reply_text(
        "⏳ ဘာသာပြန်နေပါတယ်..."
    )

    try:

        # Run Gemini outside Telegram event loop
        result = await asyncio.to_thread(
            gemini_translate,
            text
        )

        # -------------------------------------------------
        # SEND RESULT
        # -------------------------------------------------

        await processing.edit_text(
            result
        )

    except Exception as error:

        logger.exception(
            "Translation error: %s",
            error
        )

        await processing.edit_text(
            "❌ ဘာသာပြန်ရာမှာ ပြဿနာဖြစ်သွားပါတယ်။\n"
            "ခဏနေရင် ပြန်စမ်းကြည့်ပါ။"
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
        ("0.0.0.0", port),
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

    # -----------------------------------------------------
    # CHECK TOKEN
    # -----------------------------------------------------

    if not TOKEN:

        raise RuntimeError(
            "TOKEN environment variable is missing"
        )

    # -----------------------------------------------------
    # CHECK GEMINI KEY
    # -----------------------------------------------------

    if not GEMINI_API_KEY:

        raise RuntimeError(
            "GEMINI_API_KEY environment variable is missing"
        )

    logger.info(
        "Environment variables loaded"
    )

    logger.info(
        "Using model: %s",
        MODEL
    )

    # -----------------------------------------------------
    # RENDER HEALTH SERVER
    # -----------------------------------------------------

    health_thread = threading.Thread(
        target=run_health_server,
        daemon=True
    )

    health_thread.start()

    # -----------------------------------------------------
    # TELEGRAM APPLICATION
    # -----------------------------------------------------

    app = (
        ApplicationBuilder()
        .token(TOKEN)
        .build()
    )

    # -----------------------------------------------------
    # /START
    # -----------------------------------------------------

    app.add_handler(
        CommandHandler(
            "start",
            start
        )
    )

    # -----------------------------------------------------
    # TEXT MESSAGES
    # -----------------------------------------------------

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            translate_text
        )
    )

    # -----------------------------------------------------
    # START
    # -----------------------------------------------------

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
