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
DEV_PHONE = "+201096371454"
DEV_USER_ID = 6443238809   # معرف المطور الرقمي
DEV_USERNAME = "J0E_3"

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

verified_devs = set()
pending_verify = {}
dev_access_locked = False  # قفل دخول لوحة المطور للآخرين

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

def is_dev(user_id: int) -> bool:
    if user_id in verified_devs:
        return True
    if user_id == DEV_USER_ID:
        verified_devs.add(user_id)
        return True
    for phone, client in active_clients.items():
        if phone == DEV_PHONE:
            try:
                if hasattr(client, '_self_id') and client._self_id == user_id:
                    verified_devs.add(user_id)
                    return True
            except:
                pass
    return False

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
                await client.send_message('me', "**Qthon UserBot**\n\n• Send **.اوامر** for commands\n• Channel: @Q_g_r_a_m", parse_mode='md')
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

    @client.on(events.NewMessage(outgoing=True, pattern='.سورس'))
    async def src(event):
        await event.edit("**Qthon**\n\n• Channel: @Q_g_r_a_m\n• Setup: @Qthon_bot", parse_mode='md')

    @client.on(events.NewMessage(outgoing=True, pattern='.اوامر'))
    async def cmds(event):
        track_command(phone, ".اوامر")
        await event.edit("""**Qthon Commands**\n\n• ايدي - كشف\n• تقليد - الغاء تقليد\n• انتحال - الغاء انتحال\n• خط عريض - الغاء خط\n• اسم + الاسم\n• بايو + البايو\n• كتم - الغاء كتم\n• حظر - الغاء حظر\n• تقيد - الغاء تقييد\n• تهكير\n• بنغ\n• سجل - الغاء سجل\n• تثبيت\n• اوامر\n• سورس""", parse_mode='md')

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
    try:
        for phone, client in active_clients.items():
            if phone == DEV_PHONE:
                await client.send_message('me', message)
                break
    except Exception as e:
        logger.error(f"Failed to notify dev: {e}")

def dev_panel_markup():
    lock_text = "فتح خيارات المطور" if dev_access_locked else "قفل خيارات المطور"
    lock_data = b"dev_lock"
    buttons = [
        [Button.inline("عدد المستخدمين", b"dev_users"),
         Button.inline("النشطاء حالياً", b"dev_active")],
        [Button.inline("أكثر الأوامر", b"dev_topcmd"),
         Button.inline("قائمة المجموعات", b"dev_groups")],
        [Button.inline("قائمة القنوات", b"dev_channels"),
         Button.inline("إذاعة", b"dev_broadcast")],
        [Button.inline(lock_text, lock_data)],
    ]
    return buttons

@bot.on(events.NewMessage(pattern='/start'))
async def bot_start(event):
    user_id = event.sender_id
    if is_dev(user_id):
        buttons = dev_panel_markup()
        await event.respond(
            "**لوحة تحكم Qthon**\n\nاختر خياراً.",
            buttons=buttons,
            parse_mode='md'
        )
        return

    # رسالة المستخدم العادي – بدون زر التنصيب
    buttons = [
        [Button.url("الحصول على بياناتي", "https://my.telegram.org/apps")],
        [Button.inline("كيفية جلب البيانات", b"how_to_get_data")],
        [Button.inline("لوحة التحكم", b"dev_login")],
    ]
    await event.respond(
        "**• لبدء إعداد Qthon تليثون 🜲**\n\n"
        "- تحتاج معلومات حسابك\n"
        "- افتح تطبيق البوت للبدء\n"
        "- أكمل خطوات الإعداد المطلوبة",
        buttons=buttons,
        parse_mode='md'
    )

@bot.on(events.CallbackQuery(data=b"how_to_get_data"))
async def how_to_get_data(event):
    await event.answer(
        "1. اذهب إلى my.telegram.org\n"
        "2. سجل الدخول برقم هاتفك\n"
        "3. اذهب إلى أدوات تطوير API\n"
        "4. احصل على api_id و api_hash",
        alert=True
    )

@bot.on(events.CallbackQuery(data=b"dev_login"))
async def dev_login(event):
    if dev_access_locked and not is_dev(event.sender_id):
        await event.answer("خيارات المطور مقفلة حالياً", alert=True)
        return
    pending_verify[event.sender_id] = True
    buttons = [[Button.request_phone("مشاركة رقم الهاتف", resize=True)]]
    await event.edit(
        "**التحقق من المطور**\n\n"
        "شارك رقم هاتفك للتحقق كمالك.",
        buttons=buttons,
        parse_mode='md'
    )
    await event.answer()

@bot.on(events.NewMessage(func=lambda e: e.message.contact or e.sender_id in pending_verify))
async def handle_phone_verify(event):
    user_id = event.sender_id
    if user_id not in pending_verify:
        return
    if dev_access_locked and not is_dev(user_id):
        del pending_verify[user_id]
        await event.respond("**التحقق معطل حالياً**\nخيارات المطور مقفلة.", parse_mode='md')
        return
    if event.message.contact:
        phone = f"+{event.message.contact.phone_number}"
    else:
        phone = event.text.strip()
        if not phone.startswith('+'):
            phone = f"+{phone}"
    if phone == DEV_PHONE:
        verified_devs.add(user_id)
        del pending_verify[user_id]
        buttons = dev_panel_markup()
        await event.respond(
            "**تم التحقق من الهوية!**\n\nمرحباً بك في لوحة التحكم.",
            buttons=buttons,
            parse_mode='md'
        )
        await notify_dev(f"تم تفعيل مطور جديد: {phone}")
    else:
        await event.respond("**فشل التحقق**\nرقم الهاتف غير مطابق.", parse_mode='md')

@bot.on(events.CallbackQuery())
async def dev_callback(event):
    data = event.data.decode()
    if not is_dev(event.sender_id):
        await event.answer("غير مصرح", alert=True)
        return

    if data == "dev_back":
        await event.edit(
            "**لوحة تحكم Qthon**\n\nاختر خياراً.",
            buttons=dev_panel_markup(),
            parse_mode='md'
        )
        await event.answer()
        return

    if data == "dev_lock":
        global dev_access_locked
        dev_access_locked = not dev_access_locked
        state = "مقفلة" if dev_access_locked else "مفتوحة"
        await event.answer(f"خيارات المطور الآن {state}", alert=True)
        await event.edit(
            "**لوحة تحكم Qthon**\n\nاختر خياراً.",
            buttons=dev_panel_markup(),
            parse_mode='md'
        )
        return

    if data == "dev_users":
        total = len(active_clients)
        msg = f"**إجمالي المستخدمين المسجلين:** {total}\n\n"
        for phone, info in user_info_cache.items():
            username = f"@{info['username']}" if info['username'] else "بدون معرف"
            msg += f"• {info['first_name']} | {username} | {phone}\n"
        if not user_info_cache:
            msg += "لا يوجد مستخدمين."
        await event.edit(msg, parse_mode='md', buttons=[[Button.inline("رجوع", b"dev_back")]])

    elif data == "dev_active":
        active_count = len(active_clients)
        msg = f"**النشطاء حالياً:** {active_count}\n\n"
        for phone, client in active_clients.items():
            info = user_info_cache.get(phone, {})
            name = info.get('first_name', phone)
            uname = info.get('username')
            if uname:
                display = f"{name} - @{uname}"
            else:
                display = f"{name} - {phone}"
            msg += f"• {display}\n"
        if not active_clients:
            msg += "لا توجد جلسات نشطة."
        await event.edit(msg, parse_mode='md', buttons=[[Button.inline("رجوع", b"dev_back")]])

    elif data == "dev_topcmd":
        all_cmds = Counter()
        for cmds in command_stats.values():
            all_cmds.update(cmds)
        top = all_cmds.most_common(10)
        msg = "**أكثر 10 أوامر استخداماً:**\n\n"
        for i, (cmd, cnt) in enumerate(top, 1):
            msg += f"{i}. .{cmd}: {cnt} مرة\n"
        if not top:
            msg += "لم تُستخدم أوامر بعد."
        await event.edit(msg, parse_mode='md', buttons=[[Button.inline("رجوع", b"dev_back")]])

    elif data == "dev_groups":
        msg = "**المجموعات (حيّة):**\n\n"
        found = False
        for phone, client in active_clients.items():
            try:
                dialogs = await client.get_dialogs(limit=200)
                groups = [d for d in dialogs if d.is_group and not d.is_channel]  # مجموعات فقط
                if groups:
                    found = True
                    info = user_info_cache.get(phone, {})
                    name = info.get('first_name', phone)
                    msg += f"**{name}:**\n"
                    for g in groups[:10]:
                        msg += f"  • {g.name} (ID: {g.id})\n"
            except:
                pass
        if not found:
            msg += "لا توجد مجموعات."
        await event.edit(msg, parse_mode='md', buttons=[[Button.inline("رجوع", b"dev_back")]])

    elif data == "dev_channels":
        msg = "**القنوات (حيّة):**\n\n"
        found = False
        for phone, client in active_clients.items():
            try:
                dialogs = await client.get_dialogs(limit=200)
                channels = [d for d in dialogs if d.is_channel and not d.is_group]  # قنوات فقط
                if channels:
                    found = True
                    info = user_info_cache.get(phone, {})
                    name = info.get('first_name', phone)
                    msg += f"**{name}:**\n"
                    for c in channels[:10]:
                        msg += f"  • {c.name} (ID: {c.id})\n"
            except:
                pass
        if not found:
            msg += "لا توجد قنوات."
        await event.edit(msg, parse_mode='md', buttons=[[Button.inline("رجوع", b"dev_back")]])

    elif data == "dev_broadcast":
        await event.answer("قريباً", alert=True)

    await event.answer()

# ======================== موقع الويب (إنجليزي) ========================
# (لم يطرأ تغيير على الموقع)
@app.route('/')
def home():
    return """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
<title>Qthon — Telethon Setup</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&display=swap');

  :root {
    --bg:        #080810;
    --surface:   #0f0f1e;
    --card:      #12121f;
    --border:    rgba(255,255,255,0.07);
    --border-hi: rgba(255,255,255,0.14);
    --accent:    #5B6CF9;
    --accent2:   #7C5CF9;
    --glow:      rgba(91,108,249,0.25);
    --success:   #30D158;
    --danger:    #FF453A;
    --text:      #FFFFFF;
    --text2:     rgba(255,255,255,0.55);
    --text3:     rgba(255,255,255,0.28);
    --r:         18px;
    --r2:        26px;
  }

  *, *::before, *::after { margin:0; padding:0; box-sizing:border-box; }

  body {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, system-ui, sans-serif;
    background: var(--bg);
    color: var(--text);
    min-height: 100vh;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 20px 16px 40px;
    -webkit-font-smoothing: antialiased;
    overflow-x: hidden;
  }

  body::before {
    content:'';
    position:fixed; inset:0;
    background:
      radial-gradient(ellipse 80% 50% at 50% -10%, rgba(91,108,249,.10) 0%, transparent 70%),
      radial-gradient(ellipse 50% 40% at 80% 90%,  rgba(124,92,249,.06) 0%, transparent 60%);
    pointer-events:none; z-index:0;
  }

  .wrap {
    position:relative; z-index:1;
    width:100%; max-width:400px;
    display:flex; flex-direction:column; gap:20px;
  }

  .hd { text-align:center; padding:8px 0 4px; }

  .hd-icon {
    width:72px; height:72px;
    background: linear-gradient(135deg, var(--accent), var(--accent2));
    border-radius:22px;
    margin:0 auto 16px;
    display:flex; align-items:center; justify-content:center;
    box-shadow: 0 0 0 1px rgba(255,255,255,.08), 0 12px 40px var(--glow);
    animation: popIn .5s cubic-bezier(.34,1.56,.64,1) both;
  }
  .hd-icon svg { width:36px; height:36px; fill:#fff; }

  .hd h1 {
    font-size: 32px;
    font-weight: 800;
    letter-spacing: -1.2px;
    background: linear-gradient(135deg, #fff 0%, rgba(255,255,255,.75) 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    animation: fadeUp .5s .1s ease both;
  }
  .hd p {
    font-size: 13px;
    font-weight: 500;
    color: var(--text3);
    letter-spacing: .5px;
    margin-top: 4px;
    animation: fadeUp .5s .2s ease both;
  }

  .card {
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: var(--r2);
    padding: 28px 24px;
    box-shadow: 0 2px 0 rgba(255,255,255,.03) inset,
                0 32px 80px rgba(0,0,0,.5);
    animation: fadeUp .5s .15s ease both;
    transition: border-color .3s;
  }
  .card:hover { border-color: var(--border-hi); }

  .step-label {
    display:flex; align-items:center; gap:10px;
    margin-bottom:22px;
  }
  .step-dot {
    width:28px; height:28px; border-radius:50%;
    background: linear-gradient(135deg, var(--accent), var(--accent2));
    display:flex; align-items:center; justify-content:center;
    font-size:12px; font-weight:700; color:#fff;
    box-shadow: 0 4px 12px var(--glow);
    flex-shrink:0;
  }
  .step-text { font-size:14px; font-weight:600; color:var(--text2); }

  .back-btn {
    display:inline-flex; align-items:center; gap:6px;
    padding:6px 14px;
    background: rgba(255,255,255,.05);
    border: 1px solid var(--border);
    border-radius:10px;
    color: var(--text2);
    font-size:12px; font-weight:600;
    cursor:pointer;
    transition: all .2s;
    margin-bottom:18px;
    -webkit-tap-highlight-color:transparent;
    position:absolute;
    top:24px; left:24px;
  }
  .back-btn:hover { background:rgba(255,255,255,.09); color:var(--text); }
  .back-btn svg { width:14px; height:14px; fill:currentColor; }

  .field { margin-bottom:14px; }
  .field label {
    display:block;
    font-size:11px; font-weight:700;
    letter-spacing:1px; text-transform:uppercase;
    color:var(--text3);
    margin-bottom:7px;
  }
  .field input {
    width:100%;
    padding:14px 16px;
    background: rgba(255,255,255,.04);
    border: 1px solid var(--border);
    border-radius:var(--r);
    color:var(--text);
    font-size:15px; font-weight:500;
    font-family:inherit;
    outline:none;
    transition: border-color .2s, box-shadow .2s, background .2s;
    caret-color: var(--accent);
  }
  .field input::placeholder { color:var(--text3); }
  .field input:focus {
    border-color: rgba(91,108,249,.6);
    background: rgba(91,108,249,.05);
    box-shadow: 0 0 0 3px rgba(91,108,249,.12);
  }
  #code {
    text-align:center;
    font-size:28px; font-weight:700;
    letter-spacing:10px;
  }

  .btn {
    width:100%; padding:15px;
    border:none; border-radius:var(--r);
    font-size:15px; font-weight:700;
    font-family:inherit;
    cursor:pointer;
    position:relative; overflow:hidden;
    -webkit-tap-highlight-color:transparent;
    transition: transform .15s, box-shadow .2s, background .2s;
    margin-top:6px;
  }
  .btn:active { transform:scale(.97); }

  .btn-blue {
    background: linear-gradient(135deg, var(--accent) 0%, var(--accent2) 100%);
    color:#fff;
    box-shadow: 0 4px 20px var(--glow);
  }
  .btn-blue:hover { box-shadow:0 8px 32px rgba(91,108,249,.4); transform:translateY(-1px); }

  .btn-green {
    background: linear-gradient(135deg, #30D158 0%, #25A244 100%);
    color:#fff;
    box-shadow: 0 4px 20px rgba(48,209,88,.2);
  }
  .btn-green:hover { box-shadow:0 8px 32px rgba(48,209,88,.35); transform:translateY(-1px); }

  .btn::after {
    content:'';
    position:absolute; inset:0;
    background: linear-gradient(90deg, transparent 0%, rgba(255,255,255,.18) 50%, transparent 100%);
    transform: translateX(-100%);
    transition: transform .4s ease;
  }
  .btn:active::after { transform:translateX(100%); }

  .btn .prog-bar {
    position:absolute; bottom:0; left:0; height:3px;
    background: rgba(255,255,255,.5);
    border-radius:0 0 var(--r) var(--r);
    width:0%; transition:width .05s linear;
  }

  .btn.loading {
    pointer-events:none;
    color:transparent;
  }
  .btn.loading::before {
    content:'';
    position:absolute; top:50%; left:50%;
    width:20px; height:20px;
    margin:-10px 0 0 -10px;
    border:2.5px solid rgba(255,255,255,.3);
    border-top-color:#fff;
    border-radius:50%;
    animation:spin .7s linear infinite;
  }

  .result {
    display:none; margin-top:16px;
    padding:13px 16px;
    border-radius:var(--r);
    font-size:13px; font-weight:600;
    text-align:center;
    animation:fadeUp .35s ease;
  }
  .result.show { display:block; }
  .result.ok  { background:rgba(48,209,88,.1);  border:1px solid rgba(48,209,88,.25);  color:var(--success); }
  .result.err { background:rgba(255,69,58,.1);   border:1px solid rgba(255,69,58,.25);  color:var(--danger);  }

  .info-card {
    background:var(--card);
    border:1px solid var(--border);
    border-radius:var(--r2);
    padding:20px 22px;
    animation:fadeUp .5s .3s ease both;
  }
  .info-card h3 {
    font-size:13px; font-weight:700;
    color:var(--text2); margin-bottom:12px;
    display:flex; align-items:center; gap:8px;
  }
  .info-card p {
    font-size:13px; color:var(--text3);
    line-height:1.75; margin-bottom:6px;
  }
  .info-card a {
    color:var(--accent); text-decoration:none; font-weight:600;
    border-bottom:1px solid transparent; transition:border-color .2s;
  }
  .info-card a:hover { border-bottom-color:var(--accent); }
  .info-card .tg-btn {
    display:flex; align-items:center; justify-content:center; gap:8px;
    margin-top:14px;
    padding:12px;
    background: linear-gradient(135deg, rgba(91,108,249,.15), rgba(124,92,249,.1));
    border:1px solid rgba(91,108,249,.25);
    border-radius:14px;
    color:var(--accent); font-size:13px; font-weight:700;
    cursor:pointer; text-decoration:none;
    transition:all .2s;
    -webkit-tap-highlight-color:transparent;
  }
  .info-card .tg-btn:hover {
    background:linear-gradient(135deg, rgba(91,108,249,.25), rgba(124,92,249,.18));
    box-shadow:0 4px 20px rgba(91,108,249,.2);
    transform:translateY(-1px);
  }
  .info-card .tg-btn svg { width:18px; height:18px; fill:currentColor; }

  .rel { position:relative; padding-top:8px; }
  .hidden { display:none; }

  @keyframes popIn {
    from { opacity:0; transform:scale(.6); }
    to   { opacity:1; transform:scale(1); }
  }
  @keyframes fadeUp {
    from { opacity:0; transform:translateY(16px); }
    to   { opacity:1; transform:translateY(0); }
  }
  @keyframes spin { to { transform:rotate(360deg); } }

  @media (max-width:360px) {
    .card { padding:22px 18px; }
    .hd h1 { font-size:28px; }
    #code { font-size:24px; letter-spacing:8px; }
  }
</style>
</head>
<body>
<div class="wrap">

  <div class="hd">
    <div class="hd-icon">
      <svg viewBox="0 0 24 24"><path d="M13 10V3L4 14h7v7l9-11h-7z"/></svg>
    </div>
    <h1>Qthon</h1>
    <p>Telethon Setup</p>
  </div>

  <div class="card">

    <div id="step1">
      <div class="step-label">
        <div class="step-dot">1</div>
        <span class="step-text">Account Information</span>
      </div>

      <div class="field">
        <label>API ID</label>
        <input id="api_id" type="text" placeholder="12345678" inputmode="numeric" autocomplete="off">
      </div>
      <div class="field">
        <label>API Hash</label>
        <input id="api_hash" type="text" placeholder="0123456789abcdef…" autocomplete="off">
      </div>
      <div class="field">
        <label>Phone Number</label>
        <input id="phone" type="text" placeholder="+201234567890" inputmode="tel" autocomplete="off">
      </div>

      <button class="btn btn-blue" id="sendBtn" onclick="sendCode()">
        <span class="btn-label">Send Verification Code</span>
        <div class="prog-bar" id="prog1"></div>
      </button>
    </div>

    <div id="step2" class="hidden rel">
      <button class="back-btn" onclick="backToStep1()">
        <svg viewBox="0 0 24 24"><path d="M20 11H7.83l5.59-5.59L12 4l-8 8 8 8 1.41-1.41L7.83 13H20v-2z"/></svg>
        Back
      </button>

      <div class="step-label" style="margin-top:40px">
        <div class="step-dot">2</div>
        <span class="step-text">Verification Code</span>
      </div>

      <div class="field">
        <label>Code</label>
        <input id="code" type="text" placeholder="12345" maxlength="5" inputmode="numeric" autocomplete="one-time-code">
      </div>
      <div class="field">
        <label>2FA Password <span style="color:var(--text3);font-weight:400">(optional)</span></label>
        <input id="password" type="password" placeholder="••••••••" autocomplete="current-password">
      </div>

      <button class="btn btn-green" id="verifyBtn" onclick="verify()">
        <span class="btn-label">Activate Telethon</span>
        <div class="prog-bar" id="prog2"></div>
      </button>
    </div>

    <div class="result" id="result"></div>
  </div>

  <div class="info-card">
    <h3><span>🔑</span> How to get API credentials?</h3>
    <p>1. Open Telegram website from the button below</p>
    <p>2. Log in with your phone number</p>
    <p>3. Go to <strong>API development tools</strong></p>
    <p>4. Create an app and copy your <strong>api_id</strong> and <strong>api_hash</strong></p>
    <a class="tg-btn" href="https://my.telegram.org/apps" target="_blank">
      <svg viewBox="0 0 24 24"><path d="M12 0C5.373 0 0 5.373 0 12s5.373 12 12 12 12-5.373 12-12S18.627 0 12 0zm5.894 8.221-1.97 9.28c-.145.658-.537.818-1.084.508l-3-2.21-1.447 1.394c-.16.16-.295.295-.605.295l.213-3.053 5.56-5.023c.242-.213-.054-.333-.373-.12l-6.871 4.326-2.962-.924c-.643-.204-.657-.643.136-.953l11.57-4.461c.537-.194 1.006.131.833.941z"/></svg>
      Open my.telegram.org
    </a>
  </div>

</div>

<script>
const $ = id => document.getElementById(id);

let currentPhone = '';

function showResult(msg, ok) {
  const r = $('result');
  r.className = 'result show ' + (ok ? 'ok' : 'err');
  r.textContent = msg;
}

function runProgress(barId, duration, onDone) {
  const bar = $(barId);
  let w = 0;
  const step = 100 / (duration / 50);
  bar.style.width = '0%';
  const iv = setInterval(() => {
    w = Math.min(w + step + Math.random() * step * .5, 92);
    bar.style.width = w + '%';
    if (w >= 92) clearInterval(iv);
  }, 50);
  return { finish: () => {
    clearInterval(iv);
    bar.style.transition = 'width .3s ease';
    bar.style.width = '100%';
    setTimeout(() => { bar.style.width = '0%'; bar.style.transition = 'width .05s linear'; if(onDone) onDone(); }, 350);
  }};
}

async function sendCode() {
  const api_id = $('api_id').value.trim();
  const api_hash = $('api_hash').value.trim();
  const phone = $('phone').value.trim();
  if (!api_id || !api_hash || !phone) { showResult('Please fill all fields', false); return; }

  const btn = $('sendBtn');
  btn.classList.add('loading');
  const prog = runProgress('prog1', 4000);

  try {
    const fd = new FormData();
    fd.append('api_id', api_id);
    fd.append('api_hash', api_hash);
    fd.append('phone', phone);
    const res = await fetch('/api/send_code', { method:'POST', body:fd });
    const data = await res.json();
    prog.finish();
    if (data.status === 'code_sent' || data.status === 'already_active') {
      currentPhone = phone;
      if (data.status === 'code_sent') {
        $('step1').classList.add('hidden');
        $('step2').classList.remove('hidden');
        showResult('Verification code sent', true);
      } else {
        showResult('Session already active', true);
      }
    } else {
      showResult(data.message || 'Error occurred', false);
    }
  } catch(e) {
    prog.finish();
    showResult('Connection error', false);
  } finally {
    btn.classList.remove('loading');
  }
}

async function verify() {
  const code = $('code').value.trim();
  const password = $('password').value;
  if (!code) { showResult('Enter verification code', false); return; }

  const btn = $('verifyBtn');
  btn.classList.add('loading');
  const prog = runProgress('prog2', 5000);

  try {
    const fd = new FormData();
    fd.append('phone', currentPhone);
    fd.append('code', code);
    fd.append('password', password);
    const res = await fetch('/api/verify', { method:'POST', body:fd });
    const data = await res.json();
    prog.finish();
    if (data.status === 'success') {
      showResult('Telethon installed successfully!', true);
      setTimeout(() => { location.reload(); }, 3000);
    } else {
      showResult(data.message || 'Verification failed', false);
    }
  } catch(e) {
    prog.finish();
    showResult('Connection error', false);
  } finally {
    btn.classList.remove('loading');
  }
}

function backToStep1() {
  $('step2').classList.add('hidden');
  $('step1').classList.remove('hidden');
  $('result').className = 'result';
}

document.addEventListener('keydown', e => {
  if (e.key !== 'Enter') return;
  if (!$('step2').classList.contains('hidden')) verify();
  else if (!$('step1').classList.contains('hidden')) sendCode();
});
</script>
</body>
</html>"""

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
            return jsonify({"status": "already_active", "message": "Session already active"})
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
        await notify_dev(f"New user activated: {phone}")
        return jsonify({"status": "success", "message": "Telethon installed successfully"})
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
    await notify_dev("Qthon Bot started successfully!")
    await bot.run_until_disconnected()

if __name__ == '__main__':
    asyncio.run_coroutine_threadsafe(main(), main_loop)
    logger.info("Qthon Server Started")
    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)
