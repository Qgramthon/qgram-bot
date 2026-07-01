# Ultimate NinjaGram Pro Max Ultra Bot
import asyncio, uuid, os, re, random, string, aiohttp, json, time, sys
from datetime import datetime
from urllib.parse import quote, urlencode
from telethon import TelegramClient, events, Button, functions, types
from telethon.errors import *
from telethon.tl.functions.channels import InviteToChannelRequest, JoinChannelRequest
from telethon.tl.functions.messages import ImportChatInviteRequest
from collections import Counter, defaultdict, deque
import hashlib, base64, struct
from typing import Optional, Dict, List, Set, Tuple, Any
from dataclasses import dataclass, field
import logging
from concurrent.futures import ThreadPoolExecutor

# ============================================
# استيراد الإعدادات من ملف الشيرد
# ============================================
# تحميل متغيرات البيئة من الشيرد
DATA_DIR = '/data' if os.path.exists('/data') else '.'
os.makedirs(DATA_DIR, exist_ok=True)

# استيراد المتغيرات من الشيرد مباشرة
BOT_TOKEN = '7998616214:AAFGroKKmwnrOtyAeJIHmrs_bKW5jXl0B20'
BOT_API_ID = 2040
BOT_API_HASH = 'b18441a1ff607e10a989891a5462e627'
DEV_USER_ID = 6443238809

# ============================================
# تهيئة متقدمة
# ============================================
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

bot = TelegramClient(f'bot_session_{uuid.uuid4().hex[:6]}', BOT_API_ID, BOT_API_HASH)
START_IMAGE = "start.jpg"
allowed_chats: Set[int] = set()
user_states: Dict[int, str] = {}
pending_data: Dict[int, Dict] = {}
rate_limiter: Dict[int, deque] = defaultdict(lambda: deque(maxlen=10))
CACHE_TTL = 300  # 5 دقائق
username_cache: Dict[str, Tuple[float, Optional[str]]] = {}
thread_pool = ThreadPoolExecutor(max_workers=20)

# ============================================
# دالة التحقق من المطور (متوافقة مع الشيرد)
# ============================================
def is_dev(user_id: int) -> bool:
    """التحقق من صلاحيات المطور"""
    return user_id == DEV_USER_ID

# ============================================
# دالة لوحة تحكم المطور
# ============================================
def dev_panel_markup():
    """أزرار لوحة تحكم المطور"""
    return [
        [Button.inline("📊 إحصائيات البوت", b"bot_stats"),
         Button.inline("👥 المستخدمين", b"bot_users")],
        [Button.inline("📢 إرسال رسالة للكل", b"broadcast_start"),
         Button.inline("⚙️ إعدادات متقدمة", b"advanced_settings")],
        [Button.inline("🔙 القائمة الرئيسية", b"back_main")],
    ]

# ============================================
# هيكل البيانات المتقدم
# ============================================
@dataclass
class HuntConfig:
    platforms: List[str] = field(default_factory=lambda: ["tg", "ig", "tk", "fb", "gh", "x"])
    min_length: int = 3
    max_length: int = 15
    count: int = 500
    use_ai: bool = True
    semantic_check: bool = True
    parallel_checks: int = 50

@dataclass
class UsernameResult:
    username: str
    platform: str
    available: bool
    quality_score: float = 0.0
    length: int = 0
    pattern: str = ""
    timestamp: float = field(default_factory=time.time)

# ============================================
# نظام توليد يوزرات ذكي متعدد الاستراتيجيات
# ============================================
class SmartUsernameGenerator:
    """مولد يوزرات ذكي يستخدم 15 استراتيجية مختلفة"""
    
    VOWELS = "AEIOU"
    CONSONANTS = "BCDFGHJKLMNPQRSTVWXYZ"
    NUMBERS = "0123456789"
    LUCKY = ["777", "888", "999", "111", "333", "555", "666", "222", "444"]
    
    PREMIUM_WORDS = [
        "KING", "QUEEN", "BOSS", "GOD", "LEO", "ACE", "PRO", "VIP", "ELITE",
        "GOLD", "ICE", "FIRE", "WOLF", "LION", "BEAR", "HAWK", "STAR", "MOON",
        "NOVA", "ZEN", "LEGEND", "MYTH", "ICON", "TITAN", "GHOST", "DEMON",
        "ANGEL", "NINJA", "SAMURAI", "PHANTOM", "SHADOW", "STORM", "THUNDER"
    ]
    
    TRENDING_PREFIXES = ["x", "z", "v", "q", "nft", "web3", "ai", "defi", "dao", "meta"]
    TRENDING_SUFFIXES = ["eth", "sol", "btc", "nft", "dao", "ai", "xyz", "io", "gg", "wtf"]
    
    @classmethod
    def generate_pool(cls, count: int = 500, platform: str = "tg") -> List[str]:
        """توليد مجموعة يوزرات باستخدام كل الاستراتيجيات"""
        strategies = [
            cls._pattern_based, cls._vowel_consonant, cls._lucky_numbers,
            cls._premium_words, cls._trending_crypto, cls._minimalist,
            cls._double_letters, cls._palindrome, cls._numeric_rare,
            cls._word_combination, cls._leet_speak, cls._brandable,
            cls._aesthetic, cls._emoji_inspired, cls._short_premium
        ]
        
        pool = set()
        weights = [3, 3, 2, 4, 3, 2, 2, 1, 2, 3, 1, 3, 2, 1, 5]
        
        for strategy, weight in zip(strategies, weights):
            try:
                results = strategy(count // len(strategies) * weight)
                pool.update(results)
            except Exception as e:
                logger.error(f"Strategy error: {e}")
        
        pool = {u for u in pool if 3 <= len(u) <= 15}
        return sorted(list(pool), key=lambda x: cls._quality_score(x), reverse=True)[:count]
    
    @classmethod
    def _quality_score(cls, username: str) -> float:
        """تقييم جودة اليوزر"""
        score = 0.0
        length = len(username)
        
        if 4 <= length <= 8:
            score += 3
        elif length <= 12:
            score += 1
        
        if any(num in username for num in cls.LUCKY[:5]):
            score += 2
        
        if re.search(r'(.)\1', username):
            score += 1.5
        
        letters = sum(c.isalpha() for c in username)
        digits = sum(c.isdigit() for c in username)
        if letters > 0 and digits > 0:
            ratio = letters / max(digits, 1)
            if 1 <= ratio <= 4:
                score += 2
        
        for word in cls.PREMIUM_WORDS:
            if word in username.upper():
                score += 5
                break
        
        return score
    
    @classmethod
    def _pattern_based(cls, count: int) -> Set[str]:
        patterns = set()
        vowels, consonants = cls.VOWELS, cls.CONSONANTS
        nums = cls.NUMBERS
        
        for _ in range(count):
            c1, c2 = random.choice(consonants), random.choice(consonants)
            v1, v2 = random.choice(vowels), random.choice(vowels)
            n1, n2 = random.choice("1379"), random.choice("02468")
            
            patterns.update([
                f"{c1}{v1}{c2}", f"{v1}{c1}{v2}",
                f"{c1}{n1}{c2}", f"{n1}{c1}{n2}",
                f"{c1}{v1}{n1}", f"{n1}{v1}{c1}",
                f"{c1}{c2}{n1}{n2}", f"{n1}{n2}{c1}{c2}",
                f"{v1}{c1}{n1}{n2}", f"{c1}{v1}{c2}{n1}"
            ])
        return patterns
    
    @classmethod
    def _vowel_consonant(cls, count: int) -> Set[str]:
        patterns = set()
        for _ in range(count):
            c = random.choice(cls.CONSONANTS)
            v = random.choice(cls.VOWELS)
            d = random.choice("1379")
            patterns.update([f"{c}{v}{d}", f"{d}{c}{v}", f"{c}{d}{v}", f"{v}{d}{c}"])
        return patterns
    
    @classmethod
    def _lucky_numbers(cls, count: int) -> Set[str]:
        patterns = set()
        for _ in range(count):
            lucky = random.choice(cls.LUCKY)
            letter = random.choice(cls.CONSONANTS + cls.VOWELS)
            patterns.update([f"{lucky}{letter}", f"{letter}{lucky}", f"{lucky}{letter}{letter}"])
        return patterns
    
    @classmethod
    def _premium_words(cls, count: int) -> Set[str]:
        patterns = set()
        for _ in range(count):
            word = random.choice(cls.PREMIUM_WORDS)
            suffix = random.choice([random.choice(cls.NUMBERS), random.choice(cls.CONSONANTS), ""])
            prefix = random.choice([random.choice(cls.CONSONANTS), ""])
            patterns.update([f"{word}{suffix}", f"{prefix}{word}", f"{word}{random.choice(cls.LUCKY)}"])
        return patterns
    
    @classmethod
    def _trending_crypto(cls, count: int) -> Set[str]:
        patterns = set()
        for _ in range(count):
            pref = random.choice(cls.TRENDING_PREFIXES)
            suff = random.choice(cls.TRENDING_SUFFIXES)
            num = random.choice("1379")
            patterns.update([f"{pref}{suff}", f"{pref}{num}{suff}", f"{pref}_{suff}"])
        return patterns
    
    @classmethod
    def _minimalist(cls, count: int) -> Set[str]:
        patterns = set()
        chars = cls.CONSONANTS + cls.VOWELS
        for _ in range(count):
            patterns.update([f"{random.choice(chars)}{random.choice(chars)}",
                           f"{random.choice(chars)}{random.choice(chars)}{random.choice(chars)}"])
        return patterns
    
    @classmethod
    def _double_letters(cls, count: int) -> Set[str]:
        patterns = set()
        for _ in range(count):
            c = random.choice(cls.CONSONANTS + cls.VOWELS)
            v = random.choice(cls.VOWELS)
            patterns.update([f"{c}{c}{v}", f"{v}{c}{c}", f"{c}{c}{c}", f"{c}{c}{random.choice(cls.LUCKY)}"])
        return patterns
    
    @classmethod
    def _palindrome(cls, count: int) -> Set[str]:
        patterns = set()
        for _ in range(count):
            c1, c2 = random.choice(cls.CONSONANTS), random.choice(cls.CONSONANTS)
            v = random.choice(cls.VOWELS)
            patterns.update([f"{c1}{v}{c1}", f"{c1}{c2}{c2}{c1}", f"{c1}{c2}{v}{c2}{c1}"])
        return patterns
    
    @classmethod
    def _numeric_rare(cls, count: int) -> Set[str]:
        patterns = set()
        for _ in range(count):
            chars = random.choices(cls.CONSONANTS + cls.VOWELS, k=2)
            rare = random.choice(["69", "420", "007", "911", "1337", "404", "101"])
            patterns.update([f"{chars[0]}{rare}", f"{rare}{chars[0]}", f"{chars[0]}{chars[1]}{rare}"])
        return patterns
    
    @classmethod
    def _word_combination(cls, count: int) -> Set[str]:
        patterns = set()
        pairs = [("ICE", "FIRE"), ("MOON", "STAR"), ("WOLF", "HAWK"), ("ZEN", "NOVA"),
                 ("GOLD", "ACE"), ("NIGHT", "DAY"), ("DARK", "LIGHT"), ("BLACK", "WHITE")]
        for _ in range(count):
            w1, w2 = random.choice(pairs)
            patterns.update([f"{w1}{w2}", f"{w1}_{w2}", f"{w1}{random.choice(cls.LUCKY)}"])
        return patterns
    
    @classmethod
    def _leet_speak(cls, count: int) -> Set[str]:
        leet_map = {'A': '4', 'E': '3', 'I': '1', 'O': '0', 'S': '5', 'T': '7'}
        patterns = set()
        for _ in range(count):
            word = random.choice(cls.PREMIUM_WORDS)
            leet = ''.join(leet_map.get(c, c) for c in word)
            if leet != word:
                patterns.add(leet)
        return patterns
    
    @classmethod
    def _brandable(cls, count: int) -> Set[str]:
        patterns = set()
        syllables = ["ly", "fy", "io", "ia", "eo", "ux", "ix", "ox", "ex", "um", "on", "is"]
        for _ in range(count):
            s1, s2 = random.sample(syllables, 2)
            patterns.update([f"{s1}{s2}", f"{s1}{s2}{random.choice('1379')}"])
        return patterns
    
    @classmethod
    def _aesthetic(cls, count: int) -> Set[str]:
        patterns = set()
        aesthetic_chars = "xzvq"
        for _ in range(count):
            c = random.choice(aesthetic_chars)
            v = random.choice(cls.VOWELS)
            patterns.update([f"{c}{v}{c}", f"{c}{c}{v}", f"{v}{c}{c}", f"{c}{random.choice(cls.LUCKY)}"])
        return patterns
    
    @classmethod
    def _emoji_inspired(cls, count: int) -> Set[str]:
        emoji_words = ["fire", "ice", "star", "moon", "crown", "gem", "bolt", "wave", 
                       "flame", "crystal", "diamond", "spark", "glow", "shine", "flash"]
        patterns = set()
        for _ in range(count):
            word = random.choice(emoji_words)
            num = random.choice("1379")
            patterns.update([f"{word.upper()}{num}", f"{num}{word.upper()}", word.upper()])
        return patterns
    
    @classmethod
    def _short_premium(cls, count: int) -> Set[str]:
        patterns = set()
        for _ in range(count):
            c1, c2 = random.choice(cls.CONSONANTS), random.choice(cls.CONSONANTS)
            v = random.choice(cls.VOWELS)
            lucky = random.choice(cls.LUCKY)
            patterns.update([f"{c1}{v}", f"{c1}{c2}", f"{c1}{lucky}", f"{lucky}{c1}", f"{c1}{v}{lucky}"])
        return patterns

# ============================================
# نظام فحص متقدم متعدد المنصات
# ============================================
class UltimateUsernameChecker:
    """نظام فحص يوزرات متعدد المنصات مع كاش وتوازن تحميل"""
    
    USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0.0.0",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/119.0.0.0",
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15",
        "Mozilla/5.0 (Android 14; Mobile; rv:120.0) Gecko/120.0 Firefox/120.0"
    ]
    
    CHECK_URLS = {
        "tg": [
            "https://t.me/{username}",
            "https://fragment.com/username/{username}"
        ],
        "ig": [
            "https://www.instagram.com/{username}/",
            "https://i.instagram.com/api/v1/users/web_profile_info/?username={username}"
        ],
        "tk": [
            "https://www.tiktok.com/@{username}",
            "https://www.tiktok.com/api/user/detail/?uniqueId={username}"
        ],
        "fb": [
            "https://www.facebook.com/{username}",
            "https://mbasic.facebook.com/{username}"
        ],
        "gh": [
            "https://github.com/{username}",
            "https://api.github.com/users/{username}"
        ],
        "x": [
            "https://x.com/{username}",
            "https://twitter.com/{username}"
        ]
    }
    
    @classmethod
    async def check_availability(cls, username: str, platform: str, session: aiohttp.ClientSession, sem: asyncio.Semaphore) -> Optional[UsernameResult]:
        """فحص يوزر مع كاش متقدم"""
        cache_key = f"{platform}:{username.lower()}"
        
        if cache_key in username_cache:
            timestamp, result = username_cache[cache_key]
            if time.time() - timestamp < CACHE_TTL:
                return UsernameResult(username, platform, result is not None, 0, len(username)) if result else None
        
        async with sem:
            try:
                headers = {
                    'User-Agent': random.choice(cls.USER_AGENTS),
                    'Accept': 'text/html,application/json',
                    'Accept-Language': 'en-US,en;q=0.9',
                    'Cache-Control': 'no-cache'
                }
                
                urls = cls.CHECK_URLS.get(platform, [])
                available = False
                
                for url_template in urls:
                    url = url_template.format(username=username.lower())
                    try:
                        async with session.get(url, headers=headers, timeout=8, allow_redirects=True) as resp:
                            if platform == "tg":
                                available = await cls._check_telegram(resp, username)
                            elif platform == "ig":
                                available = await cls._check_instagram(resp)
                            elif platform == "tk":
                                available = await cls._check_tiktok(resp)
                            elif platform == "gh":
                                available = await cls._check_github(resp)
                            elif platform == "x":
                                available = await cls._check_twitter(resp)
                            elif platform == "fb":
                                available = await cls._check_facebook(resp)
                            
                            if available:
                                break
                    except:
                        continue
                
                username_cache[cache_key] = (time.time(), username if available else None)
                
                if available:
                    quality = SmartUsernameGenerator._quality_score(username)
                    return UsernameResult(
                        username=username,
                        platform=platform,
                        available=True,
                        quality_score=quality,
                        length=len(username)
                    )
                
            except Exception as e:
                logger.debug(f"Check error {platform}:{username} - {e}")
        
        return None
    
    @classmethod
    async def _check_telegram(cls, resp, username: str) -> bool:
        """فحص تيليجرام متقدم"""
        if resp.status == 404:
            return True
        if resp.status == 200:
            text = await resp.text()
            if any(x in text.lower() for x in ['tgme_page_extra', 'join tg', 'you can contact']):
                return False
            if 'fragment.com' in str(resp.url):
                if 'status' in text.lower() and 'unavailable' in text.lower():
                    return False
                if 'ton' in text.lower() and ('buy' in text.lower() or 'auction' in text.lower()):
                    return False
                return True
            if 'tgme_page_title' in text:
                return False
            return True
        return False
    
    @classmethod
    async def _check_instagram(cls, resp) -> bool:
        if resp.status == 404:
            return True
        if resp.status == 200:
            try:
                data = await resp.json()
                return data.get('status') == 'fail'
            except:
                text = await resp.text()
                return 'page isn' in text.lower() or 'not found' in text.lower()
        return False
    
    @classmethod
    async def _check_tiktok(cls, resp) -> bool:
        if resp.status == 404:
            return True
        if resp.status == 200:
            text = await resp.text()
            return 'couldn\'t find' in text.lower() or 'not found' in text.lower()
        return False
    
    @classmethod
    async def _check_github(cls, resp) -> bool:
        return resp.status == 404
    
    @classmethod
    async def _check_twitter(cls, resp) -> bool:
        if resp.status == 404:
            return True
        if resp.status == 200:
            text = await resp.text()
            return 'doesn\'t exist' in text.lower() or 'not found' in text.lower()
        return False
    
    @classmethod
    async def _check_facebook(cls, resp) -> bool:
        if resp.status == 404:
            return True
        return False

# ============================================
# نظام تحميل فيديو متعدد المصادر
# ============================================
class UltimateVideoDownloader:
    """نظام تحميل فيديوهات من 10+ منصات"""
    
    APIS = {
        "tiktok": [
            "https://tikwm.com/api/?url={url}",
            "https://api.tikmate.app/api/lookup?url={url}",
            "https://www.tikwm.com/api/?url={url}"
        ],
        "instagram": [
            "https://api.instasave.io/v1/media?url={url}",
            "https://instasave.io/api/media?url={url}"
        ],
        "youtube": [
            "https://api.yt-dl.org/api/youtube?url={url}",
            "https://yt-api.p.rapidapi.com/dl?id={url}"
        ],
        "facebook": [
            "https://api.fbdown.net/api/download?url={url}",
            "https://fbdownloader.io/api/video?url={url}"
        ],
        "twitter": [
            "https://api.twittervideodownloader.com/api/download?url={url}"
        ],
        "pinterest": [
            "https://api.pinterestdownloader.io/api/download?url={url}"
        ],
        "likee": [
            "https://api.likeedownloader.com/api/download?url={url}"
        ],
        "snapchat": [
            "https://api.snapdown.net/api/download?url={url}"
        ]
    }
    
    @classmethod
    async def download(cls, url: str, platform: str) -> Dict:
        """تحميل فيديو مع تجربة APIs متعددة"""
        apis = cls.APIS.get(platform, [])
        
        async with aiohttp.ClientSession() as session:
            for api_url_template in apis:
                try:
                    api_url = api_url_template.format(url=quote(url))
                    async with session.get(api_url, timeout=20) as resp:
                        data = await resp.json()
                        
                        result = cls._parse_response(data, platform)
                        if result.get("success"):
                            return result
                except:
                    continue
        
        return {"success": False, "error": "تعذر التحميل من جميع المصادر"}
    
    @classmethod
    def _parse_response(cls, data: Dict, platform: str) -> Dict:
        if platform == "tiktok":
            video_url = (data.get("data", {}).get("play") or 
                        data.get("video") or 
                        data.get("download_url"))
            if video_url:
                return {
                    "success": True,
                    "video_url": video_url,
                    "title": data.get("data", {}).get("title", ""),
                    "duration": data.get("data", {}).get("duration", 0),
                    "platform": "تيكتوك"
                }
        
        elif platform == "instagram":
            video_url = (data.get("video_url") or 
                        data.get("media", [{}])[0].get("url") if data.get("media") else None)
            if video_url:
                return {"success": True, "video_url": video_url, "platform": "انستجرام"}
        
        elif platform == "youtube":
            formats = data.get("formats", [])
            if formats:
                best = max(formats, key=lambda x: x.get("quality", 0) if isinstance(x.get("quality"), int) else 0)
                return {"success": True, "video_url": best.get("url"), "platform": "يوتيوب"}
        
        return {"success": False}

# ============================================
# نظام معلومات الحساب المتقدم
# ============================================
class AccountInfoFetcher:
    """جالب معلومات حسابات متقدم"""
    
    @classmethod
    async def get_telegram_info(cls, username: str) -> Dict:
        """معلومات حساب تيليجرام مفصلة"""
        try:
            async with aiohttp.ClientSession() as session:
                headers = {'User-Agent': random.choice(UltimateUsernameChecker.USER_AGENTS)}
                
                async with session.get(f"https://t.me/{username}", headers=headers, timeout=10) as resp:
                    text = await resp.text()
                
                info = {"username": username, "exists": resp.status == 200}
                
                if info["exists"]:
                    title_match = re.search(r'<meta property="og:title" content="([^"]+)"', text)
                    image_match = re.search(r'<meta property="og:image" content="([^"]+)"', text)
                    desc_match = re.search(r'<meta property="og:description" content="([^"]+)"', text)
                    
                    info["display_name"] = title_match.group(1) if title_match else username
                    info["profile_image"] = image_match.group(1) if image_match else None
                    info["bio"] = desc_match.group(1) if desc_match else ""
                    
                    info["is_verified"] = "verified" in text.lower()
                    info["is_premium"] = "premium" in text.lower()
                    
                    subs_match = re.search(r'(\d+[,\s]*\d*)\s*(subscribers|مشترك)', text, re.IGNORECASE)
                    if subs_match:
                        info["subscribers"] = subs_match.group(1)
                
                return info
        except:
            return {"exists": False, "error": "فشل جلب المعلومات"}
    
    @classmethod
    async def get_instagram_info(cls, username: str) -> Dict:
        """معلومات حساب انستجرام"""
        try:
            async with aiohttp.ClientSession() as session:
                headers = {
                    'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X)',
                    'X-Requested-With': 'XMLHttpRequest'
                }
                url = f"https://www.instagram.com/{username}/?__a=1"
                async with session.get(url, headers=headers, timeout=10) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        user = data.get("graphql", {}).get("user", {})
                        return {
                            "exists": True,
                            "username": user.get("username"),
                            "full_name": user.get("full_name"),
                            "followers": user.get("edge_followed_by", {}).get("count", 0),
                            "following": user.get("edge_follow", {}).get("count", 0),
                            "posts": user.get("edge_owner_to_timeline_media", {}).get("count", 0),
                            "is_verified": user.get("is_verified", False),
                            "is_private": user.get("is_private", False),
                            "profile_image": user.get("profile_pic_url_hd"),
                            "bio": user.get("biography", "")
                        }
        except:
            pass
        return {"exists": False}

# ============================================
# نظام الحماية ومكافحة السبام
# ============================================
class SecuritySystem:
    """نظام حماية متقدم"""
    
    @classmethod
    def check_rate_limit(cls, user_id: int, action: str, max_per_minute: int = 10) -> bool:
        """فحص معدل الاستخدام"""
        now = time.time()
        key = f"{user_id}:{action}"
        if key not in rate_limiter:
            rate_limiter[key] = deque(maxlen=max_per_minute)
        user_requests = rate_limiter[key]
        
        while user_requests and user_requests[0] < now - 60:
            user_requests.popleft()
        
        if len(user_requests) >= max_per_minute:
            return False
        
        user_requests.append(now)
        return True
    
    @classmethod
    def validate_url(cls, url: str) -> bool:
        """تحقق من صحة الرابط"""
        url_pattern = re.compile(
            r'^(https?://)?'
            r'([\w\-]+\.)+[\w\-]+'
            r'(/[\w\-./?%&=]*)?$'
        )
        return bool(url_pattern.match(url))

# ============================================
# واجهة المستخدم المتطورة
# ============================================
class UIManager:
    """مدير واجهة المستخدم"""
    
    @classmethod
    def main_menu(cls):
        return [
            [Button.inline(f"🎯 صيد يوزرات ذكي", b"hunt_menu"),
             Button.inline(f"🎬 تحميل فيديو", b"video_menu")],
            [Button.inline(f"🔍 معلومات حساب", b"info_menu"),
             Button.inline(f"🔗 فتح بالآيدي", b"open_start")],
            [Button.inline(f"🔄 تحويل يوزر/آيدي", b"resolve_start"),
             Button.inline(f"✅ فحص يوزر متعدد", b"check_menu")],
            [Button.inline(f"📊 إحصائيات", b"stats_menu"),
             Button.inline(f"⚙️ إعدادات", b"settings_menu")],
        ]
    
    @classmethod
    def hunt_menu(cls):
        return [
            [Button.inline(f"📱 تيليجرام (ذكي)", b"hunt_tg_smart"),
             Button.inline(f"📱 تيليجرام (سريع)", b"hunt_tg_fast")],
            [Button.inline(f"📷 انستجرام", b"hunt_ig"),
             Button.inline(f"🎵 تيكتوك", b"hunt_tk")],
            [Button.inline(f"🐙 جيت هب", b"hunt_gh"),
             Button.inline(f"🐦 إكس", b"hunt_x")],
            [Button.inline(f"🌐 صيد شامل (كل المنصات)", b"hunt_all")],
            [Button.inline(f"🔙 رجوع", b"back_main")],
        ]
    
    @classmethod
    def video_menu(cls):
        return [
            [Button.inline(f"🎵 تيكتوك", b"dl_tiktok"),
             Button.inline(f"📷 انستجرام", b"dl_instagram")],
            [Button.inline(f"▶️ يوتيوب", b"dl_youtube"),
             Button.inline(f"📘 فيسبوك", b"dl_facebook")],
            [Button.inline(f"🐦 تويتر", b"dl_twitter"),
             Button.inline(f"📌 بنترست", b"dl_pinterest")],
            [Button.inline(f"🎥 لايكي", b"dl_likee"),
             Button.inline(f"👻 سناب شات", b"dl_snapchat")],
            [Button.inline(f"🔙 رجوع", b"back_main")],
        ]
    
    @classmethod
    def info_menu(cls):
        return [
            [Button.inline(f"📱 تيليجرام", b"info_tg"),
             Button.inline(f"📷 انستجرام", b"info_ig")],
            [Button.inline(f"🔙 رجوع", b"back_main")],
        ]
    
    @classmethod
    def check_menu(cls):
        return [
            [Button.inline(f"📱 تيليجرام فقط", b"check_tg"),
             Button.inline(f"📷 انستجرام فقط", b"check_ig")],
            [Button.inline(f"🎵 تيكتوك فقط", b"check_tk"),
             Button.inline(f"🌐 كل المنصات", b"check_all_platforms")],
            [Button.inline(f"🔙 رجوع", b"back_main")],
        ]

# ============================================
# نظام الأوامر المتقدم
# ============================================
@bot.on(events.NewMessage(pattern='/start'))
async def bot_start(event):
    allowed_chats.add(event.chat_id)
    user_id = event.sender_id
    
    if is_dev(user_id):
        caption = (
            "🜲 **لوحة تحكم NinjaGram Pro**\n\n"
            "👑 مرحباً بك في لوحة التحكم المتطورة"
        )
        await bot.send_message(event.chat_id, caption, buttons=dev_panel_markup(), parse_mode='md')
        return
    
    caption = (
        "🐙 **NinjaGram Pro Max Ultra**\n\n"
        "🎯 **أقوى بوت صيد يوزرات وخدمات تيليجرام**\n\n"
        "⚡ **المميزات:**\n"
        "• صيد ذكي بـ 15 استراتيجية\n"
        "• فحص 6 منصات مختلفة\n"
        "• تحميل من 8+ منصات\n"
        "• معلومات حسابات مفصلة\n"
        "• حماية من السبام\n"
        "• دعم كامل للغة العربية\n\n"
        "📢 **Channel:** @Q_g_r_a_m\n"
        "👨‍💻 **Developer:** @NinjaGram"
    )
    
    buttons = UIManager.main_menu()
    
    if os.path.exists(START_IMAGE):
        await bot.send_file(event.chat_id, START_IMAGE, caption=caption, buttons=buttons, parse_mode='md')
    else:
        await bot.send_message(event.chat_id, caption, buttons=buttons, parse_mode='md')

# ============================================
# نظام الصيد الذكي المتقدم
# ============================================
@bot.on(events.CallbackQuery(data=b"hunt_tg_smart"))
async def hunt_telegram_smart(event):
    """صيد تيليجرام ذكي باستخدام كل الاستراتيجيات"""
    user_id = event.sender_id
    
    if not SecuritySystem.check_rate_limit(user_id, "hunt", 5):
        await event.answer("⏳ انتظر قليلاً قبل المحاولة مرة أخرى (حد أقصى 5 صيدات في الدقيقة)", alert=True)
        return
    
    await event.edit("🧠 **جاري الصيد الذكي...**\n📊 تحليل الأنماط وتوليد اليوزرات\n⏳ قد يستغرق 2-3 دقائق", parse_mode='md')
    
    usernames = SmartUsernameGenerator.generate_pool(500, "tg")
    found = []
    total = len(usernames)
    checked = 0
    start_time = time.time()
    
    async with aiohttp.ClientSession() as session:
        sem = asyncio.Semaphore(30)
        
        async def check_and_update(u):
            nonlocal checked, found
            async with sem:
                result = await UltimateUsernameChecker.check_availability(u, "tg", session, sem)
                checked += 1
                
                if checked % 100 == 0:
                    elapsed = time.time() - start_time
                    speed = checked / elapsed if elapsed > 0 else 0
                    try:
                        await event.edit(
                            f"🧠 **الصيد الذكي مستمر...**\n\n"
                            f"✅ تم الفحص: {checked}/{total}\n"
                            f"🎯 المتاح: {len(found)}\n"
                            f"⚡ السرعة: {speed:.0f} يوزر/ثانية\n"
                            f"⏱️ الوقت: {elapsed:.0f} ثانية",
                            parse_mode='md'
                        )
                    except:
                        pass
                
                if result:
                    found.append(result)
        
        await asyncio.gather(*[check_and_update(u) for u in usernames])
    
    elapsed = time.time() - start_time
    
    if found:
        found.sort(key=lambda x: x.quality_score, reverse=True)
        
        text = f"🎉 **اكتمل الصيد الذكي!**\n\n"
        text += f"📊 **إحصائيات:**\n"
        text += f"• تم الفحص: {total} يوزر\n"
        text += f"• المتاح: {len(found)} يوزر\n"
        text += f"• الوقت: {elapsed:.1f} ثانية\n"
        text += f"• ⭐ متوسط الجودة: {sum(f.quality_score for f in found)/len(found):.1f}/10\n\n"
        
        text += "🏆 **أفضل اليوزرات المتاحة:**\n"
        for i, result in enumerate(found[:20], 1):
            stars = "⭐" * min(int(result.quality_score), 5)
            text += f"{i}. @{result.username} {stars} ({result.quality_score:.1f})\n"
        
        if len(found) > 20:
            text += f"\n📋 و {len(found)-20} يوزر آخر..."
    else:
        text = "❌ **لم يتم العثور على يوزرات متاحة**\n🔄 جرب مرة أخرى بصيغة مختلفة"
    
    await event.edit(text, buttons=[[Button.inline("🔄 صيد مرة أخرى", b"hunt_tg_smart"),
                                      Button.inline("🔙 رجوع", b"back_main")]], parse_mode='md')

@bot.on(events.CallbackQuery(data=b"hunt_tg_fast"))
async def hunt_telegram_fast(event):
    """صيد تيليجرام سريع"""
    user_id = event.sender_id
    
    if not SecuritySystem.check_rate_limit(user_id, "hunt", 10):
        await event.answer("⏳ انتظر قليلاً", alert=True)
        return
    
    await event.edit("⚡ **جاري الصيد السريع...**", parse_mode='md')
    
    usernames = SmartUsernameGenerator.generate_pool(300, "tg")
    found = []
    
    async with aiohttp.ClientSession() as session:
        sem = asyncio.Semaphore(50)
        
        async def quick_check(u):
            async with sem:
                result = await UltimateUsernameChecker.check_availability(u, "tg", session, sem)
                if result:
                    found.append(result)
        
        await asyncio.gather(*[quick_check(u) for u in usernames])
    
    if found:
        found.sort(key=lambda x: x.quality_score, reverse=True)
        text = f"⚡ **الصيد السريع اكتمل!**\n\n🎯 المتاح: {len(found)} يوزر\n\n"
        text += "\n".join([f"• @{r.username} ⭐{r.quality_score:.1f}" for r in found[:30]])
    else:
        text = "❌ لم يتم العثور على يوزرات"
    
    await event.edit(text, buttons=[[Button.inline("🔙 رجوع", b"hunt_menu")]], parse_mode='md')

@bot.on(events.CallbackQuery(data=b"hunt_all"))
async def hunt_all_platforms(event):
    """صيد شامل كل المنصات"""
    user_id = event.sender_id
    
    if not SecuritySystem.check_rate_limit(user_id, "hunt_all", 2):
        await event.answer("⏳ الحد الأقصى 2 صيد شامل في الدقيقة", alert=True)
        return
    
    await event.edit("🌐 **جاري الصيد الشامل...**\n🔍 فحص 6 منصات مختلفة\n⏳ قد يستغرق 3-5 دقائق", parse_mode='md')
    
    platforms = ["tg", "ig", "tk", "gh", "x"]
    all_results = {p: [] for p in platforms}
    usernames = SmartUsernameGenerator.generate_pool(200)
    
    async with aiohttp.ClientSession() as session:
        sem = asyncio.Semaphore(20)
        
        async def check_all_platforms(u):
            async with sem:
                for platform in platforms:
                    try:
                        result = await UltimateUsernameChecker.check_availability(u, platform, session, sem)
                        if result:
                            all_results[platform].append(result)
                    except:
                        pass
        
        await asyncio.gather(*[check_all_platforms(u) for u in usernames])
    
    text = "🌐 **نتائج الصيد الشامل:**\n\n"
    total_available = 0
    
    platform_names = {"tg": "📱 تيليجرام", "ig": "📷 انستجرام", "tk": "🎵 تيكتوك", "gh": "🐙 جيت هب", "x": "🐦 إكس"}
    
    for platform, results in all_results.items():
        count = len(results)
        total_available += count
        text += f"{platform_names[platform]}: {count} يوزر متاح\n"
    
    text += f"\n📊 **الإجمالي: {total_available} يوزر متاح**\n\n"
    
    for platform, results in all_results.items():
        if results:
            results.sort(key=lambda x: x.quality_score, reverse=True)
            text += f"**{platform_names[platform]} - الأفضل:**\n"
            text += " • " + " • ".join([f"@{r.username}" for r in results[:5]]) + "\n"
    
    await event.edit(text, buttons=[[Button.inline("🔙 رجوع", b"hunt_menu")]], parse_mode='md')

# ============================================
# نظام تحميل الفيديو المتقدم
# ============================================
@bot.on(events.CallbackQuery(data=re.compile(b"dl_(.+)")))
async def video_download_handler(event):
    platform = event.data.decode().replace("dl_", "")
    user_id = event.sender_id
    
    if not SecuritySystem.check_rate_limit(user_id, "download", 5):
        await event.answer("⏳ انتظر قليلاً", alert=True)
        return
    
    platforms_ar = {
        "tiktok": "تيكتوك", "instagram": "انستجرام", "youtube": "يوتيوب",
        "facebook": "فيسبوك", "twitter": "تويتر", "pinterest": "بنترست",
        "likee": "لايكي", "snapchat": "سناب شات"
    }
    
    user_states[user_id] = f"waiting_video_{platform}"
    await event.edit(
        f"🎬 **تحميل من {platforms_ar.get(platform, platform)}**\n\n"
        f"📤 أرسل رابط الفيديو:",
        buttons=[[Button.inline("🔙 رجوع", b"video_menu")]],
        parse_mode='md'
    )

@bot.on(events.NewMessage(func=lambda e: e.sender_id in user_states and user_states[e.sender_id].startswith("waiting_video_")))
async def handle_video_download(event):
    user_id = event.sender_id
    state = user_states.pop(user_id)
    platform = state.replace("waiting_video_", "")
    url = event.text.strip()
    
    if not SecuritySystem.validate_url(url):
        await event.respond("❌ **رابط غير صالح**", buttons=[[Button.inline("🔙 رجوع", b"video_menu")]], parse_mode='md')
        return
    
    loading_msg = await event.respond("⏳ **جاري التحميل...**\n🔍 البحث عن أفضل جودة", parse_mode='md')
    
    result = await UltimateVideoDownloader.download(url, platform)
    
    if result.get("success"):
        await loading_msg.edit(
            f"✅ **تم التحميل بنجاح!**\n\n"
            f"📹 [اضغط هنا للمشاهدة/التحميل]({result['video_url']})\n"
            f"📱 المنصة: {result.get('platform', platform)}",
            buttons=[[Button.inline("🔙 رجوع", b"video_menu")]],
            parse_mode='md'
        )
    else:
        await loading_msg.edit(
            f"❌ **فشل التحميل**\n{result.get('error', 'خطأ غير معروف')}",
            buttons=[[Button.inline("🔄 حاول مرة أخرى", f"dl_{platform}".encode()),
                      Button.inline("🔙 رجوع", b"video_menu")]],
            parse_mode='md'
        )

# ============================================
# نظام معلومات الحسابات المتقدم
# ============================================
@bot.on(events.CallbackQuery(data=b"info_tg"))
async def info_telegram_start(event):
    user_id = event.sender_id
    user_states[user_id] = "waiting_info_tg"
    await event.edit(
        "🔍 **معلومات حساب تيليجرام**\n\n"
        "📤 أرسل يوزر الحساب:\n"
        "مثال: @username",
        buttons=[[Button.inline("🔙 رجوع", b"info_menu")]],
        parse_mode='md'
    )

@bot.on(events.NewMessage(func=lambda e: e.sender_id in user_states and user_states[e.sender_id] == "waiting_info_tg"))
async def handle_telegram_info(event):
    user_id = event.sender_id
    user_states.pop(user_id, None)
    username = event.text.strip().replace("@", "")
    
    loading_msg = await event.respond("🔍 **جاري جلب المعلومات...**", parse_mode='md')
    
    info = await AccountInfoFetcher.get_telegram_info(username)
    
    if info.get("exists"):
        text = f"📱 **معلومات @{username}**\n\n"
        text += f"👤 الاسم: {info.get('display_name', 'غير معروف')}\n"
        
        if info.get("bio"):
            text += f"📝 البايو: {info['bio'][:300]}\n"
        
        if info.get("is_verified"):
            text += "✅ حساب موثق\n"
        if info.get("is_premium"):
            text += "⭐ حساب بريميوم\n"
        if info.get("subscribers"):
            text += f"👥 المشتركين: {info['subscribers']}\n"
        
        text += f"\n🔗 [فتح الحساب](https://t.me/{username})\n"
        text += f"📱 [فتح في التطبيق](tg://resolve?domain={username})"
        
        if info.get("profile_image"):
            try:
                await bot.send_file(event.chat_id, info["profile_image"], caption=text, parse_mode='md')
                await loading_msg.delete()
                return
            except:
                pass
        
        await loading_msg.edit(text, buttons=[[Button.inline("🔙 رجوع", b"info_menu")]], parse_mode='md')
    else:
        await loading_msg.edit(
            f"❌ **الحساب @{username} غير موجود أو محذوف**",
            buttons=[[Button.inline("🔙 رجوع", b"info_menu")]],
            parse_mode='md'
        )

# ============================================
# نظام فحص اليوزرات المتقدم
# ============================================
@bot.on(events.CallbackQuery(data=b"check_all_platforms"))
async def check_all_platforms_start(event):
    user_id = event.sender_id
    user_states[user_id] = "waiting_check_all"
    await event.edit(
        "🌐 **فحص يوزر في كل المنصات**\n\n"
        "📤 أرسل اليوزر للفحص:\n"
        "مثال: @username",
        buttons=[[Button.inline("🔙 رجوع", b"check_menu")]],
        parse_mode='md'
    )

@bot.on(events.NewMessage(func=lambda e: e.sender_id in user_states and user_states[e.sender_id] == "waiting_check_all"))
async def handle_check_all(event):
    user_id = event.sender_id
    user_states.pop(user_id, None)
    username = event.text.strip().replace("@", "").lower()
    
    loading_msg = await event.respond("🌐 **جاري الفحص الشامل...**\n🔍 فحص 6 منصات مختلفة", parse_mode='md')
    
    platforms = ["tg", "ig", "tk", "gh", "x", "fb"]
    results = {}
    available_count = 0
    
    async with aiohttp.ClientSession() as session:
        sem = asyncio.Semaphore(10)
        
        async def check_platform(platform):
            result = await UltimateUsernameChecker.check_availability(username, platform, session, sem)
            return platform, result
        
        tasks = [check_platform(p) for p in platforms]
        completed = await asyncio.gather(*tasks)
        
        for platform, result in completed:
            if result and result.available:
                results[platform] = "✅ متاح"
                available_count += 1
            else:
                results[platform] = "❌ محجوز"
    
    text = f"🌐 **نتائج فحص @{username}**\n\n"
    text += f"📱 تيليجرام: {results.get('tg', '⚠️ خطأ')}\n"
    text += f"📷 انستجرام: {results.get('ig', '⚠️ خطأ')}\n"
    text += f"🎵 تيكتوك: {results.get('tk', '⚠️ خطأ')}\n"
    text += f"🐙 جيت هب: {results.get('gh', '⚠️ خطأ')}\n"
    text += f"🐦 إكس: {results.get('x', '⚠️ خطأ')}\n"
    text += f"📘 فيسبوك: {results.get('fb', '⚠️ خطأ')}\n\n"
    
    if available_count > 0:
        text += f"🎉 اليوزر متاح في {available_count} منصة!"
    else:
        text += "💀 اليوزر محجوز في كل المنصات"
    
    await loading_msg.edit(text, buttons=[[Button.inline("🔙 رجوع", b"check_menu")]], parse_mode='md')

# ============================================
# نظام الإحصائيات
# ============================================
@bot.on(events.CallbackQuery(data=b"stats_menu"))
async def stats_menu(event):
    """عرض إحصائيات البوت"""
    cache_size = len(username_cache)
    active_users = len([uid for uid in user_states if user_states[uid]])
    
    text = (
        "📊 **إحصائيات NinjaGram Pro**\n\n"
        f"👥 المستخدمين النشطين: {active_users}\n"
        f"💾 اليوزرات في الكاش: {cache_size}\n"
        f"⏱️ مدة الكاش: {CACHE_TTL} ثانية\n"
        f"🔒 معدل الحماية: 5 طلبات/دقيقة\n"
        f"🌐 المنصات المدعومة: 6\n"
        f"📥 منصات التحميل: 8+\n"
        f"🧠 استراتيجيات الصيد: 15\n\n"
        "⚡ **الإصدار:** Pro Max Ultra v3.0"
    )
    
    await event.edit(text, buttons=[[Button.inline("🔙 رجوع", b"back_main")]], parse_mode='md')

# ============================================
# أحداث إضافية
# ============================================
@bot.on(events.CallbackQuery(data=b"back_main"))
async def back_to_main(event):
    caption = "🐙 **NinjaGram Pro Max Ultra**\n\nاختر الخدمة:"
    await event.edit(caption, buttons=UIManager.main_menu(), parse_mode='md')

@bot.on(events.CallbackQuery(data=b"hunt_menu"))
async def hunt_menu_handler(event):
    await event.edit("🎯 **صيد اليوزرات الذكي**\n\nاختر المنصة:", buttons=UIManager.hunt_menu(), parse_mode='md')

@bot.on(events.CallbackQuery(data=b"video_menu"))
async def video_menu_handler(event):
    await event.edit("🎬 **تحميل الفيديوهات**\n\nاختر المنصة:", buttons=UIManager.video_menu(), parse_mode='md')

@bot.on(events.CallbackQuery(data=b"info_menu"))
async def info_menu_handler(event):
    await event.edit("🔍 **معلومات الحسابات**\n\nاختر المنصة:", buttons=UIManager.info_menu(), parse_mode='md')

@bot.on(events.CallbackQuery(data=b"check_menu"))
async def check_menu_handler(event):
    await event.edit("✅ **فحص اليوزرات**\n\nاختر نوع الفحص:", buttons=UIManager.check_menu(), parse_mode='md')

# ============================================
# بدء التشغيل
# ============================================
print("""
╔══════════════════════════════════════╗
║     🐙 NinjaGram Pro Max Ultra      ║
║     Ultimate Username Hunter Bot     ║
║     Version: 3.0.0 Pro Max Ultra     ║
║     Developer: @NinjaGram            ║
║     Channel: @Q_g_r_a_m              ║
╚══════════════════════════════════════╝
""")

bot.start(bot_token=BOT_TOKEN)
bot.run_until_disconnected()
