import logging
import os
import asyncio
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from googletrans import Translator

TOKEN = os.environ.get("TOKEN", "8631809233:AAHkDJwWVUnObM4pewpmjITtqSOq2F0w4as")

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

translator = Translator()

async def free_translate(text, target_lang):
    try:
        # Async translator call
        loop = asyncio.get_event_loop()
        res = await loop.run_in_executor(None, lambda: translator.translate(text, dest=target_lang))
        return res.text
    except Exception as e:
        logging.error(f"Translation Error: {e}")
        return "Translation Error occurred."

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "မင်္ဂလာပါ။ Telegram Translate Bot သို့ ကြိုဆိုပါတယ်။\n\n"
        "- မြန်မာစာ ပို့ပါက -> စပိန် နှင့် အင်္ဂလိပ် ဘာသာပြန်ပေးပါမည်။\n"
        "- အင်္ဂလိပ်/စပိန်စာ ပို့ပါက -> စပိန် နှင့် မြန်မာဘာသာ ပြန်ပေးပါမည်။"
    )

async def translate_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if not text:
        return

    try:
        is_myanmar = any('\u1000' <= char <= '\u109f' for char in text)
        
        if is_myanmar:
            spanish_trans = await free_translate(text, 'es')
            english_trans = await free_translate(text, 'en')
            
            final_result = (
                f"🇪🇸 Spanish:\n{spanish_trans}\n\n"
                f"🇬🇧 English:\n{english_trans}"
            )
        else:
            spanish_trans = await free_translate(text, 'es')
            myanmar_trans = await free_translate(text, 'my')
            
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
        self.wfile.write(b"Bot is running alive!")

def run_health_check_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
    server.serve_forever()

if __name__ == '__main__':
    threading.Thread(target=run_health_check_server, daemon=True).start()
    
    app = ApplicationBuilder().token(TOKEN).job_queue(None).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, translate_text))
    
    print("Bot is starting without API Key...")
    app.run_polling()
