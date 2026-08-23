import os
import re
import asyncio
import requests
from http.server import HTTPServer, BaseHTTPRequestHandler
from threading import Thread
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, CallbackQueryHandler

from tonutils.client import ToncenterClient
from tonutils.wallet import WalletV4R2

# ================== CONFIG ==================
BOT_TOKEN = "8860607501:AAHwZXswmo2fd8OtqOIX3E9__Ts-GuT4xkU"
BOT_USERNAME = "GramWalletPay_Bot"
MINI_APP_URL = "https://tg-mini-app-ecru.vercel.app/"
FIREBASE_URL = "https://pol-55434-default-rtdb.firebaseio.com"
ADMIN_ID = "7888333547"
PAYOUT_CHANNEL_ID = "@Smartgrowsmm_payout"
CHANNEL_URL = "https://t.me/EARNINGllNEWS"
START_IMAGE_URL = "https://ibb.co.com/BHbcTGjc"
REFER_BONUS = 20.0

# TON Credentials
TONCENTER_API_KEY = "028a77f69c8b3599ba220ca18b5d8e5c5f40c508692bd8283d9d2fe947db5fdc"
MNEMONIC = [
    "axis", "grape", "business", "tilt", "liar", "extend",
    "economy", "tiger", "water", "robot", "float", "olympic",
    "sad", "ozone", "sure", "endless", "shift", "area",
    "own", "harvest", "wine", "zebra", "web", "one"
]

IS_TESTNET = False
GD_TO_GRAM_RATE = 0.00001

# ================== HEALTH CHECK ==================
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is live!")

def run_health_check():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
    server.serve_forever()

# ================== TON SEND ==================
async def send_gram_payment(destination: str, amount_gram: float, comment: str = "GramWallet Pay"):
    if not MNEMONIC or len(MNEMONIC) < 12:
        raise Exception("TON Mnemonic missing or invalid!")
    
    client = ToncenterClient(
        api_key=TONCENTER_API_KEY,
        is_testnet=IS_TESTNET
    )
    wallet, _, _, _ = WalletV4R2.from_mnemonic(client, MNEMONIC)
    
    tx_hash = await wallet.transfer(
        destination=destination,
        amount=amount_gram,
        body=comment
    )
    return str(tx_hash)

# ================== HANDLERS ==================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = str(user.id)
    args = context.args
    ref_by = args[0].replace('ref_', '') if args and args[0].startswith('ref_') else None

    res = requests.get(f"{FIREBASE_URL}/users/{user_id}.json")
    user_data = res.json()

    if not user_data:
        new_user = {
            'name': user.first_name,
            'first_name': user.first_name,
            'username': user.username or '',
            'balance': 0.0,
            'referrals': 0,
            'referredBy': ref_by or '',
            'dailyClaimed': False,
            'completedTasks': [],
            'transactions': []
        }
        requests.put(f"{FIREBASE_URL}/users/{user_id}.json", json=new_user)

        if ref_by and ref_by != user_id:
            ref_res = requests.get(f"{FIREBASE_URL}/users/{ref_by}.json")
            referrer_data = ref_res.json()
            if referrer_data:
                current_bal = float(referrer_data.get('balance', 0.0))
                current_refs = int(referrer_data.get('referrals', 0))
                requests.patch(f"{FIREBASE_URL}/users/{ref_by}.json", json={
                    'balance': current_bal + REFER_BONUS,
                    'referrals': current_refs + 1
                })
                try:
                    await context.bot.send_message(
                        chat_id=int(ref_by),
                        text=f"🎉 New Referral!\n{user.first_name} joined.\n+{REFER_BONUS:.0f} GD",
                        parse_mode="Markdown"
                    )
                except:
                    pass

    keyboard = [
        [InlineKeyboardButton("Play 🎮", web_app=WebAppInfo(url=MINI_APP_URL))],
        [InlineKeyboardButton("Join Earning News ↗️", url=CHANNEL_URL)]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    start_text = (
        f"🎁 Welcome to Gram Wallet Pay, {user.first_name}!\n\n"
        "Earn GRAM Tokens by tasks + referrals.\n\n"
        "👇 Tap below to open the Mini App!"
    )

    try:
        await update.message.reply_photo(photo=START_IMAGE_URL, caption=start_text, reply_markup=reply_markup)
    except:
        await update.message.reply_text(text=start_text, reply_markup=reply_markup)

async def admin_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if str(query.from_user.id) != str(ADMIN_ID):
        await query.answer("❌ You are not authorized!", show_alert=True)
        return

    data = query.data
    parts = data.split("_")
    action = parts[0]
    target_user_id = parts[1]
    amount = float(parts[2]) if len(parts) > 2 else 0.0

    message_text = query.message.text or ""
    wallet_match = re.search(r'`([UE]Q[A-Za-z0-9_-]{46,})`', message_text)
    wallet_address = wallet_match.group(1) if wallet_match else None

    if action == "confirm":
        if not wallet_address:
            await query.edit_message_text(text=message_text + "\n\n❌ Wallet address not found!", parse_mode="Markdown")
            return

        try:
            gram_amount = round(amount * GD_TO_GRAM_RATE, 6)
            if gram_amount < 0.001:
                raise Exception(f"Amount too small ({gram_amount} GRAM)")

            tx_hash = await send_gram_payment(wallet_address, gram_amount, f"GWP {amount} GD | {target_user_id}")

            tx_link = f"https://tonviewer.com/transaction/{tx_hash}"

            await context.bot.send_message(
                chat_id=int(target_user_id),
                text=(
                    f"✅ **Withdrawal Paid!**\n\n"
                    f"💰 `{amount:.0f} GD` → `{gram_amount} GRAM`\n"
                    f"🏦 `{wallet_address}`\n"
                    f"🔗 TX: `{tx_hash}`\n"
                    f"🔍 {tx_link}"
                ),
                parse_mode="Markdown",
                disable_web_page_preview=True
            )

            try:
                await context.bot.send_message(
                    chat_id=PAYOUT_CHANNEL_ID,
                    text=f"🎉 **PAYOUT CONFIRMED**\nUser: `{target_user_id}`\nAmount: `{amount:.0f} GD`\nTX: `{tx_hash}`\n@{BOT_USERNAME}",
                    parse_mode="Markdown"
                )
            except:
                pass

            await query.edit_message_text(
                text=message_text + f"\n\n✅ **AUTO-PAID**\nTX: `{tx_hash}`",
                parse_mode="Markdown"
            )

        except Exception as e:
            await query.edit_message_text(
                text=message_text + f"\n\n❌ **FAILED:** `{str(e)}`",
                parse_mode="Markdown"
            )

    elif action == "reject":
        try:
            res = requests.get(f"{FIREBASE_URL}/users/{target_user_id}.json")
            udata = res.json() or {}
            current = float(udata.get("balance", 0))
            requests.patch(f"{FIREBASE_URL}/users/{target_user_id}.json", json={"balance": current + amount})
        except:
            pass

        try:
            await context.bot.send_message(
                chat_id=int(target_user_id),
                text=f"❌ Withdrawal Rejected\n`{amount:.0f} GD` refunded.",
                parse_mode="Markdown"
            )
        except:
            pass

        await query.edit_message_text(
            text=message_text + "\n\n❌ **REJECTED** (Balance refunded)",
            parse_mode="Markdown"
        )

async def main():
    Thread(target=run_health_check, daemon=True).start()
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(admin_button_handler, pattern="^(confirm|reject)_"))
    print("Bot running with Auto TON Payment...")
    await app.initialize()
    await app.start()
    await app.updater.start_polling()
    await asyncio.Event().wait()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
