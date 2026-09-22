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

MAX_TEXT_LENGTH = 5000

# Preferred models.
# The bot will check which one is actually available.
PREFERRED_MODELS = [
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
]

# Gemini API
GEMINI_BASE_URL = (
    "https://generativelanguage.googleapis.com/v1beta"
)

MODELS_URL = (
    f"{GEMINI_BASE_URL}/models"
)


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
# Reuse HTTPS connections
# =========================================================

session = requests.Session()

adapter = HTTPAdapter(
    pool_connections=20,
    pool_maxsize=20,
    max_retries=0,
)

session.mount("https://", adapter)


# =========================================================
# MODEL CACHE
# =========================================================

_current_model = None

_model_lock = threading.Lock()


# =========================================================
# LANGUAGE DETECTION
# =========================================================

def detect_language(text: str) -> str:

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
    # Spanish special characters
    # -----------------------------------------------------

    spanish_chars = (
        "áéíóúüñÁÉÍÓÚÜÑ¿¡"
    )

    if any(
        char in spanish_chars
        for char in text
    ):
        return "spanish"

    # -----------------------------------------------------
    # Spanish common words
    # -----------------------------------------------------

    spanish_words = {
        "que",
        "para",
        "como",
        "por",
        "una",
        "uno",
        "unos",
        "unas",
        "los",
        "las",
        "del",
        "con",
        "sin",
        "esta",
        "está",
        "tengo",
        "tiene",
        "tienen",
        "quiero",
        "puedo",
        "puede",
        "pueden",
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
        "como",
        "dónde",
        "donde",
        "hacer",
        "hay",
        "muy",
        "más",
        "mas",
        "necesito",
        "necesitamos",
        "debe",
        "deben",
        "favor",
        "ahora",
        "mañana",
        "hoy",
        "dinero",
        "cuenta",
        "trabajo",
        "empresa",
        "cliente",
        "información",
        "informacion",
    }

    words = {
        word.lower().strip(
            ".,!?¿¡:;()[]{}\"'"
        )
        for word in text.split()
    }

    if words.intersection(spanish_words):
        return "spanish"

    # -----------------------------------------------------
    # Default
    # -----------------------------------------------------

    return "english"


# =========================================================
# PROMPT
# =========================================================

def build_prompt(
    text: str,
    language: str
) -> str:

    # =====================================================
    # SPANISH → MYANMAR
    # =====================================================

    if language == "spanish":

        return f"""
Translate the following Spanish text into Burmese.

IMPORTANT:
- Preserve the exact original meaning.
- Translate accurately and naturally.
- Do not change the intention.
- Do not add information.
- Do not remove information.
- Do not explain.
- Do not summarize.
- Keep names, numbers, dates and money amounts unchanged.
- Return ONLY the Burmese translation.

Spanish text:
{text}
"""

    # =====================================================
    # MYANMAR / ENGLISH / CHINESE → SPANISH
    # =====================================================

    return f"""
Translate the following text into professional Venezuelan Spanish.

IMPORTANT:
- Write like a professional manager communicating with a client or colleague.
- Use natural, clear and professional Venezuelan Spanish.
- Preserve the exact original meaning and intention.
- Keep the wording close to the original.
- Do not add information.
- Do not remove information.
- Do not explain.
- Do not summarize.
- Keep names, numbers, dates and money amounts unchanged.
- Return ONLY the Spanish translation.

Source language:
{language}

Text:
{text}
"""


# =========================================================
# GET AVAILABLE GEMINI MODELS
# =========================================================

def get_available_model(force_refresh=False):

    global _current_model

    with _model_lock:

        # -------------------------------------------------
        # Use cached model
        # -------------------------------------------------

        if _current_model and not force_refresh:
            return _current_model

        if not GEMINI_API_KEY:
            raise RuntimeError(
                "GEMINI_API_KEY is missing"
            )

        headers = {
            "x-goog-api-key": GEMINI_API_KEY,
        }

        start = time.perf_counter()

        try:

            response = session.get(
                MODELS_URL,
                headers=headers,
                timeout=(5, 10),
            )

            elapsed = round(
                time.perf_counter() - start,
                2,
            )

            logger.info(
                "Gemini model list | status=%s | time=%ss",
                response.status_code,
                elapsed,
            )

            if response.status_code != 200:

                try:
                    error_data = response.json()
                except Exception:
                    error_data = response.text[:1000]

                logger.error(
                    "Gemini model list error | status=%s | body=%s",
                    response.status_code,
                    error_data,
                )

                raise RuntimeError(
                    f"Gemini model list error "
                    f"{response.status_code}: "
                    f"{error_data}"
                )

            data = response.json()

            available = set()

            for model in data.get(
                "models",
                []
            ):

                name = model.get(
                    "name",
                    ""
                )

                methods = model.get(
                    "supportedGenerationMethods",
                    []
                )

                # We only need models supporting generateContent
                if (
                    "generateContent" in methods
                    and name.startswith("models/")
                ):
                    short_name = name.split(
                        "models/",
                        1
                    )[1]

                    available.add(
                        short_name
                    )

            logger.info(
                "Available translation models: %s",
                sorted(available),
            )

            # -------------------------------------------------
            # Select preferred model
            # -------------------------------------------------

            for preferred in PREFERRED_MODELS:

                if preferred in available:

                    _current_model = preferred

                    logger.info(
                        "Selected Gemini model: %s",
                        _current_model,
                    )

                    return _current_model

            # -------------------------------------------------
            # Fallback:
            # Search for any flash-lite model
            # -------------------------------------------------

            fallback_candidates = [
                model
                for model in available
                if "flash-lite" in model
            ]

            if fallback_candidates:

                # Prefer newest-looking stable model
                fallback_candidates.sort(
                    reverse=True
                )

                _current_model = (
                    fallback_candidates[0]
                )

                logger.warning(
                    "Using fallback Gemini model: %s",
                    _current_model,
                )

                return _current_model

            raise RuntimeError(
                "No compatible Gemini "
                "generateContent model is available "
                "for this API key."
            )

        except requests.exceptions.Timeout:

            raise RuntimeError(
                "Gemini model list timeout"
            )

        except requests.exceptions.RequestException as error:

            raise RuntimeError(
                f"Gemini model list connection failed: "
                f"{error}"
            )


# =========================================================
# GEMINI TRANSLATION
# =========================================================

def gemini_translate(
    text: str
) -> str:

    if not GEMINI_API_KEY:
        raise RuntimeError(
            "GEMINI_API_KEY is missing"
        )

    language = detect_language(text)

    prompt = build_prompt(
        text,
        language,
    )

    # -----------------------------------------------------
    # Get an actually available model
    # -----------------------------------------------------

    model = get_available_model()

    url = (
        f"{GEMINI_BASE_URL}/models/"
        f"{model}:generateContent"
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
            "maxOutputTokens": 1200,

            "thinkingConfig": {
                "thinkingLevel": "minimal"
            }
        }
    }

    # -----------------------------------------------------
    # Retry settings
    # -----------------------------------------------------

    max_attempts = 3

    retry_statuses = {
        408,
        429,
        500,
        502,
        503,
        504,
    }

    for attempt in range(
        1,
        max_attempts + 1
    ):

        request_start = time.perf_counter()

        try:

            logger.info(
                "Gemini request | "
                "attempt=%s/%s | "
                "model=%s | "
                "language=%s | "
                "chars=%s",
                attempt,
                max_attempts,
                model,
                language,
                len(text),
            )

            response = session.post(
                url,
                headers=headers,
                json=data,
                timeout=(5, 25),
            )

            elapsed = round(
                time.perf_counter()
                - request_start,
                2,
            )

            status = response.status_code

            logger.info(
                "Gemini response | "
                "status=%s | "
                "time=%ss | "
                "attempt=%s",
                status,
                elapsed,
                attempt,
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

                answer_parts = []

                for part in parts:

                    # Ignore thought content
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

                total = round(
                    time.perf_counter()
                    - request_start,
                    2,
                )

                logger.info(
                    "Translation successful | "
                    "model=%s | "
                    "time=%ss",
                    model,
                    total,
                )

                return answer

            # =================================================
            # 404
            # =================================================

            if status == 404:

                try:
                    error_data = response.json()
                except Exception:
                    error_data = response.text[:1500]

                logger.error(
                    "Gemini 404 | model=%s | body=%s",
                    model,
                    error_data,
                )

                # Clear cached model
                global _current_model

                with _model_lock:
                    _current_model = None

                # Try model discovery once
                if attempt == 1:

                    model = get_available_model(
                        force_refresh=True
                    )

                    url = (
                        f"{GEMINI_BASE_URL}/models/"
                        f"{model}:generateContent"
                    )

                    logger.info(
                        "Retrying with available model: %s",
                        model,
                    )

                    continue

                raise RuntimeError(
                    f"Gemini API 404: "
                    f"{error_data}"
                )

            # =================================================
            # TEMPORARY ERROR
            # =================================================

            if status in retry_statuses:

                if attempt < max_attempts:

                    # 1.0 → 2.0 seconds approximately
                    delay = (
                        2 ** (attempt - 1)
                        + random.uniform(
                            0.1,
                            0.5
                        )
                    )

                    logger.warning(
                        "Gemini temporary error %s | "
                        "retrying in %.2fs",
                        status,
                        delay,
                    )

                    time.sleep(delay)

                    continue

            # =================================================
            # OTHER ERROR
            # =================================================

            try:
                error_data = response.json()
            except Exception:
                error_data = response.text[:1500]

            logger.error(
                "Gemini API error | "
                "status=%s | "
                "model=%s | "
                "body=%s",
                status,
                model,
                error_data,
            )

            raise RuntimeError(
                f"Gemini API error {status}: "
                f"{error_data}"
            )

        # =====================================================
        # TIMEOUT
        # =====================================================

        except requests.exceptions.Timeout as error:

            elapsed = round(
                time.perf_counter()
                - request_start,
                2,
            )

            logger.warning(
                "Gemini timeout | "
                "time=%ss | "
                "attempt=%s | "
                "%s",
                elapsed,
                attempt,
                error,
            )

            if attempt < max_attempts:

                delay = (
                    2 ** (attempt - 1)
                    + random.uniform(
                        0.1,
                        0.5
                    )
                )

                time.sleep(delay)

                continue

            raise RuntimeError(
                "Gemini response timeout"
            )

        # =====================================================
        # CONNECTION ERROR
        # =====================================================

        except requests.exceptions.ConnectionError as error:

            logger.warning(
                "Gemini connection error | "
                "attempt=%s | %s",
                attempt,
                error,
            )

            if attempt < max_attempts:

                delay = (
                    2 ** (attempt - 1)
                    + random.uniform(
                        0.1,
                        0.5
                    )
                )

                time.sleep(delay)

                continue

            raise RuntimeError(
                "Gemini connection failed"
            )

        # =====================================================
        # OTHER REQUEST ERROR
        # =====================================================

        except requests.exceptions.RequestException as error:

            logger.exception(
                "Gemini request exception: %s",
                error,
            )

            if attempt < max_attempts:

                time.sleep(1)

                continue

            raise RuntimeError(
                "Gemini request failed"
            )

    raise RuntimeError(
        "Gemini unavailable after retries"
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
        "Professional Venezuelan Spanish ဖြင့် "
        "ပြန်ပေးပါမယ်။\n\n"

        "Spanish ပို့ပါက "
        "မူရင်းအဓိပ္ပာယ်ကို တိကျစွာထိန်းသိမ်းပြီး "
        "မြန်မာဘာသာဖြင့် ပြန်ပေးပါမယ်။"
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

    text = update.message.text

    if not text:
        return

    text = text.strip()

    if not text:
        return

    # -----------------------------------------------------
    # Length
    # -----------------------------------------------------

    if len(text) > MAX_TEXT_LENGTH:

        await update.message.reply_text(
            "❌ စာအရမ်းရှည်နေပါတယ်။\n\n"
            "5000 characters အောက်နဲ့ "
            "ခွဲပြီး ပို့ပေးပါ။"
        )

        return

    # -----------------------------------------------------
    # Processing message
    # -----------------------------------------------------

    processing = await update.message.reply_text(
        "⚡ ဘာသာပြန်နေပါတယ်..."
    )

    total_start = time.perf_counter()

    try:

        result = await asyncio.to_thread(
            gemini_translate,
            text,
        )

        # -------------------------------------------------
        # Send result
        # -------------------------------------------------

        await processing.edit_text(
            result
        )

        total_time = round(
            time.perf_counter()
            - total_start,
            2,
        )

        logger.info(
            "Telegram translation complete | "
            "total=%ss | chars=%s",
            total_time,
            len(text),
        )

    except Exception as error:

        total_time = round(
            time.perf_counter()
            - total_start,
            2,
        )

        logger.exception(
            "Translation failed | "
            "total=%ss | error=%s",
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

    # -----------------------------------------------------
    # Render health server
    # -----------------------------------------------------

    health_thread = threading.Thread(
        target=run_health_server,
        daemon=True,
    )

    health_thread.start()

    # -----------------------------------------------------
    # Telegram application
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

    # Text
    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            translate_text,
        )
    )

    logger.info(
        "Telegram Translation Bot started"
    )

    # -----------------------------------------------------
    # Polling
    # -----------------------------------------------------

    app.run_polling(
        drop_pending_updates=True
    )


# =========================================================
# RUN
# =========================================================

if __name__ == "__main__":
    main()
