import os
import re
import logging
import asyncio
import requests
from http.server import HTTPServer, BaseHTTPRequestHandler
from threading import Thread
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, CallbackQueryHandler, MessageHandler, filters

# ========== TON AUTO PAYMENT ==========
from tonutils.client import ToncenterV3Client
from tonutils.wallet import WalletV4R2

# Environment Variables (Render-এ সেট করো)
MNEMONIC = os.environ.get("TON_MNEMONIC", "").split()
TONCENTER_API_KEY = os.environ.get("TONCENTER_API_KEY", None)
IS_TESTNET = False  # Mainnet

# 1 GD = কত GRAM পাঠাবে (নিজের মতো অ্যাডজাস্ট করো)
# উদাহরণ: খুব ছোট রাখলে 0.00001, বড় রাখলে বাড়াও
GD_TO_GRAM_RATE = 0.00001

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
BOT_TOKEN = os.environ.get("BOT_TOKEN", "YOUR_NEW_BOT_TOKEN_HERE")
BOT_USERNAME = "GramWalletPay_Bot"
MINI_APP_URL = "https://polmain1.vercel.app/"
REFER_BONUS = 20.0
START_IMAGE_URL = "https://ibb.co.com/BHbcTGjc"
CHANNEL_URL = "https://t.me/EARNINGllNEWS"
PAYOUT_CHANNEL_ID = "@Smartgrowsmm_payout"
ADMIN_ID = "7888333547"

async def send_gram_payment(destination: str, amount_gram: float, comment: str = "GramWallet Pay"):
    if not MNEMONIC or len(MNEMONIC) < 12:
        raise Exception("TON_MNEMONIC environment variable missing or invalid!")
    
    client = ToncenterV3Client(
        is_testnet=IS_TESTNET,
        api_key=TONCENTER_API_KEY,
        rps=1,
        max_retries=3
    )
    wallet, _, _, _ = WalletV4R2.from_mnemonic(client, MNEMONIC)
    
    tx_hash = await wallet.transfer(
        destination=destination,
        amount=amount_gram,
        body=comment
    )
    return str(tx_hash)

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
                new_bal = current_bal + REFER_BONUS
                
                requests.patch(f"{FIREBASE_URL}/users/{ref_by}.json", json={
                    'balance': new_bal,
                    'referrals': current_refs + 1
                })
                try:
                    await context.bot.send_message(
                        chat_id=int(ref_by),
                        text=f"🎉 **New Referral!**\n{user.first_name} joined.\n+{REFER_BONUS:.0f} GD\nBalance: `{new_bal:.0f} GD`",
                        parse_mode="Markdown"
                    )
                except:
                    pass

    keyboard = [
        [InlineKeyboardButton("Play 🎮", web_app=WebAppInfo(url=MINI_APP_URL))],
        [InlineKeyboardButton("Join the Earning News ↗️", url=CHANNEL_URL)]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    start_text = (
        f"🎁 Welcome to Gram Wallet Pay, {user.first_name}!\n\n"
        "Earn GRAM Tokens by tasks + referrals.\n\n"
        "👇 Tap below to open the Mini App!"
    )

    try:
        await update.message.reply_photo(
            photo=START_IMAGE_URL,
            caption=start_text,
            reply_markup=reply_markup
        )
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
    # Wallet address extract
    wallet_match = re.search(r'`([UE]Q[A-Za-z0-9_-]{46,})`', message_text)
    wallet_address = wallet_match.group(1) if wallet_match else None

    if action == "confirm":
        if not wallet_address:
            await query.edit_message_text(
                text=message_text + "\n\n❌ **ERROR: Wallet address not found!**",
                parse_mode="Markdown"
            )
            return

        try:
            gram_amount = round(amount * GD_TO_GRAM_RATE, 6)
            if gram_amount < 0.001:
                raise Exception(f"Amount too small ({gram_amount} GRAM). Increase GD_TO_GRAM_RATE")

            tx_hash = await send_gram_payment(
                destination=wallet_address,
                amount_gram=gram_amount,
                comment=f"GWP Withdraw {amount} GD | UID {target_user_id}"
            )

            tx_link = f"https://tonviewer.com/transaction/{tx_hash}"

            # User notification
            await context.bot.send_message(
                chat_id=int(target_user_id),
                text=(
                    f"✅ **Withdrawal Paid Successfully!**\n\n"
                    f"💰 Amount: `{amount:.0f} GD` → `{gram_amount} GRAM`\n"
                    f"🏦 Wallet: `{wallet_address}`\n"
                    f"🔗 TX Hash: `{tx_hash}`\n"
                    f"🔍 View: {tx_link}"
                ),
                parse_mode="Markdown",
                disable_web_page_preview=True
            )

            # Channel post
            try:
                await context.bot.send_message(
                    chat_id=PAYOUT_CHANNEL_ID,
                    text=(
                        f"🎉 **NEW PAYOUT CONFIRMED!** 🎉\n\n"
                        f"👤 User ID: `{target_user_id}`\n"
                        f"💰 `{amount:.0f} GD` → `{gram_amount} GRAM`\n"
                        f"🔗 TX: `{tx_hash}`\n"
                        f"Status: **Paid ✅**\n"
                        f"🤖 @{BOT_USERNAME}"
                    ),
                    parse_mode="Markdown"
                )
            except Exception as e:
                print("Channel error:", e)

            # Update Firebase transaction status (optional best effort)
            try:
                user_res = requests.get(f"{FIREBASE_URL}/users/{target_user_id}.json")
                udata = user_res.json() or {}
                txs = udata.get("transactions", [])
                for tx in txs:
                    if tx.get("status") == "Pending" and float(tx.get("amount", 0)) == amount:
                        tx["status"] = "Paid"
                        tx["tx_hash"] = tx_hash
                        break
                requests.patch(f"{FIREBASE_URL}/users/{target_user_id}.json", json={"transactions": txs})
            except:
                pass

            await query.edit_message_text(
                text=message_text + f"\n\n✅ **STATUS: CONFIRMED & AUTO-PAID**\nTX: `{tx_hash}`",
                parse_mode="Markdown"
            )

        except Exception as e:
            error_msg = str(e)
            await query.edit_message_text(
                text=message_text + f"\n\n❌ **AUTO-PAY FAILED:** `{error_msg}`",
                parse_mode="Markdown"
            )
            try:
                await context.bot.send_message(
                    chat_id=int(target_user_id),
                    text=f"❌ Auto payment failed. Admin will check manually.\nError: {error_msg}"
                )
            except:
                pass

    elif action == "reject":
        # Refund balance
        try:
            res = requests.get(f"{FIREBASE_URL}/users/{target_user_id}.json")
            udata = res.json() or {}
            current = float(udata.get("balance", 0))
            new_bal = current + amount
            requests.patch(f"{FIREBASE_URL}/users/{target_user_id}.json", json={"balance": new_bal})

            # Update tx status
            txs = udata.get("transactions", [])
            for tx in txs:
                if tx.get("status") == "Pending" and float(tx.get("amount", 0)) == amount:
                    tx["status"] = "Rejected"
                    break
            requests.patch(f"{FIREBASE_URL}/users/{target_user_id}.json", json={"transactions": txs})
        except Exception as e:
            print("Refund error:", e)

        try:
            await context.bot.send_message(
                chat_id=int(target_user_id),
                text=f"❌ **Withdrawal Rejected**\n\n`{amount:.0f} GD` request rejected.\nBalance refunded.",
                parse_mode="Markdown"
            )
        except:
            pass

        await query.edit_message_text(
            text=message_text + "\n\n❌ **STATUS: REJECTED** (Balance refunded)",
            parse_mode="Markdown"
        )

async def main():
    Thread(target=run_health_check, daemon=True).start()

    app = ApplicationBuilder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(admin_button_handler, pattern="^(confirm|reject)_"))

    print("Bot is running with TON Auto Payment...")
    
    await app.initialize()
    await app.start()
    await app.updater.start_polling()
    
    await asyncio.Event().wait()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
