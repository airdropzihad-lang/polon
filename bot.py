import os
import logging
import asyncio
import requests
from http.server import HTTPServer, BaseHTTPRequestHandler
from threading import Thread
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# Render Port Handler (Fixes No Open Ports Error)
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is live!")

def run_health_check():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
    server.serve_forever()

# FIREBASE SETUP
FIREBASE_URL = "https://pol-55434-default-rtdb.firebaseio.com"
BOT_TOKEN = "8807267842:AAGzBnt72SUmpjuIGUv4G2l8hHoxugh_yyc"
MINI_APP_URL = "https://tg-mini-app-ecru.vercel.app"
REFER_BONUS = 4.0

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = str(user.id)
    args = context.args

    ref_by = args[0].replace('ref_', '') if args and args[0].startswith('ref_') else None

    # Fetch User via REST API
    res = requests.get(f"{FIREBASE_URL}/users/{user_id}.json")
    user_data = res.json()

    if not user_data:
        new_user = {
            'first_name': user.first_name,
            'username': user.username or '',
            'balance': 0.0,
            'referrals': 0,
            'referred_by': ref_by or ''
        }
        requests.put(f"{FIREBASE_URL}/users/{user_id}.json", json=new_user)

        if ref_by and ref_by != user_id:
            ref_res = requests.get(f"{FIREBASE_URL}/users/{ref_by}.json")
            referrer_data = ref_res.json()
            if referrer_data:
                current_bal = referrer_data.get('balance', 0.0)
                current_refs = referrer_data.get('referrals', 0)
                requests.patch(f"{FIREBASE_URL}/users/{ref_by}.json", json={
                    'balance': current_bal + REFER_BONUS,
                    'referrals': current_refs + 1
                })

    keyboard = [
        [InlineKeyboardButton("🚀 Open Mini App", web_app=WebAppInfo(url=MINI_APP_URL))]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        f"👋 Welcome {user.first_name}!\n\n"
        f"Click below to launch the Mini App, complete tasks, and earn USDT!",
        reply_markup=reply_markup
    )

async def main():
    # Background Health Server
    Thread(target=run_health_check, daemon=True).start()

    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    print("Bot is running...")
    
    await app.initialize()
    await app.start()
    await app.updater.start_polling()
    
    await asyncio.Event().wait()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
