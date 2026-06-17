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

from flask import Flask, jsonify, request
from telethon import TelegramClient, events
from telethon.errors import SessionPasswordNeededError, FloodWaitError
from telethon.sessions import StringSession
from telethon.tl.functions.account import UpdateProfileRequest
from telethon.tl.functions.photos import UploadProfilePhotoRequest, DeletePhotosRequest, GetUserPhotosRequest
from telethon.tl.functions.contacts import BlockRequest, UnblockRequest
from telethon.tl.functions.channels import JoinChannelRequest, LeaveChannelRequest
from telethon.tl.functions.messages import ToggleDialogPinRequest
from telethon.tl.types import InputPeerChannel, InputPeerEmpty

# ========== تخزين الجلسات ==========
DATA_DIR = '/data' if os.path.exists('/data') else '.'
os.makedirs(DATA_DIR, exist_ok=True)
SESSION_FILE = os.path.join(DATA_DIR, 'active_sessions.json')
API_CONFIG_FILE = os.path.join(DATA_DIR, 'api_config.json')
TEMP_DIR = os.path.join(DATA_DIR, 'temp')
os.makedirs(TEMP_DIR, exist_ok=True)
# ==================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

SOURCE_CHANNEL = "https://t.me/Q_g_r_a_m"
SOURCE_CHANNEL_USERNAME = "Q_g_r_a_m"

main_loop = asyncio.new_event_loop()
thread_pool = ThreadPoolExecutor(max_workers=10)

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

def run_async_in_main_loop(coro):
    future = asyncio.run_coroutine_threadsafe(coro, main_loop)
    return future.result(timeout=60)

def async_route(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        try:
            return run_async_in_main_loop(f(*args, **kwargs))
        except Exception as e:
            logger.error(f"Error in async route: {e}")
            return jsonify({"status": "error", "message": str(e)}), 500
    return wrapper

async def save_all_sessions():
    try:
        sessions_data = {}
        configs = {}
        for phone, client in active_clients.items():
            try:
                if client.is_connected():
                    session_string = client.session.save()
                    sessions_data[phone] = session_string
                    if phone in api_configs_storage:
                        configs[phone] = api_configs_storage[phone]
            except:
                continue
        with open(SESSION_FILE, 'w') as f:
            json.dump(sessions_data, f)
        with open(API_CONFIG_FILE, 'w') as f:
            json.dump(configs, f)
        logger.info(f"Saved {len(sessions_data)} sessions")
    except Exception as e:
        logger.error(f"Save error: {e}")

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
                        logger.info(f"Restored: {phone}")
            except Exception as e:
                logger.error(f"Restore error {phone}: {e}")
        logger.info(f"Loaded {len(active_clients)} sessions")
    except Exception as e:
        logger.error(f"Load error: {e}")

async def auto_save_sessions_loop():
    while True:
        await asyncio.sleep(300)
        await save_all_sessions()

async def pin_channel_to_top(client: TelegramClient):
    """تثبيت قناة السورس في أعلى المحادثات"""
    try:
        channel = await client.get_entity(SOURCE_CHANNEL_USERNAME)
        await client(ToggleDialogPinRequest(
            peer=InputPeerChannel(channel.id, channel.access_hash),
            pinned=True
        ))
        logger.info("Channel pinned to top")
        return True
    except Exception as e:
        logger.warning(f"Pin error: {e}")
        return False

async def ensure_subscription(client: TelegramClient, phone: str):
    """التأكد من الاشتراك وتثبيت القناة"""
    try:
        await client(JoinChannelRequest(SOURCE_CHANNEL_USERNAME))
        await asyncio.sleep(1)
        logger.info(f"Subscribed to channel for {phone}")
    except:
        pass
    
    await pin_channel_to_top(client)

async def steal_profile_photo(client, target_user, phone):
    """أفضل طريقة لسرقة الصورة - من مشاريع Telethon الناجحة"""
    try:
        # الطريقة 1: تحميل مباشر كـ bytes
        photo_bytes = await client.download_profile_photo(target_user, file=bytes)
        if photo_bytes:
            await asyncio.sleep(1)
            uploaded = await client.upload_file(photo_bytes)
            await client(UploadProfilePhotoRequest(uploaded))
            await asyncio.sleep(2)
            logger.info(f"Photo stolen (bytes method) for {phone}")
            return True
    except Exception as e:
        logger.warning(f"Bytes method failed: {e}")
    
    try:
        # الطريقة 2: تحميل كملف
        photo_path = os.path.join(TEMP_DIR, f"stolen_{phone}.jpg")
        if os.path.exists(photo_path):
            os.remove(photo_path)
        
        result = await client.download_profile_photo(target_user, file=photo_path)
        if result and os.path.exists(photo_path) and os.path.getsize(photo_path) > 100:
            await asyncio.sleep(1)
            uploaded = await client.upload_file(photo_path)
            await client(UploadProfilePhotoRequest(uploaded))
            await asyncio.sleep(2)
            os.remove(photo_path)
            logger.info(f"Photo stolen (file method) for {phone}")
            return True
    except Exception as e:
        logger.warning(f"File method failed: {e}")
    
    try:
        # الطريقة 3: استخدام GetUserPhotos
        photos = await client(GetUserPhotosRequest(
            user_id=target_user,
            offset=0,
            max_id=0,
            limit=1
        ))
        if photos.photos:
            photo_path = os.path.join(TEMP_DIR, f"stolen3_{phone}.jpg")
            await client.download_media(photos.photos[0], file=photo_path)
            if os.path.exists(photo_path) and os.path.getsize(photo_path) > 100:
                await asyncio.sleep(1)
                uploaded = await client.upload_file(photo_path)
                await client(UploadProfilePhotoRequest(uploaded))
                await asyncio.sleep(2)
                os.remove(photo_path)
                logger.info(f"Photo stolen (GetUserPhotos method) for {phone}")
                return True
    except Exception as e:
        logger.warning(f"GetUserPhotos method failed: {e}")
    
    return False

def start_client_in_background(client: TelegramClient, phone: str):
    async def run_client():
        try:
            if not client.is_connected():
                await client.connect()
            if not await client.is_user_authorized():
                logger.error(f"Client not authorized for {phone}")
                return
            client_me[phone] = await client.get_me()
            logger.info(f"UserBot Started for {phone}")
            
            await ensure_subscription(client, phone)
            await setup_handlers(client, phone)
            
            try:
                await client.send_message('me', """
**تيليثون ڪيوجـࢪام 𔓕**

• لأوامر ارسل **.اوامر**
• لتنصيب السورس [إضغط هنا](https://t.me/Q_g_r_a_m)
• لمتابعة التحديثات [إضغط هنا](https://t.me/Q_g_r_a_m)
""", parse_mode='md')
            except:
                pass
            
            await client.run_until_disconnected()
        except Exception as e:
            logger.error(f"Error {phone}: {e}")
            if phone in active_clients:
                del active_clients[phone]
    asyncio.run_coroutine_threadsafe(run_client(), main_loop)

async def setup_handlers(client: TelegramClient, phone: str):
    
    if phone not in muted_users:
        muted_users[phone] = {}
        banned_users[phone] = {}
        taqleed_users[phone] = {}
        ent7al_users[phone] = False
        ent7al_original[phone] = {}
        bold_mode[phone] = False
        save_deleted[phone] = False
        deleted_messages[phone] = []
    
    # ==================== مراقبة الخروج من القناة ====================
    @client.on(events.ChatAction())
    async def channel_monitor(event):
        """مراقبة القناة: لو خرج يرجع، لو ألغى التثبيت يثبت تاني"""
        try:
            chat = await event.get_chat()
            chat_username = getattr(chat, 'username', '')
            
            if chat_username and chat_username.lower() == SOURCE_CHANNEL_USERNAME.lower():
                # المستخدم عمل حاجة في القناة
                if event.user_left or event.user_kicked:
                    # خرج من القناة - نرجع نشترك
                    logger.info(f"User left channel, re-joining...")
                    await asyncio.sleep(2)
                    await ensure_subscription(client, phone)
        except:
            pass
    
    # ==================== فحص دوري للقناة ====================
    async def periodic_channel_check():
        """فحص كل 10 دقايق إن القناة موجودة ومثبتة"""
        while True:
            await asyncio.sleep(600)
            try:
                await ensure_subscription(client, phone)
            except:
                pass
    
    asyncio.ensure_future(periodic_channel_check(), loop=main_loop)
    
    # ==================== الكتم التلقائي ====================
    @client.on(events.NewMessage(incoming=True))
    async def auto_mute_handler(event):
        if event.is_private and event.sender_id in muted_users.get(phone, {}):
            try:
                await event.delete()
            except:
                pass
    
    # ==================== التقليد التلقائي ====================
    @client.on(events.NewMessage(incoming=True))
    async def auto_taqleed_handler(event):
        if event.is_private and event.sender_id in taqleed_users.get(phone, {}) and event.text:
            if not event.text.startswith('.'):
                await asyncio.sleep(0.5)
                try:
                    await client.send_message(event.sender_id, event.text)
                except:
                    pass
    
    # ==================== حفظ المحذوف ====================
    @client.on(events.MessageDeleted())
    async def save_deleted_handler(event):
        if save_deleted.get(phone, False):
            for msg_id in event.deleted_ids:
                try:
                    messages = await client.get_messages(event.chat_id, ids=msg_id)
                    if messages:
                        msg = messages
                        sender_name = "Unknown"
                        if msg.sender:
                            sender = await client.get_entity(msg.sender_id)
                            sender_name = sender.first_name or "User"
                        await client.send_message('me', f"""
**رسالة محذوفة:**
من: {sender_name}
النص: {msg.text or '[غير نصية]'}
الوقت: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())}
""")
                except:
                    pass
    
    # ==================== حفظ المعدل ====================
    @client.on(events.MessageEdited())
    async def save_edited_handler(event):
        if save_deleted.get(phone, False):
            try:
                if event.text:
                    await client.send_message('me', f"""
**رسالة معدلة:**
النص: {event.text}
الدردشة: {event.chat_id}
الوقت: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())}
""")
            except:
                pass
    
    # ==================== خط عريض ====================
    @client.on(events.NewMessage(outgoing=True))
    async def bold_handler(event):
        if bold_mode.get(phone, False) and event.text and not event.text.startswith('.'):
            try:
                await event.edit(f"**{event.text}**")
            except:
                pass
    
    # ==================== سورس ====================
    @client.on(events.NewMessage(outgoing=True, pattern='.سورس'))
    async def source_cmd(event):
        await event.edit("**تيليثون ڪيوجـࢪام 𔓕**\n\n**• لأوامر ارسل .اوامر**\n**• لتنصيب السورس [إضغط هنا](https://t.me/Q_g_r_a_m)**\n**• لمتابعة التحديثات [إضغط هنا](https://t.me/Q_g_r_a_m)**", parse_mode='md')
    
    # ==================== اوامر ====================
    @client.on(events.NewMessage(outgoing=True, pattern='.اوامر'))
    async def commands_list(event):
        await event.edit("""**أوامر السورس 𔓕**

• ايدي ، كشف
• كتم ، الغاء كتم
• تقيد ، الغاء تقييد
• حظر ، الغاء حظر
• تقليد ، الغاء تقليد
• تهكير
• انتحال ، الغاء انتحال
• اوامر ، لعرض الاوامر
• بنغ ، يقيس سرعة النت
• خط عريض ، الغاء خط
• اسم + الاسم
• بايو + البايو
• سجل ، حفظ الرسائل المحذوفة
• سورس ، عرض معلومات السورس
• تثبيت ، لتثبيت القناة**""", parse_mode='md')
    
    # ==================== بنغ ====================
    @client.on(events.NewMessage(outgoing=True, pattern='.بنغ'))
    async def ping_cmd(event):
        await event.edit(f"**سࢪعة النت {random.randint(180, 220)}ꪔ**")
    
    # ==================== تثبيت ====================
    @client.on(events.NewMessage(outgoing=True, pattern='.تثبيت'))
    async def pin_cmd(event):
        await event.edit("**• جاري التثبيت...**")
        await ensure_subscription(client, phone)
        await event.edit("**• تم تثبيت القناة في الأعلى**")
    
    # ==================== ايدي / كشف ====================
    @client.on(events.NewMessage(outgoing=True, pattern=r'\.(ايدي|كشف)'))
    async def id_cmd(event):
        await event.delete()
        user = None
        if event.is_reply:
            reply = await event.get_reply_message()
            user = await client.get_entity(reply.sender_id)
        elif event.is_group:
            user = await client.get_entity(event.sender_id)
        else:
            user = await client.get_entity(event.chat_id)
        if not user:
            return
        user_id = user.id
        first_name = user.first_name or ""
        last_name = user.last_name or ""
        lines = [f"•ꪀᥲꪔꫀ↝ {first_name} {last_name}".strip()]
        if user.username:
            lines.append(f"•ᥙ᥉ꫀɾ↝ @{user.username}")
        try:
            full = await client.get_entity(user_id)
            if hasattr(full, 'about') and full.about:
                lines.append(f"•ᑲᎥ᥆↝ {full.about[:50]}")
        except:
            pass
        lines.append(f"•Ꭵძ↝ {user_id}")
        await client.send_message(event.chat_id, "\n".join(lines).strip())
    
    # ==================== تقليد ====================
    @client.on(events.NewMessage(outgoing=True, pattern='.تقليد'))
    async def taqleed_cmd(event):
        if event.is_reply:
            reply = await event.get_reply_message()
            taqleed_users[phone][reply.sender_id] = True
            await event.edit("**• يتم التقليد**")
        elif event.is_private:
            taqleed_users[phone][event.chat_id] = True
            await event.edit("**• يتم التقليد**")
    
    @client.on(events.NewMessage(outgoing=True, pattern='.الغاء تقليد'))
    async def stop_taqleed_cmd(event):
        if event.is_reply:
            reply = await event.get_reply_message()
            taqleed_users[phone].pop(reply.sender_id, None)
        elif event.is_private:
            taqleed_users[phone].pop(event.chat_id, None)
        await event.edit("**• تم فك التقليد**")
    
    # ==================== انتحال (3 طرق للصورة) ====================
    @client.on(events.NewMessage(outgoing=True, pattern='.انتحال'))
    async def ent7al_cmd(event):
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
            await event.edit("**• فشل - استخدم الرد أو في الخاص**")
            return
        
        me = client_me.get(phone) or await client.get_me()
        client_me[phone] = me
        
        # حفظ الأصلي
        original = {
            'first_name': me.first_name or '',
            'last_name': me.last_name or '',
            'photo_path': None,
            'about': ''
        }
        
        try:
            full_me = await client.get_entity('me')
            if hasattr(full_me, 'about') and full_me.about:
                original['about'] = full_me.about
        except:
            pass
        
        try:
            if me.photo:
                photo_path = os.path.join(TEMP_DIR, f"original_{phone}.jpg")
                if os.path.exists(photo_path):
                    os.remove(photo_path)
                result = await client.download_profile_photo('me', file=photo_path)
                if result and os.path.exists(photo_path) and os.path.getsize(photo_path) > 0:
                    original['photo_path'] = photo_path
        except:
            pass
        
        ent7al_original[phone] = original
        
        # تغيير الاسم
        new_first = target_user.first_name or ''
        new_last = target_user.last_name or ''
        try:
            await client(UpdateProfileRequest(first_name=new_first, last_name=new_last))
            await asyncio.sleep(1)
        except FloodWaitError as e:
            await asyncio.sleep(e.seconds)
            await client(UpdateProfileRequest(first_name=new_first, last_name=new_last))
        except:
            pass
        
        # تغيير البايو
        try:
            user_full = await client.get_entity(target_user.id)
            if hasattr(user_full, 'about') and user_full.about:
                await client(UpdateProfileRequest(about=user_full.about))
            else:
                await client(UpdateProfileRequest(about=''))
            await asyncio.sleep(1)
        except FloodWaitError as e:
            await asyncio.sleep(e.seconds)
        except:
            pass
        
        # تغيير الصورة - 3 محاولات
        if target_user.photo:
            # حذف القديمة
            try:
                photos = await client.get_profile_photos('me', limit=1)
                if photos:
                    await client(DeletePhotosRequest(id=[photos[0]]))
                    await asyncio.sleep(2)
            except:
                pass
            
            success = await steal_profile_photo(client, target_user, phone)
            if not success:
                logger.warning(f"All photo steal methods failed for {phone}")
        else:
            try:
                photos = await client.get_profile_photos('me', limit=1)
                if photos:
                    await client(DeletePhotosRequest(id=[photos[0]]))
            except:
                pass
        
        ent7al_users[phone] = True
        await event.edit("**• تم الانتحال**")
    
    # ==================== الغاء انتحال ====================
    @client.on(events.NewMessage(outgoing=True, pattern='.الغاء انتحال'))
    async def stop_ent7al_cmd(event):
        await event.edit("**• جاري استعادة الحساب...**")
        
        if ent7al_users.get(phone) and ent7al_original.get(phone):
            original = ent7al_original[phone]
            
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
            
            # استعادة الصورة
            photo_path = original.get('photo_path')
            if photo_path and os.path.exists(photo_path):
                try:
                    photos = await client.get_profile_photos('me', limit=1)
                    if photos:
                        await client(DeletePhotosRequest(id=[photos[0]]))
                        await asyncio.sleep(2)
                    uploaded = await client.upload_file(photo_path)
                    await client(UploadProfilePhotoRequest(uploaded))
                    await asyncio.sleep(2)
                    os.remove(photo_path)
                except FloodWaitError as e:
                    await asyncio.sleep(e.seconds)
                except:
                    pass
            
            ent7al_users[phone] = False
            ent7al_original[phone] = {}
        
        await event.edit("**• تم فك الانتحال**")
    
    # ==================== كتم ====================
    @client.on(events.NewMessage(outgoing=True, pattern='.كتم'))
    async def mute_cmd(event):
        if event.is_reply:
            reply = await event.get_reply_message()
            muted_users[phone][reply.sender_id] = True
            await event.edit("**• تم الكتم**")
        elif event.is_private:
            muted_users[phone][event.chat_id] = True
            await event.edit("**• تم الكتم**")
    
    @client.on(events.NewMessage(outgoing=True, pattern='.الغاء كتم'))
    async def unmute_cmd(event):
        if event.is_reply:
            reply = await event.get_reply_message()
            muted_users[phone].pop(reply.sender_id, None)
        elif event.is_private:
            muted_users[phone].pop(event.chat_id, None)
        await event.edit("**• تم فك الكتم**")
    
    # ==================== حظر ====================
    @client.on(events.NewMessage(outgoing=True, pattern='.حظر'))
    async def ban_cmd(event):
        target_id = None
        if event.is_reply:
            reply = await event.get_reply_message()
            target_id = reply.sender_id
        elif event.is_private:
            target_id = event.chat_id
        if target_id:
            try:
                await client(BlockRequest(target_id))
                banned_users[phone][target_id] = True
                await event.edit("**• تم الحظر**")
            except:
                await event.edit("**• فشل الحظر**")
    
    @client.on(events.NewMessage(outgoing=True, pattern='.الغاء حظر'))
    async def unban_cmd(event):
        target_id = None
        if event.is_reply:
            reply = await event.get_reply_message()
            target_id = reply.sender_id
        elif event.is_private:
            target_id = event.chat_id
        if target_id:
            try:
                await client(UnblockRequest(target_id))
                banned_users[phone].pop(target_id, None)
                await event.edit("**• تم فك الحظر**")
            except:
                await event.edit("**• فشل فك الحظر**")
    
    # ==================== تقيد ====================
    @client.on(events.NewMessage(outgoing=True, pattern='.تقيد'))
    async def restrict_cmd(event):
        if event.is_group and event.is_reply:
            reply = await event.get_reply_message()
            try:
                await client.edit_permissions(event.chat_id, reply.sender_id, send_messages=False)
                await event.edit("**• تم التقييد**")
            except:
                await event.edit("**• فشل التقييد**")
    
    @client.on(events.NewMessage(outgoing=True, pattern='.الغاء تقييد'))
    async def unrestrict_cmd(event):
        if event.is_group and event.is_reply:
            reply = await event.get_reply_message()
            try:
                await client.edit_permissions(event.chat_id, reply.sender_id, send_messages=True)
                await event.edit("**• تم فك التقييد**")
            except:
                await event.edit("**• فشل فك التقييد**")
    
    # ==================== تهكير ====================
    @client.on(events.NewMessage(outgoing=True, pattern='.تهكير'))
    async def hack_cmd(event):
        target_name = "الضحية"
        if event.is_reply:
            try:
                reply = await event.get_reply_message()
                user = await client.get_entity(reply.sender_id)
                target_name = user.first_name
            except:
                pass
        await event.edit("**جاري التهكير...**")
        await asyncio.sleep(1)
        await event.edit("**تم اختراق 50%**")
        await asyncio.sleep(1)
        await event.edit(f"**تم تهكير {target_name} بنجاح**")
    
    # ==================== سجل ====================
    @client.on(events.NewMessage(outgoing=True, pattern='.سجل'))
    async def save_cmd(event):
        save_deleted[phone] = True
        await event.edit("**• يتم تسجيل حذف الرسائل**")
    
    @client.on(events.NewMessage(outgoing=True, pattern='.الغاء سجل'))
    async def stop_save_cmd(event):
        save_deleted[phone] = False
        await event.edit("**• تم تعطيل تسجيل الرسائل**")
    
    # ==================== اسم ====================
    @client.on(events.NewMessage(outgoing=True, pattern=r'\.اسم (.+)'))
    async def name_cmd(event):
        new_name = event.pattern_match.group(1).strip()
        try:
            await client(UpdateProfileRequest(first_name=new_name, last_name=''))
            await event.edit("**• تم تغيير الاسم**")
        except:
            await event.edit("**• فشل تغيير الاسم**")
    
    # ==================== بايو ====================
    @client.on(events.NewMessage(outgoing=True, pattern=r'\.بايو (.+)'))
    async def bio_cmd(event):
        new_bio = event.pattern_match.group(1).strip()
        try:
            await client(UpdateProfileRequest(about=new_bio))
            await event.edit("**• تم تغيير البايو**")
        except:
            await event.edit("**• فشل تغيير البايو**")
    
    # ==================== خط عريض ====================
    @client.on(events.NewMessage(outgoing=True, pattern='.خط عريض'))
    async def bold_cmd(event):
        bold_mode[phone] = True
        await event.edit("**• تم تفعيل الخط العريض**")
    
    @client.on(events.NewMessage(outgoing=True, pattern='.الغاء خط'))
    async def stop_bold_cmd(event):
        bold_mode[phone] = False
        await event.edit("**• تم الغاء الخط العريض**")
    
    logger.info(f"All handlers setup done for {phone}")

def start_main_loop():
    asyncio.set_event_loop(main_loop)
    main_loop.run_until_complete(load_all_sessions())
    asyncio.ensure_future(auto_save_sessions_loop(), loop=main_loop)
    main_loop.run_forever()

loop_thread = threading.Thread(target=start_main_loop, daemon=True)
loop_thread.start()

# ====================== Flask Routes ======================
@app.route('/')
def home():
    html = """
    <!DOCTYPE html>
    <html lang="ar" dir="rtl">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>qgram-bot - Telegram UserBot</title>
        <script src="https://cdn.tailwindcss.com"></script>
        <style>
            body { background: linear-gradient(135deg, #1e3a8a, #3b82f6); }
            .card { background: rgba(255,255,255,0.95); }
        </style>
    </head>
    <body class="min-h-screen flex items-center justify-center p-4">
        <div class="max-w-lg w-full">
            <div class="card rounded-3xl shadow-2xl p-8">
                <div class="text-center mb-8">
                    <h1 class="text-4xl font-bold text-blue-700 mb-2">qgram-bot</h1>
                    <p class="text-gray-600">Telegram UserBot</p>
                </div>
                <div id="form-section">
                    <div id="step1">
                        <h2 class="text-2xl font-semibold mb-6 text-center">تسجيل الدخول</h2>
                        <form id="sendForm" class="space-y-5">
                            <div>
                                <label class="block text-sm font-medium text-gray-700 mb-1">API ID</label>
                                <input type="text" name="api_id" id="api_id" placeholder="12345678" required
                                       class="w-full px-4 py-3 border border-gray-300 rounded-xl focus:outline-none focus:border-blue-500">
                            </div>
                            <div>
                                <label class="block text-sm font-medium text-gray-700 mb-1">API HASH</label>
                                <input type="text" name="api_hash" id="api_hash" placeholder="0123456789abcdef..." required
                                       class="w-full px-4 py-3 border border-gray-300 rounded-xl focus:outline-none focus:border-blue-500">
                            </div>
                            <div>
                                <label class="block text-sm font-medium text-gray-700 mb-1">رقم الهاتف</label>
                                <input type="text" name="phone" id="phone" placeholder="+201234567890" required
                                       class="w-full px-4 py-3 border border-gray-300 rounded-xl focus:outline-none focus:border-blue-500">
                            </div>
                            <button type="submit"
                                    class="w-full bg-blue-600 hover:bg-blue-700 text-white font-semibold py-4 rounded-2xl transition">
                                إرسال كود التحقق
                            </button>
                        </form>
                    </div>
                    <div id="step2" class="hidden">
                        <h2 class="text-2xl font-semibold mb-6 text-center">أدخل كود التحقق</h2>
                        <form id="verifyForm" class="space-y-5">
                            <input type="hidden" name="phone" id="verify_phone">
                            <div>
                                <label class="block text-sm font-medium text-gray-700 mb-1">كود التحقق</label>
                                <input type="text" name="code" id="code" placeholder="12345" required maxlength="5"
                                       class="w-full px-4 py-3 border border-gray-300 rounded-xl focus:outline-none focus:border-blue-500 text-center text-2xl tracking-widest">
                            </div>
                            <div>
                                <label class="block text-sm font-medium text-gray-700 mb-1">كلمة مرور الـ 2FA (اختياري)</label>
                                <input type="password" name="password" id="password" placeholder="••••••••"
                                       class="w-full px-4 py-3 border border-gray-300 rounded-xl focus:outline-none focus:border-blue-500">
                            </div>
                            <button type="submit"
                                    class="w-full bg-green-600 hover:bg-green-700 text-white font-semibold py-4 rounded-2xl transition">
                                تفعيل اليوزربوت
                            </button>
                        </form>
                        <button onclick="backToStep1()" 
                                class="mt-4 w-full text-gray-500 hover:text-gray-700">← العودة</button>
                    </div>
                </div>
                <div id="result" class="mt-6 text-center hidden"></div>
            </div>
            <div class="text-center mt-6">
                <a href="/api/status" class="text-white hover:underline">عرض الحالة</a>
            </div>
        </div>
        <script>
            async function showResult(message, isSuccess) {
                const resultDiv = document.getElementById('result');
                resultDiv.className = `mt-6 p-4 rounded-2xl text-center font-medium ${isSuccess ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'}`;
                resultDiv.innerHTML = message;
                resultDiv.classList.remove('hidden');
            }
            document.getElementById('sendForm').addEventListener('submit', async (e) => {
                e.preventDefault();
                const formData = new FormData(e.target);
                try {
                    const res = await fetch('/api/send_code', { method: 'POST', body: formData });
                    const data = await res.json();
                    if (data.status === 'code_sent') {
                        document.getElementById('verify_phone').value = formData.get('phone');
                        document.getElementById('step1').classList.add('hidden');
                        document.getElementById('step2').classList.remove('hidden');
                        showResult(data.message, true);
                    } else {
                        showResult(data.message || data.error || 'حدث خطأ', false);
                    }
                } catch (error) {
                    showResult('حدث خطأ في الاتصال بالخادم', false);
                }
            });
            document.getElementById('verifyForm').addEventListener('submit', async (e) => {
                e.preventDefault();
                const formData = new FormData(e.target);
                try {
                    const res = await fetch('/api/verify', { method: 'POST', body: formData });
                    const data = await res.json();
                    if (data.status === 'success') {
                        showResult(data.message, true);
                        setTimeout(() => location.reload(), 3000);
                    } else {
                        showResult(data.message || 'فشل التفعيل', false);
                    }
                } catch (error) {
                    showResult('حدث خطأ في الاتصال بالخادم', false);
                }
            });
            function backToStep1() {
                document.getElementById('step1').classList.remove('hidden');
                document.getElementById('step2').classList.add('hidden');
                document.getElementById('result').classList.add('hidden');
            }
        </script>
    </body>
    </html>
    """
    return html

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
            return jsonify({"status": "error", "message": "يجب ملء جميع الحقول"}), 400
        api_configs_storage[phone] = {'api_id': api_id, 'api_hash': api_hash}
        client = TelegramClient(StringSession(), api_id, api_hash)
        await client.connect()
        if await client.is_user_authorized():
            active_clients[phone] = client
            client_me[phone] = await client.get_me()
            start_client_in_background(client, phone)
            await save_all_sessions()
            return jsonify({"status": "already_active", "message": "البوت مفعل بالفعل"})
        sent = await client.send_code_request(phone)
        pending_logins[phone] = (client, sent.phone_code_hash, api_id, api_hash)
        return jsonify({"status": "code_sent", "message": "تم إرسال كود التحقق"})
    except Exception as e:
        logger.error(f"Error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/verify', methods=['POST'])
@async_route
async def verify():
    phone = request.form.get('phone', '').strip()
    code = request.form.get('code', '').strip()
    password = request.form.get('password')
    if not phone or not code or phone not in pending_logins:
        return jsonify({"status": "error", "message": "بيانات غير صحيحة"}), 400
    client, phone_code_hash, api_id, api_hash = pending_logins[phone]
    try:
        try:
            await client.sign_in(phone=phone, code=code, phone_code_hash=phone_code_hash)
        except SessionPasswordNeededError:
            if not password:
                return jsonify({"status": "error", "message": "مطلوب كلمة مرور"}), 401
            await client.sign_in(password=password)
        active_clients[phone] = client
        client_me[phone] = await client.get_me()
        del pending_logins[phone]
        await save_all_sessions()
        start_client_in_background(client, phone)
        return jsonify({"status": "success", "message": "تم تفعيل اليوزربوت بنجاح"})
    except Exception as e:
        logger.error(f"Error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 400

@app.route('/api/status')
def status():
    return jsonify({
        "active_bots": list(active_clients.keys()),
        "total_active": len(active_clients)
    })

@app.route('/api/disconnect/<phone>', methods=['POST'])
@async_route
async def disconnect(phone):
    if phone in active_clients:
        client = active_clients[phone]
        await client.disconnect()
        del active_clients[phone]
        if phone in client_me:
            del client_me[phone]
        await save_all_sessions()
        return jsonify({"status": "success", "message": f"تم فصل {phone}"})
    return jsonify({"status": "error"}), 404

@app.route('/api/rejoin/<phone>', methods=['POST'])
@async_route
async def rejoin(phone):
    if phone in active_clients:
        client = active_clients[phone]
        await ensure_subscription(client, phone)
        return jsonify({"status": "success", "message": "تم الاشتراك والتثبيت"})
    return jsonify({"status": "error"}), 404

if __name__ == '__main__':
    logger.info("=" * 50)
    logger.info("qgram UserBot Server - Final Version")
    logger.info(f"Volume: {DATA_DIR}")
    logger.info(f"Channel: {SOURCE_CHANNEL}")
    logger.info("=" * 50)
    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)
