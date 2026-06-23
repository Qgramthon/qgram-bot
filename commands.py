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
from datetime import datetime
from telethon import events, functions, types, Button
from telethon.errors import (
    FloodWaitError, ChatAdminRequiredError, UserPrivacyRestrictedError,
    PeerFloodError, UserBannedInChannelError, UserNotMutualContactError,
    UserChannelsTooMuchError, UserKickedError, UserAlreadyParticipantError,
    UserNotParticipantError, ChatNotModifiedError
)
from telethon.tl.functions.account import UpdateProfileRequest
from telethon.tl.functions.photos import UploadProfilePhotoRequest, DeletePhotosRequest
from telethon.tl.functions.users import GetFullUserRequest
from telethon.tl.functions.channels import (
    InviteToChannelRequest, EditAdminRequest, EditBannedRequest,
    GetParticipantsRequest, EditPhotoRequest
)
from telethon.tl.functions.messages import (
    AddChatUserRequest, GetDialogsRequest, DeleteChatUserRequest,
    DeleteHistoryRequest, EditChatDefaultBannedRightsRequest
)
from telethon.tl.functions.contacts import AddContactRequest, DeleteContactsRequest, BlockRequest, UnblockRequest, GetBlockedRequest
from telethon.tl.types import (
    InputPhoto, DocumentAttributeAudio, DocumentAttributeVideo,
    InputPeerUser, InputPeerChat, InputPeerChannel, InputPeerEmpty,
    ChatBannedRights, ChatAdminRights, ChannelParticipantsAdmins,
    ChannelParticipantsSearch, UserStatusOnline, UserStatusOffline,
    ChannelParticipantCreator, ChannelParticipantAdmin
)
from telethon.tl.functions.phone import CreateGroupCallRequest
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

_DOWNLOAD_EXECUTOR = ThreadPoolExecutor(max_workers=5, thread_name_prefix="dl")
message_cache = {}
active_animations = {}
MIN_FREE_SPACE_MB = 50

text_format_mode = {}
tagging_active = {}
adding_members = {}
stalking_active = {}

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

# ============== دوال الزخرفة المتكاملة ==============
DECORATION_STYLES = {
    'style1': {
        'A':'𝗔','B':'𝗕','C':'𝗖','D':'𝗗','E':'𝗘','F':'𝗙','G':'𝗚','H':'𝗛','I':'𝗜','J':'𝗝','K':'𝗞','L':'𝗟','M':'𝗠',
        'N':'𝗡','O':'𝗢','P':'𝗣','Q':'𝗤','R':'𝗥','S':'𝗦','T':'𝗧','U':'𝗨','V':'𝗩','W':'𝗪','X':'𝗫','Y':'𝗬','Z':'𝗭',
        'a':'𝗮','b':'𝗯','c':'𝗰','d':'𝗱','e':'𝗲','f':'𝗳','g':'𝗴','h':'𝗵','i':'𝗶','j':'𝗷','k':'𝗸','l':'𝗹','m':'𝗺',
        'n':'𝗻','o':'𝗼','p':'𝗽','q':'𝗾','r':'𝗿','s':'𝘀','t':'𝘁','u':'𝘂','v':'𝘃','w':'𝘄','x':'𝘅','y':'𝘆','z':'𝘇',
    },
    'style2': {
        'A':'𝐀','B':'𝐁','C':'𝐂','D':'𝐃','E':'𝐄','F':'𝐅','G':'𝐆','H':'𝐇','I':'𝐈','J':'𝐉','K':'𝐊','L':'𝐋','M':'𝐌',
        'N':'𝐍','O':'𝐎','P':'𝐏','Q':'𝐐','R':'𝐑','S':'𝐒','T':'𝐓','U':'𝐔','V':'𝐕','W':'𝐖','X':'𝐗','Y':'𝐘','Z':'𝐙',
        'a':'𝐚','b':'𝐛','c':'𝐜','d':'𝐝','e':'𝐞','f':'𝐟','g':'𝐠','h':'𝐡','i':'𝐢','j':'𝐣','k':'𝐤','l':'𝐥','m':'𝐦',
        'n':'𝐧','o':'𝐨','p':'𝐩','q':'𝐪','r':'𝐫','s':'𝐬','t':'𝐭','u':'𝐮','v':'𝐯','w':'𝐰','x':'𝐱','y':'𝐲','z':'𝐳',
    },
    'style3': {
        'A':'𝔸','B':'𝔹','C':'ℂ','D':'𝔻','E':'𝔼','F':'𝔽','G':'𝔾','H':'ℍ','I':'𝕀','J':'𝕁','K':'𝕂','L':'𝕃','M':'𝕄',
        'N':'ℕ','O':'𝕆','P':'ℙ','Q':'ℚ','R':'ℝ','S':'𝕊','T':'𝕋','U':'𝕌','V':'𝕍','W':'𝕎','X':'𝕏','Y':'𝕐','Z':'ℤ',
        'a':'𝕒','b':'𝕓','c':'𝕔','d':'𝕕','e':'𝕖','f':'𝕗','g':'𝕘','h':'𝕙','i':'𝕚','j':'𝕛','k':'𝕜','l':'𝕝','m':'𝕞',
        'n':'𝕟','o':'𝕠','p':'𝕡','q':'𝕢','r':'𝕣','s':'𝕤','t':'𝕥','u':'𝕦','v':'𝕧','w':'𝕨','x':'𝕩','y':'𝕪','z':'𝕫',
    },
    'style4': {
        'A':'ᴀ','B':'ʙ','C':'ᴄ','D':'ᴅ','E':'ᴇ','F':'ꜰ','G':'ɢ','H':'ʜ','I':'ɪ','J':'ᴊ','K':'ᴋ','L':'ʟ','M':'ᴍ',
        'N':'ɴ','O':'ᴏ','P':'ᴘ','Q':'ǫ','R':'ʀ','S':'ꜱ','T':'ᴛ','U':'ᴜ','V':'ᴠ','W':'ᴡ','X':'x','Y':'ʏ','Z':'ᴢ',
        'a':'ᴀ','b':'ʙ','c':'ᴄ','d':'ᴅ','e':'ᴇ','f':'ꜰ','g':'ɢ','h':'ʜ','i':'ɪ','j':'ᴊ','k':'ᴋ','l':'ʟ','m':'ᴍ',
        'n':'ɴ','o':'ᴏ','p':'ᴘ','q':'ǫ','r':'ʀ','s':'ꜱ','t':'ᴛ','u':'ᴜ','v':'ᴠ','w':'ᴡ','x':'x','y':'ʏ','z':'ᴢ',
    },
    'style5': {
        'A':'ᗩ','B':'ᗷ','C':'ᑕ','D':'ᗞ','E':'ᗴ','F':'ᖴ','G':'Ǥ','H':'ᕼ','I':'Ꮖ','J':'ᒍ','K':'ᛕ','L':'ᒪ','M':'ᗰ',
        'N':'ᑎ','O':'Ꭷ','P':'ᑭ','Q':'ᑫ','R':'ᖇ','S':'ᔑ','T':'Ꮏ','U':'ᑌ','V':'ᐯ','W':'ᗯ','X':'᙭','Y':'Ꭹ','Z':'ᘔ',
        'a':'ᗩ','b':'ᗷ','c':'ᑕ','d':'ᗞ','e':'ᗴ','f':'ᖴ','g':'Ǥ','h':'ᕼ','i':'Ꮖ','j':'ᒍ','k':'ᛕ','l':'ᒪ','m':'ᗰ',
        'n':'ᑎ','o':'Ꭷ','p':'ᑭ','q':'ᑫ','r':'ᖇ','s':'ᔑ','t':'Ꮏ','u':'ᑌ','v':'ᐯ','w':'ᗯ','x':'᙭','y':'Ꭹ','z':'ᘔ',
    },
    'style6': {
        'A':'₳','B':'฿','C':'₵','D':'Đ','E':'Ɇ','F':'₣','G':'₲','H':'Ⱨ','I':'ł','J':'J','K':'₭','L':'Ⱡ','M':'₥',
        'N':'₦','O':'Ø','P':'₱','Q':'Q','R':'Ɽ','S':'₴','T':'₮','U':'Ʉ','V':'V','W':'₩','X':'Ӿ','Y':'Ɏ','Z':'Ⱬ',
        'a':'₳','b':'฿','c':'₵','d':'Đ','e':'Ɇ','f':'₣','g':'₲','h':'Ⱨ','i':'ł','j':'J','k':'₭','l':'Ⱡ','m':'₥',
        'n':'₦','o':'Ø','p':'₱','q':'Q','r':'Ɽ','s':'₴','t':'₮','u':'Ʉ','v':'V','w':'₩','x':'Ӿ','y':'Ɏ','z':'Ⱬ',
    },
    'style7': {
        'A':'Д','B':'Б','C':'Ͼ','D':'Ԃ','E':'Є','F':'Ғ','G':'Ԍ','H':'Ҥ','I':'Ї','J':'Ј','K':'Ҡ','L':'Լ','M':'Ӎ',
        'N':'И','O':'Ф','P':'Ҏ','Q':'Ǫ','R':'Я','S':'Ϩ','T':'Г','U':'Ц','V':'Ѷ','W':'Ш','X':'Ж','Y':'Ұ','Z':'Ȥ',
        'a':'д','b':'б','c':'ϲ','d':'ԁ','e':'є','f':'Ғ','g':'Ԍ','h':'ҥ','i':'ї','j':'ј','k':'ҡ','l':'Ӏ','m':'ӎ',
        'n':'и','o':'ф','p':'ҏ','q':'ǫ','r':'я','s':'ϩ','t':'г','u':'ц','v':'ѷ','w':'ш','x':'ж','y':'ұ','z':'ȥ',
    },
    'style8': {
        'a':'ᥲ','b':'ᑲ','c':'ᥴ','d':'ძ','e':'ꫀ','f':'ꓝ','g':'Ԍ','h':'ɦ','i':'Ꭵ','j':'ȷ','k':'κ','l':'ᥣ','m':'ꪔ',
        'n':'ꪀ','o':'᥆','p':'ρ','q':'Ԛ','r':'ᖇ','s':'᥉','t':'ƚ','u':'ᥙ','v':'᥎','w':'᭙','x':'᥊','y':'𝛄','z':'ɀ',
    },
}

def apply_decoration(text, style_name):
    """تطبيق الزخرفة على النص الإنجليزي فقط"""
    if style_name not in DECORATION_STYLES:
        return text
    
    style_map = DECORATION_STYLES[style_name]
    result = ''
    for char in text:
        if char in style_map:
            result += style_map[char]
        else:
            result += char
    return result

# ============== دوال الترجمة ==============
def translate_text(text: str) -> str:
    """ترجمة النص بين العربية والإنجليزية"""
    try:
        if re.search(r'[\u0600-\u06FF]', text):
            source, target = 'ar', 'en'
        else:
            source, target = 'en', 'ar'
        
        url = f"https://translate.googleapis.com/translate_a/single?client=gtx&sl={source}&tl={target}&dt=t&q={quote(text)}"
        resp = requests.get(url, timeout=15)
        if resp.status_code == 200:
            result = json.loads(resp.text)
            translated = ''.join([s[0] for s in result[0] if s[0]])
            return translated
    except: pass
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

HACK_MESSAGES = [
    "🔓 **جاري فتح المنافذ...**",
    "📡 **تم الاتصال بالخادم الرئيسي**",
    "🔍 **جاري فحص الثغرات الأمنية...**",
    "💉 **تم حقن الكود الخبيث**",
    "🔑 **جاري فك تشفير كلمة المرور...**",
    "📂 **تم الوصول لقاعدة البيانات**",
    "📊 **جاري سحب المعلومات...**",
    "🛡️ **تم تجاوز جدار الحماية**",
    "✅ **تم الاختراق بنجاح!**",
    "⚠️ **النظام تحت السيطرة**"
]

KILL_METHODS = [
    ["🔪 **جاري الطعن بالسكين...**", "🩸 **تم الطعن في القلب**", "☠️ **الضحية تنزف بشدة...**"],
    ["🔫 **جاري التصويب بالمسدس...**", "💥 **تم إطلاق النار**", "🎯 **إصابة مباشرة في الرأس**"],
    ["🚗 **جاري الدهس بالسيارة...**", "💨 **السيارة مسرعة نحو الهدف**", "💀 **تم الدهس بنجاح**"],
    ["🏢 **جاري الدفع من مبنى مرتفع...**", "🪂 **لا توجد مظلة نجاة**", "💥 **تم السقوط من ارتفاع 50 طابق**"],
    ["⚡ **جاري التكهرب...**", "🔌 **تم توصيل التيار**", "⚡ **صعق كهربائي مميت**"],
    ["💣 **جاري التفجير...**", "🔥 **تم إشعال الفتيل**", "💥 **انفجار هائل**"],
    ["🧪 **جاري التسميم...**", "☕ **تم وضع السم في المشروب**", "🤢 **السم ينتشر في الجسد**"],
    ["🌊 **جاري الإغراق...**", "🏊 **الضحية لا تجيد السباحة**", "🫧 **تم الإغراق في المياه العميقة**"],
]

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

# ============== دوال البحث عن الصور ==============
def search_images_google_serpapi(query: str, limit: int = 10) -> list:
    images = []
    try:
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
    
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        search_url = f"https://www.google.com/search?q={quote(query)}&tbm=isch&hl=en&safe=off"
        resp = requests.get(search_url, headers=headers, timeout=15)
        if resp.status_code == 200:
            matches = re.findall(r'"ou":"(https?://[^"]+)"', resp.text)
            for url in matches:
                if url.startswith('http') and not any(s in url.lower() for s in ['google', 'gstatic', '/favicon']):
                    images.append(url)
                    if len(images) >= limit: break
    except: pass
    return images

def search_images_bing_api(query: str, limit: int = 10) -> list:
    images = []
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        url = f"https://www.bing.com/images/search?q={quote(query)}&first=1&count={limit}"
        resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code == 200:
            matches = re.findall(r'murl&quot;:&quot;(https?://[^&]+)&quot;', resp.text)
            for url in matches:
                if 'bing.com' not in url.lower():
                    images.append(url)
                    if len(images) >= limit: break
    except: pass
    return images

def search_images_ddg(query: str, limit: int = 10) -> list:
    images = []
    try:
        from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            results = list(ddgs.images(query, max_results=limit))
            images = [img["image"] for img in results if img.get("image")]
    except: pass
    return images

def search_all_images(query: str, limit: int = 5) -> list:
    all_images = []
    engines = [
        ("DuckDuckGo", search_images_ddg),
        ("Google", search_images_google_serpapi),
        ("Bing", search_images_bing_api),
    ]
    for name, func in engines:
        try:
            results = func(query, limit=10)
            if results: all_images.extend(results)
        except: continue
    
    seen = set()
    unique = []
    blocked = ['icon', 'favicon', 'avatar', 'logo', 'thumb/32', 'thumb/64', 'gstatic.com']
    for url in all_images:
        url = url.strip()
        if not url.startswith('http'): continue
        if any(b in url.lower() for b in blocked): continue
        if url not in seen:
            seen.add(url)
            unique.append(url)
            if len(unique) >= limit: break
    
    if not unique and ' ' in query:
        parts = query.split()
        if len(parts) >= 2:
            return search_all_images(' '.join(parts[:2]), limit)
    
    return unique[:limit]

def download_image_direct(url: str, out_dir: str) -> str:
    try:
        headers = {'User-Agent': 'Mozilla/5.0', 'Referer': 'https://www.google.com/'}
        resp = requests.get(url, headers=headers, stream=True, timeout=30, allow_redirects=True)
        if resp.status_code != 200: return None
        content_type = resp.headers.get('content-type', '').lower()
        ext = '.jpg'
        if 'png' in content_type: ext = '.png'
        elif 'webp' in content_type: ext = '.webp'
        elif 'gif' in content_type: ext = '.gif'
        
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
        if size < 2048:
            safe_remove(filepath)
            return None
        return filepath
    except: return None

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
            probe = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', video_path], capture_output=True, timeout=10)
            if probe.returncode == 0: duration = float(probe.stdout.decode().strip())
        except: pass
        return {'path': audio_path, 'duration': duration, 'duration_str': format_duration(duration)}
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

async def resolve_user(event, client):
    if event.is_reply:
        reply = await event.get_reply_message()
        try: return await client.get_entity(reply.sender_id)
        except: pass
    text = event.text.split()
    if len(text) >= 2:
        username = text[1].strip('@')
        try: return await client.get_entity(username)
        except: pass
    return None

# ============== دالة قياس السرعة المحسنة ==============
async def measure_speed():
    """قياس سرعة النت بطريقة دقيقة"""
    try:
        # قياس البنق
        start = time.time()
        resp = requests.get("https://api.telegram.org", timeout=10)
        ping = int((time.time() - start) * 1000)
        
        # قياس سرعة التحميل باستخدام ملف صغير
        start = time.time()
        resp = requests.get("http://ipv4.download.thinkbroadband.com/5MB.zip", stream=True, timeout=30)
        size = 0
        for chunk in resp.iter_content(8192):
            size += len(chunk)
            elapsed = time.time() - start
            if elapsed > 8 or size > 5 * 1024 * 1024:
                break
        
        if elapsed > 0:
            speed_mbps = (size * 8) / (elapsed * 1000000)
        else:
            speed_mbps = 0
        
        return {
            'ping': ping,
            'speed': speed_mbps,
            'success': True
        }
    except:
        return {'success': False}

# ============== إعداد المعالجات ==============
async def setup_handlers(client, phone):
    
    if phone not in muted_users: muted_users[phone] = {}
    if phone not in taqleed_users: taqleed_users[phone] = {}
    if phone not in ent7al_users: ent7al_users[phone] = False
    if phone not in ent7al_original: ent7al_original[phone] = {}
    if phone not in text_format_mode: text_format_mode[phone] = None
    if phone not in tagging_active: tagging_active[phone] = False
    if phone not in stalking_active: stalking_active[phone] = False

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

    # ============== أمر .خفي / .غ خفي ==============
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.خفي$'))
    async def hide_name(event):
        try:
            await client(UpdateProfileRequest(first_name='ㅤ', last_name=''))
            await event.edit("**• ✅ تم إخفاء الاسم**")
        except Exception as e:
            await event.edit(f"**• ❌ فشل: {str(e)[:100]}**")

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.غ خفي$'))
    async def unhide_name(event):
        if phone in client_me:
            original = client_me[phone]
            try:
                await client(UpdateProfileRequest(first_name=original.first_name or '', last_name=original.last_name or ''))
                await event.edit("**• ✅ تم استرجاع الاسم**")
            except:
                await event.edit("**• ❌ فشل استرجاع الاسم**")
        else:
            await event.edit("**• ❌ لم يتم حفظ الاسم الأصلي**")

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

    # ============== أوامر المزاح - المحسنة ==============
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.تهكير$'))
    async def fake_hack(event):
        if not event.is_reply: await event.edit("**• ❌ يرجى الرد على شخص**", parse_mode='markdown'); return
        reply = await event.get_reply_message()
        user = await client.get_entity(reply.sender_id)
        name = user.first_name or "المستخدم"
        
        for msg in HACK_MESSAGES:
            await event.edit(msg, parse_mode='markdown')
            await asyncio.sleep(1.2)
        await event.edit(f"**✅ تمت السيطرة على حساب {name} بالكامل**", parse_mode='markdown')

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.قتل$'))
    async def fake_kill(event):
        if not event.is_reply: await event.edit("**• ❌ يرجى الرد على شخص**", parse_mode='markdown'); return
        reply = await event.get_reply_message()
        user = await client.get_entity(reply.sender_id)
        name = user.first_name or "المستخدم"
        
        # اختيار طريقة قتل عشوائية
        method = random.choice(KILL_METHODS)
        
        for msg in method:
            await event.edit(f"**{msg}**", parse_mode='markdown')
            await asyncio.sleep(1.5)
        await event.edit(f"**💀 تم القضاء على {name}**\n**🪦 إنا لله وإنا إليه راجعون**", parse_mode='markdown')

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

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.صوت$'))
    async def video_to_audio(event):
        if not event.is_reply: await event.edit("**• ❌ يرجى الرد على فيديو**", parse_mode='markdown'); return
        reply = await event.get_reply_message()
        if not (reply.video or reply.document): await event.edit("**• ❌ يرجى الرد على فيديو**", parse_mode='markdown'); return
        await event.edit("**• 🎵 جاري تحويل الفيديو إلى صوت...**", parse_mode='markdown')
        video_path = audio_path = None
        try:
            video_path = os.path.join(TEMP_DIR, f"video_{phone}_{int(time.time())}.mp4")
            await client.download_media(reply, video_path)
            original_name = "فيديو محول"
            if reply.video and hasattr(reply, 'message') and reply.message: original_name = reply.message[:100]
            elif reply.document:
                for attr in reply.document.attributes:
                    if hasattr(attr, 'file_name') and attr.file_name:
                        original_name = os.path.splitext(attr.file_name)[0]; break
            audio_info = await asyncio.get_event_loop().run_in_executor(_DOWNLOAD_EXECUTOR, convert_video_to_audio, video_path, TEMP_DIR)
            audio_path = audio_info['path']
            title = clean_filename(original_name)
            if len(title) > 55: title = title[:52] + '...'
            caption = f"{title}\n• {audio_info['duration_str']} | ᥲᥙძᎥ᥆"
            await client.send_file(event.chat_id, audio_path, caption=caption,
                                   attributes=[DocumentAttributeAudio(duration=int(audio_info['duration']), title=title, performer='محول من فيديو')],
                                   supports_streaming=True)
            await event.delete()
        except Exception as e: await event.edit(f"**• ❌ {str(e)[:200]}**", parse_mode='markdown')
        finally: safe_remove(video_path); safe_remove(audio_path)

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.نسخ$'))
    async def transcribe_voice(event):
        if not event.is_reply: await event.edit("**• ❌ يرجى الرد على رسالة صوتية أو فيديو**", parse_mode='markdown'); return
        reply = await event.get_reply_message()
        if not (reply.voice or reply.audio or reply.video): await event.edit("**• ❌ يرجى الرد على رسالة صوتية أو فيديو**", parse_mode='markdown'); return
        if not SR_AVAILABLE: await event.edit("**• ❌ مكتبة SpeechRecognition غير مثبتة**", parse_mode='markdown'); return
        await event.edit("**• 🎤 جاري تحويل المقطع إلى نص...**", parse_mode='markdown')
        media_path = wav_path = None
        try:
            media_path = os.path.join(TEMP_DIR, f"media_{phone}_{int(time.time())}.ogg")
            await client.download_media(reply, media_path)
            wav_path = media_path.replace('.ogg', '.wav').replace('.mp4', '.wav')
            subprocess.run(['ffmpeg', '-i', media_path, '-ac', '1', '-ar', '16000', '-sample_fmt', 's16', wav_path], capture_output=True, timeout=30)
            recognizer = sr.Recognizer()
            with sr.AudioFile(wav_path) as source: audio_data = recognizer.record(source)
            text = None
            for lang in ['ar-AR', 'en-US']:
                try: text = recognizer.recognize_google(audio_data, language=lang); break
                except: continue
            await event.edit(f"**📝 النص:**\n{text}" if text else "**• ❌ لم يتم التعرف**")
        except Exception as e: await event.edit(f"**• ❌ {str(e)[:150]}**")
        finally: safe_remove(media_path); safe_remove(wav_path)

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
            im = Image.open(img_path).convert("RGBA"); im.thumbnail((512, 512), Image.LANCZOS); im.save(stick_path, "WEBP", quality=80)
            await client.send_file(event.chat_id, stick_path, force_document=False); await event.delete()
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
            stick_path = os.path.join(TEMP_DIR, f"sticker_{phone}_{int(time.time())}.webp"); await client.download_media(reply, stick_path)
            img_path = stick_path.replace('.webp', '.png'); Image.open(stick_path).convert("RGBA").save(img_path, "PNG")
            await client.send_file(event.chat_id, img_path); await event.delete()
        except Exception as e: await event.edit(f"**• ❌ {str(e)[:150]}**", parse_mode='markdown')
        finally: safe_remove(stick_path); safe_remove(img_path)

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.بن (.+)'))
    async def image_search(event):
        query = event.pattern_match.group(1).strip()
        if query.startswith('http'):
            await event.edit("**• 📷 جاري تحميل الصورة...**", parse_mode='markdown')
            filepath = await asyncio.get_event_loop().run_in_executor(_DOWNLOAD_EXECUTOR, download_image_direct, query, TEMP_DIR)
            if filepath: await client.send_file(event.chat_id, filepath); await event.delete(); safe_remove(filepath)
            else: await event.edit("**• ❌ فشل تحميل الصورة**", parse_mode='markdown')
            return
        await event.edit(f"**• 🔍 جاري البحث عن '{query}'...**", parse_mode='markdown')
        urls = await asyncio.get_event_loop().run_in_executor(_DOWNLOAD_EXECUTOR, search_all_images, query, 15)
        if not urls: await event.edit(f"**• ❌ لم يتم العثور على صور**", parse_mode='markdown'); return
        await event.edit(f"**• ✅ تم العثور على {len(urls)} صورة**", parse_mode='markdown')
        success = 0
        for url in urls[:5]:
            try:
                filepath = await asyncio.get_event_loop().run_in_executor(_DOWNLOAD_EXECUTOR, download_image_direct, url, TEMP_DIR)
                if filepath: await client.send_file(event.chat_id, filepath); success += 1; safe_remove(filepath)
                await asyncio.sleep(0.3)
            except: continue
        if success > 0: await event.delete()
        else: await event.edit("**• ❌ فشل تحميل الصور**", parse_mode='markdown')

    # ============== أمر .ترجم - يدعم الربلاي ==============
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.ترجم(?: (.+))?$'))
    async def translate_cmd(event):
        text = None
        if event.is_reply:
            reply = await event.get_reply_message()
            text = reply.text if reply.text else None
        
        if not text and event.pattern_match.group(1):
            text = event.pattern_match.group(1).strip()
        
        if not text:
            await event.edit("**• ❌ يرجى الرد على رسالة أو كتابة نص للترجمة**")
            return
        
        await event.edit("**• 🔄 جاري الترجمة...**")
        translated = await asyncio.get_event_loop().run_in_executor(_DOWNLOAD_EXECUTOR, translate_text, text)
        await event.edit(f"**• الترجمة:**\n{translated}")

    # ============== أمر .نت - المحسن ==============
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.نت$'))
    async def speed_test(event):
        await event.edit("**• 📶 جاري قياس سرعة النت...**")
        result = await measure_speed()
        if result['success']:
            await event.edit(f"**📶 نتيجة القياس:**\n**• البنق:** {result['ping']}ms\n**• سرعة التحميل:** {result['speed']:.1f} Mbps")
        else:
            await event.edit("**• ❌ فشل قياس سرعة النت - تأكد من اتصالك**")

    # ============== أمر .خرفة - الزخارف الإنجليزية ==============
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.خرفة (.+)'))
    async def decorate_text(event):
        text = event.pattern_match.group(1).strip()
        if not text: await event.edit("**• ❌ اكتب نص للزخرفة**"); return
        
        style_names = list(DECORATION_STYLES.keys())
        results = [f"**🎨 زخرفة '{text}':**\n"]
        
        for i, style_name in enumerate(style_names, 1):
            decorated = apply_decoration(text, style_name)
            results.append(f"**{i}.** `{decorated}`")
        
        await event.edit('\n'.join(results), parse_mode='markdown')

    # ============== أوامر الإدارة ==============
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.تاك$'))
    async def tag_all(event):
        if not event.is_group: await event.edit("**• ❌ الأمر يعمل في الجروبات فقط**"); return
        tagging_active[phone] = True
        await event.edit("**• 📢 جاري عمل تاك للأعضاء...**")
        mentions = []
        async for user in client.iter_participants(event.chat_id):
            if tagging_active.get(phone):
                name = user.first_name or ''
                mentions.append(f"[\u200b](tg://user?id={user.id}){name}")
            else: break
        if mentions:
            for i in range(0, len(mentions), 5):
                if not tagging_active.get(phone): break
                await client.send_message(event.chat_id, ''.join(mentions[i:i+5]))
                await asyncio.sleep(1)
        await event.delete()

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.غ تاك$'))
    async def stop_tag(event):
        tagging_active[phone] = False
        await event.edit("**• ⏹️ تم إيقاف التاك**")

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.بلوكات$'))
    async def blocked_list(event):
        await event.edit("**• 📋 جاري جلب قائمة المحظورين...**")
        try:
            blocked = await client(GetBlockedRequest(offset=0, limit=100))
            if not blocked.users: await event.edit("**• 📋 لا يوجد محظورين**"); return
            result = "**📋 قائمة المحظورين:**\n"
            for user in blocked.users[:20]:
                name = user.first_name or ''
                if user.last_name: name += f" {user.last_name}"
                result += f"• [{name}](tg://user?id={user.id})\n"
            await event.edit(result)
        except: await event.edit("**• ❌ فشل**")

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.حظر$'))
    async def block_user(event):
        target = await resolve_user(event, client)
        if not target: await event.edit("**• ❌ يرجى الرد على شخص أو كتابة اليوزر**"); return
        try:
            await client(BlockRequest(id=target))
            await event.edit(f"**• 🚫 تم حظر {target.first_name or 'المستخدم'}**")
        except: await event.edit("**• ❌ فشل**")

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.غ حظر$'))
    async def unblock_user(event):
        target = await resolve_user(event, client)
        if not target: await event.edit("**• ❌ يرجى الرد على شخص أو كتابة اليوزر**"); return
        try:
            await client(UnblockRequest(id=target))
            await event.edit(f"**• ✅ تم فك حظر {target.first_name or 'المستخدم'}**")
        except: await event.edit("**• ❌ فشل**")

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.كتم$'))
    async def mute_user_cmd(event):
        target = await resolve_user(event, client)
        if not target: await event.edit("**• ❌ يرجى الرد على شخص أو كتابة اليوزر**"); return
        try:
            if event.is_group:
                rights = ChatBannedRights(until_date=None, send_messages=True)
                await client(EditBannedRequest(event.chat_id, target.id, rights))
            muted_users[phone][target.id] = time.time()
            await event.edit(f"**• 🤐 تم كتم {target.first_name or 'المستخدم'}**")
        except: await event.edit("**• ❌ فشل**")

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.قيد$'))
    async def restrict_user(event):
        if not event.is_group: await event.edit("**• ❌ الأمر يعمل في الجروبات فقط**"); return
        target = await resolve_user(event, client)
        if not target: await event.edit("**• ❌ يرجى الرد على شخص**"); return
        try:
            rights = ChatBannedRights(until_date=None, send_messages=True, send_media=True, send_stickers=True, send_gifs=True, send_games=True, send_inline=True, embed_links=True)
            await client(EditBannedRequest(event.chat_id, target.id, rights))
            await event.edit(f"**• 🔒 تم تقييد {target.first_name or 'المستخدم'}**")
        except: await event.edit("**• ❌ فشل**")

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.طرد$'))
    async def kick_user(event):
        if not event.is_group: await event.edit("**• ❌ الأمر يعمل في الجروبات فقط**"); return
        target = await resolve_user(event, client)
        if not target: await event.edit("**• ❌ يرجى الرد على شخص أو كتابة اليوزر**"); return
        try:
            await client.kick_participant(event.chat_id, target.id)
            await event.edit(f"**• 👢 تم طرد {target.first_name or 'المستخدم'}**")
        except: await event.edit("**• ❌ فشل**")

    # ============== أوامر المحظورين والمكتومين ==============
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.محظورين$'))
    async def banned_list(event):
        if not event.is_group: await event.edit("**• ❌ الأمر يعمل في الجروبات فقط**"); return
        await event.edit("**• 📋 جاري جلب المحظورين...**")
        try:
            banned = await client(GetParticipantsRequest(event.chat_id, types.ChannelParticipantsKicked(), 0, 100, 0))
            if not banned.users: await event.edit("**• 📋 لا يوجد محظورين**"); return
            result = "**📋 المحظورين:**\n"
            for user in banned.users[:20]:
                result += f"• [{user.first_name or ''}](tg://user?id={user.id})\n"
            await event.edit(result)
        except: await event.edit("**• ❌ فشل**")

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.فك محظور$'))
    async def unban_user(event):
        if not event.is_group: await event.edit("**• ❌ الأمر يعمل في الجروبات فقط**"); return
        target = await resolve_user(event, client)
        if not target: await event.edit("**• ❌ يرجى الرد على شخص أو كتابة اليوزر**"); return
        try:
            await client(EditBannedRequest(event.chat_id, target.id, ChatBannedRights(until_date=None)))
            await event.edit(f"**• ✅ تم فك حظر {target.first_name or 'المستخدم'}**")
        except: await event.edit("**• ❌ فشل**")

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.فك محظورين$'))
    async def unban_all(event):
        if not event.is_group: await event.edit("**• ❌ الأمر يعمل في الجروبات فقط**"); return
        await event.edit("**• 🔄 جاري فك حظر الجميع...**")
        try:
            banned = await client(GetParticipantsRequest(event.chat_id, types.ChannelParticipantsKicked(), 0, 200, 0))
            for user in banned.users:
                try: await client(EditBannedRequest(event.chat_id, user.id, ChatBannedRights(until_date=None))); await asyncio.sleep(0.5)
                except: continue
            await event.edit("**• ✅ تم فك حظر الجميع**")
        except: await event.edit("**• ❌ فشل**")

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.فك كتم$'))
    async def unmute_user(event):
        if not event.is_group: await event.edit("**• ❌ الأمر يعمل في الجروبات فقط**"); return
        target = await resolve_user(event, client)
        if not target: await event.edit("**• ❌ يرجى الرد على شخص أو كتابة اليوزر**"); return
        try:
            await client(EditBannedRequest(event.chat_id, target.id, ChatBannedRights(until_date=None)))
            await event.edit(f"**• ✅ تم فك كتم {target.first_name or 'المستخدم'}**")
        except: await event.edit("**• ❌ فشل**")

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.فك مكتومين$'))
    async def unmute_all(event):
        if not event.is_group: await event.edit("**• ❌ الأمر يعمل في الجروبات فقط**"); return
        await event.edit("**• 🔄 جاري فك كتم الجميع...**")
        try:
            async for user in client.iter_participants(event.chat_id):
                try: await client(EditBannedRequest(event.chat_id, user.id, ChatBannedRights(until_date=None)))
                except: continue
            await event.edit("**• ✅ تم فك كتم الجميع**")
        except: await event.edit("**• ❌ فشل**")

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.فك تقيد$'))
    async def unrestrict_user(event):
        if not event.is_group: await event.edit("**• ❌ الأمر يعمل في الجروبات فقط**"); return
        target = await resolve_user(event, client)
        if not target: await event.edit("**• ❌ يرجى الرد على شخص أو كتابة اليوزر**"); return
        try:
            await client(EditBannedRequest(event.chat_id, target.id, ChatBannedRights(until_date=None)))
            await event.edit(f"**• ✅ تم فك تقييد {target.first_name or 'المستخدم'}**")
        except: await event.edit("**• ❌ فشل**")

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.فك مقيدين$'))
    async def unrestrict_all(event):
        if not event.is_group: await event.edit("**• ❌ الأمر يعمل في الجروبات فقط**"); return
        await event.edit("**• 🔄 جاري فك تقييد الجميع...**")
        try:
            async for user in client.iter_participants(event.chat_id):
                try: await client(EditBannedRequest(event.chat_id, user.id, ChatBannedRights(until_date=None)))
                except: continue
            await event.edit("**• ✅ تم فك تقييد الجميع**")
        except: await event.edit("**• ❌ فشل**")

    # ============== أوامر المعرفات ==============
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.ايدي$'))
    async def get_id(event):
        target = await resolve_user(event, client)
        if not target:
            if event.is_group: target = await client.get_entity(event.chat_id)
            else: target = await client.get_me()
        
        info = f"**🆔 المعرفات:**\n**• الاسم:** {target.first_name or ''}"
        if target.last_name: info += f" {target.last_name}"
        info += f"\n**• اليوزر:** @{target.username}" if target.username else "\n**• اليوزر:** لا يوجد"
        info += f"\n**• ID:** `{target.id}`"
        await event.edit(info, parse_mode='markdown')

    # ============== أمر .انشاء - المحسن ==============
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.انشاء$'))
    async def creation_date(event):
        target = None
        if event.is_reply:
            reply = await event.get_reply_message()
            try: target = await client.get_entity(reply.sender_id)
            except: pass
        elif event.is_private:
            try: target = await client.get_entity(event.chat_id)
            except: pass
        elif event.is_group or event.is_channel:
            try: target = await client.get_entity(event.chat_id)
            except: pass
        
        if not target:
            await event.edit("**• ❌ لا يمكن تحديد تاريخ الإنشاء**")
            return
        
        if hasattr(target, 'date') and target.date:
            date = target.date.strftime('%Y-%m-%d %H:%M:%S')
            entity_type = "الحساب" if hasattr(target, 'username') and not target.broadcast else "القناة" if hasattr(target, 'broadcast') and target.broadcast else "الجروب"
            await event.edit(f"**📅 تاريخ إنشاء {entity_type}:**\n{date}")
        else:
            await event.edit("**• ❌ لا يمكن تحديد تاريخ الإنشاء لهذا النوع**")

    # ============== أمر .عدد - يعمل في جميع المحادثات ==============
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.عدد$'))
    async def message_count(event):
        target = None
        chat = event.chat_id
        
        if event.is_reply:
            reply = await event.get_reply_message()
            try: target = await client.get_entity(reply.sender_id)
            except: pass
        else:
            try: target = await client.get_me()
            except: pass
        
        if not target:
            await event.edit("**• ❌ يرجى الرد على شخص أو استخدام الأمر مباشرة**")
            return
        
        count = 0
        try:
            async for msg in client.iter_messages(chat, from_user=target.id):
                count += 1
                if count >= 10000: break
        except:
            try:
                async for msg in client.iter_messages(chat):
                    if msg.sender_id == target.id:
                        count += 1
                        if count >= 10000: break
            except: pass
        
        name = target.first_name or 'المستخدم'
        await event.edit(f"**📊 عدد رسائل {name}:** {count}")

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.رتبة$'))
    async def user_rank(event):
        if not event.is_group: await event.edit("**• ❌ الأمر يعمل في الجروبات فقط**"); return
        target = await resolve_user(event, client)
        if not target: await event.edit("**• ❌ يرجى الرد على شخص**"); return
        try:
            participant = await client(functions.channels.GetParticipantRequest(event.chat_id, target.id))
            rank = "مالك" if isinstance(participant.participant, ChannelParticipantCreator) else "مشرف" if isinstance(participant.participant, ChannelParticipantAdmin) else "عضو"
            await event.edit(f"**🏅 رتبة {target.first_name or 'المستخدم'}:** {rank}")
        except:
            await event.edit(f"**🏅 رتبة {target.first_name or 'المستخدم'}:** عضو")

    # ============== أوامر الحذف ==============
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.حذف(?: (\d+))?$'))
    async def delete_messages(event):
        count = int(event.pattern_match.group(1)) if event.pattern_match.group(1) else 1
        deleted = 0
        async for msg in client.iter_messages(event.chat_id, limit=count + 1):
            if msg.out:
                try: await msg.delete(); deleted += 1
                except: pass
        await event.edit(f"**• 🗑️ تم حذف {deleted} رسالة**") if deleted > 0 else await event.delete()

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.احذف$'))
    async def delete_chat(event):
        target = await resolve_user(event, client)
        if not target:
            if event.is_private: target = await client.get_entity(event.chat_id)
            else: await event.edit("**• ❌ يرجى الرد على شخص أو استخدام في الخاص**"); return
        try:
            await client(DeleteHistoryRequest(peer=target, max_id=0, just_clear=False, revoke=True))
            await event.edit("**• ✅ تم حذف المحادثة من الطرفين**")
        except: await event.edit("**• ❌ فشل**")

    # ============== أوامر الجروب ==============
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.فتح$'))
    async def open_group(event):
        if not event.is_group: await event.edit("**• ❌ الأمر يعمل في الجروبات فقط**"); return
        try:
            await client(EditChatDefaultBannedRightsRequest(event.chat_id, ChatBannedRights(until_date=None)))
            await event.edit("**• 🔓 تم فتح الجروب**")
        except: await event.edit("**• ❌ فشل**")

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.قفل$'))
    async def close_group(event):
        if not event.is_group: await event.edit("**• ❌ الأمر يعمل في الجروبات فقط**"); return
        try:
            rights = ChatBannedRights(until_date=None, send_messages=True)
            await client(EditChatDefaultBannedRightsRequest(event.chat_id, rights))
            await event.edit("**• 🔒 تم قفل الجروب**")
        except: await event.edit("**• ❌ فشل**")

    # ============== أوامر الرفع والتنزيل ==============
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.مش$'))
    async def promote_mod(event):
        if not event.is_group: await event.edit("**• ❌ الأمر يعمل في الجروبات فقط**"); return
        target = await resolve_user(event, client)
        if not target: await event.edit("**• ❌ يرجى الرد على شخص**"); return
        try:
            rights = ChatAdminRights(post_messages=True, delete_messages=True, ban_users=True, invite_users=True, pin_messages=True, add_admins=False, anonymous=False, manage_call=True)
            await client(EditAdminRequest(event.chat_id, target.id, rights, "مشرف"))
            await event.edit(f"**• ⭐ تم رفع {target.first_name or 'المستخدم'} مشرف**")
        except: await event.edit("**• ❌ فشل**")

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.اد$'))
    async def promote_admin(event):
        if not event.is_group: await event.edit("**• ❌ الأمر يعمل في الجروبات فقط**"); return
        target = await resolve_user(event, client)
        if not target: await event.edit("**• ❌ يرجى الرد على شخص**"); return
        try:
            rights = ChatAdminRights(post_messages=True, delete_messages=True, ban_users=True, invite_users=True, pin_messages=True, add_admins=True, anonymous=False, manage_call=True, other=True)
            await client(EditAdminRequest(event.chat_id, target.id, rights, "أدمن"))
            await event.edit(f"**• 👑 تم رفع {target.first_name or 'المستخدم'} أدمن**")
        except: await event.edit("**• ❌ فشل**")

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.مالك$'))
    async def promote_owner(event):
        if not event.is_group: await event.edit("**• ❌ الأمر يعمل في الجروبات فقط**"); return
        target = await resolve_user(event, client)
        if not target: await event.edit("**• ❌ يرجى الرد على شخص**"); return
        try:
            rights = ChatAdminRights(post_messages=True, delete_messages=True, ban_users=True, invite_users=True, pin_messages=True, add_admins=True, anonymous=True, manage_call=True, other=True)
            await client(EditAdminRequest(event.chat_id, target.id, rights, "مالك"))
            await event.edit(f"**• 🤴 تم رفع {target.first_name or 'المستخدم'} مالك**")
        except: await event.edit("**• ❌ فشل**")

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.تن$'))
    async def demote_all(event):
        if not event.is_group: await event.edit("**• ❌ الأمر يعمل في الجروبات فقط**"); return
        target = await resolve_user(event, client)
        if not target: await event.edit("**• ❌ يرجى الرد على شخص**"); return
        try:
            await client(EditAdminRequest(event.chat_id, target.id, ChatAdminRights(), ""))
            await event.edit(f"**• ⬇️ تم تنزيل {target.first_name or 'المستخدم'}**")
        except: await event.edit("**• ❌ فشل**")

    # ============== أوامر الإضافة والتسجيل ==============
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.ضيف (\d+)$'))
    async def smart_add(event):
        if not event.is_group: await event.edit("**• ❌ الأمر يعمل في الجروبات فقط**"); return
        count = int(event.pattern_match.group(1))
        await event.edit(f"**• 📥 جاري إضافة {count} عضو بذكاء...**")
        added = 0
        for dialog in await client.get_dialogs():
            if added >= count: break
            if dialog.is_group:
                try:
                    async for user in client.iter_participants(dialog.id, limit=5):
                        if added >= count: break
                        if user.bot or user.deleted: continue
                        try:
                            await client(InviteToChannelRequest(event.chat_id, [user.id]))
                            added += 1
                            await asyncio.sleep(3)
                        except FloodWaitError as e: await asyncio.sleep(e.seconds + 1)
                        except: continue
                except: continue
        await event.edit(f"**• ✅ تم إضافة {added} عضو**")

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.غ ضيف$'))
    async def stop_add(event):
        await event.edit("**• ⏹️ تم إيقاف الإضافة**")

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.تسجيل$'))
    async def add_contact(event):
        target = await resolve_user(event, client)
        if not target: await event.edit("**• ❌ يرجى الرد على شخص أو كتابة اليوزر**"); return
        try:
            await client(AddContactRequest(id=target, first_name=target.first_name or '', last_name=target.last_name or '', phone='', add_phone_privacy_exception=False))
            await event.edit(f"**• 📇 تم تسجيل {target.first_name or 'المستخدم'} في جهات الاتصال**")
        except: await event.edit("**• ❌ فشل**")

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.ممول (\d+) (.+)$'))
    async def fund_add(event):
        if not event.is_group: await event.edit("**• ❌ الأمر يعمل في الجروبات فقط**"); return
        count = int(event.pattern_match.group(1))
        username = event.pattern_match.group(2).strip('@')
        try: target_group = await client.get_entity(username)
        except: await event.edit(f"**• ❌ لم يتم العثور على {username}**"); return
        await event.edit(f"**• 📥 جاري تسجيل {count} عضو...**")
        added = 0
        try:
            async for user in client.iter_participants(event.chat_id, limit=count):
                if user.bot or user.deleted: continue
                try:
                    await client(InviteToChannelRequest(target_group, [user.id]))
                    added += 1
                    await asyncio.sleep(2)
                except FloodWaitError as e: await asyncio.sleep(e.seconds + 1)
                except: continue
        except: pass
        await event.edit(f"**• ✅ تم تسجيل {added} عضو في {username}**")

    # ============== أوامر متفرقة ==============
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.اطردني$'))
    async def leave_group(event):
        if not event.is_group: await event.edit("**• ❌ الأمر يعمل في الجروبات فقط**"); return
        try:
            await client.delete_dialog(event.chat_id)
        except: pass

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.ادمنز$'))
    async def admin_list(event):
        if not event.is_group: await event.edit("**• ❌ الأمر يعمل في الجروبات فقط**"); return
        await event.edit("**• 📋 جاري جلب قائمة الأدمنز...**")
        admins = []
        async for admin in client.iter_participants(event.chat_id, filter=ChannelParticipantsAdmins):
            admins.append(f"• {admin.first_name or ''} {'@'+admin.username if admin.username else ''}")
        await event.edit("**👑 الأدمنز:**\n" + '\n'.join(admins[:20]) if admins else "**• ❌ لا يوجد أدمنز**")

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.نيم (.+)'))
    async def set_name(event):
        name = event.pattern_match.group(1).strip()
        if event.is_group:
            try:
                await client(EditAdminRequest(event.chat_id, (await client.get_me()).id, ChatAdminRights(), name))
                await event.edit(f"**• ✅ تم تغيير اسم الجروب إلى {name}**")
            except: await event.edit("**• ❌ فشل**")
        else:
            try:
                await client(UpdateProfileRequest(first_name=name))
                await event.edit(f"**• ✅ تم تغيير الاسم إلى {name}**")
            except: await event.edit("**• ❌ فشل**")

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.بايو (.+)'))
    async def set_bio(event):
        bio = event.pattern_match.group(1).strip()
        try:
            await client(UpdateProfileRequest(about=bio[:70]))
            await event.edit("**• ✅ تم تحديث البايو**")
        except: await event.edit("**• ❌ فشل**")

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.صورة$'))
    async def set_photo(event):
        if not event.is_reply: await event.edit("**• ❌ يرجى الرد على صورة**"); return
        reply = await event.get_reply_message()
        if not reply.photo: await event.edit("**• ❌ الرد على صورة فقط**"); return
        try:
            photo = await client.download_media(reply)
            uploaded = await client.upload_file(photo)
            if event.is_group:
                await client(EditPhotoRequest(event.chat_id, uploaded))
            else:
                await client(UploadProfilePhotoRequest(file=uploaded))
            await event.edit("**• ✅ تم تحديث الصورة**")
            safe_remove(photo)
        except: await event.edit("**• ❌ فشل**")

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.تابع (.+)'))
    async def stalk_user(event):
        username = event.pattern_match.group(1).strip('@')
        try:
            target = await client.get_entity(username)
            await event.edit(f"**• 👀 جاري متابعة {target.first_name or username}...**")
            was_online = False
            stalking_active[phone] = True
            while stalking_active.get(phone):
                entity = await client.get_entity(target.id)
                if hasattr(entity, 'status'):
                    if isinstance(entity.status, UserStatusOnline):
                        if not was_online:
                            await event.edit(f"**• 🟢 {target.first_name or username} أونلاين الآن!**")
                            was_online = True
                    else:
                        if was_online:
                            await event.edit(f"**• 🔴 {target.first_name or username} أصبح أوفلاين**")
                            break
                await asyncio.sleep(10)
        except: await event.edit("**• ❌ فشل**")

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.غ تابع$'))
    async def stop_stalk(event):
        stalking_active[phone] = False
        await event.edit("**• ⏹️ تم إيقاف المتابعة**")

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.ث$'))
    async def pin_message(event):
        if not event.is_reply: await event.edit("**• ❌ يرجى الرد على رسالة**"); return
        try:
            await (await event.get_reply_message()).pin()
            await event.edit("**• 📌 تم تثبيت الرسالة**")
        except: await event.edit("**• ❌ فشل**")

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.غ ث$'))
    async def unpin_message(event):
        if not event.is_reply: await event.edit("**• ❌ يرجى الرد على رسالة**"); return
        try:
            await (await event.get_reply_message()).unpin()
            await event.edit("**• ✅ تم إلغاء التثبيت**")
        except: await event.edit("**• ❌ فشل**")

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.كول$'))
    async def create_call(event):
        if not event.is_group: await event.edit("**• ❌ الأمر يعمل في الجروبات فقط**"); return
        try:
            await client(CreateGroupCallRequest(event.chat_id, title='مكالمة صوتية'))
            await event.edit("**• 📞 تم فتح مكالمة صوتية**")
        except: await event.edit("**• ❌ فشل**")

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.اوامر$'))
    async def show_commands(event):
        cmds = """**📋 قائمة الأوامر:**

**🎨 التنسيق:** `.عريض` `.مائل` `.مشطوب` `.غ خط` `.خفي` `.غ خفي`
**😂 النسب:** `.حب` `.غباء` `.كدب`
**🎭 المزاح:** `.تهكير` `.قتل`
**📊 الإحصائيات:** `.جروباتي` `.قنواتي` `.تونزي` `.بلوكات`
**🎪 الأنيمشن:** `.ضحك` `.قلب` `.غيمة` `.ورد` `.كوكب` `.شتاء` `.قمر` `.وقف`
**📥 التحميل:** `.يوت` `.فيد` `.صوت`
**🔧 التحويل:** `.نسخ` `.استيك` `.بيك` `.ترجم`
**🖼️ الصور:** `.بن` `.صورة`
**👥 الإدارة:** `.تاك` `.غ تاك` `.حظر` `.غ حظر` `.كتم` `.قيد` `.طرد`
**🔓 فك:** `.فك محظور` `.فك محظورين` `.فك كتم` `.فك مكتومين` `.فك تقيد` `.فك مقيدين`
**📝 المعرفات:** `.ايدي` `.انشاء` `.عدد` `.رتبة`
**🗑️ الحذف:** `.حذف` `.احذف`
**🚪 الجروب:** `.فتح` `.قفل` `.ادمنز` `.اطردني` `.كول`
**👑 الرفع:** `.مش` `.اد` `.مالك` `.تن`
**📇 جهات الاتصال:** `.تسجيل` `.ممول` `.ضيف` `.غ ضيف`
**📌 التثبيت:** `.ث` `.غ ث`
**🔍 متابعة:** `.تابع` `.غ تابع`
**🎭 الانتحال:** `.انتحل` `.غ انتحل`
**🎭 التقليد:** `.قلد` `.غ تقليد`
**🔤 الزخرفة:** `.خرفة`
**📶 السرعة:** `.نت`
**ℹ️ معلومات:** `.اوامر` `.سورس` `.المساحة` `.تنظيف`"""
        await event.edit(cmds, parse_mode='markdown')

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.سورس$'))
    async def show_source(event):
        await event.edit("**👨‍💻 𝐒𝐎𝐔𝐑𝐂𝐄 𝐂𝐎𝐃𝐄:**\n**• تم التطوير بواسطة الذكاء الاصطناعي**\n**• نسخة متكاملة 2024**", parse_mode='markdown')

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.المساحة$'))
    async def space_check(event):
        await event.edit(f"**📊 المساحة:** {get_free_space_mb():.1f} MB", parse_mode='markdown')

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.تنظيف$'))
    async def force_clean(event):
        c = clean_temp_files()
        await event.edit(f"**✅ تم تنظيف {c} ملف\n📊 المساحة: {get_free_space_mb():.1f} MB**", parse_mode='markdown')

    # ============== التقليد والانتحال ==============
    @client.on(events.NewMessage(incoming=True))
    async def auto_taqleed(event):
        if event.sender_id in taqleed_users.get(phone, {}) and event.text and not event.text.startswith('.'):
            await asyncio.sleep(0.3)
            try: await event.reply(event.text)
            except: pass

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.قلد$'))
    async def taq(event):
        target = await resolve_user(event, client)
        if target: taqleed_users[phone][target.id] = True; await event.edit(f"**• ✅ تم تفعيل التقليد لـ {target.first_name or 'المستخدم'}**")
        else:
            if event.is_reply:
                reply = await event.get_reply_message()
                taqleed_users[phone][reply.sender_id] = True
                await event.edit("**• ✅ تم تفعيل التقليد**")
            else: await event.edit("**• ❌ يرجى الرد على شخص أو كتابة اليوزر**")

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.غ تقليد$'))
    async def notaq(event):
        target = await resolve_user(event, client)
        if target and target.id in taqleed_users.get(phone, {}):
            del taqleed_users[phone][target.id]; await event.edit("**• ✅ تم فك التقليد**")
        else: await event.edit("**• ❌ لا يوجد تقليد نشط**")

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.انتحل$'))
    async def ent7al(event):
        track_command(phone, ".انتحال")
        await event.edit("**• 🔄 جاري الانتحال...**", parse_mode='markdown')
        target_user = await resolve_user(event, client)
        if not target_user:
            if event.is_reply:
                reply = await event.get_reply_message()
                target_user = await client.get_entity(reply.sender_id)
            elif event.is_private:
                target_user = await client.get_entity(event.chat_id)
        if not target_user: await event.edit("**• ❌ فشل الانتحال**", parse_mode='markdown'); return
        target_info = await get_user_info_full(client, target_user.id)
        if not target_info: await event.edit("**• ❌ فشل جلب المعلومات**", parse_mode='markdown'); return
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

    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.غ انتحل$'))
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
        new = event.text or "<وسائط>"
        await client.send_message("me", f"**📝 {name} عدل رسالة**\n**من:** {old}\n**إلى:** {new}")
        message_cache.setdefault(event.chat_id, {})[event.id] = new

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
