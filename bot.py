import logging
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
import firebase_admin
from firebase_admin import credentials, db

# FIREBASE SETUP
FIREBASE_URL = "https://pol-55434-default-rtdb.firebaseio.com/"

if not firebase_admin._apps:
    firebase_admin.initialize_app(options={
        'databaseURL': FIREBASE_URL
    })

BOT_TOKEN = "8807267842:AAGzBnt72SUmpjuIGUv4G2l8hHoxugh_yyc"
MINI_APP_URL = "https://tg-mini-app-ecru.vercel.app"
REFER_BONUS = 4.0

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = str(user.id)
    args = context.args

    ref_by = args[0].replace('ref_', '') if args and args[0].startswith('ref_') else None

    user_ref = db.reference(f'users/{user_id}')
    user_data = user_ref.get()

    if not user_data:
        new_user = {
            'first_name': user.first_name,
            'username': user.username or '',
            'balance': 0.0,
            'referrals': 0,
            'referred_by': ref_by or ''
        }
        user_ref.set(new_user)

        if ref_by and ref_by != user_id:
            referrer_ref = db.reference(f'users/{ref_by}')
            referrer_data = referrer_ref.get()
            if referrer_data:
                current_bal = referrer_data.get('balance', 0.0)
                current_refs = referrer_data.get('referrals', 0)
                referrer_ref.update({
                    'balance': current_bal + REFER_BONUS,
                    'referrals': current_refs + 1
                })

    keyboard = [
        [InlineKeyboardButton("🚀 Open Mini App", url=MINI_APP_URL)]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        f"👋 Welcome {user.first_name}!\n\n"
        f"Click below to launch the Mini App, complete tasks, and earn USDT!",
        reply_markup=reply_markup
    )

async def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    print("Bot is running...")
    
    await app.initialize()
    await app.start()
    await app.updater.start_polling()
    
    # Keep application running
    await asyncio.Event().wait()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
