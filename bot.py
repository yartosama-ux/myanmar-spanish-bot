import os
import json
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

# Fast / low-latency model
MODEL = "gemini-3.5-flash-lite"

# Streaming endpoint
GEMINI_URL = (
    f"https://generativelanguage.googleapis.com/v1beta/"
    f"models/{MODEL}:streamGenerateContent?alt=sse"
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

    # Spanish characters
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
    }

    words = set(
        text.lower().split()
    )

    if words.intersection(
        spanish_words
    ):
        return "spanish"

    return "english"


# =========================================================
# PROMPT
# =========================================================

def build_prompt(text, language):

    if language == "myanmar":

        return f"""
Translate the following Burmese text.

Output:
SPANISH = professional formal Venezuelan Spanish
ENGLISH = natural English
CHINESE = natural Simplified Chinese

Rules:
- Preserve the exact meaning.
- Keep wording close to the original.
- Do not add information.
- Do not remove information.
- Do not explain.
- Do not summarize.
- Keep names, numbers, dates and money amounts unchanged.
- Venezuelan Spanish should sound natural and professional.

Use exactly:

SPANISH:
...

ENGLISH:
...

CHINESE:
...

TEXT:
{text}
"""

    if language == "chinese":

        return f"""
Translate the following Chinese text.

Output:
SPANISH = professional formal Venezuelan Spanish
MYANMAR = concise natural Burmese
ENGLISH = natural English

Rules:
- Preserve the exact meaning.
- Keep wording close to the original.
- Do not add information.
- Do not remove information.
- Do not explain.
- Do not summarize.
- Keep names, numbers, dates and money amounts unchanged.
- Venezuelan Spanish should sound natural and professional.

Use exactly:

SPANISH:
...

MYANMAR:
...

ENGLISH:
...

TEXT:
{text}
"""

    return f"""
Translate the following text.

Output:
SPANISH = professional formal Venezuelan Spanish
MYANMAR = concise natural Burmese
CHINESE = natural Simplified Chinese

Rules:
- Preserve the exact meaning.
- Keep wording close to the original.
- Do not add information.
- Do not remove information.
- Do not explain.
- Do not summarize.
- Keep names, numbers, dates and money amounts unchanged.
- Venezuelan Spanish should sound natural and professional.

Use exactly:

SPANISH:
...

MYANMAR:
...

CHINESE:
...

TEXT:
{text}
"""


# =========================================================
# GEMINI STREAMING TRANSLATION
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
        "Accept": "text/event-stream",
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
            "maxOutputTokens": 1200,
            "thinkingConfig": {
                "thinkingLevel": "minimal"
            }
        }
    }

    # =====================================================
    # ONLY RETRY TEMPORARY FAILURES
    # =====================================================

    max_attempts = 2

    for attempt in range(max_attempts):

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

                # Connection = 10 sec
                # Read = 45 sec
                timeout=(10, 45),

                # Receive streamed response
                stream=True,
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

                full_text = []

                # ---------------------------------------------
                # Read SSE stream
                # ---------------------------------------------

                for line in response.iter_lines(
                    decode_unicode=True
                ):

                    if not line:
                        continue

                    # SSE format:
                    # data: {...}

                    if not line.startswith(
                        "data:"
                    ):
                        continue

                    json_text = line[
                        5:
                    ].strip()

                    if not json_text:
                        continue

                    try:

                        chunk = json.loads(
                            json_text
                        )

                    except json.JSONDecodeError:

                        continue

                    candidates = chunk.get(
                        "candidates",
                        []
                    )

                    if not candidates:
                        continue

                    content = candidates[0].get(
                        "content",
                        {}
                    )

                    parts = content.get(
                        "parts",
                        []
                    )

                    for part in parts:

                        part_text = part.get(
                            "text",
                            ""
                        )

                        if part_text:
                            full_text.append(
                                part_text
                            )

                answer = "".join(
                    full_text
                ).strip()

                if not answer:

                    raise RuntimeError(
                        "Gemini returned empty response"
                    )

                logger.info(
                    "Translation successful"
                )

                return answer

            # =================================================
            # TEMPORARY ERROR
            # =================================================

            if status in (
                500,
                502,
                503,
                504,
            ):

                logger.warning(
                    "Temporary Gemini error: %s",
                    status
                )

                if attempt < max_attempts - 1:

                    time.sleep(1)

                    continue

            # =================================================
            # RATE LIMIT
            # =================================================

            if status == 429:

                logger.warning(
                    "Gemini rate limit"
                )

                if attempt < max_attempts - 1:

                    time.sleep(2)

                    continue

            # =================================================
            # OTHER ERROR
            # =================================================

            error_body = response.text[:1000]

            logger.error(
                "Gemini error: %s",
                error_body
            )

            raise RuntimeError(
                f"Gemini API error {status}"
            )

        # =====================================================
        # TIMEOUT
        # =====================================================

        except requests.exceptions.ReadTimeout:

            logger.warning(
                "Gemini read timeout"
            )

            if attempt < max_attempts - 1:

                time.sleep(1)

                continue

            raise RuntimeError(
                "Gemini response timeout"
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

        # =====================================================
        # CONNECTION ERROR
        # =====================================================

        except requests.exceptions.RequestException as error:

            logger.warning(
                "Gemini connection error: %s",
                error
            )

            if attempt < max_attempts - 1:

                time.sleep(1)

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
    # LENGTH CHECK
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

        # Gemini call in separate thread
        result = await asyncio.to_thread(
            gemini_translate,
            text
        )

        # =================================================
        # FINAL TELEGRAM MESSAGE
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
                "❌ ဘာသာပြန်ရာမှာ ပြဿနာဖြစ်သွားပါတယ်။\n"
                "ခဏနေရင် ပြန်စမ်းကြည့်ပါ။"
            )

        except Exception:

            await update.message.reply_text(
                "❌ ဘာသာပြန်ရာမှာ ပြဿနာဖြစ်သွားပါတယ်။"
            )


# =========================================================
# RENDER HEALTH SERVER
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

    # =====================================================
    # ENVIRONMENT CHECK
    # =====================================================

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
        MODEL
    )

    # =====================================================
    # HEALTH SERVER
    # =====================================================

    health_thread = threading.Thread(
        target=run_health_server,
        daemon=True
    )

    health_thread.start()

    # =====================================================
    # TELEGRAM BOT
    # =====================================================

    app = (
        ApplicationBuilder()
        .token(TOKEN)

        # Allow several users/messages to be processed
        # without waiting for each other.
        .concurrent_updates(8)

        .build()
    )

    # =====================================================
    # COMMAND
    # =====================================================

    app.add_handler(
        CommandHandler(
            "start",
            start
        )
    )

    # =====================================================
    # TEXT
    # =====================================================

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            translate_text
        )
    )

    # =====================================================
    # START
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
