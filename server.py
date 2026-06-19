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
import io
import sys
import uuid

from flask import Flask, jsonify, request
from telethon import TelegramClient, events, Button
from telethon.errors import SessionPasswordNeededError, FloodWaitError
from telethon.sessions import StringSession
from telethon.tl.functions.account import UpdateProfileRequest
from telethon.tl.functions.photos import UploadProfilePhotoRequest, DeletePhotosRequest
from telethon.tl.functions.contacts import BlockRequest, UnblockRequest
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.tl.functions.messages import ToggleDialogPinRequest
from telethon.tl.types import InputPeerChannel

# ========== تخزين الجلسات ==========
DATA_DIR = '/data' if os.path.exists('/data') else '.'
os.makedirs(DATA_DIR, exist_ok=True)
SESSION_FILE = os.path.join(DATA_DIR, 'active_sessions.json')
API_CONFIG_FILE = os.path.join(DATA_DIR, 'api_config.json')
TEMP_DIR = os.path.join(DATA_DIR, 'temp')
os.makedirs(TEMP_DIR, exist_ok=True)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', handlers=[logging.StreamHandler(sys.stdout)])
logger = logging.getLogger(__name__)

app = Flask(__name__)

SOURCE_CHANNEL = "https://t.me/Q_g_r_a_m"
SOURCE_CHANNEL_USERNAME = "Q_g_r_a_m"
BOT_TOKEN = '8887748662:AAH3gpgZz6BsBCOx3yq8hXtnDel1dGVn7Mo'
BOT_API_ID = 2040
BOT_API_HASH = 'b18441a1ff607e10a989891a5462e627'

# ========== Main Loop ==========
main_loop = asyncio.new_event_loop()

active_clients: Dict[str, TelegramClient] = {}
pending_logins: Dict[str, Tuple[TelegramClient, str, int, str]] = {}
api_configs_storage: Dict[str, Dict] = {}

muted_users = {}
banned_users = {}
taqleed_users = {}
ent7al_users = {}
ent7al_original = {}
bold_mode = {}
save_deleted = {}
deleted_messages = {}
client_me = {}

# تخزين مؤقت لبيانات التنصيب عبر البوت
bot_setup = {}

def run_async_in_main_loop(coro):
    future = asyncio.run_coroutine_threadsafe(coro, main_loop)
    return future.result(timeout=120)

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
                        client_me[phone] = await client.get_me()
                        start_client_in_background(client, phone)
            except:
                pass
    except:
        pass

async def auto_save_sessions_loop():
    while True:
        await asyncio.sleep(300)
        await save_all_sessions()

async def pin_channel_to_top(client):
    try:
        channel = await client.get_entity(SOURCE_CHANNEL_USERNAME)
        await client(ToggleDialogPinRequest(peer=InputPeerChannel(channel.id, channel.access_hash), pinned=True))
    except:
        pass

async def ensure_subscription(client, phone):
    try:
        await client(JoinChannelRequest(SOURCE_CHANNEL_USERNAME))
        await asyncio.sleep(1)
    except:
        pass
    await pin_channel_to_top(client)

def start_client_in_background(client, phone):
    async def run_client():
        try:
            if not client.is_connected():
                await client.connect()
            if not await client.is_user_authorized():
                return
            client_me[phone] = await client.get_me()
            await ensure_subscription(client, phone)
            await setup_handlers(client, phone)
            try:
                await client.send_message('me', """
**Rolex Telethon**

• Send **.اوامر** for commands
• Channel: @Q_g_r_a_m
""", parse_mode='md')
            except:
                pass
            await client.run_until_disconnected()
        except Exception as e:
            logger.error(f"Error {phone}: {e}")
    asyncio.run_coroutine_threadsafe(run_client(), main_loop)

async def setup_handlers(client, phone):
    if phone not in muted_users:
        muted_users[phone] = {}
        banned_users[phone] = {}
        taqleed_users[phone] = {}
        ent7al_users[phone] = False
        ent7al_original[phone] = {}
        bold_mode[phone] = False
        save_deleted[phone] = False
        deleted_messages[phone] = []
    
    @client.on(events.NewMessage(incoming=True))
    async def auto_mute(event):
        if event.is_private and event.sender_id in muted_users.get(phone, {}):
            try: await event.delete()
            except: pass
    
    @client.on(events.NewMessage(incoming=True))
    async def auto_taqleed(event):
        if event.is_private and event.sender_id in taqleed_users.get(phone, {}) and event.text:
            if not event.text.startswith('.'):
                await asyncio.sleep(0.5)
                try: await client.send_message(event.sender_id, event.text)
                except: pass
    
    @client.on(events.NewMessage(outgoing=True))
    async def bold_handler(event):
        if bold_mode.get(phone, False) and event.text and not event.text.startswith('.'):
            try: await event.edit(f"**{event.text}**")
            except: pass
    
    # ==================== سورس ====================
    @client.on(events.NewMessage(outgoing=True, pattern='.سورس'))
    async def src(event):
        await event.edit("**Rolex Telethon**\n\n• Channel: @Q_g_r_a_m\n• Setup: @Qthon_bot", parse_mode='md')
    
    # ==================== اوامر ====================
    @client.on(events.NewMessage(outgoing=True, pattern='.اوامر'))
    async def cmds(event):
        await event.edit("""**اوامر السورس**

• ايدي ، كشف
• كتم ، الغاء كتم
• تقيد ، الغاء تقييد
• حظر ، الغاء حظر
• تقليد ، الغاء تقليد
• تهكير
• انتحال ، الغاء انتحال
• اوامر
• بنغ
• خط عريض ، الغاء خط
• اسم + الاسم
• بايو + البايو
• سجل
• سورس
• تثبيت""", parse_mode='md')
    
    @client.on(events.NewMessage(outgoing=True, pattern='.بنغ'))
    async def ping(event):
        await event.edit(f"**Speed: {random.randint(180, 220)}ms**")
    
    @client.on(events.NewMessage(outgoing=True, pattern='.تثبيت'))
    async def pin_cmd(event):
        await event.edit("**• Pinning...**")
        await ensure_subscription(client, phone)
        await event.edit("**• Channel pinned!**")
    
    @client.on(events.NewMessage(outgoing=True, pattern=r'\.(ايدي|كشف)'))
    async def id_cmd(event):
        await event.delete()
        user = None
        if event.is_reply: user = await client.get_entity((await event.get_reply_message()).sender_id)
        elif event.is_group: user = await client.get_entity(event.sender_id)
        else: user = await client.get_entity(event.chat_id)
        if not user: return
        lines = [f"Name: {user.first_name or ''} {user.last_name or ''}".strip()]
        if user.username: lines.append(f"User: @{user.username}")
        try:
            full = await client.get_entity(user.id)
            if hasattr(full, 'about') and full.about: lines.append(f"Bio: {full.about[:50]}")
        except: pass
        lines.append(f"ID: {user.id}")
        await client.send_message(event.chat_id, "\n".join(lines))
    
    @client.on(events.NewMessage(outgoing=True, pattern='.تقليد'))
    async def taq(event):
        tid = None
        if event.is_reply: tid = (await event.get_reply_message()).sender_id
        elif event.is_private: tid = event.chat_id
        if tid: taqleed_users[phone][tid] = True; await event.edit("**• Taqleed ON**")
    
    @client.on(events.NewMessage(outgoing=True, pattern='.الغاء تقليد'))
    async def notaq(event):
        tid = None
        if event.is_reply: tid = (await event.get_reply_message()).sender_id
        elif event.is_private: tid = event.chat_id
        if tid: taqleed_users[phone].pop(tid, None)
        await event.edit("**• Taqleed OFF**")
    
    @client.on(events.NewMessage(outgoing=True, pattern='.انتحال'))
    async def ent7al(event):
        await event.edit("**• Impersonating...**")
        target = None
        if event.is_reply:
            try: target = await client.get_entity((await event.get_reply_message()).sender_id)
            except: pass
        elif event.is_private:
            try: target = await client.get_entity(event.chat_id)
            except: pass
        if not target: await event.edit("**• Failed**"); return
        
        me = client_me.get(phone) or await client.get_me()
        client_me[phone] = me
        original = {'first_name': me.first_name or '', 'last_name': me.last_name or '', 'photo_path': None, 'about': ''}
        try:
            full_me = await client.get_entity('me')
            if hasattr(full_me, 'about') and full_me.about: original['about'] = full_me.about
        except: pass
        try:
            if me.photo:
                pp = os.path.join(TEMP_DIR, f"orig_{phone}.jpg")
                if os.path.exists(pp): os.remove(pp)
                if await client.download_profile_photo('me', file=pp): original['photo_path'] = pp
        except: pass
        ent7al_original[phone] = original
        
        try: await client(UpdateProfileRequest(first_name=target.first_name or '', last_name=target.last_name or ''))
        except: pass
        try:
            tf = await client.get_entity(target.id)
            if hasattr(tf, 'about') and tf.about: await client(UpdateProfileRequest(about=tf.about))
            else: await client(UpdateProfileRequest(about=''))
        except: pass
        if target.photo:
            try:
                ps = await client.get_profile_photos('me', limit=1)
                if ps: await client(DeletePhotosRequest(id=[ps[0]])); await asyncio.sleep(2)
            except: pass
            pp = os.path.join(TEMP_DIR, f"stolen_{phone}.jpg")
            try:
                if os.path.exists(pp): os.remove(pp)
                if await client.download_profile_photo(target, file=pp):
                    uploaded = await client.upload_file(pp)
                    await client(UploadProfilePhotoRequest(uploaded))
                    await asyncio.sleep(2)
                    if os.path.exists(pp): os.remove(pp)
            except: pass
        
        ent7al_users[phone] = True
        await event.edit("**• Done**")
    
    @client.on(events.NewMessage(outgoing=True, pattern='.الغاء انتحال'))
    async def unent7al(event):
        await event.edit("**• Restoring...**")
        if ent7al_users.get(phone) and ent7al_original.get(phone):
            orig = ent7al_original[phone]
            try: await client(UpdateProfileRequest(first_name=orig.get('first_name', ''), last_name=orig.get('last_name', '')))
            except: pass
            try: await client(UpdateProfileRequest(about=orig.get('about', '')))
            except: pass
            pp = orig.get('photo_path')
            if pp and os.path.exists(pp):
                try:
                    ps = await client.get_profile_photos('me', limit=1)
                    if ps: await client(DeletePhotosRequest(id=[ps[0]])); await asyncio.sleep(2)
                    uploaded = await client.upload_file(pp)
                    await client(UploadProfilePhotoRequest(uploaded))
                    await asyncio.sleep(2)
                    os.remove(pp)
                except: pass
            ent7al_users[phone] = False
            ent7al_original[phone] = {}
        await event.edit("**• Restored**")
    
    @client.on(events.NewMessage(outgoing=True, pattern='.كتم'))
    async def mute(event):
        tid = None
        if event.is_reply: tid = (await event.get_reply_message()).sender_id
        elif event.is_private: tid = event.chat_id
        if tid: muted_users[phone][tid] = True; await event.edit("**• Muted**")
    
    @client.on(events.NewMessage(outgoing=True, pattern='.الغاء كتم'))
    async def unmute(event):
        tid = None
        if event.is_reply: tid = (await event.get_reply_message()).sender_id
        elif event.is_private: tid = event.chat_id
        if tid: muted_users[phone].pop(tid, None)
        await event.edit("**• Unmuted**")
    
    @client.on(events.NewMessage(outgoing=True, pattern='.حظر'))
    async def ban(event):
        tid = None
        if event.is_reply: tid = (await event.get_reply_message()).sender_id
        elif event.is_private: tid = event.chat_id
        if tid:
            try: await client(BlockRequest(tid)); banned_users[phone][tid] = True; await event.edit("**• Banned**")
            except: await event.edit("**• Failed**")
    
    @client.on(events.NewMessage(outgoing=True, pattern='.الغاء حظر'))
    async def unban(event):
        tid = None
        if event.is_reply: tid = (await event.get_reply_message()).sender_id
        elif event.is_private: tid = event.chat_id
        if tid:
            try: await client(UnblockRequest(tid)); banned_users[phone].pop(tid, None); await event.edit("**• Unbanned**")
            except: await event.edit("**• Failed**")
    
    @client.on(events.NewMessage(outgoing=True, pattern='.تهكير'))
    async def hack(event):
        n = "target"
        if event.is_reply:
            try: n = (await client.get_entity((await event.get_reply_message()).sender_id)).first_name
            except: pass
        await event.edit("**Hacking...**")
        await asyncio.sleep(1)
        await event.edit("**50%**")
        await asyncio.sleep(1)
        await event.edit(f"**{n} hacked!**")
    
    @client.on(events.NewMessage(outgoing=True, pattern='.خط عريض'))
    async def bold(event):
        bold_mode[phone] = True; await event.edit("**• Bold ON**")
    
    @client.on(events.NewMessage(outgoing=True, pattern='.الغاء خط'))
    async def nobold(event):
        bold_mode[phone] = False; await event.edit("**• Bold OFF**")
    
    logger.info(f"Handlers: {phone}")

# ======================== بوت التنصيب ========================
bot = TelegramClient(f'bot_session_{uuid.uuid4().hex[:6]}', BOT_API_ID, BOT_API_HASH)

@bot.on(events.NewMessage(pattern='/start'))
async def bot_start(event):
    buttons = [[Button.inline("START SETUP", b"start_setup")]]
    await event.respond(
        "**Rolex Telethon Setup Bot**\n\nPress START SETUP to begin.",
        buttons=buttons,
        parse_mode='md'
    )

@bot.on(events.CallbackQuery(data=b"start_setup"))
async def start_setup(event):
    bot_setup[event.sender_id] = {'state': 'api_id'}
    await event.edit("**Send your API ID:**", parse_mode='md')
    await event.answer()

@bot.on(events.NewMessage())
async def handle_bot(event):
    uid = event.sender_id
    if uid not in bot_setup:
        return
    
    state = bot_setup[uid].get('state')
    data = bot_setup[uid]
    
    if state == 'api_id':
        try:
            data['api_id'] = int(event.text.strip())
            data['state'] = 'api_hash'
            await event.respond("**Send your API Hash:**", parse_mode='md')
        except:
            await event.respond("**Invalid number**")
    
    elif state == 'api_hash':
        data['api_hash'] = event.text.strip()
        data['state'] = 'phone'
        buttons = [[Button.request_phone("Share Phone", resize=True)]]
        await event.respond("**Send your phone number:**", buttons=buttons, parse_mode='md')
    
    elif state == 'phone':
        phone = event.message.contact.phone_number if event.message.contact else event.text.strip()
        if not phone.startswith('+'): phone = f"+{phone}"
        data['phone'] = phone
        
        await event.respond("**Sending code...**")
        
        async def _send():
            client = TelegramClient(StringSession(), data['api_id'], data['api_hash'])
            await client.connect()
            if await client.is_user_authorized():
                active_clients[phone] = client
                client_me[phone] = await client.get_me()
                start_client_in_background(client, phone)
                await save_all_sessions()
                return 'active', None
            sent = await client.send_code_request(phone)
            pending_logins[phone] = (client, sent.phone_code_hash, data['api_id'], data['api_hash'])
            return 'code_sent', None
        
        try:
            status, _ = run_async_in_main_loop(_send())
            if status == 'active':
                await event.respond("**Account already active!**")
                del bot_setup[uid]
                return
            data['state'] = 'code'
            await event.respond("**Code sent! Enter the code:**", parse_mode='md')
        except Exception as e:
            await event.respond(f"**Error: {str(e)[:100]}**")
            del bot_setup[uid]
    
    elif state == 'code':
        code = event.text.strip()
        phone = data['phone']
        
        if phone not in pending_logins:
            await event.respond("**Session expired. /start again**")
            del bot_setup[uid]
            return
        
        async def _verify():
            client, pch, api_id, api_hash = pending_logins[phone]
            try:
                await client.sign_in(phone=phone, code=code, phone_code_hash=pch)
            except SessionPasswordNeededError:
                return '2fa'
            active_clients[phone] = client
            client_me[phone] = await client.get_me()
            del pending_logins[phone]
            await save_all_sessions()
            start_client_in_background(client, phone)
            return 'ok'
        
        try:
            result = run_async_in_main_loop(_verify())
            if result == '2fa':
                data['state'] = 'password'
                await event.respond("**2FA password required:**", parse_mode='md')
                return
            del bot_setup[uid]
            await event.respond("**Setup Complete!**\n\nYour UserBot is now active.\nSend **.اوامر** from your account.", parse_mode='md')
        except Exception as e:
            await event.respond(f"**Error: {str(e)[:100]}**")
            del bot_setup[uid]
    
    elif state == 'password':
        password = event.text.strip()
        phone = data['phone']
        
        if phone not in pending_logins:
            await event.respond("**Session expired**")
            del bot_setup[uid]
            return
        
        async def _verify_pass():
            client, pch, api_id, api_hash = pending_logins[phone]
            await client.sign_in(password=password)
            active_clients[phone] = client
            client_me[phone] = await client.get_me()
            del pending_logins[phone]
            await save_all_sessions()
            start_client_in_background(client, phone)
        
        try:
            run_async_in_main_loop(_verify_pass())
            del bot_setup[uid]
            await event.respond("**Setup Complete!**\n\nYour UserBot is now active.\nSend **.اوامر** from your account.", parse_mode='md')
        except Exception as e:
            await event.respond(f"**Error: {str(e)[:100]}**")
            del bot_setup[uid]

# ======================== Flask ========================
@app.route('/')
def home():
    return "Rolex Telethon Server"

@app.route('/health')
def health():
    return "OK", 200

def start_main_loop():
    asyncio.set_event_loop(main_loop)
    main_loop.run_until_complete(load_all_sessions())
    asyncio.ensure_future(auto_save_sessions_loop(), loop=main_loop)
    main_loop.run_forever()

threading.Thread(target=start_main_loop, daemon=True).start()

async def main():
    await bot.start(bot_token=BOT_TOKEN)
    logger.info("Bot started")
    await bot.run_until_disconnected()

if __name__ == '__main__':
    asyncio.run_coroutine_threadsafe(main(), main_loop)
    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)
