# kraken_bot.py
import asyncio
import aiohttp
import os
import sys
import json
import random
import string
import re
import time
import requests
from datetime import datetime
from urllib.parse import quote

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from telegram.constants import ParseMode

# ============================================
# التوكن من Railway
# ============================================
TOKEN = os.getenv("BOT_TOKEN", "YOUR_TOKEN_HERE")

# ============================================
# User Data Storage
# ============================================
user_states = {}

# ============================================
# البانر والقوائم
# ============================================
START_TEXT = """
🐙 <b>KRAKEN MULTI-TOOL BOT</b>
<blockquote>البوت الشامل - صيد يوزرات | تحميل فيديوهات | معلومات حسابات</blockquote>

🎯 <b>الخدمات المتاحة:</b>
1️⃣ صيد يوزرات (تيليجرام | انستا | تيكتوك)
2️⃣ تحميل فيديوهات (تيكتوك | يوتيوب | انستا | فيسبوك)
3️⃣ معلومات حساب تيليجرام باليوزر
4️⃣ فتح حساب/قناة/جروب بالآيدي
5️⃣ تحويل يوزر لآيدي والعكس
6️⃣ فحص توفر يوزر معين

🔥 <b>اختر الخدمة من القائمة:</b>"""

def main_keyboard():
    keyboard = [
        [InlineKeyboardButton("🎯 صيد يوزرات", callback_data="hunt_menu")],
        [InlineKeyboardButton("🎬 تحميل فيديو", callback_data="video_info")],
        [InlineKeyboardButton("🔍 معلومات حساب", callback_data="info_info")],
        [InlineKeyboardButton("🔗 فتح بالآيدي", callback_data="open_info")],
        [InlineKeyboardButton("🔄 تحويل يوزر/آيدي", callback_data="resolve_info")],
        [InlineKeyboardButton("✅ فحص يوزر", callback_data="check_info")],
    ]
    return InlineKeyboardMarkup(keyboard)

def back_keyboard():
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع للقائمة", callback_data="back_main")]])

def hunt_keyboard():
    keyboard = [
        [InlineKeyboardButton("📱 تيليجرام", callback_data="hunt_tg")],
        [InlineKeyboardButton("📷 انستجرام", callback_data="hunt_ig")],
        [InlineKeyboardButton("🎵 تيكتوك", callback_data="hunt_tk")],
        [InlineKeyboardButton("🌐 الثلاثة معاً", callback_data="hunt_all")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="back_main")],
    ]
    return InlineKeyboardMarkup(keyboard)

def video_platforms_keyboard():
    keyboard = [
        [InlineKeyboardButton("🎵 تيكتوك", callback_data="dl_tiktok")],
        [InlineKeyboardButton("▶️ يوتيوب", callback_data="dl_youtube")],
        [InlineKeyboardButton("📷 انستجرام", callback_data="dl_instagram")],
        [InlineKeyboardButton("📘 فيسبوك", callback_data="dl_facebook")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="back_main")],
    ]
    return InlineKeyboardMarkup(keyboard)

# ============================================
# مولد اليوزرات المميزة
# ============================================
def generate_usernames(platform="tg"):
    usernames = []
    chars = string.ascii_uppercase
    vowels = "AEIOU"
    consonants = "BCDFGHJKLMNPQRSTVWXYZ"
    nums = "0123456789"
    
    # أنماط ثلاثية
    for _ in range(50):
        l1 = random.choice(consonants)
        l2 = random.choice(vowels)
        d = random.choice("1379")
        usernames.extend([f"{l1}{l2}{d}", f"{d}{l1}{l2}", f"{l1}{d}{l2}"])
    
    # أنماط متناظرة
    for _ in range(30):
        l = random.choice(chars)
        d = random.choice(nums)
        usernames.extend([f"{l}{d}{l}", f"{d}{l}{d}"])
    
    # أنماط متكررة
    for l in random.sample(chars, 10):
        usernames.append(f"{l}{l}{l}")
    
    # أرقام محظوظة
    lucky = ["777", "888", "999", "111", "333", "555"]
    for num in lucky:
        for l in random.sample(chars, 5):
            usernames.extend([f"{num}{l}", f"{l}{num}"])
    
    # كلمات VIP
    vip = ["VIP", "KING", "BOSS", "GOD", "LEO", "ACE", "PRO", "X", "OG"]
    for word in vip:
        for d in "1379":
            usernames.extend([f"{word}{d}", f"{d}{word}"])
    
    # رباعي
    for _ in range(30):
        l1, l2 = random.sample(chars, 2)
        d1, d2 = random.sample(nums, 2)
        usernames.extend([f"{l1}{l2}{d1}{d2}", f"{d1}{d2}{l1}{l2}"])
    
    return list(set(usernames))

# ============================================
# فحص يوزر تيليجرام
# ============================================
async def check_tg_username(username):
    try:
        async with aiohttp.ClientSession() as session:
            url = f"https://fragment.com/username/{username.lower()}"
            headers = {'User-Agent': 'Mozilla/5.0'}
            async with session.get(url, headers=headers, timeout=8) as resp:
                text = await resp.text()
                if "Not Found" in text or resp.status == 404:
                    return f"✅ @{username}"
    except:
        pass
    return None

# ============================================
# فحص يوزر انستجرام
# ============================================
async def check_ig_username(username):
    try:
        async with aiohttp.ClientSession() as session:
            url = f"https://www.instagram.com/{username}/"
            headers = {'User-Agent': 'Mozilla/5.0'}
            async with session.get(url, headers=headers, timeout=8) as resp:
                if resp.status == 404:
                    return f"✅ @{username}"
    except:
        pass
    return None

# ============================================
# فحص يوزر تيكتوك
# ============================================
async def check_tk_username(username):
    try:
        async with aiohttp.ClientSession() as session:
            url = f"https://www.tiktok.com/@{username}"
            headers = {'User-Agent': 'Mozilla/5.0'}
            async with session.get(url, headers=headers, timeout=8) as resp:
                if resp.status == 404:
                    return f"✅ @{username}"
    except:
        pass
    return None

# ============================================
# تحميل الفيديوهات
# ============================================
async def download_video(url, platform):
    try:
        if platform == "tiktok":
            api_url = f"https://tikwm.com/api/?url={quote(url)}"
            async with aiohttp.ClientSession() as session:
                async with session.get(api_url, timeout=15) as resp:
                    data = await resp.json()
                    if data.get("code") == 0:
                        video_url = data.get("data", {}).get("play")
                        return {"success": True, "video_url": video_url, "platform": "تيكتوك"}
        
        elif platform == "instagram":
            api_url = f"https://instagram-downloader-download-instagram-videos-stories.p.rapidapi.com/index?url={quote(url)}"
            headers = {
                'X-RapidAPI-Key': 'your_key_here',
                'X-RapidAPI-Host': 'instagram-downloader-download-instagram-videos-stories.p.rapidapi.com'
            }
            async with aiohttp.ClientSession() as session:
                async with session.get(api_url, headers=headers, timeout=15) as resp:
                    data = await resp.json()
                    if data.get("media"):
                        return {"success": True, "video_url": data["media"], "platform": "انستجرام"}
        
        elif platform == "youtube":
            api_url = f"https://yt-api.p.rapidapi.com/dl?id={url.split('v=')[-1]}" if 'youtu' in url else f"https://yt-api.p.rapidapi.com/dl?id={url.split('/')[-1]}"
            return {"success": False, "error": "استخدم @vid_downloader_bot لتحميل فيديوهات يوتيوب"}
        
        elif platform == "facebook":
            api_url = f"https://facebook-video-downloader.p.rapidapi.com/?url={quote(url)}"
            return {"success": False, "error": "استخدم @fbdownloader_bot لتحميل فيديوهات فيسبوك"}
        
        return {"success": False, "error": "فشل التحميل"}
    except Exception as e:
        return {"success": False, "error": str(e)}

# ============================================
# معلومات حساب تيليجرام
# ============================================
async def get_telegram_info(username):
    try:
        async with aiohttp.ClientSession() as session:
            url = f"https://t.me/{username}"
            headers = {'User-Agent': 'Mozilla/5.0'}
            async with session.get(url, headers=headers, timeout=8) as resp:
                text = await resp.text()
                
                info = {
                    "username": username,
                    "url": url,
                    "exists": resp.status == 200
                }
                
                # استخراج اسم العرض
                name_match = re.search(r'<meta property="og:title" content="([^"]+)"', text)
                if name_match:
                    info["display_name"] = name_match.group(1)
                
                # استخراج الصورة
                image_match = re.search(r'<meta property="og:image" content="([^"]+)"', text)
                if image_match:
                    info["profile_image"] = image_match.group(1)
                
                # استخراج البايو
                desc_match = re.search(r'<meta property="og:description" content="([^"]+)"', text)
                if desc_match:
                    info["bio"] = desc_match.group(1)
                
                return info
    except:
        return {"exists": False, "error": "فشل الاتصال"}

# ============================================
# أوامر البوت
# ============================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(START_TEXT, reply_markup=main_keyboard(), parse_mode=ParseMode.HTML)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = """
📚 <b>قائمة الأوامر:</b>

/start - تشغيل البوت
/help - عرض المساعدة
/hunt - صيد يوزرات مميزة
/video - تحميل فيديو
/info - معلومات حساب تيليجرام
/open - فتح حساب بالآيدي
/resolve - تحويل يوزر لآيدي
/check - فحص توفر يوزر
"""
    await update.message.reply_text(help_text, parse_mode=ParseMode.HTML)

# ============================================
# صيد اليوزرات
# ============================================
async def hunt_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🎯 <b>اختر منصة الصيد:</b>", reply_markup=hunt_keyboard(), parse_mode=ParseMode.HTML)

async def video_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🎬 <b>اختر منصة التحميل:</b>", reply_markup=video_platforms_keyboard(), parse_mode=ParseMode.HTML)

async def info_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔍 <b>أرسل يوزر تيليجرام:</b>\nمثال: @username", reply_markup=back_keyboard(), parse_mode=ParseMode.HTML)
    user_states[update.effective_user.id] = "waiting_info"

async def open_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🔗 <b>أرسل الآيدي الرقمي:</b>\n\n"
        "مثال: 123456789\n\n"
        "سأعطيك رابط يفتح الحساب/القناة/الجروب مباشرة",
        reply_markup=back_keyboard(),
        parse_mode=ParseMode.HTML
    )
    user_states[update.effective_user.id] = "waiting_open"

async def resolve_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🔄 <b>أرسل اليوزر أو الآيدي:</b>\n\n"
        "مثال: @username أو 123456789",
        reply_markup=back_keyboard(),
        parse_mode=ParseMode.HTML
    )
    user_states[update.effective_user.id] = "waiting_resolve"

async def check_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "✅ <b>أرسل اليوزر للفحص:</b>\n\n"
        "مثال: @username",
        reply_markup=back_keyboard(),
        parse_mode=ParseMode.HTML
    )
    user_states[update.effective_user.id] = "waiting_check"

# ============================================
# معالجة الكول باك
# ============================================
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = update.effective_user.id
    
    # الرجوع للقائمة
    if data == "back_main":
        await query.edit_message_text(START_TEXT, reply_markup=main_keyboard(), parse_mode=ParseMode.HTML)
        return
    
    # قائمة الصيد
    if data == "hunt_menu":
        await query.edit_message_text("🎯 <b>اختر منصة الصيد:</b>", reply_markup=hunt_keyboard(), parse_mode=ParseMode.HTML)
        return
    
    # صيد تيليجرام
    if data == "hunt_tg":
        await query.edit_message_text("📱 <b>جاري صيد يوزرات تيليجرام...</b>\n⏳ استنى شوية...", parse_mode=ParseMode.HTML)
        msg = await query.message.reply_text("🔄 جاري الفحص...")
        
        usernames = generate_usernames("tg")[:300]
        found = []
        
        async with aiohttp.ClientSession() as session:
            semaphore = asyncio.Semaphore(30)
            async def check_with_sem(u):
                async with semaphore:
                    return await check_tg_username(u)
            
            tasks = [check_with_sem(u) for u in usernames]
            results = await asyncio.gather(*tasks)
            found = [r for r in results if r]
        
        if found:
            result_text = f"✅ <b>تم العثور على {len(found)} يوزر متاح:</b>\n\n"
            for i, username in enumerate(found[:20], 1):
                result_text += f"{i}. {username}\n"
            if len(found) > 20:
                result_text += f"\n... و {len(found) - 20} آخرين"
        else:
            result_text = "❌ <b>لم يتم العثور على يوزرات متاحة</b>\nجرب مرة تانية"
        
        await msg.delete()
        await query.edit_message_text(result_text, reply_markup=back_keyboard(), parse_mode=ParseMode.HTML)
        return
    
    # صيد انستجرام
    if data == "hunt_ig":
        await query.edit_message_text("📷 <b>جاري صيد يوزرات انستجرام...</b>\n⏳ استنى شوية...", parse_mode=ParseMode.HTML)
        msg = await query.message.reply_text("🔄 جاري الفحص...")
        
        usernames = generate_usernames("ig")[:300]
        found = []
        
        async with aiohttp.ClientSession() as session:
            semaphore = asyncio.Semaphore(30)
            async def check_with_sem(u):
                async with semaphore:
                    return await check_ig_username(u.lower())
            
            tasks = [check_with_sem(u) for u in usernames]
            results = await asyncio.gather(*tasks)
            found = [r for r in results if r]
        
        if found:
            result_text = f"✅ <b>تم العثور على {len(found)} يوزر متاح:</b>\n\n"
            for i, username in enumerate(found[:20], 1):
                result_text += f"{i}. {username}\n"
        else:
            result_text = "❌ <b>لم يتم العثور على يوزرات متاحة</b>"
        
        await msg.delete()
        await query.edit_message_text(result_text, reply_markup=back_keyboard(), parse_mode=ParseMode.HTML)
        return
    
    # صيد تيكتوك
    if data == "hunt_tk":
        await query.edit_message_text("🎵 <b>جاري صيد يوزرات تيكتوك...</b>\n⏳ استنى شوية...", parse_mode=ParseMode.HTML)
        msg = await query.message.reply_text("🔄 جاري الفحص...")
        
        usernames = generate_usernames("tk")[:300]
        found = []
        
        async with aiohttp.ClientSession() as session:
            semaphore = asyncio.Semaphore(30)
            async def check_with_sem(u):
                async with semaphore:
                    return await check_tk_username(u.lower())
            
            tasks = [check_with_sem(u) for u in usernames]
            results = await asyncio.gather(*tasks)
            found = [r for r in results if r]
        
        if found:
            result_text = f"✅ <b>تم العثور على {len(found)} يوزر متاح:</b>\n\n"
            for i, username in enumerate(found[:20], 1):
                result_text += f"{i}. {username}\n"
        else:
            result_text = "❌ <b>لم يتم العثور على يوزرات متاحة</b>"
        
        await msg.delete()
        await query.edit_message_text(result_text, reply_markup=back_keyboard(), parse_mode=ParseMode.HTML)
        return
    
    # صيد الكل
    if data == "hunt_all":
        await query.edit_message_text("🌐 <b>جاري صيد يوزرات من الثلاث منصات...</b>\n⏳ استنى شوية الموضوع هيكون أبطأ...", parse_mode=ParseMode.HTML)
        msg = await query.message.reply_text("🔄 جاري الفحص الشامل...")
        
        all_found = {"tg": [], "ig": [], "tk": []}
        usernames = generate_usernames()[:200]
        
        async with aiohttp.ClientSession() as session:
            semaphore = asyncio.Semaphore(20)
            
            async def check_all(u):
                async with semaphore:
                    tg = await check_tg_username(u)
                    ig = await check_ig_username(u.lower())
                    tk = await check_tk_username(u.lower())
                    return {"tg": tg, "ig": ig, "tk": tk}
            
            tasks = [check_all(u) for u in usernames]
            results = await asyncio.gather(*tasks)
            
            for r in results:
                if r["tg"]: all_found["tg"].append(r["tg"])
                if r["ig"]: all_found["ig"].append(r["ig"])
                if r["tk"]: all_found["tk"].append(r["tk"])
        
        result_text = "✅ <b>نتائج الصيد الشامل:</b>\n\n"
        result_text += f"📱 تيليجرام: {len(all_found['tg'])} يوزر\n"
        result_text += f"📷 انستجرام: {len(all_found['ig'])} يوزر\n"
        result_text += f"🎵 تيكتوك: {len(all_found['tk'])} يوزر\n"
        
        if all_found["tg"]:
            result_text += f"\n<b>أفضل يوزرات تيليجرام:</b>\n"
            for u in all_found["tg"][:5]:
                result_text += f"{u}\n"
        
        await msg.delete()
        await query.edit_message_text(result_text, reply_markup=back_keyboard(), parse_mode=ParseMode.HTML)
        return
    
    # قائمة التحميل
    if data == "video_info":
        await query.edit_message_text("🎬 <b>اختر منصة التحميل:</b>", reply_markup=video_platforms_keyboard(), parse_mode=ParseMode.HTML)
        return
    
    # منصات التحميل
    if data.startswith("dl_"):
        platform = data.replace("dl_", "")
        await query.edit_message_text(
            f"🎬 <b>تحميل من {platform}</b>\n\nأرسل رابط الفيديو:",
            reply_markup=back_keyboard(),
            parse_mode=ParseMode.HTML
        )
        user_states[user_id] = f"waiting_video_{platform}"
        return
    
    # معلومات
    if data == "info_info":
        await query.edit_message_text(
            "🔍 <b>أرسل يوزر تيليجرام:</b>\nمثال: @username",
            reply_markup=back_keyboard(),
            parse_mode=ParseMode.HTML
        )
        user_states[user_id] = "waiting_info"
        return
    
    # فتح بالآيدي
    if data == "open_info":
        await query.edit_message_text(
            "🔗 <b>أرسل الآيدي الرقمي:</b>\n\nمثال: 123456789",
            reply_markup=back_keyboard(),
            parse_mode=ParseMode.HTML
        )
        user_states[user_id] = "waiting_open"
        return
    
    # تحويل
    if data == "resolve_info":
        await query.edit_message_text(
            "🔄 <b>أرسل اليوزر أو الآيدي:</b>",
            reply_markup=back_keyboard(),
            parse_mode=ParseMode.HTML
        )
        user_states[user_id] = "waiting_resolve"
        return
    
    # فحص
    if data == "check_info":
        await query.edit_message_text(
            "✅ <b>أرسل اليوزر للفحص:</b>",
            reply_markup=back_keyboard(),
            parse_mode=ParseMode.HTML
        )
        user_states[user_id] = "waiting_check"
        return

# ============================================
# معالجة الرسائل
# ============================================
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()
    state = user_states.get(user_id, "")
    
    if not state:
        return
    
    # تحميل فيديو
    if state.startswith("waiting_video_"):
        platform = state.replace("waiting_video_", "")
        await update.message.reply_text("⏳ <b>جاري معالجة الرابط...</b>", parse_mode=ParseMode.HTML)
        
        result = await download_video(text, platform)
        
        if result.get("success"):
            await update.message.reply_text(
                f"✅ <b>تم التحميل!</b>\n\n🔗 <a href='{result['video_url']}'>اضغط للتحميل</a>",
                reply_markup=back_keyboard(),
                parse_mode=ParseMode.HTML
            )
        else:
            await update.message.reply_text(
                f"❌ <b>فشل التحميل:</b>\n{result.get('error', 'خطأ غير معروف')}",
                reply_markup=back_keyboard(),
                parse_mode=ParseMode.HTML
            )
        
        del user_states[user_id]
        return
    
    # معلومات حساب
    if state == "waiting_info":
        username = text.replace("@", "").strip()
        await update.message.reply_text("🔍 <b>جاري جلب المعلومات...</b>", parse_mode=ParseMode.HTML)
        
        info = await get_telegram_info(username)
        
        if info.get("exists"):
            result_text = f"🔍 <b>معلومات @{username}:</b>\n\n"
            if info.get("display_name"):
                result_text += f"📛 <b>الاسم:</b> {info['display_name']}\n"
            if info.get("bio"):
                result_text += f"📝 <b>البايو:</b> {info['bio'][:200]}\n"
            result_text += f"\n🔗 <a href='{info['url']}'>فتح الحساب</a>"
            result_text += f"\n🔗 <a href='tg://user?id={username}'>فتح في التطبيق</a>"
        else:
            result_text = f"❌ <b>الحساب @{username} غير موجود</b>"
        
        await update.message.reply_text(result_text, reply_markup=back_keyboard(), parse_mode=ParseMode.HTML)
        del user_states[user_id]
        return
    
    # فتح بالآيدي
    if state == "waiting_open":
        entity_id = text.replace("@", "").strip()
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔗 فتح في تيليجرام", url=f"tg://user?id={entity_id}")],
            [InlineKeyboardButton("🌐 فتح في المتصفح", url=f"https://t.me/@id{entity_id}")],
            [InlineKeyboardButton("🔙 رجوع", callback_data="back_main")],
        ])
        
        await update.message.reply_text(
            f"🔗 <b>فتح بالآيدي: {entity_id}</b>\n\nاختر طريقة الفتح:",
            reply_markup=keyboard,
            parse_mode=ParseMode.HTML
        )
        del user_states[user_id]
        return
    
    # تحويل
    if state == "waiting_resolve":
        entity = text.replace("@", "").strip()
        
        if entity.isdigit():
            # آيدي
            result_text = f"🔄 <b>تحويل الآيدي:</b>\n\n"
            result_text += f"🆔 <b>الآيدي:</b> {entity}\n"
            result_text += f"🔗 <b>رابط الحساب:</b> tg://user?id={entity}\n"
            result_text += f"🌐 <b>المتصفح:</b> https://t.me/@id{entity}"
        else:
            # يوزر
            result_text = f"🔄 <b>تحويل اليوزر:</b>\n\n"
            result_text += f"📛 <b>اليوزر:</b> @{entity}\n"
            result_text += f"🔗 <b>رابط الحساب:</b> https://t.me/{entity}\n"
            result_text += f"📱 <b>فتح في التطبيق:</b> tg://resolve?domain={entity}"
        
        await update.message.reply_text(result_text, reply_markup=back_keyboard(), parse_mode=ParseMode.HTML)
        del user_states[user_id]
        return
    
    # فحص يوزر
    if state == "waiting_check":
        username = text.replace("@", "").strip()
        await update.message.reply_text("✅ <b>جاري الفحص...</b>", parse_mode=ParseMode.HTML)
        
        tg_available = await check_tg_username(username)
        ig_available = await check_ig_username(username.lower())
        tk_available = await check_tk_username(username.lower())
        
        result_text = f"✅ <b>نتائج فحص: @{username}</b>\n\n"
        result_text += f"📱 تيليجرام: {tg_available if tg_available else '❌ مستخدم'}\n"
        result_text += f"📷 انستجرام: {ig_available if ig_available else '❌ مستخدم'}\n"
        result_text += f"🎵 تيكتوك: {tk_available if tk_available else '❌ مستخدم'}\n"
        
        await update.message.reply_text(result_text, reply_markup=back_keyboard(), parse_mode=ParseMode.HTML)
        del user_states[user_id]
        return

# ============================================
# Keep Alive Server
# ============================================
from flask import Flask
from threading import Thread

flask_app = Flask('')

@flask_app.route('/')
def home():
    return "🐙 KRAKEN BOT IS ALIVE!"

@flask_app.route('/health')
def health():
    return "OK", 200

def run_server():
    flask_app.run(host='0.0.0.0', port=5000)

def keep_alive():
    Thread(target=run_server, daemon=True).start()

# ============================================
# تشغيل البوت
# ============================================
def main():
    print("🐙 KRAKEN MULTI-TOOL BOT")
    print("="*40)
    
    # Keep alive server
    keep_alive()
    
    # إنشاء البوت
    app = Application.builder().token(TOKEN).build()
    
    # الأوامر
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("hunt", hunt_command))
    app.add_handler(CommandHandler("video", video_command))
    app.add_handler(CommandHandler("info", info_command))
    app.add_handler(CommandHandler("open", open_command))
    app.add_handler(CommandHandler("resolve", resolve_command))
    app.add_handler(CommandHandler("check", check_command))
    
    # الكول باك
    app.add_handler(CallbackQueryHandler(button_handler))
    
    # الرسائل
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    
    print("✅ البوت يعمل الآن!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
