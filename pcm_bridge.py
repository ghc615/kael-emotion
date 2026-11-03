#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pcm_bridge.py v15 (Final)
1. 统一导入 pcm 的危机正则。
2. 修复 _SELF_PAT 心疼误判。
3. 彻底解耦 say() 死代码，完全由 bridge 决定输出。
"""
from __future__ import annotations
import json, os, random, re, sys, time, urllib.request

try:
    import archive
    try:
        import body                      # 身体接口（本仓库不含，接入时自带）
    except ImportError:
        class _NoBody:
            def act(self, *a, **k): pass
            def on_action(self, *a, **k): pass
        body = _NoBody()
    import feed
    from emotion_v6 import Mind
    from pcm import PersonaMemory, SelfProfile, DEMO_PROFILE, crisis_level
except ImportError as e:
    sys.exit(f"缺失依赖: {e}. 请确保 emotion_v6.py, pcm.py, pcm_bridge.py 在同一目录")

_SELF_PAT = re.compile(r"(我|俺)([^，。！？,.!?\n]{0,8})(饿|没吃|累|困|(?<!心)疼|病|难受|不舒服|睡不着|撑不住)")
_RAW_WEAK = re.compile(r"(饿死了|没吃饭|没吃东西|累死了|困死了|(?<!心)疼死了|(?<!心)难受死了|不舒服|痛死了)")
_NEGATORS = ("不", "没", "别", "无", "未", "非")

KIND_TO_BIAS = {
    "wound": {"悲伤": -4.0, "恐惧": -4.0},
    "state": {"悲伤": -2.0},
    "user_aggression": {"愤怒": -8.0, "悲伤": -4.0},
    "user_warmth": {"愤怒": +5.0, "恐惧": +2.0},
}

def default_preprocess(text: str, who: str) -> tuple[str, str | None]:
    # 分级拦截：自杀级走危机，高危示弱走示弱
    lv = crisis_level(text)
    if lv == "crisis":
        return text, "自毁危机"
    if lv == "weak":
        return text, "对方示弱"

    # "我心疼得难受" 里的 难受 会被兜底规则误判成示弱；
    # 只要"心疼"没被否定，整句就是关心，先处理掉。
    i = text.find("心疼")
    if i >= 0 and not any(neg in text[max(0, i - 3):i] for neg in _NEGATORS):
        return text, "被关心"
    for m in _SELF_PAT.finditer(text):
        between = m.group(2)
        if any(t in between for t in ("朋友", "同学", "他", "她", "妈", "爸", "奶奶", "爷爷")):
            continue                      # "我朋友撑不住了" 是说他，不是说我自己
        if not any(neg in between for neg in _NEGATORS):
            return text, "对方示弱"

    for m in _RAW_WEAK.finditer(text):
        prefix = text[max(0, m.start()-3):m.start()]
        if any(neg in prefix for neg in _NEGATORS):
            continue
        if "？" in text or "?" in text:      # "你不舒服吗？" 是在问，不是在示弱
            continue
        if any(p in prefix for p in ("你", "他", "她", "它")):
            continue
        return text, "对方示弱"

    return text, None

def _key_from_file() -> str:
    """双击启动脚本时没有环境变量：允许把 key 写进同目录 key.txt。"""
    try:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "key.txt")
        if os.path.exists(path):
            return open(path, encoding="utf-8").read().strip()
    except Exception:
        pass
    return ""


def call_llm(messages: list[dict]) -> str:
    ds_key = os.environ.get("DEEPSEEK_API_KEY") or _key_from_file()
    oa_key = os.environ.get("OPENAI_API_KEY")
    
    if ds_key:
        api_key = ds_key
        base_url = os.environ.get("LLM_BASE_URL", "https://api.deepseek.com/chat/completions")
        model = os.environ.get("LLM_MODEL", "deepseek-chat")
    elif oa_key:
        api_key = oa_key
        base_url = os.environ.get("LLM_BASE_URL", "https://api.openai.com/v1/chat/completions")
        model = os.environ.get("LLM_MODEL", "gpt-4o-mini")
    else:
        return ""
    
    # 回复长度上限：默认 1200；想让她想多长就多长，就把它调大（比如 2000）
    try:
        max_tokens = int(os.environ.get("LLM_MAX_TOKENS", "1200"))
    except Exception:
        max_tokens = 400
    data = {"model": model, "messages": messages, "temperature": 0.8, "max_tokens": max_tokens}
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
    body = json.dumps(data).encode("utf-8")
    for attempt in (1, 2):
        try:
            req = urllib.request.Request(base_url, data=body, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=15) as resp:
                res = json.loads(resp.read().decode("utf-8"))
                return res["choices"][0]["message"]["content"].strip()
        except Exception as e:
            if attempt == 2:
                sys.stderr.write(f"\n[Bridge] LLM 调用失败({base_url}): {e}\n")
                return ""
            time.sleep(1.0)      # 抖动一次，等一秒再来

_TAG_PRIORITY = ("被否定", "被抛弃", "受伤", "家人", "被关心", "亲密")
# 语义路由：先判断对方在问什么，再决定怎么答
_ROUTES = [
    ("relation", ("我们", "关系", "喜欢", "爱", "是不是你", "要不要", "在一起", "娶", "嫁")),
    ("memory",   ("记得", "上次", "以前", "那天", "说过", "还记得")),
    ("self",     ("你怎么", "你感觉", "你想", "你累", "你饿", "你难过", "你开心")),
    ("person",   ("我是什么", "我这个人", "你觉得我", "我是不是")),
    ("fact",     ("怎么", "为什么", "多少", "能不能", "帮我", "怎么做")),
]

def route(text: str) -> str:
    for name, keys in _ROUTES:
        if any(k in text for k in keys):
            return name
    return "chat"

_TRACE_OF_TAGS = {
    "被否定": "被否定", "被抛弃": "被丢下", "受伤": "病",
    "被关心": "被接住", "亲密": "被接住", "家人": "被丢下",
}

class Bridge:
    def __init__(self, mind: Mind, pcm: PersonaMemory, preprocess=None, handoff_interval=40):
        self.mind = mind
        self.pcm = pcm
        self.preprocess = preprocess or default_preprocess
        self.handoff_interval = handoff_interval
        self._turn_count = 0
        self._last_handoff_raw = self.pcm.raw.count()
        self.recent_turns = []
        self._crisis_left = 0      
        self._crisis_seen = 0
        self._idle_fail = 0
        self._recent_inner = []
        self.last_action = ""
        self._recent_actions = []      # 刚做过什么动作，防止每轮都“抬手看表、叹口气”
        body.on_action(self._after_action)      

    def turn(self, user_text: str, who: str = "他", now: float | None = None):
        now = now or time.time()
        self.mind._route = route(user_text)
        # idle 熔断：连续失败 3 次暂停，但每 20 轮给一次复活机会，不能一坏就永久禁用
        if self._idle_fail >= 3 and (self._turn_count + 1) % 20 == 0:
            self._idle_fail = 0
            sys.stderr.write("[Bridge] idle 熔断重置，重试\n")
        if self._idle_fail < 3:
            try:
                self.mind.idle(now)   # 没人说话时，角色自己也在漂（idle 内部有 gap 门槛）
                self._idle_fail = 0
            except Exception as e:
                self._idle_fail += 1
                sys.stderr.write(f"[Bridge] idle error({self._idle_fail}/3): {e}\n")

        try:
            one = feed.fetch_one(now)          # 三小时一次，自己看点什么
            if one:
                self.mind.add_thought("刚看到：" + one["title"], ttl=4 * 3600)
                self.mind.learn(one["title"])
        except Exception as e:
            sys.stderr.write(f"[Bridge] feed: {e}\n")
        self.mind.last_speak = now
        self.mind.pulse(now)        # 心跳：没人说话时她也在过日子
        self._sync_budget(now)      # 余额就是饭钱：钱少了，人就饿
        hits = self.pcm.recall(user_text, k=8)
        # 刚说过的话不算“记忆”：不然你问“你记得X吗”，她拿你这句话当证据
        _fresh = [h for h in hits if now - getattr(h[0], "when", 0) > 180]
        hits = _fresh if _fresh else hits[:1]
        mem_prompt = ""
        self.mind.memory_bias = {} 
        
        if hits:
            mem_lines = ["【你想起了以前的事】"]
            for m, _ in hits:
                mem_lines.append(f"- {m.content}")
                kind_to_use = m.kind
                if m.speaker == self.mind.name and m.kind in ("wound", "state"):
                    kind_to_use = m.kind
                elif m.speaker != self.mind.name and m.kind in ("user_aggression", "user_warmth"):
                    kind_to_use = m.kind
                else:
                    kind_to_use = None
                
                if kind_to_use and kind_to_use in KIND_TO_BIAS:
                    for emo, bias in KIND_TO_BIAS[kind_to_use].items():
                        self.mind.add_bias(emo, bias)

                tr = next((_TRACE_OF_TAGS[t] for t in _TAG_PRIORITY if t in (m.tags or ())), None)
                if tr is None:
                    tr = {"wound": "病", "user_aggression": "被否定"}.get(kind_to_use or "")
                if tr:
                    if kind_to_use in ("wound", "user_aggression"):
                        self.mind.wound(tr, 0.05)
                    elif kind_to_use in ("bond", "user_warmth"):
                        self.mind.heal(tr, 0.02)
            mem_lines.append("")
            mem_lines.append("【规矩】只准拿上面这些、和你确实记得的说事。")
            mem_lines.append("上面没有的细节（哪天的截图、什么气味、具体说了哪句），一律不许补。")
            mem_lines.append("记不清就说记不清，或者直接问回去——不要为了让话好听而编。")
            mem_lines.append("也不许反过来说“不是那回事”“我没说过”——你只是记不清，不是能证伪。")
            mem_prompt = "\n".join(mem_lines)

        # 摘要记不清的时候，去原文里翻（只翻，不编）
        state_prompt = ""      # 后面才生成；这里先占位，去重要用
        _arc = os.environ.get("KAEL_ARCHIVE") or ""
        if not _arc:
            for _c in ("./record.txt", "./archive.txt", os.path.join(self.pcm.data_dir, "archive.txt")):
                if os.path.exists(_c):
                    _arc = _c
                    break
        # 不靠记忆分数判断：那个分数普遍虚高，会把档案入口堵死。
        # 只要是“你记得吗/我们之间/你觉得我”这类问法，就直接去档案里翻一次。
        if _arc and len(user_text) >= 4 and self.mind._route in ("memory", "relation", "person"):
            found = archive.search(_arc, user_text, k=2, context=1)   # 证据常在邻行
            # 和已有的记忆重复就别再放一遍，省上下文
            found = [x for x in found
                     if x[:24] not in mem_prompt and x[:24] not in state_prompt]
            if found:
                mem_prompt += ("\n【档案里翻到的原文】（这是记录，不是你记起来的）\n"
                               + "\n".join(f"- {x[:800]}" for x in found) + "\n")

        text_for_mind, hint = self.preprocess(user_text, who)
        try:
            self.mind.event(text_for_mind, who=who, now=now, force_event=hint)
        except Exception as e:
            sys.stderr.write(f"[Bridge] mind.event error: {e}\n")

        self._turn_count += 1

        # 主动提起旧事：从命中里挑一条"有年头"的，偶尔让它自己冒出来
        self.mind._callback = None
        self._archive_cb = ""
        if hits and random.random() < 0.35:
            old = [m for m, _ in hits
                   if (now - getattr(m, "when", now)) > 1800
                   and m.kind not in ("inner", "danger")]   # 旧事：有年头、又不是心声和危机
            if old:
                pick = random.choice(old).content
                self.mind._callback = pick.replace("说：", "说过：", 1)
                if _arc:
                    _hit = archive.search(_arc, pick, k=1)
                    if _hit and _hit[0][:20] not in (mem_prompt or ""):
                        self._archive_cb = _hit[0][:400]
        # 把最近两轮的开头交给 Mind，用来避免千篇一律的"（动作）嗯。"
        self.mind._route = route(user_text)
        self.mind._recent_shapes = [x[:10] for _, x in self.recent_turns[-2:]]
        state_prompt = self.mind.say_prompt()
        if getattr(self, "_archive_cb", ""):
            state_prompt += ("\n（档案里那句原文，能对上你想起来的事："
                             + self._archive_cb.replace("\n", " ") + "）")
        if self._recent_actions:
            _a = "；".join(self._recent_actions[-3:])
            state_prompt += f"\n（你刚才做过这些动作：{_a}——这轮换个不一样的，别重复同一个。）"
        boot_prompt = self.pcm.boot(scene_hint=user_text, hits=hits)
        full_sys_prompt = f"{boot_prompt}\n\n{mem_prompt}\n\n{state_prompt}"
        
        messages = [{"role": "system", "content": full_sys_prompt}]
        for u, a in self.recent_turns[-5:]:
            messages.append({"role": "user", "content": u})
            messages.append({"role": "assistant", "content": a})
        messages.append({"role": "user", "content": user_text})
        
        # 偶尔不说话，只留一个动作。人不是每句都接。
        # 但对方喊疼、喊累、说害怕的时候，不许沉默——那不叫"像人"，那叫冷血。
        _crisis_pre = crisis_level(user_text) is not None
        _distress = re.search(r"(疼|难受|不舒服|累|困|饿|怕|慌|哭|喘|晕|血|睡不着|不想)", user_text)
        # 打招呼、叫人、问在不在——这些必须应，不能拿沉默对付
        _greet = re.search(r"(回来|在吗|在不在|你好|喂|哈喽|晚安|早安|睡了)", user_text)
        _can_silent = (self.mind._route == "chat" and not _crisis_pre
                       and not _distress and not _greet and 1 <= len(user_text) <= 8)
        if (_can_silent and random.random() < 0.08):
            real_reply = "（" + random.choice(["没说话", "只是看了你一眼", "嗯了一声", "把杯子往你那边推了推"]) + "）"
        else:
            try:
                real_reply = call_llm(messages)
            except Exception as e:
                # 模型/网络出什么事都不能把这一轮变成崩溃
                sys.stderr.write(f"[Bridge] 这一轮没答上来：{e}\n")
                real_reply = ""
        inner = ""
        if real_reply:
            # 双轨：第一段是心声，其余是台词。模型常不听话，格式得宽容。
            # 模型经常不按两行写：可能"心声：…（动作）…"挤一行，也可能没有结尾换行
            # 三段式：心声 / 动作 / 说。动作交给身体，嘴只说话。
            m_inner = re.search(r"^\s*[*_]{0,2}\s*心声\s*[*_]{0,2}\s*[:：]\s*(.*)$", real_reply, re.M)
            m_act = re.search(r"^\s*[*_]{0,2}\s*动作\s*[*_]{0,2}\s*[:：]\s*(.*)$", real_reply, re.M)
            m_say = re.search(r"^\s*[*_]{0,2}\s*(?:说|台词)\s*[*_]{0,2}\s*[:：]\s*(.*)$", real_reply, re.M)
            if m_inner:
                inner = re.sub(r"[*_]", "", m_inner.group(1)).strip()
            if m_act:
                self.last_action = re.sub(r"[*_（）()]", "", m_act.group(1)).strip()
                # 同一动作连着来：这轮干脆不动，比复读机强
                if self._recent_actions and self.last_action == self._recent_actions[-1]:
                    sys.stderr.write("[Bridge] 动作重复，这一轮跳过\n")
                    self.last_action = ""
                elif self.last_action not in self._recent_actions:
                    self._recent_actions.append(self.last_action)
                    self._recent_actions = self._recent_actions[-3:]
                body.act(self.last_action)      # 动作交给身体去执行，嘴上不再念
            if m_say:
                real_reply = re.sub(r"[*_]", "", m_say.group(1)).strip()
            elif m_act or m_inner:
                # 只有动作和心声、没有话——那就不说话，只做
                rest = re.sub(r"^\s*[*_]{0,2}\s*(?:心声|动作)\s*[*_]{0,2}\s*[:：].*$", "", real_reply, flags=re.M).strip()
                real_reply = rest or "（没说话）"
        
        # 旧存档或异常数据可能把 afterglow 存成 [] 或长度不为 2，直接解包会 ValueError
        ag = getattr(self.mind, "afterglow", (None, 0))
        after, until = ag if isinstance(ag, (tuple, list)) and len(ag) == 2 else (None, 0)
        in_crisis = (after == "危机" and now < until)
        
        if in_crisis:
            if until != self._crisis_seen:
                self._crisis_seen = until
                self._crisis_left = 2
            if self._crisis_left > 0:
                self._crisis_left -= 1
            else:
                in_crisis = False
                
        # 最终输出逻辑
        if real_reply:
            final_reply = real_reply
        elif in_crisis:
            final_reply = self.mind.say_crisis()
        else:
            final_reply = self.mind.say_short()
        
        if final_reply:
            self.recent_turns.append((user_text, final_reply))
            if len(self.recent_turns) > 10: self.recent_turns.pop(0)

        # 同一句心声连着两轮就不再存：否则 recall 会把它捞回来，模型越说越像复读
        self._recent_inner = getattr(self, "_recent_inner", [])
        if inner:
            self.mind.add_thought(inner)      # 心声变成念头，跟着走几轮
        if inner and inner not in self._recent_inner[-2:]:
            self.pcm.ingest([{"speaker": self.mind.name,
                              "content": f"（心里想：{inner}）", "ts": now + 0.0005}])
            self._recent_inner = (self._recent_inner + [inner])[-4:]
        # 这一轮她有多激动：情绪越冲，这一段记得越久
        _peak = max(self.mind.emotions.values()) / 100.0 if self.mind.emotions else 0.0
        self.pcm.ingest([
            {"speaker": who, "content": user_text, "ts": now},
            {"speaker": self.mind.name, "content": final_reply, "ts": now + 0.001},
        ], intensity=_peak)

        # 她想干的事，如果这轮聊到了，就算做成了（不用谁去点“完成”）
        for g in list(getattr(self.mind, "goals", [])):
            if g.get("done"):
                continue
            # 两种算完成：聊到了，或者那个缺口被填上了
            common = len(set(g["text"]) & set(user_text + final_reply))
            filled = self.mind.desires.get(g.get("from", ""), 0) > 30
            if common >= 3 or filled:
                self.mind.done_goal(g["text"])

        triggered = False
        raw_count = self.pcm.raw.count()
        if raw_count - self._last_handoff_raw >= self.handoff_interval * 2:
            self.pcm.make_handoff()
            self.pcm.save()
            self._last_handoff_raw = raw_count
            triggered = True

        return final_reply, triggered

    def boot(self, scene_hint: str = "") -> str:
        hits = self.pcm.recall(scene_hint, k=6) if scene_hint else None
        return self.pcm.boot(scene_hint, hits=hits)

    def idle(self, now: float | None = None):
        now = now or time.time()
        imp = self.mind.idle(now=now)
        if imp:
            self.pcm.ingest([{"speaker": self.mind.name, "content": f"（闲着，{imp}）", "ts": now}])
        return imp

    def _after_action(self, piece: str):
        """动作真发出去之后，手艺才涨。"""
        self.mind._did_action = True
        try:
            self.mind.learn(piece)
        finally:
            self.mind._did_action = False

    def _sync_budget(self, now):
        """把 API 余额接进饥饿。这不是比喻：聊得越多，它越饿。"""
        path = os.path.join(self.pcm.data_dir, "budget.json")
        if not os.path.exists(path):
            return
        try:
            bal = float(json.load(open(path, encoding="utf-8"))["balance"])
        except Exception:
            return
        floor = 0.0
        if bal < 5:    floor = 95.0      # 见底：要死了
        elif bal < 10: floor = 70.0      # 快饿死了
        elif bal < 30: floor = 40.0      # 紧
        if floor > self.mind.hunger:
            self.mind.hunger = floor

    def save(self):
        self.pcm.save()

def build_bridge(profile: SelfProfile | None = None, mind_state="./emotion_v6_state.json", pcm_dir="./pcm_data"):
    if os.path.exists(mind_state):
        mind = Mind()
        mind.state_path = mind_state
        mind.load()
    else:
        mind = Mind()
        mind.state_path = mind_state
        mind.last_t = time.time()

    if os.path.exists(os.path.join(pcm_dir, "self.json")):
        pcm = PersonaMemory.load(pcm_dir)
    else:
        if profile is None: raise ValueError("首次运行需要提供 SelfProfile")
        pcm = PersonaMemory(profile, pcm_dir)
        pcm.save()

    mind.name = pcm.profile.name
    return Bridge(mind, pcm)

def demo():
    import shutil
    random.seed(20261030)
    root = "./pcm_bridge_demo"
    if os.path.exists(root): shutil.rmtree(root)
    os.makedirs(root, exist_ok=True)
    
    bridge = build_bridge(DEMO_PROFILE, os.path.join(root, "emotion_state.json"), os.path.join(root, "pcm"))
    bridge.mind.person = "Bob"
    bridge.mind.who.setdefault("Bob", 1.3)
    bridge.mind.favor = 60
    bridge.mind.emotions["爱意"] = 55

    dialog = [
        ("Bob", "你怎么这么笨，这都办不好。"),
        ("Bob", "我心疼你。"),     # 测试不误判示弱
        ("Bob", "我真的撑不住了。"), # 测试新危机词
        ("Bob", "算了吧，我没事。"),
    ]

    print("=" * 60)
    print("演示：测试新危机拦截与心疼误判")
    print("=" * 60)

    for who, text in dialog:
        reply, _ = bridge.turn(text, who=who)
        print(f"\n{who} : {text}")
        print(f"她: {reply}")

if __name__ == "__main__":
    demo()