import asyncio
import io
import os
import logging
import subprocess
import shutil
import requests
import re
import tempfile
from concurrent.futures import ThreadPoolExecutor
from telethon import events
from telethon.errors import FloodWaitError, ChatAdminRequiredError
from telethon.tl.functions.account import UpdateProfileRequest
from telethon.tl.functions.photos import UploadProfilePhotoRequest, DeletePhotosRequest
from telethon.tl.types import (
    InputPhoto, DocumentAttributeAudio, DocumentAttributeVideo
)
from telethon.tl.functions.users import GetFullUserRequest
from telethon.tl.functions.channels import InviteToChannelRequest
from telethon.tl.functions.messages import AddChatUserRequest
from shared import (
    active_clients, muted_users, taqleed_users, ent7al_users, ent7al_original,
    client_me, track_command, logger, TEMP_DIR
)

_DOWNLOAD_EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="dl")

# ============== إدارة المساحة ==============
MIN_FREE_SPACE_MB = 50

def get_free_space_mb():
    try:
        temp_dir = TEMP_DIR if TEMP_DIR and os.path.exists(TEMP_DIR) else '/'
        disk_usage = shutil.disk_usage(temp_dir)
        return disk_usage.free / (1024 * 1024)
    except:
        return 999

def check_disk_space(min_mb=MIN_FREE_SPACE_MB):
    free_mb = get_free_space_mb()
    if free_mb < min_mb:
        clean_temp_files()
        free_mb = get_free_space_mb()
    return free_mb >= min_mb, free_mb

def clean_temp_files():
    cleaned = 0
    if TEMP_DIR and os.path.exists(TEMP_DIR):
        for f in os.listdir(TEMP_DIR):
            fp = os.path.join(TEMP_DIR, f)
            if os.path.isfile(fp):
                try:
                    os.remove(fp)
                    cleaned += 1
                except:
                    continue
    try:
        tmp = tempfile.gettempdir()
        for f in os.listdir(tmp):
            if f.startswith(('voice_', 'img_', 'sticker_', 'audio_', 'video_', 'cobalt_', 'y2mate_')):
                fp = os.path.join(tmp, f)
                if os.path.isfile(fp):
                    try:
                        os.remove(fp)
                        cleaned += 1
                    except:
                        continue
    except:
        pass
    return cleaned

def safe_remove(filepath):
    try:
        if filepath and os.path.exists(filepath):
            os.remove(filepath)
            return True
    except:
        pass
    return False

def format_duration(seconds):
    if not seconds: return "0:00"
    mins, secs = divmod(int(seconds), 60)
    return f"{mins}:{secs:02d}"

# ────────────── البحث عن الصور (محركات متعددة) ──────────────
def _search_images_bing(query: str, limit: int = 5) -> list:
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    try:
        resp = requests.get("https://www.bing.com/images/search",
                            params={"q": query, "first": 0, "count": limit},
                            headers=headers, timeout=15)
        if resp.status_code != 200: raise ValueError("Bing لم يستجب")
        matches = re.findall(r'<img[^>]+src="([^"]+)"', resp.text)
        urls = [m for m in matches if m.startswith("http") and not m.startswith("https://www.bing.com")][:limit]
        return urls or []
    except Exception as e:
        raise ValueError(f"Bing: {e}")

def _search_images_ddg(query: str, limit: int = 5) -> list:
    try:
        from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            results = list(ddgs.images(query, max_results=limit))
        return [img["image"] for img in results if img.get("image")]
    except Exception as e:
        raise ValueError(f"DuckDuckGo: {e}")

def _search_images_pixabay(query: str, limit: int = 5) -> list:
    try:
        resp = requests.get("https://pixabay.com/api/",
                            params={"key": "25564984-2e3f8b5f6b6f6e5e5e5e5e5e5", "q": query,
                                    "image_type": "photo", "per_page": limit},
                            timeout=15)
        if resp.status_code != 200: raise ValueError("Pixabay لم يستجب")
        return [img["webformatURL"] for img in resp.json().get("hits", [])][:limit]
    except Exception as e:
        raise ValueError(f"Pixabay: {e}")

def _download_image(url: str, out_dir: str) -> str:
    try:
        has_space, _ = check_disk_space(10)
        if not has_space:
            clean_temp_files()
            has_space, _ = check_disk_space(10)
            if not has_space:
                return None
        
        resp = requests.get(url, stream=True, timeout=15)
        if resp.status_code != 200: return None
        ext = os.path.splitext(url)[1].split('?')[0] or '.jpg'
        if ext.lower() not in ('.jpg','.jpeg','.png','.webp','.gif','.bmp'): ext = '.jpg'
        filepath = os.path.join(out_dir, f"img_{int(asyncio.get_event_loop().time())}{ext}")
        with open(filepath, 'wb') as f:
            for chunk in resp.iter_content(8192): f.write(chunk)
        return filepath
    except: return None

# ────────────── خدمات تحميل الفيديو/الصوت الوسيطة ──────────────
def _cobalt_download(query: str, out_dir: str, audio_only: bool) -> tuple:
    """Cobalt API – خدمة وسيطة سريعة"""
    # فحص المساحة قبل التحميل
    has_space, _ = check_disk_space(100)
    if not has_space:
        clean_temp_files()
        has_space, _ = check_disk_space(100)
        if not has_space:
            raise ValueError("المساحة غير كافية. استخدم .تنظيف")
    
    if not query.startswith("http"):
        yt_url = _search_youtube_link(query)
        if not yt_url: raise ValueError("لم يتم العثور على فيديو")
        query = yt_url

    try:
        resp = requests.post("https://co.wuk.sh/api/json",
                             json={"url": query, "filenamePattern": "basic",
                                   "downloadMode": "audio" if audio_only else "auto"},
                             headers={"Accept": "application/json"}, timeout=45)
        if resp.status_code != 200: raise ValueError("Cobalt رفض")
        data = resp.json()
        dl_url = data.get("url")
        if not dl_url: raise ValueError("Cobalt لم يرجع رابط تحميل")
        
        file_resp = requests.get(dl_url, stream=True, timeout=120)
        if file_resp.status_code != 200: raise ValueError("فشل تحميل الملف")
        
        ext = "mp3" if audio_only else "mp4"
        filepath = os.path.join(out_dir, f"cobalt_{int(asyncio.get_event_loop().time())}.{ext}")
        
        total_size = 0
        with open(filepath, "wb") as f:
            for chunk in file_resp.iter_content(8192):
                f.write(chunk)
                total_size += len(chunk)
        
        if total_size < 1024:
            safe_remove(filepath)
            raise ValueError("الملف المحمل صغير جداً أو تالف")
        
        title = data.get("filename", "cobalt_media")
        duration = data.get("duration", 0)
        uploader = data.get("uploader", "")
        
        return {"title": title, "duration": duration, "uploader": uploader}, filepath
        
    except Exception as e:
        raise ValueError(f"Cobalt: {e}")

def _y2mate_download(query: str, out_dir: str, audio_only: bool) -> tuple:
    """Y2mate API – بديل احتياطي"""
    # فحص المساحة قبل التحميل
    has_space, _ = check_disk_space(100)
    if not has_space:
        clean_temp_files()
        has_space, _ = check_disk_space(100)
        if not has_space:
            raise ValueError("المساحة غير كافية. استخدم .تنظيف")
    
    if not query.startswith("http"):
        yt_url = _search_youtube_link(query)
        if not yt_url: raise ValueError("لم يتم العثور على فيديو")
        query = yt_url

    try:
        vid = re.search(r"(?:v=|/)([\w-]{11})", query)
        if not vid: raise ValueError("رابط غير صالح")
        vid = vid.group(1)

        headers = {"User-Agent": "Mozilla/5.0"}
        resp = requests.post("https://www.y2mate.com/mates/analyzeV2/ajax",
                             data={"k_query": f"https://www.youtube.com/watch?v={vid}", "k_page": "home", "hl": "en", "q_auto": 1},
                             headers=headers, timeout=15)
        if resp.status_code != 200: raise ValueError("Y2mate Analyze فشل")
        data = resp.json()
        video_id = data.get("vid")
        if not video_id: raise ValueError("Y2mate لم يعثر على الفيديو")

        resp2 = requests.post("https://www.y2mate.com/mates/convertV2/index",
                              data={"vid": video_id, "k": "mp3" if audio_only else "mp4"},
                              headers=headers, timeout=15)
        if resp2.status_code != 200: raise ValueError("Y2mate Convert فشل")
        data2 = resp2.json()
        dl_url = data2.get("dlink")
        if not dl_url: raise ValueError("Y2mate لم يرجع رابط تحميل")

        file_resp = requests.get(dl_url, stream=True, timeout=120)
        if file_resp.status_code != 200: raise ValueError("فشل تحميل الملف من Y2mate")
        
        ext = "mp3" if audio_only else "mp4"
        filepath = os.path.join(out_dir, f"y2mate_{int(asyncio.get_event_loop().time())}.{ext}")
        
        total_size = 0
        with open(filepath, "wb") as f:
            for chunk in file_resp.iter_content(8192):
                f.write(chunk)
                total_size += len(chunk)
        
        if total_size < 1024:
            safe_remove(filepath)
            raise ValueError("الملف المحمل صغير جداً أو تالف")
        
        title = data2.get("title", "y2mate_media")
        duration = data2.get("duration", 0)
        uploader = data2.get("uploader", "")
        
        return {"title": title, "duration": duration, "uploader": uploader}, filepath
        
    except Exception as e:
        raise ValueError(f"Y2mate: {e}")

def _search_youtube_link(query: str) -> str:
    """يبحث عن أول فيديو يوتيوب في Bing"""
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        resp = requests.get(f"https://www.bing.com/search?q={requests.utils.quote(query)}+site:youtube.com/watch",
                            headers=headers, timeout=15)
        if resp.status_code != 200: return None
        match = re.search(r"https?://(?:www\.)?youtube\.com/watch\?v=([\w-]{11})", resp.text)
        if match: return match.group(0)
    except: pass
    return None

# ────────────── دوال الانتحال ──────────────
async def get_user_info_full(client, user_id):
    try:
        user = await client.get_entity(user_id)
        name = user.first_name or ""
        if user.last_name: name += f" {user.last_name}"
        bio = ""
        try:
            full = await client(GetFullUserRequest(user_id))
            if full.full_user.about: bio = full.full_user.about
        except: pass
        return {'name': name.strip() or "غير معروف", 'first_name': user.first_name or '', 'last_name': user.last_name or '', 'bio': bio, 'id': user.id}
    except: return None

async def change_profile_photo(client, user_id, phone):
    try:
        bio = io.BytesIO()
        await client.download_profile_photo(user_id, file=bio); bio.seek(0)
        uploaded = await client.upload_file(bio, file_name="photo.jpg")
        result = await client(UploadProfilePhotoRequest(file=uploaded))
        await asyncio.sleep(2)
        if hasattr(result, 'photo') and hasattr(result.photo, 'id'): return True, result.photo.id
        return True, None
    except FloodWaitError as e:
        logger.warning(f"Flood wait {e.seconds}s")
        await asyncio.sleep(e.seconds)
        try:
            bio = io.BytesIO(); await client.download_profile_photo(user_id, file=bio); bio.seek(0)
            uploaded = await client.upload_file(bio, file_name="photo.jpg")
            result = await client(UploadProfilePhotoRequest(file=uploaded))
            await asyncio.sleep(2)
            if hasattr(result, 'photo') and hasattr(result.photo, 'id'): return True, result.photo.id
            return True, None
        except: return False, None
    except Exception as e:
        logger.error(f"Photo change failed: {e}")
        return False, None

# ────────────── المعالجات ──────────────
async def setup_handlers(client, phone):
    if phone not in muted_users: muted_users[phone] = {}
    if phone not in taqleed_users: taqleed_users[phone] = {}
    if phone not in ent7al_users: ent7al_users[phone] = False
    if phone not in ent7al_original: ent7al_original[phone] = {}

    # ─ـ أمر .المساحة ─ـ
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.المساحة$'))
    async def space_check(event):
        await event.edit("**• 📊 جاري فحص المساحة...**")
        free_mb = get_free_space_mb()
        cleaned = clean_temp_files()
        free_after = get_free_space_mb()
        
        msg = f"**📊 المساحة المتاحة:** {free_after:.1f} MB\n"
        if cleaned > 0:
            msg += f"**🧹 تم تنظيف {cleaned} ملف**\n"
        if free_after < MIN_FREE_SPACE_MB:
            msg += "⚠️ **المساحة منخفضة!**"
        else:
            msg += "✅ **المساحة كافية**"
        await event.edit(msg)

    # ─ـ أمر .تنظيف ─ـ
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.تنظيف$'))
    async def force_clean(event):
        await event.edit("**• 🧹 جاري التنظيف...**")
        c1 = clean_temp_files()
        await asyncio.sleep(1)
        c2 = clean_temp_files()
        free_mb = get_free_space_mb()
        await event.edit(f"**✅ تم التنظيف ({c1 + c2} ملف)**\n**المساحة المتاحة:** {free_mb:.1f} MB")

    # ─ـ التقليد ─ـ
    @client.on(events.NewMessage(incoming=True))
    async def auto_taqleed(event):
        if event.sender_id in taqleed_users.get(phone, {}) and event.text and not event.text.startswith('.'):
            await asyncio.sleep(0.3)
            try: await event.reply(event.text)
            except: pass

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.تقليد$'))
    async def taq(event):
        target = (await event.get_reply_message()).sender_id if event.is_reply else event.chat_id if event.is_private else None
        if target: taqleed_users[phone][target] = True; await event.edit("**• يتم التقليد**")

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.غ تقليد$'))
    async def notaq(event):
        target = (await event.get_reply_message()).sender_id if event.is_reply else event.chat_id if event.is_private else None
        if target and target in taqleed_users.get(phone, {}): del taqleed_users[phone][target]
        await event.edit("**• تم فك التقليد**")

    # ─ـ الانتحال ─ـ
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.انتحال$'))
    async def ent7al(event):
        track_command(phone, ".انتحال")
        await event.edit("**• جاري الانتحال...**")
        target_user = None
        if event.is_reply:
            try: target_user = await client.get_entity((await event.get_reply_message()).sender_id)
            except: pass
        elif event.is_private:
            try: target_user = await client.get_entity(event.chat_id)
            except: pass
        if not target_user: await event.edit("**• فشل الانتحال**"); return
        target_info = await get_user_info_full(client, target_user.id)
        if not target_info: await event.edit("**• فشل الانتحال**"); return
        me = await client.get_me(); client_me[phone] = me
        original = {'first_name': me.first_name or '', 'last_name': me.last_name if me.last_name is not None else '', 'photo_bytes': None, 'added_photo_id': None, 'about': ''}
        try:
            fu = await client(GetFullUserRequest('me'))
            if fu.full_user.about: original['about'] = fu.full_user.about
        except: pass
        name_ok = False
        try:
            await client(UpdateProfileRequest(first_name=target_info['first_name'], last_name=target_info['last_name']))
            await asyncio.sleep(1); name_ok = True
        except FloodWaitError as e:
            await asyncio.sleep(e.seconds)
            try: await client(UpdateProfileRequest(first_name=target_info['first_name'], last_name=target_info['last_name'])); name_ok = True
            except: pass
        except: pass
        bio_ok = False
        try:
            await client(UpdateProfileRequest(about=target_info['bio'][:70] if target_info['bio'] else ''))
            await asyncio.sleep(0.5); bio_ok = True
        except FloodWaitError as e:
            await asyncio.sleep(e.seconds)
            try: await client(UpdateProfileRequest(about=target_info['bio'][:70] if target_info['bio'] else '')); bio_ok = True
            except: pass
        except: pass
        photo_ok, added_id = await change_profile_photo(client, target_user.id, phone)
        if photo_ok and added_id: original['added_photo_id'] = added_id
        ent7al_original[phone] = original; ent7al_users[phone] = True
        if name_ok and bio_ok and photo_ok: await event.edit("**• تم الانتحال**")
        elif not name_ok and not bio_ok and not photo_ok: await event.edit("**• فشل الانتحال**")
        else: await event.edit("**• تم الانتحال جزئياً**")

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.الغاء انتحال$'))
    async def unent7al(event):
        track_command(phone, ".الغاء انتحال")
        await event.edit("**• جاري إلغاء الانتحال...**")
        if not ent7al_users.get(phone) or not ent7al_original.get(phone): await event.edit("**• لا يوجد انتحال**"); return
        original = ent7al_original[phone]
        first, last = original.get('first_name', ''), original.get('last_name', '')
        restored_name = False
        for attempt in range(3):
            try:
                await client(UpdateProfileRequest(first_name=first, last_name=last))
                await asyncio.sleep(1.5); me_now = await client.get_me()
                if me_now.first_name == first and (me_now.last_name or '') == last: restored_name = True; break
            except FloodWaitError as e: await asyncio.sleep(e.seconds)
            except Exception as e: logger.error(f"Restore name attempt {attempt+1}: {e}"); await asyncio.sleep(1)
        if not restored_name: logger.error(f"Could not fully restore name for {phone}")
        if original.get('added_photo_id'):
            try: await client(DeletePhotosRequest(id=[InputPhoto(id=original['added_photo_id'], access_hash=0, file_reference=b'')])); await asyncio.sleep(2)
            except FloodWaitError as e: await asyncio.sleep(e.seconds)
            except Exception as e: logger.error(f"Failed to delete added photo: {e}")
        else:
            try:
                current_photos = await client.get_profile_photos('me', limit=1)
                if current_photos: await client(DeletePhotosRequest(id=[InputPhoto(id=current_photos[0].id, access_hash=current_photos[0].access_hash, file_reference=current_photos[0].file_reference)]))
                await asyncio.sleep(2)
            except Exception as e: logger.error(f"Fallback photo deletion failed: {e}")
        try: await client(UpdateProfileRequest(about=original.get('about', '')))
        except FloodWaitError as e: await asyncio.sleep(e.seconds)
        except Exception as e: logger.error(f"Restore bio failed: {e}")
        ent7al_users[phone] = False; ent7al_original[phone] = {}
        await event.edit("**• تم إلغاء الانتحال**")

    # ─ـ إضافة أعضاء ─ـ
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.اضافة (\d+) (@?\w+)$'))
    async def add_members_from_group(event):
        if not event.is_group: await event.edit("**• الأمر يعمل في المجموعات فقط**"); return
        count, target_username = int(event.pattern_match.group(1)), event.pattern_match.group(2).strip()
        await event.edit(f"**• جاري سحب {count} عضو من {target_username} وإضافتهم هنا...**")
        try: source_group = await client.get_entity(target_username)
        except Exception: await event.edit(f"**• لم يتم العثور على الجروب {target_username}**"); return
        try: await client.join_channel(source_group); await asyncio.sleep(3)
        except: pass
        added = failed = 0
        try:
            async for user in client.iter_participants(source_group, limit=count):
                if user.bot or user.deleted: continue
                try:
                    if hasattr(event.chat, 'megagroup') and event.chat.megagroup: await client(InviteToChannelRequest(channel=event.chat_id, users=[user.id]))
                    else: await client(AddChatUserRequest(chat_id=event.chat_id, user_id=user.id, fwd_limit=10))
                    added += 1; await asyncio.sleep(1.5)
                except FloodWaitError as e:
                    await asyncio.sleep(e.seconds)
                    try:
                        if hasattr(event.chat, 'megagroup') and event.chat.megagroup: await client(InviteToChannelRequest(channel=event.chat_id, users=[user.id]))
                        else: await client(AddChatUserRequest(chat_id=event.chat_id, user_id=user.id, fwd_limit=10))
                        added += 1
                    except: failed += 1
                except ChatAdminRequiredError: await event.edit("**• الصلاحيات غير كافية - يجب أن تكون مشرفًا**"); return
                except Exception as e:
                    failed += 1
                    if "PEER_FLOOD" in str(e) or "USER_PRIVACY_RESTRICTED" in str(e): break
            msg = f"**• تمت إضافة {added} عضو بنجاح**"
            if failed: msg += f"\n• فشل في إضافة {failed} عضو"
            await event.edit(msg)
        except ChatAdminRequiredError: await event.edit("**• لا تملك صلاحيات لسحب الأعضاء**")
        except Exception as e: await event.edit(f"**• فشل: {str(e)[:50]}**")

    # ─ـ نسخ الصوت ─ـ
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.نسخ$'))
    async def transcribe_voice(event):
        if not event.is_reply: await event.edit("**• يرجى الرد على رسالة صوتية أو فيديو**"); return
        reply = await event.get_reply_message()
        if not reply.voice and not reply.audio and not reply.video: await event.edit("**• الرد على رسالة صوتية أو فيديو فقط**"); return
        
        has_space, free_mb = check_disk_space(30)
        if not has_space:
            await event.edit(f"**• ❌ المساحة غير كافية ({free_mb:.1f}MB)**\n**• استخدم .تنظيف**")
            return
        
        await event.edit("**• جاري تحويل المقطع إلى نص...**")
        try: import speech_recognition as sr
        except ImportError: await event.edit("**• مكتبة SpeechRecognition غير مثبتة**"); return
        
        voice_path = os.path.join(TEMP_DIR, f"voice_{phone}_{reply.id}.ogg")
        await client.download_media(reply, voice_path)
        wav_path = voice_path.replace(".ogg", ".wav")
        try:
            subprocess.run(["ffmpeg", "-i", voice_path, "-ac","1","-ar","16000", wav_path], check=True, capture_output=True, timeout=30)
            recognizer = sr.Recognizer()
            with sr.AudioFile(wav_path) as source: audio_data = recognizer.record(source)
            text = recognizer.recognize_google(audio_data, language="ar-AR")
            await event.edit(f"**النص:**\n{text}")
        except subprocess.CalledProcessError as e: await event.edit(f"**• فشل تحويل الصوت: {e.stderr.decode()[:100]}**")
        except sr.UnknownValueError: await event.edit("**• لم يتم التعرف على أي كلام**")
        except sr.RequestError as e: await event.edit(f"**• خطأ في خدمة التعرف: {e}**")
        except Exception as e: await event.edit(f"**• فشل: {str(e)[:100]}**")
        finally:
            safe_remove(voice_path)
            safe_remove(wav_path)

    # ─ـ استيكر / صورة ─ـ
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.استيك$'))
    async def photo_to_sticker(event):
        if not event.is_reply: await event.edit("**• يرجى الرد على صورة**"); return
        reply = await event.get_reply_message()
        if not reply.photo: await event.edit("**• الرد على صورة فقط**"); return
        
        has_space, free_mb = check_disk_space(10)
        if not has_space:
            await event.edit(f"**• ❌ المساحة غير كافية ({free_mb:.1f}MB)**")
            return
        
        await event.edit("**• جاري تحويل الصورة إلى استيكر...**")
        try: from PIL import Image
        except ImportError: await event.edit("**• مكتبة Pillow غير مثبتة**"); return
        
        img_path = os.path.join(TEMP_DIR, f"img_{phone}_{reply.id}.jpg")
        stick_path = os.path.join(TEMP_DIR, f"sticker_{phone}_{reply.id}.webp")
        await client.download_media(reply, img_path)
        try:
            im = Image.open(img_path).convert("RGBA")
            im.thumbnail((512,512), Image.LANCZOS)
            im.save(stick_path, "WEBP")
            await client.send_file(event.chat_id, stick_path)
            await event.delete()
        except Exception as e: await event.edit(f"**• فشل: {str(e)[:100]}**")
        finally:
            safe_remove(img_path)
            safe_remove(stick_path)

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.بيك$'))
    async def sticker_to_photo(event):
        if not event.is_reply: await event.edit("**• يرجى الرد على استيكر**"); return
        reply = await event.get_reply_message()
        if not reply.sticker: await event.edit("**• الرد على استيكر فقط**"); return
        
        has_space, free_mb = check_disk_space(10)
        if not has_space:
            await event.edit(f"**• ❌ المساحة غير كافية ({free_mb:.1f}MB)**")
            return
        
        await event.edit("**• جاري تحويل الاستيكر إلى صورة...**")
        try: from PIL import Image
        except ImportError: await event.edit("**• مكتبة Pillow غير مثبتة**"); return
        
        stick_path = os.path.join(TEMP_DIR, f"sticker_{phone}_{reply.id}.webp")
        img_path = os.path.join(TEMP_DIR, f"img_{phone}_{reply.id}.png")
        await client.download_media(reply, stick_path)
        try:
            im = Image.open(stick_path)
            im.save(img_path, "PNG")
            await client.send_file(event.chat_id, img_path)
            await event.delete()
        except Exception as e: await event.edit(f"**• فشل: {str(e)[:100]}**")
        finally:
            safe_remove(stick_path)
            safe_remove(img_path)

    # ─ـ تحميل الصور (بن) ─ـ
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.بن (.+)'))
    async def image_search_download(event):
        query = event.pattern_match.group(1).strip()
        
        has_space, free_mb = check_disk_space(20)
        if not has_space:
            await event.edit(f"**• ❌ المساحة غير كافية ({free_mb:.1f}MB)**\n**• استخدم .تنظيف**")
            return
        
        if query.startswith("http"):
            await event.edit("**• 📷 جاري تحميل الصورة...**")
            loop = asyncio.get_event_loop()
            try:
                filepath = await loop.run_in_executor(_DOWNLOAD_EXECUTOR, _download_image, query, TEMP_DIR)
                if filepath:
                    await client.send_file(event.chat_id, filepath)
                    await event.delete()
                    safe_remove(filepath)
                else:
                    await event.edit("**• فشل تحميل الصورة**")
            except Exception as e:
                await event.edit(f"**• فشل: {str(e)[:100]}**")
            return

        await event.edit("**• 🔍 جاري البحث عن صور...**")
        loop = asyncio.get_event_loop()
        urls = []
        for finder in (_search_images_bing, _search_images_ddg, _search_images_pixabay):
            try:
                urls = await loop.run_in_executor(_DOWNLOAD_EXECUTOR, finder, query, 5)
                if urls: break
            except: continue
        if not urls:
            await event.edit("**• لم يتم العثور على صور**")
            return
        downloaded = []
        for url in urls[:3]:
            path = await loop.run_in_executor(_DOWNLOAD_EXECUTOR, _download_image, url, TEMP_DIR)
            if path: downloaded.append(path)
        if not downloaded:
            await event.edit("**• فشل تحميل الصور**")
            return
        for path in downloaded:
            await client.send_file(event.chat_id, path)
            safe_remove(path)
        await event.delete()

    # ─ـ تحميل صوت (يوت) ─ـ
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.يوت (.+)'))
    async def youtube_audio(event):
        query = event.pattern_match.group(1).strip()
        
        has_space, free_mb = check_disk_space(80)
        if not has_space:
            await event.edit(f"**• ❌ المساحة غير كافية ({free_mb:.1f}MB)**\n**• استخدم .تنظيف**")
            return
        
        await event.edit("**• 🎵 جاري التحميل عبر الخدمات الوسيطة...**")
        loop = asyncio.get_event_loop()
        info = filepath = None
        
        try:
            info, filepath = await loop.run_in_executor(_DOWNLOAD_EXECUTOR, _cobalt_download, query, TEMP_DIR, True)
        except Exception:
            try:
                info, filepath = await loop.run_in_executor(_DOWNLOAD_EXECUTOR, _y2mate_download, query, TEMP_DIR, True)
            except Exception as e:
                await event.edit(f"**• فشل التحميل:**\n{str(e)[:200]}"); return
        
        try:
            # طريقة الكود القديم في التسمية والكابشن
            title = info.get('title', 'بدون عنوان')
            if len(title) > 55: title = title[:52] + '...'
            dur = format_duration(info.get('duration', 0))
            caption = f"{title}\n• {dur} | ᥲᥙძᎥ᥆"
            
            await client.send_file(event.chat_id, filepath, caption=caption,
                                   attributes=[DocumentAttributeAudio(duration=info.get('duration',0), title=title, performer=info.get('uploader',''))])
            await event.delete()
        except Exception as e:
            await event.edit(f"**• فشل الإرسال:**\n{str(e)[:200]}")
        finally:
            safe_remove(filepath)
            clean_temp_files()

    # ─ـ تحميل فيديو (فيد) ─ـ
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.فيد (.+)'))
    async def video_download(event):
        query = event.pattern_match.group(1).strip()
        
        has_space, free_mb = check_disk_space(100)
        if not has_space:
            await event.edit(f"**• ❌ المساحة غير كافية ({free_mb:.1f}MB)**\n**• استخدم .تنظيف**")
            return
        
        await event.edit("**• 🎬 جاري التحميل عبر الخدمات الوسيطة...**")
        loop = asyncio.get_event_loop()
        info = filepath = None
        
        try:
            info, filepath = await loop.run_in_executor(_DOWNLOAD_EXECUTOR, _cobalt_download, query, TEMP_DIR, False)
        except Exception:
            try:
                info, filepath = await loop.run_in_executor(_DOWNLOAD_EXECUTOR, _y2mate_download, query, TEMP_DIR, False)
            except Exception as e:
                await event.edit(f"**• فشل تحميل الفيديو:**\n{str(e)[:200]}"); return
        
        try:
            # طريقة الكود القديم في التسمية والكابشن
            title = info.get('title', 'بدون عنوان')
            if len(title) > 55: title = title[:52] + '...'
            dur = format_duration(info.get('duration', 0))
            caption = f"{title}\n• {dur} | ᥎Ꭵძꫀ᥆"
            
            await client.send_file(event.chat_id, filepath, caption=caption,
                                   attributes=[DocumentAttributeVideo(duration=info.get('duration',0), w=0, h=0, supports_streaming=True)])
            await event.delete()
        except Exception as e:
            await event.edit(f"**• فشل الإرسال:**\n{str(e)[:200]}")
        finally:
            safe_remove(filepath)
            clean_temp_files()

    # ─ـ مراقبة الخاص ─ـ
    message_cache = {}
    @client.on(events.NewMessage(incoming=True, func=lambda e: e.is_private and not e.out))
    async def cache_private_message(event):
        if event.sender_id == (await client.get_me()).id: return
        message_cache.setdefault(event.chat_id, {})[event.id] = event.text or "<وسائط>"

    @client.on(events.MessageEdited(incoming=True, func=lambda e: e.is_private and not e.out))
    async def notify_edit(event):
        if event.sender_id == (await client.get_me()).id: return
        user = await event.get_sender()
        name = user.first_name or ""
        if user.last_name: name += f" {user.last_name}"
        old_text = message_cache.get(event.chat_id, {}).get(event.id, "نص غير معروف")
        new_text = event.text or "<وسائط>"
        await client.send_message("me", f"**قام المستخدم {name} بتعديل الرسالة**\n**من:** {old_text}\n**إلى:** {new_text}")
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
                except: pass
                await client.send_message("me", f"**قام المستخدم {user_name} بحذف الرسالة**\n**{old_text}**")
                if chat_id in message_cache and msg_id in message_cache[chat_id]:
                    del message_cache[chat_id][msg_id]

    # ─ـ تنظيف دوري ─ـ
    async def auto_cleanup():
        while True:
            await asyncio.sleep(1800)  # كل 30 دقيقة
            free_mb = get_free_space_mb()
            if free_mb < MIN_FREE_SPACE_MB * 2:
                count = clean_temp_files()
                if count > 0:
                    logger.info(f"🧹 تنظيف تلقائي: {count} ملف")

    asyncio.create_task(auto_cleanup())

    logger.info(f"All handlers ready for {phone} - Space: {get_free_space_mb():.1f}MB")
