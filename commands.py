import asyncio
import io
import os
import logging
import subprocess
import shutil
import requests
import re
import time
import hashlib
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

# ============== استيراد المكتبات ==============
try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    logger.warning("⚠️ Pillow غير مثبتة")

try:
    import speech_recognition as sr
    SR_AVAILABLE = True
except ImportError:
    SR_AVAILABLE = False
    logger.warning("⚠️ SpeechRecognition غير مثبتة")

try:
    import yt_dlp
    YTDLP_AVAILABLE = True
except ImportError:
    YTDLP_AVAILABLE = False
    logger.warning("⚠️ yt-dlp غير مثبتة")

# ThreadPoolExecutor
_DOWNLOAD_EXECUTOR = ThreadPoolExecutor(max_workers=3, thread_name_prefix="dl")

# متغيرات مراقبة الخاص
message_cache = {}

# الحد الأدنى للمساحة
MIN_FREE_SPACE_MB = 50

# ============== دوال إدارة المساحة ==============
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
    freed = 0
    if TEMP_DIR and os.path.exists(TEMP_DIR):
        for f in os.listdir(TEMP_DIR):
            fp = os.path.join(TEMP_DIR, f)
            if os.path.isfile(fp):
                try:
                    sz = os.path.getsize(fp)
                    os.remove(fp)
                    cleaned += 1
                    freed += sz
                except:
                    continue
    try:
        tmp = tempfile.gettempdir()
        for f in os.listdir(tmp):
            if f.startswith(('voice_', 'img_', 'sticker_', 'audio_', 'video_')):
                fp = os.path.join(tmp, f)
                if os.path.isfile(fp):
                    try:
                        sz = os.path.getsize(fp)
                        os.remove(fp)
                        cleaned += 1
                        freed += sz
                    except:
                        continue
    except:
        pass
    if cleaned > 0:
        logger.info(f"🧹 تنظيف: {cleaned} ملف, {freed/(1024*1024):.1f}MB")
    return cleaned, freed

def safe_remove(filepath):
    try:
        if filepath and os.path.exists(filepath):
            os.remove(filepath)
            return True
    except:
        pass
    return False

# ============== دوال التنسيق ==============
def format_duration(seconds):
    if not seconds: return "0:00"
    mins, secs = divmod(int(seconds), 60)
    return f"{mins}:{secs:02d}"

def format_size(bytes_size):
    if bytes_size == 0:
        return "0 B"
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes_size < 1024.0:
            return f"{bytes_size:.1f} {unit}"
        bytes_size /= 1024.0
    return f"{bytes_size:.1f} TB"

def clean_filename(name):
    name = re.sub(r'[<>:"/\\|?*]', '', name)
    name = re.sub(r'\s+', ' ', name).strip()
    return name[:100]

# ============== دوال التحميل من يوتيوب - المعدلة ==============
def download_youtube_media(query: str, out_dir: str, audio_only: bool = False):
    """تحميل من يوتيوب مع استخراج المعلومات الصحيحة"""
    if not YTDLP_AVAILABLE:
        raise ValueError("مكتبة yt-dlp غير مثبتة")
    
    has_space, free_mb = check_disk_space(100)
    if not has_space:
        raise ValueError(f"المساحة غير كافية. المتاح: {free_mb:.1f}MB")
    
    if not query.startswith("http"):
        query = f"ytsearch:{query}"
    
    timestamp = int(time.time())
    
    if audio_only:
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': os.path.join(out_dir, f'audio_{timestamp}.%(ext)s'),
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'quiet': True,
            'no_warnings': True,
            'max_filesize': 50 * 1024 * 1024,
            'extract_flat': False,  # مهم: استخراج المعلومات الكاملة
        }
    else:
        ydl_opts = {
            'format': 'best[height<=720]/best',
            'outtmpl': os.path.join(out_dir, f'video_{timestamp}.%(ext)s'),
            'quiet': True,
            'no_warnings': True,
            'max_filesize': 100 * 1024 * 1024,
            'merge_output_format': 'mp4',
            'extract_flat': False,  # مهم: استخراج المعلومات الكاملة
        }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # الخطوة 1: استخراج المعلومات أولاً بدون تحميل
            info_dict = ydl.extract_info(query, download=False)
            
            # التعامل مع قوائم التشغيل والبحث
            if 'entries' in info_dict:
                info_dict = info_dict['entries'][0]
            
            # استخراج المعلومات الصحيحة
            title = info_dict.get('title', 'بدون عنوان')
            uploader = info_dict.get('uploader', 'غير معروف')
            duration = info_dict.get('duration', 0)
            
            logger.info(f"تم استخراج المعلومات: {title} - {uploader} - {duration}s")
            
            # الخطوة 2: التحميل الفعلي
            info_dict = ydl.extract_info(query, download=True)
            
            # البحث عن الملف المحمل
            prefix = 'audio_' if audio_only else 'video_'
            files = [f for f in os.listdir(out_dir) if f.startswith(f'{prefix}{timestamp}')]
            
            if not files:
                raise ValueError("لم يتم العثور على الملف المحمل")
            
            filepath = os.path.join(out_dir, files[0])
            
            if not os.path.exists(filepath) or os.path.getsize(filepath) < 1024:
                raise ValueError("الملف تالف")
            
            # التأكد من القيم
            if duration == 0 and 'duration' in info_dict:
                duration = info_dict.get('duration', 0)
            
            return {
                'title': title,
                'uploader': uploader,
                'duration': duration,
                'duration_str': format_duration(duration),
                'size': os.path.getsize(filepath),
                'size_str': format_size(os.path.getsize(filepath)),
            }, filepath
            
    except Exception as e:
        prefix = 'audio_' if audio_only else 'video_'
        for f in os.listdir(out_dir):
            if f.startswith(f'{prefix}{timestamp}'):
                safe_remove(os.path.join(out_dir, f))
        raise ValueError(f"فشل التحميل: {str(e)[:200]}")

# ============== دوال تحميل الصور ==============
def download_image_direct(url: str, out_dir: str):
    has_space, free_mb = check_disk_space(10)
    if not has_space:
        raise ValueError(f"المساحة غير كافية. المتاح: {free_mb:.1f}MB")
    
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        resp = requests.get(url, headers=headers, stream=True, timeout=30)
        
        if resp.status_code != 200:
            raise ValueError(f"خطأ في التحميل: {resp.status_code}")
        
        content_type = resp.headers.get('content-type', '')
        ext = '.jpg'
        if 'png' in content_type:
            ext = '.png'
        elif 'webp' in content_type:
            ext = '.webp'
        elif 'gif' in content_type:
            ext = '.gif'
        
        timestamp = int(time.time() * 1000)
        filepath = os.path.join(out_dir, f"img_{timestamp}{ext}")
        
        total_size = 0
        with open(filepath, 'wb') as f:
            for chunk in resp.iter_content(8192):
                if chunk:
                    f.write(chunk)
                    total_size += len(chunk)
                    if total_size > 10 * 1024 * 1024:
                        safe_remove(filepath)
                        raise ValueError("الصورة كبيرة جداً")
        
        if total_size < 1024:
            safe_remove(filepath)
            raise ValueError("الملف تالف")
        
        return filepath
        
    except Exception as e:
        raise ValueError(f"فشل التحميل: {str(e)[:150]}")

def search_images(query: str, limit: int = 5):
    images = []
    try:
        from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            results = list(ddgs.images(query, max_results=limit))
        images = [img["image"] for img in results if img.get("image")]
    except:
        pass
    
    if not images:
        try:
            headers = {'User-Agent': 'Mozilla/5.0'}
            url = f"https://www.google.com/search?q={requests.utils.quote(query)}&tbm=isch&hl=ar"
            resp = requests.get(url, headers=headers, timeout=15)
            if resp.status_code == 200:
                urls = re.findall(r'"(https?://[^"]+\.(?:jpg|jpeg|png|webp))"', resp.text, re.I)
                images = urls[:limit]
        except:
            pass
    
    if not images:
        try:
            resp = requests.get(
                "https://pixabay.com/api/",
                params={
                    "key": "25564984-2e3f8b5f6b6f6e5e5e5e5e5e",
                    "q": query,
                    "image_type": "photo",
                    "per_page": limit
                },
                timeout=15
            )
            if resp.status_code == 200:
                images = [img["webformatURL"] for img in resp.json().get("hits", [])][:limit]
        except:
            pass
    
    return images

# ============== دوال الانتحال ==============
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
    except Exception as e:
        logger.error(f"فشل جلب معلومات المستخدم: {e}")
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
        logger.warning(f"Flood wait {e.seconds}s")
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
        logger.error(f"فشل تغيير الصورة: {e}")
        return False, None

# ============== إعداد المعالجات ==============
async def setup_handlers(client, phone):
    
    # تهيئة المتغيرات
    if phone not in muted_users:
        muted_users[phone] = {}
    if phone not in taqleed_users:
        taqleed_users[phone] = {}
    if phone not in ent7al_users:
        ent7al_users[phone] = False
    if phone not in ent7al_original:
        ent7al_original[phone] = {}

    # ============== أمر .المساحة ==============
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.المساحة$'))
    async def space_check(event):
        await event.edit("**• 📊 جاري فحص المساحة...**")
        
        free_mb = get_free_space_mb()
        cleaned, freed = clean_temp_files()
        free_after = get_free_space_mb()
        
        msg = "**📊 حالة التخزين:**\n"
        msg += f"**• المساحة المتاحة:** {free_after:.1f} MB\n"
        
        if cleaned > 0:
            msg += f"**• 🧹 تم تنظيف {cleaned} ملف**\n"
            msg += f"**• 💾 تم تحرير: {format_size(freed)}**\n"
        
        if free_after < MIN_FREE_SPACE_MB:
            msg += "\n⚠️ **تحذير: المساحة منخفضة!**"
        else:
            msg += "\n✅ **المساحة كافية**"
        
        await event.edit(msg)

    # ============== أمر .تنظيف ==============
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.تنظيف$'))
    async def force_clean(event):
        await event.edit("**• 🧹 جاري التنظيف...**")
        
        c1, s1 = clean_temp_files()
        await asyncio.sleep(1)
        c2, s2 = clean_temp_files()
        
        total_cleaned = c1 + c2
        total_freed = s1 + s2
        free_mb = get_free_space_mb()
        
        msg = "**✅ تم التنظيف:**\n"
        msg += f"**• الملفات المحذوفة:** {total_cleaned}\n"
        msg += f"**• المساحة المحررة:** {format_size(total_freed)}\n"
        msg += f"**• المساحة المتاحة الآن:** {free_mb:.1f} MB"
        
        await event.edit(msg)

    # ============== أمر .يوت (تحميل صوت) - المعدل ==============
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.يوت (.+)'))
    async def youtube_audio(event):
        if not YTDLP_AVAILABLE:
            await event.edit("**• ❌ مكتبة yt-dlp غير مثبتة**\n**• استخدم: `pip install yt-dlp`**")
            return
        
        query = event.pattern_match.group(1).strip()
        
        has_space, free_mb = check_disk_space(80)
        if not has_space:
            await event.edit(f"**• ❌ المساحة غير كافية ({free_mb:.1f}MB)**\n**• استخدم .تنظيف**")
            return
        
        await event.edit("**• 🎵 جاري تحميل الصوت...**")
        
        filepath = None
        
        try:
            info, filepath = await asyncio.get_event_loop().run_in_executor(
                _DOWNLOAD_EXECUTOR, download_youtube_media, query, TEMP_DIR, True
            )
            
            # استخدام الاسم الأصلي والمدة الصحيحة
            title = info['title']
            if len(title) > 55:
                title = title[:52] + '...'
            dur = info['duration_str']  # المدة الصحيحة
            caption = f"{title}\n• {dur} | ᥲᥙძᎥ᥆"
            
            await client.send_file(
                event.chat_id,
                filepath,
                caption=caption,
                attributes=[
                    DocumentAttributeAudio(
                        duration=info['duration'],  # المدة الصحيحة بالثواني
                        title=info['title'],  # الاسم الأصلي
                        performer=info['uploader']  # اسم القناة
                    )
                ],
                supports_streaming=True
            )
            
            await event.delete()
            
        except Exception as e:
            await event.edit(f"**• ❌ {str(e)[:200]}**")
        finally:
            safe_remove(filepath)
            clean_temp_files()

    # ============== أمر .فيد (تحميل فيديو) - المعدل ==============
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.فيد (.+)'))
    async def video_download(event):
        if not YTDLP_AVAILABLE:
            await event.edit("**• ❌ مكتبة yt-dlp غير مثبتة**\n**• استخدم: `pip install yt-dlp`**")
            return
        
        query = event.pattern_match.group(1).strip()
        
        has_space, free_mb = check_disk_space(150)
        if not has_space:
            await event.edit(f"**• ❌ المساحة غير كافية ({free_mb:.1f}MB)**\n**• استخدم .تنظيف**")
            return
        
        await event.edit("**• 🎬 جاري تحميل الفيديو...**")
        
        filepath = None
        
        try:
            info, filepath = await asyncio.get_event_loop().run_in_executor(
                _DOWNLOAD_EXECUTOR, download_youtube_media, query, TEMP_DIR, False
            )
            
            # استخدام الاسم الأصلي والمدة الصحيحة
            title = info['title']
            if len(title) > 55:
                title = title[:52] + '...'
            dur = info['duration_str']  # المدة الصحيحة
            caption = f"{title}\n• {dur} | ᥎Ꭵძꫀ᥆"
            
            await client.send_file(
                event.chat_id,
                filepath,
                caption=caption,
                attributes=[
                    DocumentAttributeVideo(
                        duration=info['duration'],  # المدة الصحيحة بالثواني
                        w=0,
                        h=0,
                        supports_streaming=True
                    )
                ],
                supports_streaming=True
            )
            
            await event.delete()
            
        except Exception as e:
            await event.edit(f"**• ❌ {str(e)[:200]}**")
        finally:
            safe_remove(filepath)
            clean_temp_files()

    # ============== أمر .نسخ (تحويل صوت لنص) ==============
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.نسخ$'))
    async def transcribe_voice(event):
        if not event.is_reply:
            await event.edit("**• ❌ يرجى الرد على رسالة صوتية**")
            return
        
        reply = await event.get_reply_message()
        if not (reply.voice or reply.audio):
            await event.edit("**• ❌ الرد على رسالة صوتية فقط**")
            return
        
        has_space, free_mb = check_disk_space(30)
        if not has_space:
            await event.edit(f"**• ❌ المساحة غير كافية ({free_mb:.1f}MB)**\n**• استخدم .تنظيف**")
            return
        
        if not SR_AVAILABLE:
            await event.edit("**• ❌ مكتبة SpeechRecognition غير مثبتة**")
            return
        
        await event.edit("**• 🎤 جاري تحويل الصوت إلى نص...**")
        
        voice_path = None
        wav_path = None
        
        try:
            voice_path = os.path.join(TEMP_DIR, f"voice_{phone}_{int(time.time())}.ogg")
            await client.download_media(reply, voice_path)
            
            if not os.path.exists(voice_path) or os.path.getsize(voice_path) < 100:
                raise ValueError("فشل تحميل الملف الصوتي")
            
            wav_path = voice_path.replace('.ogg', '.wav')
            
            result = subprocess.run(
                ['ffmpeg', '-i', voice_path, '-ac', '1', '-ar', '16000', 
                 '-sample_fmt', 's16', wav_path],
                capture_output=True,
                timeout=30
            )
            
            if result.returncode != 0 or not os.path.exists(wav_path):
                raise ValueError("فشل تحويل الصوت")
            
            recognizer = sr.Recognizer()
            with sr.AudioFile(wav_path) as source:
                audio_data = recognizer.record(source)
            
            text = None
            for lang in ['ar-AR', 'en-US']:
                try:
                    text = recognizer.recognize_google(audio_data, language=lang)
                    break
                except:
                    continue
            
            if text:
                await event.edit(f"**📝 النص:**\n{text}")
            else:
                await event.edit("**• ❌ لم يتم التعرف على أي نص**")
                
        except subprocess.CalledProcessError as e:
            error_text = e.stderr.decode()[:100] if e.stderr else str(e)
            await event.edit(f"**• ❌ فشل التحويل: {error_text}**")
        except Exception as e:
            await event.edit(f"**• ❌ {str(e)[:150]}**")
        finally:
            safe_remove(voice_path)
            safe_remove(wav_path)
            clean_temp_files()

    # ============== أمر .استيك (صورة إلى استيكر) ==============
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.استيك$'))
    async def photo_to_sticker(event):
        if not event.is_reply:
            await event.edit("**• ❌ يرجى الرد على صورة**")
            return
        
        reply = await event.get_reply_message()
        if not reply.photo:
            await event.edit("**• ❌ الرد على صورة فقط**")
            return
        
        if not PIL_AVAILABLE:
            await event.edit("**• ❌ مكتبة Pillow غير مثبتة**")
            return
        
        has_space, free_mb = check_disk_space(10)
        if not has_space:
            await event.edit(f"**• ❌ المساحة غير كافية ({free_mb:.1f}MB)**")
            return
        
        await event.edit("**• 🔄 جاري التحويل...**")
        
        img_path = None
        stick_path = None
        
        try:
            img_path = os.path.join(TEMP_DIR, f"img_{phone}_{int(time.time())}.jpg")
            await client.download_media(reply, img_path)
            
            if not os.path.exists(img_path):
                raise ValueError("فشل تحميل الصورة")
            
            stick_path = img_path.replace('.jpg', '.webp')
            
            im = Image.open(img_path).convert("RGBA")
            im.thumbnail((512, 512), Image.LANCZOS)
            im.save(stick_path, "WEBP", quality=80)
            
            if os.path.exists(stick_path) and os.path.getsize(stick_path) > 0:
                await client.send_file(event.chat_id, stick_path, force_document=False)
                await event.delete()
            else:
                await event.edit("**• ❌ فشل إنشاء الاستيكر**")
                
        except Exception as e:
            await event.edit(f"**• ❌ {str(e)[:150]}**")
        finally:
            safe_remove(img_path)
            safe_remove(stick_path)

    # ============== أمر .بيك (استيكر إلى صورة) ==============
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.بيك$'))
    async def sticker_to_photo(event):
        if not event.is_reply:
            await event.edit("**• ❌ يرجى الرد على استيكر**")
            return
        
        reply = await event.get_reply_message()
        if not reply.sticker:
            await event.edit("**• ❌ الرد على استيكر فقط**")
            return
        
        if not PIL_AVAILABLE:
            await event.edit("**• ❌ مكتبة Pillow غير مثبتة**")
            return
        
        has_space, free_mb = check_disk_space(10)
        if not has_space:
            await event.edit(f"**• ❌ المساحة غير كافية ({free_mb:.1f}MB)**")
            return
        
        await event.edit("**• 🔄 جاري التحويل...**")
        
        stick_path = None
        img_path = None
        
        try:
            stick_path = os.path.join(TEMP_DIR, f"sticker_{phone}_{int(time.time())}.webp")
            await client.download_media(reply, stick_path)
            
            if not os.path.exists(stick_path):
                raise ValueError("فشل تحميل الاستيكر")
            
            img_path = stick_path.replace('.webp', '.png')
            
            im = Image.open(stick_path).convert("RGBA")
            im.save(img_path, "PNG")
            
            if os.path.exists(img_path) and os.path.getsize(img_path) > 0:
                await client.send_file(event.chat_id, img_path)
                await event.delete()
            else:
                await event.edit("**• ❌ فشل التحويل**")
                
        except Exception as e:
            await event.edit(f"**• ❌ {str(e)[:150]}**")
        finally:
            safe_remove(stick_path)
            safe_remove(img_path)

    # ============== أمر .بن (تحميل صور) ==============
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.بن (.+)'))
    async def image_search_download(event):
        query = event.pattern_match.group(1).strip()
        
        has_space, free_mb = check_disk_space(20)
        if not has_space:
            await event.edit(f"**• ❌ المساحة غير كافية ({free_mb:.1f}MB)**\n**• استخدم .تنظيف**")
            return
        
        if query.startswith('http'):
            await event.edit("**• 📷 جاري تحميل الصورة...**")
            
            try:
                filepath = await asyncio.get_event_loop().run_in_executor(
                    _DOWNLOAD_EXECUTOR, download_image_direct, query, TEMP_DIR
                )
                
                if filepath and os.path.exists(filepath):
                    await client.send_file(event.chat_id, filepath)
                    await event.delete()
                    safe_remove(filepath)
                else:
                    await event.edit("**• ❌ فشل تحميل الصورة**")
                    
            except Exception as e:
                await event.edit(f"**• ❌ {str(e)[:150]}**")
            return
        
        await event.edit("**• 🔍 جاري البحث...**")
        
        urls = await asyncio.get_event_loop().run_in_executor(
            _DOWNLOAD_EXECUTOR, search_images, query, 5
        )
        
        if not urls:
            await event.edit("**• ❌ لم يتم العثور على صور**")
            return
        
        success = 0
        for i, url in enumerate(urls[:3]):
            try:
                await event.edit(f"**• 📥 جاري تحميل {i+1}/{min(len(urls), 3)}...**")
                
                filepath = await asyncio.get_event_loop().run_in_executor(
                    _DOWNLOAD_EXECUTOR, download_image_direct, url, TEMP_DIR
                )
                
                if filepath and os.path.exists(filepath):
                    await client.send_file(event.chat_id, filepath)
                    success += 1
                    safe_remove(filepath)
                
                await asyncio.sleep(0.5)
                
            except Exception as e:
                logger.error(f"فشل الصورة {i+1}: {e}")
                continue
        
        if success > 0:
            await event.delete()
        else:
            await event.edit("**• ❌ فشل تحميل جميع الصور**")

    # ============== التقليد ==============
    @client.on(events.NewMessage(incoming=True))
    async def auto_taqleed(event):
        if event.sender_id in taqleed_users.get(phone, {}) and event.text and not event.text.startswith('.'):
            await asyncio.sleep(0.5)
            try:
                await event.reply(event.text)
            except:
                pass

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.تقليد$'))
    async def taq(event):
        target = None
        if event.is_reply:
            reply = await event.get_reply_message()
            target = reply.sender_id
        elif event.is_private:
            target = event.chat_id
        
        if target:
            taqleed_users[phone][target] = True
            await event.edit("**• ✅ تم تفعيل التقليد**")
        else:
            await event.edit("**• ❌ يرجى الرد على رسالة**")

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.غ تقليد$'))
    async def notaq(event):
        target = None
        if event.is_reply:
            reply = await event.get_reply_message()
            target = reply.sender_id
        elif event.is_private:
            target = event.chat_id
        
        if target and target in taqleed_users.get(phone, {}):
            del taqleed_users[phone][target]
            await event.edit("**• ✅ تم إلغاء التقليد**")
        else:
            await event.edit("**• ❌ لا يوجد تقليد نشط**")

    # ============== الانتحال ==============
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.انتحال$'))
    async def ent7al(event):
        track_command(phone, ".انتحال")
        await event.edit("**• 🔄 جاري الانتحال...**")
        
        target_user = None
        if event.is_reply:
            try:
                reply = await event.get_reply_message()
                target_user = await client.get_entity(reply.sender_id)
            except:
                pass
        elif event.is_private:
            try:
                target_user = await client.get_entity(event.chat_id)
            except:
                pass
        
        if not target_user:
            await event.edit("**• ❌ فشل الانتحال**")
            return
        
        target_info = await get_user_info_full(client, target_user.id)
        if not target_info:
            await event.edit("**• ❌ فشل جلب معلومات المستخدم**")
            return
        
        me = await client.get_me()
        client_me[phone] = me
        
        original = {
            'first_name': me.first_name or '',
            'last_name': me.last_name if me.last_name is not None else '',
            'about': '',
            'added_photo_id': None
        }
        
        try:
            fu = await client(GetFullUserRequest('me'))
            if fu.full_user.about:
                original['about'] = fu.full_user.about
        except:
            pass
        
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
            except:
                pass
        except:
            pass
        
        bio_ok = False
        try:
            await client(UpdateProfileRequest(about=target_info['bio'][:70] if target_info['bio'] else ''))
            await asyncio.sleep(0.5)
            bio_ok = True
        except FloodWaitError as e:
            await asyncio.sleep(e.seconds)
            try:
                await client(UpdateProfileRequest(about=target_info['bio'][:70] if target_info['bio'] else ''))
                bio_ok = True
            except:
                pass
        except:
            pass
        
        photo_ok, added_id = await change_profile_photo(client, target_user.id, phone)
        if photo_ok and added_id:
            original['added_photo_id'] = added_id
        
        ent7al_original[phone] = original
        ent7al_users[phone] = True
        
        if name_ok and bio_ok and photo_ok:
            await event.edit("**• ✅ تم الانتحال**")
        elif name_ok or bio_ok or photo_ok:
            await event.edit("**• ⚠️ تم الانتحال جزئياً**")
        else:
            await event.edit("**• ❌ فشل الانتحال**")

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.الغاء انتحال$'))
    async def unent7al(event):
        track_command(phone, ".الغاء انتحال")
        await event.edit("**• 🔄 جاري إلغاء الانتحال...**")
        
        if not ent7al_users.get(phone) or not ent7al_original.get(phone):
            await event.edit("**• ❌ لا يوجد انتحال**")
            return
        
        original = ent7al_original[phone]
        
        for attempt in range(3):
            try:
                await client(UpdateProfileRequest(
                    first_name=original.get('first_name', ''),
                    last_name=original.get('last_name', '')
                ))
                await asyncio.sleep(1.5)
                break
            except FloodWaitError as e:
                await asyncio.sleep(e.seconds)
            except:
                await asyncio.sleep(1)
        
        if original.get('added_photo_id'):
            try:
                await client(DeletePhotosRequest(id=[InputPhoto(
                    id=original['added_photo_id'],
                    access_hash=0,
                    file_reference=b''
                )]))
                await asyncio.sleep(2)
            except FloodWaitError as e:
                await asyncio.sleep(e.seconds)
            except:
                pass
        
        try:
            await client(UpdateProfileRequest(about=original.get('about', '')))
        except:
            pass
        
        ent7al_users[phone] = False
        ent7al_original[phone] = {}
        await event.edit("**• ✅ تم إلغاء الانتحال**")

    # ============== مراقبة الخاص ==============
    @client.on(events.NewMessage(incoming=True, func=lambda e: e.is_private and not e.out))
    async def cache_message(event):
        try:
            me = await client.get_me()
            if event.sender_id == me.id:
                return
            
            if event.chat_id not in message_cache:
                message_cache[event.chat_id] = {}
            
            message_cache[event.chat_id][event.id] = {
                'text': event.text or "<وسائط>",
                'time': time.time()
            }
        except:
            pass

    @client.on(events.MessageEdited(incoming=True, func=lambda e: e.is_private and not e.out))
    async def notify_edit(event):
        try:
            me = await client.get_me()
            if event.sender_id == me.id:
                return
            
            user = await event.get_sender()
            name = user.first_name or ""
            if user.last_name:
                name += f" {user.last_name}"
            
            old = "نص غير معروف"
            if event.chat_id in message_cache and event.id in message_cache[event.chat_id]:
                old = message_cache[event.chat_id][event.id]['text']
            
            new = event.text or "<وسائط>"
            
            await client.send_message("me", f"**📝 {name} عدل رسالة**\n\n**من:** {old}\n**إلى:** {new}")
            
            if event.chat_id not in message_cache:
                message_cache[event.chat_id] = {}
            message_cache[event.chat_id][event.id] = {'text': new, 'time': time.time()}
            
        except:
            pass

    @client.on(events.MessageDeleted(incoming=True, func=lambda e: e.is_private and not e.out))
    async def notify_delete(event):
        try:
            for chat_id, msg_ids in event.deleted_ids.items():
                for msg_id in msg_ids:
                    if chat_id in message_cache and msg_id in message_cache[chat_id]:
                        text = message_cache[chat_id][msg_id]['text']
                        
                        user_name = "مستخدم"
                        try:
                            chat = await client.get_entity(chat_id)
                            user_name = chat.first_name or "مستخدم"
                        except:
                            pass
                        
                        await client.send_message("me", f"**🗑️ {user_name} حذف رسالة**\n\n**{text}**")
                        
                        del message_cache[chat_id][msg_id]
        except:
            pass

    # ============== تنظيف دوري ==============
    async def auto_cleanup():
        while True:
            await asyncio.sleep(1800)
            free_mb = get_free_space_mb()
            if free_mb < MIN_FREE_SPACE_MB * 2:
                count, size = clean_temp_files()
                if count > 0:
                    logger.info(f"🧹 تنظيف تلقائي: {count} ملف, {format_size(size)}")
    
    asyncio.create_task(auto_cleanup())

    logger.info(f"✅ جميع الأوامر جاهزة لـ {phone} - المساحة: {get_free_space_mb():.1f}MB")
