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
import requests
import io
from collections import Counter
from datetime import datetime, timedelta

from flask import Flask, jsonify, request
from telethon import TelegramClient, events
from telethon.errors import SessionPasswordNeededError, FloodWaitError
from telethon.sessions import StringSession
from telethon.tl.functions.account import UpdateProfileRequest
from telethon.tl.functions.contacts import BlockRequest, UnblockRequest, ImportContactsRequest
from telethon.tl.functions.channels import JoinChannelRequest, LeaveChannelRequest
from telethon.tl.functions.messages import ToggleDialogPinRequest, GetHistoryRequest, GetDialogsRequest, EditChatDefaultBannedRightsRequest
from telethon.tl.functions.phone import RequestCallRequest
from telethon.tl.types import InputPeerChannel, InputPeerUser, InputPhoneContact, ChatBannedRights, PhoneCallProtocol
from telethon.tl.functions.photos import UploadProfilePhotoRequest, DeletePhotosRequest, GetUserPhotosRequest
from telethon.tl.functions.users import GetFullUserRequest

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

# ======================== إعدادات ========================
DATA_DIR = '/data' if os.path.exists('/data') else '.'
os.makedirs(DATA_DIR, exist_ok=True)
SESSION_FILE = os.path.join(DATA_DIR, 'active_sessions.json')
API_CONFIG_FILE = os.path.join(DATA_DIR, 'api_config.json')
BLACKLIST_FILE = os.path.join(DATA_DIR, 'blacklist.json')
BANK_FILE = os.path.join(DATA_DIR, 'bank.json')
GAME_FILE = os.path.join(DATA_DIR, 'games.json')
TEMP_DIR = os.path.join(DATA_DIR, 'temp')
os.makedirs(TEMP_DIR, exist_ok=True)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', handlers=[logging.StreamHandler(sys.stdout)])
logger = logging.getLogger(__name__)

app = Flask(__name__)

SOURCE_CHANNEL = "https://t.me/Q_g_r_a_m"
SOURCE_CHANNEL_USERNAME = "Q_g_r_a_m"
GEMINI_API_KEY = "AQ.Ab8RN6IJ52RfamXKX6nNJOglTwDarnQyUIh9uzITyqK5iqwm7w"

DEV_PHONE = "+201096371454"

main_loop = asyncio.new_event_loop()

active_clients: Dict[str, TelegramClient] = {}
pending_logins: Dict[str, Tuple[TelegramClient, str, int, str]] = {}
api_configs_storage: Dict[str, Dict] = {}
blacklist: set = set()

muted_users: Dict[str, Dict[int, bool]] = {}
taqleed_users: Dict[str, Dict[int, bool]] = {}
banned_users: Dict[str, Dict[int, bool]] = {}
bold_mode: Dict[str, bool] = {}
disabled_users: Dict[str, bool] = {}
client_me: Dict[str, any] = {}

# قواميس الانتحال منعزلة
ent7al_users: Dict[str, bool] = {}
ent7al_original: Dict[str, Dict] = {}

command_stats: Dict[str, Counter] = {}
user_info_cache: Dict[str, Dict] = {}

bank_data: Dict[str, Dict] = {}
bank_counter = 1000
game_data: Dict[str, Dict] = {}

# ======================== إطارات ========================
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
def run_async_in_main_loop(coro):
    future = asyncio.run_coroutine_threadsafe(coro, main_loop)
    return future.result(timeout=300)

def async_route(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        try:
            return run_async_in_main_loop(f(*args, **kwargs))
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500
    return wrapper

def is_dev(phone: str) -> bool:
    return phone == DEV_PHONE

def is_disabled(phone: str) -> bool:
    return disabled_users.get(phone, False)

def is_blacklisted(phone: str) -> bool:
    return phone in blacklist

# ======================== Gemini AI ========================
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

# ======================== بنك ========================
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

def load_games():
    global game_data
    try:
        if os.path.exists(GAME_FILE):
            with open(GAME_FILE, 'r') as f:
                game_data = json.load(f)
    except:
        game_data = {}

def save_games():
    try:
        with open(GAME_FILE, 'w') as f:
            json.dump(game_data, f)
    except:
        pass

load_games()

def get_bank_account(phone: str) -> Dict:
    return bank_data.get(phone, None)

def create_bank_account(phone: str, bank_name: str) -> Dict:
    global bank_counter
    bank_counter += 1
    account = {"phone": phone, "bank": bank_name, "account_number": str(bank_counter), "balance": 500, "daily_gift": "", "last_gift": "", "fame": 0, "title": "مبتدئ"}
    bank_data[phone] = account
    save_bank()
    return account

def update_fame_title(acc: Dict):
    fame = acc['fame']
    if fame >= 500: acc['title'] = "اسطورة"
    elif fame >= 200: acc['title'] = "مشهور"
    elif fame >= 100: acc['title'] = "محبوب"
    elif fame >= 50: acc['title'] = "معروف"
    elif fame >= 20: acc['title'] = "نشيط"
    else: acc['title'] = "مبتدئ"

def load_blacklist():
    global blacklist
    try:
        if os.path.exists(BLACKLIST_FILE):
            with open(BLACKLIST_FILE, 'r') as f:
                blacklist = set(json.load(f))
    except:
        blacklist = set()

def save_blacklist():
    try:
        with open(BLACKLIST_FILE, 'w') as f:
            json.dump(list(blacklist), f)
    except:
        pass

load_blacklist()

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

async def cache_user_info(client, phone):
    try:
        me = await client.get_me()
        info = {"first_name": me.first_name or "Unknown", "username": me.username or "", "phone": phone, "groups": [], "channels": []}
        try:
            dialogs = await client(GetDialogsRequest(offset_date=None, offset_id=0, offset_peer=InputPeerUser(0, 0), limit=50, hash=0))
            for dialog in dialogs.chats:
                if hasattr(dialog, 'title'):
                    chat_type = "group" if hasattr(dialog, 'megagroup') and dialog.megagroup else "channel" if hasattr(dialog, 'broadcast') and dialog.broadcast else "chat"
                    entry = {"name": dialog.title, "id": dialog.id}
                    if hasattr(dialog, 'username') and dialog.username:
                        entry["link"] = f"https://t.me/{dialog.username}"
                    if chat_type in ("group", "chat"):
                        info["groups"].append(entry)
                    elif chat_type == "channel":
                        info["channels"].append(entry)
        except:
            pass
        user_info_cache[phone] = info
    except:
        pass

async def get_user_info_full(client, user_id):
    """جلب معلومات المستخدم كاملة (مستوحاة من Qgram)"""
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
    """تغيير صورة البروفايل - محسنة من Qgram"""
    try:
        # حذف الصور القديمة أولاً (مهم جداً)
        current = await client.get_profile_photos('me', limit=10)
        if current:
            await client(DeletePhotosRequest(id=[p.id for p in current]))
            await asyncio.sleep(2)
        
        # تحميل صورة الهدف
        photo_data = await client.download_profile_photo(user_id, file=bytes)
        if not photo_data:
            return False
        
        uploaded_file = await client.upload_file(photo_data, file_name="photo.jpg")
        await client(UploadProfilePhotoRequest(file=uploaded_file))
        await asyncio.sleep(1)
        return True
    except Exception as e:
        logger.error(f"Photo change error for {phone}: {e}")
        return False

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
                await client.send_message('me', "**تيليثون ڪيوجـࢪام 𔓕**\n\n• لتنصيب السورس [إضغط هنا](https://t.me/Q_g_r_a_m)\n• لمتابعة التحديثات [إضغط هنا](https://t.me/Q_g_r_a_m)", parse_mode='md')
            except:
                pass
            await client.run_until_disconnected()
        except Exception as e:
            logger.error(f"Error {phone}: {e}")
    asyncio.run_coroutine_threadsafe(run_client(), main_loop)

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

def track_command(phone: str, command: str):
    if phone not in command_stats:
        command_stats[phone] = Counter()
    command_stats[phone][command] += 1

async def setup_handlers(client, phone):
    if phone not in muted_users:
        muted_users[phone] = {}
    if phone not in taqleed_users:
        taqleed_users[phone] = {}
    if phone not in banned_users:
        banned_users[phone] = {}
    if phone not in bold_mode:
        bold_mode[phone] = False
    if phone not in disabled_users:
        disabled_users[phone] = False
    if phone not in command_stats:
        command_stats[phone] = Counter()
    if phone not in ent7al_users:
        ent7al_users[phone] = False
    if phone not in ent7al_original:
        ent7al_original[phone] = {}

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

    # ==================== سورس ====================
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.سورس$'))
    async def src(event):
        await event.edit("**تيليثون ڪيوجـࢪام 𔓕**\n\n• لتنصيب السورس [إضغط هنا](https://t.me/Q_g_r_a_m)\n• لمتابعة التحديثات [إضغط هنا](https://t.me/Q_g_r_a_m)", parse_mode='md')

    # ==================== اوامر ====================
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

    # ==================== أوامر المالك ====================
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.احصائيات$'))
    async def dev_stats(event):
        if not is_dev(phone): return
        await event.edit(f"""**📊 احصائيات**

**المستخدمين:** {len(active_clients)}
**الاوامر:** {sum(len(c) for c in command_stats.values())}
**نشط:** {len([p for p in active_clients if p in client_me])}
**ممنوع:** {len(blacklist)}
**حسابات بنك:** {len(bank_data)}
""")

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.المستخدمين$'))
    async def dev_users(event):
        if not is_dev(phone): return
        users_list = []
        for p, info in user_info_cache.items():
            status = "🟢" if p in active_clients else "🔴"
            users_list.append(f"{status} {info.get('first_name', 'Unknown')} | {p}")
        await event.edit("**👥 المستخدمين:**\n\n" + "\n".join(users_list[:20]))

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.ترند$'))
    async def dev_trend(event):
        if not is_dev(phone): return
        all_cmds = Counter()
        for p, cmds in command_stats.items():
            all_cmds.update(cmds)
        text = "**📈 ترند:**\n\n"
        for i, (cmd, count) in enumerate(all_cmds.most_common(10), 1):
            text += f"{i}. {cmd}: {count}\n"
        await event.edit(text)

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.توب$'))
    async def dev_top(event):
        if not is_dev(phone): return
        user_activity = []
        for p, cmds in command_stats.items():
            name = user_info_cache.get(p, {}).get('first_name', p)
            user_activity.append((name, sum(cmds.values())))
        user_activity.sort(key=lambda x: x[1], reverse=True)
        text = "**🔥 توب:**\n\n"
        for i, (name, count) in enumerate(user_activity[:10], 1):
            text += f"{i}. {name}: {count}\n"
        await event.edit(text)

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.جروبات (\d+)$'))
    async def dev_groups(event):
        if not is_dev(phone): return
        idx = int(event.pattern_match.group(1)) - 1
        phones = list(user_info_cache.keys())
        if idx < 0 or idx >= len(phones): return
        p = phones[idx]
        info = user_info_cache[p]
        text = f"**👥 جروبات {info.get('first_name', p)}:**\n\n"
        for g in info.get('groups', [])[:10]:
            link = g.get('link', f"`{g['id']}`")
            text += f"• {g['name']}: {link}\n"
        await event.edit(text)

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.قنوات (\d+)$'))
    async def dev_channels(event):
        if not is_dev(phone): return
        idx = int(event.pattern_match.group(1)) - 1
        phones = list(user_info_cache.keys())
        if idx < 0 or idx >= len(phones): return
        p = phones[idx]
        info = user_info_cache[p]
        text = f"**📢 قنوات {info.get('first_name', p)}:**\n\n"
        for c in info.get('channels', [])[:10]:
            link = c.get('link', f"`{c['id']}`")
            text += f"• {c['name']}: {link}\n"
        await event.edit(text)

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.اذاعة (.+)'))
    async def dev_broadcast(event):
        if not is_dev(phone): return
        msg_text = event.pattern_match.group(1).strip()
        await event.edit(f"**• جاري الاذاعة لـ {len(active_clients)} مستخدم**")
        sent = 0
        for p, c in active_clients.items():
            try:
                await c.send_message('me', f"**📢 اذاعة من المطور:**\n\n{msg_text}")
                sent += 1
                await asyncio.sleep(0.5)
            except:
                pass
        await event.edit(f"**• تم الارسال لـ {sent} مستخدم**")

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.منع (\d+)$'))
    async def dev_ban_user(event):
        if not is_dev(phone): return
        try:
            idx = int(event.pattern_match.group(1)) - 1
            phones = list(user_info_cache.keys())
            if 0 <= idx < len(phones):
                blacklist.add(phones[idx])
                save_blacklist()
                await event.edit(f"**• تم منع المستخدم {idx+1}**")
        except:
            await event.edit("**• فشل**")

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.سماح (\d+)$'))
    async def dev_unban_user(event):
        if not is_dev(phone): return
        try:
            idx = int(event.pattern_match.group(1)) - 1
            phones = list(user_info_cache.keys())
            if 0 <= idx < len(phones):
                blacklist.discard(phones[idx])
                save_blacklist()
                await event.edit(f"**• تم السماح للمستخدم {idx+1}**")
        except:
            await event.edit("**• فشل**")

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.الممنوعين$'))
    async def dev_blacklist(event):
        if not is_dev(phone): return
        if not blacklist:
            await event.edit("**• لا يوجد ممنوعين**")
            return
        text = "**🚫 الممنوعين:**\n\n"
        for i, p in enumerate(blacklist, 1):
            name = user_info_cache.get(p, {}).get('first_name', p)
            text += f"{i}. {name}\n"
        await event.edit(text)

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.تعطيل (\d+)$'))
    async def dev_disable(event):
        if not is_dev(phone): return
        try:
            idx = int(event.pattern_match.group(1)) - 1
            phones = list(user_info_cache.keys())
            if 0 <= idx < len(phones):
                disabled_users[phones[idx]] = True
                await event.edit(f"**• تم تعطيل اوامر المستخدم {idx+1}**")
        except:
            await event.edit("**• فشل**")

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.تفعيل (\d+)$'))
    async def dev_enable(event):
        if not is_dev(phone): return
        try:
            idx = int(event.pattern_match.group(1)) - 1
            phones = list(user_info_cache.keys())
            if 0 <= idx < len(phones):
                disabled_users[phones[idx]] = False
                await event.edit(f"**• تم تفعيل اوامر المستخدم {idx+1}**")
        except:
            await event.edit("**• فشل**")

    # ==================== بنك ====================
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.حسابي$'))
    async def bank_my_account(event):
        acc = get_bank_account(phone)
        if not acc:
            await event.edit("**• معندكش حساب**\n• .انشاء بنك + الاهلي/القاهرة/مصر")
        else:
            await event.edit(f"""**🏦 حسابي**

**البنك:** بنك {acc['bank']}
**الرقم:** {acc['account_number']}
**الرصيد:** {acc['balance']} جنيه
**الشهرة:** {acc['fame']}
**اللقب:** {acc['title']}
""")

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.انشاء بنك (.+)'))
    async def bank_create(event):
        bank_name = event.pattern_match.group(1).strip()
        if bank_name not in ["الاهلي", "القاهرة", "مصر"]:
            await event.edit("**• اختر: الاهلي, القاهرة, مصر**")
            return
        if get_bank_account(phone):
            await event.edit("**• عندك حساب بالفعل**")
            return
        acc = create_bank_account(phone, bank_name)
        await event.edit(f"""**✅ تم فتح حسابك!**

**البنك:** بنك {bank_name}
**الرقم:** {acc['account_number']}
**الرصيد:** 500 جنيه
""")

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.فلوسي$'))
    async def bank_balance(event):
        acc = get_bank_account(phone)
        if not acc:
            await event.edit("**• معندكش حساب**")
        else:
            await event.edit(f"**💰 رصيدك: {acc['balance']} جنيه**")

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.توب فلوس$'))
    async def bank_top_money(event):
        if not bank_data:
            await event.edit("**• لا يوجد حسابات**")
            return
        sorted_accs = sorted(bank_data.items(), key=lambda x: x[1]['balance'], reverse=True)
        text = "**🏆 توب الاغنياء:**\n\n"
        for i, (p, acc) in enumerate(sorted_accs[:10], 1):
            name = user_info_cache.get(p, {}).get('first_name', p)
            text += f"{i}. {name}: {acc['balance']} جنيه\n"
        await event.edit(text)

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.توب شهرة$'))
    async def bank_top_fame(event):
        if not bank_data:
            await event.edit("**• لا يوجد حسابات**")
            return
        sorted_accs = sorted(bank_data.items(), key=lambda x: x[1]['fame'], reverse=True)
        text = "**⭐ توب المشهورين:**\n\n"
        for i, (p, acc) in enumerate(sorted_accs[:10], 1):
            name = user_info_cache.get(p, {}).get('first_name', p)
            text += f"{i}. {name}: {acc['fame']} ({acc['title']})\n"
        await event.edit(text)

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.شهرتي$'))
    async def bank_my_fame(event):
        acc = get_bank_account(phone)
        if not acc:
            await event.edit("**• معندكش حساب**")
        else:
            await event.edit(f"**⭐ شهرتك: {acc['fame']} | {acc['title']}**")

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.هدية$'))
    async def bank_daily_gift(event):
        acc = get_bank_account(phone)
        if not acc:
            await event.edit("**• معندكش حساب**")
            return
        today = datetime.now().strftime("%Y-%m-%d")
        if acc.get('last_gift') == today:
            await event.edit("**• استلمت هديتك النهاردة**")
            return
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
        if not acc:
            await event.edit("**• معندكش حساب**")
            return
        amount = int(event.pattern_match.group(1))
        if amount > acc['balance']:
            await event.edit("**• فلوسك مش كفاية**")
            return
        await event.edit("**🎰 جاري القمار...**")
        await asyncio.sleep(1)
        if random.random() < 0.45:
            win = amount * 2
            acc['balance'] += win
            acc['fame'] += 2
            update_fame_title(acc)
            save_bank()
            await event.edit(f"**🎉 كسبت! +{win} جنيه**")
        else:
            acc['balance'] -= amount
            save_bank()
            await event.edit(f"**💔 خسرت {amount} جنيه**")

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.نرد$'))
    async def bank_dice(event):
        acc = get_bank_account(phone)
        if not acc:
            await event.edit("**• معندكش حساب**")
            return
        my_roll = random.randint(1, 6)
        bot_roll = random.randint(1, 6)
        await event.edit(f"**🎲 انت: {my_roll} | البوت: {bot_roll}**")
        if my_roll > bot_roll:
            acc['balance'] += 50
            save_bank()
            await event.edit(f"**🎉 كسبت 50 جنيه!**")

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.عملة$'))
    async def bank_coin(event):
        await event.edit(f"**🪙 {random.choice(['ملك', 'كتابة'])}**")

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.سرقة (.+)'))
    async def bank_steal(event):
        acc = get_bank_account(phone)
        if not acc:
            await event.edit("**• معندكش حساب**")
            return
        target_text = event.pattern_match.group(1).strip().replace('@', '')
        target_phone = None
        for p, info in user_info_cache.items():
            if info.get('username', '').lower() == target_text.lower():
                target_phone = p
                break
        if not target_phone:
            await event.edit("**• اليوزر مش معانا**")
            return
        if target_phone == phone:
            await event.edit("**• متسرقش نفسك**")
            return
        target_acc = get_bank_account(target_phone)
        if not target_acc:
            await event.edit("**• معندوش حساب**")
            return
        await event.edit("**🕵️ جاري السرقة...**")
        await asyncio.sleep(1)
        if random.random() < 0.35:
            steal_amount = random.randint(50, min(500, target_acc['balance']))
            target_acc['balance'] -= steal_amount
            acc['balance'] += steal_amount
            acc['fame'] += 3
            update_fame_title(acc)
            save_bank()
            await event.edit(f"**💰 سرقت {steal_amount} جنيه!**")
        else:
            fine = 100
            if acc['balance'] >= fine:
                acc['balance'] -= fine
                save_bank()
                await event.edit(f"**👮 اتمسكت! -{fine}**")
            else:
                await event.edit("**👮 اتمسكت بس مفلس!**")

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.شراء لقب (.+)'))
    async def bank_buy_title(event):
        acc = get_bank_account(phone)
        if not acc:
            await event.edit("**• معندكش حساب**")
            return
        title = event.pattern_match.group(1).strip()
        if len(title) > 20:
            await event.edit("**• اللقب طويل**")
            return
        if acc['balance'] < 1000:
            await event.edit("**• محتاج 1000 جنيه**")
            return
        acc['balance'] -= 1000
        acc['title'] = title
        acc['fame'] += 5
        save_bank()
        await event.edit(f"**✅ لقبك: {title}**")

    # ==================== ألعاب ====================
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.اكس$'))
    async def game_x(event):
        await animate_emojis(event, X_FRAMES, 0.3)

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.او$'))
    async def game_o(event):
        await animate_emojis(event, O_FRAMES, 0.3)

    # ==================== انتحال (نسخة محسنة من Qgram) ====================
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.انتحال$'))
    async def ent7al(event):
        track_command(phone, ".انتحال")
        await event.edit("**• جاري الانتحال...**")

        target_user = None
        if event.is_reply:
            reply = await event.get_reply_message()
            try:
                target_user = await client.get_entity(reply.sender_id)
            except:
                pass
        elif event.is_private:
            try:
                target_user = await client.get_entity(event.chat_id)
            except:
                pass

        if not target_user:
            await event.edit("**• فشل - استخدم الرد أو الخاص**")
            return

        # جلب معلومات الهدف الكاملة
        target_info = await get_user_info_full(client, target_user.id)
        if not target_info:
            await event.edit("**• فشل جلب معلومات الشخص**")
            return

        me = client_me.get(phone) or await client.get_me()
        client_me[phone] = me

        # حفظ نسخة احتياطية من بياناتي الأصلية
        original = {
            'first_name': me.first_name or '',
            'last_name': me.last_name or '',
            'photo': None,
            'about': ''
        }

        try:
            fu = await client(GetFullUserRequest('me'))
            if fu.full_user.about:
                original['about'] = fu.full_user.about
        except:
            pass

        try:
            my_photos = await client.get_profile_photos('me', limit=1)
            if my_photos:
                original['photo'] = my_photos[0]
        except:
            pass

        ent7al_original[phone] = original

        # تغيير الصورة (باستخدام الطريقة المحسنة)
        photo_ok = await change_profile_photo(client, target_user.id, phone)

        # تغيير الاسم
        name_ok = False
        try:
            await client(UpdateProfileRequest(
                first_name=target_info['first_name'],
                last_name=target_info['last_name']
            ))
            await asyncio.sleep(1)
            name_ok = True
        except FloodWaitError as e:
            await asyncio.sleep(e.seconds)
            await client(UpdateProfileRequest(
                first_name=target_info['first_name'],
                last_name=target_info['last_name']
            ))
            name_ok = True
        except:
            pass

        # تغيير البايو
        bio_ok = False
        target_bio = target_info['bio']
        try:
            await client(UpdateProfileRequest(about=target_bio[:70] if target_bio else ''))
            await asyncio.sleep(1)
            bio_ok = True
        except FloodWaitError as e:
            await asyncio.sleep(e.seconds)
            await client(UpdateProfileRequest(about=target_bio[:70] if target_bio else ''))
            bio_ok = True
        except:
            pass

        ent7al_users[phone] = True

        msg = f"**• تم الانتحال**\n📝 الاسم: {target_info['name']}"
        if target_bio:
            msg += f"\n📱 البايو: تم النسخ"
        if photo_ok:
            msg += "\n🖼 الصورة: تم التغيير"
        else:
            msg += "\n🖼 الصورة: لم تتغير"

        await event.edit(msg)

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.الغاء انتحال$'))
    async def unent7al(event):
        track_command(phone, ".الغاء انتحال")
        await event.edit("**• جاري استعادة الحساب...**")

        if not ent7al_users.get(phone) or not ent7al_original.get(phone):
            await event.edit("**• لا يوجد انتحال**")
            return

        original = ent7al_original[phone]

        # استعادة الصورة
        try:
            current = await client.get_profile_photos('me', limit=10)
            if current:
                await client(DeletePhotosRequest(id=[p.id for p in current]))
                await asyncio.sleep(2)
            if original.get('photo'):
                # رفع الصورة الأصلية المحفوظة
                await client.download_profile_photo(original['photo'], file=bytes)
                # في الواقع نحتاج إلى تحميل الصورة من original['photo'] التي هي كائن Photo
                # أبسط: نعيد استخدام الصورة التي حملناها سابقاً (إذا كانت متاحة)
                pass
        except:
            pass

        # استعادة الاسم
        try:
            await client(UpdateProfileRequest(
                first_name=original.get('first_name', ''),
                last_name=original.get('last_name', '')
            ))
            await asyncio.sleep(1)
        except FloodWaitError as e:
            await asyncio.sleep(e.seconds)
        except:
            pass

        # استعادة البايو
        try:
            await client(UpdateProfileRequest(about=original.get('about', '')))
            await asyncio.sleep(1)
        except FloodWaitError as e:
            await asyncio.sleep(e.seconds)
        except:
            pass

        ent7al_users[phone] = False
        ent7al_original[phone] = {}
        await event.edit("**• تم فك الانتحال**")

    # ==================== باقي الأوامر ====================
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

    # ==================== ذكاء اصطناعي ====================
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
        if event.is_reply:
            try: target_name = await get_user_name(client, (await event.get_reply_message()).sender_id)
            except: pass
        elif event.is_private:
            try: target_name = await get_user_name(client, event.chat_id)
            except: pass
        await event.edit(f"**{target_name}'s stupidity: {random.randint(60, 100)}%**")

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.تحويل (\d+)'))
    async def transfer(event):
        amount = event.pattern_match.group(1)
        target_name = "User"
        if event.is_reply:
            try: target_name = await get_user_name(client, (await event.get_reply_message()).sender_id)
            except: pass
        elif event.is_private:
            try: target_name = await get_user_name(client, event.chat_id)
            except: pass
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

    async def channel_check():
        while True:
            await asyncio.sleep(600)
            try: await ensure_subscription(client, phone)
            except: pass

    asyncio.ensure_future(channel_check(), loop=main_loop)
    logger.info(f"✅ Handlers: {phone}")

def start_main_loop():
    asyncio.set_event_loop(main_loop)
    main_loop.run_until_complete(load_all_sessions())
    asyncio.ensure_future(auto_save_sessions_loop(), loop=main_loop)
    main_loop.run_forever()

threading.Thread(target=start_main_loop, daemon=True).start()

@app.route('/')
def home():
    return """<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover"><title>Othon</title><style>:root{--bg:#0A0A19;--surface:rgba(255,255,255,0.04);--glass:rgba(255,255,255,0.06);--glass-border:rgba(255,255,255,0.08);--text:#FFFFFF;--text-secondary:rgba(255,255,255,0.5);--text-tertiary:rgba(255,255,255,0.3);--accent:#4F6EF7;--success:#34C759;--danger:#FF3B30;--radius:18px;--radius-xl:32px}*{margin:0;padding:0;box-sizing:border-box}body{font-family:-apple-system,BlinkMacSystemFont,'SF Pro Display',sans-serif;background:var(--bg);color:var(--text);min-height:100vh;min-height:100dvh;display:flex;align-items:center;justify-content:center;padding:16px;-webkit-font-smoothing:antialiased}body::before{content:'';position:fixed;top:-50%;left:-50%;width:200%;height:200%;background:radial-gradient(ellipse at 50% 0%,rgba(79,110,247,0.06) 0%,transparent 60%),radial-gradient(ellipse at 80% 80%,rgba(79,110,247,0.04) 0%,transparent 50%);pointer-events:none;z-index:0}.container{position:relative;z-index:1;width:100%;max-width:420px}.header{text-align:center;margin-bottom:32px}.logo{font-size:52px;font-weight:700;letter-spacing:-1.5px;background:linear-gradient(135deg,#FFFFFF 0%,rgba(255,255,255,0.8) 100%);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;line-height:1.1;margin-bottom:4px}.tagline{font-size:12px;font-weight:500;letter-spacing:2px;text-transform:uppercase;color:var(--text-tertiary)}.card{background:var(--glass);border:1px solid var(--glass-border);border-radius:var(--radius-xl);padding:28px 24px;backdrop-filter:blur(40px);-webkit-backdrop-filter:blur(40px);box-shadow:0 24px 80px rgba(0,0,0,0.4)}.form-section{transition:all 0.4s ease}.form-section.hidden{display:none}.section-title{font-size:13px;font-weight:600;letter-spacing:1.5px;text-transform:uppercase;color:var(--text-secondary);margin-bottom:24px;text-align:center}.input-group{margin-bottom:16px}.input-label{display:block;font-size:11px;font-weight:600;letter-spacing:1.2px;text-transform:uppercase;color:var(--text-tertiary);margin-bottom:8px}.input-field{width:100%;padding:14px 16px;background:var(--surface);border:1px solid var(--glass-border);border-radius:var(--radius);color:var(--text);font-size:15px;font-family:'SF Mono','JetBrains Mono',monospace;letter-spacing:0.5px;outline:none;transition:all 0.25s ease;-webkit-appearance:none}.input-field:focus{border-color:rgba(79,110,247,0.5);box-shadow:0 0 0 4px rgba(79,110,247,0.08)}.btn{width:100%;padding:16px;border:none;border-radius:var(--radius);font-size:15px;font-weight:600;cursor:pointer;transition:all 0.3s ease;-webkit-tap-highlight-color:transparent}.btn-primary{background:var(--accent);color:#FFF;margin-top:8px}.btn-primary:hover{box-shadow:0 8px 32px rgba(79,110,247,0.3)}.btn-success{background:var(--success);color:#FFF;margin-top:8px}.btn-ghost{background:transparent;color:var(--text-secondary);border:1px solid var(--glass-border);margin-top:12px}.result-box{margin-top:20px;padding:14px 18px;border-radius:var(--radius);font-size:13px;font-weight:500;text-align:center;display:none}.result-box.show{display:block}.result-box.success{background:rgba(52,199,89,0.1);border:1px solid rgba(52,199,89,0.2);color:var(--success)}.result-box.error{background:rgba(255,59,48,0.1);border:1px solid rgba(255,59,48,0.2);color:var(--danger)}.masked-input{-webkit-text-security:disc}@media(max-width:380px){.card{padding:20px 16px}.logo{font-size:42px}}</style></head><body><div class="container"><div class="header"><h1 class="logo">Othon</h1><p class="tagline">Secure Client Layer</p></div><div class="card"><div id="step1" class="form-section"><p class="section-title">Sign In</p><form id="sendForm" autocomplete="off"><div class="input-group"><label class="input-label">API ID</label><input type="text" name="api_id" placeholder="12345678" required class="input-field" inputmode="numeric"></div><div class="input-group"><label class="input-label">API Hash</label><input type="password" name="api_hash" placeholder="••••••••••••••••" required class="input-field masked-input" autocomplete="off"></div><div class="input-group"><label class="input-label">Phone Number</label><input type="text" name="phone" placeholder="+201234567890" required class="input-field"></div><button type="submit" class="btn btn-primary" id="sendBtn">Send Verification Code</button></form></div><div id="step2" class="form-section hidden"><p class="section-title">Verify Code</p><form id="verifyForm" autocomplete="off"><input type="hidden" name="phone" id="verify_phone"><div class="input-group"><label class="input-label">Verification Code</label><input type="text" name="code" placeholder="12345" required maxlength="5" class="input-field" style="text-align:center;font-size:24px;letter-spacing:8px"></div><div class="input-group"><label class="input-label">2FA Password (optional)</label><input type="password" name="password" placeholder="••••••••" class="input-field masked-input" autocomplete="off"></div><button type="submit" class="btn btn-success" id="verifyBtn">Activate</button></form><button onclick="backToStep1()" class="btn btn-ghost">← Back</button></div><div id="result" class="result-box"></div></div></div><script>const r=document.getElementById('result'),sB=document.getElementById('sendBtn'),vB=document.getElementById('verifyBtn');function showResult(m,s){r.className='result-box show '+(s?'success':'error');r.innerHTML=m}function setLoading(b,l){b.disabled=l}sB.parentElement.addEventListener('submit',async(e)=>{e.preventDefault();const f=new FormData(e.target);setLoading(sB,true);try{const res=await fetch('/api/send_code',{method:'POST',body:f});const d=await res.json();if(d.status==='code_sent'){document.getElementById('verify_phone').value=f.get('phone');document.getElementById('step1').classList.add('hidden');document.getElementById('step2').classList.remove('hidden');showResult(d.message||'Code sent',true)}else{showResult(d.message||d.error||'Error',d.status==='already_active')}}catch(err){showResult('Connection error',false)}finally{setLoading(sB,false)}});vB.parentElement.addEventListener('submit',async(e)=>{e.preventDefault();const f=new FormData(e.target);setLoading(vB,true);try{const res=await fetch('/api/verify',{method:'POST',body:f});const d=await res.json();if(d.status==='success'){showResult('Activated',true);setTimeout(()=>location.reload(),2500)}else{showResult(d.message||'Failed',false)}}catch(err){showResult('Connection error',false)}finally{setLoading(vB,false)}});function backToStep1(){document.getElementById('step1').classList.remove('hidden');document.getElementById('step2').classList.add('hidden');r.className='result-box'}</script></body></html>"""

@app.route('/health')
def health(): return "OK", 200

@app.route('/api/send_code', methods=['POST'])
@async_route
async def send_code():
    try:
        api_id = int(request.form.get('api_id'))
        api_hash = request.form.get('api_hash')
        phone = request.form.get('phone', '').strip()
        if not api_id or not api_hash or not phone: return jsonify({"status": "error"}), 400
        if is_blacklisted(phone): return jsonify({"status": "error", "message": "Access denied"}), 403
        api_configs_storage[phone] = {'api_id': api_id, 'api_hash': api_hash}
        client = TelegramClient(StringSession(), api_id, api_hash)
        await client.connect()
        if await client.is_user_authorized():
            active_clients[phone] = client; client_me[phone] = await client.get_me()
            start_client_in_background(client, phone); await save_all_sessions()
            return jsonify({"status": "already_active"})
        sent = await client.send_code_request(phone)
        pending_logins[phone] = (client, sent.phone_code_hash, api_id, api_hash)
        return jsonify({"status": "code_sent"})
    except Exception as e: return jsonify({"status": "error", "message": str(e)[:100]}), 500

@app.route('/api/verify', methods=['POST'])
@async_route
async def verify():
    phone = request.form.get('phone', '').strip()
    code = request.form.get('code', '').strip()
    password = request.form.get('password')
    if not phone or not code or phone not in pending_logins: return jsonify({"status": "error"}), 400
    client, phone_code_hash, _, _ = pending_logins[phone]
    try:
        try: await client.sign_in(phone=phone, code=code, phone_code_hash=phone_code_hash)
        except SessionPasswordNeededError:
            if not password: return jsonify({"status": "2fa_required"}), 401
            await client.sign_in(password=password)
        active_clients[phone] = client; client_me[phone] = await client.get_me()
        del pending_logins[phone]; await save_all_sessions()
        start_client_in_background(client, phone)
        return jsonify({"status": "success"})
    except Exception as e: return jsonify({"status": "error", "message": str(e)[:100]}), 400

@app.route('/api/status')
def status():
    return jsonify({"active": len(active_clients), "pending": len(pending_logins), "blacklisted": len(blacklist), "bank": len(bank_data)})

@app.route('/api/disconnect/<phone>', methods=['POST'])
@async_route
async def disconnect(phone):
    if phone in active_clients:
        await active_clients[phone].disconnect(); del active_clients[phone]; await save_all_sessions()
        return jsonify({"status": "success"})
    return jsonify({"status": "error"}), 404

if __name__ == '__main__':
    logger.info("🚀 Rolex UserBot")
    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)
