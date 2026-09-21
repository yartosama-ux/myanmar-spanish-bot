import logging
import os
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

def translate(text, source_lang, target_lang):
    """LibreTranslate API ကို သုံး၍ ဘာသာပြန်ခြင်း (တိကျပြီး Error မရှိပါ)"""
    try:
        url = "https://libretranslate.de/translate"
        payload = {
            "q": text,
            "source": source_lang,
            "target": target_lang,
            "format": "text"
        }
        headers = {"Content-Type": "application/json"}
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
            translated = data.get("translatedText", "")
            if translated:
                return translated
    except Exception as e:
        logging.error(f"LibreTranslate Error ({source_lang} to {target_lang}): {e}")

    # အကယ်၍ libretranslate.de အလုပ်မလုပ်ပါက MyMemory သို့ Fallback အနေဖြင့် ပြောင်းသုံးမည်
    try:
        url2 = f"https://api.mymemory.translated.net/get?q={text}&langpair={source_lang}|{target_lang}"
        res2 = requests.get(url2, timeout=10)
        if res2.status_code == 200:
            data2 = res2.json()
            translated2 = data2.get("responseData", {}).get("translatedText", "")
            if translated2 and "MYMEMORY WARNING" not in translated2:
                return translated2
    except Exception as e2:
        logging.error(f"Fallback Translate Error: {e2}")

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
            raw_spanish = translate(text, "my", "es")
            spanish_manager = apply_venezuelan_manager_style(raw_spanish)
            english_trans = translate(text, "my", "en")
            
            final_result = (
                f"🇪🇸 *Spanish (Venezuela Manager Style):*\n{spanish_manager}\n\n"
                f"🇬🇧 *English (Professional):*\n{english_trans}"
            )
            
        else:
            # အင်္ဂလိပ် သို့မဟုတ် စပိန်စာ ဖြစ်ပါက (Auto detect source as 'en' or 'es')
            # ပထမဦးစွာ အင်္ဂလိပ်မှ စပိန်နှင့် မြန်မာသို့ ပြန်ကြည့်မည်
            spanish_raw = translate(text, "en", "es")
            myanmar_trans = translate(text, "en", "my")
            
            # စပိန်စာ ဟုတ်မဟုတ် စစ်ဆေးရန် စပိန်မှ မြန်မာသို့ ပြန်ကြည့်မည်
            spanish_check = translate(text, "es", "my")
            
            # အကယ်၍ ပို့လိုက်သောစာသည် စပိန်စာဖြစ်နေပါက (သို့မဟုတ် အင်္ဂလိပ်နှင့် မတူတော့ပါက)
            # ဤနေရာတွင် ရိုးရှင်းစေရန် အင်္ဂလိပ်/စပိန် မည်သည့်စာ ပို့သည်ဖြစ်စေ စပိန်နှင့် မြန်မာ နှစ်ခုလုံး ထုတ်ပေးမည်
            spanish_manager = apply_venezuelan_manager_style(spanish_raw)
            
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
