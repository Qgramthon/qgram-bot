import asyncio
import threading
from functools import wraps
from typing import Dict, Tuple
from concurrent.futures import ThreadPoolExecutor
import logging
import time
import random
import json
import os
import sys
import uuid
from collections import Counter
from datetime import datetime, timedelta

from flask import Flask, jsonify, request
from telethon import TelegramClient, events, Button
from telethon.errors import SessionPasswordNeededError, FloodWaitError
from telethon.sessions import StringSession

# ======================== إعدادات ========================
BOT_TOKEN = '8887748662:AAFgLMUO2eXpYzityDj35-IDTLywtdO8S8Q'
BOT_API_ID = 2040
BOT_API_HASH = 'b18441a1ff607e10a989891a5462e627'

DATA_DIR = '/data' if os.path.exists('/data') else '.'
os.makedirs(DATA_DIR, exist_ok=True)
SESSION_FILE = os.path.join(DATA_DIR, 'active_sessions.json')
API_CONFIG_FILE = os.path.join(DATA_DIR, 'api_config.json')

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', handlers=[logging.StreamHandler(sys.stdout)])
logger = logging.getLogger(__name__)

# ======================== Flask للـ health check ========================
app = Flask(__name__)

@app.route('/')
def home():
    return "OK"

@app.route('/health')
def health():
    return "OK", 200

# ======================== Main Loop (نفس الموقع بالضبط) ========================
main_loop = asyncio.new_event_loop()

active_clients: Dict[str, TelegramClient] = {}
pending_logins: Dict[str, Tuple[TelegramClient, str, int, str]] = {}
api_configs_storage: Dict[str, Dict] = {}

def run_async_in_main_loop(coro):
    future = asyncio.run_coroutine_threadsafe(coro, main_loop)
    return future.result(timeout=300)

async def save_all_sessions():
    try:
        sessions_data, configs = {}, {}
        for phone, client in active_clients.items():
            try:
                if client.is_connected():
                    sessions_data[phone] = client.session.save()
                    if phone in api_configs_storage:
                        configs[phone] = api_configs_storage[phone]
            except:
                continue
        with open(SESSION_FILE, 'w') as f:
            json.dump(sessions_data, f)
        with open(API_CONFIG_FILE, 'w') as f:
            json.dump(configs, f)
    except:
        pass

async def load_all_sessions():
    try:
        if not os.path.exists(SESSION_FILE):
            return
        with open(SESSION_FILE, 'r') as f:
            sessions = json.load(f)
        with open(API_CONFIG_FILE, 'r') as f:
            configs = json.load(f)
        for phone, session_str in sessions.items():
            try:
                if phone in configs:
                    api_id = configs[phone]['api_id']
                    api_hash = configs[phone]['api_hash']
                    client = TelegramClient(StringSession(session_str), api_id, api_hash)
                    await client.connect()
                    if await client.is_user_authorized():
                        active_clients[phone] = client
                        api_configs_storage[phone] = configs[phone]
                        logger.info(f"Restored: {phone}")
            except:
                pass
    except:
        pass

# ======================== بوت تيليجرام ========================
bot = TelegramClient(f'bot_session_{uuid.uuid4().hex[:6]}', BOT_API_ID, BOT_API_HASH)

# تخزين مؤقت للمستخدمين أثناء التنصيب
setup_state = {}  # {user_id: {'state': ..., 'api_id': ..., 'api_hash': ...}}

@bot.on(events.NewMessage(pattern='/ping'))
async def ping(event):
    await event.respond('Pong!')

@bot.on(events.NewMessage(pattern='/start'))
async def start(event):
    buttons = [[Button.inline("START SETUP", b"start_setup")]]
    await event.respond(
        "**Rolex Telethon Setup Bot**\n\nPress START SETUP to begin.",
        buttons=buttons,
        parse_mode='md'
    )

@bot.on(events.CallbackQuery(data=b"start_setup"))
async def start_setup(event):
    setup_state[event.sender_id] = {'state': 'api_id'}
    await event.edit("**Send your API ID:**", parse_mode='md')
    await event.answer()

@bot.on(events.NewMessage())
async def handle_setup(event):
    uid = event.sender_id
    if uid not in setup_state:
        return
    
    state = setup_state[uid].get('state')
    data = setup_state[uid]
    
    if state == 'api_id':
        try:
            api_id = int(event.text.strip())
            data['api_id'] = api_id
            data['state'] = 'api_hash'
            await event.respond("**Send your API Hash:**", parse_mode='md')
        except:
            await event.respond("**Invalid API ID**")
    
    elif state == 'api_hash':
        data['api_hash'] = event.text.strip()
        data['state'] = 'phone'
        buttons = [[Button.request_phone("Share Phone Number", resize=True)]]
        await event.respond(
            "**Send your Phone Number:**\n\nPress button or type: +201234567890",
            buttons=buttons,
            parse_mode='md'
        )
    
    elif state == 'phone':
        if event.message.contact:
            phone = f"+{event.message.contact.phone_number}"
        else:
            phone = event.text.strip()
        
        # استخدام main_loop لإرسال الكود (نفس الموقع)
        async def send_code():
            api_id = data['api_id']
            api_hash = data['api_hash']
            
            api_configs_storage[phone] = {'api_id': api_id, 'api_hash': api_hash}
            client = TelegramClient(StringSession(), api_id, api_hash)
            await client.connect()
            
            if await client.is_user_authorized():
                active_clients[phone] = client
                await save_all_sessions()
                return 'already_active', None
            
            sent = await client.send_code_request(phone)
            pending_logins[phone] = (client, sent.phone_code_hash, api_id, api_hash)
            return 'code_sent', sent.phone_code_hash
        
        try:
            status, result = run_async_in_main_loop(send_code())
            
            if status == 'already_active':
                await event.respond("**Account already active!**")
                del setup_state[uid]
                return
            
            setup_state[uid]['phone'] = phone
            setup_state[uid]['state'] = 'code'
            await event.respond(
                "**Code sent!**\n\nCheck your Telegram app for the code.\nEnter the code:",
                parse_mode='md'
            )
        except Exception as e:
            logger.error(f"Send code error: {e}")
            await event.respond(f"**Error: {str(e)[:100]}**")
            del setup_state[uid]
    
    elif state == 'code':
        code = event.text.strip()
        phone = setup_state[uid].get('phone')
        
        if phone not in pending_logins:
            await event.respond("**Session expired. Please restart with /start**")
            del setup_state[uid]
            return
        
        # استخدام main_loop للتحقق (نفس الموقع)
        async def verify():
            client, phone_code_hash, api_id, api_hash = pending_logins[phone]
            try:
                await client.sign_in(phone=phone, code=code, phone_code_hash=phone_code_hash)
            except SessionPasswordNeededError:
                return '2fa_needed'
            
            active_clients[phone] = client
            del pending_logins[phone]
            await save_all_sessions()
            return 'success'
        
        try:
            status = run_async_in_main_loop(verify())
            
            if status == '2fa_needed':
                setup_state[uid]['state'] = 'password'
                await event.respond("**2FA Password Required**\nEnter your password:", parse_mode='md')
                return
            
            del setup_state[uid]
            await event.respond(
                "**Setup Complete!**\n\nYour account is now active as a UserBot.\nSend `.بنغ` from your account to test.",
                parse_mode='md'
            )
        except Exception as e:
            logger.error(f"Verify error: {e}")
            await event.respond(f"**Error: {str(e)[:100]}**")
            del setup_state[uid]
    
    elif state == 'password':
        password = event.text.strip()
        phone = setup_state[uid].get('phone')
        
        if phone not in pending_logins:
            await event.respond("**Session expired. Please restart with /start**")
            del setup_state[uid]
            return
        
        async def verify_pass():
            client, phone_code_hash, api_id, api_hash = pending_logins[phone]
            await client.sign_in(password=password)
            active_clients[phone] = client
            del pending_logins[phone]
            await save_all_sessions()
        
        try:
            run_async_in_main_loop(verify_pass())
            del setup_state[uid]
            await event.respond(
                "**Setup Complete!**\n\nYour account is now active as a UserBot.\nSend `.بنغ` from your account to test.",
                parse_mode='md'
            )
        except Exception as e:
            logger.error(f"Password error: {e}")
            await event.respond(f"**Error: {str(e)[:100]}**")
            del setup_state[uid]

# ======================== بدء التشغيل ========================
def start_main_loop():
    asyncio.set_event_loop(main_loop)
    main_loop.run_until_complete(load_all_sessions())
    main_loop.run_forever()

threading.Thread(target=start_main_loop, daemon=True).start()

async def main():
    flask_thread = threading.Thread(
        target=lambda: app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False),
        daemon=True
    )
    flask_thread.start()
    logger.info("Flask started")
    
    await bot.start(bot_token=BOT_TOKEN)
    logger.info("Bot started")
    await bot.run_until_disconnected()

if __name__ == '__main__':
    asyncio.run_coroutine_threadsafe(main(), main_loop)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
