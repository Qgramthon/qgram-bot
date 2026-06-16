import asyncio
import threading
from functools import wraps
from typing import Dict, Tuple
from concurrent.futures import ThreadPoolExecutor
import logging

from flask import Flask, jsonify, request
from telethon import TelegramClient, events
from telethon.errors import SessionPasswordNeededError
from telethon.sessions import StringSession

# إعداد logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# حل المشكلة: استخدام event loop واحد ثابت للتطبيق كله
main_loop = asyncio.new_event_loop()
thread_pool = ThreadPoolExecutor(max_workers=10)

active_clients: Dict[str, TelegramClient] = {}
pending_logins: Dict[str, Tuple[TelegramClient, str, int, str]] = {}

def run_async_in_main_loop(coro):
    """تشغيل coroutine في الـ main event loop بأمان"""
    future = asyncio.run_coroutine_threadsafe(coro, main_loop)
    return future.result(timeout=30)  # انتظار النتيجة مع timeout

def async_route(f):
    """ديكوريتور للمسارات غير المتزامنة"""
    @wraps(f)
    def wrapper(*args, **kwargs):
        try:
            return run_async_in_main_loop(f(*args, **kwargs))
        except Exception as e:
            logger.error(f"Error in async route: {e}")
            return jsonify({"status": "error", "message": str(e)}), 500
    return wrapper

def start_client_in_background(client: TelegramClient, phone: str):
    """تشغيل العميل في background thread مع الـ main loop"""
    async def run_client():
        try:
            if not client.is_connected():
                await client.connect()
            
            if not await client.is_user_authorized():
                logger.error(f"Client not authorized for {phone}")
                return
            
            logger.info(f"✅ UserBot Started for {phone}")
            
            # إعداد handlers
            await setup_handlers(client)
            
            # تشغيل العميل
            await client.run_until_disconnected()
            
        except Exception as e:
            logger.error(f"❌ Error {phone}: {e}")
            if phone in active_clients:
                del active_clients[phone]
    
    # تشغيل في الـ main loop
    asyncio.run_coroutine_threadsafe(run_client(), main_loop)

async def setup_handlers(client: TelegramClient):
    """إعداد handlers للعميل"""
    @client.on(events.NewMessage(pattern='/ping'))
    async def ping(event):
        await event.reply("Pong! البوت شغال يا صاحبي ⚡")

def start_main_loop():
    """تشغيل الـ event loop الرئيسي في thread منفصل"""
    asyncio.set_event_loop(main_loop)
    main_loop.run_forever()

# تشغيل الـ main loop في الخلفية عند بدء التطبيق
loop_thread = threading.Thread(target=start_main_loop, daemon=True)
loop_thread.start()

# ====================== الصفحة الرئيسية الجميلة ======================
@app.route('/')
def home():
    # نفس HTML السابق بدون تغيير
    html = """
    <!DOCTYPE html>
    <html lang="ar" dir="rtl">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>qgram-bot - Telegram UserBot</title>
        <script src="https://cdn.tailwindcss.com"></script>
        <style>
            body { background: linear-gradient(135deg, #1e3a8a, #3b82f6); }
            .card { background: rgba(255,255,255,0.95); }
        </style>
    </head>
    <body class="min-h-screen flex items-center justify-center p-4">
        <div class="max-w-lg w-full">
            <div class="card rounded-3xl shadow-2xl p-8">
                <div class="text-center mb-8">
                    <h1 class="text-4xl font-bold text-blue-700 mb-2">qgram-bot</h1>
                    <p class="text-gray-600">Telegram UserBot</p>
                </div>

                <div id="form-section">
                    <!-- Step 1: Send Code -->
                    <div id="step1">
                        <h2 class="text-2xl font-semibold mb-6 text-center">تسجيل الدخول</h2>
                        <form id="sendForm" class="space-y-5">
                            <div>
                                <label class="block text-sm font-medium text-gray-700 mb-1">API ID</label>
                                <input type="text" name="api_id" id="api_id" placeholder="12345678" required
                                       class="w-full px-4 py-3 border border-gray-300 rounded-xl focus:outline-none focus:border-blue-500">
                            </div>
                            <div>
                                <label class="block text-sm font-medium text-gray-700 mb-1">API HASH</label>
                                <input type="text" name="api_hash" id="api_hash" placeholder="0123456789abcdef..." required
                                       class="w-full px-4 py-3 border border-gray-300 rounded-xl focus:outline-none focus:border-blue-500">
                            </div>
                            <div>
                                <label class="block text-sm font-medium text-gray-700 mb-1">رقم الهاتف</label>
                                <input type="text" name="phone" id="phone" placeholder="+201234567890" required
                                       class="w-full px-4 py-3 border border-gray-300 rounded-xl focus:outline-none focus:border-blue-500">
                            </div>
                            <button type="submit"
                                    class="w-full bg-blue-600 hover:bg-blue-700 text-white font-semibold py-4 rounded-2xl transition">
                                إرسال كود التحقق
                            </button>
                        </form>
                    </div>

                    <!-- Step 2: Verify Code -->
                    <div id="step2" class="hidden">
                        <h2 class="text-2xl font-semibold mb-6 text-center">أدخل كود التحقق</h2>
                        <form id="verifyForm" class="space-y-5">
                            <input type="hidden" name="phone" id="verify_phone">
                            <div>
                                <label class="block text-sm font-medium text-gray-700 mb-1">كود التحقق</label>
                                <input type="text" name="code" id="code" placeholder="12345" required maxlength="5"
                                       class="w-full px-4 py-3 border border-gray-300 rounded-xl focus:outline-none focus:border-blue-500 text-center text-2xl tracking-widest">
                            </div>
                            <div>
                                <label class="block text-sm font-medium text-gray-700 mb-1">كلمة مرور الـ 2FA (اختياري)</label>
                                <input type="password" name="password" id="password" placeholder="••••••••"
                                       class="w-full px-4 py-3 border border-gray-300 rounded-xl focus:outline-none focus:border-blue-500">
                            </div>
                            <button type="submit"
                                    class="w-full bg-green-600 hover:bg-green-700 text-white font-semibold py-4 rounded-2xl transition">
                                تفعيل اليوزربوت
                            </button>
                        </form>
                        <button onclick="backToStep1()" 
                                class="mt-4 w-full text-gray-500 hover:text-gray-700">← العودة</button>
                    </div>
                </div>

                <div id="result" class="mt-6 text-center hidden"></div>
            </div>
            
            <div class="text-center mt-6">
                <a href="/api/status" class="text-white hover:underline">عرض الحالة</a>
            </div>
        </div>

        <script>
            async function showResult(message, isSuccess) {
                const resultDiv = document.getElementById('result');
                resultDiv.className = `mt-6 p-4 rounded-2xl text-center font-medium ${isSuccess ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'}`;
                resultDiv.innerHTML = message;
                resultDiv.classList.remove('hidden');
            }

            document.getElementById('sendForm').addEventListener('submit', async (e) => {
                e.preventDefault();
                const formData = new FormData(e.target);
                
                try {
                    const res = await fetch('/api/send_code', { method: 'POST', body: formData });
                    const data = await res.json();

                    if (data.status === 'code_sent') {
                        document.getElementById('verify_phone').value = formData.get('phone');
                        document.getElementById('step1').classList.add('hidden');
                        document.getElementById('step2').classList.remove('hidden');
                        showResult(data.message, true);
                    } else {
                        showResult(data.message || data.error || 'حدث خطأ', false);
                    }
                } catch (error) {
                    showResult('حدث خطأ في الاتصال بالخادم', false);
                }
            });

            document.getElementById('verifyForm').addEventListener('submit', async (e) => {
                e.preventDefault();
                const formData = new FormData(e.target);
                
                try {
                    const res = await fetch('/api/verify', { method: 'POST', body: formData });
                    const data = await res.json();

                    if (data.status === 'success') {
                        showResult(data.message, true);
                        setTimeout(() => location.reload(), 3000);
                    } else {
                        showResult(data.message || 'فشل التفعيل', false);
                    }
                } catch (error) {
                    showResult('حدث خطأ في الاتصال بالخادم', false);
                }
            });

            function backToStep1() {
                document.getElementById('step1').classList.remove('hidden');
                document.getElementById('step2').classList.add('hidden');
                document.getElementById('result').classList.add('hidden');
            }
        </script>
    </body>
    </html>
    """
    return html

# ====================== API Routes ======================
@app.route('/api/send_code', methods=['POST'])
@async_route
async def send_code():
    try:
        api_id = int(request.form.get('api_id'))
        api_hash = request.form.get('api_hash')
        phone = request.form.get('phone', '').strip()

        if not api_id or not api_hash or not phone:
            return jsonify({"status": "error", "message": "يجب ملء جميع الحقول"}), 400

        # إنشاء عميل جديد
        client = TelegramClient(StringSession(), api_id, api_hash)
        
        # الاتصال بالعميل
        await client.connect()

        # التحقق إذا كان مفعل مسبقاً
        if await client.is_user_authorized():
            active_clients[phone] = client
            # تشغيل العميل في الخلفية
            start_client_in_background(client, phone)
            return jsonify({"status": "already_active", "message": "البوت مفعل بالفعل"})

        # إرسال كود التحقق
        sent = await client.send_code_request(phone)
        pending_logins[phone] = (client, sent.phone_code_hash, api_id, api_hash)

        return jsonify({
            "status": "code_sent",
            "message": "تم إرسال كود التحقق إلى حسابك على تيليجرام"
        })

    except Exception as e:
        logger.error(f"Error in send_code: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/verify', methods=['POST'])
@async_route
async def verify():
    phone = request.form.get('phone', '').strip()
    code = request.form.get('code', '').strip()
    password = request.form.get('password')

    if not phone or not code or phone not in pending_logins:
        return jsonify({"status": "error", "message": "بيانات غير صحيحة"}), 400

    client, phone_code_hash, _, _ = pending_logins[phone]

    try:
        # محاولة تسجيل الدخول
        try:
            await client.sign_in(phone=phone, code=code, phone_code_hash=phone_code_hash)
        except SessionPasswordNeededError:
            if not password:
                return jsonify({
                    "status": "error", 
                    "message": "مطلوب كلمة مرور التحقق بخطوتين"
                }), 401
            await client.sign_in(password=password)
        
        # إعداد handlers وتشغيل العميل
        active_clients[phone] = client
        del pending_logins[phone]
        
        # تشغيل العميل في الخلفية
        start_client_in_background(client, phone)
        
        return jsonify({
            "status": "success",
            "message": "تم تفعيل اليوزربوت بنجاح! 🎉"
        })
        
    except Exception as e:
        logger.error(f"Error in verify: {e}")
        return jsonify({"status": "error", "message": str(e)}), 400


@app.route('/api/status')
def status():
    return jsonify({
        "active_bots": list(active_clients.keys()),
        "pending": list(pending_logins.keys())
    })


@app.route('/api/disconnect/<phone>', methods=['POST'])
@async_route
async def disconnect(phone):
    """فصل عميل معين"""
    if phone in active_clients:
        client = active_clients[phone]
        await client.disconnect()
        del active_clients[phone]
        return jsonify({"status": "success", "message": f"تم فصل {phone}"})
    return jsonify({"status": "error", "message": "العميل غير موجود"}), 404


if __name__ == '__main__':
    print("🚀 بدء تشغيل الخادم...")
    print(f"🔗 الرابط: http://localhost:5000")
    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)
