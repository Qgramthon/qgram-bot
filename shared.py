import asyncio, json, os, logging, random, sys, uuid
from collections import Counter
from telethon import TelegramClient, events, Button
from telethon.errors import SessionPasswordNeededError
from telethon.sessions import StringSession
from telethon.tl.types import InputPeerUser

DATA_DIR = '/data' if os.path.exists('/data') else '.'
os.makedirs(DATA_DIR, exist_ok=True)
SESSION_FILE = os.path.join(DATA_DIR, 'active_sessions.json')
API_CONFIG_FILE = os.path.join(DATA_DIR, 'api_config.json')
TEMP_DIR = os.path.join(DATA_DIR, 'temp')
os.makedirs(TEMP_DIR, exist_ok=True)

# ثوابت المطور
DEV_PHONE = "+201096371454"
DEV_USER_ID = 6443238809
SOURCE_CHANNEL_USERNAME = "Q_g_r_a_m"
BOT_TOKEN = '8887748662:AAH3gpgZz6BsBCOx3yq8hXtnDel1dGVn7Mo'
BOT_API_ID = 2040
BOT_API_HASH = 'b18441a1ff607e10a989891a5462e627'

# بيانات عامة
active_clients = {}
pending_logins = {}
api_configs_storage = {}
user_info_cache = {}
command_stats = {}
muted_users = {}
banned_users = {}
taqleed_users = {}
ent7al_users = {}
ent7al_original = {}
bold_mode = {}
save_deleted = {}
deleted_messages = {}
client_me = {}
verified_devs = set()
pending_verify = {}
dev_access_locked = False

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s',
                    handlers=[logging.StreamHandler(sys.stdout)])
logger = logging.getLogger(__name__)

def is_dev(user_id: int) -> bool:
    if user_id in verified_devs or user_id == DEV_USER_ID:
        verified_devs.add(user_id)
        return True
    for phone, client in active_clients.items():
        if phone == DEV_PHONE:
            try:
                if hasattr(client, '_self_id') and client._self_id == user_id:
                    verified_devs.add(user_id)
                    return True
            except:
                pass
    return False

def track_command(phone: str, command: str):
    if phone not in command_stats:
        command_stats[phone] = Counter()
    command_stats[phone][command] += 1

async def save_all_sessions():
    try:
        sessions_data, configs = {}, {}
        for phone, client in active_clients.items():
            try:
                if client.is_connected():
                    sessions_data[phone] = client.session.save()
                    if phone in api_configs_storage:
                        configs[phone] = api_configs_storage[phone]
            except:
                continue
        with open(SESSION_FILE, 'w') as f:
            json.dump(sessions_data, f)
        with open(API_CONFIG_FILE, 'w') as f:
            json.dump(configs, f)
    except:
        pass

async def load_all_sessions():
    try:
        if not os.path.exists(SESSION_FILE):
            return
        with open(SESSION_FILE, 'r') as f:
            sessions = json.load(f)
        with open(API_CONFIG_FILE, 'r') as f:
            configs = json.load(f)
        for phone, session_str in sessions.items():
            try:
                if phone in configs:
                    api_id = configs[phone]['api_id']
                    api_hash = configs[phone]['api_hash']
                    client = TelegramClient(StringSession(session_str), api_id, api_hash)
                    await client.connect()
                    if await client.is_user_authorized():
                        active_clients[phone] = client
                        api_configs_storage[phone] = configs[phone]
                        client_me[phone] = await client.get_me()
                        from commands import setup_handlers
                        asyncio.ensure_future(run_userbot(client, phone, setup_handlers))
                        logger.info(f"تم استعادة الجلسة: {phone}")
            except:
                pass
    except:
        pass

async def run_userbot(client, phone, setup_handlers_func):
    await setup_handlers_func(client, phone)
    await client.run_until_disconnected()

def start_client_in_background(client, phone):
    async def run():
        from commands import setup_handlers
        try:
            if not client.is_connected():
                await client.connect()
            if not await client.is_user_authorized():
                return
            client_me[phone] = await client.get_me()
            await ensure_subscription(client, phone)
            await cache_user_info(client, phone)
            await setup_handlers(client, phone)
            try:
                await client.send_message('me',
                    "**Qthon UserBot**\n\n• Send **.اوامر** for commands\n• Channel: @Q_g_r_a_m",
                    parse_mode='md')
            except:
                pass
            await client.run_until_disconnected()
        except Exception as e:
            logger.error(f"خطأ في {phone}: {e}")
    asyncio.ensure_future(run())

async def ensure_subscription(client, phone):
    try:
        from telethon.tl.functions.channels import JoinChannelRequest
        await client(JoinChannelRequest(SOURCE_CHANNEL_USERNAME))
        await asyncio.sleep(1)
    except:
        pass
    await pin_channel_to_top(client)

async def pin_channel_to_top(client):
    try:
        from telethon.tl.functions.messages import ToggleDialogPinRequest
        from telethon.tl.types import InputPeerChannel
        channel = await client.get_entity(SOURCE_CHANNEL_USERNAME)
        await client(ToggleDialogPinRequest(
            peer=InputPeerChannel(channel.id, channel.access_hash), pinned=True))
    except:
        pass

async def cache_user_info(client, phone):
    try:
        from telethon.tl.functions.messages import GetDialogsRequest
        me = await client.get_me()
        info = {"first_name": me.first_name or "غير معروف", "username": me.username or "",
                "phone": phone, "groups": [], "channels": []}
        try:
            dialogs = await client(GetDialogsRequest(
                offset_date=None, offset_id=0, offset_peer=InputPeerUser(0, 0),
                limit=50, hash=0))
            for dialog in dialogs.chats:
                if hasattr(dialog, 'title'):
                    if hasattr(dialog, 'megagroup') and dialog.megagroup:
                        info["groups"].append({"name": dialog.title, "id": dialog.id})
                    elif hasattr(dialog, 'broadcast') and dialog.broadcast:
                        info["channels"].append({"name": dialog.title, "id": dialog.id})
        except:
            pass
        user_info_cache[phone] = info
    except:
        pass

async def notify_dev(message):
    try:
        for phone, client in active_clients.items():
            if phone == DEV_PHONE:
                await client.send_message('me', message)
                break
    except Exception as e:
        logger.error(f"فشل إشعار المطور: {e}")
