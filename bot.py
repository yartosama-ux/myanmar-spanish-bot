import logging
import os
import requests
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

TOKEN = "8631809233:AAFdyh_E9vKjs92jqGQviGCJ34wyeDNPdEo"
OPENAI_API_KEY = "DoLwwyD1RU6kg_0ohhEERiwopRrdUA"  # Render ထဲက သင့်ရဲ့ Key အစစ်

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

def openai_translate(text, system_prompt):
    """OpenAI API ကို requests ဖြင့် တိုက်ရိုက်နှင့် အမှားအယွင်းမရှိ ခေါ်ယူခြင်း"""
    url = "https://api.openai.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "gpt-4o-mini",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": text}
        ],
        "temperature": 0.3
    }
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=15)
        if response.status_code == 200:
            data = response.json()
            return data["choices"][0]["message"]["content"].strip()
        else:
            logging.error(f"OpenAI API Error Status {response.status_code}: {response.text}")
    except Exception as e:
        logging.error(f"OpenAI Exception: {e}")
    return text  # Error ဖြစ်မှသာ မူရင်းစာသားကို ပြန်ပေးမည်

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "မင်္ဂလာပါ။ Manager-Style Translate Bot (OpenAI Fixed Version) မှ ကြိုဆိုပါတယ်။\n\n"
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
        is_myanmar = any('\u1000' <= char <= \u109f' for char in text)
        
        if is_myanmar:
            spanish_manager = openai_translate(text, "Translate this text into polite, professional Venezuelan Spanish manager style using 'Usted'. Return ONLY the translated text.")
            english_trans = openai_translate(text, "Translate this text into professional English. Return ONLY the translated text.")
            
            final_result = (
                f"🇪🇸 *Spanish (Venezuela Manager Style):*\n{spanish_manager}\n\n"
                f"🇬🇧 *English (Professional):*\n{english_trans}"
            )
        else:
            spanish_manager = openai_translate(text, "Translate this text into polite, professional Venezuelan Spanish manager style using 'Usted'. Return ONLY the translated text.")
            myanmar_trans = openai_translate(text, "Translate this text into natural, clear Myanmar (Burmese) language. Return ONLY the translated text.")
            
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
