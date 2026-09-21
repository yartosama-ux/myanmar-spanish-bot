import logging
import os
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
import google.generativeai as genai

TOKEN = os.environ.get("TOKEN", "8631809233:AAFdyh_E9vKjs92jqGQviGCJ34wyeDNPdEo")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "AQ.Ab8RN6Jtk6MHRTfp-yfD5UDoTC93dwhAe2kitfj--fX7v2Xcsg")

# Gemini Configure လုပ်ခြင်း
genai.configure(api_key=GEMINI_API_KEY)

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

def gemini_translate(text, system_prompt):
    try:
        # Gemini 1.5 Flash Model ကို အသုံးပြုပါသည် (မြန်ဆန်ပြီး တည်ငြိမ်သည်)
        model = genai.GenerativeModel(
            model_name="gemini-1.5-flash",
            system_instruction=system_prompt
        )
        response = model.generate_content(text)
        return response.text.strip()
    except Exception as e:
        logging.error(f"Gemini API Error: {e}")
        return "Translation Error occurred."

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "မင်္ဂလာပါ။ Manager-Style Translate Bot (Powered by Gemini) သို့ ကြိုဆိုပါတယ်။\n\n"
        "- **မြန်မာစာ** ပို့ပါက -> စပိန် (Venezuela Manager Style) နှင့် အင်္ဂလိပ် ဘာသာပြန်ပေးပါမည်။\n"
        "- **အင်္ဂလိပ်/စပိန်စာ** ပို့ပါက -> စပိန် (Venezuela Manager Style) နှင့် မြန်မာဘာသာ ပြန်ပေးပါမည်။"
    )

async def translate_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if not text:
        return

    try:
        is_myanmar = any('\u1000' <= char <= '\u109f' for char in text)
        
        if is_myanmar:
            spanish_manager = gemini_translate(text, "Translate this text into polite, professional Venezuelan Spanish manager style using 'Usted'. Return ONLY the translated text.")
            english_trans = gemini_translate(text, "Translate this text into professional English. Return ONLY the translated text.")
            
            final_result = (
                f"🇪🇸 Spanish (Venezuela Manager Style):\n{spanish_manager}\n\n"
                f"🇬🇧 English (Professional):\n{english_trans}"
            )
        else:
            spanish_manager = gemini_translate(text, "Translate this text into polite, professional Venezuelan Spanish manager style using 'Usted'. Return ONLY the translated text.")
            myanmar_trans = gemini_translate(text, "Translate this text into natural, clear Myanmar (Burmese) language. Return ONLY the translated text.")
            
            final_result = (
                f"🇪🇸 Spanish (Venezuela Manager Style):\n{spanish_manager}\n\n"
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
    
    print("Gemini Translate Bot အလုပ်လုပ်နေပါပြီ...")
    app.run_polling()
