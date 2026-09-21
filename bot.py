import logging
import urllib.request
import urllib.parse
import json
import os
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

TOKEN = "8631809233:AAFdyh_E9vKjs92jqGQviGCJ34wyeDNPdEo"

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

def direct_google_translate(text, target_lang):
    """Google Translate Web API သို့ Request ပို့၍ ဘာသာပြန်ပေးသည့် Function"""
    url = f"https://translate.googleapis.com/translate_a/single?client=gtx&sl=auto&tl={target_lang}&dt=t&q=" + urllib.parse.quote(text)
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    req = urllib.request.Request(url, headers=headers)
    
    with urllib.request.urlopen(req) as response:
        result = json.loads(response.read().decode('utf-8'))
        
    translated_text = "".join([item[0] for item in result[0] if item[0]])
    return translated_text

def apply_venezuelan_manager_style(spanish_text):
    """Venezuela မန်နေဂျာ/ရုံးသုံး Professional (Usted) စတိုင်သို့ ပြောင်းလဲပေးသည့် Logic"""
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
        "- **မြန်မာစာ** ပို့ပါက -> စပိန် (Manager Style) နှင့် အင်္ဂလိပ် ဘာသာပြန်ပေးပါမည်။\n"
        "- **စပိန်စာ** ပို့ပါက -> မြန်မာဘာသာသို့ တိကျစွာ ပြန်ပေးပါမည်။\n"
        "- **အင်္ဂလိပ်စာ** ပို့ပါက -> စပိန် (Manager Style) နှင့် မြန်မာဘာသာ ပြန်ပေးပါမည်။"
    )

async def translate_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    
    try:
        # ၁။ မြန်မာစာ Unicode Range (\u1000-\u109F) စစ်ဆေးခြင်း
        is_myanmar = any('\u1000' <= char <= '\u109f' for char in text)
        
        if is_myanmar:
            # မြန်မာစာ ပို့ပါက -> စပိန် (Manager Style) + အင်္ဂလိပ် ရုံးသုံး
            raw_spanish = direct_google_translate(text, 'es')
            spanish_manager = apply_venezuelan_manager_style(raw_spanish)
            english_trans = direct_google_translate(text, 'en')
            
            final_result = (
                f"🇪🇸 **Spanish (Venezuela Manager Style):**\n{spanish_manager}\n\n"
                f"🇬🇧 **English (Professional):**\n{english_trans}"
            )
            
        else:
            # ၂။ အင်္ဂလိပ် သို့မဟုတ် စပိန် ဟုတ်မဟုတ် စစ်ဆေးခြင်း
            translated_es = direct_google_translate(text, 'es')
            
            # မူရင်းစာနှင့် စပိန်သို့ ပြန်ထားသောစာ တူနေပါက စပိန်စာဖြစ်သည်
            if text.strip().lower() == translated_es.strip().lower():
                # စပိန်စာ ပို့ပါက -> မြန်မာဘာသာ တိကျစွာ ပြန်ပေးမည်
                myanmar_trans = direct_google_translate(text, 'my')
                final_result = f"🇲🇲 **မြန်မာဘာသာပြန်:**\n{myanmar_trans}"
            else:
                # အင်္ဂလိပ်စာ ပို့ပါက -> စပိန် (Manager Style) + မြန်မာဘာသာ
                myanmar_trans = direct_google_translate(text, 'my')
                spanish_manager = apply_venezuelan_manager_style(translated_es)
                
                final_result = (
                    f"🇪🇸 **Spanish (Venezuela Manager Style):**\n{spanish_manager}\n\n"
                    f"🇲🇲 **မြန်မာဘာသာပြန်:**\n{myanmar_trans}"
                )
            
        await update.message.reply_text(final_result)
    except Exception as e:
        logging.error(f"Translation Error: {e}")
        await update.message.reply_text("ဘာသာပြန်ရာတွင် အမှားအယွင်း ရှိနေပါသည်။")

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
    
    print("Manager-Style Translate Bot အလုပ်လုပ်နေပါပြီ...")
    app.run_polling()