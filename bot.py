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
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)

logger = logging.getLogger("telegram_translation_bot")


# =========================================================
# LANGUAGE DETECTION
# =========================================================

def detect_language(text):
    """
    Detect the main language of the user's message.
    """

    # Myanmar
    if any("\u1000" <= char <= "\u109f" for char in text):
        return "myanmar"

    # Chinese
    chinese_count = sum(
        1
        for char in text
        if "\u4e00" <= char <= "\u9fff"
    )

    if chinese_count >= 2:
        return "chinese"

    # Spanish common characters / words
    spanish_chars = "áéíóúüñ¿¡ÁÉÍÓÚÜÑ"

    if any(char in spanish_chars for char in text):
        return "spanish"

    spanish_words = [
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
        "está",
        "esta",
        "tengo",
        "quiero",
        "puedo",
        "dinero",
        "porque",
        "pero",
    ]

    lower_text = text.lower()

    if any(
        f" {word} " in f" {lower_text} "
        for word in spanish_words
    ):
        return "spanish"

    # Default = English / other foreign language
    return "english"


# =========================================================
# TRANSLATION INSTRUCTION
# =========================================================

def build_instruction(source_language):

    if source_language == "myanmar":

        return """
You are a professional translation assistant.

The user provided Burmese text.

Translate the ORIGINAL Burmese text into:

1. Professional formal Venezuelan Spanish
2. Natural English
3. Natural Simplified Chinese

IMPORTANT RULES:

- Preserve the original meaning exactly.
- Keep the wording as close to the original as possible.
- Do NOT rewrite the message.
- Do NOT add information.
- Do NOT remove information.
- Do NOT change the intention.
- Do NOT explain anything.
- Do NOT summarize.
- Keep names, numbers, amounts and important details unchanged.
- Spanish must sound natural and professional for Venezuela.

Return ONLY this format:

SPANISH:
[translation]

ENGLISH:
[translation]

CHINESE:
[translation]
"""

    elif source_language == "chinese":

        return """
You are a professional translation assistant.

The user provided Chinese text.

Translate the ORIGINAL Chinese text into:

1. Professional formal Venezuelan Spanish
2. Concise natural Burmese
3. Natural English

IMPORTANT RULES:

- Preserve the original meaning exactly.
- Keep the wording as close to the original as possible.
- Do NOT rewrite the message.
- Do NOT add information.
- Do NOT remove information.
- Do NOT change the intention.
- Do NOT explain anything.
- Do NOT summarize.
- Keep names, numbers, amounts and important details unchanged.
- Spanish must sound natural and professional for Venezuela.

Return ONLY this format:

SPANISH:
[translation]

MYANMAR:
[translation]

ENGLISH:
[translation]
"""

    else:

        return """
You are a professional translation assistant.

The user provided Spanish, English, or another foreign-language text.

Translate the ORIGINAL text into:

1. Professional formal Venezuelan Spanish
2. Concise natural Burmese
3. Natural Simplified Chinese

IMPORTANT RULES:

- Preserve the original meaning exactly.
- Keep the wording as close to the original as possible.
- Do NOT rewrite the message.
- Do NOT add information.
- Do NOT remove information.
- Do NOT change the intention.
- Do NOT explain anything.
- Do NOT summarize.
- Keep names, numbers, amounts and important details unchanged.
- Spanish must sound natural and professional for Venezuela.

Return ONLY this format:

SPANISH:
[translation]

MYANMAR:
[translation]

CHINESE:
[translation]
"""


# =========================================================
# GEMINI TRANSLATION
# =========================================================

def gemini_translate(text):

    if not GEMINI_API_KEY:
        raise RuntimeError(
            "GEMINI_API_KEY is missing"
        )

    source_language = detect_language(text)

    instruction = build_instruction(
        source_language
    )

    prompt = f"""
{instruction}

ORIGINAL TEXT:

{text}
"""

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
            "maxOutputTokens": 2000
        }
    }

    # =====================================================
    # RETRY 3 TIMES
    # =====================================================

    max_attempts = 3

    for attempt in range(max_attempts):

        try:

            logger.info(
                "Calling Gemini API... attempt %s/%s",
                attempt + 1,
                max_attempts,
            )

            response = requests.post(
                GEMINI_URL,
                headers=headers,
                json=data,
                timeout=60,
            )

            logger.info(
                "Gemini HTTP status: %s",
                response.status_code,
            )

            # ---------------------------------------------
            # SUCCESS
            # ---------------------------------------------

            if response.status_code == 200:

                result = response.json()

                try:
                    answer = (
                        result["candidates"][0]
                        ["content"]["parts"][0]
                        ["text"]
                        .strip()
                    )

                except (KeyError, IndexError, TypeError):

                    logger.error(
                        "Unexpected Gemini response: %s",
                        result,
                    )

                    raise RuntimeError(
                        "Gemini returned an unexpected response"
                    )

                if not answer:
                    raise RuntimeError(
                        "Gemini returned an empty response"
                    )

                logger.info(
                    "Gemini translation successful"
                )

                return answer

            # ---------------------------------------------
            # TEMPORARY SERVER ERRORS
            # ---------------------------------------------

            if response.status_code in (
                500,
                502,
                503,
                504,
            ):

                logger.warning(
                    "Temporary Gemini error %s",
                    response.status_code,
                )

                logger.warning(
                    "Gemini response: %s",
                    response.text[:1000],
                )

                if attempt < max_attempts - 1:

                    wait_time = 2 ** attempt

                    logger.info(
                        "Retrying in %s seconds...",
                        wait_time,
                    )

                    time.sleep(wait_time)

                    continue

            # ---------------------------------------------
            # RATE LIMIT
            # ---------------------------------------------

            if response.status_code == 429:

                logger.warning(
                    "Gemini rate limit / quota response: %s",
                    response.text[:1000],
                )

                if attempt < max_attempts - 1:

                    wait_time = 5 * (attempt + 1)

                    logger.info(
                        "Waiting %s seconds before retry...",
                        wait_time,
                    )

                    time.sleep(wait_time)

                    continue

            # ---------------------------------------------
            # OTHER API ERROR
            # ---------------------------------------------

            logger.error(
                "Gemini API error body: %s",
                response.text[:2000],
            )

            raise RuntimeError(
                f"Gemini API error {response.status_code}"
            )

        except requests.RequestException as error:

            logger.warning(
                "Gemini connection error: %s",
                error,
            )

            if attempt < max_attempts - 1:

                wait_time = 2 ** attempt

                logger.info(
                    "Retrying connection in %s seconds...",
                    wait_time,
                )

                time.sleep(wait_time)

                continue

            raise RuntimeError(
                "Could not connect to Gemini API"
            )

    raise RuntimeError(
        "Gemini API unavailable after 3 attempts"
    )


# =========================================================
# TELEGRAM /START
# =========================================================

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not update.message:
        return

    await update.message.reply_text(
        "မင်္ဂလာပါ။ Telegram Translation Bot မှ ကြိုဆိုပါတယ်။\n\n"
        "ဘာသာပြန်လိုသောစာကို ပို့ပေးပါ။\n\n"
        "🇲🇲 မြန်မာစာ → 🇻🇪 Spanish + 🇬🇧 English + 🇨🇳 Chinese\n"
        "🇪🇸 Spanish → 🇻🇪 Spanish + 🇲🇲 Myanmar + 🇨🇳 Chinese\n"
        "🇬🇧 English → 🇻🇪 Spanish + 🇲🇲 Myanmar + 🇨🇳 Chinese\n"
        "🇨🇳 Chinese → 🇻🇪 Spanish + 🇲🇲 Myanmar + 🇬🇧 English"
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

    # ---------------------------------------------
    # TEXT LENGTH LIMIT
    # ---------------------------------------------

    if len(text) > MAX_TEXT_LENGTH:

        await update.message.reply_text(
            "စာအရမ်းရှည်နေပါတယ်။\n"
            "5000 characters အောက်နဲ့ ပြန်ပို့ပေးပါ။"
        )

        return

    # ---------------------------------------------
    # SHOW PROCESSING MESSAGE
    # ---------------------------------------------

    processing_message = await update.message.reply_text(
        "⏳ ဘာသာပြန်နေပါတယ်..."
    )

    try:

        # Gemini request is blocking,
        # so run it in a separate thread.

        result = await asyncio.to_thread(
            gemini_translate,
            text
        )

        # -----------------------------------------
        # SEND RESULT
        # -----------------------------------------

        await processing_message.edit_text(
            result
        )

    except Exception as error:

        logger.exception(
            "Translation failed: %s",
            error,
        )

        try:

            await processing_message.edit_text(
                "❌ ဘာသာပြန်ရာမှာ ပြဿနာတစ်ခု ဖြစ်သွားပါတယ်။\n\n"
                "ခဏနေရင် ပြန်စမ်းကြည့်ပါ။"
            )

        except Exception:

            await update.message.reply_text(
                "❌ ဘာသာပြန်ရာမှာ ပြဿနာတစ်ခု ဖြစ်သွားပါတယ်။"
            )


# =========================================================
# HEALTH CHECK SERVER FOR RENDER
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


def run_health_check_server():

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
        HealthCheckHandler,
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

    # ---------------------------------------------
    # CHECK ENVIRONMENT VARIABLES
    # ---------------------------------------------

    if not TOKEN:

        raise RuntimeError(
            "TOKEN environment variable is missing"
        )

    if not GEMINI_API_KEY:

        raise RuntimeError(
            "GEMINI_API_KEY environment variable is missing"
        )

    logger.info(
        "Environment variables loaded successfully."
    )

    logger.info(
        "Using Gemini model: %s",
        MODEL
    )

    # ---------------------------------------------
    # START RENDER HEALTH SERVER
    # ---------------------------------------------

    health_thread = threading.Thread(
        target=run_health_check_server,
        daemon=True,
    )

    health_thread.start()

    # ---------------------------------------------
    # CREATE TELEGRAM BOT
    # ---------------------------------------------

    app = (
        ApplicationBuilder()
        .token(TOKEN)
        .build()
    )

    # ---------------------------------------------
    # COMMANDS
    # ---------------------------------------------

    app.add_handler(
        CommandHandler(
            "start",
            start
        )
    )

    # ---------------------------------------------
    # TEXT TRANSLATION
    # ---------------------------------------------

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            translate_text
        )
    )

    # ---------------------------------------------
    # START BOT
    # ---------------------------------------------

    logger.info(
        "Telegram Translation Bot is starting..."
    )

    app.run_polling(
        drop_pending_updates=True
    )


# =========================================================
# RUN
# =========================================================

if __name__ == "__main__":
    main()
