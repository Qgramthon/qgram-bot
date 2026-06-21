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
    logger.warning("⚠️ Pillow غير مثبتة. استخدم: pip install Pillow")

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
    logger.warning("⚠️ yt-dlp غير مثبتة. استخدم: pip install yt-dlp")

# ThreadPoolExecutor
_DOWNLOAD_EXECUTOR = ThreadPoolExecutor(max_workers=3, thread_name_prefix="dl")

# متغيرات مراقبة الخاص
message_cache = {}

# الحد الأدنى للمساحة بالميجابايت
MIN_FREE_SPACE_MB = 50

# ============== دوال إدارة المساحة ==============
def get_free_space_mb():
    """الحصول على المساحة المتاحة بالميجابايت"""
    try:
        # فحص المساحة في مجلد التخزين المؤقت
        temp_dir = TEMP_DIR if TEMP_DIR and os.path.exists(TEMP_DIR) else '/'
        disk_usage = shutil.disk_usage(temp_dir)
        free_mb = disk_usage.free / (1024 * 1024)
        return free_mb
    except Exception as e:
        logger.error(f"فشل فحص المساحة: {e}")
        return 999  # افتراض وجود مساحة كافية

def check_disk_space(min_mb=MIN_FREE_SPACE_MB):
    """فحص إذا كانت المساحة كافية"""
    free_mb = get_free_space_mb()
    
    if free_mb < min_mb:
        # محاولة تنظيف سريع
        clean_temp_files()
        free_mb = get_free_space_mb()
        
    return free_mb >= min_mb, free_mb

def clean_temp_files():
    """تنظيف جميع الملفات المؤقتة"""
    cleaned = 0
    freed_size = 0
    
    # تنظيف مجلد TEMP_DIR
    if TEMP_DIR and os.path.exists(TEMP_DIR):
        for filename in os.listdir(TEMP_DIR):
            filepath = os.path.join(TEMP_DIR, filename)
            if os.path.isfile(filepath):
                try:
                    file_size = os.path.getsize(filepath)
                    os.remove(filepath)
                    cleaned += 1
                    freed_size += file_size
                except:
                    continue
    
    # تنظيف مجلد temp العام
    try:
        temp_dir = tempfile.gettempdir()
        for filename in os.listdir(temp_dir):
            if filename.startswith(('voice_', 'img_', 'sticker_', 'audio_', 'video_', 'cobalt_', 'y2mate_')):
                filepath = os.path.join(temp_dir, filename)
                if os.path.isfile(filepath):
                    try:
                        file_size = os.path.getsize(filepath)
                        os.remove(filepath)
                        cleaned += 1
                        freed_size += file_size
                    except:
                        continue
    except:
        pass
    
    if cleaned > 0:
        logger.info(f"🧹 تنظيف: {cleaned} ملف، تم تحرير {freed_size/(1024*1024):.1f}MB")
    
    return cleaned, freed_size

def safe_remove(filepath):
    """حذف آمن للملف"""
    try:
        if filepath and os.path.exists(filepath):
            os.remove(filepath)
            return True
    except Exception as e:
        logger.error(f"فشل حذف {filepath}: {e}")
    return False

# ============== دوال مساعدة ==============
def format_duration(seconds):
    """تنسيق المدة الزمنية"""
    if not seconds:
        return "0:00"
    try:
        seconds = int(float(seconds))
        mins, secs = divmod(seconds, 60)
        hours, mins = divmod(mins, 60)
        if hours > 0:
            return f"{hours}:{mins:02d}:{secs:02d}"
        return f"{mins}:{secs:02d}"
    except:
        return "0:00"

def format_size(bytes_size):
    """تنسيق حجم الملف"""
    if bytes_size == 0:
        return "0 B"
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes_size < 1024.0:
            return f"{bytes_size:.1f} {unit}"
        bytes_size /= 1024.0
    return f"{bytes_size:.1f} TB"

# ============== دوال التحميل ==============
def download_yt_media(query: str, out_dir: str, audio_only: bool = False):
    """تحميل من يوتيوب باستخدام yt-dlp"""
    if not YTDLP_AVAILABLE:
        raise ValueError("مكتبة yt-dlp غير مثبتة")
    
    # تنظيف المساحة قبل التحميل
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
                'preferredquality': '128',  # جودة أقل لتوفير مساحة
            }],
            'quiet': True,
            'no_warnings': True,
            'max_filesize': 30 * 1024 * 1024,  # 30MB حد أقصى
        }
    else:
        ydl_opts = {
            'format': 'best[height<=360]/best',  # جودة منخفضة لتوفير مساحة
            'outtmpl': os.path.join(out_dir, f'video_{timestamp}.%(ext)s'),
            'quiet': True,
            'no_warnings': True,
            'max_filesize': 40 * 1024 * 1024,  # 40MB
            'merge_output_format': 'mp4',
        }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(query, download=True)
            
            # البحث عن الملف المحمل
            prefix = 'audio_' if audio_only else 'video_'
            files = [f for f in os.listdir(out_dir) if f.startswith(f'{prefix}{timestamp}')]
            
            if not files:
                raise ValueError("لم يتم العثور على الملف المحمل")
            
            filepath = os.path.join(out_dir, files[0])
            file_size = os.path.getsize(filepath)
            
            # التحقق من الحجم
            max_size = 30 if audio_only else 40
            if file_size > max_size * 1024 * 1024:
                safe_remove(filepath)
                raise ValueError(f"الملف كبير جداً ({format_size(file_size)})")
            
            return {
                'title': info.get('title', 'غير معروف')[:100],
                'duration': info.get('duration', 0),
                'uploader': info.get('uploader', 'غير معروف')[:50],
                'size': file_size
            }, filepath
            
    except Exception as e:
        # تنظيف الملفات المؤقتة
        prefix = 'audio_' if audio_only else 'video_'
        for f in os.listdir(out_dir):
            if f.startswith(f'{prefix}{timestamp}'):
                safe_remove(os.path.join(out_dir, f))
        raise ValueError(f"فشل التحميل: {str(e)[:150]}")

def download_image_direct(url: str, out_dir: str):
    """تحميل صورة مباشرة"""
    has_space, free_mb = check_disk_space(10)
    if not has_space:
        raise ValueError(f"المساحة غير كافية. المتاح: {free_mb:.1f}MB")
    
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        resp = requests.get(url, headers=headers, stream=True, timeout=30)
        
        if resp.status_code != 200:
            raise ValueError(f"خطأ في التحميل: {resp.status_code}")
        
        # تحديد الامتداد
        content_type = resp.headers.get('content-type', '')
        ext = '.jpg'
        if 'png' in content_type:
            ext = '.png'
        elif 'webp' in content_type:
            ext = '.webp'
        elif 'gif' in content_type:
            ext = '.gif'
        
        # حفظ الملف بحجم صغير
        timestamp = int(time.time() * 1000)
        filename = f"img_{timestamp}{ext}"
        filepath = os.path.join(out_dir, filename)
        
        total_size = 0
        with open(filepath, 'wb') as f:
            for chunk in resp.iter_content(8192):
                if chunk:
                    f.write(chunk)
                    total_size += len(chunk)
                    if total_size > 5 * 1024 * 1024:  # 5MB حد أقصى للصورة
                        safe_remove(filepath)
                        raise ValueError("الصورة كبيرة جداً (> 5MB)")
        
        if total_size < 1024:  # أقل من 1KB
            safe_remove(filepath)
            raise ValueError("الملف تالف أو صغير جداً")
        
        return filepath
        
    except Exception as e:
        raise ValueError(f"فشل تحميل الصورة: {str(e)[:150]}")

def search_images(query: str, limit: int = 5):
    """البحث عن صور"""
    images = []
    
    # تجربة DuckDuckGo
    try:
        from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            results = list(ddgs.images(query, max_results=limit))
        images = [img["image"] for img in results if img.get("image")]
    except:
        pass
    
    # إذا لم نجد، تجربة Google مباشرة
    if not images:
        try:
            headers = {'User-Agent': 'Mozilla/5.0'}
            url = f"https://www.google.com/search?q={requests.utils.quote(query)}&tbm=isch&hl=ar"
            resp = requests.get(url, headers=headers, timeout=15)
            if resp.status_code == 200:
                # استخراج روابط الصور
                urls = re.findall(r'"(https?://[^"]+\.(?:jpg|jpeg|png|webp))"', resp.text, re.I)
                images = urls[:limit]
        except:
            pass
    
    return images

# ============== دوال الانتحال ==============
async def get_user_info_full(client, user_id):
    """جلب معلومات المستخدم"""
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
    """تغيير صورة البروفايل"""
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
    """إعداد جميع الأوامر"""
    
    # تهيئة المتغيرات
    if phone not in muted_users:
        muted_users[phone] = {}
    if phone not in taqleed_users:
        taqleed_users[phone] = {}
    if phone not in ent7al_users:
        ent7al_users[phone] = False
    if phone not in ent7al_original:
        ent7al_original[phone] = {}

    # ============== أمر المساحة ==============
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.المساحة$'))
    async def space_check(event):
        """فحص المساحة وتنظيفها"""
        await event.edit("**• 📊 جاري فحص المساحة...**")
        
        # فحص المساحة
        free_mb = get_free_space_mb()
        has_space = free_mb >= MIN_FREE_SPACE_MB
        
        # تنظيف الملفات
        cleaned, freed = clean_temp_files()
        free_after = get_free_space_mb()
        
        msg = "**📊 حالة التخزين:**\n"
        msg += f"**• المساحة المتاحة:** {free_after:.1f} MB\n"
        
        if cleaned > 0:
            msg += f"**• 🧹 تم تنظيف {cleaned} ملف**\n"
            msg += f"**• 💾 تم تحرير: {format_size(freed)}**\n"
        
        msg += f"\n**• الحد الأدنى المطلوب:** {MIN_FREE_SPACE_MB} MB"
        
        if not has_space:
            msg += "\n\n⚠️ **تحذير: المساحة منخفضة!**"
        else:
            msg += "\n\n✅ **المساحة كافية**"
        
        await event.edit(msg)

    # ============== أمر تنظيف ==============
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.تنظيف$'))
    async def force_clean(event):
        """تنظيف جميع الملفات المؤقتة"""
        await event.edit("**• 🧹 جاري التنظيف الشامل...**")
        
        # تنظيف مزدوج
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

    # ============== أمر .نسخ (تحويل الصوت لنص) ==============
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.نسخ$'))
    async def transcribe_voice(event):
        """تحويل الصوت إلى نص - مع إدارة المساحة"""
        if not event.is_reply:
            await event.edit("**• ❌ يرجى الرد على رسالة صوتية**")
            return
        
        reply = await event.get_reply_message()
        if not (reply.voice or reply.audio):
            await event.edit("**• ❌ الرد على رسالة صوتية فقط**")
            return
        
        # فحص المساحة
        has_space, free_mb = check_disk_space(30)
        if not has_space:
            await event.edit(f"**• ❌ المساحة غير كافية ({free_mb:.1f}MB)**\n**• استخدم .تنظيف لتحرير مساحة**")
            return
        
        if not SR_AVAILABLE:
            await event.edit("**• ❌ مكتبة SpeechRecognition غير مثبتة**")
            return
        
        await event.edit("**• 🎤 جاري تحويل الصوت إلى نص...**")
        
        voice_path = None
        wav_path = None
        
        try:
            # تحميل الصوت في ملف مؤقت
            voice_path = os.path.join(TEMP_DIR, f"voice_{phone}_{int(time.time())}.ogg")
            await client.download_media(reply, voice_path)
            
            if not os.path.exists(voice_path) or os.path.getsize(voice_path) < 100:
                raise ValueError("فشل تحميل الملف الصوتي")
            
            # فحص المساحة مرة أخرى
            has_space, free_mb = check_disk_space(20)
            if not has_space:
                safe_remove(voice_path)
                raise ValueError("المساحة غير كافية للتحويل")
            
            # تحويل إلى WAV
            wav_path = voice_path.replace('.ogg', '.wav')
            
            result = subprocess.run(
                ['ffmpeg', '-i', voice_path, '-ac', '1', '-ar', '16000', 
                 '-sample_fmt', 's16', wav_path],
                capture_output=True,
                timeout=30
            )
            
            if result.returncode != 0 or not os.path.exists(wav_path):
                raise ValueError("فشل تحويل الصوت")
            
            # التعرف على النص
            recognizer = sr.Recognizer()
            with sr.AudioFile(wav_path) as source:
                audio_data = recognizer.record(source)
            
            # محاولة التعرف بالعربية ثم الإنجليزية
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
            # تنظيف فوري للملفات
            safe_remove(voice_path)
            safe_remove(wav_path)
            # تنظيف إضافي
            clean_temp_files()

    # ============== أمر .استيك (صورة إلى استيكر) ==============
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.استيك$'))
    async def photo_to_sticker(event):
        """تحويل صورة إلى استيكر - مع إدارة المساحة"""
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
        
        # فحص المساحة
        has_space, free_mb = check_disk_space(10)
        if not has_space:
            await event.edit(f"**• ❌ المساحة غير كافية ({free_mb:.1f}MB)**")
            return
        
        await event.edit("**• 🔄 جاري تحويل الصورة إلى استيكر...**")
        
        img_path = None
        stick_path = None
        
        try:
            # تحميل الصورة
            img_path = os.path.join(TEMP_DIR, f"img_{phone}_{int(time.time())}.jpg")
            await client.download_media(reply, img_path)
            
            if not os.path.exists(img_path):
                raise ValueError("فشل تحميل الصورة")
            
            # تحويل إلى استيكر
            stick_path = img_path.replace('.jpg', '.webp')
            
            # استخدام Image لتحويل الصورة
            im = Image.open(img_path)
            
            # تحويل إلى RGBA إذا لزم الأمر
            if im.mode != 'RGBA':
                im = im.convert('RGBA')
            
            # تصغير الحجم
            im.thumbnail((512, 512), Image.LANCZOS)
            
            # حفظ كـ WEBP مع ضغط
            im.save(stick_path, 'WEBP', quality=80, optimize=True)
            
            # إرسال الاستيكر
            if os.path.exists(stick_path) and os.path.getsize(stick_path) > 0:
                await client.send_file(event.chat_id, stick_path, force_document=False)
                await event.delete()
            else:
                await event.edit("**• ❌ فشل إنشاء الاستيكر**")
                
        except Exception as e:
            await event.edit(f"**• ❌ {str(e)[:150]}**")
        finally:
            # تنظيف فوري
            safe_remove(img_path)
            safe_remove(stick_path)

    # ============== أمر .بيك (استيكر إلى صورة) ==============
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.بيك$'))
    async def sticker_to_photo(event):
        """تحويل استيكر إلى صورة - مع إدارة المساحة"""
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
        
        # فحص المساحة
        has_space, free_mb = check_disk_space(10)
        if not has_space:
            await event.edit(f"**• ❌ المساحة غير كافية ({free_mb:.1f}MB)**")
            return
        
        await event.edit("**• 🔄 جاري تحويل الاستيكر إلى صورة...**")
        
        stick_path = None
        img_path = None
        
        try:
            # تحميل الاستيكر
            stick_path = os.path.join(TEMP_DIR, f"sticker_{phone}_{int(time.time())}.webp")
            await client.download_media(reply, stick_path)
            
            if not os.path.exists(stick_path):
                raise ValueError("فشل تحميل الاستيكر")
            
            # تحويل إلى PNG
            img_path = stick_path.replace('.webp', '.png')
            
            im = Image.open(stick_path)
            if im.mode != 'RGBA':
                im = im.convert('RGBA')
            
            # حفظ كـ PNG
            im.save(img_path, 'PNG', optimize=True)
            
            # إرسال الصورة
            if os.path.exists(img_path) and os.path.getsize(img_path) > 0:
                await client.send_file(event.chat_id, img_path)
                await event.delete()
            else:
                await event.edit("**• ❌ فشل تحويل الاستيكر**")
                
        except Exception as e:
            await event.edit(f"**• ❌ {str(e)[:150]}**")
        finally:
            # تنظيف فوري
            safe_remove(stick_path)
            safe_remove(img_path)

    # ============== أمر .بن (تحميل صور) ==============
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.بن (.+)'))
    async def image_search_download(event):
        """تحميل الصور - مع إدارة المساحة"""
        query = event.pattern_match.group(1).strip()
        
        # فحص المساحة
        has_space, free_mb = check_disk_space(20)
        if not has_space:
            await event.edit(f"**• ❌ المساحة غير كافية ({free_mb:.1f}MB)**\n**• استخدم .تنظيف**")
            return
        
        # إذا كان رابط مباشر
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
        
        # البحث عن صور
        await event.edit("**• 🔍 جاري البحث...**")
        
        urls = await asyncio.get_event_loop().run_in_executor(
            _DOWNLOAD_EXECUTOR, search_images, query, 5
        )
        
        if not urls:
            await event.edit("**• ❌ لم يتم العثور على صور**")
            return
        
        # تحميل وإرسال الصور
        success = 0
        for i, url in enumerate(urls[:3]):  # 3 صور فقط كحد أقصى
            try:
                await event.edit(f"**• 📥 جاري تحميل {i+1}/{min(len(urls), 3)}...**")
                
                filepath = await asyncio.get_event_loop().run_in_executor(
                    _DOWNLOAD_EXECUTOR, download_image_direct, url, TEMP_DIR
                )
                
                if filepath and os.path.exists(filepath):
                    await client.send_file(event.chat_id, filepath)
                    success += 1
                    safe_remove(filepath)  # حذف فوري بعد الإرسال
                
                await asyncio.sleep(0.5)
                
            except Exception as e:
                logger.error(f"فشل الصورة {i+1}: {e}")
                continue
        
        if success > 0:
            await event.delete()
        else:
            await event.edit("**• ❌ فشل تحميل جميع الصور**")

    # ============== أمر .يوت (تحميل صوت) ==============
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.يوت (.+)'))
    async def youtube_audio(event):
        """تحميل صوت من يوتيوب"""
        if not YTDLP_AVAILABLE:
            await event.edit("**• ❌ مكتبة yt-dlp غير مثبتة**")
            return
        
        query = event.pattern_match.group(1).strip()
        
        # فحص المساحة
        has_space, free_mb = check_disk_space(80)
        if not has_space:
            await event.edit(f"**• ❌ المساحة غير كافية ({free_mb:.1f}MB)**\n**• استخدم .تنظيف**")
            return
        
        await event.edit("**• 🎵 جاري تحميل الصوت...**")
        
        filepath = None
        
        try:
            info, filepath = await asyncio.get_event_loop().run_in_executor(
                _DOWNLOAD_EXECUTOR, download_yt_media, query, TEMP_DIR, True
            )
            
            # إرسال الملف
            await client.send_file(
                event.chat_id,
                filepath,
                caption=f"🎵 {info['title']}\n⏱ {format_duration(info['duration'])}",
                attributes=[DocumentAttributeAudio(
                    duration=info['duration'],
                    title=info['title'],
                    performer=info['uploader']
                )],
                supports_streaming=True
            )
            
            await event.delete()
            
        except Exception as e:
            await event.edit(f"**• ❌ {str(e)[:200]}**")
        finally:
            safe_remove(filepath)  # حذف فوري
            clean_temp_files()  # تنظيف إضافي

    # ============== أمر .فيد (تحميل فيديو) ==============
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.فيد (.+)'))
    async def video_download(event):
        """تحميل فيديو من يوتيوب"""
        if not YTDLP_AVAILABLE:
            await event.edit("**• ❌ مكتبة yt-dlp غير مثبتة**")
            return
        
        query = event.pattern_match.group(1).strip()
        
        # فحص المساحة
        has_space, free_mb = check_disk_space(80)
        if not has_space:
            await event.edit(f"**• ❌ المساحة غير كافية ({free_mb:.1f}MB)**\n**• استخدم .تنظيف**")
            return
        
        await event.edit("**• 🎬 جاري تحميل الفيديو...**")
        
        filepath = None
        
        try:
            info, filepath = await asyncio.get_event_loop().run_in_executor(
                _DOWNLOAD_EXECUTOR, download_yt_media, query, TEMP_DIR, False
            )
            
            # إرسال الفيديو
            await client.send_file(
                event.chat_id,
                filepath,
                caption=f"🎬 {info['title']}\n⏱ {format_duration(info['duration'])}",
                attributes=[DocumentAttributeVideo(
                    duration=info['duration'],
                    w=0,
                    h=0,
                    supports_streaming=True
                )],
                supports_streaming=True
            )
            
            await event.delete()
            
        except Exception as e:
            await event.edit(f"**• ❌ {str(e)[:200]}**")
        finally:
            safe_remove(filepath)  # حذف فوري
            clean_temp_files()  # تنظيف إضافي

    # ============== التقليد ==============
    @client.on(events.NewMessage(incoming=True))
    async def auto_taqleed(event):
        """تقليد تلقائي"""
        if event.sender_id in taqleed_users.get(phone, {}) and event.text and not event.text.startswith('.'):
            await asyncio.sleep(0.5)
            try:
                await event.reply(event.text)
            except:
                pass

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.تقليد$'))
    async def taq(event):
        """تفعيل التقليد"""
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
        """إلغاء التقليد"""
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
        """انتحال شخصية"""
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
        
        # حفظ المعلومات الأصلية
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
            except:
                pass
        except:
            pass
        
        # تغيير البايو
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
        
        # تغيير الصورة
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
        """إلغاء الانتحال"""
        track_command(phone, ".الغاء انتحال")
        await event.edit("**• 🔄 جاري إلغاء الانتحال...**")
        
        if not ent7al_users.get(phone) or not ent7al_original.get(phone):
            await event.edit("**• ❌ لا يوجد انتحال**")
            return
        
        original = ent7al_original[phone]
        
        # استعادة الاسم
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
        
        # حذف الصورة
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
        
        # استعادة البايو
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
        """تخزين رسائل الخاص"""
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
        """إشعار بتعديل رسالة"""
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
        """إشعار بحذف رسالة"""
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
        """تنظيف تلقائي كل 30 دقيقة"""
        while True:
            await asyncio.sleep(1800)  # 30 دقيقة
            free_mb = get_free_space_mb()
            if free_mb < MIN_FREE_SPACE_MB * 2:  # إذا كانت المساحة أقل من 100MB
                count, size = clean_temp_files()
                if count > 0:
                    logger.info(f"🧹 تنظيف تلقائي: {count} ملف، {format_size(size)}")
    
    asyncio.create_task(auto_cleanup())

    logger.info(f"✅ جميع الأوامر جاهزة لـ {phone} - المساحة: {get_free_space_mb():.1f}MB")
