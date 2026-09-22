import logging
import os
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
import requests
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

TOKEN = os.environ.get("TOKEN", "8631809233:AAHkDJwWVUnObM4pewpmjITtqSOq2F0w4as")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "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")

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

def ai_translate(text, system_prompt):
    try:
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": "llama-3.3-70b-versatile",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text}
            ],
            "temperature": 0.3
        }
        res = requests.post(url, json=payload, headers=headers, timeout=10)
        if res.status_code == 200:
            return res.json()['choices'][0]['message']['content'].strip()
        else:
            logging.error(f"Groq API Error Response: {res.text}")
            return "Translation Error occurred."
    except Exception as e:
        logging.error(f"Groq API Exception: {e}")
        return "Translation Error occurred."

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "မင်္ဂလာပါ။ Venezuelan Manager Style Translate Bot မှ ကြိုဆိုပါတယ်။\n\n"
        "- မြန်မာစာ ပို့ပါက -> စပိန် (Venezuela Manager Style) နှင့် အင်္ဂလိပ် ဘာသာပြန်ပေးပါမည်။\n"
        "- အင်္ဂလိပ်/စပိန်စာ ပို့ပါက -> စပိန် (Venezuela Manager Style) နှင့် မြန်မာဘာသာ ပြန်ပေးပါမည်။"
    )

async def translate_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if not text:
        return

    try:
        is_myanmar = any('\u1000' <= char <= '\u109f' for char in text)
        
        if is_myanmar:
            spanish_prompt = (
                "You are an expert translator. Translate the following Myanmar text into polite, professional Venezuelan Spanish manager style using 'Usted'. "
                "Keep the tone formal, respectful, and authoritative yet warm. Return ONLY the translation, no extra comments."
            )
            english_prompt = (
                "Translate the following Myanmar text into clear, professional business English. Return ONLY the translation, no extra comments."
            )
            
            spanish_trans = ai_translate(text, spanish_prompt)
            english_trans = ai_translate(text, english_prompt)
            
            final_result = (
                f"🇪🇸 Spanish (Venezuela Manager Style):\n{spanish_trans}\n\n"
                f"🇬🇧 English (Professional):\n{english_trans}"
            )
        else:
            spanish_prompt = (
                "You are an expert translator. Translate the following text into polite, professional Venezuelan Spanish manager style using 'Usted'. "
                "Keep the tone formal, respectful, and authoritative yet warm. Return ONLY the translation, no extra comments."
            )
            myanmar_prompt = (
                "Translate the following text into natural, grammatically correct, fluent Myanmar (Burmese) language. Return ONLY the translation, no extra comments."
            )
            
            spanish_trans = ai_translate(text, spanish_prompt)
            myanmar_trans = ai_translate(text, myanmar_prompt)
            
            final_result = (
                f"🇪🇸 Spanish (Venezuela Manager Style):\n{spanish_trans}\n\n"
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
    
    print("Bot is starting with Groq AI Model...")
    app.run_polling()
