import logging
import os
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from googletrans import Translator
from langdetect import detect

TOKEN = "8631809233:AAFdyh_E9vKjs92jqGQviGCJ34wyeDNPdEo"

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

translator = Translator()

def apply_venezuelan_manager_style(spanish_text):
    """Venezuela မန်နေဂျာ/ရုံးသုံး Professional (Usted) စတိုင်သို့ ပြောင်းလဲပေးသည့် Logic"""
    if not spanish_text:
        return ""
        
    replacements = {
        " tú ": " usted ",
        "Tú ": "Usted ",
        " te ": " le ",
        " ti ": " usted ",
        "tu ": "su ",
        "Tu ": "Su ",
        "tus ": "sus ",
        "Tus ": "Sus ",
        "hola": "estimado/a, un cordial saludo",
        "Hola": "Estimado/a, un cordial saludo",
        "gracias": "muchas gracias por su atención y apoyo",
        "Gracias": "Muchas gracias por su atención y apoyo",
    }
    
    formatted_text = spanish_text
    for old, new in replacements.items():
        formatted_text = formatted_text.replace(old, new)
        
    return formatted_text

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "မင်္ဂလာပါ။ Manager-Style Translate Bot မှ ကြိုဆိုပါတယ်။\n\n"
        "- **မြန်မာစာ** ပို့ပါက -> စပိန် (Venezuela Manager Style) နှင့် အင်္ဂလိပ် ဘာသာပြန်ပေးပါမည်။\n"
        "- **စပိန်စာ** ပို့ပါက -> မြန်မာဘာသာသို့ ပြန်ပေးပါမည်။\n"
        "- **အင်္ဂလိပ်စာ** ပို့ပါက -> စပိန် (Venezuela Manager Style) နှင့် မြန်မာဘာသာ ပြန်ပေးပါမည်။",
        parse_mode='Markdown'
    )

async def translate_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if not text:
        return

    try:
        # ဘာသာစကား အလိုအလျောက် စစ်ဆေးခြင်း
        try:
            lang = detect(text)
        except:
            lang = 'en'

        # မြန်မာစာ ဖြစ်ပါက (my)
        if lang == 'my' or any('\u1000' <= char <= '\u109f' for char in text):
            raw_spanish = translator.translate(text, src='my', dest='es').text
            spanish_manager = apply_venezuelan_manager_style(raw_spanish)
            english_trans = translator.translate(text, src='my', dest='en').text
            
            final_result = (
                f"🇪🇸 *Spanish (Venezuela Manager Style):*\n{spanish_manager}\n\n"
                f"🇬🇧 *English (Professional):*\n{english_trans}"
            )
            
        # စပိန်စာ ဖြစ်ပါက (es)
        elif lang == 'es':
            myanmar_trans = translator.translate(text, src='es', dest='my').text
            final_result = f"🇲🇲 *မြန်မာဘာသာပြန်:*\n{myanmar_trans}"
            
        # အခြားဘာသာ (အဓိကအားဖြင့် အင်္ဂလိပ် - en) ဖြစ်ပါက
        else:
            raw_spanish = translator.translate(text, src='en', dest='es').text
            spanish_manager = apply_venezuelan_manager_style(raw_spanish)
            myanmar_trans = translator.translate(text, src='en', dest='my').text
            
            final_result = (
                f"🇪🇸 *Spanish (Venezuela Manager Style):*\n{spanish_manager}\n\n"
                f"🇲🇲 *မြန်မာဘာသာပြန်:*\n{myanmar_trans}"
            )
            
        await update.message.reply_text(final_result, parse_mode='Markdown')
    except Exception as e:
        logging.error(f"General Error: {e}")
        await update.message.reply_text("ဘာသာပြန်ရာတွင် အမှားအယွင်း ရှိနေပါသည်။ ကျေးဇူးပြု၍ ခဏနေမှ ထပ်ကြိုးစားပါ။")

# Render Web Service အတွက် Port Listening Server
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
    
    print("Translate Bot အလုပ်လုပ်နေပါပြီ...")
    app.run_polling()
