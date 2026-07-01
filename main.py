import asyncio, os, threading
from aiohttp import web
from telethon import TelegramClient, events, Button

BOT_TOKEN = '7998616214:AAHJmfPpL8rzRgso3hxIO-CKHE2rlycyNwo'
API_ID = 2040
API_HASH = 'b18441a1ff607e10a989891a5462e627'
PORT = int(os.environ.get('PORT', 8080))

# Web
app = web.Application()
app.router.add_get('/', lambda r: web.Response(text="OK"))

# Bot  
bot = TelegramClient('bot', API_ID, API_HASH)

@bot.on(events.NewMessage(pattern='/start'))
async def start(event):
    await event.respond("✅ **البوت شغال!**", buttons=[
        [Button.inline("📞 تروكولر", b"tc")],
        [Button.inline("🕵️ OSINT", b"osint")],
    ])

@bot.on(events.CallbackQuery(data=b"tc"))
async def tc(event):
    await event.respond("📞 أرسل الرقم:")

@bot.on(events.CallbackQuery(data=b"osint"))
async def osint(event):
    await event.respond("🕵️ أرسل اليوزر:")

if __name__ == '__main__':
    # Web in thread
    t = threading.Thread(target=lambda: web.run_app(app, host='0.0.0.0', port=PORT))
    t.daemon = True
    t.start()
    
    # Bot
    async def main():
        await bot.start(bot_token=BOT_TOKEN)
        print("Bot ready")
        await bot.run_until_disconnected()
    
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
