import os
import logging
import asyncio
import requests
from http.server import HTTPServer, BaseHTTPRequestHandler
from threading import Thread
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, CallbackQueryHandler, MessageHandler, filters

# Render Port Handler
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is live!")

def run_health_check():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
    server.serve_forever()

# CONFIGURATION
FIREBASE_URL = "https://pol-55434-default-rtdb.firebaseio.com"
BOT_TOKEN = "8807267842:AAGzBnt72SUmpjuIGUv4G2l8hHoxugh_yyc"
BOT_USERNAME = "PolzyxBot"  # সঠিক বোট ইউজারনেম সেট করা হয়েছে
MINI_APP_URL = "https://tg-mini-app-ecru.vercel.app"
REFER_BONUS = 4.0

# বাধ্যতামূলক চ্যানেলের লিস্ট (লিংক এবং চ্যানেল আইডি/ইউজারনেম)
REQUIRED_CHANNELS = [
    {"name": "Main Channel", "url": "https://t.me/Crypto_Income_BD", "id": "@Crypto_Income_BD"}
]

# অ্যাডমিনের টেলিগ্রাম আইডি (এখানে আপনার আইডি বসান)
ADMIN_ID = "7888333547" 

# চ্যানেল জয়েন চেক ফাংশন
async def is_subscribed(bot, user_id):
    for ch in REQUIRED_CHANNELS:
        try:
            member = await bot.get_chat_member(chat_id=ch["id"], user_id=user_id)
            if member.status in ['left', 'kicked']:
                return False
        except Exception:
            return False
    return True

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = str(user.id)
    args = context.args

    # ১. চ্যানেল জয়েন করেছে কিনা ভেরিফাই করা
    if not await is_subscribed(context.bot, user.id):
        buttons = []
        for ch in REQUIRED_CHANNELS:
            buttons.append([InlineKeyboardButton(f"📢 Join {ch['name']}", url=ch["url"])])
        buttons.append([InlineKeyboardButton("✅ Verify / Check", callback_data="check_join")])
        
        await update.message.reply_text(
            "⚠️ **Must Join Our Channels First!**\n\n"
            "You need to join all required channels below to use this bot and earn rewards.",
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode="Markdown"
        )
        return

    # ২. ইউজার ডাটা চেক এবং রেফারাল কাউন্ট
    ref_by = args[0].replace('ref_', '') if args and args[0].startswith('ref_') else None

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

        # রেফারকারী থাকলে তার ব্যালেন্স ও রেফারাল কাউন্ট আপডেট
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
                try:
                    await context.bot.send_message(
                        chat_id=int(ref_by),
                        text=f"🎉 **New Referral!**\nUser {user.first_name} joined using your link. You earned +${REFER_BONUS} USDT!"
                    )
                except Exception:
                    pass

    # ফিক্সড রেফারাল লিংক জেনারেট
    ref_link = f"https://t.me/{BOT_USERNAME}?start=ref_{user_id}"

    keyboard = [
        [InlineKeyboardButton("🚀 Open Mini App", web_app=WebAppInfo(url=MINI_APP_URL))],
        [InlineKeyboardButton("💰 Balance", callback_data="my_balance"), InlineKeyboardButton("💸 Withdraw", callback_data="withdraw_start")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        f"👋 Welcome **{user.first_name}**!\n\n"
        f"🔗 **Your Referral Link:**\n`{ref_link}`\n\n"
        f"Click below to launch the Mini App, complete tasks, and earn USDT!",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

# ভেরিফাই বাটনের কলব্যাক
async def verify_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if await is_subscribed(context.bot, query.from_user.id):
        await query.message.edit_text("✅ Verification successful! Please type /start to continue.")
    else:
        await query.answer("❌ You haven't joined all channels yet!", show_alert=True)

# ব্যালেন্স বাটন কলব্যাক
async def balance_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = str(query.from_user.id)

    res = requests.get(f"{FIREBASE_URL}/users/{user_id}.json")
    user_data = res.json() or {}
    balance = user_data.get('balance', 0.0)
    referrals = user_data.get('referrals', 0)

    await query.message.reply_text(
        f"💵 **Your Account Info:**\n\n"
        f"👤 User: {query.from_user.first_name}\n"
        f"💰 Balance: `${balance:.2f} USDT`\n"
        f"👥 Total Referrals: `{referrals}`",
        parse_mode="Markdown"
    )

# উইথড্র ফ্লো
async def withdraw_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = str(query.from_user.id)

    res = requests.get(f"{FIREBASE_URL}/users/{user_id}.json")
    user_data = res.json() or {}
    balance = user_data.get('balance', 0.0)

    if balance <= 0:
        await query.message.reply_text("❌ Your balance is 0 USDT. Earn rewards first to withdraw!")
        return

    context.user_data['awaiting_address'] = True
    context.user_data['user_balance'] = balance

    await query.message.reply_text(
        f"💸 **Withdrawal Request**\n\n"
        f"Available Balance: `${balance:.2f} USDT`\n\n"
        f"Please send your **USDT (TRC20 / BEP20) Wallet Address** now in the chat:",
        parse_mode="Markdown"
    )

# এড্রেস রিসিভ ও এডমিনকে নোটিফিকেশন পাঠানো
async def handle_address_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('awaiting_address'):
        wallet_address = update.message.text.strip()
        user = update.effective_user
        balance = context.user_data.get('user_balance', 0.0)

        context.user_data['awaiting_address'] = False

        # অ্যাডমিনকে মেসেজ পাঠানো
        admin_msg = (
            f"📥 **NEW WITHDRAWAL REQUEST**\n\n"
            f"👤 **User:** {user.first_name} (@{user.username or 'N/A'})\n"
            f"📱 **Chat ID:** `{user.id}`\n"
            f"💰 **Amount:** `${balance:.2f} USDT`\n"
            f"🏦 **Wallet Address:**\n`{wallet_address}`"
        )
        try:
            await context.bot.send_message(chat_id=int(ADMIN_ID), text=admin_msg, parse_mode="Markdown")
        except Exception as e:
            print(f"Error sending to admin: {e}")

        # ব্যবহারকারীকে কনফার্মেশন
        await update.message.reply_text(
            f"✅ **Withdrawal Request Submitted!**\n\n"
            f"Amount: `${balance:.2f} USDT`\n"
            f"Address: `{wallet_address}`\n\n"
            f"The admin will review and process your payout soon.",
            parse_mode="Markdown"
        )

async def main():
    Thread(target=run_health_check, daemon=True).start()

    app = ApplicationBuilder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(verify_callback, pattern="^check_join$"))
    app.add_handler(CallbackQueryHandler(balance_callback, pattern="^my_balance$"))
    app.add_handler(CallbackQueryHandler(withdraw_start, pattern="^withdraw_start$"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_address_input))

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
