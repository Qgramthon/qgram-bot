import asyncio
import threading
import logging
import sys
from shared import *
from server import app
from bot import bot

# لا تنشئ main_loop هنا، لأنه موجود في shared.py
# main_loop = asyncio.new_event_loop()   <-- تم حذفه

def start_main_loop():
    asyncio.set_event_loop(main_loop)          # main_loop من shared.py
    main_loop.run_until_complete(load_all_sessions())
    asyncio.ensure_future(auto_save_sessions_loop())
    main_loop.run_forever()

async def auto_save_sessions_loop():
    while True:
        await asyncio.sleep(300)
        await save_all_sessions()

async def start_bot():
    await bot.start(bot_token=BOT_TOKEN)
    logger.info("بوت المطور يعمل")
    await notify_dev("Qthon Bot started successfully!")
    await bot.run_until_disconnected()

if __name__ == '__main__':
    loop_thread = threading.Thread(target=start_main_loop, daemon=True)
    loop_thread.start()

    asyncio.run_coroutine_threadsafe(start_bot(), main_loop)

    logger.info("Qthon Server Started")
    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)
