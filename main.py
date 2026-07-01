#!/usr/bin/env python3
# 🧨 NinjaGram Pro Max Ultra v10 - Railway Fixed
import asyncio, uuid, os, re, random, time, io, textwrap, logging, json, threading
from datetime import datetime, timedelta
from urllib.parse import quote
from typing import Dict, List, Optional
from collections import deque, defaultdict
from io import BytesIO
import aiohttp
from PIL import Image, ImageDraw
import phonenumbers
from phonenumbers import geocoder, carrier, timezone as pn_timezone
from fake_useragent import UserAgent
from telethon import TelegramClient, events, Button, functions, types
from telethon.errors import *
from telethon.tl.functions.users import GetFullUserRequest
from telethon.tl.functions.messages import SearchRequest, CheckChatInviteRequest
from telethon.tl.functions.channels import GetFullChannelRequest, JoinChannelRequest
from telethon.tl.functions.contacts import ImportContactsRequest, DeleteContactsRequest, ResolveUsernameRequest
from telethon.tl.types import InputPhoneContact, InputPeerUser, InputPeerChannel
from telethon.tl.functions.account import UpdateProfileRequest
from aiohttp import web

# ==================== CONFIG ====================
DATA_DIR = './data'
os.makedirs(DATA_DIR, exist_ok=True)
BOT_TOKEN = '7998616214:AAHJmfPpL8rzRgso3hxIO-CKHE2rlycyNwo'
API_ID = 2040
API_HASH = 'b18441a1ff607e10a989891a5462e627'
DEV_ID = 6443238809
PORT = int(os.environ.get('PORT', 8080))

user_states = {}
pending_data = {}
rate_limiter = defaultdict(lambda: deque(maxlen=10))

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger('NinjaGram')

# Create new event loop (FIX)
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

bot = TelegramClient(f'{DATA_DIR}/session', API_ID, API_HASH, loop=loop)
ua = UserAgent()

# ==================== WEB APP ====================
async def handle_health(request):
    return web.Response(text="✅ Bot Running")

app = web.Application()
app.router.add_get('/', handle_health)

# ==================== SECURITY SYSTEM ====================
class Security:
    @staticmethod
    def rate(uid, action, mx=10):
        now = time.time(); k = f"{uid}:{action}"
        if k not in rate_limiter: rate_limiter[k] = deque(maxlen=mx)
        r = rate_limiter[k]
        while r and r[0] < now - 60: r.popleft()
        if len(r) >= mx: return False
        r.append(now); return True

    @staticmethod
    def valid_un(u): return bool(re.match(r'^[a-zA-Z][a-zA-Z0-9_]{3,31}$', u))

    @staticmethod
    def valid_ph(p):
        try: return phonenumbers.is_valid_number(phonenumbers.parse(p))
        except: return bool(re.match(r'^\+?[1-9]\d{7,14}$', p.replace(" ", "")))

# ==================== UI ====================
class UI:
    @staticmethod
    def main_menu():
        return [
            [Button.inline("📞 1. تروكولر حقيقي", b"tc")],
            [Button.inline("🔫 2. نظام البلاغات (15 نوع)", b"rpt")],
            [Button.inline("🕵️ 3. OSINT متقدم", b"osint")],
            [Button.inline("📞 4. كشف رقم (Russian)", b"reveal")],
            [Button.inline("🔍 5. تجميع جروبات عربي", b"scrape")],
            [Button.inline("🔓 6. فك حظر (TG+WA)", b"unban")],
            [Button.inline("🧬 7. فحص التسريبات", b"breach")],
            [Button.inline("💣 8. صيد اليوزرات", b"hunt")],
            [Button.inline("📊 9. تحليل جروب/قناة", b"analyze")],
            [Button.inline("📝 10. مزور رسائل", b"faker")],
            [Button.inline("📱 11. أدوات واتساب", b"wa")],
            [Button.inline("🔗 12. تحليل الروابط", b"link")],
            [Button.inline("🎭 13. كشف وهمي", b"fake")],
            [Button.inline("📡 14. ماسح أرقام", b"scan_nums")],
            [Button.inline("🔐 15. فاحص أمان", b"security")],
            [Button.inline("🖼️ 16. بحث عكسي صور", b"reverse_img")],
            [Button.inline("📨 17. إرسال جماعي", b"mass_msg")],
            [Button.inline("🔄 تحويل ID ↔ يوزر", b"convert")],
            [Button.inline("📊 إحصائيات", b"info")],
        ]

# ==================== HANDLERS ====================
@bot.on(events.NewMessage(pattern='/start'))
async def start_handler(event):
    welcome = """
🧨 **NinjaGram Pro Max Ultra v10**

📋 **17 خدمة احترافية:**
• تروكولر حقيقي للبحث عن الأرقام
• نظام بلاغات شامل (15 نوع)
• OSINT فحص عميق للحسابات
• كشف رقم الهاتف (Russian Method)
• تجميع جروبات بالعربي
• فك حظر تيليجرام وواتساب
• فحص التسريبات والبيانات المسربة
• صيد اليوزرات المميزة
• تحليل الجروبات والقنوات
• مزور رسائل تيليجرام وواتساب
• أدوات واتساب المتقدمة
• تحليل الروابط
• كشف الحسابات الوهمية
• ماسح الأرقام
• فاحص أمان الحساب
• بحث عكسي عن الصور
• إرسال رسائل جماعية

👨‍💻 @NinjaGram | @Q_g_r_a_m
"""
    await event.respond(welcome, buttons=UI.main_menu(), parse_mode='md')

@bot.on(events.CallbackQuery(data=b"main"))
async def back_main(event):
    await event.edit("🧨 **القائمة الرئيسية - 17 خدمة**", buttons=UI.main_menu(), parse_mode='md')

@bot.on(events.CallbackQuery(data=b"info"))
async def info_handler(event):
    stats = """
📊 **إحصائيات البوت:**
• 17 خدمة رئيسية
• 15 نوع بلاغات
• 100% واجهة عربية
• شغال على Railway 🚂

👨‍💻 @NinjaGram
"""
    await event.edit(stats, buttons=[[Button.inline("🔙", b"main")]], parse_mode='md')

@bot.on(events.CallbackQuery(data=b"tc"))
async def tc_start(event):
    user_states[event.sender_id] = "tc"
    await event.edit("📞 **تروكولر**\n\nأرسل رقم الهاتف أو الاسم للبحث:", buttons=[[Button.inline("🔙", b"main")]], parse_mode='md')

@bot.on(events.CallbackQuery(data=b"osint"))
async def osint_start(event):
    user_states[event.sender_id] = "osint"
    await event.edit("🕵️ **OSINT فحص عميق**\n\nأرسل اليوزر أو ID:", buttons=[[Button.inline("🔙", b"main")]], parse_mode='md')

@bot.on(events.CallbackQuery(data=b"scrape"))
async def scrape_start(event):
    user_states[event.sender_id] = "scrape"
    await event.edit("🔍 **بحث جروبات**\n\nأرسل الكلمة المفتاحية:", buttons=[[Button.inline("🔙", b"main")]], parse_mode='md')

@bot.on(events.CallbackQuery(data=b"wa"))
async def wa_start(event):
    user_states[event.sender_id] = "wa"
    await event.edit("📱 **واتساب**\n\nأرسل رقم الهاتف:", buttons=[[Button.inline("🔙", b"main")]], parse_mode='md')

@bot.on(events.CallbackQuery(data=b"fake"))
async def fake_start(event):
    user_states[event.sender_id] = "fake"
    await event.edit("🎭 **كشف وهمي**\n\nأرسل يوزر أو ID:", buttons=[[Button.inline("🔙", b"main")]], parse_mode='md')

@bot.on(events.CallbackQuery(data=b"convert"))
async def convert_start(event):
    user_states[event.sender_id] = "convert"
    await event.edit("🔄 **تحويل ID ↔ يوزر**\n\nأرسل اليوزر أو ID:", buttons=[[Button.inline("🔙", b"main")]], parse_mode='md')

# ==================== MESSAGE HANDLER ====================
@bot.on(events.NewMessage(func=lambda e: e.sender_id in user_states and not e.text.startswith('/')))
async def message_handler(event):
    uid = event.sender_id
    st = user_states.pop(uid, None)
    txt = event.text.strip()
    if not st: return
    
    try:
        if st == "tc":
            await event.respond(f"📞 جاري البحث عن: {txt}\n\n🔍 هذه الخدمة قيد التطوير...", buttons=[[Button.inline("🔙", b"main")]])
        
        elif st == "osint":
            try:
                target = int(txt) if txt.lstrip('-').isdigit() else txt.replace("@", "")
                entity = await bot.get_entity(target)
                info = f"""
🕵️ **تقرير OSINT**

📋 **معلومات الحساب:**
• ID: `{entity.id}`
• يوزر: @{getattr(entity, 'username', 'لا يوجد')}
• اسم: {getattr(entity, 'first_name', '')} {getattr(entity, 'last_name', '')}
• بوت: {'🤖 نعم' if getattr(entity, 'bot', False) else '👤 لا'}
• موثق: {'✅ نعم' if getattr(entity, 'verified', False) else '❌ لا'}
• احتيال: {'⚠️ نعم' if getattr(entity, 'scam', False) else '✅ لا'}
"""
                await event.respond(info, buttons=[[Button.inline("🔙", b"main")]], parse_mode='md')
            except:
                await event.respond("❌ الحساب غير موجود", buttons=[[Button.inline("🔙", b"main")]])
        
        elif st == "scrape":
            await event.respond(f"🔍 جاري البحث عن: {txt}\n\n🔍 هذه الخدمة قيد التطوير...", buttons=[[Button.inline("🔙", b"main")]])
        
        elif st == "wa":
            await event.respond(f"📱 فحص واتساب: {txt}\n\n📱 هذه الخدمة قيد التطوير...", buttons=[[Button.inline("🔙", b"main")]])
        
        elif st == "fake":
            await event.respond(f"🎭 فحص: {txt}\n\n🎭 هذه الخدمة قيد التطوير...", buttons=[[Button.inline("🔙", b"main")]])
        
        elif st == "convert":
            try:
                target = int(txt) if txt.lstrip('-').isdigit() else txt.replace("@", "")
                entity = await bot.get_entity(target)
                un = getattr(entity, 'username', None)
                out = f"🔄 **تحويل**\n\n🆔 ID: `{entity.id}`\n🔖 يوزر: @{un if un else 'لا يوجد'}\n👤 {getattr(entity, 'first_name', '')} {getattr(entity, 'last_name', '')}"
                await event.respond(out, buttons=[[Button.inline("🔙", b"main")]], parse_mode='md')
            except:
                await event.respond("❌ غير موجود", buttons=[[Button.inline("🔙", b"main")]])
    
    except Exception as e:
        await event.respond(f"❌ خطأ: {str(e)[:100]}", buttons=[[Button.inline("🔙", b"main")]])

# ==================== RUN (RAILWAY FIXED) ====================
if __name__ == '__main__':
    print("""
╔══════════════════════════════════════╗
║   🧨 NinjaGram Pro Max Ultra v10  ║
║   @NinjaGram | @Q_g_r_a_m         ║
╚══════════════════════════════════════╝
    """)
    
    # Start web in thread
    def run_web():
        print(f"🌐 Web Server on port {PORT}")
        web.run_app(app, host='0.0.0.0', port=PORT, print=lambda _: None)
    
    threading.Thread(target=run_web, daemon=True).start()
    
    # Start bot with fixed event loop
    async def main():
        await bot.start(bot_token=BOT_TOKEN)
        me = await bot.get_me()
        print(f"✅ Bot Online: @{me.username}")
        print("🚀 Ready on Railway!")
        await bot.run_until_disconnected()
    
    loop.run_until_complete(main())
