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

from flask import Flask, jsonify, request
from telethon import TelegramClient, events
from telethon.errors import SessionPasswordNeededError, FloodWaitError
from telethon.sessions import StringSession
from telethon.tl.functions.account import UpdateProfileRequest
from telethon.tl.functions.contacts import BlockRequest, UnblockRequest, ImportContactsRequest
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.tl.functions.messages import ToggleDialogPinRequest, GetHistoryRequest, GetDialogsRequest, EditChatDefaultBannedRightsRequest
from telethon.tl.functions.phone import RequestCallRequest
from telethon.tl.types import InputPeerChannel, InputPeerUser, InputPhoneContact, ChatBannedRights, PhoneCallProtocol

DATA_DIR = '/data' if os.path.exists('/data') else '.'
os.makedirs(DATA_DIR, exist_ok=True)
SESSION_FILE = os.path.join(DATA_DIR, 'active_sessions.json')
API_CONFIG_FILE = os.path.join(DATA_DIR, 'api_config.json')

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', handlers=[logging.StreamHandler(sys.stdout)])
logger = logging.getLogger(__name__)

app = Flask(__name__)

SOURCE_CHANNEL = "https://t.me/Q_g_r_a_m"
SOURCE_CHANNEL_USERNAME = "Q_g_r_a_m"
GEMINI_API_KEY = "AQ.Ab8RN6IJ52RfamXKX6nNJOglTwDarnQyUIh9uzITyqK5iqwm7w"

main_loop = asyncio.new_event_loop()

active_clients: Dict[str, TelegramClient] = {}
pending_logins: Dict[str, Tuple[TelegramClient, str, int, str]] = {}
api_configs_storage: Dict[str, Dict] = {}

muted_users: Dict[str, Dict[int, bool]] = {}
taqleed_users: Dict[str, Dict[int, bool]] = {}
banned_users: Dict[str, Dict[int, bool]] = {}
bold_mode: Dict[str, bool] = {}
client_me: Dict[str, any] = {}

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

def ask_gemini(question: str) -> str:
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
        headers = {'Content-Type': 'application/json'}
        data = {"contents": [{"parts": [{"text": question}]}], "generationConfig": {"temperature": 0.7, "maxOutputTokens": 1000}}
        response = requests.post(url, headers=headers, json=data, timeout=30)
        if response.status_code != 200:
            return None
        result = response.json()
        if 'candidates' in result and len(result['candidates']) > 0:
            candidate = result['candidates'][0]
            if 'content' in candidate and 'parts' in candidate['content']:
                for part in candidate['content']['parts']:
                    if 'text' in part and part['text'].strip():
                        return part['text'].strip()[:2000]
        return None
    except:
        return None

# ======================== إدارة الجلسات ========================

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
                await client.send_message('me', "**تيليثون ڪيوجـࢪام 𔓕**\n\n• لتنصيب السورس [إضغط هنا](https://t.me/Q_g_r_a_m)\n• لمتابعة التحديثات [إضغط هنا](https://t.me/Q_g_r_a_m)", parse_mode='md')
            except:
                pass
            await client.run_until_disconnected()
        except Exception as e:
            logger.error(f"Error {phone}: {e}")
    asyncio.run_coroutine_threadsafe(run_client(), main_loop)

# ======================== أوامر ترفيهية ========================

LAUGH_EMOJIS = [
    "😂🤣😭😹", "🤣😹😂😭", "😭😂😹🤣", "😹🤣😭😂",
    "😂😹🤣😭", "🤣😭😹😂", "😭😹😂🤣", "😹😂🤣😭",
    "😂🤣😹😭", "🤣😂😭😹", "😭🤣😂😹", "😹😭🤣😂",
    "😂😭😹🤣", "🤣😹😭😂", "😭😹🤣😂", "😹🤣😂😭"
]

RAF3_TYPES = {
    "شحات": "شحات",
    "حمار": "حمار", 
    "غبي": "غبي",
    "سباك": "سباك",
    "مالك": "مالك",
    "ادمن": "أدمن"
}

def get_target_name(event):
    """استخراج اسم الهدف من الرد أو المحادثة"""
    if event.is_reply:
        return (await event.get_reply_message()).sender_id
    elif event.is_private:
        return event.chat_id
    return None

async def get_user_name(client, user_id):
    """جلب اسم المستخدم"""
    try:
        user = await client.get_entity(user_id)
        return user.first_name or "المستخدم"
    except:
        return "المستخدم"

# ======================== إعداد handlers ========================

async def setup_handlers(client, phone):
    if phone not in muted_users:
        muted_users[phone] = {}
    if phone not in taqleed_users:
        taqleed_users[phone] = {}
    if phone not in banned_users:
        banned_users[phone] = {}
    if phone not in bold_mode:
        bold_mode[phone] = False
    
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
ذكاء + سؤال
بوت + سؤال
صراحة
كت
ضحك
غباء
تحويل + رقم
رفع شحات
رفع حمار
رفع غبي
رفع سباك
رفع مالك
رفع ادمن
اوامر
سورس""", parse_mode='md')
    
    # ==================== ايدي / ا ====================
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.(ايدي|ا)$'))
    async def id_cmd(event):
        await event.delete()
        user = None
        if event.is_reply:
            user = await client.get_entity((await event.get_reply_message()).sender_id)
        elif event.is_group:
            user = await client.get_entity(event.sender_id)
        else:
            user = await client.get_entity(event.chat_id)
        if not user:
            return
        lines = [f"ꪀᥲꪔꫀ {user.first_name or ''} {user.last_name or ''}".strip()]
        if user.username:
            lines.append(f"ᥙ᥉ꫀɾ @{user.username}")
        try:
            full = await client.get_entity(user.id)
            if hasattr(full, 'about') and full.about:
                lines.append(f"ᑲᎥ᥆ {full.about[:50]}")
        except:
            pass
        lines.append(f"Ꭵძ {user.id}")
        await client.send_message(event.chat_id, "\n".join(lines))
    
    # ==================== تقليد ====================
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.تقليد$'))
    async def taq(event):
        target = None
        if event.is_reply:
            target = (await event.get_reply_message()).sender_id
        elif event.is_private:
            target = event.chat_id
        if target:
            taqleed_users[phone][target] = True
            await event.edit("**• يتم التقليد**")
    
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.غ تقليد$'))
    async def notaq(event):
        target = None
        if event.is_reply:
            target = (await event.get_reply_message()).sender_id
        elif event.is_private:
            target = event.chat_id
        if target and target in taqleed_users.get(phone, {}):
            del taqleed_users[phone][target]
        await event.edit("**• تم فك التقليد**")
    
    # ==================== خط / غ خط ====================
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.خط$'))
    async def bold(event):
        bold_mode[phone] = True
        await event.edit("**• تم تفعيل الخط العريض**")
    
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.غ خط$'))
    async def nobold(event):
        bold_mode[phone] = False
        await event.edit("**• تم الغاء الخط العريض**")
    
    # ==================== اسم ====================
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.اسم (.+)'))
    async def name(event):
        try:
            await client(UpdateProfileRequest(first_name=event.pattern_match.group(1).strip(), last_name=''))
            await event.edit("**• تم تغيير الاسم**")
        except:
            await event.edit("**• فشل**")
    
    # ==================== بايو ====================
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.بايو (.+)'))
    async def bio(event):
        try:
            await client(UpdateProfileRequest(about=event.pattern_match.group(1).strip()))
            await event.edit("**• تم تغيير البايو**")
        except:
            await event.edit("**• فشل**")
    
    # ==================== ث / غ ث ====================
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.ث$'))
    async def pin_msg(event):
        try:
            if event.is_reply:
                await (await event.get_reply_message()).pin()
                await event.edit("**• تم التثبيت**")
            else:
                await client(ToggleDialogPinRequest(peer=event.input_chat, pinned=True))
                await event.edit("**• تم تثبيت المحادثة**")
        except:
            await event.edit("**• فشل**")
    
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.غ ث$'))
    async def unpin_msg(event):
        try:
            if event.is_reply:
                await (await event.get_reply_message()).unpin()
                await event.edit("**• تم الغاء التثبيت**")
            else:
                await client(ToggleDialogPinRequest(peer=event.input_chat, pinned=False))
                await event.edit("**• تم الغاء تثبيت المحادثة**")
        except:
            await event.edit("**• فشل**")
    
    # ==================== اضافة ====================
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
                        await client(ImportContactsRequest([contact]))
                        added += 1
                        await asyncio.sleep(0.5)
                except:
                    pass
            await event.edit(f"**• تم اضافة {added} جهة**")
        except:
            await event.edit("**• فشل**")
    
    # ==================== عدد ====================
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.عدد$'))
    async def msg_count(event):
        await event.edit("**• جاري العد**")
        try:
            history = await client(GetHistoryRequest(peer=event.input_chat, limit=0, offset_date=None, offset_id=0, add_offset=0, max_id=0, min_id=0, hash=0))
            await event.edit(f"**ꪔᥲ᥉᥉ᥲᧁꫀ᥉ {history.count}**")
        except:
            await event.edit("**• فشل**")
    
    # ==================== حذف ====================
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.حذف (\d+)$'))
    async def delete_count(event):
        count = int(event.pattern_match.group(1))
        await event.edit(f"**• جاري حذف {count} رسالة**")
        try:
            messages = await client.get_messages(event.chat_id, limit=count)
            await client.delete_messages(event.chat_id, [m.id for m in messages])
            await event.edit(f"**• تم حذف {len(messages)} رسالة**")
        except:
            await event.edit("**• فشل**")
    
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.حذف$'))
    async def delete_reply(event):
        if event.is_reply:
            try:
                await (await event.get_reply_message()).delete()
                await event.delete()
            except:
                await event.edit("**• فشل**")
    
    # ==================== رن ====================
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.رن$'))
    async def call(event):
        await event.edit("**• جاري الاتصال**")
        try:
            target = None
            if event.is_private:
                target = event.chat_id
            elif event.is_reply:
                target = (await event.get_reply_message()).sender_id
            if target:
                await client(RequestCallRequest(user_id=target, g_a_hash=b'', protocol=PhoneCallProtocol()))
                await event.edit("**• تم الاتصال**")
            else:
                await event.edit("**• فشل**")
        except:
            await event.edit("**• فشل الاتصال**")
    
    # ==================== قفل / فتح ====================
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.قفل$'))
    async def lock(event):
        if event.is_group:
            try:
                rights = ChatBannedRights(until_date=None, send_messages=True, send_media=True, send_stickers=True, send_gifs=True, send_games=True, send_inline=True, send_polls=True, change_info=True, invite_users=True, pin_messages=True)
                await client(EditChatDefaultBannedRightsRequest(peer=event.input_chat, banned_rights=rights))
                await event.edit("**• تم قفل الجروب**")
            except:
                await event.edit("**• فشل**")
    
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.فتح$'))
    async def unlock(event):
        if event.is_group:
            try:
                rights = ChatBannedRights(until_date=None, send_messages=False, send_media=False, send_stickers=False, send_gifs=False, send_games=False, send_inline=False, send_polls=False, change_info=False, invite_users=False, pin_messages=False)
                await client(EditChatDefaultBannedRightsRequest(peer=event.input_chat, banned_rights=rights))
                await event.edit("**• تم فتح الجروب**")
            except:
                await event.edit("**• فشل**")
    
    # ==================== كتم / غ كتم ====================
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.كتم$'))
    async def mute(event):
        target = None
        if event.is_reply:
            target = (await event.get_reply_message()).sender_id
        elif event.is_private:
            target = event.chat_id
        if target:
            muted_users[phone][target] = True
        await event.edit("**• تم الكتم**")
    
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.غ كتم$'))
    async def unmute(event):
        target = None
        if event.is_reply:
            target = (await event.get_reply_message()).sender_id
        elif event.is_private:
            target = event.chat_id
        if target and target in muted_users.get(phone, {}):
            del muted_users[phone][target]
        await event.edit("**• تم فك الكتم**")
    
    # ==================== حظر / غ حظر ====================
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.حظر$'))
    async def ban(event):
        target = None
        if event.is_reply:
            target = (await event.get_reply_message()).sender_id
        elif event.is_private:
            target = event.chat_id
        if target:
            try:
                await client(BlockRequest(target))
                banned_users[phone][target] = True
                await event.edit("**• تم الحظر**")
            except:
                await event.edit("**• فشل**")
    
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.غ حظر$'))
    async def unban(event):
        target = None
        if event.is_reply:
            target = (await event.get_reply_message()).sender_id
        elif event.is_private:
            target = event.chat_id
        if target:
            try:
                await client(UnblockRequest(target))
                if target in banned_users.get(phone, {}):
                    del banned_users[phone][target]
                await event.edit("**• تم فك الحظر**")
            except:
                await event.edit("**• فشل**")
    
    # ==================== تقيد / غ تقييد ====================
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.تقيد$'))
    async def restrict(event):
        if event.is_group and event.is_reply:
            try:
                await client.edit_permissions(event.chat_id, (await event.get_reply_message()).sender_id, send_messages=False)
                await event.edit("**• تم التقييد**")
            except:
                await event.edit("**• فشل**")
    
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.غ تقييد$'))
    async def unrestrict(event):
        if event.is_group and event.is_reply:
            try:
                await client.edit_permissions(event.chat_id, (await event.get_reply_message()).sender_id, send_messages=True)
                await event.edit("**• تم فك التقييد**")
            except:
                await event.edit("**• فشل**")
    
    # ==================== تهكير ====================
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.تهكير$'))
    async def hack(event):
        n = "الضحية"
        if event.is_reply:
            try:
                n = (await client.get_entity((await event.get_reply_message()).sender_id)).first_name
            except:
                pass
        await event.edit("**جاري التهكير**")
        await asyncio.sleep(1)
        await event.edit("**تم اختراق 50%**")
        await asyncio.sleep(1)
        await event.edit(f"**تم تهكير {n} بنجاح**")
    
    # ==================== ذكاء ====================
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.ذكاء (.+)'))
    async def ai_cmd(event):
        question = event.pattern_match.group(1).strip()
        await event.edit("**• جاري التفكير**")
        answer = await asyncio.get_event_loop().run_in_executor(None, ask_gemini, question)
        await event.edit(f"**{answer}**" if answer else "**• فشل**")
    
    # ==================== بوت ====================
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.بوت (.+)'))
    async def bot_cmd(event):
        question = event.pattern_match.group(1).strip()
        await event.edit("**• جاري التفكير**")
        prompt = f"أنت بوت تيليجرام اسمه كيوجرام. أجب بالعربية. {question}"
        answer = await asyncio.get_event_loop().run_in_executor(None, ask_gemini, prompt)
        await event.edit(f"**{answer}**" if answer else "**• فشل**")
    
    # ==================== صراحة ====================
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.صراحة$'))
    async def sarah(event):
        await event.edit("**• جاري توليد سؤال صراحة**")
        prompt = "أعطني سؤال صراحة واحد فقط، سؤال جريء ومحرج للعبة الصراحة بين الأصدقاء. أجب بالسؤال فقط."
        answer = await asyncio.get_event_loop().run_in_executor(None, ask_gemini, prompt)
        await event.edit(f"**{answer}**" if answer else "**• فشل**")
    
    # ==================== كت ====================
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.كت$'))
    async def kat(event):
        await event.edit("**• جاري توليد سؤال**")
        prompt = "أعطني سؤال واحد من أسئلة لعبة كت، سؤال جريء ومحرخ. أجب بالسؤال فقط."
        answer = await asyncio.get_event_loop().run_in_executor(None, ask_gemini, prompt)
        await event.edit(f"**{answer}**" if answer else "**• فشل**")
    
    # ==================== ضحك ====================
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.ضحك$'))
    async def laugh(event):
        emojis = random.choice(LAUGH_EMOJIS)
        await event.edit(f"**{emojis}**")
    
    # ==================== غباء ====================
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.غباء$'))
    async def stupidity(event):
        target_name = "المستخدم"
        if event.is_reply:
            try:
                reply = await event.get_reply_message()
                target_name = await get_user_name(client, reply.sender_id)
            except:
                pass
        elif event.is_private:
            try:
                target_name = await get_user_name(client, event.chat_id)
            except:
                pass
        
        percentage = random.randint(60, 100)
        await event.edit(f"**نسبة غباء {target_name} {percentage}%**")
    
    # ==================== تحويل ====================
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.تحويل (\d+)'))
    async def transfer(event):
        amount = event.pattern_match.group(1)
        target_name = "المستخدم"
        if event.is_reply:
            try:
                reply = await event.get_reply_message()
                target_name = await get_user_name(client, reply.sender_id)
            except:
                pass
        elif event.is_private:
            try:
                target_name = await get_user_name(client, event.chat_id)
            except:
                pass
        
        await event.edit(f"**تم إرسال {amount} دولار للشحات {target_name}** 💸")
    
    # ==================== رفع شحات ====================
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.رفع شحات$'))
    async def raf3_shahat(event):
        target_name = "المستخدم"
        if event.is_reply:
            try:
                reply = await event.get_reply_message()
                target_name = await get_user_name(client, reply.sender_id)
            except:
                pass
        elif event.is_private:
            try:
                target_name = await get_user_name(client, event.chat_id)
            except:
                pass
        await event.edit(f"**تم رفع {target_name} شحات** 🥙")
    
    # ==================== رفع حمار ====================
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.رفع حمار$'))
    async def raf3_hmar(event):
        target_name = "المستخدم"
        if event.is_reply:
            try:
                reply = await event.get_reply_message()
                target_name = await get_user_name(client, reply.sender_id)
            except:
                pass
        elif event.is_private:
            try:
                target_name = await get_user_name(client, event.chat_id)
            except:
                pass
        await event.edit(f"**تم رفع {target_name} حمار** 🐴")
    
    # ==================== رفع غبي ====================
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.رفع غبي$'))
    async def raf3_ghaby(event):
        target_name = "المستخدم"
        if event.is_reply:
            try:
                reply = await event.get_reply_message()
                target_name = await get_user_name(client, reply.sender_id)
            except:
                pass
        elif event.is_private:
            try:
                target_name = await get_user_name(client, event.chat_id)
            except:
                pass
        await event.edit(f"**تم رفع {target_name} غبي** 🤪")
    
    # ==================== رفع سباك ====================
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.رفع سباك$'))
    async def raf3_sabbak(event):
        target_name = "المستخدم"
        if event.is_reply:
            try:
                reply = await event.get_reply_message()
                target_name = await get_user_name(client, reply.sender_id)
            except:
                pass
        elif event.is_private:
            try:
                target_name = await get_user_name(client, event.chat_id)
            except:
                pass
        await event.edit(f"**تم رفع {target_name} سباك** 🔧")
    
    # ==================== رفع مالك ====================
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.رفع مالك$'))
    async def raf3_malek(event):
        target_name = "المستخدم"
        if event.is_reply:
            try:
                reply = await event.get_reply_message()
                target_name = await get_user_name(client, reply.sender_id)
            except:
                pass
        elif event.is_private:
            try:
                target_name = await get_user_name(client, event.chat_id)
            except:
                pass
        await event.edit(f"**تم رفع {target_name} مالك** 👑")
    
    # ==================== رفع ادمن ====================
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.رفع ادمن$'))
    async def raf3_admin(event):
        target_name = "المستخدم"
        if event.is_reply:
            try:
                reply = await event.get_reply_message()
                target_name = await get_user_name(client, reply.sender_id)
            except:
                pass
        elif event.is_private:
            try:
                target_name = await get_user_name(client, event.chat_id)
            except:
                pass
        await event.edit(f"**تم رفع {target_name} أدمن** ⭐")
    
    # ==================== فحص القناة ====================
    async def channel_check():
        while True:
            await asyncio.sleep(600)
            try:
                await ensure_subscription(client, phone)
            except:
                pass
    
    asyncio.ensure_future(channel_check(), loop=main_loop)
    logger.info(f"✅ Handlers: {phone}")

def start_main_loop():
    asyncio.set_event_loop(main_loop)
    main_loop.run_until_complete(load_all_sessions())
    asyncio.ensure_future(auto_save_sessions_loop(), loop=main_loop)
    main_loop.run_forever()

threading.Thread(target=start_main_loop, daemon=True).start()

# ======================== Flask ========================

@app.route('/')
def home():
    return """<!DOCTYPE html><html lang="ar" dir="rtl"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>qgram-bot</title><script src="https://cdn.tailwindcss.com"></script><style>body{background:linear-gradient(135deg,#1e3a8a,#3b82f6)}.card{background:rgba(255,255,255,0.95)}</style></head><body class="min-h-screen flex items-center justify-center p-4"><div class="max-w-lg w-full"><div class="card rounded-3xl shadow-2xl p-8"><div class="text-center mb-8"><h1 class="text-4xl font-bold text-blue-700 mb-2">qgram-bot</h1><p class="text-gray-600">Telegram UserBot</p></div><div id="form-section"><div id="step1"><h2 class="text-2xl font-semibold mb-6 text-center">تسجيل الدخول</h2><form id="sendForm" class="space-y-5"><div><label class="block text-sm font-medium text-gray-700 mb-1">API ID</label><input type="text" name="api_id" placeholder="12345678" required class="w-full px-4 py-3 border border-gray-300 rounded-xl focus:outline-none focus:border-blue-500"></div><div><label class="block text-sm font-medium text-gray-700 mb-1">API HASH</label><input type="text" name="api_hash" placeholder="0123456789abcdef..." required class="w-full px-4 py-3 border border-gray-300 rounded-xl focus:outline-none focus:border-blue-500"></div><div><label class="block text-sm font-medium text-gray-700 mb-1">رقم الهاتف</label><input type="text" name="phone" placeholder="+201234567890" required class="w-full px-4 py-3 border border-gray-300 rounded-xl focus:outline-none focus:border-blue-500"></div><button type="submit" class="w-full bg-blue-600 hover:bg-blue-700 text-white font-semibold py-4 rounded-2xl transition">ارسال كود التحقق</button></form></div><div id="step2" class="hidden"><h2 class="text-2xl font-semibold mb-6 text-center">ادخل كود التحقق</h2><form id="verifyForm" class="space-y-5"><input type="hidden" name="phone" id="verify_phone"><div><label class="block text-sm font-medium text-gray-700 mb-1">كود التحقق</label><input type="text" name="code" placeholder="12345" required maxlength="5" class="w-full px-4 py-3 border border-gray-300 rounded-xl focus:outline-none focus:border-blue-500 text-center text-2xl tracking-widest"></div><div><label class="block text-sm font-medium text-gray-700 mb-1">2FA (اختياري)</label><input type="password" name="password" placeholder="••••••••" class="w-full px-4 py-3 border border-gray-300 rounded-xl focus:outline-none focus:border-blue-500"></div><button type="submit" class="w-full bg-green-600 hover:bg-green-700 text-white font-semibold py-4 rounded-2xl transition">تفعيل</button></form><button onclick="backToStep1()" class="mt-4 w-full text-gray-500">العودة</button></div></div><div id="result" class="mt-6 text-center hidden"></div></div><div class="text-center mt-6"><a href="/api/status" class="text-white hover:underline">عرض الحالة</a></div></div><script>async function showResult(m,s){const d=document.getElementById('result');d.className=`mt-6 p-4 rounded-2xl text-center font-medium ${s?'bg-green-100 text-green-700':'bg-red-100 text-red-700'}`;d.innerHTML=m;d.classList.remove('hidden')}document.getElementById('sendForm').addEventListener('submit',async(e)=>{e.preventDefault();const f=new FormData(e.target);try{const r=await fetch('/api/send_code',{method:'POST',body:f});const d=await r.json();if(d.status==='code_sent'){document.getElementById('verify_phone').value=f.get('phone');document.getElementById('step1').classList.add('hidden');document.getElementById('step2').classList.remove('hidden');showResult(d.message,true)}else{showResult(d.message||d.error||'حدث خطأ',false)}}catch(err){showResult('حدث خطأ',false)}});document.getElementById('verifyForm').addEventListener('submit',async(e)=>{e.preventDefault();const f=new FormData(e.target);try{const r=await fetch('/api/verify',{method:'POST',body:f});const d=await r.json();if(d.status==='success'){showResult(d.message,true);setTimeout(()=>location.reload(),3000)}else{showResult(d.message||'فشل التفعيل',false)}}catch(err){showResult('حدث خطأ',false)}});function backToStep1(){document.getElementById('step1').classList.remove('hidden');document.getElementById('step2').classList.add('hidden');document.getElementById('result').classList.add('hidden')}</script></body></html>"""

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
            return jsonify({"status": "error"}), 400
        api_configs_storage[phone] = {'api_id': api_id, 'api_hash': api_hash}
        client = TelegramClient(StringSession(), api_id, api_hash)
        await client.connect()
        if await client.is_user_authorized():
            active_clients[phone] = client
            client_me[phone] = await client.get_me()
            start_client_in_background(client, phone)
            await save_all_sessions()
            return jsonify({"status": "already_active"})
        sent = await client.send_code_request(phone)
        pending_logins[phone] = (client, sent.phone_code_hash, api_id, api_hash)
        return jsonify({"status": "code_sent"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/verify', methods=['POST'])
@async_route
async def verify():
    phone = request.form.get('phone', '').strip()
    code = request.form.get('code', '').strip()
    password = request.form.get('password')
    if not phone or not code or phone not in pending_logins:
        return jsonify({"status": "error"}), 400
    client, phone_code_hash, _, _ = pending_logins[phone]
    try:
        try:
            await client.sign_in(phone=phone, code=code, phone_code_hash=phone_code_hash)
        except SessionPasswordNeededError:
            if not password:
                return jsonify({"status": "2fa_required"}), 401
            await client.sign_in(password=password)
        active_clients[phone] = client
        client_me[phone] = await client.get_me()
        del pending_logins[phone]
        await save_all_sessions()
        start_client_in_background(client, phone)
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400

@app.route('/api/status')
def status():
    return jsonify({"active": list(active_clients.keys()), "total": len(active_clients)})

@app.route('/api/disconnect/<phone>', methods=['POST'])
@async_route
async def disconnect(phone):
    if phone in active_clients:
        await active_clients[phone].disconnect()
        del active_clients[phone]
        await save_all_sessions()
        return jsonify({"status": "success"})
    return jsonify({"status": "error"}), 404

if __name__ == '__main__':
    logger.info("🚀 qgram UserBot - Fun Edition")
    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)
