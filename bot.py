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
BOT_TOKEN = "8860607501:AAFGnbOb9RA3iVwxPWpGACgnp9J3E1O03LQ"
BOT_USERNAME = "GramWalletPay_Bot"
MINI_APP_URL = "https://polmain1.vercel.app/"
REFER_BONUS = 2000.0  # Gram Wallet GD Bonus

# ছবি এবং চ্যানেল আপডেট
START_IMAGE_URL = "https://ibb.co.com/BHbcTGjc"
CHANNEL_URL = "https://t.me/EARNINGllNEWS"
PAYOUT_CHANNEL_ID = "@Smartgrowsmm_payout"  # পেমেন্ট চ্যানেল

# অ্যাডমিনের টেলিগ্রাম আইডি
ADMIN_ID = "7888333547"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = str(user.id)
    args = context.args

    # ইউজার ডাটা সেভ এবং রেফারাল কাউন্ট
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

        # রেফারকারী থাকলে ব্যালেন্স ও রেফারাল আপডেট
        if ref_by and ref_by != user_id:
            ref_res = requests.get(f"{FIREBASE_URL}/users/{ref_by}.json")
            referrer_data = ref_res.json()
            if referrer_data:
                current_bal = referrer_data.get('balance', 0.0)
                current_refs = referrer_data.get('referrals', 0)
                new_bal = current_bal + REFER_BONUS
                
                requests.patch(f"{FIREBASE_URL}/users/{ref_by}.json", json={
                    'balance': new_bal,
                    'referrals': current_refs + 1
                })
                try:
                    await context.bot.send_message(
                        chat_id=int(ref_by),
                        text=f"🎉 **New Referral!**\nUser {user.first_name} joined using your link. You earned +{REFER_BONUS:.0f} GD!\nYour Updated Balance: `{new_bal:.0f} GD`",
                        parse_mode="Markdown"
                    )
                except Exception:
                    pass

    # বাটন সেটআপ
    keyboard = [
        [InlineKeyboardButton("Play 🎮", web_app=WebAppInfo(url=MINI_APP_URL))],
        [InlineKeyboardButton("Join the Earning News ↗️", url=CHANNEL_URL)]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    start_text = (
        f"🎁 Welcome to Gram Wallet Pay, {user.first_name}!\n\n"
        "The Telegram Mini App where you can earn GRAM Tokens by completing simple tasks + earn more through referrals.\n\n"
        "👇 Tap the button below to open the app and start earning!"
    )

    try:
        await update.message.reply_photo(
            photo=START_IMAGE_URL,
            caption=start_text,
            reply_markup=reply_markup
        )
    except Exception:
        await update.message.reply_text(
            text=start_text,
            reply_markup=reply_markup
        )

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
        f"💰 Balance: `{balance:.0f} GD`\n"
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

    if balance < 10000:
        await query.message.reply_text("❌ Minimum withdrawal is 10,000 GD. Complete tasks and refer to earn more!")
        return

    context.user_data['awaiting_address'] = True
    context.user_data['user_balance'] = balance

    await query.message.reply_text(
        f"💸 **Withdrawal Request**\n\n"
        f"Available Balance: `{balance:.0f} GD`\n\n"
        f"Please send your **GRAM Wallet Address** now in the chat:",
        parse_mode="Markdown"
    )

# এড্রেস রিসিভ ও এডমিনকে ইনলাইন বাটন সহ নোটিফিকেশন পাঠানো
async def handle_address_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('awaiting_address'):
        wallet_address = update.message.text.strip()
        user = update.effective_user
        balance = context.user_data.get('user_balance', 0.0)

        context.user_data['awaiting_address'] = False

        # এডমিন বাটনের জন্য ডাটা (confirm_USERID_AMOUNT বা reject_USERID_AMOUNT)
        admin_keyboard = [
            [
                InlineKeyboardButton("✅ Confirm", callback_query_handler=None, callback_data=f"confirm_{user.id}_{balance:.0f}"),
                InlineKeyboardButton("❌ Reject", callback_query_handler=None, callback_data=f"reject_{user.id}_{balance:.0f}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(admin_keyboard)

        admin_msg = (
            f"📥 **NEW WITHDRAWAL REQUEST**\n\n"
            f"👤 **User:** {user.first_name} (@{user.username or 'N/A'})\n"
            f"📱 **Chat ID:** `{user.id}`\n"
            f"💰 **Amount:** `{balance:.0f} GD`\n"
            f"🏦 **GRAM Wallet Address:**\n`{wallet_address}`"
        )
        try:
            await context.bot.send_message(
                chat_id=int(ADMIN_ID), 
                text=admin_msg, 
                parse_mode="Markdown",
                reply_markup=reply_markup
            )
        except Exception as e:
            print(f"Error sending to admin: {e}")

        # ব্যবহারকারীকে কনফার্মেশন
        await update.message.reply_text(
            f"✅ **Withdrawal Request Submitted!**\n\n"
            f"Amount: `{balance:.0f} GD`\n"
            f"Address: `{wallet_address}`\n\n"
            f"The admin will review and process your payout soon.",
            parse_mode="Markdown"
        )

# এডমিন বাটন অ্যাকশন (Confirm / Reject)
async def admin_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    # শুধুমাত্র এডমিন ক্লিক করতে পারবে
    if str(query.from_user.id) != str(ADMIN_ID):
        await query.answer("❌ You are not authorized!", show_alert=True)
        return

    data = query.data
    parts = data.split("_")
    action = parts[0]
    target_user_id = parts[1]
    amount = parts[2] if len(parts) > 2 else "0"

    if action == "confirm":
        # ১. ইউজারের কাছে মেসেজ পাঠানো
        try:
            await context.bot.send_message(
                chat_id=int(target_user_id),
                text=f"✅ **Withdrawal Confirmed!**\n\nYour withdrawal request for `{amount} GD` has been successfully processed and sent to your wallet.",
                parse_mode="Markdown"
            )
        except Exception as e:
            print(f"Failed to message user: {e}")

        # ২. চ্যানেলে পেমেন্ট প্রুফ পাঠানো
        try:
            channel_msg = (
                f"🎉 **NEW PAYOUT CONFIRMED!** 🎉\n\n"
                f"👤 **User ID:** `{target_user_id}`\n"
                f"💰 **Amount:** `{amount} GD`\n"
                f"Status: **Paid ✅**\n\n"
                f"🤖 Bot: @{BOT_USERNAME}"
            )
            await context.bot.send_message(
                chat_id=PAYOUT_CHANNEL_ID,
                text=channel_msg,
                parse_mode="Markdown"
            )
        except Exception as e:
            print(f"Failed to post in channel: {e}")

        # মেসেজ এডিট করে কনফার্মড দেখানো
        await query.edit_message_text(
            text=query.message.text + "\n\n✅ **STATUS: CONFIRMED & PAID**",
            parse_mode="Markdown"
        )

    elif action == "reject":
        # ইউজারের কাছে রিজেক্ট মেসেজ পাঠানো
        try:
            await context.bot.send_message(
                chat_id=int(target_user_id),
                text=f"❌ **Withdrawal Rejected**\n\nYour withdrawal request for `{amount} GD` has been rejected by the admin.",
                parse_mode="Markdown"
            )
        except Exception as e:
            print(f"Failed to message user: {e}")

        # মেসেজ এডিট করে রিজেক্টেড দেখানো
        await query.edit_message_text(
            text=query.message.text + "\n\n❌ **STATUS: REJECTED**",
            parse_mode="Markdown"
        )

async def main():
    Thread(target=run_health_check, daemon=True).start()

    app = ApplicationBuilder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(balance_callback, pattern="^my_balance$"))
    app.add_handler(CallbackQueryHandler(withdraw_start, pattern="^withdraw_start$"))
    
    # এডমিন বাটন হ্যান্ডলার যোগ করা হয়েছে
    app.add_handler(CallbackQueryHandler(admin_button_handler, pattern="^(confirm|reject)_"))
    
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
