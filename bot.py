import logging
import os
import urllib.parse
import requests
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

TOKEN = "8631809233:AAFdyh_E9vKjs92jqGQviGCJ34wyeDNPdEo"

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

def translate(text, target_lang):
    """Google Translate Public API ကို သုံး၍ ဘာသာပြန်ခြင်း (Error မတက်ပါ)"""
    try:
        encoded_text = urllib.parse.quote(text)
        url = f"https://translate.googleapis.com/translate_a/single?client=gtx&sl=auto&tl={target_lang}&dt=t&q={encoded_text}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            result = response.json()
            translated_text = "".join([item[0] for item in result[0] if item[0]])
            return translated_text if translated_text else text
    except Exception as e:
        logging.error(f"Translation Error ({target_lang}): {e}")
    return text

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
        # ၁။ မြန်မာစာ Unicode Range (\u1000-\u109F) ပါဝင်မှု စစ်ဆေးခြင်း
        is_myanmar = any('\u1000' <= char <= '\u109f' for char in text)
        
        if is_myanmar:
            # မြန်မာစာ ပို့ပါက -> စပိန် (Manager Style) + အင်္ဂလိပ်
            raw_spanish = translate(text, 'es')
            spanish_manager = apply_venezuelan_manager_style(raw_spanish)
            english_trans = translate(text, 'en')
            
            final_result = (
                f"🇪🇸 *Spanish (Venezuela Manager Style):*\n{spanish_manager}\n\n"
                f"🇬🇧 *English (Professional):*\n{english_trans}"
            )
            
        else:
            # အင်္ဂလိပ် သို့မဟုတ် စပိန် ဖြစ်ပါက
            # စပိန်သို့ ဘာသာပြန်ကြည့်မည်
            translated_es = translate(text, 'es')
            
            # မူရင်းစာနှင့် စပိန်သို့ ပြန်ထားသောစာ တူနေပါက (သို့မဟုတ် စပိန်စာဖြစ်နေပါက) မြန်မာသို့ ပြန်မည်
            # အင်္ဂလိပ်စာ ဖြစ်ပါက စပိန်နှင့် မြန်မာ နှစ်ခုလုံး ထုတ်ပေးမည်
            myanmar_trans = translate(text, 'my')
            
            # စပိန်စာ ဟုတ်မဟုတ် စစ်ဆေးရန် စပိန်မှ အင်္ဂလိပ်သို့ ပြန်ကြည့်မည်
            back_to_en = translate(text, 'en')
            
            if text.lower() == translated_es.lower():
                # စပိန်စာ ပို့ထားခြင်း ဖြစ်ပါက -> မြန်မာဘာသာသို့ ပြန်မည်
                final_result = f"🇲🇲 *မြန်မာဘာသာပြန်:*\n{myanmar_trans}"
            else:
                # အင်္ဂလိပ်စာ ပို့ထားခြင်း ဖြစ်ပါက -> စပိန် (Manager Style) + မြန်မာဘာသာ
                spanish_manager = apply_venezuelan_manager_style(translated_es)
                final_result = (
                    f"🇪🇸 *Spanish (Venezuela Manager Style):*\n{spanish_manager}\n\n"
                    f"🇲🇲 *မြန်မာဘာသာပြန်:*\n{myanmar_trans}"
                )
            
        await update.message.reply_text(final_result, parse_mode='Markdown')
    except Exception as e:
        logging.error(f"General Error: {e}")
        await update.message.reply_text("ဘာသာပြန်ရာတွင် အမှားအယွင်း ရှိနေပါသည်။ ခဏနေမှ ထပ်ကြိုးစားပါ။")

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
