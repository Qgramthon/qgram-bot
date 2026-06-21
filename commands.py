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
import json
import random
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote, urlencode
from telethon import events
from telethon.errors import FloodWaitError, ChatAdminRequiredError
from telethon.tl.functions.account import UpdateProfileRequest
from telethon.tl.functions.photos import UploadProfilePhotoRequest, DeletePhotosRequest
from telethon.tl.types import (
    InputPhoto, DocumentAttributeAudio, DocumentAttributeVideo
)
from telethon.tl.functions.users import GetFullUserRequest
from telethon.tl.functions.channels import InviteToChannelRequest
from telethon.tl.functions.messages import AddChatUserRequest, GetDialogsRequest
from telethon.tl.types import InputPeerEmpty
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

try:
    import speech_recognition as sr
    SR_AVAILABLE = True
except ImportError:
    SR_AVAILABLE = False

try:
    import yt_dlp
    YTDLP_AVAILABLE = True
except ImportError:
    YTDLP_AVAILABLE = False

_DOWNLOAD_EXECUTOR = ThreadPoolExecutor(max_workers=3, thread_name_prefix="dl")
message_cache = {}
active_animations = {}
MIN_FREE_SPACE_MB = 50

text_format_mode = {}

# ============== دوال المساحة ==============
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
    return cleaned

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
    if bytes_size == 0: return "0 B"
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes_size < 1024.0: return f"{bytes_size:.1f} {unit}"
        bytes_size /= 1024.0
    return f"{bytes_size:.1f} TB"

def clean_filename(name):
    name = re.sub(r'[<>:"/\\|?*]', '', name)
    name = re.sub(r'\s+', ' ', name).strip()
    return name[:100]

def apply_telegram_format(text, format_type):
    if not text: return text
    if format_type == 'bold': return f"**{text}**"
    elif format_type == 'italic': return f"__{text}__"
    elif format_type == 'strike': return f"~~{text}~~"
    return text

# ============== دوال النسب ==============
def get_random_percentage(): return random.randint(1, 100)
def get_love_comment(p): 
    if p >= 90: return "💘 حب من طرف واحد ولا اتنين يا عم"
    elif p >= 70: return "❤️‍🔥 فيه حب بس مش قد كده"
    elif p >= 50: return "💕 نص نص يا معلم"
    elif p >= 30: return "💔 الحب ضعيف شوية"
    else: return "💀 مفيش حب خالص يا عم"
def get_stupidity_comment(p): 
    if p >= 90: return "🐄 هاتوله برسيم... شكل مفيش منك امل"
    elif p >= 70: return "🤪 غبي بس لسه فيه بصيص أمل"
    elif p >= 50: return "🤔 نص نص... مش متأكدين"
    elif p >= 30: return "🧐 لا يعم ده طلع بيفهم اهو"
    else: return "🧠 ده عبقري والله"
def get_lying_comment(p): 
    if p >= 90: return "🤥 دنت كداب اوي يلا"
    elif p >= 70: return "😏 كداب ومحترف كمان"
    elif p >= 50: return "🤨 فيه كدب شوية"
    elif p >= 30: return "🙂 لا يعم ده غلبان صادق"
    else: return "😇 ده صادق جدا والله"

HACK_MESSAGES = ["🔓 جاري اختراق الحساب...","📱 جاري الوصول للبيانات...","🔑 تم كسر كلمة المرور: ******","📸 جاري تحميل الصور الخاصة...","💬 جاري قراءة المحادثات...","📍 تم تحديد الموقع الجغرافي...","💰 جاري سرقة الرصيد...","✅ تم الاختراق بنجاح!","😈 كنت بهزر معاك يسطا"]
KILL_MESSAGES = ["🔫 جاري التصويب...","💣 تم القاء قنبلة...","🚀 صاروخ في الطريق...","💀 الضربة القاضية...","🪦 تم الدفن...","👻 روحه طلعت...","😇 البقاء لله...","😂 كنت بهزر يا غلبان"]

# ============== دوال الأنيمشن ==============
def create_animation_pattern(emoji_list):
    patterns = []
    for i in range(len(emoji_list)):
        shifted = emoji_list[i:] + emoji_list[:i]
        patterns.append(''.join(shifted))
    return patterns

ANIMATION_PATTERNS = {
    'ضحك': create_animation_pattern(['😂', '🤣', '😂', '🤣']),
    'قلب': create_animation_pattern(['❤️', '💛', '💚', '💜']),
    'غيمة': create_animation_pattern(['☁️', '🌧️', '⛅', '🌩️']),
    'ورد': create_animation_pattern(['🌸', '🌹', '🌻', '🌺']),
    'كوكب': create_animation_pattern(['✨', '🌍', '🪐', '🌙']),
    'شتاء': create_animation_pattern(['⛄', '❄️', '☂️', '🌙']),
    'قمر': create_animation_pattern(['🌕', '🌖', '🌗', '🌘']),
}

async def run_animation(event, animation_name, duration=5):
    if animation_name not in ANIMATION_PATTERNS: return
    patterns = ANIMATION_PATTERNS[animation_name]
    chat_id = event.chat_id
    message = await event.get_reply_message() if event.is_reply else None
    anim_key = f"{chat_id}_{animation_name}"
    active_animations[anim_key] = True
    start_time = time.time()
    try:
        while active_animations.get(anim_key, False):
            for pattern in patterns:
                if not active_animations.get(anim_key, False): break
                try:
                    if message: await message.edit(pattern)
                    else: await event.edit(pattern)
                    await asyncio.sleep(0.5)
                    if time.time() - start_time >= duration:
                        active_animations[anim_key] = False
                        break
                except FloodWaitError as e: await asyncio.sleep(e.seconds)
                except: active_animations[anim_key] = False; break
    except: pass
    finally:
        if anim_key in active_animations: del active_animations[anim_key]

# ============== دوال البحث عن الصور - محسنة بالكامل ==============
def search_images_google_serpapi(query: str, limit: int = 10) -> list:
    """بحث باستخدام SerpAPI (Google Images) - أدق نتيجة"""
    images = []
    try:
        # استخدام SerpAPI لو موجود
        api_key = os.environ.get("SERPAPI_KEY", "")
        if api_key:
            from serpapi import GoogleSearch
            params = {"q": query, "tbm": "isch", "ijn": "0", "api_key": api_key}
            search = GoogleSearch(params)
            results = search.get_dict()
            for img in results.get("images_results", []):
                if img.get("original"):
                    images.append(img["original"])
                if len(images) >= limit: break
            if images: return images
    except: pass
    
    # طريقة مباشرة بدون API
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml',
            'Accept-Language': 'en-US,en;q=0.9',
        }
        # بحث مباشر عن الصور
        search_url = f"https://www.google.com/search?q={quote(query)}&tbm=isch&hl=en&safe=off&nfpr=1"
        resp = requests.get(search_url, headers=headers, timeout=15)
        
        if resp.status_code == 200:
            # استخراج روابط الصور من البيانات المنظمة
            matches = re.findall(r'"ou":"(https?://[^"]+)"', resp.text)
            if not matches:
                matches = re.findall(r'"src":"(https?://[^"]+)"', resp.text)
            if not matches:
                matches = re.findall(r'"(https?://[^"]+\.(?:jpg|jpeg|png|webp|gif)[^"]*)"', resp.text, re.I)
            
            for url in matches:
                if url.startswith('http') and not any(s in url.lower() for s in ['google', 'gstatic', '/favicon', '/icon', 'data:image']):
                    # التأكد إن الرابط صورة فعلاً
                    if any(ext in url.lower() for ext in ['.jpg', '.jpeg', '.png', '.webp', '.gif']) or 'image' in url.lower():
                        images.append(url)
                        if len(images) >= limit: break
    except Exception as e:
        logger.error(f"Google search error: {e}")
    
    return images

def search_images_bing_api(query: str, limit: int = 10) -> list:
    """بحث في Bing"""
    images = []
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml',
        }
        url = f"https://www.bing.com/images/search?q={quote(query)}&first=1&count={limit}&qft=+filterui:photo-photo&form=IRFLTR"
        resp = requests.get(url, headers=headers, timeout=15)
        
        if resp.status_code == 200:
            # استخراج murl من Bing
            matches = re.findall(r'murl&quot;:&quot;(https?://[^&]+)&quot;', resp.text)
            if not matches:
                matches = re.findall(r'src="(https?://[^"]+\.(?:jpg|jpeg|png|webp)[^"]*)"', resp.text, re.I)
            
            for url in matches:
                if url.startswith('http') and 'bing.com' not in url.lower():
                    images.append(url)
                    if len(images) >= limit: break
    except Exception as e:
        logger.error(f"Bing search error: {e}")
    
    return images

def search_images_ddg(query: str, limit: int = 10) -> list:
    """بحث في DuckDuckGo"""
    images = []
    try:
        from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            results = list(ddgs.images(query, max_results=limit))
            images = [img["image"] for img in results if img.get("image")]
    except:
        pass
    return images

def search_all_images(query: str, limit: int = 5) -> list:
    """بحث شامل من جميع المحركات مع تصفية دقيقة"""
    all_images = []
    
    # البحث في كل المحركات
    engines = [
        ("DuckDuckGo", search_images_ddg),
        ("Google", search_images_google_serpapi),
        ("Bing", search_images_bing_api),
    ]
    
    for name, func in engines:
        try:
            results = func(query, limit=10)
            if results:
                logger.info(f"{name}: {len(results)} results for '{query}'")
                all_images.extend(results)
        except Exception as e:
            logger.error(f"{name} failed: {e}")
    
    # تنظيف وتصفية النتائج
    seen = set()
    unique = []
    
    # كلمات ممنوعة في الروابط
    blocked = ['icon', 'favicon', 'avatar', 'logo', 'thumb/32', 'thumb/64', 
               'placeholder', '1x1', 'blank', 'transparent', 'pixel', 'spacer',
               'data:image', 'svg', 'gstatic.com']
    
    for url in all_images:
        url = url.strip()
        if not url.startswith('http'): continue
        
        # تخطي الروابط الممنوعة
        if any(b in url.lower() for b in blocked): continue
        
        # التأكد من وجود امتداد صورة أو كلمة image في الرابط
        is_image = any(ext in url.lower() for ext in ['.jpg', '.jpeg', '.png', '.webp', '.gif', '.bmp'])
        if not is_image:
            # لو مفيش امتداد نتأكد إنه مش SVG أو أيقونة
            if '.svg' in url.lower() or url.endswith('/'): continue
        
        if url not in seen:
            seen.add(url)
            unique.append(url)
            if len(unique) >= limit * 2: break  # نجيب ضعف العدد عشان التحميل
    
    logger.info(f"Unique images for '{query}': {len(unique)}")
    
    # لو مفيش نتائج، نجرب البحث بدون مسافات أو بأول كلمة
    if not unique and ' ' in query:
        # نجرب أول كلمتين
        parts = query.split()
        if len(parts) >= 2:
            simple = ' '.join(parts[:2])
            logger.info(f"Retrying with: {simple}")
            return search_all_images(simple, limit)
    
    return unique[:limit]

def download_image_direct(url: str, out_dir: str) -> str:
    """تحميل صورة"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Referer': 'https://www.google.com/',
            'Accept': 'image/webp,image/*,*/*;q=0.8',
        }
        resp = requests.get(url, headers=headers, stream=True, timeout=30, allow_redirects=True)
        if resp.status_code != 200: return None
        
        content_type = resp.headers.get('content-type', '').lower()
        ext = '.jpg'
        if 'png' in content_type: ext = '.png'
        elif 'webp' in content_type: ext = '.webp'
        elif 'gif' in content_type: ext = '.gif'
        elif 'jpeg' in content_type: ext = '.jpg'
        
        filename = f"img_{int(time.time()*1000)}_{hashlib.md5(url.encode()).hexdigest()[:8]}{ext}"
        filepath = os.path.join(out_dir, filename)
        
        size = 0
        with open(filepath, 'wb') as f:
            for chunk in resp.iter_content(8192):
                if chunk:
                    f.write(chunk)
                    size += len(chunk)
                    if size > 15 * 1024 * 1024:
                        safe_remove(filepath)
                        return None
        
        if size < 2048:  # 2KB minimum
            safe_remove(filepath)
            return None
        
        return filepath
    except:
        return None

# ============== دوال يوتيوب ==============
def download_youtube_media(query: str, out_dir: str, audio_only: bool = False):
    if not YTDLP_AVAILABLE: raise ValueError("مكتبة yt-dlp غير مثبتة")
    
    if not query.startswith("http"): query = f"ytsearch:{query}"
    
    timestamp = int(time.time())
    
    if audio_only:
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': os.path.join(out_dir, f'audio_{timestamp}.%(ext)s'),
            'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '192'}],
            'quiet': True, 'no_warnings': True, 'max_filesize': 50*1024*1024, 'extract_flat': False,
        }
    else:
        ydl_opts = {
            'format': 'best[height<=720]/best',
            'outtmpl': os.path.join(out_dir, f'video_{timestamp}.%(ext)s'),
            'quiet': True, 'no_warnings': True, 'max_filesize': 100*1024*1024,
            'merge_output_format': 'mp4', 'extract_flat': False,
        }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(query, download=False)
            if 'entries' in info_dict: info_dict = info_dict['entries'][0]
            
            title = info_dict.get('title', 'بدون عنوان')
            uploader = info_dict.get('uploader', 'غير معروف')
            duration = info_dict.get('duration', 0)
            
            info_dict = ydl.extract_info(query, download=True)
            
            prefix = 'audio_' if audio_only else 'video_'
            files = [f for f in os.listdir(out_dir) if f.startswith(f'{prefix}{timestamp}')]
            if not files: raise ValueError("لم يتم العثور على الملف")
            
            filepath = os.path.join(out_dir, files[0])
            if duration == 0: duration = info_dict.get('duration', 0)
            
            return {
                'title': title, 'uploader': uploader, 'duration': duration,
                'duration_str': format_duration(duration),
                'size': os.path.getsize(filepath), 'size_str': format_size(os.path.getsize(filepath)),
            }, filepath
    except Exception as e:
        for f in os.listdir(out_dir):
            if f.startswith(f'{prefix}{timestamp}'): safe_remove(os.path.join(out_dir, f))
        raise ValueError(f"فشل: {str(e)[:200]}")

def convert_video_to_audio(video_path: str, out_dir: str):
    if not os.path.exists(video_path): raise ValueError("الملف غير موجود")
    
    audio_path = os.path.join(out_dir, f"audio_conv_{int(time.time())}.mp3")
    
    try:
        result = subprocess.run([
            'ffmpeg', '-i', video_path, '-vn', '-acodec', 'libmp3lame',
            '-ab', '192k', '-ar', '44100', '-y', audio_path
        ], capture_output=True, timeout=120)
        
        if result.returncode != 0: raise ValueError("فشل التحويل")
        
        duration = 0
        try:
            probe = subprocess.run([
                'ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                '-of', 'default=noprint_wrappers=1:nokey=1', video_path
            ], capture_output=True, timeout=10)
            if probe.returncode == 0: duration = float(probe.stdout.decode().strip())
        except: pass
        
        return {
            'path': audio_path, 'duration': duration,
            'duration_str': format_duration(duration),
            'size': os.path.getsize(audio_path), 'size_str': format_size(os.path.getsize(audio_path)),
        }
    except:
        safe_remove(audio_path)
        raise

# ============== دوال الانتحال ==============
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
        await asyncio.sleep(e.seconds)
        try:
            bio = io.BytesIO(); await client.download_profile_photo(user_id, file=bio); bio.seek(0)
            uploaded = await client.upload_file(bio, file_name="photo.jpg")
            await client(UploadProfilePhotoRequest(file=uploaded))
            return True, None
        except: return False, None
    except: return False, None

# ============== إعداد المعالجات ==============
async def setup_handlers(client, phone):
    
    if phone not in muted_users: muted_users[phone] = {}
    if phone not in taqleed_users: taqleed_users[phone] = {}
    if phone not in ent7al_users: ent7al_users[phone] = False
    if phone not in ent7al_original: ent7al_original[phone] = {}
    if phone not in text_format_mode: text_format_mode[phone] = None

    # ============== تنسيق تلقائي ==============
    @client.on(events.NewMessage(outgoing=True))
    async def auto_format_outgoing(event):
        if event.text and event.text.startswith('.'): return
        format_type = text_format_mode.get(phone)
        if format_type and event.text:
            formatted_text = apply_telegram_format(event.text, format_type)
            if formatted_text != event.text:
                try: await event.edit(formatted_text, parse_mode='markdown')
                except: pass

    # ============== أوامر التنسيق ==============
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.عريض$'))
    async def toggle_bold(event):
        if text_format_mode.get(phone) == 'bold':
            text_format_mode[phone] = None
            await event.edit("**• ✅ تم إلغاء الخط العريض**", parse_mode='markdown')
        else:
            text_format_mode[phone] = 'bold'
            await event.edit("**• ✅ تم تفعيل الخط العريض**", parse_mode='markdown')

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.مائل$'))
    async def toggle_italic(event):
        if text_format_mode.get(phone) == 'italic':
            text_format_mode[phone] = None
            await event.edit("**• ✅ تم إلغاء الخط المائل**", parse_mode='markdown')
        else:
            text_format_mode[phone] = 'italic'
            await event.edit("**• ✅ تم تفعيل الخط المائل**", parse_mode='markdown')

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.مشطوب$'))
    async def toggle_strike(event):
        if text_format_mode.get(phone) == 'strike':
            text_format_mode[phone] = None
            await event.edit("**• ✅ تم إلغاء الخط المشطوب**", parse_mode='markdown')
        else:
            text_format_mode[phone] = 'strike'
            await event.edit("**• ✅ تم تفعيل الخط المشطوب**", parse_mode='markdown')

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.غ خط$'))
    async def reset_format(event):
        text_format_mode[phone] = None
        await event.edit("**• ✅ تم إرجاع الخط إلى الوضع الطبيعي**", parse_mode='markdown')

    # ============== أوامر النسب ==============
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.حب$'))
    async def love_calc(event):
        if not event.is_reply: await event.edit("**• ❌ يرجى الرد على شخص**", parse_mode='markdown'); return
        reply = await event.get_reply_message()
        user = await client.get_entity(reply.sender_id)
        name = user.first_name or "المستخدم"
        p = get_random_percentage()
        result = f"💘 **نسبة حب {name}:**\n{'█' * (p // 10)}{'░' * (10 - p // 10)} **{p}%**\n\n**{get_love_comment(p)}**"
        await event.edit(result, parse_mode='markdown')

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.غباء$'))
    async def stupidity_calc(event):
        if not event.is_reply: await event.edit("**• ❌ يرجى الرد على شخص**", parse_mode='markdown'); return
        reply = await event.get_reply_message()
        user = await client.get_entity(reply.sender_id)
        name = user.first_name or "المستخدم"
        p = get_random_percentage()
        result = f"🧠 **نسبة غباء {name}:**\n{'█' * (p // 10)}{'░' * (10 - p // 10)} **{p}%**\n\n**{get_stupidity_comment(p)}**"
        await event.edit(result, parse_mode='markdown')

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.كدب$'))
    async def lying_calc(event):
        if not event.is_reply: await event.edit("**• ❌ يرجى الرد على شخص**", parse_mode='markdown'); return
        reply = await event.get_reply_message()
        user = await client.get_entity(reply.sender_id)
        name = user.first_name or "المستخدم"
        p = get_random_percentage()
        result = f"🤥 **نسبة كذب {name}:**\n{'█' * (p // 10)}{'░' * (10 - p // 10)} **{p}%**\n\n**{get_lying_comment(p)}**"
        await event.edit(result, parse_mode='markdown')

    # ============== أوامر المزاح ==============
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.تهكير$'))
    async def fake_hack(event):
        if not event.is_reply: await event.edit("**• ❌ يرجى الرد على شخص**", parse_mode='markdown'); return
        for msg in HACK_MESSAGES:
            await event.edit(f"**{msg}**", parse_mode='markdown')
            await asyncio.sleep(1.5)

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.قتل$'))
    async def fake_kill(event):
        if not event.is_reply: await event.edit("**• ❌ يرجى الرد على شخص**", parse_mode='markdown'); return
        for msg in KILL_MESSAGES:
            await event.edit(f"**{msg}**", parse_mode='markdown')
            await asyncio.sleep(1.5)

    # ============== أوامر الإحصائيات ==============
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.جروباتي$'))
    async def my_groups(event):
        await event.edit("**• 📊 جاري حساب الجروبات...**", parse_mode='markdown')
        groups = sum(1 async for d in client.iter_dialogs() if d.is_group)
        await event.edit(f"**📊 عدد الجروبات:** {groups}", parse_mode='markdown')

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.قنواتي$'))
    async def my_channels(event):
        await event.edit("**• 📊 جاري حساب القنوات...**", parse_mode='markdown')
        channels = sum(1 async for d in client.iter_dialogs() if d.is_channel and not d.is_group)
        await event.edit(f"**📊 عدد القنوات:** {channels}", parse_mode='markdown')

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.تونزي$'))
    async def top_interactions(event):
        await event.edit("**• 📊 جاري تحليل التفاعلات...**", parse_mode='markdown')
        interactions = {}
        async for dialog in client.iter_dialogs():
            try:
                async for message in client.iter_messages(dialog.id, limit=100):
                    if message.sender_id and message.sender_id != (await client.get_me()).id:
                        interactions[message.sender_id] = interactions.get(message.sender_id, 0) + 1
            except: continue
        if not interactions: await event.edit("**• ❌ لا توجد تفاعلات**", parse_mode='markdown'); return
        top = max(interactions, key=interactions.get)
        try: name = (await client.get_entity(top)).first_name or "مستخدم"
        except: name = "مستخدم"
        await event.edit(f"**🏆 الأكثر تفاعلاً:**\n👤 **{name}**\n💬 **{interactions[top]} رسالة**", parse_mode='markdown')

    # ============== أوامر الأنيمشن ==============
    for cmd_name in ['ضحك', 'قلب', 'غيمة', 'ورد', 'كوكب', 'شتاء', 'قمر']:
        @client.on(events.NewMessage(outgoing=True, pattern=rf'^\.{cmd_name}$'))
        async def animation_handler(event, name=cmd_name):
            asyncio.create_task(run_animation(event, name, duration=5))

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.وقف$'))
    async def stop_animation(event):
        stopped = sum(1 for k in list(active_animations.keys()) if k.startswith(str(event.chat_id)) and active_animations.pop(k, None))
        await event.edit(f"**• ⏹️ تم إيقاف {stopped} أنيمشن**" if stopped else "**• ❌ لا يوجد أنيمشن**", parse_mode='markdown')

    # ============== أوامر التحميل ==============
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.يوت (.+)'))
    async def youtube_audio(event):
        if not YTDLP_AVAILABLE: await event.edit("**• ❌ مكتبة yt-dlp غير مثبتة**", parse_mode='markdown'); return
        query = event.pattern_match.group(1).strip()
        await event.edit("**• 🎵 جاري التحميل...**", parse_mode='markdown')
        filepath = None
        try:
            info, filepath = await asyncio.get_event_loop().run_in_executor(_DOWNLOAD_EXECUTOR, download_youtube_media, query, TEMP_DIR, True)
            title = info['title'][:52] + '...' if len(info['title']) > 55 else info['title']
            await client.send_file(event.chat_id, filepath,
                                   caption=f"{title}\n• {info['duration_str']} | ᥲᥙძᎥ᥆",
                                   attributes=[DocumentAttributeAudio(duration=info['duration'], title=info['title'], performer=info['uploader'])],
                                   supports_streaming=True)
            await event.delete()
        except Exception as e: await event.edit(f"**• ❌ {str(e)[:200]}**", parse_mode='markdown')
        finally: safe_remove(filepath)

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.فيد (.+)'))
    async def video_download(event):
        if not YTDLP_AVAILABLE: await event.edit("**• ❌ مكتبة yt-dlp غير مثبتة**", parse_mode='markdown'); return
        query = event.pattern_match.group(1).strip()
        await event.edit("**• 🎬 جاري التحميل...**", parse_mode='markdown')
        filepath = None
        try:
            info, filepath = await asyncio.get_event_loop().run_in_executor(_DOWNLOAD_EXECUTOR, download_youtube_media, query, TEMP_DIR, False)
            title = info['title'][:52] + '...' if len(info['title']) > 55 else info['title']
            await client.send_file(event.chat_id, filepath,
                                   caption=f"{title}\n• {info['duration_str']} | ᥎Ꭵძꫀ᥆",
                                   attributes=[DocumentAttributeVideo(duration=info['duration'], w=0, h=0, supports_streaming=True)],
                                   supports_streaming=True)
            await event.delete()
        except Exception as e: await event.edit(f"**• ❌ {str(e)[:200]}**", parse_mode='markdown')
        finally: safe_remove(filepath)

    # ============== أمر .صوت - المعدل ==============
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.صوت$'))
    async def video_to_audio(event):
        if not event.is_reply: await event.edit("**• ❌ يرجى الرد على فيديو**", parse_mode='markdown'); return
        
        reply = await event.get_reply_message()
        if not (reply.video or reply.document): await event.edit("**• ❌ يرجى الرد على فيديو**", parse_mode='markdown'); return
        
        await event.edit("**• 🎵 جاري تحويل الفيديو إلى صوت...**", parse_mode='markdown')
        video_path = audio_path = None
        
        try:
            # تحميل الفيديو
            video_path = os.path.join(TEMP_DIR, f"video_{phone}_{int(time.time())}.mp4")
            await client.download_media(reply, video_path)
            
            # استخراج اسم الفيديو الأصلي
            original_name = "فيديو محول"
            if reply.video:
                # لو فيه كابشن
                if hasattr(reply, 'message') and reply.message:
                    original_name = reply.message[:100]
            elif reply.document:
                # لو ملف
                for attr in reply.document.attributes:
                    if hasattr(attr, 'file_name') and attr.file_name:
                        original_name = os.path.splitext(attr.file_name)[0]
                        break
            
            # تحويل الفيديو لصوت
            audio_info = await asyncio.get_event_loop().run_in_executor(_DOWNLOAD_EXECUTOR, convert_video_to_audio, video_path, TEMP_DIR)
            audio_path = audio_info['path']
            
            # كابشن زي نظام .فيد و .يوت بالضبط
            title = clean_filename(original_name)
            if len(title) > 55: title = title[:52] + '...'
            dur = audio_info['duration_str']
            caption = f"{title}\n• {dur} | ᥲᥙძᎥ᥆"
            
            await client.send_file(event.chat_id, audio_path,
                                   caption=caption,
                                   attributes=[DocumentAttributeAudio(duration=int(audio_info['duration']), title=title, performer='محول من فيديو')],
                                   supports_streaming=True)
            await event.delete()
        except Exception as e:
            await event.edit(f"**• ❌ {str(e)[:200]}**", parse_mode='markdown')
        finally:
            safe_remove(video_path); safe_remove(audio_path)

    # ============== أمر .نسخ - المعدل ==============
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.نسخ$'))
    async def transcribe_voice(event):
        if not event.is_reply: await event.edit("**• ❌ يرجى الرد على رسالة صوتية أو فيديو**", parse_mode='markdown'); return
        
        reply = await event.get_reply_message()
        
        # قبول الصوت والفيديو
        if not (reply.voice or reply.audio or reply.video):
            await event.edit("**• ❌ يرجى الرد على رسالة صوتية أو فيديو**", parse_mode='markdown'); return
        
        if not SR_AVAILABLE: await event.edit("**• ❌ مكتبة SpeechRecognition غير مثبتة**", parse_mode='markdown'); return
        
        await event.edit("**• 🎤 جاري تحويل المقطع إلى نص...**", parse_mode='markdown')
        media_path = wav_path = None
        
        try:
            # تحميل الميديا
            media_path = os.path.join(TEMP_DIR, f"media_{phone}_{int(time.time())}.ogg")
            await client.download_media(reply, media_path)
            
            if not os.path.exists(media_path) or os.path.getsize(media_path) < 100:
                raise ValueError("فشل تحميل الملف")
            
            # تحويل إلى WAV
            wav_path = media_path.replace('.ogg', '.wav').replace('.mp4', '.wav')
            result = subprocess.run(
                ['ffmpeg', '-i', media_path, '-ac', '1', '-ar', '16000', '-sample_fmt', 's16', wav_path],
                capture_output=True, timeout=30
            )
            
            if result.returncode != 0 or not os.path.exists(wav_path):
                raise ValueError("فشل تحويل الصوت")
            
            recognizer = sr.Recognizer()
            with sr.AudioFile(wav_path) as source:
                audio_data = recognizer.record(source)
            
            text = None
            for lang in ['ar-AR', 'en-US']:
                try: text = recognizer.recognize_google(audio_data, language=lang); break
                except: continue
            
            if text: await event.edit(f"**📝 النص:**\n{text}")
            else: await event.edit("**• ❌ لم يتم التعرف على أي نص**")
                
        except subprocess.CalledProcessError as e:
            error_text = e.stderr.decode()[:100] if e.stderr else str(e)
            await event.edit(f"**• ❌ فشل التحويل: {error_text}**")
        except Exception as e:
            await event.edit(f"**• ❌ {str(e)[:150]}**")
        finally:
            safe_remove(media_path); safe_remove(wav_path)

    # ============== أمر .استيك ==============
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.استيك$'))
    async def photo_to_sticker(event):
        if not event.is_reply or not PIL_AVAILABLE: await event.edit("**• ❌ يرجى الرد على صورة**", parse_mode='markdown'); return
        reply = await event.get_reply_message()
        if not reply.photo: await event.edit("**• ❌ الرد على صورة فقط**", parse_mode='markdown'); return
        await event.edit("**• 🔄 جاري التحويل...**", parse_mode='markdown')
        img_path = stick_path = None
        try:
            img_path = os.path.join(TEMP_DIR, f"img_{phone}_{int(time.time())}.jpg")
            await client.download_media(reply, img_path)
            stick_path = img_path.replace('.jpg', '.webp')
            im = Image.open(img_path).convert("RGBA")
            im.thumbnail((512, 512), Image.LANCZOS)
            im.save(stick_path, "WEBP", quality=80)
            await client.send_file(event.chat_id, stick_path, force_document=False)
            await event.delete()
        except Exception as e: await event.edit(f"**• ❌ {str(e)[:150]}**", parse_mode='markdown')
        finally: safe_remove(img_path); safe_remove(stick_path)

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.بيك$'))
    async def sticker_to_photo(event):
        if not event.is_reply or not PIL_AVAILABLE: await event.edit("**• ❌ يرجى الرد على استيكر**", parse_mode='markdown'); return
        reply = await event.get_reply_message()
        if not reply.sticker: await event.edit("**• ❌ الرد على استيكر فقط**", parse_mode='markdown'); return
        await event.edit("**• 🔄 جاري التحويل...**", parse_mode='markdown')
        stick_path = img_path = None
        try:
            stick_path = os.path.join(TEMP_DIR, f"sticker_{phone}_{int(time.time())}.webp")
            await client.download_media(reply, stick_path)
            img_path = stick_path.replace('.webp', '.png')
            Image.open(stick_path).convert("RGBA").save(img_path, "PNG")
            await client.send_file(event.chat_id, img_path)
            await event.delete()
        except Exception as e: await event.edit(f"**• ❌ {str(e)[:150]}**", parse_mode='markdown')
        finally: safe_remove(stick_path); safe_remove(img_path)

    # ============== أمر .بن - المحسن ==============
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.بن (.+)'))
    async def image_search(event):
        query = event.pattern_match.group(1).strip()
        
        if query.startswith('http'):
            await event.edit("**• 📷 جاري تحميل الصورة...**", parse_mode='markdown')
            filepath = await asyncio.get_event_loop().run_in_executor(_DOWNLOAD_EXECUTOR, download_image_direct, query, TEMP_DIR)
            if filepath:
                await client.send_file(event.chat_id, filepath)
                await event.delete()
                safe_remove(filepath)
            else: await event.edit("**• ❌ فشل تحميل الصورة**", parse_mode='markdown')
            return
        
        await event.edit(f"**• 🔍 جاري البحث عن '{query}' في 3 محركات...**", parse_mode='markdown')
        urls = await asyncio.get_event_loop().run_in_executor(_DOWNLOAD_EXECUTOR, search_all_images, query, 10)
        
        if not urls:
            await event.edit(f"**• ❌ لم يتم العثور على صور لـ '{query}'**\n**• جرب كلمات بحث أدق أو اسم مختلف**", parse_mode='markdown')
            return
        
        await event.edit(f"**• ✅ تم العثور على {len(urls)} صورة**\n**• 📥 جاري تحميل وعرض الصور...**", parse_mode='markdown')
        
        success = 0
        for i, url in enumerate(urls[:5], 1):
            try:
                filepath = await asyncio.get_event_loop().run_in_executor(_DOWNLOAD_EXECUTOR, download_image_direct, url, TEMP_DIR)
                if filepath:
                    await client.send_file(event.chat_id, filepath)
                    success += 1
                    safe_remove(filepath)
                    if success < min(len(urls), 5):
                        await event.edit(f"**• 📤 تم إرسال {success} من {min(len(urls), 5)} صورة...**", parse_mode='markdown')
                await asyncio.sleep(0.3)
            except Exception as e:
                logger.error(f"Failed image {i}: {e}")
                continue
        
        if success > 0: await event.delete()
        else: await event.edit(f"**• ❌ فشل تحميل صور '{query}'**\n**• جرب مرة أخرى**", parse_mode='markdown')

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.المساحة$'))
    async def space_check(event):
        await event.edit(f"**📊 المساحة:** {get_free_space_mb():.1f} MB", parse_mode='markdown')

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.تنظيف$'))
    async def force_clean(event):
        c = clean_temp_files()
        await event.edit(f"**✅ تم تنظيف {c} ملف\n📊 المساحة: {get_free_space_mb():.1f} MB**", parse_mode='markdown')

    # ============== التقليد ==============
    @client.on(events.NewMessage(incoming=True))
    async def auto_taqleed(event):
        if event.sender_id in taqleed_users.get(phone, {}) and event.text and not event.text.startswith('.'):
            await asyncio.sleep(0.3)
            try: await event.reply(event.text)
            except: pass

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.تقليد$'))
    async def taq(event):
        target = (await event.get_reply_message()).sender_id if event.is_reply else event.chat_id if event.is_private else None
        if target: taqleed_users[phone][target] = True; await event.edit("**• ✅ تم التقليد**", parse_mode='markdown')

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.غ تقليد$'))
    async def notaq(event):
        target = (await event.get_reply_message()).sender_id if event.is_reply else event.chat_id if event.is_private else None
        if target and target in taqleed_users.get(phone, {}): del taqleed_users[phone][target]; await event.edit("**• ✅ تم فك التقليد**", parse_mode='markdown')

    # ============== الانتحال ==============
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.انتحال$'))
    async def ent7al(event):
        track_command(phone, ".انتحال")
        await event.edit("**• 🔄 جاري الانتحال...**", parse_mode='markdown')
        target_user = None
        if event.is_reply:
            try: target_user = await client.get_entity((await event.get_reply_message()).sender_id)
            except: pass
        elif event.is_private:
            try: target_user = await client.get_entity(event.chat_id)
            except: pass
        if not target_user: await event.edit("**• ❌ فشل**", parse_mode='markdown'); return
        target_info = await get_user_info_full(client, target_user.id)
        if not target_info: await event.edit("**• ❌ فشل**", parse_mode='markdown'); return
        me = await client.get_me(); client_me[phone] = me
        original = {'first_name': me.first_name or '', 'last_name': me.last_name or '', 'about': '', 'added_photo_id': None}
        try:
            fu = await client(GetFullUserRequest('me'))
            if fu.full_user.about: original['about'] = fu.full_user.about
        except: pass
        try:
            await client(UpdateProfileRequest(first_name=target_info['first_name'], last_name=target_info['last_name']))
            await asyncio.sleep(1)
        except FloodWaitError as e:
            await asyncio.sleep(e.seconds)
            try: await client(UpdateProfileRequest(first_name=target_info['first_name'], last_name=target_info['last_name']))
            except: pass
        except: pass
        try: await client(UpdateProfileRequest(about=target_info['bio'][:70] if target_info['bio'] else ''))
        except: pass
        photo_ok, added_id = await change_profile_photo(client, target_user.id, phone)
        if photo_ok and added_id: original['added_photo_id'] = added_id
        ent7al_original[phone] = original; ent7al_users[phone] = True
        await event.edit("**• ✅ تم الانتحال**", parse_mode='markdown')

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.الغاء انتحال$'))
    async def unent7al(event):
        if not ent7al_users.get(phone): await event.edit("**• ❌ لا يوجد انتحال**", parse_mode='markdown'); return
        original = ent7al_original[phone]
        try: await client(UpdateProfileRequest(first_name=original.get('first_name',''), last_name=original.get('last_name','')))
        except: pass
        if original.get('added_photo_id'):
            try: await client(DeletePhotosRequest(id=[InputPhoto(id=original['added_photo_id'], access_hash=0, file_reference=b'')]))
            except: pass
        try: await client(UpdateProfileRequest(about=original.get('about','')))
        except: pass
        ent7al_users[phone] = False; ent7al_original[phone] = {}
        await event.edit("**• ✅ تم إلغاء الانتحال**", parse_mode='markdown')

    # ============== مراقبة الخاص ==============
    @client.on(events.NewMessage(incoming=True, func=lambda e: e.is_private and not e.out))
    async def cache_message(event):
        if event.sender_id == (await client.get_me()).id: return
        message_cache.setdefault(event.chat_id, {})[event.id] = event.text or "<وسائط>"

    @client.on(events.MessageEdited(incoming=True, func=lambda e: e.is_private and not e.out))
    async def notify_edit(event):
        if event.sender_id == (await client.get_me()).id: return
        user = await event.get_sender()
        name = user.first_name or ""; name += f" {user.last_name}" if user.last_name else ""
        old = message_cache.get(event.chat_id, {}).get(event.id, "نص غير معروف")
        await client.send_message("me", f"**📝 {name} عدل رسالة**\n**من:** {old}\n**إلى:** {event.text or '<وسائط>'}")
        message_cache.setdefault(event.chat_id, {})[event.id] = event.text or "<وسائط>"

    @client.on(events.MessageDeleted(incoming=True, func=lambda e: e.is_private and not e.out))
    async def notify_delete(event):
        for chat_id, msg_ids in event.deleted_ids.items():
            for msg_id in msg_ids:
                if chat_id in message_cache and msg_id in message_cache[chat_id]:
                    text = message_cache[chat_id][msg_id]
                    user_name = "مستخدم"
                    try: 
                        chat = await client.get_entity(chat_id)
                        user_name = chat.first_name or "مستخدم"
                    except: pass
                    await client.send_message("me", f"**🗑️ {user_name} حذف رسالة**\n**{text}**")
                    del message_cache[chat_id][msg_id]

    # ============== تنظيف دوري ==============
    async def auto_cleanup():
        while True:
            await asyncio.sleep(1800)
            if get_free_space_mb() < MIN_FREE_SPACE_MB * 2:
                clean_temp_files()
    
    asyncio.create_task(auto_cleanup())

    logger.info(f"✅ جميع الأوامر جاهزة لـ {phone}")
