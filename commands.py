import asyncio
import io
from telethon import events
from telethon.errors import FloodWaitError
from telethon.tl.functions.account import UpdateProfileRequest
from telethon.tl.functions.photos import UploadProfilePhotoRequest, DeletePhotosRequest
from telethon.tl.functions.users import GetFullUserRequest
from shared import (
    active_clients, pending_logins, api_configs_storage,
    muted_users, taqleed_users, ent7al_users, ent7al_original,
    client_me, logger, track_command,
    DEV_PHONE
)

async def get_user_info_full(client, user_id):
    try:
        user = await client.get_entity(user_id)
        name = user.first_name or "غير معروف"
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
            'name': name,
            'first_name': user.first_name or '',
            'last_name': user.last_name or '',
            'bio': bio,
            'id': user.id
        }
    except:
        return None

async def change_profile_photo(client, user_id, phone):
    try:
        current = await client.get_profile_photos('me', limit=10)
        if current:
            await client(DeletePhotosRequest(id=[p.id for p in current]))
            await asyncio.sleep(2)
        bio = io.BytesIO()
        await client.download_profile_photo(user_id, file=bio)
        bio.seek(0)
        uploaded = await client.upload_file(bio, file_name="photo.jpg")
        await client(UploadProfilePhotoRequest(file=uploaded))
        await asyncio.sleep(1)
        return True
    except Exception as e:
        logger.error(f"Photo change error for {phone}: {e}")
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

        me = client_me.get(phone) or await client.get_me()
        client_me[phone] = me

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
        except: pass

        try:
            my_photos = await client.get_profile_photos('me', limit=1)
            if my_photos:
                original['photo'] = my_photos[0]
        except: pass

        ent7al_original[phone] = original

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

        try:
            current = await client.get_profile_photos('me', limit=10)
            if current:
                await client(DeletePhotosRequest(id=[p.id for p in current]))
                await asyncio.sleep(2)
            if original.get('photo'):
                bio = io.BytesIO()
                await client.download_profile_photo(original['photo'], file=bio)
                bio.seek(0)
                uploaded = await client.upload_file(bio, file_name="orig.jpg")
                await client(UploadProfilePhotoRequest(file=uploaded))
                await asyncio.sleep(1)
        except: pass

        try:
            await client(UpdateProfileRequest(
                first_name=original.get('first_name', ''),
                last_name=original.get('last_name', '')
            ))
            await asyncio.sleep(1)
        except FloodWaitError as e:
            await asyncio.sleep(e.seconds)
        except: pass

        try:
            await client(UpdateProfileRequest(about=original.get('about', '')))
            await asyncio.sleep(1)
        except FloodWaitError as e:
            await asyncio.sleep(e.seconds)
        except: pass

        ent7al_users[phone] = False
        ent7al_original[phone] = {}
        await event.edit("**• تم فك الانتحال**")

    logger.info(f"Handlers ready (taqleed/ent7al) for {phone}")
