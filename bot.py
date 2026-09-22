import logging
import os
import requests
import asyncio
import threading

from http.server import HTTPServer, BaseHTTPRequestHandler

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)


# =========================================================
# CONFIG
# =========================================================

TOKEN = os.getenv("TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Gemini model
MODEL = "gemini-3.5-flash-lite"

# Gemini API endpoint
GEMINI_URL = (
    f"https://generativelanguage.googleapis.com/v1beta/"
    f"models/{MODEL}:generateContent"
)

MAX_TEXT_LENGTH = 5000


# =========================================================
# LOGGING
# =========================================================

logging.basicConfig(
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
    level=logging.INFO
)

logger = logging.getLogger("translation_bot")


# =========================================================
# GEMINI API
# =========================================================

def gemini_translate(text, source_type):

    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY is missing")

    headers = {
        "x-goog-api-key": GEMINI_API_KEY,
        "Content-Type": "application/json"
    }

    # Burmese input
    if source_type == "myanmar":

        instruction = """
You are a professional translation assistant.

Translate the Burmese text into:

1. Professional formal Venezuelan Spanish
2. Natural professional English

IMPORTANT:
- Preserve the original meaning exactly.
- Keep the wording as close to the original as possible.
- Do not add information.
- Do not remove information.
- Do not explain the translation.
- Return only the translations.

Use exactly this format:

SPANISH:
[Spanish translation]

ENGLISH:
[English translation]
"""

    # Spanish or English input
    else:

        instruction = """
You are a professional translation assistant.

Translate the user's text into:

1. Professional formal Venezuelan Spanish
2. Concise natural Burmese

IMPORTANT:
- Preserve the original meaning exactly.
- Keep the wording as close to the original as possible.
- Do not add information.
- Do not remove information.
- Do not explain the translation.
- Return only the translations.

Use exactly this format:

SPANISH:
[Spanish translation]

MYANMAR:
[Burmese translation]
"""

    prompt = f"""
{instruction}

TEXT:
{text}
"""

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
            "temperature": 0.2,
            "maxOutputTokens": 2000
        }
    }

    logger.info("Calling Gemini API...")

    try:

        response = requests.post(
            GEMINI_URL,
            headers=headers,
            json=data,
            timeout=60
        )

        logger.info(
            "Gemini response status: %s",
            response.status_code
        )

        # API error
        if response.status_code != 200:

            logger.error(
                "Gemini response body: %s",
                response.text
            )

            raise RuntimeError(
                f"Gemini API error {response.status_code}"
            )

        result = response.json()

        # Get generated text
        answer = (
            result["candidates"][0]
            ["content"]["parts"][0]
            ["text"]
            .strip()
        )

        logger.info("Gemini translation successful")

        return answer

    except requests.RequestException as e:

        logger.exception(
            "Gemini connection failed: %s",
            e
        )

        raise RuntimeError(
            "Could not connect to Gemini API"
        )


# =========================================================
# LANGUAGE DETECTION
# =========================================================

def is_myanmar(text):

    return any(
        "\u1000" <= char <= "\u109f"
        for char in text
    )


# =========================================================
# START COMMAND
# =========================================================

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    await update.message.reply_text(
        "မင်္ဂလာပါ။ Telegram Translate Bot မှ ကြိုဆိုပါတယ်။\n\n"
        "မြန်မာစာ ပို့ပါက → Spanish + English ဘာသာပြန်ပေးပါမည်။\n"
        "Spanish/English ပို့ပါက → Spanish + မြန်မာဘာသာ ပြန်ပေးပါမည်။"
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

    # Prevent very large messages
    if len(text) > MAX_TEXT_LENGTH:

        await update.message.reply_text(
            "စာအရမ်းရှည်နေပါတယ်။ "
            "5000 characters အောက်နဲ့ ပြန်ပို့ပေးပါ။"
        )

        return

    try:

        if is_myanmar(text):

            source_type = "myanmar"

        else:

            source_type = "foreign"

        # Run API call outside Telegram event loop
        result = await asyncio.to_thread(
            gemini_translate,
            text,
            source_type
        )

        await update.message.reply_text(
            result
        )

    except Exception as e:

        logger.exception(
            "Translation failed: %s",
            e
        )

        await update.message.reply_text(
            "ဘာသာပြန်ရာမှာ ပြဿနာတစ်ခု ဖြစ်သွားပါတယ်။\n"
            "ခဏနေရင် ပြန်စမ်းကြည့်ပါ။"
        )


# =========================================================
# RENDER HEALTH CHECK
# =========================================================

class HealthCheckHandler(BaseHTTPRequestHandler):

    def do_GET(self):

        self.send_response(200)
        self.end_headers()

        self.wfile.write(
            b"Telegram Translation Bot is running."
        )

    def log_message(self, format, *args):
        return


def run_health_check_server():

    port = int(
        os.getenv("PORT", 10000)
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

if __name__ == "__main__":

    # Check Telegram token
    if not TOKEN:

        raise RuntimeError(
            "TOKEN environment variable is missing"
        )

    # Check Gemini API key
    if not GEMINI_API_KEY:

        raise RuntimeError(
            "GEMINI_API_KEY environment variable is missing"
        )

    # Start Render health server
    threading.Thread(
        target=run_health_check_server,
        daemon=True
    ).start()

    # Telegram application
    app = (
        ApplicationBuilder()
        .token(TOKEN)
        .job_queue(None)
        .build()
    )

    # /start
    app.add_handler(
        CommandHandler(
            "start",
            start
        )
    )

    # Normal text messages
    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            translate_text
        )
    )

    logger.info(
        "Telegram translation bot is starting..."
    )

    app.run_polling(
        drop_pending_updates=True
    )
