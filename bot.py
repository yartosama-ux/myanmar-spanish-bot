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

def translate(text, src='auto', target='en'):
    """Google Translate Web Engine သုံး၍ ၁၀၀% တိကျစွာ ဘာသာပြန်ပေးသည့် Function"""
    try:
        encoded_text = urllib.parse.quote(text)
        url = f"https://translate.googleapis.com/translate_a/single?client=gtx&sl={src}&tl={target}&dt=t&q={encoded_text}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
        }
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code == 200:
            data = res.json()
            translated_pieces = [sentence[0] for sentence in data[0] if sentence[0]]
            return "".join(translated_pieces)
    except Exception as e:
        logging.error(f"Translate Exception ({target}): {e}")
    return ""

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
        # ၁။ မြန်မာစာ Unicode Range (\u1000-\u109F) စစ်ဆေးခြင်း
        is_myanmar = any('\u1000' <= char <= '\u109f' for char in text)
        
        if is_myanmar:
            # မြန်မာစာ ပို့ပါက -> စပိန် (Manager Style) + အင်္ဂလိပ်
            raw_spanish = translate(text, src='my', target='es')
            spanish_manager = apply_venezuelan_manager_style(raw_spanish) if raw_spanish else "ဘာသာပြန်၍ မရပါ"
            
            english_trans = translate(text, src='my', target='en')
            if not english_trans:
                english_trans = "ဘာသာပြန်၍ မရပါ"
            
            final_result = (
                f"🇪🇸 *Spanish (Venezuela Manager Style):*\n{spanish_manager}\n\n"
                f"🇬🇧 *English (Professional):*\n{english_trans}"
            )
            
        else:
            # အင်္ဂလိပ် သို့မဟုတ် စပိန်
            # စပိန်စာ ဟုတ်မဟုတ် စစ်ဆေးရန် စပိန်မှ မြန်မာသို့ အရင်ပြန်ကြည့်မည်
            es_to_my = translate(text, src='es', target='my')
            en_to_my = translate(text, src='en', target='my')
            
            # မူရင်းစာသည် စပိန် သို့မဟုတ် အင်္ဂလိပ် ဖြစ်သည်ကို ခွဲခြားခြင်း
            # စပိန်မှ မြန်မာသို့ ပြန်ထားသော စာသားနှင့် အင်္ဂလိပ်မှ မြန်မာသို့ ပြန်ထားသော စာသား ကွဲပြားမှု ရှိမရှိ စစ်ပါမည်
            raw_spanish = translate(text, src='en', target='es')
            
            if text.lower() == raw_spanish.lower():
                # စပိန်စာ ဖြစ်ပါက -> မြန်မာဘာသာသို့ ပြန်မည်
                myanmar_trans = es_to_my if es_to_my else "ဘာသာပြန်၍ မရပါ"
                final_result = f"🇲🇲 *မြန်မာဘာသာပြန်:*\n{myanmar_trans}"
            else:
                # အင်္ဂလိပ်စာ ဖြစ်ပါက -> စပိန် (Manager Style) + မြန်မာဘာသာ
                spanish_manager = apply_venezuelan_manager_style(raw_spanish) if raw_spanish else "ဘာသာပြန်၍ မရပါ"
                myanmar_trans = en_to_my if en_to_my else "ဘာသာပြန်၍ မရပါ"
                
                final_result = (
                    f"🇪🇸 *Spanish (Venezuela Manager Style):*\n{spanish_manager}\n\n"
                    f"🇲🇲 *မြန်မာဘာသာပြန်:*\n{myanmar_trans}"
                )
            
        await update.message.reply_text(final_result, parse_mode='Markdown')
    except Exception as e:
        logging.error(f"General Error: {e}")
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
    
    print("Translate Bot အလုပ်လုပ်နေပါပြီ...")
    app.run_polling()
