import asyncio
import threading
import logging
import time
import random
import json
import os
import sys
import requests
import io
import uuid
from collections import Counter
from datetime import datetime, timedelta

from flask import Flask
from telethon import TelegramClient, events
from telethon.errors import (
    SessionPasswordNeededError, FloodWaitError, PhoneCodeInvalidError,
    PhoneCodeExpiredError, PhoneNumberInvalidError
)
from telethon.sessions import StringSession
from telethon.tl.functions.account import UpdateProfileRequest
from telethon.tl.functions.contacts import BlockRequest, UnblockRequest, ImportContactsRequest
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.tl.functions.messages import (
    ToggleDialogPinRequest, GetHistoryRequest, GetDialogsRequest,
    EditChatDefaultBannedRightsRequest
)
from telethon.tl.functions.phone import RequestCallRequest
from telethon.tl.types import (
    InputPeerChannel, InputPeerUser, InputPhoneContact,
    ChatBannedRights, PhoneCallProtocol
)
from telethon.tl.functions.photos import UploadProfilePhotoRequest, DeletePhotosRequest
from telethon.tl.functions.users import GetFullUserRequest

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

# ======================== الإعدادات الأساسية ========================
API_ID = 2040
API_HASH = 'b18441a1ff607e10a989891a5462e627'
BOT_TOKEN = '8887748662:AAFgLMUO2eXpYzityDj35-IDTLywtdO8S8Q'

DATA_DIR = '/data' if os.path.exists('/data') else '.'
os.makedirs(DATA_DIR, exist_ok=True)
SESSION_FILE = os.path.join(DATA_DIR, 'active_sessions.json')
BANK_FILE = os.path.join(DATA_DIR, 'bank.json')
TEMP_DIR = os.path.join(DATA_DIR, 'temp')
os.makedirs(TEMP_DIR, exist_ok=True)

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
    """تشغيل Flask في الخلفية عشان Railway يلاقي port مفتوح"""
    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)

# ======================== المتغيرات العامة ========================
# جلسة بوت فريدة كل مرة (عشان نضمن عدم وجود تعارض)
bot = TelegramClient(f'bot_session_{uuid.uuid4().hex[:6]}', API_ID, API_HASH)

active_clients = {}
client_me = {}
pending_logins = {}

muted_users = {}
taqleed_users = {}
banned_users = {}
bold_mode = {}
disabled_users = {}
ent7al_users = {}
ent7al_original = {}
command_stats = {}
user_info_cache = {}

bank_data = {}
bank_counter = 1000

# ======================== إطارات الأنيميشن ========================
LAUGH_FRAMES = [
    "😂🤣😭😹", "🤣😂😭😹", "🤣😭😂😹", "😭🤣😂😹",
    "😭🤣😹😂", "😭😹🤣😂", "😹😭🤣😂", "😹😂🤣😭",
    "😂😹🤣😭", "😂🤣😹😭", "🤣😂😹😭", "🤣😹😂😭",
    "😹🤣😂😭", "😹🤣😭😂", "😭😹🤣😂", "😭🤣😹😂"
]

CLOUD_FRAMES = [
    "☁️⛅🌤️☁️", "⛅☁️🌤️☁️", "⛅🌤️☁️☁️", "🌤️⛅☁️☁️",
    "🌤️☁️⛅☁️", "☁️🌤️⛅☁️", "☁️🌤️☁️⛅", "☁️☁️🌤️⛅",
    "⛅☁️☁️🌤️", "⛅☁️🌤️☁️", "🌤️☁️⛅☁️", "🌤️⛅☁️☁️",
    "☁️⛅☁️🌤️", "☁️⛅🌤️☁️", "⛅🌤️☁️☁️", "🌤️☁️☁️⛅"
]

HEART_FRAMES = [
    "❤️🧡💛💚", "🧡❤️💛💚", "🧡💛❤️💚", "💛🧡❤️💚",
    "💛🧡💚❤️", "💛💚🧡❤️", "💚💛🧡❤️", "💚❤️🧡💛",
    "❤️💚🧡💛", "❤️🧡💚💛", "🧡❤️💚💛", "🧡💚❤️💛",
    "💚🧡❤️💛", "💚🧡💛❤️", "💛💚🧡❤️", "💛🧡💚❤️"
]

ROSE_FRAMES = [
    "🌹🥀🌷🌸", "🥀🌹🌷🌸", "🥀🌷🌹🌸", "🌷🥀🌹🌸",
    "🌷🥀🌸🌹", "🌷🌸🥀🌹", "🌸🌷🥀🌹", "🌸🌹🌷🥀",
    "🌹🌸🌷🥀", "🌹🌸🥀🌷", "🌹🥀🌸🌷", "🥀🌹🌸🌷",
    "🥀🌸🌹🌷", "🌸🥀🌹🌷", "🌸🥀🌷🌹", "🌷🌸🥀🌹"
]

X_FRAMES = ["❌", "❎", "✖️", "❌❌", "❎❎", "✖️✖️", "❌❎❌", "❎❌❎", "✖️❌✖️", "❌✖️❌", "❌❎✖️❌", "❎❌✖️❎", "✖️❎❌✖️"]
O_FRAMES = ["⭕", "⚪", "🔴", "🟢", "🔵", "⭕⭕", "⚪⚪", "🔴🔴", "⭕⚪🔴", "⚪🔴🟢", "🔴🟢🔵"]

# ======================== دوال عامة ========================
def track_command(phone: str, command: str):
    if phone not in command_stats:
        command_stats[phone] = Counter()
    command_stats[phone][command] += 1

def is_dev(phone: str) -> bool:
    return phone == "+201096371454"

async def get_user_name(client, user_id):
    try:
        user = await client.get_entity(user_id)
        return user.first_name or "User"
    except:
        return "User"

async def animate_emojis(event, frames, speed=0.4):
    for frame in frames:
        await event.edit(f"**{frame}**")
        await asyncio.sleep(speed)

# ======================== Gemini AI ========================
GEMINI_API_KEY = "AQ.Ab8RN6IJ52RfamXKX6nNJOglTwDarnQyUIh9uzITyqK5iqwm7w"

def ask_gemini(question: str) -> str:
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
        headers = {'Content-Type': 'application/json'}
        data = {"contents": [{"parts": [{"text": question}]}]}
        response = requests.post(url, headers=headers, json=data, timeout=30)
        if response.status_code == 200:
            result = response.json()
            return result['candidates'][0]['content']['parts'][0]['text'][:2000]
    except:
        pass
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
        response = requests.post(url, headers={'Content-Type': 'application/json'}, json={"contents": [{"parts": [{"text": question}]}]}, timeout=30)
        if response.status_code == 200:
            result = response.json()
            return result['candidates'][0]['content']['parts'][0]['text'][:2000]
    except:
        pass
    return None

# ======================== نظام البنك ========================
def load_bank():
    global bank_data, bank_counter
    try:
        if os.path.exists(BANK_FILE):
            with open(BANK_FILE, 'r') as f:
                data = json.load(f)
                bank_data = data.get('accounts', {})
                bank_counter = data.get('counter', 1000)
    except:
        bank_data = {}
        bank_counter = 1000

def save_bank():
    try:
        with open(BANK_FILE, 'w') as f:
            json.dump({'accounts': bank_data, 'counter': bank_counter}, f)
    except:
        pass

load_bank()

def get_bank_account(phone: str):
    return bank_data.get(phone)

def create_bank_account(phone: str, bank_name: str):
    global bank_counter
    bank_counter += 1
    account = {
        "phone": phone, "bank": bank_name,
        "account_number": str(bank_counter), "balance": 500,
        "fame": 0, "title": "مبتدئ",
        "last_gift": ""
    }
    bank_data[phone] = account
    save_bank()
    return account

def update_fame_title(acc):
    fame = acc['fame']
    if fame >= 500: acc['title'] = "اسطورة"
    elif fame >= 200: acc['title'] = "مشهور"
    elif fame >= 100: acc['title'] = "محبوب"
    elif fame >= 50: acc['title'] = "معروف"
    elif fame >= 20: acc['title'] = "نشيط"
    else: acc['title'] = "مبتدئ"

# ======================== إدارة الجلسات ========================
async def save_all_sessions():
    sessions = {}
    for phone, client in active_clients.items():
        if client.is_connected():
            sessions[phone] = client.session.save()
    with open(SESSION_FILE, 'w') as f:
        json.dump(sessions, f)

async def load_all_sessions():
    if not os.path.exists(SESSION_FILE):
        return
    with open(SESSION_FILE, 'r') as f:
        sessions = json.load(f)
    for phone, session_str in sessions.items():
        try:
            client = TelegramClient(StringSession(session_str), API_ID, API_HASH)
            await client.connect()
            if await client.is_user_authorized():
                active_clients[phone] = client
                client_me[phone] = await client.get_me()
                asyncio.ensure_future(run_userbot(client, phone))
                logger.info(f"✅ تم تحميل حساب: {phone}")
        except Exception as e:
            logger.error(f"❌ فشل تحميل حساب {phone}: {e}")

# ======================== وظائف الانتحال ========================
async def get_user_info_full(client, user_id):
    try:
        user = await client.get_entity(user_id)
        name = user.first_name or "غير معروف"
        if user.last_name:
            name += f" {user.last_name}"
        username = f"@{user.username}" if user.username else "لا يوجد"
        bio = ""
        try:
            full = await client(GetFullUserRequest(user_id))
            if full.full_user.about:
                bio = full.full_user.about
        except:
            pass
        return {
            'name': name,
            'first_name': user.first_name or '',
            'last_name': user.last_name or '',
            'username': username,
            'bio': bio,
            'id': user.id
        }
    except:
        return None

async def change_profile_photo(client, user_id, phone):
    try:
        old_photos = await client.get_profile_photos('me', limit=10)
        for p in old_photos:
            try:
                await client(DeletePhotosRequest(id=[p]))
                await asyncio.sleep(0.5)
            except:
                pass
        if old_photos:
            await asyncio.sleep(2)

        photo_bytes = await client.download_profile_photo(user_id, file=bytes)
        if not photo_bytes:
            return False

        for attempt in range(2):
            try:
                uploaded = await client.upload_file(photo_bytes, file_name="photo.jpg")
                await client(UploadProfilePhotoRequest(file=uploaded))
                await asyncio.sleep(2)
                me = await client.get_me()
                if me.photo:
                    return True
                if PIL_AVAILABLE and attempt == 0:
                    img = Image.open(io.BytesIO(photo_bytes))
                    if img.mode != 'RGB':
                        img = img.convert('RGB')
                    buf = io.BytesIO()
                    img.save(buf, format='JPEG', quality=85)
                    photo_bytes = buf.getvalue()
                else:
                    break
            except FloodWaitError as e:
                await asyncio.sleep(e.seconds)
            except Exception as e:
                logger.error(f"Upload error: {e}")
                break
        return False
    except Exception as e:
        logger.error(f"Photo change fatal error: {e}")
        return False

# ======================== تشغيل userbot ========================
async def run_userbot(client, phone):
    try:
        await setup_handlers(client, phone)
        me = await client.get_me()
        logger.info(f"🤖 UserBot نشط: {me.first_name} ({phone})")
        await client.run_until_disconnected()
    except Exception as e:
        logger.error(f"❌ خطأ في حساب {phone}: {e}")
    finally:
        if phone in active_clients:
            del active_clients[phone]

async def setup_handlers(client, phone):
    if phone not in muted_users:
        muted_users[phone] = {}
        taqleed_users[phone] = {}
        banned_users[phone] = {}
        bold_mode[phone] = False
        disabled_users[phone] = False
        ent7al_users[phone] = False
        ent7al_original[phone] = {}
        command_stats[phone] = Counter()

    @client.on(events.NewMessage(incoming=True))
    async def auto_mute(event):
        if event.is_private and event.sender_id in muted_users.get(phone, {}):
            try:
                await event.delete()
            except:
                pass

    @client.on(events.NewMessage(incoming=True))
    async def auto_taqleed(event):
        sender_id = event.sender_id
        if sender_id and sender_id in taqleed_users.get(phone, {}):
            if event.text and not event.text.startswith('.'):
                await asyncio.sleep(0.3)
                try:
                    await event.reply(event.text)
                except:
                    pass

    @client.on(events.NewMessage(outgoing=True))
    async def auto_bold(event):
        if bold_mode.get(phone, False) and event.text and not event.text.startswith('.'):
            try:
                await event.edit(f"**{event.text}**")
            except:
                pass

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.سورس$'))
    async def src(event):
        await event.edit("**⚜️ Rolex Telethon**\n\n• المطور: ƚᥲɦ᥆ᥙꪀ\n• قناة السورس: @Q_g_r_a_m\n• للأوامر: .اوامر", parse_mode='md')

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.اوامر$'))
    async def cmds(event):
        track_command(phone, ".اوامر")
        await event.edit("""**اوامر السورس 𔓕**
ايدي ا
تقليد غ تقليد
خط غ خط
اسم + الاسم
بايو + البايو
ث غ ث
اضافة + عدد
عدد
حذف + عدد
رن
قفل فتح
كتم غ كتم
حظر غ حظر
تقيد غ تقييد
تهكير
انتحال الغاء انتحال
ذكاء + سؤال
بوت + سؤال
صراحة
كت
ضحك غيوم قلوب ورود
غباء
تحويل + رقم
رفع شحات رفع حمار رفع غبي رفع سباك رفع مالك رفع ادمن
حسابي انشاء بنك + اسم
فلوسي توب فلوس
هدية قمار + مبلغ
نرد عملة
سرقة + @يوزر
توب شهرة شهرتي
شراء لقب + اسم
اكس او
اوامر سورس""", parse_mode='md')

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.(ايدي|ا)$'))
    async def id_cmd(event):
        track_command(phone, ".ايدي")
        await event.delete()
        user = None
        if event.is_reply:
            user = await client.get_entity((await event.get_reply_message()).sender_id)
        elif event.is_group:
            user = await client.get_entity(event.sender_id)
        else:
            user = await client.get_entity(event.chat_id)
        if not user: return
        lines = [f"ꪀᥲꪔꫀ {user.first_name or ''} {user.last_name or ''}".strip()]
        if user.username: lines.append(f"ᥙ᥉ꫀɾ @{user.username}")
        try:
            full = await client.get_entity(user.id)
            if hasattr(full, 'about') and full.about: lines.append(f"ᑲᎥ᥆ {full.about[:50]}")
        except: pass
        lines.append(f"Ꭵძ {user.id}")
        await client.send_message(event.chat_id, "\n".join(lines))

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.تقليد$'))
    async def taq(event):
        target = None
        if event.is_reply: target = (await event.get_reply_message()).sender_id
        elif event.is_private: target = event.chat_id
        if target:
            taqleed_users[phone][target] = True
            await event.edit("**• يتم التقليد**")

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.غ تقليد$'))
    async def notaq(event):
        target = None
        if event.is_reply: target = (await event.get_reply_message()).sender_id
        elif event.is_private: target = event.chat_id
        if target and target in taqleed_users.get(phone, {}): del taqleed_users[phone][target]
        await event.edit("**• تم فك التقليد**")

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.خط$'))
    async def bold(event):
        bold_mode[phone] = True
        await event.edit("**• تم تفعيل الخط العريض**")

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.غ خط$'))
    async def nobold(event):
        bold_mode[phone] = False
        await event.edit("**• تم الغاء الخط العريض**")

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.اسم (.+)'))
    async def name(event):
        try:
            await client(UpdateProfileRequest(first_name=event.pattern_match.group(1).strip(), last_name=''))
            await event.edit("**• تم تغيير الاسم**")
        except: await event.edit("**• فشل**")

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.بايو (.+)'))
    async def bio(event):
        try:
            await client(UpdateProfileRequest(about=event.pattern_match.group(1).strip()))
            await event.edit("**• تم تغيير البايو**")
        except: await event.edit("**• فشل**")

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.ث$'))
    async def pin_msg(event):
        try:
            if event.is_reply: await (await event.get_reply_message()).pin(); await event.edit("**• تم التثبيت**")
            else: await client(ToggleDialogPinRequest(peer=event.input_chat, pinned=True)); await event.edit("**• تم تثبيت المحادثة**")
        except: await event.edit("**• فشل**")

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.غ ث$'))
    async def unpin_msg(event):
        try:
            if event.is_reply: await (await event.get_reply_message()).unpin(); await event.edit("**• تم الغاء التثبيت**")
            else: await client(ToggleDialogPinRequest(peer=event.input_chat, pinned=False)); await event.edit("**• تم الغاء تثبيت المحادثة**")
        except: await event.edit("**• فشل**")

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.اضافة (\d+)'))
    async def add_contacts(event):
        count = int(event.pattern_match.group(1))
        await event.edit(f"**• جاري اضافة {count} جهة**")
        added = 0
        try:
            dialogs = await client(GetDialogsRequest(offset_date=None, offset_id=0, offset_peer=InputPeerUser(0, 0), limit=count, hash=0))
            for user in dialogs.users[:count]:
                try:
                    if hasattr(user, 'phone') and user.phone and not user.bot:
                        contact = InputPhoneContact(client_id=0, phone=user.phone, first_name=user.first_name or "User", last_name=user.last_name or "")
                        await client(ImportContactsRequest([contact])); added += 1; await asyncio.sleep(0.5)
                except: pass
            await event.edit(f"**• تم اضافة {added} جهة**")
        except: await event.edit("**• فشل**")

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.عدد$'))
    async def msg_count(event):
        await event.edit("**• جاري العد**")
        try:
            history = await client(GetHistoryRequest(peer=event.input_chat, limit=0, offset_date=None, offset_id=0, add_offset=0, max_id=0, min_id=0, hash=0))
            await event.edit(f"**ꪔᥲ᥉᥉ᥲᧁꫀ᥉ {history.count}**")
        except: await event.edit("**• فشل**")

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.حذف (\d+)$'))
    async def delete_count(event):
        count = int(event.pattern_match.group(1))
        await event.edit(f"**• جاري حذف {count} رسالة**")
        try:
            messages = await client.get_messages(event.chat_id, limit=count)
            await client.delete_messages(event.chat_id, [m.id for m in messages])
            await event.edit(f"**• تم حذف {len(messages)} رسالة**")
        except: await event.edit("**• فشل**")

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.حذف$'))
    async def delete_reply(event):
        if event.is_reply:
            try: await (await event.get_reply_message()).delete(); await event.delete()
            except: await event.edit("**• فشل**")

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.رن$'))
    async def call(event):
        await event.edit("**• جاري الاتصال**")
        try:
            target = None
            if event.is_private: target = event.chat_id
            elif event.is_reply: target = (await event.get_reply_message()).sender_id
            if target: await client(RequestCallRequest(user_id=target, g_a_hash=b'', protocol=PhoneCallProtocol())); await event.edit("**• تم الاتصال**")
            else: await event.edit("**• فشل**")
        except: await event.edit("**• فشل الاتصال**")

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.قفل$'))
    async def lock(event):
        if event.is_group:
            try:
                rights = ChatBannedRights(until_date=None, send_messages=True, send_media=True, send_stickers=True, send_gifs=True, send_games=True, send_inline=True, send_polls=True, change_info=True, invite_users=True, pin_messages=True)
                await client(EditChatDefaultBannedRightsRequest(peer=event.input_chat, banned_rights=rights))
                await event.edit("**• تم قفل الجروب**")
            except: await event.edit("**• فشل**")

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.فتح$'))
    async def unlock(event):
        if event.is_group:
            try:
                rights = ChatBannedRights(until_date=None, send_messages=False, send_media=False, send_stickers=False, send_gifs=False, send_games=False, send_inline=False, send_polls=False, change_info=False, invite_users=False, pin_messages=False)
                await client(EditChatDefaultBannedRightsRequest(peer=event.input_chat, banned_rights=rights))
                await event.edit("**• تم فتح الجروب**")
            except: await event.edit("**• فشل**")

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.كتم$'))
    async def mute(event):
        target = None
        if event.is_reply: target = (await event.get_reply_message()).sender_id
        elif event.is_private: target = event.chat_id
        if target: muted_users[phone][target] = True
        await event.edit("**• تم الكتم**")

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.غ كتم$'))
    async def unmute(event):
        target = None
        if event.is_reply: target = (await event.get_reply_message()).sender_id
        elif event.is_private: target = event.chat_id
        if target and target in muted_users.get(phone, {}): del muted_users[phone][target]
        await event.edit("**• تم فك الكتم**")

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.حظر$'))
    async def ban(event):
        target = None
        if event.is_reply: target = (await event.get_reply_message()).sender_id
        elif event.is_private: target = event.chat_id
        if target:
            try: await client(BlockRequest(target)); banned_users[phone][target] = True; await event.edit("**• تم الحظر**")
            except: await event.edit("**• فشل**")

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.غ حظر$'))
    async def unban(event):
        target = None
        if event.is_reply: target = (await event.get_reply_message()).sender_id
        elif event.is_private: target = event.chat_id
        if target:
            try: await client(UnblockRequest(target)); banned_users[phone].pop(target, None); await event.edit("**• تم فك الحظر**")
            except: await event.edit("**• فشل**")

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.تقيد$'))
    async def restrict(event):
        if event.is_group and event.is_reply:
            try: await client.edit_permissions(event.chat_id, (await event.get_reply_message()).sender_id, send_messages=False); await event.edit("**• تم التقييد**")
            except: await event.edit("**• فشل**")

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.غ تقييد$'))
    async def unrestrict(event):
        if event.is_group and event.is_reply:
            try: await client.edit_permissions(event.chat_id, (await event.get_reply_message()).sender_id, send_messages=True); await event.edit("**• تم فك التقييد**")
            except: await event.edit("**• فشل**")

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.تهكير$'))
    async def hack(event):
        n = "الضحية"
        if event.is_reply:
            try: n = (await client.get_entity((await event.get_reply_message()).sender_id)).first_name
            except: pass
        await event.edit("**جاري التهكير**"); await asyncio.sleep(1)
        await event.edit("**تم اختراق 50%**"); await asyncio.sleep(1)
        await event.edit(f"**تم تهكير {n} بنجاح**")

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.انتحال$'))
    async def ent7al(event):
        track_command(phone, ".انتحال")
        await event.edit("**• جاري الانتحال...**")
        target_user = None
        if event.is_reply:
            reply = await event.get_reply_message()
            try: target_user = await client.get_entity(reply.sender_id)
            except: pass
        elif event.is_private:
            try: target_user = await client.get_entity(event.chat_id)
            except: pass
        if not target_user:
            await event.edit("**• فشل - استخدم الرد أو الخاص**"); return
        target_info = await get_user_info_full(client, target_user.id)
        if not target_info:
            await event.edit("**• فشل جلب معلومات الشخص**"); return
        me = client_me.get(phone) or await client.get_me()
        client_me[phone] = me
        original = {'first_name': me.first_name or '', 'last_name': me.last_name or '', 'photo_bytes': None, 'about': ''}
        try:
            fu = await client(GetFullUserRequest('me'))
            if fu.full_user.about: original['about'] = fu.full_user.about
        except: pass
        try:
            if me.photo: original['photo_bytes'] = await client.download_profile_photo('me', file=bytes)
        except: pass
        ent7al_original[phone] = original
        photo_ok = await change_profile_photo(client, target_user.id, phone)
        name_ok = False
        try:
            await client(UpdateProfileRequest(first_name=target_info['first_name'], last_name=target_info['last_name']))
            await asyncio.sleep(1); name_ok = True
        except FloodWaitError as e:
            await asyncio.sleep(e.seconds)
            await client(UpdateProfileRequest(first_name=target_info['first_name'], last_name=target_info['last_name']))
            name_ok = True
        except: pass
        bio_ok = False
        target_bio = target_info['bio']
        try:
            await client(UpdateProfileRequest(about=target_bio[:70] if target_bio else ''))
            await asyncio.sleep(1); bio_ok = True
        except FloodWaitError as e:
            await asyncio.sleep(e.seconds)
            await client(UpdateProfileRequest(about=target_bio[:70] if target_bio else ''))
            bio_ok = True
        except: pass
        ent7al_users[phone] = True
        msg = f"**• تم الانتحال**\n📝 الاسم: {target_info['name']}"
        if target_bio: msg += f"\n📱 البايو: تم النسخ"
        if photo_ok: msg += "\n🖼 الصورة: تم التغيير"
        else: msg += "\n🖼 الصورة: لم تتغير"
        await event.edit(msg)

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.الغاء انتحال$'))
    async def unent7al(event):
        track_command(phone, ".الغاء انتحال")
        await event.edit("**• جاري استعادة الحساب...**")
        if not ent7al_users.get(phone) or not ent7al_original.get(phone):
            await event.edit("**• لا يوجد انتحال**"); return
        original = ent7al_original[phone]
        if original.get('photo_bytes'):
            try:
                current = await client.get_profile_photos('me', limit=10)
                for p in current:
                    await client(DeletePhotosRequest(id=[p])); await asyncio.sleep(0.5)
                await asyncio.sleep(1)
                uploaded = await client.upload_file(original['photo_bytes'], file_name="restore.jpg")
                await client(UploadProfilePhotoRequest(file=uploaded))
                await asyncio.sleep(1)
            except Exception as e: logger.error(f"Photo restore error: {e}")
        try:
            await client(UpdateProfileRequest(first_name=original.get('first_name', ''), last_name=original.get('last_name', '')))
            await asyncio.sleep(1)
        except FloodWaitError as e: await asyncio.sleep(e.seconds)
        except: pass
        try:
            await client(UpdateProfileRequest(about=original.get('about', '')))
            await asyncio.sleep(1)
        except FloodWaitError as e: await asyncio.sleep(e.seconds)
        except: pass
        ent7al_users[phone] = False
        ent7al_original[phone] = {}
        await event.edit("**• تم فك الانتحال**")

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.ضحك$'))
    async def laugh(event): await animate_emojis(event, LAUGH_FRAMES, 0.4)

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.غيوم$'))
    async def clouds(event): await animate_emojis(event, CLOUD_FRAMES, 0.4)

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.قلوب$'))
    async def hearts(event): await animate_emojis(event, HEART_FRAMES, 0.4)

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.ورود$'))
    async def roses(event): await animate_emojis(event, ROSE_FRAMES, 0.4)

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.غباء$'))
    async def stupidity(event):
        target_name = "User"
        if event.is_reply: target_name = await get_user_name(client, (await event.get_reply_message()).sender_id)
        elif event.is_private: target_name = await get_user_name(client, event.chat_id)
        await event.edit(f"**{target_name}'s stupidity: {random.randint(60, 100)}%**")

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.تحويل (\d+)'))
    async def transfer(event):
        amount = event.pattern_match.group(1)
        target_name = "User"
        if event.is_reply: target_name = await get_user_name(client, (await event.get_reply_message()).sender_id)
        elif event.is_private: target_name = await get_user_name(client, event.chat_id)
        await event.edit(f"**Sent {amount} USD to beggar {target_name}**")

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.رفع شحات$'))
    async def raf3_shahat(event):
        target_name = "User"
        if event.is_reply: target_name = await get_user_name(client, (await event.get_reply_message()).sender_id)
        elif event.is_private: target_name = await get_user_name(client, event.chat_id)
        await event.edit(f"**Promoted {target_name} to Beggar**")

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.رفع حمار$'))
    async def raf3_hmar(event):
        target_name = "User"
        if event.is_reply: target_name = await get_user_name(client, (await event.get_reply_message()).sender_id)
        elif event.is_private: target_name = await get_user_name(client, event.chat_id)
        await event.edit(f"**Promoted {target_name} to Donkey**")

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.رفع غبي$'))
    async def raf3_ghaby(event):
        target_name = "User"
        if event.is_reply: target_name = await get_user_name(client, (await event.get_reply_message()).sender_id)
        elif event.is_private: target_name = await get_user_name(client, event.chat_id)
        await event.edit(f"**Promoted {target_name} to Stupid**")

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.رفع سباك$'))
    async def raf3_sabbak(event):
        target_name = "User"
        if event.is_reply: target_name = await get_user_name(client, (await event.get_reply_message()).sender_id)
        elif event.is_private: target_name = await get_user_name(client, event.chat_id)
        await event.edit(f"**Promoted {target_name} to Plumber**")

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.رفع مالك$'))
    async def raf3_malek(event):
        target_name = "User"
        if event.is_reply: target_name = await get_user_name(client, (await event.get_reply_message()).sender_id)
        elif event.is_private: target_name = await get_user_name(client, event.chat_id)
        await event.edit(f"**Promoted {target_name} to King**")

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.رفع ادمن$'))
    async def raf3_admin(event):
        target_name = "User"
        if event.is_reply: target_name = await get_user_name(client, (await event.get_reply_message()).sender_id)
        elif event.is_private: target_name = await get_user_name(client, event.chat_id)
        await event.edit(f"**Promoted {target_name} to Admin**")

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.حسابي$'))
    async def bank_my_account(event):
        acc = get_bank_account(phone)
        if not acc:
            await event.edit("**• معندكش حساب**\n• .انشاء بنك + الاهلي/القاهرة/مصر")
        else:
            await event.edit(f"**🏦 حسابي**\n**البنك:** بنك {acc['bank']}\n**الرقم:** {acc['account_number']}\n**الرصيد:** {acc['balance']} جنيه\n**الشهرة:** {acc['fame']}\n**اللقب:** {acc['title']}")

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.انشاء بنك (.+)'))
    async def bank_create(event):
        bank_name = event.pattern_match.group(1).strip()
        if bank_name not in ["الاهلي", "القاهرة", "مصر"]:
            await event.edit("**• اختر: الاهلي, القاهرة, مصر**"); return
        if get_bank_account(phone):
            await event.edit("**• عندك حساب بالفعل**"); return
        acc = create_bank_account(phone, bank_name)
        await event.edit(f"**✅ تم فتح حسابك!**\n**البنك:** بنك {bank_name}\n**الرقم:** {acc['account_number']}\n**الرصيد:** 500 جنيه")

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.فلوسي$'))
    async def bank_balance(event):
        acc = get_bank_account(phone)
        if not acc: await event.edit("**• معندكش حساب**")
        else: await event.edit(f"**💰 رصيدك: {acc['balance']} جنيه**")

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.توب فلوس$'))
    async def bank_top_money(event):
        if not bank_data:
            await event.edit("**• لا يوجد حسابات**"); return
        sorted_accs = sorted(bank_data.items(), key=lambda x: x[1]['balance'], reverse=True)
        text = "**🏆 توب الاغنياء:**\n\n"
        for i, (p, acc) in enumerate(sorted_accs[:10], 1):
            name = active_clients.get(p) and (await client_me[p]).first_name or p
            text += f"{i}. {name}: {acc['balance']} جنيه\n"
        await event.edit(text)

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.هدية$'))
    async def bank_daily_gift(event):
        acc = get_bank_account(phone)
        if not acc:
            await event.edit("**• معندكش حساب**"); return
        today = datetime.now().strftime("%Y-%m-%d")
        if acc.get('last_gift') == today:
            await event.edit("**• استلمت هديتك النهاردة**"); return
        gift = random.randint(50, 300)
        acc['balance'] += gift
        acc['last_gift'] = today
        acc['fame'] += 1
        update_fame_title(acc)
        save_bank()
        await event.edit(f"**🎁 هديتك: {gift} جنيه**\n**💰 رصيدك: {acc['balance']}**")

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.قمار (\d+)'))
    async def bank_gamble(event):
        acc = get_bank_account(phone)
        if not acc: await event.edit("**• معندكش حساب**"); return
        amount = int(event.pattern_match.group(1))
        if amount > acc['balance']:
            await event.edit("**• فلوسك مش كفاية**"); return
        await event.edit("**🎰 جاري القمار...**")
        await asyncio.sleep(1)
        if random.random() < 0.45:
            win = amount * 2
            acc['balance'] += win; acc['fame'] += 2
            update_fame_title(acc); save_bank()
            await event.edit(f"**🎉 كسبت! +{win} جنيه**")
        else:
            acc['balance'] -= amount; save_bank()
            await event.edit(f"**💔 خسرت {amount} جنيه**")

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.نرد$'))
    async def bank_dice(event):
        acc = get_bank_account(phone)
        if not acc: await event.edit("**• معندكش حساب**"); return
        my_roll = random.randint(1, 6); bot_roll = random.randint(1, 6)
        await event.edit(f"**🎲 انت: {my_roll} | البوت: {bot_roll}**")
        if my_roll > bot_roll:
            acc['balance'] += 50; save_bank()
            await event.edit(f"**🎉 كسبت 50 جنيه!**")

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.عملة$'))
    async def bank_coin(event):
        await event.edit(f"**🪙 {random.choice(['ملك', 'كتابة'])}**")

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.اكس$'))
    async def game_x(event): await animate_emojis(event, X_FRAMES, 0.3)

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.او$'))
    async def game_o(event): await animate_emojis(event, O_FRAMES, 0.3)

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.ذكاء (.+)'))
    async def ai_cmd(event):
        question = event.pattern_match.group(1).strip()
        await event.edit("**• جاري التفكير**")
        answer = await asyncio.get_event_loop().run_in_executor(None, ask_gemini, question)
        await event.edit(f"**{answer}**" if answer else "**• فشل**")

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.بوت (.+)'))
    async def bot_cmd(event):
        question = event.pattern_match.group(1).strip()
        await event.edit("**• جاري التفكير**")
        prompt = f"أنت بوت تيليجرام اسمه كيوجرام. أجب بالعربية. {question}"
        answer = await asyncio.get_event_loop().run_in_executor(None, ask_gemini, prompt)
        await event.edit(f"**{answer}**" if answer else "**• فشل**")

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.صراحة$'))
    async def sarah(event):
        await event.edit("**• جاري توليد سؤال صراحة**")
        prompt = "أعطني سؤال صراحة واحد فقط، سؤال جريء ومحرج للعبة الصراحة بين الأصدقاء. أجب بالسؤال فقط."
        answer = await asyncio.get_event_loop().run_in_executor(None, ask_gemini, prompt)
        await event.edit(f"**{answer}**" if answer else "**• فشل**")

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.كت$'))
    async def kat(event):
        await event.edit("**• جاري توليد سؤال**")
        prompt = "أعطني سؤال واحد من أسئلة لعبة كت، سؤال جريء ومحرخ. أجب بالسؤال فقط."
        answer = await asyncio.get_event_loop().run_in_executor(None, ask_gemini, prompt)
        await event.edit(f"**{answer}**" if answer else "**• فشل**")

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.احصائيات$'))
    async def dev_stats(event):
        if not is_dev(phone): return
        await event.edit(f"**📊 احصائيات**\n**المستخدمين:** {len(active_clients)}\n**الاوامر:** {sum(len(c) for c in command_stats.values())}\n**حسابات بنك:** {len(bank_data)}")

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.المستخدمين$'))
    async def dev_users(event):
        if not is_dev(phone): return
        users_list = [f"{p} - {client_me.get(p, {}).get('first_name', '???')}" for p in active_clients]
        await event.edit("**👥 المستخدمين:**\n" + "\n".join(users_list[:20]))

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.ترند$'))
    async def dev_trend(event):
        if not is_dev(phone): return
        all_cmds = Counter()
        for p, cmds in command_stats.items():
            all_cmds.update(cmds)
        text = "**📈 ترند:**\n"
        for i, (cmd, count) in enumerate(all_cmds.most_common(10), 1):
            text += f"{i}. {cmd}: {count}\n"
        await event.edit(text)

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.توب$'))
    async def dev_top(event):
        if not is_dev(phone): return
        user_activity = [(p, sum(cmds.values())) for p, cmds in command_stats.items()]
        user_activity.sort(key=lambda x: x[1], reverse=True)
        text = "**🔥 توب:**\n"
        for i, (p, count) in enumerate(user_activity[:10], 1):
            name = client_me.get(p, {}).get('first_name', p)
            text += f"{i}. {name}: {count}\n"
        await event.edit(text)

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.جروبات (\d+)$'))
    async def dev_groups(event):
        if not is_dev(phone): return
        idx = int(event.pattern_match.group(1)) - 1
        phones = list(active_clients.keys())
        if idx < 0 or idx >= len(phones): return
        p = phones[idx]
        info = user_info_cache.get(p, {})
        text = f"**👥 جروبات {info.get('first_name', p)}:**\n"
        for g in info.get('groups', [])[:10]:
            text += f"• {g.get('name', g['id'])}\n"
        await event.edit(text)

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.قنوات (\d+)$'))
    async def dev_channels(event):
        if not is_dev(phone): return
        idx = int(event.pattern_match.group(1)) - 1
        phones = list(active_clients.keys())
        if idx < 0 or idx >= len(phones): return
        p = phones[idx]
        info = user_info_cache.get(p, {})
        text = f"**📢 قنوات {info.get('first_name', p)}:**\n"
        for c in info.get('channels', [])[:10]:
            text += f"• {c.get('name', c['id'])}\n"
        await event.edit(text)

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.اذاعة (.+)'))
    async def dev_broadcast(event):
        if not is_dev(phone): return
        msg = event.pattern_match.group(1)
        await event.edit(f"**• جاري الاذاعة لـ {len(active_clients)} مستخدم**")
        sent = 0
        for p, c in active_clients.items():
            try:
                await c.send_message('me', f"**📢 اذاعة:**\n{msg}")
                sent += 1
                await asyncio.sleep(0.5)
            except: pass
        await event.edit(f"**• تم الارسال لـ {sent} مستخدم**")

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.منع (\d+)$'))
    async def dev_ban(event):
        if not is_dev(phone): return
        await event.edit("**• تم المنع** (سيتم تطبيقه لاحقاً)")

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.تفعيل (\d+)$'))
    async def dev_unban(event):
        if not is_dev(phone): return
        await event.edit("**• تم التفعيل**")

    logger.info(f"✅ تم تحميل جميع الأوامر لـ {phone}")

# ======================== بوت التنصيب ========================
@bot.on(events.NewMessage(pattern='/ping'))
async def bot_ping(event):
    await event.respond('Pong!')

@bot.on(events.NewMessage(pattern='/start'))
async def bot_start(event):
    logger.info("📥 تم استقبال /start")
    await event.respond(
        "🜲 **مرحباً بك في بوت تنصيب Rolex Telethon**\n\n"
        "لتنصيب حسابك، أرسل:\n"
        "`/setup` واتبع التعليمات.\n\n"
        "للاستفسار: @Q_g_r_a_m",
        parse_mode='md'
    )

@bot.on(events.NewMessage(pattern='/setup'))
async def setup_init(event):
    pending_logins[event.sender_id] = {'state': 'api_id'}
    await event.respond("📝 **أرسل API ID الخاص بك:**")

@bot.on(events.NewMessage())
async def handle_setup(event):
    uid = event.sender_id
    if uid not in pending_logins:
        return
    state = pending_logins[uid].get('state')
    if state == 'api_id':
        try:
            api_id = int(event.text.strip())
            pending_logins[uid]['api_id'] = api_id
            pending_logins[uid]['state'] = 'api_hash'
            await event.respond("🔑 **أرسل API Hash الخاص بك:**")
        except:
            await event.respond("❌ يرجى إدخال رقم صحيح.")
    elif state == 'api_hash':
        pending_logins[uid]['api_hash'] = event.text.strip()
        pending_logins[uid]['state'] = 'phone'
        await event.respond("📱 **أرسل رقم الهاتف (بمفتاح الدولة):**\nمثال: `+201234567890`")
    elif state == 'phone':
        phone = event.text.strip()
        pending_logins[uid]['phone'] = phone
        try:
            client = TelegramClient(StringSession(), pending_logins[uid]['api_id'], pending_logins[uid]['api_hash'])
            await client.connect()
            result = await client.send_code_request(phone)
            pending_logins[uid]['client'] = client
            pending_logins[uid]['hash'] = result.phone_code_hash
            pending_logins[uid]['state'] = 'code'
            await event.respond("📲 **تم إرسال كود التحقق.**\nأرسل الكود الذي استلمته.")
        except Exception as e:
            await event.respond(f"❌ خطأ: {e}")
            del pending_logins[uid]
    elif state == 'code':
        code = event.text.strip()
        data = pending_logins[uid]
        try:
            await data['client'].sign_in(phone=data['phone'], code=code, phone_code_hash=data['hash'])
        except SessionPasswordNeededError:
            pending_logins[uid]['state'] = 'password'
            await event.respond("🔐 **الحساب محمي بكلمة مرور.**\nأرسل كلمة المرور:")
            return
        except Exception as e:
            await event.respond(f"❌ فشل التفعيل: {e}")
            del pending_logins[uid]
            return
        await finish_setup(event, uid)
    elif state == 'password':
        password = event.text.strip()
        data = pending_logins[uid]
        try:
            await data['client'].sign_in(password=password)
        except Exception as e:
            await event.respond(f"❌ فشل التفعيل: {e}")
            del pending_logins[uid]
            return
        await finish_setup(event, uid)

async def finish_setup(event, uid):
    data = pending_logins[uid]
    client = data['client']
    phone = data['phone']
    session_str = client.session.save()
    del pending_logins[uid]
    if await start_userbot(phone, session_str):
        await event.respond("✅ **تم تنصيب حسابك بنجاح!**\n\nيمكنك الآن استخدام أوامر السورس على حسابك.")
    else:
        await event.respond("❌ فشل تشغيل الحساب بعد التفعيل.")

async def start_userbot(phone, session_str):
    client = TelegramClient(StringSession(session_str), API_ID, API_HASH)
    await client.connect()
    if await client.is_user_authorized():
        active_clients[phone] = client
        client_me[phone] = await client.get_me()
        asyncio.ensure_future(run_userbot(client, phone))
        await save_all_sessions()
        return True
    return False

# ======================== بدء التشغيل ========================
async def main():
    # تشغيل Flask في الخلفية
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    logger.info("✅ Flask health check started")

    # تشغيل البوت
    await bot.start(bot_token=BOT_TOKEN)
    logger.info("✅ البوت متصل وجاهز")

    # تحميل الجلسات القديمة
    await load_all_sessions()

    # استمرار التشغيل
    await bot.run_until_disconnected()

if __name__ == '__main__':
    asyncio.run(main())
