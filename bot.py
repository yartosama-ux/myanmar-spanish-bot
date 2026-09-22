import os
import time
import random
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

# အမြန်ဆုံးနှင့် အမှန်ကန်ဆုံး ဘာသာပြန်ပေးသည့် Stable Model
MODEL = "gemini-1.5-flash"

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
# REUSABLE HTTP SESSION
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
        "hay",
        "muy",
        "más",
        "mas",
        "necesito",
        "quiero",
        "puede",
    }

    words = {
        word.lower().strip(".,!?¿¡:;")
        for word in text.split()
    }

    if words.intersection(spanish_words):
        return "spanish"

    # Default = English
    return "english"


# =========================================================
# PROMPT
# =========================================================

def build_prompt(text: str, language: str) -> str:

    # Spanish → Myanmar
    if language == "spanish":

        return f"""
Translate this Spanish text into Burmese.

Rules:
- Preserve the exact meaning.
- Be accurate and natural.
- Do not add information.
- Do not remove information.
- Do not explain.
- Do not summarize.
- Keep names, numbers, dates and amounts unchanged.
- Return ONLY the Burmese translation.

TEXT:
{text}
"""

    # Myanmar / English / Chinese → Spanish

    return f"""
Translate this text into professional Venezuelan Spanish.

Rules:
- Sound like a professional manager communicating with a client or colleague.
- Use natural, clear and professional Venezuelan Spanish.
- Preserve the exact meaning and intention.
- Stay close to the original.
- Do not add information.
- Do not remove information.
- Do not explain.
- Do not summarize.
- Keep names, numbers, dates and amounts unchanged.
- Return ONLY the Spanish translation.

SOURCE LANGUAGE:
{language}

TEXT:
{text}
"""


# =========================================================
# GEMINI API
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

    # Thinking Config ကို ပယ်ဖျက်ပြီး Speed မြင့်မားစေရန် Temperature ပြင်ဆင်ထားပါသည်
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
            "maxOutputTokens": 1000,
            "temperature": 0.2
        }
    }

    # -----------------------------------------------------
    # RETRY SETTINGS
    # -----------------------------------------------------

    max_attempts = 4

    retry_statuses = {
        408,
        429,
        500,
        502,
        503,
        504,
    }

    for attempt in range(1, max_attempts + 1):

        request_start = time.perf_counter()

        try:

            logger.info(
                "Gemini request | attempt=%s/%s | language=%s | chars=%s",
                attempt,
                max_attempts,
                language,
                len(text),
            )

            response = session.post(
                GEMINI_URL,
                headers=headers,
                json=data,
                timeout=(5, 30),
            )

            elapsed = round(
                time.perf_counter() - request_start,
                2,
            )

            status = response.status_code

            logger.info(
                "Gemini response | status=%s | time=%ss | attempt=%s",
                status,
                elapsed,
                attempt,
            )

            # =================================================
            # SUCCESS
            # =================================================

            if status == 200:

                result = response.json()

                candidates = result.get("candidates", [])

                if not candidates:
                    raise RuntimeError("Gemini returned no candidates")

                content = candidates[0].get("content", {})
                parts = content.get("parts", [])

                answer_parts = []

                for part in parts:
                    part_text = part.get("text", "")
                    if part_text:
                        answer_parts.append(part_text)

                answer = "".join(answer_parts).strip()

                if not answer:
                    raise RuntimeError("Gemini returned empty response")

                logger.info(
                    "Translation successful | total_time=%ss",
                    round(time.perf_counter() - request_start, 2),
                )

                return answer

            # =================================================
            # TEMPORARY ERROR
            # =================================================

            if status in retry_statuses:

                if attempt < max_attempts:

                    base_delay = 2 ** (attempt - 1)
                    jitter = random.uniform(0.0, 0.5)
                    delay = base_delay + jitter

                    logger.warning(
                        "Gemini temporary error %s | retrying in %.2fs",
                        status,
                        delay,
                    )

                    time.sleep(delay)
                    continue

            # =================================================
            # PERMANENT / OTHER ERROR
            # =================================================

            try:
                error_data = response.json()
                logger.error("Gemini API error: %s", error_data)
            except Exception:
                logger.error("Gemini API error body: %s", response.text[:500])

            raise RuntimeError(f"Gemini API error {status}")

        # =====================================================
        # TIMEOUT
        # =====================================================

        except requests.exceptions.Timeout as error:

            elapsed = round(time.perf_counter() - request_start, 2)

            logger.warning(
                "Gemini timeout | time=%ss | attempt=%s | %s",
                elapsed,
                attempt,
                error,
            )

            if attempt < max_attempts:

                base_delay = 2 ** (attempt - 1)
                jitter = random.uniform(0.0, 0.5)
                delay = base_delay + jitter

                logger.info("Retrying after timeout in %.2fs", delay)

                time.sleep(delay)
                continue

            raise RuntimeError("Gemini response timeout")

        # =====================================================
        # CONNECTION ERROR
        # =====================================================

        except requests.exceptions.ConnectionError as error:

            logger.warning(
                "Gemini connection error | attempt=%s | %s",
                attempt,
                error,
            )

            if attempt < max_attempts:

                base_delay = 2 ** (attempt - 1)
                jitter = random.uniform(0.0, 0.5)
                delay = base_delay + jitter

                time.sleep(delay)
                continue

            raise RuntimeError("Gemini connection failed")

        # =====================================================
        # OTHER REQUEST ERROR
        # =====================================================

        except requests.exceptions.RequestException as error:

            logger.exception("Gemini request error: %s", error)

            if attempt < max_attempts:
                time.sleep(1)
                continue

            raise RuntimeError("Gemini request failed")

    raise RuntimeError("Gemini unavailable after retries")


# =========================================================
# START COMMAND
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
        "Professional Venezuelan Spanish ဖြင့် "
        "ပြန်ပေးပါမယ်။\n\n"

        "Spanish ပို့ပါက "
        "အဓိပ္ပာယ်တိကျသော မြန်မာဘာသာဖြင့် "
        "ပြန်ပေးပါမယ်။"
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

    # -----------------------------------------------------
    # LENGTH CHECK
    # -----------------------------------------------------

    if len(text) > MAX_TEXT_LENGTH:

        await update.message.reply_text(
            "❌ စာအရမ်းရှည်နေပါတယ်။\n\n"
            "5000 characters အောက်နဲ့ "
            "ခွဲပြီး ပို့ပေးပါ။"
        )

        return

    # -----------------------------------------------------
    # START TIMER
    # -----------------------------------------------------

    total_start = time.perf_counter()

    # -----------------------------------------------------
    # PROCESSING MESSAGE
    # -----------------------------------------------------

    processing = await update.message.reply_text("⚡ ဘာသာပြန်နေပါတယ်...")

    try:

        # -------------------------------------------------
        # GEMINI
        # -------------------------------------------------

        result = await asyncio.to_thread(
            gemini_translate,
            text,
        )

        # -------------------------------------------------
        # TELEGRAM RESPONSE
        # -------------------------------------------------

        await processing.edit_text(result)

        total_time = round(time.perf_counter() - total_start, 2)

        logger.info(
            "Telegram translation complete | total=%ss | chars=%s",
            total_time,
            len(text),
        )

    except Exception as error:

        total_time = round(time.perf_counter() - total_start, 2)

        logger.exception(
            "Translation failed | total=%ss | error=%s",
            total_time,
            error,
        )

        try:

            await processing.edit_text(
                "❌ ဘာသာပြန်ရာမှာ "
                "ယာယီပြဿနာဖြစ်သွားပါတယ်။\n\n"
                "ခဏနေရင် ပြန်စမ်းကြည့်ပါ။"
            )

        except Exception:

            await update.message.reply_text(
                "❌ ဘာသာပြန်ရာမှာ "
                "ယာယီပြဿနာဖြစ်သွားပါတယ်။"
            )


# =========================================================
# RENDER HEALTH CHECK
# =========================================================

class HealthCheckHandler(BaseHTTPRequestHandler):

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

    def log_message(self, format, *args):
        return


def run_health_server():

    port = int(os.getenv("PORT", "10000"))

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

    if not TOKEN:
        raise RuntimeError("TOKEN environment variable is missing")

    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY environment variable is missing")

    logger.info("Environment variables loaded")

    logger.info(
        "Gemini model: %s",
        MODEL,
    )

    # -----------------------------------------------------
    # RENDER HEALTH SERVER
    # -----------------------------------------------------

    health_thread = threading.Thread(
        target=run_health_server,
        daemon=True,
    )

    health_thread.start()

    # -----------------------------------------------------
    # TELEGRAM APP
    # -----------------------------------------------------

    app = (
        ApplicationBuilder()
        .token(TOKEN)
        .concurrent_updates(8)
        .build()
    )

    # /start
    app.add_handler(
        CommandHandler(
            "start",
            start,
        )
    )

    # Translation
    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            translate_text,
        )
    )

    logger.info("Telegram Translation Bot started")

    # -----------------------------------------------------
    # START POLLING
    # -----------------------------------------------------

    app.run_polling(drop_pending_updates=True)


# =========================================================
# RUN
# =========================================================

if __name__ == "__main__":
    main()
