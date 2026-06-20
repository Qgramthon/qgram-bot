import asyncio
import io
import os
import logging
import subprocess
from telethon import events
from telethon.errors import FloodWaitError, ChatAdminRequiredError
from telethon.tl.functions.account import UpdateProfileRequest
from telethon.tl.functions.photos import UploadProfilePhotoRequest, DeletePhotosRequest
from telethon.tl.types import (
    InputPhoto, DocumentAttributeAudio, DocumentAttributeVideo,
    InputGroupCall
)
from telethon.tl.functions.users import GetFullUserRequest
from telethon.tl.functions.channels import InviteToChannelRequest
from telethon.tl.functions.messages import AddChatUserRequest
from telethon.tl.functions.phone import GetGroupParticipants
from shared import (
    active_clients, muted_users, taqleed_users, ent7al_users, ent7al_original,
    client_me, track_command, logger, TEMP_DIR
)

def format_duration(seconds):
    if not seconds:
        return "0:00"
    mins, secs = divmod(int(seconds), 60)
    return f"{mins}:{secs:02d}"

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

    # --------------------- تحويل الصوت إلى نص (نسخ) ---------------------
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.نسخ$'))
    async def transcribe_voice(event):
        if not event.is_reply:
            await event.edit("**• يرجى الرد على رسالة صوتية**")
            return

        reply = await event.get_reply_message()
        if not reply.voice and not reply.audio:
            await event.edit("**• الرد على رسالة صوتية فقط**")
            return

        await event.edit("**• جاري تحويل الصوت إلى نص...**")

        try:
            import speech_recognition as sr
        except ImportError:
            await event.edit("**• مكتبة SpeechRecognition غير مثبتة**")
            return

        voice_path = os.path.join(TEMP_DIR, f"voice_{phone}_{reply.id}.ogg")
        await client.download_media(reply, voice_path)
        wav_path = voice_path.replace(".ogg", ".wav")

        try:
            subprocess.run(
                ["ffmpeg", "-i", voice_path, "-ac", "1", "-ar", "16000", wav_path],
                check=True, capture_output=True, timeout=30
            )

            recognizer = sr.Recognizer()
            with sr.AudioFile(wav_path) as source:
                audio_data = recognizer.record(source)
            text = recognizer.recognize_google(audio_data, language="ar-AR")

            await event.edit(f"**النص:**\n{text}")
        except subprocess.CalledProcessError as e:
            await event.edit(f"**• فشل تحويل الصوت: {e.stderr.decode()[:100]}**")
        except sr.UnknownValueError:
            await event.edit("**• لم يتم التعرف على أي كلام**")
        except sr.RequestError as e:
            await event.edit(f"**• خطأ في خدمة التعرف: {e}**")
        except Exception as e:
            await event.edit(f"**• فشل: {str(e)[:100]}**")
        finally:
            for p in [voice_path, wav_path]:
                if os.path.exists(p):
                    os.remove(p)

    # --------------------- تحويل صورة إلى استيكر (.استيك) ---------------------
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.استيك$'))
    async def photo_to_sticker(event):
        if not event.is_reply:
            await event.edit("**• يرجى الرد على صورة**")
            return
        reply = await event.get_reply_message()
        if not reply.photo:
            await event.edit("**• الرد على صورة فقط**")
            return
        await event.edit("**• جاري تحويل الصورة إلى استيكر...**")
        try:
            from PIL import Image
        except ImportError:
            await event.edit("**• مكتبة Pillow غير مثبتة**")
            return
        img_path = os.path.join(TEMP_DIR, f"img_{phone}_{reply.id}.jpg")
        stick_path = os.path.join(TEMP_DIR, f"sticker_{phone}_{reply.id}.webp")
        await client.download_media(reply, img_path)
        try:
            im = Image.open(img_path)
            im = im.convert("RGBA")
            im.thumbnail((512, 512), Image.LANCZOS)
            im.save(stick_path, "WEBP")
            await client.send_file(event.chat_id, stick_path)
            await event.delete()
        except Exception as e:
            await event.edit(f"**• فشل: {str(e)[:100]}**")
        finally:
            for p in [img_path, stick_path]:
                if os.path.exists(p):
                    os.remove(p)

    # --------------------- تحويل استيكر إلى صورة (.بيك) ---------------------
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.بيك$'))
    async def sticker_to_photo(event):
        if not event.is_reply:
            await event.edit("**• يرجى الرد على استيكر**")
            return
        reply = await event.get_reply_message()
        if not reply.sticker:
            await event.edit("**• الرد على استيكر فقط**")
            return
        await event.edit("**• جاري تحويل الاستيكر إلى صورة...**")
        try:
            from PIL import Image
        except ImportError:
            await event.edit("**• مكتبة Pillow غير مثبتة**")
            return
        stick_path = os.path.join(TEMP_DIR, f"sticker_{phone}_{reply.id}.webp")
        img_path = os.path.join(TEMP_DIR, f"img_{phone}_{reply.id}.png")
        await client.download_media(reply, stick_path)
        try:
            im = Image.open(stick_path)
            im.save(img_path, "PNG")
            await client.send_file(event.chat_id, img_path)
            await event.delete()
        except Exception as e:
            await event.edit(f"**• فشل: {str(e)[:100]}**")
        finally:
            for p in [stick_path, img_path]:
                if os.path.exists(p):
                    os.remove(p)

    # --------------------- تحميل الصوت (يوت) – تحسين السرعة ---------------------
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
        def hook(d):
            nonlocal final_filepath
            if d['status'] == 'finished':
                final_filepath = d.get('info_dict', {}).get('filepath') or d.get('postprocessor_result', {}).get('filepath')

        search_query = f"ytsearch1:{query}" if not query.startswith("http") else query
        ydl_opts = {
            'outtmpl': f'{TEMP_DIR}/%(title)s.%(ext)s',
            'quiet': True,
            'format': 'bestaudio[ext=m4a]/bestaudio',   # تنسيق أسرع للصوت
            'extractor_args': {'youtube': {'player_client': ['android']}},
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '128',               # جودة أقل → سرعة أعلى
            }],
            'postprocessor_hooks': [hook],
            'retries': 2,
            'fragment_retries': 2,
            'concurrent_fragment_downloads': 4,          # تحميل متوازي
            'nooverwrites': True,
            'no_color': True,
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

            duration_str = format_duration(info.get('duration', 0))
            caption = f"᥉᥆ᥙɾᥴꫀ Ϙƚһ᥆ꪀ\n• {duration_str} | ᥲᥙძᎥ᥆"

            await client.send_file(
                event.chat_id,
                filepath,
                caption=caption,
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

    # --------------------- تحميل الفيديو (فيد) – تحسين السرعة ---------------------
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.فيد (.+)'))
    async def video_download(event):
        query = event.pattern_match.group(1).strip()
        await event.edit("**• جاري تحميل الفيديو...**")

        try:
            import yt_dlp
        except ImportError:
            await event.edit("**• مكتبة yt-dlp غير مثبتة**")
            return

        final_filepath = None
        def hook(d):
            nonlocal final_filepath
            if d['status'] == 'finished':
                final_filepath = d.get('info_dict', {}).get('filepath') or d.get('postprocessor_result', {}).get('filepath')

        search_query = f"ytsearch1:{query}" if not query.startswith("http") else query
        ydl_opts = {
            'outtmpl': f'{TEMP_DIR}/%(title)s.%(ext)s',
            'quiet': True,
            'format': 'best[height<=480][ext=mp4]/best[height<=480]',   # جودة 480p أسرع
            'merge_output_format': 'mp4',
            'extractor_args': {'youtube': {'player_client': ['android']}},
            'postprocessor_hooks': [hook],
            'retries': 2,
            'fragment_retries': 2,
            'concurrent_fragment_downloads': 4,
            'nooverwrites': True,
            'no_color': True,
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
                for ext in ['.mp4', '.webm', '.mkv']:
                    candidate = base_no_ext + ext
                    if os.path.exists(candidate):
                        filepath = candidate
                        break
                else:
                    await event.edit("**• فشل في العثور على ملف الفيديو**")
                    return

            duration_str = format_duration(info.get('duration', 0))
            caption = f"᥉᥆ᥙɾᥴꫀ Ϙƚһ᥆ꪀ\n• {duration_str} | ᥎Ꭵძꫀ᥆"

            await client.send_file(
                event.chat_id,
                filepath,
                caption=caption,
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

    # --------------------- تحميل بنترست (بين) ---------------------
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.بين (.+)'))
    async def pinterest_download(event):
        url = event.pattern_match.group(1).strip()
        if "pinterest.com" not in url and "pin.it" not in url:
            await event.edit("**• الرجاء إدخال رابط بنترست صالح**")
            return
        await event.edit("**• جاري التحميل من بنترست...**")

        try:
            import yt_dlp
        except ImportError:
            await event.edit("**• مكتبة yt-dlp غير مثبتة**")
            return

        final_filepath = None
        def hook(d):
            nonlocal final_filepath
            if d['status'] == 'finished':
                final_filepath = d.get('info_dict', {}).get('filepath') or d.get('postprocessor_result', {}).get('filepath')

        ydl_opts = {
            'outtmpl': f'{TEMP_DIR}/%(title)s.%(ext)s',
            'quiet': True,
            'format': 'best',
            'merge_output_format': 'mp4',
            'extractor_args': {'youtube': {'player_client': ['android']}},
            'postprocessor_hooks': [hook],
        }
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                await asyncio.sleep(1)

            if final_filepath and os.path.exists(final_filepath):
                filepath = final_filepath
            else:
                base = ydl.prepare_filename(info)
                base_no_ext = os.path.splitext(base)[0]
                for ext in ['.mp4', '.webm', '.jpg', '.jpeg', '.png', '.gif']:
                    candidate = base_no_ext + ext
                    if os.path.exists(candidate):
                        filepath = candidate
                        break
                else:
                    await event.edit("**• فشل في العثور على الملف**")
                    return

            if filepath.lower().endswith(('.mp4', '.webm')):
                duration_str = format_duration(info.get('duration', 0))
                caption = f"᥉᥆ᥙɾᥴꫀ Ϙƚһ᥆ꪀ\n• {duration_str} | ρᎥꪀƚɾꫀ᥉ꫀƚ"
                await client.send_file(event.chat_id, filepath, caption=caption,
                                       attributes=[DocumentAttributeVideo(
                                           duration=info.get('duration', 0),
                                           w=info.get('width', 0),
                                           h=info.get('height', 0),
                                           supports_streaming=True)])
            else:
                caption = f"᥉᥆ᥙɾᥴꫀ Ϙƚһ᥆ꪀ\n• Pin | ρᎥꪀƚɾꫀ᥉ꫀƚ"
                await client.send_file(event.chat_id, filepath, caption=caption)

            await event.delete()
            os.remove(filepath)

        except Exception as e:
            await event.edit(f"**• فشل تحميل بنترست:**\n{str(e)[:200]}")

    # --------------------- معرفة الموجودين في المكالمة الجماعية ---------------------
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.مين فالكول$'))
    async def who_in_call(event):
        if not event.is_group:
            await event.edit("**• الأمر يعمل في المجموعات فقط**")
            return
        await event.edit("**• جاري جلب المشاركين في المكالمة...**")
        try:
            full_chat = await client.get_entity(event.chat_id)
            if not hasattr(full_chat, 'call') or not full_chat.call:
                await event.edit("**• لا توجد مكالمة جماعية نشطة حاليًا**")
                return
            call = full_chat.call
            input_call = InputGroupCall(id=call.id, access_hash=call.access_hash)
            result = await client(GetGroupParticipants(
                call=input_call,
                ids=[],
                sources=[],
                offset='',
                limit=100
            ))
            users = []
            for participant in result.participants:
                user_id = participant.user_id if hasattr(participant, 'user_id') else participant.peer.user_id
                try:
                    user = await client.get_entity(user_id)
                    name = user.first_name or ''
                    if user.last_name:
                        name += ' ' + user.last_name
                    if user.username:
                        name += f' (@{user.username})'
                    users.append(name)
                except:
                    users.append(str(user_id))
            if not users:
                await event.edit("**• لا يوجد مشاركين حاليًا**")
            else:
                text = "**👥 الموجودون في المكالمة:**\n"
                for i, name in enumerate(users, 1):
                    text += f"{i}. {name}\n"
                await event.edit(text)
        except Exception as e:
            await event.edit(f"**• خطأ: {str(e)[:100]}**")

    # --------------------- مراقبة التعديل والحذف في الخاص ---------------------
    message_cache = {}

    @client.on(events.NewMessage(incoming=True, func=lambda e: e.is_private and not e.out))
    async def cache_private_message(event):
        if event.sender_id == (await client.get_me()).id:
            return
        chat_id = event.chat_id
        message_cache.setdefault(chat_id, {})[event.id] = event.text or "<وسائط>"

    @client.on(events.MessageEdited(incoming=True, func=lambda e: e.is_private and not e.out))
    async def notify_edit(event):
        if event.sender_id == (await client.get_me()).id:
            return
        user = await event.get_sender()
        name = user.first_name or ""
        if user.last_name: name += f" {user.last_name}"
        old_text = message_cache.get(event.chat_id, {}).get(event.id, "نص غير معروف")
        new_text = event.text or "<وسائط>"
        msg = (
            f"**قام المستخدم {name} بتعديل الرسالة**\n"
            f"**من:** {old_text}\n"
            f"**إلى:** {new_text}"
        )
        await client.send_message("me", msg)
        message_cache.setdefault(event.chat_id, {})[event.id] = new_text

    @client.on(events.MessageDeleted(incoming=True, func=lambda e: e.is_private and not e.out))
    async def notify_delete(event):
        for chat_id, msg_ids in event.deleted_ids.items():
            for msg_id in msg_ids:
                old_text = message_cache.get(chat_id, {}).get(msg_id, "نص غير معروف")
                user_name = "مستخدم"
                try:
                    chat = await client.get_entity(chat_id)
                    user_name = chat.first_name or "مستخدم"
                except:
                    pass
                msg = (
                    f"**قام المستخدم {user_name} بحذف الرسالة**\n"
                    f"**{old_text}**"
                )
                await client.send_message("me", msg)
                if chat_id in message_cache and msg_id in message_cache[chat_id]:
                    del message_cache[chat_id][msg_id]

    logger.info(f"All handlers ready for {phone}")
