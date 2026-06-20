import asyncio
import io
import os
import logging
from telethon import events
from telethon.errors import FloodWaitError, ChatAdminRequiredError
from telethon.tl.functions.account import UpdateProfileRequest
from telethon.tl.functions.photos import UploadProfilePhotoRequest, DeletePhotosRequest
from telethon.tl.types import InputPhoto, DocumentAttributeAudio, DocumentAttributeVideo
from telethon.tl.functions.users import GetFullUserRequest
from telethon.tl.functions.channels import InviteToChannelRequest
from telethon.tl.functions.messages import AddChatUserRequest
from shared import (
    active_clients, muted_users, taqleed_users, ent7al_users, ent7al_original,
    client_me, track_command, logger, TEMP_DIR
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
    try:
        bio = io.BytesIO()
        await client.download_profile_photo(user_id, file=bio)
        bio.seek(0)
        uploaded = await client.upload_file(bio, file_name="photo.jpg")
        result = await client(UploadProfilePhotoRequest(file=uploaded))
        await asyncio.sleep(2)
        if hasattr(result, 'photo') and hasattr(result.photo, 'id'):
            return True, result.photo.id
        return True, None
    except FloodWaitError as e:
        logger.warning(f"Flood wait {e.seconds}s during photo change for {phone}")
        await asyncio.sleep(e.seconds)
        try:
            bio = io.BytesIO()
            await client.download_profile_photo(user_id, file=bio)
            bio.seek(0)
            uploaded = await client.upload_file(bio, file_name="photo.jpg")
            result = await client(UploadProfilePhotoRequest(file=uploaded))
            await asyncio.sleep(2)
            if hasattr(result, 'photo') and hasattr(result.photo, 'id'):
                return True, result.photo.id
            return True, None
        except:
            return False, None
    except Exception as e:
        logger.error(f"Photo change failed for {phone}: {e}")
        return False, None

async def setup_handlers(client, phone):
    if phone not in muted_users:
        muted_users[phone] = {}
    if phone not in taqleed_users:
        taqleed_users[phone] = {}
    if phone not in ent7al_users:
        ent7al_users[phone] = False
    if phone not in ent7al_original:
        ent7al_original[phone] = {}

    # --------------------- التقليد ---------------------
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

    # --------------------- الانتحال ---------------------
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

        me = await client.get_me()
        client_me[phone] = me

        original = {
            'first_name': me.first_name or '',
            'last_name': me.last_name if me.last_name is not None else '',
            'photo_bytes': None,
            'added_photo_id': None,
            'about': ''
        }

        try:
            fu = await client(GetFullUserRequest('me'))
            if fu.full_user.about:
                original['about'] = fu.full_user.about
        except: pass

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
            await asyncio.sleep(0.5)
            bio_ok = True
        except FloodWaitError as e:
            await asyncio.sleep(e.seconds)
            try:
                await client(UpdateProfileRequest(about=target_bio[:70] if target_bio else ''))
                bio_ok = True
            except: pass
        except: pass

        photo_ok, added_id = await change_profile_photo(client, target_user.id, phone)
        if photo_ok and added_id:
            original['added_photo_id'] = added_id

        ent7al_original[phone] = original
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
        await event.edit("**• جاري إلغاء الانتحال...**")

        if not ent7al_users.get(phone) or not ent7al_original.get(phone):
            await event.edit("**• لا يوجد انتحال**")
            return

        original = ent7al_original[phone]

        restored_name = False
        first = original.get('first_name', '')
        last = original.get('last_name', '')
        for attempt in range(3):
            try:
                await client(UpdateProfileRequest(
                    first_name=first,
                    last_name=last
                ))
                await asyncio.sleep(1.5)
                me_now = await client.get_me()
                if me_now.first_name == first and (me_now.last_name or '') == last:
                    restored_name = True
                    break
            except FloodWaitError as e:
                await asyncio.sleep(e.seconds)
            except Exception as e:
                logger.error(f"Restore name attempt {attempt+1}: {e}")
                await asyncio.sleep(1)

        if not restored_name:
            logger.error(f"Could not fully restore name for {phone}")

        if original.get('added_photo_id'):
            try:
                await client(DeletePhotosRequest(id=[InputPhoto(
                    id=original['added_photo_id'],
                    access_hash=0,
                    file_reference=b''
                )]))
                await asyncio.sleep(2)
                logger.info(f"Deleted impersonated photo ID {original['added_photo_id']}")
            except FloodWaitError as e:
                await asyncio.sleep(e.seconds)
                try:
                    await client(DeletePhotosRequest(id=[InputPhoto(
                        id=original['added_photo_id'],
                        access_hash=0,
                        file_reference=b''
                    )]))
                except: pass
            except Exception as e:
                logger.error(f"Failed to delete added photo: {e}")
        else:
            try:
                current_photos = await client.get_profile_photos('me', limit=1)
                if current_photos:
                    p = current_photos[0]
                    await client(DeletePhotosRequest(id=[InputPhoto(
                        id=p.id,
                        access_hash=p.access_hash,
                        file_reference=p.file_reference
                    )]))
                    await asyncio.sleep(2)
                    logger.info("Deleted most recent photo as fallback")
            except Exception as e:
                logger.error(f"Fallback photo deletion failed: {e}")

        try:
            await client(UpdateProfileRequest(about=original.get('about', '')))
        except FloodWaitError as e:
            await asyncio.sleep(e.seconds)
            try:
                await client(UpdateProfileRequest(about=original.get('about', '')))
            except: pass
        except Exception as e:
            logger.error(f"Restore bio failed: {e}")

        ent7al_users[phone] = False
        ent7al_original[phone] = {}
        await event.edit("**• تم إلغاء الانتحال**")

    # --------------------- إضافة أعضاء من جروب خارجي ---------------------
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.اضافة (\d+) (@?\w+)$'))
    async def add_members_from_group(event):
        if not event.is_group:
            await event.edit("**• الأمر يعمل في المجموعات فقط**")
            return

        count = int(event.pattern_match.group(1))
        target_username = event.pattern_match.group(2).strip()
        await event.edit(f"**• جاري سحب {count} عضو من {target_username} وإضافتهم هنا...**")

        try:
            source_group = await client.get_entity(target_username)
        except Exception as e:
            await event.edit(f"**• لم يتم العثور على الجروب {target_username}**")
            return

        try:
            await client.join_channel(source_group)
            await asyncio.sleep(3)
        except:
            pass

        added = 0
        failed = 0
        try:
            participants_iter = client.iter_participants(source_group, limit=count)
            async for user in participants_iter:
                if user.bot or user.deleted:
                    continue
                try:
                    if hasattr(event.chat, 'megagroup') and event.chat.megagroup:
                        await client(InviteToChannelRequest(channel=event.chat_id, users=[user.id]))
                    else:
                        await client(AddChatUserRequest(chat_id=event.chat_id, user_id=user.id, fwd_limit=10))
                    added += 1
                    await asyncio.sleep(1.5)
                except FloodWaitError as e:
                    logger.info(f"Flood wait {e.seconds}s")
                    await asyncio.sleep(e.seconds)
                    try:
                        if hasattr(event.chat, 'megagroup') and event.chat.megagroup:
                            await client(InviteToChannelRequest(channel=event.chat_id, users=[user.id]))
                        else:
                            await client(AddChatUserRequest(chat_id=event.chat_id, user_id=user.id, fwd_limit=10))
                        added += 1
                    except:
                        failed += 1
                except ChatAdminRequiredError:
                    await event.edit("**• الصلاحيات غير كافية - يجب أن تكون مشرفًا في هذا الجروب**")
                    return
                except Exception as e:
                    logger.warning(f"Failed to add {user.id}: {e}")
                    failed += 1
                    if "PEER_FLOOD" in str(e) or "USER_PRIVACY_RESTRICTED" in str(e):
                        break

            result_msg = f"**• تمت إضافة {added} عضو بنجاح**"
            if failed > 0:
                result_msg += f"\n• فشل في إضافة {failed} عضو (بسبب الخصوصية أو الحظر)"
            await event.edit(result_msg)

        except ChatAdminRequiredError:
            await event.edit("**• لا تملك صلاحيات لسحب الأعضاء من الجروب المصدر**")
        except Exception as e:
            await event.edit(f"**• فشل في جلب الأعضاء: {str(e)[:50]}**")

    # --------------------- تحميل الصوت (يوت) ---------------------
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.يوت (.+)'))
    async def youtube_audio(event):
        query = event.pattern_match.group(1).strip()
        await event.edit("**• جاري البحث عن الفيديو...**")

        try:
            import yt_dlp
        except ImportError:
            await event.edit("**• مكتبة yt-dlp غير مثبتة**")
            return

        final_filepath = None

        def postprocessor_hook(d):
            nonlocal final_filepath
            if d['status'] == 'finished':
                final_filepath = d.get('info_dict', {}).get('filepath') or d.get('postprocessor_result', {}).get('filepath')

        if query.startswith("http"):
            search_query = query
        else:
            search_query = f"ytsearch1:{query}"

        ydl_opts = {
            'outtmpl': f'{TEMP_DIR}/%(title)s.%(ext)s',   # الاسم الأصلي للفيديو
            'quiet': True,
            'no_warnings': True,
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'postprocessor_hooks': [postprocessor_hook],
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(search_query, download=True)
                await asyncio.sleep(1)

            if final_filepath and os.path.exists(final_filepath):
                filepath = final_filepath
            else:
                base = ydl.prepare_filename(info)
                base_no_ext = os.path.splitext(base)[0]
                for ext in ['.mp3', '.m4a', '.webm', '.opus', '.ogg']:
                    candidate = base_no_ext + ext
                    if os.path.exists(candidate):
                        filepath = candidate
                        break
                else:
                    await event.edit("**• فشل في العثور على الملف بعد التحميل**")
                    return

            await client.send_file(
                event.chat_id,
                filepath,
                caption=f"**🎵 {info.get('title', 'بدون عنوان')}**",
                attributes=[DocumentAttributeAudio(
                    duration=info.get('duration', 0),
                    title=info.get('title', ''),
                    performer=info.get('uploader', '')
                )]
            )
            await event.delete()
            os.remove(filepath)

        except Exception as e:
            await event.edit(f"**• فشل التحميل:**\n{str(e)[:200]}")

    # --------------------- تحميل الفيديو (فيد) ---------------------
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.فيد (.+)'))
    async def video_download(event):
        query = event.pattern_match.group(1).strip()
        await event.edit("**• جاري تحميل الفيديو...**")

        try:
            import yt_dlp
        except ImportError:
            await event.edit("**• مكتبة yt-dlp غير مثبتة**")
            return

        # سنستخدم نفس منطق الاسم الأصلي
        if query.startswith("http"):
            search_query = query
        else:
            search_query = f"ytsearch1:{query}"

        ydl_opts = {
            'outtmpl': f'{TEMP_DIR}/%(title)s.%(ext)s',   # العنوان الأصلي
            'quiet': True,
            'no_warnings': True,
            'format': 'best[height<=720]',   # جودة 720p كحد أقصى لتجنب حجم كبير
            'merge_output_format': 'mp4',
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(search_query, download=True)
                filepath = ydl.prepare_filename(info)
                if not os.path.exists(filepath):
                    # في بعض الأحيان قد يكون الملف بصيغة مختلفة
                    base = os.path.splitext(filepath)[0]
                    for ext in ['.mp4', '.webm', '.mkv']:
                        if os.path.exists(base + ext):
                            filepath = base + ext
                            break
                    else:
                        await event.edit("**• فشل في العثور على ملف الفيديو**")
                        return

            await client.send_file(
                event.chat_id,
                filepath,
                caption=f"**🎬 {info.get('title', 'بدون عنوان')}**",
                attributes=[DocumentAttributeVideo(
                    duration=info.get('duration', 0),
                    w=info.get('width', 0),
                    h=info.get('height', 0),
                    supports_streaming=True
                )]
            )
            await event.delete()
            os.remove(filepath)

        except Exception as e:
            await event.edit(f"**• فشل تحميل الفيديو:**\n{str(e)[:200]}")

    logger.info(f"Handlers (taqleed/ent7al/add/youtube_audio/video) ready for {phone}")
