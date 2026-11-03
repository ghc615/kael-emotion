#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
kael_web.py —— 网页版外壳（不用装任何东西）

跑起来：
    python3 kael_web.py
然后浏览器打开 http://127.0.0.1:8765

左边聊天，右边看状态：情绪、身体、她此刻在哪、手上的活、欠了什么。
只用标准库，Windows 自带 Python 就能跑。
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

import emotion_v6
import pcm
import pcm_bridge

HOST, PORT = "127.0.0.1", 8765
DATA = os.environ.get("KAEL_DATA", "./pcm_data")
STATE = os.environ.get("KAEL_STATE", "./emotion_v6_state.json")
_lock = threading.Lock()


def _load():
    mind = emotion_v6.Mind()
    mind.state_path = STATE
    if os.path.exists(STATE):
        mind.load()
    if os.path.exists(os.path.join(DATA, "self.json")):
        store = pcm.PersonaMemory.load(DATA)
    else:
        store = pcm.PersonaMemory(pcm.DEMO_PROFILE, DATA)
        store.save()
    mind.name = store.profile.name
    bridge = pcm_bridge.Bridge(mind, store)
    return mind, store, bridge


MIND, STORE, BRIDGE = _load()


def snapshot() -> dict:
    m = MIND
    top = sorted(m.emotions.items(), key=lambda kv: kv[1], reverse=True)[:3]
    return {
        "name": m.name,
        "turns": m.turns,
        "emotions": {k: round(v) for k, v in top},
        "body": {"饿": round(m.hunger), "缺觉": round(m.sleep_debt), "疼": round(m.pain)},
        "hormones": {k: round(v) for k, v in m.hormones.items()},
        "place": getattr(m, "place", "屋里"),
        "activity": getattr(m, "activity", "发呆"),
        "desires": {k: round(v) for k, v in m.desires.items()},
        "skills": {k: round(v) for k, v in m.skills.items() if v > 0},
        "scars": dict(m.scars),
        "favor": round(m.favor),
        "crisis": m.crisis_count,
        "afterglow": (m.afterglow[0] or ""),
        "action": BRIDGE.last_action,
    }


PAGE = """<!doctype html>
<html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>%NAME%</title>
<style>
 :root{--bg:#14161a;--fg:#e8e6e3;--dim:#8b8f96;--line:#262a30;--accent:#7fb3a6}
 *{box-sizing:border-box}
 body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.65 -apple-system,"Segoe UI","Microsoft YaHei",sans-serif;height:100vh;display:flex;overflow:hidden}
 #chat{flex:1;display:flex;flex-direction:column;min-width:0}
 #log{flex:1;overflow-y:auto;padding:22px 20px}
 .bubble{max-width:78%;margin:10px 0;padding:10px 14px;border-radius:12px;white-space:pre-wrap;word-break:break-word}
 .me{background:#243040;margin-left:auto}
 .ai{background:#1b1e23;border:1px solid var(--line)}
 .meta{color:var(--dim);font-size:11px;margin-top:4px}
 #bar{display:flex;gap:8px;padding:12px;border-top:1px solid var(--line);background:#111317}
 #inp{flex:1;background:#1b1e23;border:1px solid var(--line);color:var(--fg);padding:11px 13px;border-radius:10px;font:inherit;resize:none;height:46px}
 button{background:#232830;color:var(--fg);border:1px solid var(--line);border-radius:10px;padding:0 16px;cursor:pointer;font:inherit}
 button:hover{border-color:var(--accent)}
 button:disabled{opacity:.5;cursor:default}
 #side{width:290px;border-left:1px solid var(--line);background:#111317;padding:16px;overflow-y:auto;font-size:13px}
 h3{margin:16px 0 6px;font-size:12px;color:var(--accent);letter-spacing:.08em;font-weight:600}
 h3:first-child{margin-top:0}
 .kv{display:flex;justify-content:space-between;color:var(--dim)}
 .kv b{color:var(--fg);font-weight:500}
 .tag{display:inline-block;background:#1b1e23;border:1px solid var(--line);border-radius:6px;padding:1px 7px;margin:2px 3px 2px 0;color:var(--dim)}
 @media(max-width:760px){#side{display:none}}
</style></head><body>
<div id="chat">
  <div id="log"></div>
  <div id="bar">
    <textarea id="inp" placeholder="说点什么…（Enter 发送，Shift+Enter 换行）"></textarea>
    <button id="send">说</button>
  </div>
</div>
<div id="side"></div>
<script>
const log=document.getElementById('log'), inp=document.getElementById('inp'), send=document.getElementById('send'), side=document.getElementById('side');
function add(text, cls, extra){const d=document.createElement('div');d.className='bubble '+cls;d.textContent=text;
  if(extra){const m=document.createElement('div');m.className='meta';m.textContent=extra;d.appendChild(m);}
  log.appendChild(d);log.scrollTop=log.scrollHeight;}
async function refresh(){const r=await fetch('/api/state');const s=await r.json();
  let h='';
  h+='<h3>此刻</h3><div class="kv"><span>在</span><b>'+s.place+'</b></div><div class="kv"><span>在做</span><b>'+s.activity+'</b></div>';
  h+='<h3>情绪</h3>';for(const k in s.emotions){h+='<div class="kv"><span>'+k+'</span><b>'+s.emotions[k]+'</b></div>';}
  h+='<h3>身体</h3>';for(const k in s.body){h+='<div class="kv"><span>'+k+'</span><b>'+s.body[k]+'</b></div>';}
  h+='<h3>六欲</h3>';for(const k in s.desires){h+='<span class="tag">'+k+' '+s.desires[k]+'</span>';}
  if(Object.keys(s.skills).length){h+='<h3>手上的活</h3>';for(const k in s.skills){h+='<span class="tag">'+k+' '+s.skills[k]+'</span>';}}
  if(Object.keys(s.scars).length){h+='<h3>旧伤</h3>';for(const k in s.scars){h+='<span class="tag">'+k+' '+s.scars[k].toFixed(1)+'</span>';}}
  h+='<h3>关系</h3><div class="kv"><span>好感</span><b>'+s.favor+'</b></div><div class="kv"><span>危机</span><b>'+s.crisis+'</b></div><div class="kv"><span>余温</span><b>'+(s.afterglow||'无')+'</b></div>';
  h+='<h3>轮数</h3><div class="kv"><span>总共</span><b>'+s.turns+'</b></div>';
  side.innerHTML=h;}
async function say(){
  const text=inp.value.trim(); if(!text||send.disabled) return;
  add(text,'me'); inp.value=''; send.disabled=true; add('…','ai');
  const dots=log.lastChild;
  try{
    const r=await fetch('/api/turn',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text})});
    const d=await r.json();
    dots.remove();
    add(d.reply, 'ai', d.action?('动作：'+d.action):'');
  }catch(e){dots.textContent='（没连上）';}
  send.disabled=false; inp.focus(); refresh();
}
send.onclick=say;
inp.addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();say();}});
add('%GREET%','ai'); refresh(); inp.focus();
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code: int, body: bytes, ctype: str = "text/html; charset=utf-8"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/":
            html = PAGE.replace("%NAME%", MIND.name).replace("%GREET%", "我在这儿。")
            self._send(200, html.encode("utf-8"))
        elif path == "/api/state":
            self._send(200, json.dumps(snapshot(), ensure_ascii=False).encode("utf-8"),
                       "application/json; charset=utf-8")
        else:
            self._send(404, b"not found")

    def do_POST(self):
        if urlparse(self.path).path != "/api/turn":
            return self._send(404, b"not found")
        try:
            n = int(self.headers.get("Content-Length", 0))
            data = json.loads(self.rfile.read(n).decode("utf-8") or "{}")
            text = (data.get("text") or "").strip()
        except Exception:
            return self._send(400, b"bad request")
        if not text:
            return self._send(200, json.dumps({"reply": "（没说话）", "action": ""},
                                              ensure_ascii=False).encode("utf-8"),
                              "application/json; charset=utf-8")
        try:
            with _lock:
                reply, _ = BRIDGE.turn(text, who="他")
                action = BRIDGE.last_action
            body = json.dumps({"reply": reply or "……", "action": action}, ensure_ascii=False)
        except Exception as e:
            body = json.dumps({"reply": f"（出错：{e}）", "action": ""}, ensure_ascii=False)
        self._send(200, body.encode("utf-8"), "application/json; charset=utf-8")


def main():
    has_key = (os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("OPENAI_API_KEY")
               or pcm_bridge._key_from_file())
    if not has_key:
        print("提示：没找到 key（环境变量和 key.txt 都没有），会只回半句兜底。")
    try:
        srv = ThreadingHTTPServer((HOST, PORT), Handler)
    except OSError as e:
        print(f"端口 {PORT} 起不来：{e}")
        print("八成是已经开了一个（先关掉旧窗口），或者端口被别的程序占了。")
        print("换个端口：在 kael_web.py 顶上一行改 PORT = 8766 再启动。")
        input("按回车退出…")
        sys.exit(1)
    print(f"{MIND.name} 在 http://{HOST}:{PORT}")
    try:
        webbrowser.open(f"http://{HOST}:{PORT}")
    except Exception:
        pass
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n（存好了。）")
        MIND.save()
        STORE.save()


if __name__ == "__main__":
    main()
