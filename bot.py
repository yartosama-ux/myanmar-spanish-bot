import logging
import os
import requests
import asyncio
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

TOKEN = os.environ.get("TOKEN", "8631809233:AAHkDJwWVUnObM4pewpmjITtqSOq2F0w4as")

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

def free_google_translate(text, target_lang):
    try:
        url = "https://translate.googleapis.com/translate_a/single"
        params = {
            "client": "gtx",
            "sl": "auto",
            "tl": target_lang,
            "dt": "t",
            "q": text
        }
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        response = requests.get(url, params=params, headers=headers, timeout=10)
        
        if response.status_code == 200:
            result = response.json()
            translated_text = "".join([item[0] for item in result[0] if item and item[0]])
            return translated_text
        else:
            return "Translation Error occurred."
    except Exception as e:
        logging.error(f"Translation Error: {e}")
        return "Translation Error occurred."

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "မင်္ဂလာပါ။ Telegram Translate Bot မှ ကြိုဆိုပါတယ်။\n\n"
        "- မြန်မာစာ ပို့ပါက -> စပိန် နှင့် အင်္ဂလိပ် ဘာသာပြန်ပေးပါမည်။\n"
        "- အင်္ဂလိပ်/စပိန်စာ ပို့ပါက -> စပိန် နှင့် မြန်မာဘာသာ ပြန်ပေးပါမည်။"
    )

async def translate_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if not text:
        return

    try:
        loop = asyncio.get_event_loop()
        is_myanmar = any('\u1000' <= char <= '\u109f' for char in text)
        
        if is_myanmar:
            spanish_trans = await loop.run_in_executor(None, free_google_translate, text, 'es')
            english_trans = await loop.run_in_executor(None, free_google_translate, text, 'en')
            
            final_result = (
                f"🇪🇸 Spanish:\n{spanish_trans}\n\n"
                f"🇬🇧 English:\n{english_trans}"
            )
        else:
            spanish_trans = await loop.run_in_executor(None, free_google_translate, text, 'es')
            myanmar_trans = await loop.run_in_executor(None, free_google_translate, text, 'my')
            
            final_result = (
                f"🇪🇸 Spanish:\n{spanish_trans}\n\n"
                f"🇲🇲 မြန်မာဘာသာပြန်:\n{myanmar_trans}"
            )
            
        await update.message.reply_text(final_result)
    except Exception as e:
        logging.error(f"General Error: {e}")
        await update.message.reply_text("ဘာသာပြန်ရာတွင် အမှားအယွင်း ရှိနေပါသည်။")

class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

def run_health_check_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
    server.serve_forever()

if __name__ == '__main__':
    # Start Health Check HTTP Server for Render
    threading.Thread(target=run_health_check_server, daemon=True).start()
    
    app = ApplicationBuilder().token(TOKEN).job_queue(None).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, translate_text))
    
    print("Bot is starting...")
    app.run_polling(drop_pending_updates=True)
