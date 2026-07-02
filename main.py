#!/usr/bin/env python3
import asyncio, os, threading, sys, time
from aiohttp import web
from telethon import TelegramClient, events, Button

BOT_TOKEN = '7998616214:AAHJmfPpL8rzRgso3hxIO-CKHE2rlycyNwo'
API_ID = 2040
API_HASH = 'b18441a1ff607e10a989891a5462e627'
PORT = int(os.environ.get('PORT', 8080))

# Web app
async def handle(request):
    return web.Response(text="OK")

app = web.Application()
app.router.add_get('/', handle)

# Bot
bot = TelegramClient('session', API_ID, API_HASH)

@bot.on(events.NewMessage(pattern='/start'))
async def start(event):
    await event.respond("✅ **البوت شغال!**\n\n🧨 NinjaGram v10", buttons=[
        [Button.inline("📞 تروكولر", b"tc")],
        [Button.inline("🕵️ OSINT", b"osint")],
    ])

@bot.on(events.CallbackQuery(data=b"tc"))
async def tc(event):
    await event.respond("📞 أرسل رقم الهاتف:")

@bot.on(events.CallbackQuery(data=b"osint"))
async def osint(event):
    await event.respond("🕵️ أرسل يوزر أو ID:")

# Run
if __name__ == '__main__':
    # Start web
    threading.Thread(target=lambda: web.run_app(app, host='0.0.0.0', port=PORT), daemon=True).start()
    print(f"Web on {PORT}")
    
    # Start bot
    async def main():
        await bot.start(bot_token=BOT_TOKEN)
        me = await bot.get_me()
        print(f"Bot: @{me.username}")
        await bot.run_until_disconnected()
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(main())
