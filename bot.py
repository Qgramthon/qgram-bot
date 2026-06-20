# bot.py
import asyncio, uuid, os
from telethon import TelegramClient, events, Button
from shared import *
from collections import Counter

bot = TelegramClient(f'bot_session_{uuid.uuid4().hex[:6]}', BOT_API_ID, BOT_API_HASH)

START_IMAGE = "start.jpg"

# --- القائمة البيضاء (Whitelist) ---
allowed_chats = set()

# --- قائمة الكلمات المسموحة في الرسائل الصادرة (تمنع أي سبام) ---
ALLOWED_KEYWORDS = ["Qthon", "تيليثون", "لوحة تحكم", "طريقة جلب", "التحقق من المطور",
                    "تم التحقق", "فشل التحقق", "التحقق معطل", "خيارات المطور",
                    "المستخدمين", "النشطاء", "أكثر الأوامر", "المجموعات", "القنوات",
                    "إذاعة", "رجوع", "قريباً", "غير مصرح", "تم تفعيل"]

def is_allowed_text(text):
    if not text:
        return False
    for keyword in ALLOWED_KEYWORDS:
        if keyword in text:
            return True
    return False

def dev_panel_markup():
    lock_text = "فتح خيارات المطور" if dev_access_locked else "قفل خيارات المطور"
    return [
        [Button.inline("عدد المستخدمين", b"dev_users"),
         Button.inline("النشطاء حالياً", b"dev_active")],
        [Button.inline("أكثر الأوامر", b"dev_topcmd"),
         Button.inline("قائمة المجموعات", b"dev_groups")],
        [Button.inline("قائمة القنوات", b"dev_channels"),
         Button.inline("إذاعة", b"dev_broadcast")],
        [Button.inline(lock_text, b"dev_lock")],
    ]

# --- منع إرسال أي رسالة غير مسموح بها ---
@bot.on(events.NewMessage(outgoing=True))
async def block_unauthorized(event):
    if event.chat_id not in allowed_chats:
        await event.delete()
        logger.warning(f"تم حذف رسالة صادرة غير مصرح بها إلى {event.chat_id}")
        return
    if not is_allowed_text(event.text):
        await event.delete()
        logger.warning(f"تم حذف رسالة غير مصرح بها نصياً إلى {event.chat_id}: {event.text[:50]}")

@bot.on(events.NewMessage(pattern='/start'))
async def bot_start(event):
    allowed_chats.add(event.chat_id)
    user_id = event.sender_id

    buttons = [
        [Button.url("الحصول على بياناتي", "https://my.telegram.org/apps")],
        [Button.url("بدء التنصيب", "https://t.me/Qthon_bot")]
    ]

    caption = (
        "**• لبدء تنصيب تيليثون ڪيوجࢪام 🜲**\n"
        "**- قم بجلب معلومات حسابك**\n"
        "**- لبدء تنصيب إفتح تطبيق البوت**\n"
        "**- أكمل إجراءات التنصيب المطلوبة**\n"
        "**- لن يستغرق التنصيب الكثير من الوقت**"
    )

    # إرسال الصورة إذا كانت موجودة في المشروع
    if os.path.exists(START_IMAGE):
        await event.respond(
            file=START_IMAGE,
            caption=caption,
            buttons=buttons,
            parse_mode='md'
        )
    else:
        await event.respond(caption, buttons=buttons, parse_mode='md')

    # لوحة المطور تظهر فقط للمطور بعد /start
    if is_dev(user_id):
        await event.respond("**لوحة تحكم Qthon**\n\nاختر خياراً.",
                            buttons=dev_panel_markup(), parse_mode='md')

@bot.on(events.CallbackQuery(data=b"how_to_get_data"))
async def how_to_get_data(event):
    allowed_chats.add(event.chat_id)
    await event.answer(
        "🔹 **طريقة جلب بيانات API:**\n\n"
        "1. افتح المتصفح واذهب إلى:\n   my.telegram.org\n\n"
        "2. أدخل رقم هاتفك الدولي\n   مثال: +2010xxxxxxxx\n\n"
        "3. ستستلم رمز تحقق في تيليجرام، أدخله في الموقع.\n\n"
        "4. بعد الدخول، اختر: «API development tools»\n\n"
        "5. املأ النموذج:\n"
        "   - App title: أي اسم (مثلاً Qthon)\n"
        "   - Short name: اسم قصير (مثلاً qthon)\n"
        "   - Platform: اختر «Desktop»\n\n"
        "6. اضغط «Create application» سيظهر لك:\n"
        "   • api_id (رقم)\n"
        "   • api_hash (نص طويل)\n\n"
        "7. انسخهما واستخدمهما في موقع التنصيب.",
        alert=True)

@bot.on(events.CallbackQuery(data=b"dev_login"))
async def dev_login(event):
    allowed_chats.add(event.chat_id)
    if not is_dev(event.sender_id):
        await event.answer("غير مصرح", alert=True)
        return
    pending_verify[event.sender_id] = True
    buttons = [[Button.request_phone("مشاركة رقم الهاتف", resize=True)]]
    await event.edit("**التحقق من المطور**\n\nشارك رقم هاتفك للتحقق كمالك.",
                     buttons=buttons, parse_mode='md')
    await event.answer()

@bot.on(events.NewMessage(func=lambda e: e.message.contact or e.sender_id in pending_verify))
async def handle_phone_verify(event):
    allowed_chats.add(event.chat_id)
    user_id = event.sender_id
    if user_id not in pending_verify:
        return
    if dev_access_locked and not is_dev(user_id):
        del pending_verify[user_id]
        await event.respond("**التحقق معطل حالياً**\nخيارات المطور مقفلة.", parse_mode='md')
        return
    phone = (f"+{event.message.contact.phone_number}" if event.message.contact
             else event.text.strip().replace("+", ""))
    if not phone.startswith('+'): phone = f"+{phone}"
    if phone == DEV_PHONE:
        verified_devs.add(user_id)
        del pending_verify[user_id]
        await event.respond("**تم التحقق من الهوية!**\n\nمرحباً بك في لوحة التحكم.",
                            buttons=dev_panel_markup(), parse_mode='md')
        await notify_dev(f"تم تفعيل مطور جديد: {phone}")
    else:
        await event.respond("**فشل التحقق**\nرقم الهاتف غير مطابق.", parse_mode='md')

@bot.on(events.CallbackQuery())
async def dev_callback(event):
    allowed_chats.add(event.chat_id)
    data = event.data.decode()
    if not is_dev(event.sender_id):
        await event.answer("غير مصرح", alert=True)
        return

    if data == "dev_back":
        await event.edit("**لوحة تحكم Qthon**\n\nاختر خياراً.",
                         buttons=dev_panel_markup(), parse_mode='md')
        await event.answer()
        return

    if data == "dev_lock":
        global dev_access_locked
        dev_access_locked = not dev_access_locked
        state = "مقفلة" if dev_access_locked else "مفتوحة"
        await event.answer(f"خيارات المطور الآن {state}", alert=True)
        await event.edit("**لوحة تحكم Qthon**\n\nاختر خياراً.",
                         buttons=dev_panel_markup(), parse_mode='md')
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
            display = f"{name} - @{uname}" if uname else f"{name} - {phone}"
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
                groups = [d for d in dialogs if d.is_group and not d.is_channel]
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
                channels = [d for d in dialogs if d.is_channel and not d.is_group]
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
