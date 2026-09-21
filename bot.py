import logging
import os
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from openai import OpenAI

TOKEN = "8631809233:AAFdyh_E9vKjs92jqGQviGCJ34wyeDNPdEo"
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY") # Render Environment Variable မှ ယူပါမည်

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

client = OpenAI(api_key=OPENAI_API_KEY)

def ai_translate(text, target_instruction):
    """OpenAI GPT ကို အသုံးပြု၍ တိကျစွာ ဘာသာပြန်ခြင်း"""
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",  # မြန်ဆန်ပြီး တိကျသော Model
            messages=[
                {"role": "system", "content": target_instruction},
                {"role": "user", "content": text}
            ]
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logging.error(f"OpenAI API Error: {e}")
    return text

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "မင်္ဂလာပါ။ Manager-Style Translate Bot (OpenAI Version) မှ ကြိုဆိုပါတယ်။\n\n"
        "- **မြန်မာစာ** ပို့ပါက -> စပိန် (Venezuela Manager Style) နှင့် အင်္ဂလိပ် ဘာသာပြန်ပေးပါမည်။\n"
        "- **အင်္ဂလိပ်/စပိန်စာ** ပို့ပါက -> စပိန် (Venezuela Manager Style) နှင့် မြန်မာဘာသာ ပြန်ပေးပါမည်။",
        parse_mode='Markdown'
    )

async def translate_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if not text:
        return

    try:
        # မြန်မာစာ Unicode Range (\u1000-\u109F) ပါဝင်မှု စစ်ဆေးခြင်း
        is_myanmar = any('\u1000' <= char <= '\u109f' for char in text)
        
        if is_myanmar:
            # မြန်မာစာ ပို့ပါက -> စပိန် (Manager Style) + အင်္ဂလိပ်
            spanish_manager = ai_translate(text, "Translate this text into polite professional Venezuelan Spanish manager style using 'Usted'. Return ONLY the translated text.")
            english_trans = ai_translate(text, "Translate this text into professional English. Return ONLY the translated text.")
            
            final_result = (
                f"🇪🇸 *Spanish (Venezuela Manager Style):*\n{spanish_manager}\n\n"
                f"🇬🇧 *English (Professional):*\n{english_trans}"
            )
            
        else:
            # အင်္ဂလိပ် သို့မဟုတ် အခြားဘာသာ ဖြစ်ပါက -> စပိန် (Manager Style) + မြန်မာဘာသာ
            spanish_manager = ai_translate(text, "Translate this text into polite professional Venezuelan Spanish manager style using 'Usted'. Return ONLY the translated text.")
            myanmar_trans = ai_translate(text, "Translate this text into natural, clear Myanmar (Burmese) language. Return ONLY the translated text.")
            
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
