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


# =========================
# CONFIG
# =========================

TOKEN = os.getenv("TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

MODEL = "gemini-3.5-flash"

MAX_TEXT_LENGTH = 5000

GEMINI_URL = (
    f"https://generativelanguage.googleapis.com/v1beta/"
    f"models/{MODEL}:generateContent"
)


# =========================
# LOGGING
# =========================

logging.basicConfig(
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
    level=logging.INFO
)

logger = logging.getLogger("translation_bot")


# =========================
# GEMINI TRANSLATION
# =========================

def gemini_translate(text, instruction):

    headers = {
        "x-goog-api-key": GEMINI_API_KEY,
        "Content-Type": "application/json"
    }

    prompt = f"""
{instruction}

Text to translate:

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
        ]
    }

    response = requests.post(
        GEMINI_URL,
        headers=headers,
        json=data,
        timeout=60
    )

    if response.status_code != 200:
        logger.error(
            "Gemini API error %s: %s",
            response.status_code,
            response.text
        )

        raise RuntimeError(
            f"Gemini API error: {response.status_code}"
        )

    result = response.json()

    try:
        return result["candidates"][0]["content"]["parts"][0]["text"].strip()

    except (KeyError, IndexError):
        logger.error("Unexpected Gemini response: %s", result)
        raise RuntimeError("Gemini returned an unexpected response.")


# =========================
# LANGUAGE DETECTION
# =========================

def is_myanmar(text):

    return any(
        "\u1000" <= char <= "\u109f"
        for char in text
    )


# =========================
# START COMMAND
# =========================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await update.message.reply_text(
        "မင်္ဂလာပါ။ Telegram Translate Bot မှ ကြိုဆိုပါတယ်။\n\n"
        "မြန်မာစာ ပို့ပါက → Spanish + English ဘာသာပြန်ပေးပါမည်။\n"
        "Spanish/English ပို့ပါက → Spanish + မြန်မာဘာသာ ပြန်ပေးပါမည်။"
    )


# =========================
# TRANSLATION
# =========================

async def translate_text(update: Update, context: ContextTypes.DEFAULT_TYPE):

    text = update.message.text.strip()

    if not text:
        return

    if len(text) > MAX_TEXT_LENGTH:

        await update.message.reply_text(
            "စာအရမ်းရှည်နေပါတယ်။ 5000 characters အောက်နဲ့ ပြန်ပို့ပေးပါ။"
        )

        return

    try:

        if is_myanmar(text):

            spanish_instruction = """
Translate the Burmese text into professional,
formal Venezuelan Spanish.

Preserve the original meaning and wording as closely
as possible.

Do not rewrite, add information, or change the meaning.
Return only the Spanish translation.
"""

            english_instruction = """
Translate the Burmese text into natural professional English.

Preserve the original meaning as closely as possible.
Do not add information or change the meaning.

Return only the English translation.
"""

            spanish = await asyncio.to_thread(
                gemini_translate,
                text,
                spanish_instruction
            )

            english = await asyncio.to_thread(
                gemini_translate,
                text,
                english_instruction
            )

            result = (
                "🇻🇪 Spanish:\n"
                f"{spanish}\n\n"
                "🇬🇧 English:\n"
                f"{english}"
            )

        else:

            spanish_instruction = """
Translate the text into professional,
formal Venezuelan Spanish.

Preserve the original meaning and wording as closely
as possible.

Do not rewrite, add information, or change the meaning.

Return only the Spanish translation.
"""

            myanmar_instruction = """
Translate the text into concise, natural Burmese.

Keep the translation to the point.
Preserve the original meaning.
Do not add unnecessary explanations.

Return only the Burmese translation.
"""

            spanish = await asyncio.to_thread(
                gemini_translate,
                text,
                spanish_instruction
            )

            myanmar = await asyncio.to_thread(
                gemini_translate,
                text,
                myanmar_instruction
            )

            result = (
                "🇻🇪 Spanish:\n"
                f"{spanish}\n\n"
                "🇲🇲 မြန်မာ:\n"
                f"{myanmar}"
            )

        await update.message.reply_text(result)

    except Exception as e:

        logger.exception("Translation failed")

        await update.message.reply_text(
            "ဘာသာပြန်ရာမှာ ပြဿနာတစ်ခု ဖြစ်သွားပါတယ်။ "
            "ခဏနေရင် ပြန်စမ်းကြည့်ပါ။"
        )


# =========================
# HEALTH CHECK
# =========================

class HealthCheckHandler(BaseHTTPRequestHandler):

    def do_GET(self):

        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

    def log_message(self, format, *args):
        return


def run_health_check_server():

    port = int(os.getenv("PORT", 10000))

    server = HTTPServer(
        ("0.0.0.0", port),
        HealthCheckHandler
    )

    server.serve_forever()


# =========================
# MAIN
# =========================

if __name__ == "__main__":

    if not TOKEN:
        raise RuntimeError("TOKEN is missing")

    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY is missing")

    threading.Thread(
        target=run_health_check_server,
        daemon=True
    ).start()

    app = (
        ApplicationBuilder()
        .token(TOKEN)
        .job_queue(None)
        .build()
    )

    app.add_handler(
        CommandHandler("start", start)
    )

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            translate_text
        )
    )

    print("Telegram translation bot is starting...")

    app.run_polling(
        drop_pending_updates=True
    )
