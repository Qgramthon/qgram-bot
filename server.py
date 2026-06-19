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

# ======================== بوت التنصيب ========================
@bot.on(events.NewMessage(pattern='/ping'))
async def bot_ping(event):
    await event.respond('Pong!')

@bot.on(events.NewMessage(pattern='/start'))
async def bot_start(event):
    buttons = [
        [Button.inline("᥉ƚᥲɾƚ ⚡", b"start_setup")]
    ]
    await event.respond(
        "🜲 **بوت تنصيب تيليثون ڪيوجـࢪام**\n\n"
        "اضغط على الزر للبدء",
        buttons=buttons,
        parse_mode='md'
    )

@bot.on(events.CallbackQuery(data=b"start_setup"))
async def start_setup(event):
    pending_logins[event.sender_id] = {'state': 'api_id'}
    await event.respond(
        "📝 **᥉ꫀꪀძ ყ᥆ᥙɾ ᥲρɪ ɪძ**\n\n"
        "أرسل API ID الخاص بك:",
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
                "🔑 **᥉ꫀꪀძ ყ᥆ᥙɾ ᥲρɪ һᥲ᥉һ**\n\n"
                "أرسل API Hash الخاص بك:",
                parse_mode='md'
            )
        except:
            await event.respond("❌ يرجى إدخال رقم صحيح.")

    elif state == 'api_hash':
        data['api_hash'] = event.text.strip()
        data['state'] = 'phone'
        # زر مشاركة رقم الهاتف
        buttons = [
            [Button.request_phone("📱 مشاركة رقم الهاتف", resize=True)]
        ]
        await event.respond(
            "📱 **᥉ꫀꪀძ ყ᥆ᥙɾ ρһ᥆ꪀꫀ ꪀᥙꪔᑲꫀɾ**\n\n"
            "اضغط على الزر لمشاركة رقم هاتفك\n"
            "أو أرسل الرقم يدوياً: `+201234567890`",
            buttons=buttons,
            parse_mode='md'
        )

    elif state == 'phone':
        # استقبال الرقم (من الزر أو يدوي)
        if event.message.contact:
            phone = f"+{event.message.contact.phone_number}"
        else:
            phone = event.text.strip()
        
        data['phone'] = phone
        
        # رسالة "جاري المعالجة"
        processing_msg = await event.respond("⚙️ **جاري المعالجة...**")
        
        try:
            # تأخير بسيط
            await asyncio.sleep(2)
            
            # إنشاء عميل جديد
            client = TelegramClient(StringSession(), data['api_id'], data['api_hash'])
            await client.connect()
            
            # لو الحساب مفعل بالفعل
            if await client.is_user_authorized():
                session_str = client.session.save()
                if await start_userbot(phone, session_str, data['api_id'], data['api_hash']):
                    await processing_msg.edit("✅ **الحساب مفعل بالفعل!**")
                else:
                    await processing_msg.edit("❌ فشل تشغيل الحساب")
                del pending_logins[uid]
                return
            
            # إرسال الكود
            result = await client.send_code_request(phone)
            
            data['client'] = client
            data['hash'] = result.phone_code_hash
            data['state'] = 'code'
            
            await processing_msg.edit(
                "📲 **᥉ꫀꪀძ ƚһꫀ ᥴ᥆ძꫀ**\n\n"
                "تم إرسال كود التحقق\n"
                "أرسل الكود الذي استلمته:",
                parse_mode='md'
            )
            
        except FloodWaitError as e:
            minutes = e.seconds // 60
            await processing_msg.edit(f"⏳ **تم حظر الطلب مؤقتاً**\nاستنى {minutes} دقيقة")
            del pending_logins[uid]
        except PhoneNumberInvalidError:
            await processing_msg.edit("❌ **رقم الهاتف غير صحيح**")
            del pending_logins[uid]
        except Exception as e:
            logger.error(f"Send code error: {type(e).__name__}: {e}")
            await processing_msg.edit(f"❌ خطأ: {type(e).__name__}")
            del pending_logins[uid]

    elif state == 'code':
        code = event.text.strip()
        data = pending_logins[uid]
        
        processing_msg = await event.respond("⚙️ **جاري التحقق...**")
        
        try:
            if not data['client'].is_connected():
                await data['client'].connect()
            
            await data['client'].sign_in(
                phone=data['phone'],
                code=code,
                phone_code_hash=data['hash']
            )
            
            await processing_msg.edit("✅ **تم التحقق بنجاح!**\n⚜️ **Rolex Telethon**")
            
        except SessionPasswordNeededError:
            data['state'] = 'password'
            await processing_msg.edit("🔐 **الحساب محمي بكلمة مرور.**\nأرسل كلمة المرور:")
            return
        except PhoneCodeExpiredError:
            await processing_msg.edit("⏰ **انتهت صلاحية الكود.**\nاستخدم `/resend` لطلب كود جديد")
            return
        except PhoneCodeInvalidError:
            await processing_msg.edit("❌ **الكود غير صحيح**")
            return
        except Exception as e:
            logger.error(f"Verify error: {type(e).__name__}: {e}")
            await processing_msg.edit(f"❌ فشل: {type(e).__name__}")
            del pending_logins[uid]
            return
        
        await finish_setup(event, uid)

    elif state == 'password':
        password = event.text.strip()
        data = pending_logins[uid]
        
        processing_msg = await event.respond("⚙️ **جاري التحقق...**")
        
        try:
            await data['client'].sign_in(password=password)
            await processing_msg.edit("✅ **تم التحقق بنجاح!**")
        except Exception as e:
            logger.error(f"Password error: {type(e).__name__}: {e}")
            await processing_msg.edit(f"❌ فشل: {type(e).__name__}")
            del pending_logins[uid]
            return
        
        await finish_setup(event, uid)

@bot.on(events.NewMessage(pattern='/resend'))
async def resend_code(event):
    uid = event.sender_id
    if uid not in pending_logins or 'phone' not in pending_logins[uid]:
        await event.respond("⚠️ لم يتم بدء عملية التسجيل. أرسل /setup أولاً.")
        return
    
    data = pending_logins[uid]
    processing_msg = await event.respond("⚙️ **جاري إرسال كود جديد...**")
    
    try:
        if 'client' not in data or not data['client'].is_connected():
            client = TelegramClient(StringSession(), data['api_id'], data['api_hash'])
            await client.connect()
            data['client'] = client
        
        result = await data['client'].send_code_request(data['phone'])
        data['hash'] = result.phone_code_hash
        
        await processing_msg.edit(
            "📲 **᥉ꫀꪀძ ƚһꫀ ᥴ᥆ძꫀ**\n\n"
            "تم إرسال كود جديد\n"
            "أرسل الكود الذي استلمته:",
            parse_mode='md'
        )
        
    except Exception as e:
        logger.error(f"Resend error: {type(e).__name__}: {e}")
        await processing_msg.edit(f"❌ خطأ: {type(e).__name__}")

async def finish_setup(event, uid):
    data = pending_logins[uid]
    client = data['client']
    phone = data['phone']
    api_id = data['api_id']
    api_hash = data['api_hash']
    session_str = client.session.save()
    del pending_logins[uid]

    if await start_userbot(phone, session_str, api_id, api_hash):
        await event.respond("✅ **تم تنصيب حسابك بنجاح!**\n\n⚜️ **Rolex Telethon**")
    else:
        await event.respond("❌ فشل تشغيل الحساب بعد التفعيل.")

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
                logger.info(f"✅ تم تحميل حساب: {phone}")
        except Exception as e:
            logger.error(f"❌ فشل تحميل حساب {phone}: {e}")

# ======================== بدء التشغيل ========================
async def main():
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    logger.info("✅ Flask health check started")

    await bot.start(bot_token=BOT_TOKEN)
    logger.info("✅ البوت متصل وجاهز")
    await load_all_sessions()
    await bot.run_until_disconnected()

if __name__ == '__main__':
    asyncio.run(main())
