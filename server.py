import asyncio
import threading
import logging
import time
import random
import json
import os
import sys
import uuid
from datetime import datetime

from flask import Flask
from telethon import TelegramClient, events, Button
from telethon.errors import (
    SessionPasswordNeededError, FloodWaitError, PhoneCodeInvalidError,
    PhoneCodeExpiredError, PhoneNumberInvalidError
)
from telethon.sessions import StringSession

# ======================== الإعدادات الأساسية ========================
BOT_TOKEN = '8887748662:AAFgLMUO2eXpYzityDj35-IDTLywtdO8S8Q'
BOT_API_ID = 2040
BOT_API_HASH = 'b18441a1ff607e10a989891a5462e627'

DATA_DIR = '/data' if os.path.exists('/data') else '.'
os.makedirs(DATA_DIR, exist_ok=True)
SESSION_FILE = os.path.join(DATA_DIR, 'active_sessions.json')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# ======================== Flask للـ health check ========================
app = Flask(__name__)

@app.route('/')
def health():
    return "OK", 200

def run_flask():
    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)

# ======================== المتغيرات العامة ========================
bot = TelegramClient(f'bot_session_{uuid.uuid4().hex[:6]}', BOT_API_ID, BOT_API_HASH)

active_clients = {}
pending_logins = {}

# ======================== دالة ذكية لإرسال الكود ========================
async def smart_send_code(api_id, api_hash, phone):
    """تحاول إرسال الكود بكل الطرق الممكنة"""
    errors = []
    
    # طريقة 1: عادي
    try:
        client = TelegramClient(StringSession(), api_id, api_hash)
        await client.connect()
        result = await client.send_code_request(phone)
        return client, result.phone_code_hash
    except Exception as e:
        errors.append(f"Method1: {type(e).__name__}")
        try: await client.disconnect()
        except: pass
    
    # طريقة 2: force_sms=True
    try:
        await asyncio.sleep(2)
        client = TelegramClient(StringSession(), api_id, api_hash)
        await client.connect()
        result = await client.send_code_request(phone, force_sms=True)
        return client, result.phone_code_hash
    except Exception as e:
        errors.append(f"Method2: {type(e).__name__}")
        try: await client.disconnect()
        except: pass
    
    # طريقة 3: تأخير أطول
    try:
        await asyncio.sleep(5)
        client = TelegramClient(StringSession(), api_id, api_hash)
        await client.connect()
        result = await client.send_code_request(phone, force_sms=False)
        return client, result.phone_code_hash
    except Exception as e:
        errors.append(f"Method3: {type(e).__name__}")
        try: await client.disconnect()
        except: pass
    
    raise Exception(f"All methods failed: {' | '.join(errors)}")

# ======================== دالة ذكية للتحقق من الكود ========================
async def smart_sign_in(client, phone, code, phone_code_hash):
    """تحاول تسجيل الدخول بكل الطرق الممكنة"""
    errors = []
    
    # طريقة 1: عادي
    try:
        if not client.is_connected():
            await client.connect()
        await client.sign_in(phone=phone, code=code, phone_code_hash=phone_code_hash)
        return True
    except SessionPasswordNeededError:
        raise  # نعيدها عشان نطلب كلمة المرور
    except Exception as e:
        errors.append(f"Method1: {type(e).__name__}")
    
    # طريقة 2: إعادة اتصال
    try:
        await asyncio.sleep(1)
        await client.connect()
        await client.sign_in(phone=phone, code=code, phone_code_hash=phone_code_hash)
        return True
    except SessionPasswordNeededError:
        raise
    except Exception as e:
        errors.append(f"Method2: {type(e).__name__}")
    
    raise Exception(f"Sign in failed: {' | '.join(errors)}")

# ======================== بوت التنصيب ========================
@bot.on(events.NewMessage(pattern='/ping'))
async def bot_ping(event):
    await event.respond('Pong!')

@bot.on(events.NewMessage(pattern='/start'))
async def bot_start(event):
    buttons = [
        [Button.inline("START", b"start_setup")],
        [Button.inline("RESTART", b"restart_setup")]
    ]
    await event.respond(
        "**Rolex Telethon Setup**\n\n"
        "Press START to begin",
        buttons=buttons,
        parse_mode='md'
    )

@bot.on(events.CallbackQuery(data=b"start_setup"))
async def start_setup(event):
    pending_logins[event.sender_id] = {'state': 'api_id'}
    await event.edit(
        "**Send Your API ID**\n\n"
        "Please enter your API ID:",
        parse_mode='md'
    )
    await event.answer()

@bot.on(events.CallbackQuery(data=b"restart_setup"))
async def restart_setup(event):
    pending_logins[event.sender_id] = {'state': 'api_id'}
    await event.edit(
        "**Send Your API ID**\n\n"
        "Please enter your API ID:",
        parse_mode='md'
    )
    await event.answer()

@bot.on(events.NewMessage())
async def handle_setup(event):
    uid = event.sender_id
    if uid not in pending_logins:
        return

    state = pending_logins[uid].get('state')
    data = pending_logins[uid]

    if state == 'api_id':
        try:
            api_id = int(event.text.strip())
            data['api_id'] = api_id
            data['state'] = 'api_hash'
            await event.respond(
                "**Send Your API Hash**\n\n"
                "Please enter your API Hash:",
                parse_mode='md'
            )
        except:
            await event.respond("**Invalid API ID**")

    elif state == 'api_hash':
        data['api_hash'] = event.text.strip()
        data['state'] = 'phone'
        buttons = [[Button.request_phone("Share Phone Number", resize=True)]]
        await event.respond(
            "**Send Your Phone Number**\n\n"
            "Press the button or type manually: +201234567890",
            buttons=buttons,
            parse_mode='md'
        )

    elif state == 'phone':
        if event.message.contact:
            phone = f"+{event.message.contact.phone_number}"
        else:
            phone = event.text.strip()
        
        data['phone'] = phone
        processing = await event.respond("**Sending code...**")
        
        try:
            # استخدام الدالة الذكية
            client, phone_code_hash = await smart_send_code(
                data['api_id'], data['api_hash'], phone
            )
            
            data['client'] = client
            data['hash'] = phone_code_hash
            data['state'] = 'code'
            
            await processing.edit(
                "**Send The Code**\n\n"
                "Code sent. Please enter the code:",
                parse_mode='md'
            )
            
        except FloodWaitError as e:
            minutes = e.seconds // 60
            buttons = [[Button.inline("RETRY", b"restart_setup")]]
            await processing.edit(
                f"**Rate Limited**\nWait {minutes} min",
                buttons=buttons,
                parse_mode='md'
            )
            del pending_logins[uid]
        except Exception as e:
            logger.error(f"Send error: {e}")
            buttons = [[Button.inline("RETRY", b"restart_setup")]]
            await processing.edit(
                f"**Error: {str(e)[:50]}**",
                buttons=buttons,
                parse_mode='md'
            )
            del pending_logins[uid]

    elif state == 'code':
        code = event.text.strip()
        data = pending_logins[uid]
        processing = await event.respond("**Verifying...**")
        
        try:
            await smart_sign_in(data['client'], data['phone'], code, data['hash'])
            
            buttons = [[Button.inline("START", b"start_setup")]]
            await processing.edit(
                "**Success!**\n**Rolex Telethon**",
                buttons=buttons,
                parse_mode='md'
            )
            
        except SessionPasswordNeededError:
            data['state'] = 'password'
            await processing.edit("**2FA Password Required**\nEnter password:")
            return
        except PhoneCodeExpiredError:
            buttons = [[Button.inline("RESEND", b"resend_code")]]
            await processing.edit(
                "**Code Expired**",
                buttons=buttons,
                parse_mode='md'
            )
            return
        except PhoneCodeInvalidError:
            await processing.edit("**Invalid Code**")
            return
        except Exception as e:
            logger.error(f"Verify error: {e}")
            buttons = [[Button.inline("RETRY", b"restart_setup")]]
            await processing.edit(
                f"**Error: {str(e)[:50]}**",
                buttons=buttons,
                parse_mode='md'
            )
            del pending_logins[uid]
            return
        
        await finish_setup(event, uid)

    elif state == 'password':
        password = event.text.strip()
        data = pending_logins[uid]
        processing = await event.respond("**Verifying...**")
        
        try:
            await data['client'].sign_in(password=password)
            buttons = [[Button.inline("START", b"start_setup")]]
            await processing.edit(
                "**Success!**",
                buttons=buttons,
                parse_mode='md'
            )
        except Exception as e:
            await processing.edit(f"**Error: {str(e)[:50]}**")
            del pending_logins[uid]
            return
        
        await finish_setup(event, uid)

@bot.on(events.CallbackQuery(data=b"resend_code"))
async def resend_code_callback(event):
    uid = event.sender_id
    if uid not in pending_logins or 'phone' not in pending_logins[uid]:
        await event.answer("No active setup")
        return
    
    data = pending_logins[uid]
    
    try:
        if 'client' not in data or not data['client'].is_connected():
            client = TelegramClient(StringSession(), data['api_id'], data['api_hash'])
            await client.connect()
            data['client'] = client
        
        result = await data['client'].send_code_request(data['phone'])
        data['hash'] = result.phone_code_hash
        
        await event.edit(
            "**Send The Code**\n\nNew code sent. Enter code:",
            parse_mode='md'
        )
    except Exception as e:
        buttons = [[Button.inline("RETRY", b"restart_setup")]]
        await event.edit(
            f"**Error: {str(e)[:50]}**",
            buttons=buttons,
            parse_mode='md'
        )
    
    await event.answer()

async def finish_setup(event, uid):
    data = pending_logins[uid]
    client = data['client']
    phone = data['phone']
    api_id = data['api_id']
    api_hash = data['api_hash']
    session_str = client.session.save()
    del pending_logins[uid]

    if await start_userbot(phone, session_str, api_id, api_hash):
        msg = "**Setup Complete!**\n**Rolex Telethon**"
        if hasattr(event, 'edit'):
            await event.edit(msg, parse_mode='md')
        else:
            await event.respond(msg, parse_mode='md')
    else:
        msg = "**Failed to start account**"
        if hasattr(event, 'edit'):
            await event.edit(msg, parse_mode='md')
        else:
            await event.respond(msg, parse_mode='md')

async def start_userbot(phone, session_str, api_id, api_hash):
    client = TelegramClient(StringSession(session_str), api_id, api_hash)
    await client.connect()
    if await client.is_user_authorized():
        active_clients[phone] = client
        await save_all_sessions()
        return True
    return False

async def save_all_sessions():
    sessions = {}
    for phone, client in active_clients.items():
        if client.is_connected():
            sessions[phone] = {
                'session': client.session.save(),
                'api_id': client.api_id,
                'api_hash': client.api_hash
            }
    with open(SESSION_FILE, 'w') as f:
        json.dump(sessions, f)

async def load_all_sessions():
    if not os.path.exists(SESSION_FILE):
        return
    with open(SESSION_FILE, 'r') as f:
        sessions = json.load(f)
    for phone, data in sessions.items():
        try:
            client = TelegramClient(StringSession(data['session']), data['api_id'], data['api_hash'])
            await client.connect()
            if await client.is_user_authorized():
                active_clients[phone] = client
                logger.info(f"Account loaded: {phone}")
        except Exception as e:
            logger.error(f"Failed to load {phone}: {e}")

# ======================== بدء التشغيل ========================
async def main():
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    logger.info("Flask started")

    await bot.start(bot_token=BOT_TOKEN)
    logger.info("Bot ready")
    await load_all_sessions()
    await bot.run_until_disconnected()

if __name__ == '__main__':
    asyncio.run(main())
