# server.py
import threading, asyncio, uuid, logging, sys
from flask import Flask, jsonify, request
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError
from telethon.sessions import StringSession
from shared import *            # يستورد كل المتغيرات والدوال، بما فيها main_loop

app = Flask(__name__)

# ------------------- موقع الويب -------------------
@app.route('/')
def home():
    return """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
<title>ninjathon — Setup</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
<style>
:root {
  --bg:      #0D0D12;
  --card:    #17171F;
  --lift:    #1C1C26;
  --border:  rgba(255,255,255,.07);
  --bhi:     rgba(255,255,255,.16);
  --white:   #FFFFFF;
  --off:     rgba(255,255,255,.55);
  --dim:     rgba(255,255,255,.28);
  --ghost:   rgba(255,255,255,.10);
  --ok:      #4ADE80;
  --err:     #F87171;
  --r:       14px;
  --r-lg:    22px;
  --shadow:  0 24px 64px rgba(0,0,0,.7);
}

*, *::before, *::after { margin:0; padding:0; box-sizing:border-box; }

body {
  font-family: 'Inter', system-ui, sans-serif;
  background: var(--bg);
  color: var(--white);
  min-height: 100dvh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 40px 16px 64px;
  -webkit-font-smoothing: antialiased;
  text-rendering: optimizeLegibility;
  overflow-x: hidden;
}

/* subtle noise */
body::before {
  content: '';
  position: fixed; inset: 0; z-index: 0;
  background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 200 200' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)' opacity='0.04'/%3E%3C/svg%3E");
  background-size: 180px;
  pointer-events: none;
  opacity: .5;
}

.wrap {
  position: relative; z-index: 1;
  width: 100%; max-width: 420px;
  display: flex; flex-direction: column; gap: 12px;
}

/* ── Header ── */
.hd { text-align: center; padding: 4px 0 14px; }

.logo {
  width: 68px; height: 68px;
  background: var(--white);
  border-radius: 20px;
  margin: 0 auto 18px;
  display: flex; align-items: center; justify-content: center;
  box-shadow: 0 0 0 1px rgba(255,255,255,.1), 0 16px 48px rgba(0,0,0,.6);
  animation: popIn .45s cubic-bezier(.34,1.56,.64,1) both;
}
.logo-mask {
  width: 40px; height: 18px;
  background: var(--bg);
  border-radius: 18px;
  display: flex; align-items: center; justify-content: center;
  gap: 9px;
}
.logo-eye {
  width: 10px; height: 10px;
  background: var(--white);
  border-radius: 50%;
}

.hd h1 {
  font-size: 26px; font-weight: 700;
  letter-spacing: -.6px;
  color: var(--white);
  line-height: 1.1;
  animation: fadeUp .4s .08s ease both;
}
.hd p {
  font-size: 12px; font-weight: 400;
  color: var(--dim);
  margin-top: 5px;
  letter-spacing: .4px;
  animation: fadeUp .4s .14s ease both;
}

/* ── Card ── */
.card {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: var(--r-lg);
  padding: 28px 24px 24px;
  box-shadow: var(--shadow);
  animation: fadeUp .4s .1s ease both;
  transition: border-color .3s;
}
.card:focus-within { border-color: var(--bhi); }

/* ── Step label ── */
.step-label {
  display: flex; align-items: center; gap: 10px;
  margin-bottom: 22px;
}
.step-dot {
  width: 26px; height: 26px;
  background: var(--white);
  border-radius: 8px;
  display: flex; align-items: center; justify-content: center;
  font-size: 12px; font-weight: 700; color: var(--bg);
  flex-shrink: 0;
}
.step-title {
  font-size: 14px; font-weight: 600;
  color: var(--off);
}

/* ── Back btn ── */
.back-btn {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 6px 12px;
  background: var(--ghost);
  border: 1px solid var(--border);
  border-radius: 9px;
  color: var(--dim);
  font-size: 12px; font-weight: 500; font-family: inherit;
  cursor: pointer;
  transition: color .2s, background .2s, border-color .2s;
  margin-bottom: 20px;
  -webkit-tap-highlight-color: transparent;
}
.back-btn:hover { color: var(--white); border-color: var(--bhi); background: rgba(255,255,255,.06); }
.back-btn svg { width: 13px; height: 13px; fill: currentColor; flex-shrink: 0; }

/* ── Field ── */
.field { margin-bottom: 12px; }

.field label {
  display: block;
  font-size: 11px; font-weight: 500;
  letter-spacing: .8px; text-transform: uppercase;
  color: var(--dim);
  margin-bottom: 6px;
}

/* wrapper keeps eye btn perfectly centered */
.fw {
  position: relative;
  display: flex; align-items: stretch;
}

.fw input {
  width: 100%; min-width: 0;
  height: 48px;
  padding: 0 46px 0 14px;
  background: var(--lift);
  border: 1px solid var(--border);
  border-radius: var(--r);
  color: var(--white);
  font-size: 15px; font-weight: 400; font-family: inherit;
  outline: none;
  transition: border-color .2s, box-shadow .2s;
  caret-color: var(--white);
  -webkit-appearance: none;
}
.fw input::placeholder { color: var(--ghost); }
.fw input:focus {
  border-color: rgba(255,255,255,.3);
  box-shadow: 0 0 0 3px rgba(255,255,255,.05);
}

#code {
  text-align: center;
  font-size: 26px; font-weight: 600;
  letter-spacing: 10px;
  padding-left: 10px; /* offset for centering with letter-spacing */
}
#code::placeholder { font-size: 18px; letter-spacing: 6px; font-weight: 300; }

/* eye toggle — absolute, fills height, perfectly centered */
.eye-btn {
  position: absolute;
  right: 0; top: 0; bottom: 0;
  width: 46px;
  display: flex; align-items: center; justify-content: center;
  background: none; border: none;
  cursor: pointer;
  color: var(--dim);
  transition: color .2s;
  -webkit-tap-highlight-color: transparent;
  padding: 0;
}
.eye-btn:hover { color: var(--white); }
.eye-btn svg {
  width: 17px; height: 17px;
  stroke: currentColor; stroke-width: 1.8;
  fill: none; stroke-linecap: round; stroke-linejoin: round;
  display: block; pointer-events: none;
  flex-shrink: 0;
}

/* ── Divider ── */
.divider {
  display: flex; align-items: center; gap: 10px;
  margin: 4px 0 14px;
}
.divider::before, .divider::after {
  content: ''; flex: 1; height: 1px;
  background: var(--border);
}
.divider span {
  font-size: 10px; font-weight: 500;
  letter-spacing: 1.2px; text-transform: uppercase;
  color: rgba(255,255,255,.18);
  white-space: nowrap;
}

/* ── Button ── */
.btn {
  width: 100%; height: 48px;
  border: none; border-radius: var(--r);
  font-size: 14px; font-weight: 600; font-family: inherit;
  letter-spacing: .1px;
  cursor: pointer;
  position: relative; overflow: hidden;
  display: flex; align-items: center; justify-content: center;
  -webkit-tap-highlight-color: transparent;
  transition: transform .15s, box-shadow .2s;
  margin-top: 8px;
}
.btn:active { transform: scale(.97); }

.btn-p {
  background: var(--white);
  color: var(--bg);
  box-shadow: 0 4px 20px rgba(255,255,255,.1);
}
.btn-p:hover { box-shadow: 0 6px 28px rgba(255,255,255,.18); }

.btn-s {
  background: transparent;
  color: var(--white);
  border: 1px solid rgba(255,255,255,.22);
}
.btn-s:hover { background: var(--ghost); border-color: var(--bhi); }

/* progress bar */
.prog {
  position: absolute; bottom: 0; left: 0;
  height: 2px; width: 0%;
  background: rgba(0,0,0,.18);
  border-radius: 0 0 var(--r) var(--r);
  transition: width .05s linear;
}
.btn-s .prog { background: rgba(255,255,255,.28); }

/* loading state */
.btn.loading { color: transparent !important; pointer-events: none; }
.btn.loading::before {
  content: '';
  position: absolute; top: 50%; left: 50%;
  width: 18px; height: 18px; margin: -9px 0 0 -9px;
  border: 2px solid rgba(0,0,0,.15);
  border-top-color: var(--bg);
  border-radius: 50%;
  animation: spin .65s linear infinite;
}
.btn-s.loading::before {
  border-color: rgba(255,255,255,.2);
  border-top-color: var(--white);
}

/* ── Result ── */
.result {
  display: none; margin-top: 14px;
  padding: 12px 14px; border-radius: var(--r);
  font-size: 13px; font-weight: 500; text-align: center; line-height: 1.5;
  animation: fadeUp .3s ease;
}
.result.show { display: block; }
.result.ok  { background: rgba(74,222,128,.08); border: 1px solid rgba(74,222,128,.2); color: var(--ok); }
.result.err { background: rgba(248,113,113,.08); border: 1px solid rgba(248,113,113,.2); color: var(--err); }

/* ── Info card ── */
.info-card {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: var(--r-lg);
  padding: 22px 24px;
  animation: fadeUp .4s .2s ease both;
}
.info-card-title {
  font-size: 11px; font-weight: 600;
  letter-spacing: .8px; text-transform: uppercase;
  color: var(--dim);
  margin-bottom: 14px;
  display: flex; align-items: center; gap: 7px;
}
.info-card-title svg { flex-shrink: 0; }

.info-steps { list-style: none; }
.info-steps li {
  font-size: 13px; color: var(--dim);
  line-height: 1.7;
  display: flex; gap: 9px; align-items: flex-start;
  margin-bottom: 3px;
}
.step-n {
  font-size: 10px; font-weight: 700;
  color: var(--bg); background: var(--dim);
  width: 17px; height: 17px; border-radius: 5px;
  display: flex; align-items: center; justify-content: center;
  flex-shrink: 0; margin-top: 3px;
}
.info-steps strong { color: var(--off); font-weight: 500; }

.tg-link {
  display: flex; align-items: center; justify-content: center; gap: 8px;
  margin-top: 16px; padding: 12px;
  background: var(--ghost);
  border: 1px solid var(--border);
  border-radius: var(--r);
  color: var(--off);
  font-size: 13px; font-weight: 500;
  text-decoration: none;
  transition: background .2s, border-color .2s, color .2s;
  -webkit-tap-highlight-color: transparent;
}
.tg-link:hover { background: rgba(255,255,255,.08); border-color: var(--bhi); color: var(--white); }
.tg-link svg { width: 16px; height: 16px; fill: currentColor; flex-shrink: 0; }

/* ── Utils ── */
.hidden { display: none !important; }

/* ── Animations ── */
@keyframes popIn {
  from { opacity: 0; transform: scale(.6); }
  to   { opacity: 1; transform: scale(1); }
}
@keyframes fadeUp {
  from { opacity: 0; transform: translateY(14px); }
  to   { opacity: 1; transform: translateY(0); }
}
@keyframes spin { to { transform: rotate(360deg); } }

/* ── Responsive ── */
@media (max-width: 380px) {
  .card { padding: 22px 18px 20px; }
  .hd h1 { font-size: 22px; }
  #code { font-size: 22px; letter-spacing: 8px; }
}
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { animation: none !important; transition-duration: .01ms !important; }
}
</style>
</head>
<body>

<div class="wrap">

  <!-- Header -->
  <div class="hd">
    <div class="logo" aria-hidden="true">
      <div class="logo-mask">
        <div class="logo-eye"></div>
        <div class="logo-eye"></div>
      </div>
    </div>
    <h1>ninjathon</h1>
    <p>Telethon Setup &middot; by ninjagram</p>
  </div>

  <!-- Card -->
  <div class="card">

    <!-- Step 1 -->
    <div id="step1">
      <div class="step-label">
        <div class="step-dot">1</div>
        <span class="step-title">Account credentials</span>
      </div>

      <div class="field">
        <label>API ID</label>
        <div class="fw">
          <input id="api_id" type="password" placeholder="12345678" inputmode="numeric" autocomplete="off" spellcheck="false">
          <button class="eye-btn" type="button" onclick="toggleVis('api_id',this)" aria-label="Toggle visibility">
            <svg class="i-hide" viewBox="0 0 24 24"><path d="M17.94 17.94A10.07 10.07 0 0112 20c-7 0-11-8-11-8a18.45 18.45 0 015.06-5.94M9.9 4.24A9.12 9.12 0 0112 4c7 0 11 8 11 8a18.5 18.5 0 01-2.16 3.19m-6.72-1.07a3 3 0 11-4.24-4.24"/><line x1="1" y1="1" x2="23" y2="23"/></svg>
            <svg class="i-show" viewBox="0 0 24 24" style="display:none"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
          </button>
        </div>
      </div>

      <div class="field">
        <label>API Hash</label>
        <div class="fw">
          <input id="api_hash" type="password" placeholder="0123456789abcdef…" autocomplete="off" spellcheck="false">
          <button class="eye-btn" type="button" onclick="toggleVis('api_hash',this)" aria-label="Toggle visibility">
            <svg class="i-hide" viewBox="0 0 24 24"><path d="M17.94 17.94A10.07 10.07 0 0112 20c-7 0-11-8-11-8a18.45 18.45 0 015.06-5.94M9.9 4.24A9.12 9.12 0 0112 4c7 0 11 8 11 8a18.5 18.5 0 01-2.16 3.19m-6.72-1.07a3 3 0 11-4.24-4.24"/><line x1="1" y1="1" x2="23" y2="23"/></svg>
            <svg class="i-show" viewBox="0 0 24 24" style="display:none"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
          </button>
        </div>
      </div>

      <div class="field">
        <label>Phone number</label>
        <div class="fw">
          <input id="phone" type="password" placeholder="+201234567890" inputmode="tel" autocomplete="off" spellcheck="false">
          <button class="eye-btn" type="button" onclick="toggleVis('phone',this)" aria-label="Toggle visibility">
            <svg class="i-hide" viewBox="0 0 24 24"><path d="M17.94 17.94A10.07 10.07 0 0112 20c-7 0-11-8-11-8a18.45 18.45 0 015.06-5.94M9.9 4.24A9.12 9.12 0 0112 4c7 0 11 8 11 8a18.5 18.5 0 01-2.16 3.19m-6.72-1.07a3 3 0 11-4.24-4.24"/><line x1="1" y1="1" x2="23" y2="23"/></svg>
            <svg class="i-show" viewBox="0 0 24 24" style="display:none"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
          </button>
        </div>
      </div>

      <button class="btn btn-p" id="sendBtn" onclick="sendCode()">
        Send verification code
        <div class="prog" id="prog1"></div>
      </button>
    </div>

    <!-- Step 2 -->
    <div id="step2" class="hidden">
      <button class="back-btn" type="button" onclick="backToStep1()">
        <svg viewBox="0 0 24 24"><path d="M19 12H5M12 5l-7 7 7 7"/></svg>
        Back
      </button>

      <div class="step-label">
        <div class="step-dot">2</div>
        <span class="step-title">Verification</span>
      </div>

      <div class="field">
        <label>Confirmation code</label>
        <div class="fw">
          <input id="code" type="password" placeholder="·····" maxlength="5" inputmode="numeric" autocomplete="one-time-code" spellcheck="false">
          <button class="eye-btn" type="button" onclick="toggleVis('code',this)" aria-label="Toggle visibility">
            <svg class="i-hide" viewBox="0 0 24 24"><path d="M17.94 17.94A10.07 10.07 0 0112 20c-7 0-11-8-11-8a18.45 18.45 0 015.06-5.94M9.9 4.24A9.12 9.12 0 0112 4c7 0 11 8 11 8a18.5 18.5 0 01-2.16 3.19m-6.72-1.07a3 3 0 11-4.24-4.24"/><line x1="1" y1="1" x2="23" y2="23"/></svg>
            <svg class="i-show" viewBox="0 0 24 24" style="display:none"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
          </button>
        </div>
      </div>

      <div class="divider"><span>Optional</span></div>

      <div class="field">
        <label>2FA password</label>
        <div class="fw">
          <input id="password" type="password" placeholder="••••••••" autocomplete="current-password" spellcheck="false">
          <button class="eye-btn" type="button" onclick="toggleVis('password',this)" aria-label="Toggle visibility">
            <svg class="i-hide" viewBox="0 0 24 24"><path d="M17.94 17.94A10.07 10.07 0 0112 20c-7 0-11-8-11-8a18.45 18.45 0 015.06-5.94M9.9 4.24A9.12 9.12 0 0112 4c7 0 11 8 11 8a18.5 18.5 0 01-2.16 3.19m-6.72-1.07a3 3 0 11-4.24-4.24"/><line x1="1" y1="1" x2="23" y2="23"/></svg>
            <svg class="i-show" viewBox="0 0 24 24" style="display:none"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
          </button>
        </div>
      </div>

      <button class="btn btn-p" id="verifyBtn" onclick="verify()">
        Activate Telethon
        <div class="prog" id="prog2"></div>
      </button>
    </div>

    <div class="result" id="result"></div>
  </div>

  <!-- Info card -->
  <div class="info-card">
    <div class="info-card-title">
      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>
      How to get API credentials
    </div>
    <ol class="info-steps">
      <li><span class="step-n">1</span><span>Open Telegram and go to <strong>my.telegram.org</strong></span></li>
      <li><span class="step-n">2</span><span>Sign in with your phone number</span></li>
      <li><span class="step-n">3</span><span>Open <strong>API development tools</strong></span></li>
      <li><span class="step-n">4</span><span>Create an app — copy your <strong>api_id</strong> and <strong>api_hash</strong></span></li>
    </ol>
    <a class="tg-link" href="https://my.telegram.org/apps" target="_blank" rel="noopener">
      <svg viewBox="0 0 24 24"><path d="M12 0C5.373 0 0 5.373 0 12s5.373 12 12 12 12-5.373 12-12S18.627 0 12 0zm5.894 8.221-1.97 9.28c-.145.658-.537.818-1.084.508l-3-2.21-1.447 1.394c-.16.16-.295.295-.605.295l.213-3.053 5.56-5.023c.242-.213-.054-.333-.373-.12l-6.871 4.326-2.962-.924c-.643-.204-.657-.643.136-.953l11.57-4.461c.537-.194 1.006.131.833.941z"/></svg>
      Open my.telegram.org
    </a>
  </div>

</div>

<script>
const $ = id => document.getElementById(id);
let currentPhone = '';

function showResult(msg, ok) {
  const r = $('result');
  r.className = 'result show ' + (ok ? 'ok' : 'err');
  r.textContent = msg;
}

function toggleVis(fieldId, btn) {
  const inp  = $(fieldId);
  const hide = btn.querySelector('.i-hide');
  const show = btn.querySelector('.i-show');
  const isHidden = inp.type === 'password';
  inp.type = isHidden ? 'text' : 'password';
  if (hide) hide.style.display = isHidden ? 'none'  : 'block';
  if (show) show.style.display = isHidden ? 'block' : 'none';
}

function runProgress(barId, duration) {
  const bar = $(barId);
  let w = 0;
  bar.style.transition = 'width .05s linear';
  bar.style.width = '0%';
  const step = 100 / (duration / 50);
  const iv = setInterval(() => {
    w = Math.min(w + step + Math.random() * step * .4, 90);
    bar.style.width = w + '%';
    if (w >= 90) clearInterval(iv);
  }, 50);
  return {
    finish() {
      clearInterval(iv);
      bar.style.transition = 'width .25s ease';
      bar.style.width = '100%';
      setTimeout(() => { bar.style.width = '0%'; bar.style.transition = 'width .05s linear'; }, 300);
    }
  };
}

async function sendCode() {
  const api_id   = $('api_id').value.trim();
  const api_hash = $('api_hash').value.trim();
  const phone    = $('phone').value.trim();
  if (!api_id || !api_hash || !phone) { showResult('Please fill all fields', false); return; }
  const btn  = $('sendBtn');
  btn.classList.add('loading');
  const prog = runProgress('prog1', 4000);
  try {
    const fd = new FormData();
    fd.append('api_id', api_id); fd.append('api_hash', api_hash); fd.append('phone', phone);
    const res  = await fetch('/api/send_code', { method: 'POST', body: fd });
    const data = await res.json();
    prog.finish();
    if (data.status === 'code_sent' || data.status === 'already_active') {
      currentPhone = phone;
      if (data.status === 'code_sent') {
        $('step1').classList.add('hidden');
        $('step2').classList.remove('hidden');
        showResult('Verification code sent to your Telegram', true);
      } else {
        showResult('Session already active', true);
      }
    } else {
      showResult(data.message || 'An error occurred', false);
    }
  } catch (e) {
    prog.finish();
    showResult('Connection error', false);
  } finally {
    btn.classList.remove('loading');
  }
}

async function verify() {
  const code     = $('code').value.trim();
  const password = $('password').value;
  if (!code) { showResult('Enter the verification code', false); return; }
  const btn  = $('verifyBtn');
  btn.classList.add('loading');
  const prog = runProgress('prog2', 5000);
  try {
    const fd = new FormData();
    fd.append('phone', currentPhone); fd.append('code', code); fd.append('password', password);
    const res  = await fetch('/api/verify', { method: 'POST', body: fd });
    const data = await res.json();
    prog.finish();
    if (data.status === 'success') {
      showResult('Telethon activated successfully', true);
      setTimeout(() => { location.reload(); }, 3000);
    } else {
      showResult(data.message || 'Verification failed', false);
    }
  } catch (e) {
    prog.finish();
    showResult('Connection error', false);
  } finally {
    btn.classList.remove('loading');
  }
}

function backToStep1() {
  $('step2').classList.add('hidden');
  $('step1').classList.remove('hidden');
  $('result').className = 'result';
}

document.addEventListener('keydown', e => {
  if (e.key !== 'Enter') return;
  if (!$('step2').classList.contains('hidden')) verify();
  else if (!$('step1').classList.contains('hidden')) sendCode();
});
</script>
</body>
</html>
"""

@app.route('/health')
def health():
    return "OK", 200

# ------------------- API -------------------
@app.route('/api/send_code', methods=['POST'])
def api_send_code():
    try:
        api_id = int(request.form.get('api_id'))
        api_hash = request.form.get('api_hash')
        phone = request.form.get('phone', '').strip()
        if not api_id or not api_hash or not phone:
            return jsonify({"status": "error", "message": "All fields required"}), 400

        async def _send():
            api_configs_storage[phone] = {'api_id': api_id, 'api_hash': api_hash}
            client = TelegramClient(StringSession(), api_id, api_hash)
            await client.connect()
            if await client.is_user_authorized():
                active_clients[phone] = client
                client_me[phone] = await client.get_me()
                start_client_in_background(client, phone)          # <-- تم إصلاحه
                await save_all_sessions()
                return jsonify({"status": "already_active", "message": "Session already active"})
            sent = await client.send_code_request(phone)
            pending_logins[phone] = (client, sent.phone_code_hash, api_id, api_hash)
            return jsonify({"status": "code_sent", "message": "Verification code sent"})
        return run_in_main(_send())
    except Exception as e:
        logger.error(f"خطأ في إرسال الكود: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/verify', methods=['POST'])
def api_verify():
    phone = request.form.get('phone', '').strip()
    code = request.form.get('code', '').strip()
    password = request.form.get('password')
    if not phone or not code or phone not in pending_logins:
        return jsonify({"status": "error", "message": "Invalid session"}), 400

    async def _verify():
        client, phone_code_hash, api_id, api_hash = pending_logins[phone]
        try:
            try:
                await client.sign_in(phone=phone, code=code, phone_code_hash=phone_code_hash)
            except SessionPasswordNeededError:
                if not password:
                    return jsonify({"status": "error", "message": "2FA password required"}), 401
                await client.sign_in(password=password)
            active_clients[phone] = client
            client_me[phone] = await client.get_me()
            del pending_logins[phone]
            await save_all_sessions()
            start_client_in_background(client, phone)          # <-- تم إصلاحه
            await notify_dev(f"تم تفعيل مستخدم جديد: {phone}")
            return jsonify({"status": "success", "message": "Telethon installed successfully"})
        except Exception as e:
            logger.error(f"خطأ في التحقق: {e}")
            return jsonify({"status": "error", "message": str(e)}), 400
    return run_in_main(_verify())

def run_in_main(coro):
    from shared import main_loop
    future = asyncio.run_coroutine_threadsafe(coro, main_loop)
    return future.result(timeout=60)
