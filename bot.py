import logging
import os
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from google import genai

TOKEN = "8631809233:AAFdyh_E9vKjs92jqGQviGCJ34wyeDNPdEo"
GEMINI_API_KEY = "AQ.Ab8RN6IBDmdlAHhVzqZUWA4OCyVpfEv2LIhe4AL2uiSGHw20sQ"  # ဒီနေရာမှာ Gemini API Key ထည့်ပါ

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

client = genai.Client(api_key=GEMINI_API_KEY)

def ai_translate(text, target_instruction):
    """Gemini AI ကို သုံး၍ တိကျစွာ ဘာသာပြန်ခြင်း"""
    try:
        prompt = f"Translate the following text. {target_instruction}\nText: {text}\nProvide only the translated text as output without any preamble or quotes."
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
        )
        return response.text.strip()
    except Exception as e:
        logging.error(f"Gemini API Error: {e}")
        return text

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "မင်္ဂလာပါ။ Manager-Style Translate Bot မှ ကြိုဆိုပါတယ်။\n\n"
        "- **မြန်မာစာ** ပို့ပါက -> စပိန် (Venezuela Manager Style) နှင့် အင်္ဂလိပ် (Professional) ဘာသာပြန်ပေးပါမည်။\n"
        "- **စပိန်စာ** ပို့ပါက -> မြန်မာဘာသာသို့ ပြန်ပေးပါမည်။\n"
        "- **အင်္ဂလိပ်စာ** ပို့ပါက -> စပိန် (Venezuela Manager Style) နှင့် မြန်မာဘာသာ ပြန်ပေးပါမည်။",
        parse_mode='Markdown'
    )

async def translate_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    
    try:
        is_myanmar = any('\u1000' <= char <= '\u109f' for char in text)
        
        if is_myanmar:
            # မြန်မာစာ ပို့ပါက -> စပိန် (Manager Style) + အင်္ဂလိပ်
            spanish_trans = ai_translate(text, "Translate to polite professional Venezuelan Spanish manager style (using 'Usted').")
            english_trans = ai_translate(text, "Translate to professional English.")
            
            final_result = (
                f"🇪🇸 *Spanish (Venezuela Manager Style):*\n{spanish_trans}\n\n"
                f"🇬🇧 *English (Professional):*\n{english_trans}"
            )
            
        else:
            # အင်္ဂလိပ် သို့မဟုတ် စပိန်
            spanish_trans = ai_translate(text, "Translate to polite professional Venezuelan Spanish manager style (using 'Usted').")
            
            if text.strip().lower() == spanish_trans.strip().lower():
                # စပိန်စာဖြစ်ပါက -> မြန်မာဘာသာ
                myanmar_trans = ai_translate(text, "Translate to natural, clear Myanmar (Burmese) language.")
                final_result = f"🇲🇲 *မြန်မာဘာသာပြန်:*\n{myanmar_trans}"
            else:
                # အင်္ဂလိပ်စာဖြစ်ပါက -> စပိန် + မြန်မာဘာသာ
                myanmar_trans = ai_translate(text, "Translate to natural, clear Myanmar (Burmese) language.")
                final_result = (
                    f"🇪🇸 *Spanish (Venezuela Manager Style):*\n{spanish_trans}\n\n"
                    f"🇲🇲 *မြန်မာဘာသာပြန်:*\n{myanmar_trans}"
                )
            
        await update.message.reply_text(final_result, parse_mode='Markdown')
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
    
    print("AI Translate Bot အလုပ်လုပ်နေပါပြီ...")
    app.run_polling()