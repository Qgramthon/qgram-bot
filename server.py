import os, json, asyncio, time, random, logging
from datetime import datetime
from pathlib import Path
from flask import Flask, request, jsonify, render_template_string
from telethon import TelegramClient, events
from telethon.errors import SessionPasswordNeededError, PhoneCodeInvalidError, PhoneCodeExpiredError

PORT = int(os.environ.get("PORT", 5000))
SESSIONS_DIR = Path("sessions")
SESSIONS_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
pending_logins = {}
active_clients = {}
app = Flask(__name__)

HTML = """<!DOCTYPE html><html lang="ar" dir="rtl"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"><title>Qgram</title><script src="https://telegram.org/js/telegram-web-app.js"></script><style>:root{--bg:#0A0A19;--card:#1A1A2E;--border:#2A2A4A;--accent:#6C63FF;--text:#E8E8F0;--sub:#9090B0;--success:#4ADE80;--danger:#F87171}*{margin:0;padding:0;box-sizing:border-box}body{font-family:-apple-system,sans-serif;background:var(--bg);color:var(--text);min-height:100vh;padding:16px}.container{max-width:500px;margin:0 auto}.header{text-align:center;padding:24px 0}.logo{font-size:32px;font-weight:800;background:linear-gradient(135deg,var(--accent),#8B83FF);-webkit-background-clip:text;-webkit-text-fill-color:transparent}.sub{color:var(--sub);font-size:13px}.card{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:20px;margin-bottom:14px}.card h3{color:var(--accent);margin-bottom:16px}.step{display:none}.step.active{display:block}label{color:var(--sub);font-size:12px;display:block;margin:14px 0 6px}input{width:100%;padding:13px;background:var(--bg);border:1.5px solid var(--border);border-radius:8px;color:var(--text);font-size:14px}input:focus{outline:none;border-color:var(--accent)}button{width:100%;padding:14px;background:var(--accent);color:#fff;border:none;border-radius:8px;font-size:15px;font-weight:600;cursor:pointer;margin-top:16px}button:disabled{opacity:0.5}.msg{padding:12px;border-radius:8px;margin-top:12px;text-align:center;display:none}.msg.success{background:rgba(74,222,128,0.1);color:var(--success);display:block}.msg.error{background:rgba(248,113,113,0.1);color:var(--danger);display:block}.info{background:rgba(108,99,255,0.06);border:1px solid rgba(108,99,255,0.2);border-radius:8px;padding:12px;margin:12px 0;font-size:12px;color:var(--sub)}.info b{color:var(--accent)}.cmds{display:grid;grid-template-columns:1fr 1fr;gap:7px;margin-top:12px}.cmd{background:var(--bg);border:1px solid var(--border);padding:10px;border-radius:8px;text-align:center;font-size:11px;color:var(--sub)}.cmd b{color:var(--accent);display:block;font-size:13px}</style></head><body><div class="container"><div class="header"><div class="logo">QGRAM</div><div class="sub">Telethon UserBot Cloud</div></div><div class="step active" id="s1"><div class="card"><h3>Connect Account</h3><div class="info">Get <b>API_ID</b> and <b>API_HASH</b> from <b>my.telegram.org</b></div><label>API ID</label><input type="number" id="api_id" placeholder="12345678"><label>API HASH</label><input type="text" id="api_hash" placeholder="a1b2c3d4"><label>Phone</label><input type="text" id="phone" placeholder="+201234567890"><button onclick="sendCode()">Send Code</button><div id="msg1" class="msg"></div></div></div><div class="step" id="s2"><div class="card"><h3>Verify Code</h3><label>Code</label><input type="text" id="code" placeholder="12345"><label>2FA Password</label><input type="password" id="password" placeholder="Leave empty"><button onclick="verifyCode()">Activate</button><div id="msg2" class="msg"></div></div></div><div class="step" id="s3"><div class="card"><h3>Activated</h3><div class="msg success">Bot is running 24/7!</div><div class="cmds"><div class="cmd"><b>.كتم</b>Mute</div><div class="cmd"><b>.خط عريض</b>Bold</div><div class="cmd"><b>.تقليد</b>Mimic</div><div class="cmd"><b>.انتحال</b>Clone</div><div class="cmd"><b>.حفظ</b>Save</div><div class="cmd"><b>.بنق</b>Ping</div><div class="cmd"><b>.تاريخ</b>Date</div><div class="cmd"><b>.ايدي</b>ID</div></div></div></div></div><script>const tg=window.Telegram.WebApp;tg.ready();tg.expand();let ph='';function sm(n,t,c){document.getElementById('msg'+n).textContent=t;document.getElementById('msg'+n).className='msg '+c}function ss(n){document.querySelectorAll('.step').forEach(s=>s.classList.remove('active'));document.getElementById('s'+n).classList.add('active')}async function sendCode(){let b=event.target;b.disabled=true;b.textContent='Sending...';let ai=document.getElementById('api_id').value;let ah=document.getElementById('api_hash').value;let p=document.getElementById('phone').value;ph=p;if(!ai||!ah||!p){sm(1,'All fields required','error');b.disabled=false;b.textContent='Send Code';return}try{let r=await fetch('/api/send_code',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({api_id:ai,api_hash:ah,phone:p})});let d=await r.json();d.success?(sm(1,'Code sent!','success'),setTimeout(()=>ss(2),500)):sm(1,d.message,'error')}catch(e){sm(1,'Connection failed','error')}b.disabled=false;b.textContent='Send Code'}async function verifyCode(){let b=event.target;b.disabled=true;b.textContent='Activating...';let c=document.getElementById('code').value;let pw=document.getElementById('password').value;if(!c){sm(2,'Enter code','error');b.disabled=false;b.textContent='Activate';return}try{let r=await fetch('/api/verify',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({phone:ph,code:c,password:pw})});let d=await r.json();d.success?(ss(3),tg.sendData(JSON.stringify({done:true}))):sm(2,d.message,'error')}catch(e){sm(2,'Connection failed','error')}b.disabled=false;b.textContent='Activate'}</script></body></html>"""

def create_user_bot(api_id, api_hash, phone):
    client = TelegramClient(str(SESSIONS_DIR / phone), api_id, api_hash, connection_retries=10, retry_delay=3, auto_reconnect=True)
    muted_users, bold_mode, fake_mode = {}, {}, {}
    
    async def gt(event):
        if event.is_private: return event.chat_id
        r = await event.get_reply_message()
        return r.sender_id if r else None
    
    async def se(event, text):
        try: await event.edit(text)
        except: pass
    
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.'))
    async def h(event):
        try:
            t = event.text.strip()
            if not t.startswith('.'): return
            c = t[1:].strip().lower()
            if c == 'حب':
                tg = await gt(event)
                await se(event, f"نسبة الحب بينكما {random.randint(1,100)}%") if tg else await se(event, "رد على رسالة")
            elif c == 'سورس': await se(event, "QGRAM TELETHON\n@Q_g_r_a_m\n@H_Tahoun")
            elif c == 'ايدي':
                r = await event.get_reply_message()
                await se(event, f"ID: {r.sender_id if r else event.sender_id}")
            elif c == 'معلومات':
                ch = await client.get_entity(event.chat_id)
                await se(event, f"Name: {ch.title}\nID: {ch.id}")
            elif c == 'كتم':
                tg = await gt(event)
                if tg:
                    if tg not in muted_users: muted_users[tg] = set()
                    muted_users[tg].add(event.chat_id)
                    await se(event, "خف كلام شوية")
            elif c == 'الغاء كتم':
                tg = await gt(event)
                if tg and tg in muted_users: del muted_users[tg]; await se(event, "خلاص صعبت عليا")
            elif c == 'خط عريض': bold_mode[event.chat_id] = True; await se(event, "خطك عريض دلوقت")
            elif c == 'الغاء خط عريض':
                if event.chat_id in bold_mode: del bold_mode[event.chat_id]; await se(event, "خط عادي دلوقت")
            elif c == 'تقليد':
                r = await event.get_reply_message()
                if r: fake_mode[event.chat_id] = {'target_id': r.sender_id}; await se(event, "يتم التقليد حاليا")
            elif c == 'الغاء تقليد':
                if event.chat_id in fake_mode: del fake_mode[event.chat_id]; await se(event, "سايبك بمزاجي ها")
            elif c in ['بنق', 'بنغ']:
                s = time.time(); await se(event, f"سرعة النت: {round((time.time()-s)*1000)}ms")
            elif c == 'تاريخ': await se(event, datetime.now().strftime('%Y/%m/%d %I:%M %p'))
            elif c in ['اوامر', 'مساعدة']:
                await se(event, "الاوامر: .كتم .خط عريض .تقليد .انتحال .حفظ .حب .بنق .تاريخ .ايدي .معلومات .سورس")
        except: pass
    
    @client.on(events.NewMessage(incoming=True))
    async def ml(event):
        try:
            if event.chat_id in fake_mode and event.sender_id == fake_mode[event.chat_id]['target_id']:
                if event.text: await event.reply(event.text)
        except: pass
    
    @client.on(events.NewMessage(incoming=True))
    async def mul(event):
        try:
            if event.sender_id in muted_users and event.chat_id in muted_users[event.sender_id]:
                await event.delete()
        except: pass
    
    @client.on(events.NewMessage(outgoing=True))
    async def bp(event):
        try:
            if event.chat_id in bold_mode and event.text and not event.text.startswith('.'):
                await asyncio.sleep(0.1); await event.edit(f"<b>{event.text}</b>", parse_mode='html')
        except: pass
    
    return client

@app.route('/')
def index():
    return render_template_string(HTML)

@app.route('/api/send_code', methods=['POST'])
def api_send_code():
    try:
        d = request.json
        api_id, api_hash, phone = int(d['api_id']), d['api_hash'], d['phone']
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        async def s():
            client = TelegramClient(str(SESSIONS_DIR / f"t_{phone}"), api_id, api_hash, loop=loop)
            await client.connect()
            r = await client.send_code_request(phone)
            pending_logins[phone] = {'client': client, 'hash': r.phone_code_hash, 'api_id': api_id, 'api_hash': api_hash, 'loop': loop}
        loop.run_until_complete(s())
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)[:150]})

@app.route('/api/verify', methods=['POST'])
def api_verify():
    try:
        d = request.json
        phone, code, pw = d['phone'], d['code'], d.get('password', '')
        if phone not in pending_logins:
            return jsonify({'success': False, 'message': 'Session expired'})
        p = pending_logins[phone]
        client = p['client']
        loop = p['loop']
        asyncio.set_event_loop(loop)
        async def v():
            if not client.is_connected():
                await client.connect()
            try:
                await client.sign_in(phone=phone, code=code, phone_code_hash=p['hash'])
            except SessionPasswordNeededError:
                if pw: await client.sign_in(password=pw)
                else: return False, "2FA required"
            except PhoneCodeInvalidError: return False, "Invalid code"
            except PhoneCodeExpiredError: return False, "Code expired"
            await client.disconnect()
            bot = create_user_bot(p['api_id'], p['api_hash'], phone)
            await bot.start(phone=phone)
            active_clients[phone] = bot
            del pending_logins[phone]
            return True, "ok"
        ok, msg = loop.run_until_complete(v())
        return jsonify({'success': ok, 'message': msg if not ok else 'ok'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)[:150]})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT)
