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
    
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.سورس$'))
    async def src(event):
        await event.edit("**تيليثون ڪيوجـࢪام 𔓕**\n\n• لتنصيب السورس [إضغط هنا](https://t.me/Q_g_r_a_m)\n• لمتابعة التحديثات [إضغط هنا](https://t.me/Q_g_r_a_m)", parse_mode='md')
    
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
غيوم
قلوب
ورود
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
        except:
            await event.edit("**• فشل**")
    
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.بايو (.+)'))
    async def bio(event):
        try:
            await client(UpdateProfileRequest(about=event.pattern_match.group(1).strip()))
            await event.edit("**• تم تغيير البايو**")
        except:
            await event.edit("**• فشل**")
    
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
    
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.عدد$'))
    async def msg_count(event):
        await event.edit("**• جاري العد**")
        try:
            history = await client(GetHistoryRequest(peer=event.input_chat, limit=0, offset_date=None, offset_id=0, add_offset=0, max_id=0, min_id=0, hash=0))
            await event.edit(f"**ꪔᥲ᥉᥉ᥲᧁꫀ᥉ {history.count}**")
        except:
            await event.edit("**• فشل**")
    
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
    async def laugh(event):
        await animate_emojis(event, LAUGH_FRAMES, 0.4)
    
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.غيوم$'))
    async def clouds(event):
        await animate_emojis(event, CLOUD_FRAMES, 0.4)
    
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.قلوب$'))
    async def hearts(event):
        await animate_emojis(event, HEART_FRAMES, 0.4)
    
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.ورود$'))
    async def roses(event):
        await animate_emojis(event, ROSE_FRAMES, 0.4)
    
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.غباء$'))
    async def stupidity(event):
        target_name = "User"
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
        await event.edit(f"**{target_name}'s stupidity: {percentage}%**")
    
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.تحويل (\d+)'))
    async def transfer(event):
        amount = event.pattern_match.group(1)
        target_name = "User"
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
        await event.edit(f"**Sent {amount} USD to beggar {target_name}**")
    
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.رفع شحات$'))
    async def raf3_shahat(event):
        target_name = "User"
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
        await event.edit(f"**Promoted {target_name} to Beggar**")
    
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.رفع حمار$'))
    async def raf3_hmar(event):
        target_name = "User"
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
        await event.edit(f"**Promoted {target_name} to Donkey**")
    
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.رفع غبي$'))
    async def raf3_ghaby(event):
        target_name = "User"
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
        await event.edit(f"**Promoted {target_name} to Stupid**")
    
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.رفع سباك$'))
    async def raf3_sabbak(event):
        target_name = "User"
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
        await event.edit(f"**Promoted {target_name} to Plumber**")
    
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.رفع مالك$'))
    async def raf3_malek(event):
        target_name = "User"
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
        await event.edit(f"**Promoted {target_name} to King**")
    
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.رفع ادمن$'))
    async def raf3_admin(event):
        target_name = "User"
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
        await event.edit(f"**Promoted {target_name} to Admin**")
    
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

# ======================== FLASK ROUTES ========================

@app.route('/')
def home():
    return """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover, user-scalable=no">
    <title>Othon</title>
    <style>
        :root {
            --bg: #0A0A19;
            --surface: rgba(255, 255, 255, 0.04);
            --glass: rgba(255, 255, 255, 0.06);
            --glass-border: rgba(255, 255, 255, 0.08);
            --glass-hover: rgba(255, 255, 255, 0.1);
            --text: #FFFFFF;
            --text-secondary: rgba(255, 255, 255, 0.5);
            --text-tertiary: rgba(255, 255, 255, 0.3);
            --accent: #4F6EF7;
            --accent-glow: rgba(79, 110, 247, 0.3);
            --success: #34C759;
            --danger: #FF3B30;
            --radius-sm: 12px;
            --radius: 18px;
            --radius-lg: 24px;
            --radius-xl: 32px;
            --font-mono: 'SF Mono', 'JetBrains Mono', 'Fira Code', monospace;
        }

        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Display', 'Segoe UI', system-ui, sans-serif;
            background: var(--bg);
            color: var(--text);
            min-height: 100vh;
            min-height: 100dvh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 16px;
            -webkit-font-smoothing: antialiased;
            -moz-osx-font-smoothing: grayscale;
            overflow-x: hidden;
        }

        /* Ambient background glow */
        body::before {
            content: '';
            position: fixed;
            top: -50%;
            left: -50%;
            width: 200%;
            height: 200%;
            background: radial-gradient(ellipse at 50% 0%, rgba(79, 110, 247, 0.06) 0%, transparent 60%),
                        radial-gradient(ellipse at 80% 80%, rgba(79, 110, 247, 0.04) 0%, transparent 50%);
            pointer-events: none;
            z-index: 0;
            animation: ambientPulse 8s ease-in-out infinite;
        }

        @keyframes ambientPulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.6; }
        }

        .container {
            position: relative;
            z-index: 1;
            width: 100%;
            max-width: 420px;
        }

        /* Header */
        .header {
            text-align: center;
            margin-bottom: 32px;
        }

        .logo {
            font-size: 52px;
            font-weight: 700;
            letter-spacing: -1.5px;
            background: linear-gradient(135deg, #FFFFFF 0%, rgba(255,255,255,0.8) 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
            line-height: 1.1;
            margin-bottom: 4px;
        }

        .tagline {
            font-size: 12px;
            font-weight: 500;
            letter-spacing: 2px;
            text-transform: uppercase;
            color: var(--text-tertiary);
        }

        /* Glass card */
        .card {
            background: var(--glass);
            border: 1px solid var(--glass-border);
            border-radius: var(--radius-xl);
            padding: 28px 24px;
            backdrop-filter: blur(40px);
            -webkit-backdrop-filter: blur(40px);
            box-shadow: 0 24px 80px rgba(0, 0, 0, 0.4),
                        0 0 0 1px rgba(255, 255, 255, 0.03) inset;
            transition: border-color 0.3s ease;
        }

        .card:hover {
            border-color: rgba(255, 255, 255, 0.12);
        }

        /* Form section */
        .form-section {
            transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1);
        }

        .form-section.hidden {
            display: none;
        }

        .section-title {
            font-size: 13px;
            font-weight: 600;
            letter-spacing: 1.5px;
            text-transform: uppercase;
            color: var(--text-secondary);
            margin-bottom: 24px;
            text-align: center;
        }

        /* Input group */
        .input-group {
            margin-bottom: 16px;
        }

        .input-label {
            display: block;
            font-size: 11px;
            font-weight: 600;
            letter-spacing: 1.2px;
            text-transform: uppercase;
            color: var(--text-tertiary);
            margin-bottom: 8px;
        }

        .input-field {
            width: 100%;
            padding: 14px 16px;
            background: var(--surface);
            border: 1px solid var(--glass-border);
            border-radius: var(--radius);
            color: var(--text);
            font-size: 15px;
            font-family: var(--font-mono);
            letter-spacing: 0.5px;
            outline: none;
            transition: all 0.25s ease;
            -webkit-appearance: none;
            appearance: none;
        }

        .input-field::placeholder {
            color: var(--text-tertiary);
            font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Display', sans-serif;
            letter-spacing: 0;
        }

        .input-field:focus {
            border-color: rgba(79, 110, 247, 0.5);
            box-shadow: 0 0 0 4px rgba(79, 110, 247, 0.08);
            background: rgba(255, 255, 255, 0.06);
        }

        /* Button */
        .btn {
            width: 100%;
            padding: 16px;
            border: none;
            border-radius: var(--radius);
            font-size: 15px;
            font-weight: 600;
            letter-spacing: 0.5px;
            cursor: pointer;
            transition: all 0.3s ease;
            -webkit-tap-highlight-color: transparent;
            -webkit-appearance: none;
            appearance: none;
            position: relative;
            overflow: hidden;
        }

        .btn-primary {
            background: var(--accent);
            color: #FFFFFF;
            margin-top: 8px;
        }

        .btn-primary:hover {
            background: #5F7EF9;
            box-shadow: 0 8px 32px var(--accent-glow);
            transform: translateY(-1px);
        }

        .btn-primary:active {
            transform: scale(0.98);
            transition: transform 0.1s ease;
        }

        .btn-success {
            background: var(--success);
            color: #FFFFFF;
            margin-top: 8px;
        }

        .btn-ghost {
            background: transparent;
            color: var(--text-secondary);
            border: 1px solid var(--glass-border);
            margin-top: 12px;
        }

        .btn-ghost:hover {
            background: var(--glass-hover);
            color: var(--text);
        }

        /* Result */
        .result-box {
            margin-top: 20px;
            padding: 14px 18px;
            border-radius: var(--radius);
            font-size: 13px;
            font-weight: 500;
            letter-spacing: 0.3px;
            text-align: center;
            display: none;
            animation: fadeSlideIn 0.4s ease;
        }

        .result-box.show {
            display: block;
        }

        .result-box.success {
            background: rgba(52, 199, 89, 0.1);
            border: 1px solid rgba(52, 199, 89, 0.2);
            color: var(--success);
        }

        .result-box.error {
            background: rgba(255, 59, 48, 0.1);
            border: 1px solid rgba(255, 59, 48, 0.2);
            color: var(--danger);
        }

        @keyframes fadeSlideIn {
            from {
                opacity: 0;
                transform: translateY(8px);
            }
            to {
                opacity: 1;
                transform: translateY(0);
            }
        }

        /* Status link */
        .status-link {
            display: block;
            text-align: center;
            margin-top: 20px;
            font-size: 11px;
            font-weight: 500;
            letter-spacing: 1.5px;
            text-transform: uppercase;
            color: var(--text-tertiary);
            text-decoration: none;
            transition: color 0.3s ease;
        }

        .status-link:hover {
            color: var(--text-secondary);
        }

        /* Password field wrapper for hidden state */
        .input-password-wrapper {
            position: relative;
        }

        .input-password-wrapper input {
            -webkit-text-security: disc;
        }

        /* Loading state */
        .btn.loading {
            pointer-events: none;
            opacity: 0.7;
        }

        .btn.loading::after {
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
            animation: spin 0.7s linear infinite;
        }

        @keyframes spin {
            to { transform: rotate(360deg); }
        }

        /* Hide password text visually when typing */
        .masked-input {
            -webkit-text-security: disc;
            text-security: disc;
        }

        /* Responsive */
        @media (max-width: 380px) {
            .card {
                padding: 20px 16px;
            }
            .logo {
                font-size: 42px;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1 class="logo">Othon</h1>
            <p class="tagline">Secure Client Layer</p>
        </div>

        <div class="card">
            <!-- Step 1: Sign In -->
            <div id="step1" class="form-section">
                <p class="section-title">Sign In</p>
                <form id="sendForm" autocomplete="off">
                    <div class="input-group">
                        <label class="input-label">API ID</label>
                        <input type="text" name="api_id" id="api_id" placeholder="12345678" required class="input-field" inputmode="numeric" pattern="[0-9]*">
                    </div>
                    <div class="input-group">
                        <label class="input-label">API Hash</label>
                        <input type="password" name="api_hash" id="api_hash" placeholder="••••••••••••••••" required class="input-field masked-input" autocomplete="off">
                    </div>
                    <div class="input-group">
                        <label class="input-label">Phone Number</label>
                        <input type="text" name="phone" id="phone" placeholder="+201234567890" required class="input-field" inputmode="numeric">
                    </div>
                    <button type="submit" class="btn btn-primary" id="sendBtn">
                        Send Verification Code
                    </button>
                </form>
            </div>

            <!-- Step 2: Verify -->
            <div id="step2" class="form-section hidden">
                <p class="section-title">Verify Code</p>
                <form id="verifyForm" autocomplete="off">
                    <input type="hidden" name="phone" id="verify_phone">
                    <div class="input-group">
                        <label class="input-label">Verification Code</label>
                        <input type="text" name="code" id="code" placeholder="12345" required maxlength="5" class="input-field" inputmode="numeric" pattern="[0-9]*" style="text-align:center;font-size:24px;letter-spacing:8px;">
                    </div>
                    <div class="input-group">
                        <label class="input-label">2FA Password (optional)</label>
                        <input type="password" name="password" id="password" placeholder="••••••••" class="input-field masked-input" autocomplete="off">
                    </div>
                    <button type="submit" class="btn btn-success" id="verifyBtn">
                        Activate
                    </button>
                </form>
                <button onclick="backToStep1()" class="btn btn-ghost">
                    ← Back
                </button>
            </div>

            <div id="result" class="result-box"></div>
        </div>

        <a href="/api/status" class="status-link">System Status</a>
    </div>

    <script>
        const resultBox = document.getElementById('result');
        const sendBtn = document.getElementById('sendBtn');
        const verifyBtn = document.getElementById('verifyBtn');

        function showResult(message, isSuccess) {
            resultBox.className = 'result-box show ' + (isSuccess ? 'success' : 'error');
            resultBox.innerHTML = message;
        }

        function setLoading(btn, loading) {
            if (loading) {
                btn.classList.add('loading');
                btn.disabled = true;
            } else {
                btn.classList.remove('loading');
                btn.disabled = false;
            }
        }

        document.getElementById('sendForm').addEventListener('submit', async (e) => {
            e.preventDefault();
            const formData = new FormData(e.target);
            setLoading(sendBtn, true);

            try {
                const res = await fetch('/api/send_code', { method: 'POST', body: formData });
                const data = await res.json();

                if (data.status === 'code_sent') {
                    document.getElementById('verify_phone').value = formData.get('phone');
                    document.getElementById('step1').classList.add('hidden');
                    document.getElementById('step2').classList.remove('hidden');
                    showResult(data.message || 'Code sent successfully', true);
                } else if (data.status === 'already_active') {
                    showResult('Session already active', true);
                } else {
                    showResult(data.message || data.error || 'An error occurred', false);
                }
            } catch (error) {
                showResult('Connection error', false);
            } finally {
                setLoading(sendBtn, false);
            }
        });

        document.getElementById('verifyForm').addEventListener('submit', async (e) => {
            e.preventDefault();
            const formData = new FormData(e.target);
            setLoading(verifyBtn, true);

            try {
                const res = await fetch('/api/verify', { method: 'POST', body: formData });
                const data = await res.json();

                if (data.status === 'success') {
                    showResult('Activated successfully', true);
                    setTimeout(() => location.reload(), 2500);
                } else {
                    showResult(data.message || 'Activation failed', false);
                }
            } catch (error) {
                showResult('Connection error', false);
            } finally {
                setLoading(verifyBtn, false);
            }
        });

        function backToStep1() {
            document.getElementById('step1').classList.remove('hidden');
            document.getElementById('step2').classList.add('hidden');
            resultBox.className = 'result-box';
        }
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
            return jsonify({"status": "already_active", "message": "Session active"})
        sent = await client.send_code_request(phone)
        pending_logins[phone] = (client, sent.phone_code_hash, api_id, api_hash)
        return jsonify({"status": "code_sent", "message": "Code sent"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)[:100]}), 500

@app.route('/api/verify', methods=['POST'])
@async_route
async def verify():
    phone = request.form.get('phone', '').strip()
    code = request.form.get('code', '').strip()
    password = request.form.get('password')
    if not phone or not code or phone not in pending_logins:
        return jsonify({"status": "error", "message": "Invalid data"}), 400
    client, phone_code_hash, _, _ = pending_logins[phone]
    try:
        try:
            await client.sign_in(phone=phone, code=code, phone_code_hash=phone_code_hash)
        except SessionPasswordNeededError:
            if not password:
                return jsonify({"status": "2fa_required", "message": "2FA required"}), 401
            await client.sign_in(password=password)
        active_clients[phone] = client
        client_me[phone] = await client.get_me()
        del pending_logins[phone]
        await save_all_sessions()
        start_client_in_background(client, phone)
        return jsonify({"status": "success", "message": "Activated"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)[:100]}), 400

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
    logger.info("🚀 Othon Server")
    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)
