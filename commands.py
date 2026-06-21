import asyncio
import io
import os
import logging
import subprocess
import shutil
import re
import time
import json
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

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

try:
    import aiohttp
    HAS_AIOHTTP = True
except ImportError:
    HAS_AIOHTTP = False

try:
    import httpx
    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False

_DOWNLOAD_EXECUTOR = ThreadPoolExecutor(max_workers=8, thread_name_prefix="dl")

# ═══════════════════════════════════════════════════════════════
#  أدوات مساعدة
# ═══════════════════════════════════════════════════════════════

def format_duration(seconds):
    if not seconds:
        return "0:00"
    mins, secs = divmod(int(seconds), 60)
    hrs, mins = divmod(mins, 60)
    if hrs:
        return f"{hrs}:{mins:02d}:{secs:02d}"
    return f"{mins}:{secs:02d}"


def _get_headers(extra: dict = None) -> dict:
    base = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "*/*",
    }
    if extra:
        base.update(extra)
    return base


def _req_get(url, **kwargs):
    """طلب GET مع fallback بين المكتبات المتاحة"""
    timeout = kwargs.pop("timeout", 30)
    headers = kwargs.pop("headers", _get_headers())
    if HAS_REQUESTS:
        import requests as rq
        return rq.get(url, headers=headers, timeout=timeout, **kwargs)
    raise RuntimeError("لا توجد مكتبة HTTP متاحة")


def _req_post(url, **kwargs):
    timeout = kwargs.pop("timeout", 30)
    headers = kwargs.pop("headers", _get_headers())
    if HAS_REQUESTS:
        import requests as rq
        return rq.post(url, headers=headers, timeout=timeout, **kwargs)
    raise RuntimeError("لا توجد مكتبة HTTP متاحة")


def _stream_download(url: str, filepath: str, headers: dict = None, timeout: int = 300) -> str:
    """تحميل ملف بالبث مع دعم استئناف التحميل"""
    if not headers:
        headers = _get_headers()
    # نحاول استئناف التحميل إن كان الملف موجوداً جزئياً
    downloaded = 0
    if os.path.exists(filepath):
        downloaded = os.path.getsize(filepath)
        if downloaded > 0:
            headers = dict(headers)
            headers["Range"] = f"bytes={downloaded}-"

    mode = "ab" if downloaded > 0 else "wb"
    if HAS_REQUESTS:
        import requests as rq
        with rq.get(url, headers=headers, stream=True, timeout=timeout) as resp:
            if resp.status_code not in (200, 206):
                raise ValueError(f"HTTP {resp.status_code} من {url}")
            with open(filepath, mode) as f:
                for chunk in resp.iter_content(chunk_size=65536):
                    if chunk:
                        f.write(chunk)
        return filepath
    raise RuntimeError("لا توجد مكتبة HTTP متاحة")


def _get_temp_path(prefix: str, ext: str) -> str:
    ts = int(time.time() * 1000)
    return os.path.join(TEMP_DIR, f"{prefix}_{ts}.{ext}")


# ═══════════════════════════════════════════════════════════════
#  البحث عن رابط يوتيوب
# ═══════════════════════════════════════════════════════════════

def _extract_yt_id(text: str):
    patterns = [
        r"(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/shorts/)([\w-]{11})",
        r"(?:^|[\s])v=([\w-]{11})",
    ]
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            return m.group(1)
    return None


def _search_youtube_link(query: str) -> str:
    """يبحث عن رابط يوتيوب عبر عدة محركات"""
    strategies = [
        lambda q: _yt_search_bing(q),
        lambda q: _yt_search_ddg(q),
        lambda q: _yt_search_invidious(q),
    ]
    for fn in strategies:
        try:
            url = fn(query)
            if url:
                return url
        except Exception:
            continue
    return None


def _yt_search_bing(query: str) -> str:
    resp = _req_get(
        "https://www.bing.com/search",
        params={"q": f"{query} site:youtube.com/watch"},
        timeout=15,
    )
    match = re.search(r"https?://(?:www\.)?youtube\.com/watch\?v=([\w-]{11})", resp.text)
    return f"https://www.youtube.com/watch?v={match.group(1)}" if match else None


def _yt_search_ddg(query: str) -> str:
    resp = _req_get(
        "https://html.duckduckgo.com/html/",
        params={"q": f"{query} site:youtube.com"},
        headers=_get_headers({"Accept": "text/html"}),
        timeout=15,
    )
    match = re.search(r"https?://(?:www\.)?youtube\.com/watch\?v=([\w-]{11})", resp.text)
    return f"https://www.youtube.com/watch?v={match.group(1)}" if match else None


def _yt_search_invidious(query: str) -> str:
    instances = ["https://invidious.tiekoetter.com", "https://vid.puffyan.us", "https://yt.artemislena.eu"]
    for base in instances:
        try:
            resp = _req_get(f"{base}/api/v1/search", params={"q": query, "type": "video"}, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                if data and data[0].get("videoId"):
                    return f"https://www.youtube.com/watch?v={data[0]['videoId']}"
        except Exception:
            continue
    return None


# ═══════════════════════════════════════════════════════════════
#  مصادر التحميل - 10 طرق مختلفة
# ═══════════════════════════════════════════════════════════════

def _normalize_query(query: str) -> str:
    """إذا لم يكن رابطاً ابحث عن رابط يوتيوب"""
    if re.match(r"https?://", query):
        return query
    url = _search_youtube_link(query)
    if not url:
        raise ValueError("لم يتم العثور على الفيديو في يوتيوب")
    return url


# ─── 1. yt-dlp (الأفضل والأكثر موثوقية) ───
def _ytdlp_download(query: str, out_dir: str, audio_only: bool) -> tuple:
    if not shutil.which("yt-dlp"):
        raise ValueError("yt-dlp غير مثبت")
    url = _normalize_query(query)
    out_tmpl = os.path.join(out_dir, f"ytdlp_{int(time.time())}.%(ext)s")
    cmd = ["yt-dlp", "--no-playlist", "--no-warnings",
           "--socket-timeout", "30",
           "--retries", "3",
           "--concurrent-fragments", "4",
           "-o", out_tmpl]
    if audio_only:
        cmd += ["-x", "--audio-format", "mp3", "--audio-quality", "192K"]
    else:
        cmd += ["-f", "bestvideo[ext=mp4][height<=720]+bestaudio[ext=m4a]/best[ext=mp4]/best"]
    # محاولة بدون cookies أولاً
    try:
        info_cmd = cmd + ["--print", "%(title)s\n%(duration)s\n%(uploader)s", url]
        r = subprocess.run(info_cmd, capture_output=True, text=True, timeout=120)
        lines = r.stdout.strip().splitlines()
        title = lines[0] if lines else "بدون عنوان"
        duration = int(float(lines[1])) if len(lines) > 1 and lines[1] else 0
        uploader = lines[2] if len(lines) > 2 else ""
    except Exception:
        title, duration, uploader = "بدون عنوان", 0, ""

    dl_cmd = cmd + [url]
    result = subprocess.run(dl_cmd, capture_output=True, text=True, timeout=300)
    # البحث عن الملف الناتج
    ext = "mp3" if audio_only else "mp4"
    pattern = f"ytdlp_{int(time.time()) - 5}"
    for f in sorted(os.listdir(out_dir), reverse=True):
        if f.endswith(f".{ext}") and "ytdlp_" in f:
            return {"title": title, "duration": duration, "uploader": uploader}, os.path.join(out_dir, f)
    # بحث أوسع
    for f in sorted(os.listdir(out_dir), reverse=True):
        if f.startswith("ytdlp_"):
            return {"title": title, "duration": duration, "uploader": uploader}, os.path.join(out_dir, f)
    raise ValueError(f"yt-dlp فشل: {result.stderr[:200]}")


# ─── 2. Cobalt API ───
def _cobalt_download(query: str, out_dir: str, audio_only: bool) -> tuple:
    url = _normalize_query(query)
    endpoints = [
        "https://co.wuk.sh/api/json",
        "https://cobalt.tools/api/json",
        "https://api.cobalt.tools/api/json",
    ]
    for endpoint in endpoints:
        try:
            resp = _req_post(
                endpoint,
                json={"url": url, "filenamePattern": "basic",
                      "downloadMode": "audio" if audio_only else "auto",
                      "audioFormat": "mp3", "isAudioOnly": audio_only},
                headers=_get_headers({"Accept": "application/json", "Content-Type": "application/json"}),
                timeout=45,
            )
            if resp.status_code != 200:
                continue
            data = resp.json()
            dl_url = data.get("url")
            if not dl_url:
                continue
            ext = "mp3" if audio_only else "mp4"
            filepath = _get_temp_path("cobalt", ext)
            _stream_download(dl_url, filepath)
            return {"title": data.get("filename", "cobalt_media"), "duration": 0, "uploader": ""}, filepath
        except Exception:
            continue
    raise ValueError("Cobalt: جميع العناوين فشلت")


# ─── 3. SaveFrom ───
def _savefrom_download(query: str, out_dir: str, audio_only: bool) -> tuple:
    url = _normalize_query(query)
    vid_id = _extract_yt_id(url)
    if not vid_id:
        raise ValueError("SaveFrom: معرف الفيديو غير صالح")
    resp = _req_get(
        f"https://worker.sf-tools.com/savefrom.php",
        params={"sf_url": url},
        headers=_get_headers({"Referer": "https://en.savefrom.net/"}),
        timeout=30,
    )
    if resp.status_code != 200:
        raise ValueError(f"SaveFrom: HTTP {resp.status_code}")
    data = resp.json()
    title = data.get("meta", {}).get("title", "savefrom_media")
    # اختر الجودة المناسبة
    links = data.get("url", [])
    chosen = None
    if audio_only:
        for lnk in links:
            if lnk.get("ext") == "mp3":
                chosen = lnk.get("url")
                break
    else:
        for quality in ["720", "360", "480"]:
            for lnk in links:
                if quality in str(lnk.get("quality", "")):
                    chosen = lnk.get("url")
                    break
            if chosen:
                break
    if not chosen and links:
        chosen = links[0].get("url")
    if not chosen:
        raise ValueError("SaveFrom: لا توجد روابط تحميل")
    ext = "mp3" if audio_only else "mp4"
    filepath = _get_temp_path("savefrom", ext)
    _stream_download(chosen, filepath)
    return {"title": title, "duration": 0, "uploader": ""}, filepath


# ─── 4. Y2Mate ───
def _y2mate_download(query: str, out_dir: str, audio_only: bool) -> tuple:
    url = _normalize_query(query)
    vid_id = _extract_yt_id(url)
    if not vid_id:
        raise ValueError("Y2mate: معرف غير صالح")
    headers = _get_headers({"Content-Type": "application/x-www-form-urlencoded"})
    resp = _req_post(
        "https://www.y2mate.com/mates/analyzeV2/ajax",
        data={"k_query": f"https://www.youtube.com/watch?v={vid_id}", "k_page": "home", "hl": "en", "q_auto": 1},
        headers=headers,
        timeout=20,
    )
    if resp.status_code != 200:
        raise ValueError(f"Y2mate Analyze: HTTP {resp.status_code}")
    data = resp.json()
    video_id = data.get("vid")
    title = data.get("title", "y2mate_media")
    if not video_id:
        raise ValueError("Y2mate: الفيديو غير موجود")
    fmt_key = "mp3" if audio_only else "137"  # 137 = 1080p video
    # جرب جودات متعددة للفيديو
    for key in ([fmt_key] if audio_only else ["137", "22", "18"]):
        try:
            resp2 = _req_post(
                "https://www.y2mate.com/mates/convertV2/index",
                data={"vid": video_id, "k": key},
                headers=headers,
                timeout=20,
            )
            if resp2.status_code != 200:
                continue
            data2 = resp2.json()
            dl_url = data2.get("dlink")
            if not dl_url:
                continue
            ext = "mp3" if audio_only else "mp4"
            filepath = _get_temp_path("y2mate", ext)
            _stream_download(dl_url, filepath)
            return {"title": title, "duration": 0, "uploader": ""}, filepath
        except Exception:
            continue
    raise ValueError("Y2mate: فشلت جميع جودات التحميل")


# ─── 5. Invidious API ───
def _invidious_download(query: str, out_dir: str, audio_only: bool) -> tuple:
    url = _normalize_query(query)
    vid_id = _extract_yt_id(url)
    if not vid_id:
        raise ValueError("Invidious: معرف غير صالح")
    instances = [
        "https://invidious.tiekoetter.com",
        "https://vid.puffyan.us",
        "https://yt.artemislena.eu",
        "https://invidious.privacyredirect.com",
    ]
    for base in instances:
        try:
            resp = _req_get(f"{base}/api/v1/videos/{vid_id}", timeout=15)
            if resp.status_code != 200:
                continue
            data = resp.json()
            title = data.get("title", "invidious_media")
            duration = data.get("lengthSeconds", 0)
            author = data.get("author", "")
            formats = data.get("adaptiveFormats", []) + data.get("formatStreams", [])
            chosen_url = None
            if audio_only:
                audio_fmts = [f for f in formats if f.get("type", "").startswith("audio")]
                if audio_fmts:
                    chosen_url = audio_fmts[0].get("url")
            else:
                for res in ["720p", "360p", "480p", "1080p"]:
                    for fmt in formats:
                        if fmt.get("qualityLabel") == res and "video" in fmt.get("type", ""):
                            chosen_url = fmt.get("url")
                            break
                    if chosen_url:
                        break
            if not chosen_url:
                continue
            ext = "mp3" if audio_only else "mp4"
            filepath = _get_temp_path("invidious", ext)
            _stream_download(chosen_url, filepath)
            return {"title": title, "duration": duration, "uploader": author}, filepath
        except Exception:
            continue
    raise ValueError("Invidious: جميع الخوادم فشلت")


# ─── 6. RapidAPI YouTube Downloader ───
def _rapidapi_download(query: str, out_dir: str, audio_only: bool) -> tuple:
    url = _normalize_query(query)
    vid_id = _extract_yt_id(url)
    if not vid_id:
        raise ValueError("RapidAPI: معرف غير صالح")
    # نستخدم نقطة وصول عامة لا تحتاج مفتاح
    apis = [
        f"https://youtube-mp36.p.rapidapi.com/dl?id={vid_id}",
        f"https://youtube-mp3-download1.p.rapidapi.com/dl?id={vid_id}",
    ]
    for api_url in apis:
        try:
            resp = _req_get(api_url, timeout=30)
            if resp.status_code != 200:
                continue
            data = resp.json()
            dl_url = data.get("link") or data.get("url")
            title = data.get("title", "rapidapi_media")
            if not dl_url:
                continue
            ext = "mp3" if audio_only else "mp4"
            filepath = _get_temp_path("rapidapi", ext)
            _stream_download(dl_url, filepath)
            return {"title": title, "duration": 0, "uploader": ""}, filepath
        except Exception:
            continue
    raise ValueError("RapidAPI: جميع الطرق فشلت")


# ─── 7. 9xBuddy / SnapSave (للروابط العامة) ───
def _snapsave_download(query: str, out_dir: str, audio_only: bool) -> tuple:
    url = _normalize_query(query)
    # 9xbuddy
    resp = _req_post(
        "https://9xbuddy.in/process",
        data={"url": url},
        headers=_get_headers({"Referer": "https://9xbuddy.in/"}),
        timeout=30,
    )
    if resp.status_code != 200:
        raise ValueError(f"9xBuddy: HTTP {resp.status_code}")
    data = resp.json()
    links = data.get("links") or data.get("data", {}).get("download", [])
    if not links:
        raise ValueError("9xBuddy: لا توجد روابط")
    # اختر الأفضل
    chosen = links[0].get("url") if isinstance(links[0], dict) else links[0]
    ext = "mp3" if audio_only else "mp4"
    filepath = _get_temp_path("9xbuddy", ext)
    _stream_download(chosen, filepath)
    return {"title": data.get("title", "media"), "duration": 0, "uploader": ""}, filepath


# ─── 8. SSYouTube (direct link trick) ───
def _ssyoutube_download(query: str, out_dir: str, audio_only: bool) -> tuple:
    url = _normalize_query(query)
    # حيلة ss: بدّل youtube.com بـ ssyoutube.com
    ss_url = url.replace("https://www.youtube.com", "https://ssyoutube.com")
    ss_url = ss_url.replace("https://youtube.com", "https://ssyoutube.com")
    resp = _req_get(ss_url, timeout=20)
    if resp.status_code != 200:
        raise ValueError(f"SSYouTube: HTTP {resp.status_code}")
    # استخراج روابط التحميل من HTML
    pattern = r'href="(https://[^"]+\.(?:mp4|mp3|webm)[^"]*)"'
    matches = re.findall(pattern, resp.text)
    if not matches:
        raise ValueError("SSYouTube: لم يتم العثور على روابط")
    title_m = re.search(r'<title>([^<]+)</title>', resp.text)
    title = title_m.group(1).replace(" - SSYouTube", "").strip() if title_m else "ssyt_media"
    ext = "mp3" if audio_only else "mp4"
    # اختر حسب النوع
    preferred = [m for m in matches if (".mp3" in m if audio_only else ".mp4" in m)]
    chosen = preferred[0] if preferred else matches[0]
    filepath = _get_temp_path("ssyt", ext)
    _stream_download(chosen, filepath)
    return {"title": title, "duration": 0, "uploader": ""}, filepath


# ─── 9. aria2c (تسريع التحميل الخام) ───
def _aria2c_download(dl_url: str, out_dir: str, ext: str) -> str:
    """تحميل رابط مباشر باستخدام aria2c للسرعة القصوى"""
    if not shutil.which("aria2c"):
        raise ValueError("aria2c غير مثبت")
    filepath = _get_temp_path("aria2", ext)
    cmd = [
        "aria2c", dl_url,
        "-o", os.path.basename(filepath),
        "-d", out_dir,
        "--max-connection-per-server=16",
        "--split=16",
        "--min-split-size=1M",
        "--max-concurrent-downloads=4",
        "--file-allocation=none",
        "--quiet=true",
        "--timeout=60",
    ]
    result = subprocess.run(cmd, capture_output=True, timeout=300)
    if result.returncode != 0:
        raise ValueError(f"aria2c فشل: {result.stderr.decode()[:100]}")
    if os.path.exists(filepath):
        return filepath
    raise ValueError("aria2c: الملف لم يُنشأ")


# ─── 10. ffmpeg stream copy (تحميل HLS/DASH) ───
def _ffmpeg_download(query: str, out_dir: str, audio_only: bool) -> tuple:
    """استخدام ffmpeg مباشرة لتحميل الستريم"""
    if not shutil.which("ffmpeg"):
        raise ValueError("ffmpeg غير مثبت")
    url = _normalize_query(query)
    ext = "mp3" if audio_only else "mp4"
    filepath = _get_temp_path("ffmpeg", ext)
    if audio_only:
        cmd = ["ffmpeg", "-i", url, "-vn", "-acodec", "libmp3lame", "-q:a", "4", filepath, "-y", "-loglevel", "error"]
    else:
        cmd = ["ffmpeg", "-i", url, "-c", "copy", filepath, "-y", "-loglevel", "error"]
    result = subprocess.run(cmd, capture_output=True, timeout=300)
    if result.returncode != 0 or not os.path.exists(filepath):
        raise ValueError(f"ffmpeg فشل: {result.stderr.decode()[:100]}")
    return {"title": "ffmpeg_media", "duration": 0, "uploader": ""}, filepath


# ═══════════════════════════════════════════════════════════════
#  المحرك الرئيسي للتحميل - يجرب الطرق بالترتيب
# ═══════════════════════════════════════════════════════════════

DOWNLOAD_METHODS_AUDIO = [
    ("yt-dlp",      _ytdlp_download),
    ("Cobalt",      _cobalt_download),
    ("Invidious",   _invidious_download),
    ("Y2mate",      _y2mate_download),
    ("SaveFrom",    _savefrom_download),
    ("RapidAPI",    _rapidapi_download),
    ("SSYouTube",   _ssyoutube_download),
    ("9xBuddy",     _snapsave_download),
    ("ffmpeg",      _ffmpeg_download),
]

DOWNLOAD_METHODS_VIDEO = [
    ("yt-dlp",      _ytdlp_download),
    ("Cobalt",      _cobalt_download),
    ("Invidious",   _invidious_download),
    ("Y2mate",      _y2mate_download),
    ("SaveFrom",    _savefrom_download),
    ("9xBuddy",     _snapsave_download),
    ("SSYouTube",   _ssyoutube_download),
    ("ffmpeg",      _ffmpeg_download),
]


async def _smart_download(query: str, audio_only: bool, status_msg, loop) -> tuple:
    """
    يجرب كل الطرق بالترتيب ويُحدّث رسالة الحالة.
    يعيد (info_dict, filepath)
    """
    methods = DOWNLOAD_METHODS_AUDIO if audio_only else DOWNLOAD_METHODS_VIDEO
    errors = []

    for name, fn in methods:
        try:
            await status_msg.edit(f"**• ⏳ جاري التحميل عبر {name}...**")
            info, filepath = await loop.run_in_executor(
                _DOWNLOAD_EXECUTOR, fn, query, TEMP_DIR, audio_only
            )
            if filepath and os.path.exists(filepath) and os.path.getsize(filepath) > 1024:
                logger.info(f"✅ التحميل نجح عبر {name}")
                return info, filepath
            errors.append(f"{name}: الملف فارغ أو غير موجود")
        except Exception as e:
            err = str(e)[:80]
            errors.append(f"{name}: {err}")
            logger.warning(f"❌ {name} فشل: {err}")
            continue

    # إذا فشلت كل الطرق
    err_summary = "\n".join(f"• {e}" for e in errors[:5])
    raise ValueError(f"فشلت جميع طرق التحميل:\n{err_summary}")


# ═══════════════════════════════════════════════════════════════
#  البحث عن الصور (محركات متعددة)
# ═══════════════════════════════════════════════════════════════

def _search_images_bing(query: str, limit: int = 5) -> list:
    resp = _req_get(
        "https://www.bing.com/images/search",
        params={"q": query, "first": 0, "count": limit},
        timeout=15,
    )
    if resp.status_code != 200:
        raise ValueError("Bing Images: لا استجابة")
    matches = re.findall(r'"murl":"([^"]+)"', resp.text)
    if not matches:
        matches = re.findall(r'<img[^>]+src="(https?://[^"]+)"', resp.text)
    return [m for m in matches if not "bing.com" in m][:limit]


def _search_images_ddg(query: str, limit: int = 5) -> list:
    try:
        from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            results = list(ddgs.images(query, max_results=limit))
        return [img["image"] for img in results if img.get("image")]
    except ImportError:
        raise ValueError("duckduckgo_search غير مثبت")
    except Exception as e:
        raise ValueError(f"DuckDuckGo Images: {e}")


def _search_images_pixabay(query: str, limit: int = 5) -> list:
    # مفتاح عام للتجربة – استبدله بمفتاحك
    resp = _req_get(
        "https://pixabay.com/api/",
        params={"key": "25564984-2e3f8b5f6b6f6e5e5e5e5e5e5", "q": query,
                "image_type": "photo", "per_page": limit},
        timeout=15,
    )
    if resp.status_code != 200:
        raise ValueError("Pixabay: لا استجابة")
    return [img["webformatURL"] for img in resp.json().get("hits", [])][:limit]


def _search_images_unsplash(query: str, limit: int = 5) -> list:
    resp = _req_get(
        "https://unsplash.com/napi/search/photos",
        params={"query": query, "per_page": limit},
        headers=_get_headers({"Authorization": "Client-ID 2b9d8a4-placeholder"}),
        timeout=15,
    )
    if resp.status_code != 200:
        raise ValueError("Unsplash: لا استجابة")
    data = resp.json()
    return [p["urls"]["regular"] for p in data.get("results", [])][:limit]


IMAGE_SEARCH_METHODS = [
    _search_images_ddg,
    _search_images_bing,
    _search_images_pixabay,
    _search_images_unsplash,
]


def _download_image(url: str, out_dir: str) -> str:
    try:
        resp = _req_get(url, timeout=20)
        if resp.status_code != 200:
            return None
        ext = os.path.splitext(url.split("?")[0])[1].lower()
        if ext not in (".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"):
            ext = ".jpg"
        filepath = _get_temp_path("img", ext.lstrip("."))
        with open(filepath, "wb") as f:
            f.write(resp.content)
        if os.path.getsize(filepath) < 512:
            os.remove(filepath)
            return None
        return filepath
    except Exception:
        return None


# ═══════════════════════════════════════════════════════════════
#  دوال الانتحال
# ═══════════════════════════════════════════════════════════════

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
        except Exception:
            pass
        return {
            "name": name.strip() or "غير معروف",
            "first_name": user.first_name or "",
            "last_name": user.last_name or "",
            "bio": bio,
            "id": user.id,
        }
    except Exception:
        return None


async def change_profile_photo(client, user_id, phone):
    try:
        bio = io.BytesIO()
        await client.download_profile_photo(user_id, file=bio)
        bio.seek(0)
        if bio.getbuffer().nbytes == 0:
            return False, None
        uploaded = await client.upload_file(bio, file_name="photo.jpg")
        result = await client(UploadProfilePhotoRequest(file=uploaded))
        await asyncio.sleep(2)
        if hasattr(result, "photo") and hasattr(result.photo, "id"):
            return True, result.photo.id
        return True, None
    except FloodWaitError as e:
        await asyncio.sleep(e.seconds)
        try:
            bio = io.BytesIO()
            await client.download_profile_photo(user_id, file=bio)
            bio.seek(0)
            uploaded = await client.upload_file(bio, file_name="photo.jpg")
            result = await client(UploadProfilePhotoRequest(file=uploaded))
            await asyncio.sleep(2)
            if hasattr(result, "photo") and hasattr(result.photo, "id"):
                return True, result.photo.id
            return True, None
        except Exception:
            return False, None
    except Exception as e:
        logger.error(f"Photo change failed: {e}")
        return False, None


# ═══════════════════════════════════════════════════════════════
#  المعالجات الرئيسية
# ═══════════════════════════════════════════════════════════════

async def setup_handlers(client, phone):
    if phone not in muted_users:
        muted_users[phone] = {}
    if phone not in taqleed_users:
        taqleed_users[phone] = {}
    if phone not in ent7al_users:
        ent7al_users[phone] = False
    if phone not in ent7al_original:
        ent7al_original[phone] = {}

    # ─ـ التقليد ─ـ
    @client.on(events.NewMessage(incoming=True))
    async def auto_taqleed(event):
        if event.sender_id in taqleed_users.get(phone, {}) and event.text and not event.text.startswith("."):
            await asyncio.sleep(0.3)
            try:
                await event.reply(event.text)
            except Exception:
                pass

    @client.on(events.NewMessage(outgoing=True, pattern=r"^\.تقليد$"))
    async def taq(event):
        target = (
            (await event.get_reply_message()).sender_id
            if event.is_reply
            else event.chat_id if event.is_private else None
        )
        if target:
            taqleed_users[phone][target] = True
            await event.edit("**• يتم التقليد**")

    @client.on(events.NewMessage(outgoing=True, pattern=r"^\.غ تقليد$"))
    async def notaq(event):
        target = (
            (await event.get_reply_message()).sender_id
            if event.is_reply
            else event.chat_id if event.is_private else None
        )
        if target and target in taqleed_users.get(phone, {}):
            del taqleed_users[phone][target]
        await event.edit("**• تم فك التقليد**")

    # ─ـ الانتحال ─ـ
    @client.on(events.NewMessage(outgoing=True, pattern=r"^\.انتحال$"))
    async def ent7al(event):
        track_command(phone, ".انتحال")
        await event.edit("**• جاري الانتحال...**")
        target_user = None
        if event.is_reply:
            try:
                target_user = await client.get_entity((await event.get_reply_message()).sender_id)
            except Exception:
                pass
        elif event.is_private:
            try:
                target_user = await client.get_entity(event.chat_id)
            except Exception:
                pass
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
            "first_name": me.first_name or "",
            "last_name": me.last_name if me.last_name is not None else "",
            "photo_bytes": None,
            "added_photo_id": None,
            "about": "",
        }
        try:
            fu = await client(GetFullUserRequest("me"))
            if fu.full_user.about:
                original["about"] = fu.full_user.about
        except Exception:
            pass
        name_ok = False
        try:
            await client(UpdateProfileRequest(first_name=target_info["first_name"], last_name=target_info["last_name"]))
            await asyncio.sleep(1)
            name_ok = True
        except FloodWaitError as e:
            await asyncio.sleep(e.seconds)
            try:
                await client(UpdateProfileRequest(first_name=target_info["first_name"], last_name=target_info["last_name"]))
                name_ok = True
            except Exception:
                pass
        except Exception:
            pass
        bio_ok = False
        try:
            await client(UpdateProfileRequest(about=target_info["bio"][:70] if target_info["bio"] else ""))
            await asyncio.sleep(0.5)
            bio_ok = True
        except FloodWaitError as e:
            await asyncio.sleep(e.seconds)
            try:
                await client(UpdateProfileRequest(about=target_info["bio"][:70] if target_info["bio"] else ""))
                bio_ok = True
            except Exception:
                pass
        except Exception:
            pass
        photo_ok, added_id = await change_profile_photo(client, target_user.id, phone)
        if photo_ok and added_id:
            original["added_photo_id"] = added_id
        ent7al_original[phone] = original
        ent7al_users[phone] = True
        if name_ok and bio_ok and photo_ok:
            await event.edit("**• تم الانتحال**")
        elif not name_ok and not bio_ok and not photo_ok:
            await event.edit("**• فشل الانتحال**")
        else:
            await event.edit("**• تم الانتحال جزئياً**")

    @client.on(events.NewMessage(outgoing=True, pattern=r"^\.الغاء انتحال$"))
    async def unent7al(event):
        track_command(phone, ".الغاء انتحال")
        await event.edit("**• جاري إلغاء الانتحال...**")
        if not ent7al_users.get(phone) or not ent7al_original.get(phone):
            await event.edit("**• لا يوجد انتحال**")
            return
        original = ent7al_original[phone]
        first, last = original.get("first_name", ""), original.get("last_name", "")
        restored_name = False
        for attempt in range(3):
            try:
                await client(UpdateProfileRequest(first_name=first, last_name=last))
                await asyncio.sleep(1.5)
                me_now = await client.get_me()
                if me_now.first_name == first and (me_now.last_name or "") == last:
                    restored_name = True
                    break
            except FloodWaitError as e:
                await asyncio.sleep(e.seconds)
            except Exception as e:
                logger.error(f"Restore name attempt {attempt + 1}: {e}")
                await asyncio.sleep(1)
        if not restored_name:
            logger.error(f"Could not fully restore name for {phone}")
        if original.get("added_photo_id"):
            try:
                await client(DeletePhotosRequest(id=[InputPhoto(id=original["added_photo_id"], access_hash=0, file_reference=b"")]))
                await asyncio.sleep(2)
            except FloodWaitError as e:
                await asyncio.sleep(e.seconds)
            except Exception as e:
                logger.error(f"Failed to delete added photo: {e}")
        else:
            try:
                current_photos = await client.get_profile_photos("me", limit=1)
                if current_photos:
                    await client(DeletePhotosRequest(id=[InputPhoto(id=current_photos[0].id, access_hash=current_photos[0].access_hash, file_reference=current_photos[0].file_reference)]))
                await asyncio.sleep(2)
            except Exception as e:
                logger.error(f"Fallback photo deletion failed: {e}")
        try:
            await client(UpdateProfileRequest(about=original.get("about", "")))
        except FloodWaitError as e:
            await asyncio.sleep(e.seconds)
        except Exception as e:
            logger.error(f"Restore bio failed: {e}")
        ent7al_users[phone] = False
        ent7al_original[phone] = {}
        await event.edit("**• تم إلغاء الانتحال**")

    # ─ـ إضافة أعضاء ─ـ
    @client.on(events.NewMessage(outgoing=True, pattern=r"^\.اضافة (\d+) (@?\w+)$"))
    async def add_members_from_group(event):
        if not event.is_group:
            await event.edit("**• الأمر يعمل في المجموعات فقط**")
            return
        count = int(event.pattern_match.group(1))
        target_username = event.pattern_match.group(2).strip()
        await event.edit(f"**• جاري سحب {count} عضو من {target_username} وإضافتهم هنا...**")
        try:
            source_group = await client.get_entity(target_username)
        except Exception:
            await event.edit(f"**• لم يتم العثور على الجروب {target_username}**")
            return
        try:
            await client.join_channel(source_group)
            await asyncio.sleep(3)
        except Exception:
            pass
        added = failed = 0
        try:
            async for user in client.iter_participants(source_group, limit=count):
                if user.bot or user.deleted:
                    continue
                try:
                    if hasattr(event.chat, "megagroup") and event.chat.megagroup:
                        await client(InviteToChannelRequest(channel=event.chat_id, users=[user.id]))
                    else:
                        await client(AddChatUserRequest(chat_id=event.chat_id, user_id=user.id, fwd_limit=10))
                    added += 1
                    await asyncio.sleep(1.5)
                except FloodWaitError as e:
                    await asyncio.sleep(e.seconds)
                    try:
                        if hasattr(event.chat, "megagroup") and event.chat.megagroup:
                            await client(InviteToChannelRequest(channel=event.chat_id, users=[user.id]))
                        else:
                            await client(AddChatUserRequest(chat_id=event.chat_id, user_id=user.id, fwd_limit=10))
                        added += 1
                    except Exception:
                        failed += 1
                except ChatAdminRequiredError:
                    await event.edit("**• الصلاحيات غير كافية - يجب أن تكون مشرفًا**")
                    return
                except Exception as e:
                    failed += 1
                    if "PEER_FLOOD" in str(e) or "USER_PRIVACY_RESTRICTED" in str(e):
                        break
            msg = f"**• تمت إضافة {added} عضو بنجاح**"
            if failed:
                msg += f"\n• فشل في إضافة {failed} عضو"
            await event.edit(msg)
        except ChatAdminRequiredError:
            await event.edit("**• لا تملك صلاحيات لسحب الأعضاء**")
        except Exception as e:
            await event.edit(f"**• فشل: {str(e)[:50]}**")

    # ─ـ نسخ الصوت ─ـ
    @client.on(events.NewMessage(outgoing=True, pattern=r"^\.نسخ$"))
    async def transcribe_voice(event):
        if not event.is_reply:
            await event.edit("**• يرجى الرد على رسالة صوتية أو فيديو**")
            return
        reply = await event.get_reply_message()
        if not reply.voice and not reply.audio and not reply.video:
            await event.edit("**• الرد على رسالة صوتية أو فيديو فقط**")
            return
        await event.edit("**• جاري تحويل المقطع إلى نص...**")
        try:
            import speech_recognition as sr
        except ImportError:
            await event.edit("**• مكتبة SpeechRecognition غير مثبتة**")
            return
        voice_path = os.path.join(TEMP_DIR, f"voice_{phone}_{reply.id}.ogg")
        wav_path = voice_path.replace(".ogg", ".wav")
        await client.download_media(reply, voice_path)
        try:
            subprocess.run(["ffmpeg", "-i", voice_path, "-ac", "1", "-ar", "16000", wav_path],
                           check=True, capture_output=True, timeout=30)
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

    # ─ـ استيكر / صورة ─ـ
    @client.on(events.NewMessage(outgoing=True, pattern=r"^\.استيك$"))
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
            im = Image.open(img_path).convert("RGBA")
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

    @client.on(events.NewMessage(outgoing=True, pattern=r"^\.بيك$"))
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

    # ─ـ تحميل الصور (بن) ─ـ
    @client.on(events.NewMessage(outgoing=True, pattern=r"^\.بن (.+)"))
    async def image_search_download(event):
        query = event.pattern_match.group(1).strip()
        loop = asyncio.get_event_loop()

        if query.startswith("http"):
            await event.edit("**• 📷 جاري تحميل الصورة...**")
            try:
                filepath = await loop.run_in_executor(_DOWNLOAD_EXECUTOR, _download_image, query, TEMP_DIR)
                if filepath:
                    await client.send_file(event.chat_id, filepath)
                    await event.delete()
                    os.remove(filepath)
                else:
                    await event.edit("**• فشل تحميل الصورة**")
            except Exception as e:
                await event.edit(f"**• فشل: {str(e)[:100]}**")
            return

        await event.edit("**• 🔍 جاري البحث عن صور...**")
        urls = []
        for finder in IMAGE_SEARCH_METHODS:
            try:
                urls = await loop.run_in_executor(_DOWNLOAD_EXECUTOR, finder, query, 5)
                if urls:
                    break
            except Exception:
                continue

        if not urls:
            await event.edit("**• لم يتم العثور على صور**")
            return

        downloaded = []
        for url in urls[:3]:
            path = await loop.run_in_executor(_DOWNLOAD_EXECUTOR, _download_image, url, TEMP_DIR)
            if path:
                downloaded.append(path)

        if not downloaded:
            await event.edit("**• فشل تحميل الصور**")
            return

        for path in downloaded:
            await client.send_file(event.chat_id, path)
            os.remove(path)
        await event.delete()

    # ─ـ تحميل صوت (يوت) ─ـ
    @client.on(events.NewMessage(outgoing=True, pattern=r"^\.يوت (.+)"))
    async def youtube_audio(event):
        query = event.pattern_match.group(1).strip()
        loop = asyncio.get_event_loop()
        filepath = None
        try:
            info, filepath = await _smart_download(query, True, event, loop)
            title = info.get("title", "بدون عنوان")
            if len(title) > 55:
                title = title[:52] + "..."
            dur = format_duration(info.get("duration", 0))
            caption = f"{title}\n• {dur} | ᥲᥙძᎥ᥆"
            await client.send_file(
                event.chat_id, filepath,
                caption=caption,
                attributes=[DocumentAttributeAudio(
                    duration=info.get("duration", 0),
                    title=title,
                    performer=info.get("uploader", ""),
                )],
            )
            await event.delete()
        except Exception as e:
            await event.edit(f"**• فشل التحميل:**\n{str(e)[:300]}")
        finally:
            if filepath and os.path.exists(filepath):
                try:
                    os.remove(filepath)
                except Exception:
                    pass

    # ─ـ تحميل فيديو (فيد) ─ـ
    @client.on(events.NewMessage(outgoing=True, pattern=r"^\.فيد (.+)"))
    async def video_download(event):
        query = event.pattern_match.group(1).strip()
        loop = asyncio.get_event_loop()
        filepath = None
        try:
            info, filepath = await _smart_download(query, False, event, loop)
            title = info.get("title", "بدون عنوان")
            if len(title) > 55:
                title = title[:52] + "..."
            dur = format_duration(info.get("duration", 0))
            caption = f"{title}\n• {dur} | ᥎Ꭵძꫀ᥆"
            await client.send_file(
                event.chat_id, filepath,
                caption=caption,
                attributes=[DocumentAttributeVideo(
                    duration=info.get("duration", 0),
                    w=0, h=0,
                    supports_streaming=True,
                )],
            )
            await event.delete()
        except Exception as e:
            await event.edit(f"**• فشل التحميل:**\n{str(e)[:300]}")
        finally:
            if filepath and os.path.exists(filepath):
                try:
                    os.remove(filepath)
                except Exception:
                    pass

    # ─ـ مراقبة الخاص ─ـ
    message_cache = {}

    @client.on(events.NewMessage(incoming=True, func=lambda e: e.is_private and not e.out))
    async def cache_private_message(event):
        if event.sender_id == (await client.get_me()).id:
            return
        message_cache.setdefault(event.chat_id, {})[event.id] = event.text or "<وسائط>"

    @client.on(events.MessageEdited(incoming=True, func=lambda e: e.is_private and not e.out))
    async def notify_edit(event):
        if event.sender_id == (await client.get_me()).id:
            return
        user = await event.get_sender()
        name = user.first_name or ""
        if user.last_name:
            name += f" {user.last_name}"
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
                except Exception:
                    pass
                await client.send_message("me", f"**قام المستخدم {user_name} بحذف الرسالة**\n**{old_text}**")
                if chat_id in message_cache and msg_id in message_cache[chat_id]:
                    del message_cache[chat_id][msg_id]

    logger.info(f"All handlers ready for {phone}")
