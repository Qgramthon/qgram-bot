import asyncio
import io
import logging
from telethon import events
from telethon.errors import FloodWaitError
from telethon.tl.functions.account import UpdateProfileRequest
from telethon.tl.functions.photos import UploadProfilePhotoRequest, DeletePhotosRequest
from telethon.tl.functions.users import GetFullUserRequest
from shared import (
    active_clients, muted_users, taqleed_users, ent7al_users, ent7al_original,
    client_me, track_command, logger
)

async def get_user_info_full(client, user_id):
    try:
        user = await client.get_entity(user_id)
        name = user.first_name or ""
        if user.last_name:
            name += f" {user.last_name}"
        bio = ""
        try:
            full = await client(GetFullUserRequest(user_id))
            if full.full_user.about:
                bio = full.full_user.about
        except:
            pass
        return {
            'name': name.strip() or "غير معروف",
            'first_name': user.first_name or '',
            'last_name': user.last_name or '',
            'bio': bio,
            'id': user.id
        }
    except:
        return None

async def change_profile_photo(client, user_id, phone):
    """تغيير الصورة دون حذف القديمة (الرفع يستبدل الصورة الحالية تلقائياً)"""
    try:
        bio = io.BytesIO()
        await client.download_profile_photo(user_id, file=bio)
        bio.seek(0)
        uploaded = await client.upload_file(bio, file_name="photo.jpg")
        await client(UploadProfilePhotoRequest(file=uploaded))
        await asyncio.sleep(2)
        return True
    except FloodWaitError as e:
        logger.warning(f"Flood wait {e.seconds}s during photo change for {phone}")
        await asyncio.sleep(e.seconds)
        try:
            bio = io.BytesIO()
            await client.download_profile_photo(user_id, file=bio)
            bio.seek(0)
            uploaded = await client.upload_file(bio, file_name="photo.jpg")
            await client(UploadProfilePhotoRequest(file=uploaded))
            await asyncio.sleep(2)
            return True
        except:
            return False
    except Exception as e:
        logger.error(f"Photo change failed for {phone}: {e}")
        return False

async def setup_handlers(client, phone):
    if phone not in muted_users:
        muted_users[phone] = {}
    if phone not in taqleed_users:
        taqleed_users[phone] = {}
    if phone not in ent7al_users:
        ent7al_users[phone] = False
    if phone not in ent7al_original:
        ent7al_original[phone] = {}

    @client.on(events.NewMessage(incoming=True))
    async def auto_mute(event):
        if event.is_private and event.sender_id in muted_users.get(phone, {}):
            try: await event.delete()
            except: pass

    @client.on(events.NewMessage(incoming=True))
    async def auto_taqleed(event):
        sender_id = event.sender_id
        if sender_id and sender_id in taqleed_users.get(phone, {}):
            if event.text and not event.text.startswith('.'):
                await asyncio.sleep(0.3)
                try: await event.reply(event.text)
                except: pass

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
        if target and target in taqleed_users.get(phone, {}):
            del taqleed_users[phone][target]
        await event.edit("**• تم فك التقليد**")

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
            await event.edit("**• فشل الانتحال**")
            return

        target_info = await get_user_info_full(client, target_user.id)
        if not target_info:
            await event.edit("**• فشل الانتحال**")
            return

        # جلب بياناتي الحالية من السيرفر مباشرة لضمان الدقة
        me = await client.get_me()
        client_me[phone] = me

        # حفظ نسخة أصلية كاملة
        original = {
            'first_name': me.first_name or '',
            'last_name': me.last_name or '',   # مهم لاستعادة الاسم بدقة
            'photo_bytes': None,
            'about': ''
        }

        try:
            fu = await client(GetFullUserRequest('me'))
            if fu.full_user.about:
                original['about'] = fu.full_user.about
        except: pass

        try:
            if me.photo:
                bio_orig = io.BytesIO()
                await client.download_profile_photo('me', file=bio_orig)
                bio_orig.seek(0)
                original['photo_bytes'] = bio_orig.getvalue()
        except Exception as e:
            logger.warning(f"Could not backup original photo: {e}")

        ent7al_original[phone] = original

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
            try:
                await client(UpdateProfileRequest(
                    first_name=target_info['first_name'],
                    last_name=target_info['last_name']
                ))
                name_ok = True
            except: pass
        except: pass

        # تغيير البايو
        bio_ok = False
        target_bio = target_info['bio']
        try:
            await client(UpdateProfileRequest(about=target_bio[:70] if target_bio else ''))
            await asyncio.sleep(1)
            bio_ok = True
        except FloodWaitError as e:
            await asyncio.sleep(e.seconds)
            try:
                await client(UpdateProfileRequest(about=target_bio[:70] if target_bio else ''))
                bio_ok = True
            except: pass
        except: pass

        # تغيير الصورة (رفع مباشر)
        photo_ok = await change_profile_photo(client, target_user.id, phone)

        ent7al_users[phone] = True

        if name_ok and bio_ok and photo_ok:
            await event.edit("**• تم الانتحال**")
        elif not name_ok and not bio_ok and not photo_ok:
            await event.edit("**• فشل الانتحال**")
        else:
            await event.edit("**• تم الانتحال جزئياً**")

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.الغاء انتحال$'))
    async def unent7al(event):
        track_command(phone, ".الغاء انتحال")
        await event.edit("**• جاري استعادة الحساب...**")

        if not ent7al_users.get(phone) or not ent7al_original.get(phone):
            await event.edit("**• لا يوجد انتحال**")
            return

        original = ent7al_original[phone]

        # استعادة الاسم (3 محاولات لضمان النجاح)
        restored_name = False
        first = original.get('first_name', '')
        last = original.get('last_name', '')
        for attempt in range(3):
            try:
                await client(UpdateProfileRequest(
                    first_name=first,
                    last_name=last
                ))
                await asyncio.sleep(2)
                restored_name = True
                break
            except FloodWaitError as e:
                logger.info(f"Flood wait {e.seconds}s while restoring name")
                await asyncio.sleep(e.seconds)
            except Exception as e:
                logger.error(f"Restore name attempt {attempt+1} failed: {e}")
                await asyncio.sleep(2)

        if not restored_name:
            logger.error(f"Could not restore name for {phone} after 3 attempts")

        # استعادة الصورة الأصلية من البايتات
        if original.get('photo_bytes'):
            try:
                bio = io.BytesIO(original['photo_bytes'])
                bio.seek(0)
                uploaded = await client.upload_file(bio, file_name="original.jpg")
                await client(UploadProfilePhotoRequest(file=uploaded))
                await asyncio.sleep(1)
                logger.info(f"Original photo restored")
            except FloodWaitError as e:
                await asyncio.sleep(e.seconds)
                try:
                    bio = io.BytesIO(original['photo_bytes'])
                    bio.seek(0)
                    uploaded = await client.upload_file(bio, file_name="original.jpg")
                    await client(UploadProfilePhotoRequest(file=uploaded))
                except: pass
            except Exception as e:
                logger.error(f"Restore photo failed: {e}")
        else:
            # لا توجد صورة أصلية، نحذف الصورة الحالية إن وجدت
            try:
                current = await client.get_profile_photos('me', limit=10)
                if current:
                    await client(DeletePhotosRequest(id=[p.id for p in current]))
                    await asyncio.sleep(2)
            except: pass

        # استعادة البايو
        try:
            await client(UpdateProfileRequest(about=original.get('about', '')))
            await asyncio.sleep(1)
        except FloodWaitError as e:
            await asyncio.sleep(e.seconds)
            try:
                await client(UpdateProfileRequest(about=original.get('about', '')))
            except: pass
        except Exception as e:
            logger.error(f"Restore bio failed: {e}")

        ent7al_users[phone] = False
        ent7al_original[phone] = {}
        await event.edit("**• تم فك الانتحال**")

    logger.info(f"Handlers (taqleed/ent7al) ready for {phone}")
