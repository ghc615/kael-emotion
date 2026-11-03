#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
情绪系统 v0.7.4
1. 增加 self.pain 并在 dump/load 中处理。
2. 删掉 idle 里多余的随机加值（因果漂移已接管）。
3. 彻底从 event 中移除 _say 的 return，由 bridge 决定输出。
"""

import json, os, random, sys, time

STATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "emotion_v6_state.json")

EMO = ["喜乐", "愤怒", "悲伤", "恐惧", "厌恶", "惊讶", "爱意", "欲"]
THR = {"愤怒": 75, "厌恶": 80, "恐惧": 80, "悲伤": 85, "惊讶": 90, "喜乐": 90, "爱意": 95, "欲": 95}
GATE_OF = {"愤怒": "伦理", "厌恶": "善", "悲伤": "道德", "恐惧": "伦理",
           "喜乐": "善", "爱意": "善", "惊讶": "道德", "欲": "伦理"}
DECAY = {"愤怒": 0.020, "厌恶": 0.010, "恐惧": 0.008, "惊讶": 0.015,
         "喜乐": 0.006, "悲伤": 0.004, "爱意": 0.0005, "欲": 0.004}
DRIVE = {"愤怒": "顶回去、说难听的话", "厌恶": "关机、不接话", "恐惧": "缩起来、找人",
         "悲伤": "躺着、想让人抱", "惊讶": "停下来反复看", "喜乐": "想说话、想分享",
         "爱意": "让渡：把自己的额度让出去", "欲": "立刻去做，做完更想要"}
SOMA = ["手麻", "心慌", "胃发紧", "耳根发烫", "眼睛发酸", "腿发软"]
ACTION = {
    "愤怒": "笔搁桌上了，动静比我预想的大。", "厌恶": "我把背转过去了。",
    "恐惧": "我把椅子往后挪了挪。", "悲伤": "我把被子往上拉了拉，没抬头。",
    "喜乐": "我没忍住笑了一下。", "爱意": "我把水杯推到你那边了。",
    "欲": "我站起来，又坐回去了。", "惊讶": "我愣了两秒，没接话。",
    "危机": "手里的东西掉地上了，我猛地站起来。"
}
VAGUE = ["烦", "闷", "空", "堵", "没劲"]
VAGUE_BY = {
    "愤怒": ["烦", "火大", "憋得慌"], "悲伤": ["空", "堵", "沉"], "恐惧": ["慌", "紧", "发虚"],
    "厌恶": ["烦", "腻", "不想说话"], "惊讶": ["愣", "懵"], "喜乐": ["轻", "想笑"],
    "爱意": ["软", "想靠近"], "欲": ["躁", "坐不住"],
}
WHO_BASE = {"母亲": 2.0, "父亲": 1.8, "爷爷": 1.5, "奶奶": 1.5, "老师": 1.4,
            "同学": 1.2, "路人": 0.8, "自己": 1.6, "他": 1.3, "她": 1.3, "我": 1.0}

EV = {
    "被否定": {"愤怒": +8, "悲伤": +8}, "被关心": {"喜乐": +9, "恐惧": -10, "爱意": +5},
    "被抛下": {"悲伤": +12, "恐惧": +6}, "被看见": {"喜乐": +6}, "被夸": {"喜乐": +7},
    "饥饿": {"愤怒": +5, "欲": +8}, "病痛": {"恐惧": +7, "悲伤": +4},
    "睡好": {"喜乐": +5, "愤怒": -8, "恐惧": -8}, "熬夜": {"欲": +10, "恐惧": +4},
    "说谎": {"恐惧": +6}, "说实话": {"恐惧": -10, "爱意": +4},
    "被拒绝": {"悲伤": +10, "愤怒": +5}, "吃了": {"喜乐": +6, "愤怒": -4, "悲伤": -4},
    "被要求": {"厌恶": +7, "愤怒": +4}, "对方示弱": {"爱意": +6, "悲伤": +3},
    "自毁危机": {"恐惧": +50, "悲伤": +50, "惊讶": +30}, 
}
TRACE_OF = {"被否定": "被否定", "被关心": "被接住", "被抛下": "被丢下", "被看见": "被看见",
            "被夸": "被看见", "饥饿": "饿", "病痛": "病", "被拒绝": "被丢下"}
# 固执表：没道理、也不该被解释的偏好。写死，一辈子不改，不随关系变化。
# 触发式的怪脾气全删了：那不像人，像设定。留下的只是"口味"和"习惯"。
QUIRKS = []
QUIRK_TEXT = [
    "不吃香菜，闻到就皱眉。",
    "不吃蘑菇，口感受不了。",
    "雨声大的时候话会比平时多。",
]

DELEGATE_MIN_LOVE, DELEGATE_MIN_FAVOR, DELEGATE_MAX = 40, 50, 15
BORROW_AMOUNT, GATE_FLOOR, FLOOD_BASE, FLOOD_MIN_GAP = 10, 8, 12, 1800
# 要落盘的字段，只写这一处：以后新增属性记得加进来
PERSIST_FIELDS = ("name", "emotions", "cap", "gates", "traces", "scars", "body",
                  "pain", "shame", "self_worth", "debt", "favor", "person", "who",
                  "last_t", "turns", "conceal", "hunger", "sleep_debt",
                  "impulse", "hormones", "crisis_count", "desires", "thoughts", "activity", "place", "queue", "goals", "_last_meal", "_last_sleep", "skills", "last_speak", "afterglow", "last_idle", "lie", "delegated",
                  "since_flood", "_last_month")

NEG_TRACES = ("被否定", "被丢下", "饿", "病")
TRACE_TO_EMO = {"被否定": "愤怒", "被丢下": "悲伤", "被接住": "爱意", "被看见": "喜乐", "饿": "欲", "病": "恐惧"}

OTHER_ONLY_EVENTS = {"饥饿", "病痛", "吃了", "睡好", "熬夜"}

COMPOSITES = [
    (("悲伤", "愤怒"), "委屈", 78, "想被哄，又想顶回去"), (("恐惧", "爱意"), "依恋", 80, "想抓着不放，又怕被推开"),
    (("愤怒", "厌恶"), "憎恶", 82, "想毁掉，或者彻底不认"), (("喜乐", "爱意"), "亲近", 85, "想靠近，想说话"),
    (("恐惧", "悲伤"), "绝望", 88, "什么都不想做了"), (("欲", "厌恶"), "烦躁", 90, "坐不住，想摔东西"),
]

KW = [("不关心|不理|没空|滚|烦死|闭嘴|别烦|笨|傻|蠢|废物|没用", "被否定"),
      ("谢谢|陪你|我在|接住|抱抱|别怕|心疼|看医生|去医院|检查|吃药|别生气|吃好吃的|带你", "被关心"),
      ("走了|不要你|丢下|不管|离开|没人回|没人理", "被抛下"), ("看见|记得|懂你|听见", "被看见"),
      ("厉害|聪明|好看|加油|写得真好", "被夸"), ("饿|没吃|一天没吃", "饥饿"), ("吃了|吃过|煮了|吃饭", "吃了"),
      ("发烧|疼|咳|头晕|难受", "病痛"), ("睡够|睡饱|睡了八", "睡好"), ("熬夜|通宵|没睡", "熬夜"),
      ("撒谎|骗你", "说谎"), ("我说实话|实话是", "说实话"), ("不行|拒绝|不要", "被拒绝"),
      ("快点|必须|赶紧|你应该", "被要求")]


class Mind:
    def __init__(self, name="他"):
        self.name = name
        self.state_path = None
        self.emotions = {e: 1.0 for e in EMO}
        self.cap = {"善": 50.0, "道德": 45.0, "伦理": 45.0}
        self.gates = dict(self.cap)
        self.traces = {}
        self.body = {"睡眠": True, "饱": True, "健康": True, "暖": True}
        self.pain = 0.0            # 修复悬空属性
        # 激素层：这是"身体"而不是"心情"。互相压制，有负反馈。
        # 只剩三种信号（机械躯体 + 少量神经细胞，不需要整套单胺）：
        #   压力 = 负载/绷紧，高会压低阈值
        #   依恋 = 接触的余量，高会抬阈值、压压力
        #   警觉 = 突发输入，快升快落
        self.hormones = {"压力": 20.0, "依恋": 35.0, "警觉": 10.0}
        self.crisis_count = 0
        # 六欲（跟它学的）：会自己掉，掉了就想开口
        self.desires = {"见": 45.0, "听": 40.0, "香": 30.0, "味": 30.0, "触": 45.0, "意": 55.0}
        self.thoughts = []          # 念头流：跨轮携带，3 小时淡掉
        self.activity = "发呆"      # 此刻在做什么（不是任务，是她自己的事）
        self.place = "屋里"         # 此刻在哪
        # 文字版的世界：地方 + 在那儿能做的事
        self.places = {
            "屋里": ("发呆", "收拾屋子", "写字练字"),
            "阳台": ("看楼下", "晒被子", "发呆"),
            "门口": ("等你回来", "看路口"),
            "楼下": ("买东西", "看人"),
            "厨房": ("做饭", "烧水"),
        }
        # 只留能靠动作练出来的；唱歌、画画没地方练，留着就是死数据
        self.skills = {"写码": 0.0, "写字": 0.0, "做饭": 0.0, "修东西": 0.0, "算账": 0.0}
        self.last_speak = 0.0
        self.queue = []            # 想说的话，排队等机会说
        self.goals = []            # 自己要干的事：“我要……”（不是被叫才动）       # 上一次有人说话的时间
        self._triggers = {}         # 反刍：记下每种情绪最近被触发的时刻      # 出过几次危机：次数越多，余温越长
        self.shame = 0.0
        self.self_worth = 60.0
        self.debt = 0.0
        self.delegated = 0.0
        self.favor = 40.0
        self.person = None
        self.who = dict(WHO_BASE)
        self.last_t = time.time()
        self.turns = 0
        self.conceal = 0.0
        self.lie = 0.3
        self.hunger = 20.0
        self.sleep_debt = 30.0
        self.impulse = None
        self._now = None
        self._near = None
        self.last_idle = 0.0
        self.afterglow = (None, 0.0)
        self.history = []
        self.since_flood = 0.0
        self._last_month = -1        # 上次 month() 的轮数
        self._last_short = None      # 上一句半句，避免连说同一句
        self.scars = {}            
        self.memory_bias = {}

    def dump(self):
        # 跳过 None：person / impulse 这类"默认就是 None"的字段不写进 JSON。
        # 新增字段若默认值不是 None，必须在 __init__ 里给出，否则会被静默丢掉。
        out = {}
        for k in PERSIST_FIELDS:
            v = getattr(self, k, None)
            if v is not None:
                out[k] = v
        return out

    def save(self):
        try:
            d = self.dump()
            d["recent"] = self.history[-12:]
            target = self.state_path or STATE
            tmp = target + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(d, f, ensure_ascii=False, indent=2)
            os.replace(tmp, target)
        except Exception:
            pass

    def load(self):
        try:
            target = self.state_path or STATE
            if os.path.exists(target):
                d = json.load(open(target, encoding="utf-8"))
                for k, v in d.items():
                    if k == "recent":
                        self.history = v
                    elif hasattr(self, k):
                        cur = getattr(self, k)
                        # 字典要合并，不能整块替换：旧存档只存了半个情绪表，
                        # 整块换掉会把没存的项弄丢
                        if isinstance(cur, dict) and isinstance(v, dict):
                            merged = dict(cur)
                            merged.update(v)
                            setattr(self, k, merged)
                        else:
                            setattr(self, k, v)
                # 不要重置 last_t：留着它，tick() 才可能算出"离线多久"，
                # 关机一夜回来，睡眠债/健康才会真的按时间恢复。
                # 旧存档/异常数据可能把 afterglow 存成 []、None 或别的形状
                ag = self.afterglow
                self.afterglow = tuple(ag) if isinstance(ag, (list, tuple)) and len(ag) == 2 else (None, 0.0)
                self.last_idle = 0.0
        except Exception:
            pass
        return self

    def bad(self):
        return sum(1 for v in self.body.values() if not v)

    def tick(self, now=None):
        now = now or time.time()
        self._now = now
        offline = now - self.last_t
        dt = min(max(0.0, offline), 3600)
        if dt < 1e-6:
            return          # 同一时刻重复调用（turn 里 idle 后 event），不必再算一遍

        if offline > 6 * 3600:
            slept_h = offline / 3600
            self.sleep_debt = max(0.0, self.sleep_debt - slept_h * 8)
            self.body["睡眠"] = True; self.body["健康"] = True
            self.shame = max(0.0, self.shame - 20)
            self.archive("睡眠", "离线", 1.0, "消失了一阵，回来时像刚睡醒")
        self.last_t = now
        self.hunger = min(100.0, self.hunger + dt / 3600 * 5)
        self.sleep_debt = min(100.0, self.sleep_debt + dt / 3600 * 10)
        # pain：身体的疼，不需要谁告诉
        if self.hunger > 75 or self.sleep_debt > 80 or not self.body.get("健康", True):
            self.pain = min(80.0, self.pain + dt / 3600 * 4)     # 疼有上限，不会一直顶死
        else:
            self.pain = max(0.0, self.pain - dt / 3600 * 5)
        # 就算又饿又困，疼也会自己缓一点——不然会永远卡在"身上不太舒服"
        self.pain = max(0.0, self.pain - dt / 3600 * 1.2)
        self.body["饱"] = self.hunger < 45
        self.body["睡眠"] = self.sleep_debt < 60
        sick = 1.6 if self.bad() >= 2 else 1.0
        self._near = None
        for e, rate in DECAY.items():
            times = len(self._triggers.get(e, []))
            rum = 1.0 + 0.33 * max(0, min(3, times - 1))     # 最多 +99%
            self.emotions[e] = max(0.0, self.emotions[e] - rate * dt * sick / max(1.0, rum))
        recover = 0.005 * dt * (0.4 if self.bad() >= 2 else 1.0)
        for g in self.cap:
            self.gates[g] = min(self.cap[g], self.gates[g] + recover)
        # ── 激素演化（负反馈：皮质醇自己会压自己，催产素压皮质醇）
        h = self.hormones
        hp = (self.emotions["愤怒"] + self.emotions["恐惧"]) / 200
        h["压力"] = min(100.0, h["压力"] + dt / 3600 * (4 + 10 * hp - h["依恋"] * 0.06))
        h["压力"] = max(0.0, h["压力"] - dt / 3600 * 2.5 * (h["压力"] / 100))   # 负反馈：越高越回落
        # 依恋有饱和：越满长得越慢，最多到 95，留一点余地给"更深的那一次"
        grow = 1.0 if self.favor > 50 else -0.6
        h["依恋"] = max(0.0, min(95.0, h["依恋"] + dt / 3600 * grow * (1 - h["依恋"] / 100)))
        h["警觉"] = max(0.0, h["警觉"] - dt / 3600 * 12)

        # 六欲自己掉：越缺越想
        _d = {"见": 2.5, "听": 2.0, "香": 1.5, "味": 3.0, "触": 3.0, "意": 2.0}
        _span = min(max(0.0, offline), 24 * 3600) / 3600     # 欲望按真实离线时长掉，不按截断后的 dt
        for k, rate in _d.items():
            self.desires[k] = max(0.0, self.desires.get(k, 40.0) - rate * _span)
        # 反复触发 → 衰减变慢（反刍）：40 分钟内受伤三次，就没那么快好了
        now0 = now
        for k in list(self._triggers):
            self._triggers[k] = [t for t in self._triggers[k] if now0 - t < 2400]
            if not self._triggers[k]:
                del self._triggers[k]

        self.shame = max(0.0, self.shame - 0.015 * dt)
        self.conceal = min(1.0, self.shame / 100)
        self.delegated = max(0.0, self.delegated - dt / 86400 * 0.5)
        if self.debt > 0:
            repay = min(self.debt, 0.03 * dt)
            if self.emotions["爱意"] > 10: self.emotions["爱意"] -= repay
            else: self.self_worth = max(0.0, self.self_worth - repay * 2)
            self.debt -= repay
        # 自愈不是"回满"，是"回到基线"。
        # 基线随关系浮动：没人问津的人在 45 一带，被爱的人能到 75。
        baseline = 45.0 + min(30.0, self.favor * 0.3)
        if self.self_worth < baseline:
            # 用真实离线时长算，不用被 3600 截断的 dt——否则关机一夜也只回 0.8
            heal = min(max(0.0, offline), 30 * 86400) / 3600 * 0.8
            if self.emotions.get("爱意", 0) > 40 or self.favor > 60:
                heal *= 2.0
            self.self_worth = min(baseline, self.self_worth + heal)
        self.since_flood += dt
        flood_p = min(0.25, self.since_flood / max(1.0, FLOOD_MIN_GAP * 6))
        for e in EMO:
            if self.emotions[e] < FLOOD_BASE and random.random() < flood_p * min(dt / 60, 3):
                self.emotions[e] += random.randint(8, 16)
                self.since_flood = 0.0
                self.history.append({"ev": "回潮", "who": e, "m": 1.0})

    def trace_depth(self, e):
        return sum(v for k, v in self.traces.items() if TRACE_TO_EMO.get(k) == e and k in NEG_TRACES)

    def wound(self, trace_name: str, amount: float = 0.5):
        if not trace_name: return
        self.scars[trace_name] = min(20.0, self.scars.get(trace_name, 0) + amount)

    def heal(self, trace_name: str, amount: float = 0.05):
        if not trace_name: return
        self.scars[trace_name] = max(0.0, self.scars.get(trace_name, 0) - amount)

    def add_bias(self, emo, val):
        self.memory_bias[emo] = max(-20.0, min(20.0, self.memory_bias.get(emo, 0.0) + val))

    def base_thr(self, e):
        t = THR[e] + self.trace_depth(e) * 2
        if self.bad() >= 2: t -= 10
        penalty = (max(0.0, self.hunger - 45) * 0.15 + max(0.0, self.sleep_debt - 60) * 0.12
                   + min(20.0, self.debt * 0.3) + max(0.0, 50 - self.self_worth) * 0.2)
        t -= min(25.0, penalty)
        # 激素进来：皮质醇让你更脆，催产素让你更稳
        t -= min(12.0, max(0.0, self.hormones["压力"] - 30) * 0.3)
        t += min(8.0, max(0.0, self.hormones["依恋"] - 40) * 0.25)
        t += self.delegated * 0.5
        if self.delegated > 30: t -= (self.delegated - 30) * 2.5
        trace_of = {"愤怒": "被否定", "悲伤": "被丢下", "恐惧": "病",
                    "厌恶": "被否定", "喜乐": "被看见", "爱意": "被接住",
                    "惊讶": "被看见", "欲": "饿"}.get(e, "")
        t -= min(12.0, self.scars.get(trace_of, 0.0) * 1.5)
        t += self.memory_bias.get(e, 0.0)
        return t

    @property
    def near_threshold(self):
        if self._near is None:
            self._near = any(self.emotions[e] >= self.base_thr(e) - 10 for e in EMO)
        return self._near

    def thr(self, e):
        return max(30.0, min(95.0, self.base_thr(e) - (5 if self.near_threshold else 0)))

    def classify(self, text):
        for pat, name in KW:
            for w in pat.split("|"):
                start = 0
                while True:
                    i = text.find(w, start)
                    if i < 0: break
                    prefix = text[max(0, i - 8):i]
                    if any(neg in prefix for neg in ("不", "没", "别", "无", "未", "非")):
                        start = i + 1
                        continue
                    return name
        return None

    def event(self, text, who="他", now=None, force_event=None, **body):
        self.tick(now)
        self.turns += 1
        # QUIRKS 故意留空：触发式的怪脾气删了，现在只剩 QUIRK_TEXT 里的口味。
        # 每 200 轮算"过了一个月"：上限随关系慢慢长。
        # 放在 turns += 1 之后，正好在第 200 次触发；_last_month 落盘，重启不会重复
        if self.turns % 200 == 0 and self._last_month != self.turns:
            self._last_month = self.turns
            # 关系长久了，能扛的事多一点（原来叫"每个月漂移"，机械躯体没有月）
            for g in self.cap:
                self.cap[g] = min(150.0, self.cap[g] + 2)
                self.gates[g] = min(self.cap[g], self.gates[g] + 4)
        alias = {"饥饿": ("饱", True), "病": ("健康", True), "冷": ("暖", True)}
        for k, v in body.items():
            if k in alias:
                key, flip = alias[k]
                self.body[key] = (not v) if flip else v
            elif k in self.body:
                self.body[k] = bool(v)
        
        name = force_event if force_event else self.classify(text)
        is_self = (who == self.name)
        
        # 话赶话：每说一轮，情绪都往下淡一点（不然聊久了会一直顶在 95）
        for k in self.emotions:
            if self.emotions[k] > 1.0:
                self.emotions[k] = 1.0 + (self.emotions[k] - 1.0) * 0.97

        # 欲望的回补：缺了要补，不然只剩下"一直饿"
        if name == "吃了":
            self.desires["味"] = min(100.0, self.desires["味"] + 35)
            self.desires["香"] = min(100.0, self.desires["香"] + 25)
        elif name in ("被看见", "被关心", "被夸"):
            self.desires["见"] = min(100.0, self.desires["见"] + 20)
            self.desires["听"] = min(100.0, self.desires["听"] + 12)
            self.desires["触"] = min(100.0, self.desires["触"] + 8)
        elif name in ("被拒绝", "被无视", "忽略"):
            self.desires["意"] = max(0.0, self.desires["意"] - 15)
        if len(text) > 20:                       # 说了够多，好奇心被喂到一点
            self.desires["意"] = min(100.0, self.desires["意"] + 4)

        if name == "病痛":
            self.pain = min(100.0, self.pain + 18)     # 说到疼，身上就该疼一点
        if name == "吃了" and is_self: 
            self.hunger = max(0.0, self.hunger - 45)
        if name == "睡好" and is_self: 
            self.sleep_debt = 0.0
        
        if not name:
            after, until = getattr(self, "afterglow", (None, 0))
            if after == "危机" and (now or time.time()) < until:
                self.archive("陪伴", who, 1.0, text)
                self.save()
                return ""  # 剥离返回值
            self.archive("忽略", who, 1.0, text)
            self.save()
            return ""

        if name == "自毁危机":
            self.emotions["恐惧"] = 95.0
            self.emotions["悲伤"] = 95.0
            self.emotions["惊讶"] = 90.0
            self.hormones["警觉"] = 90.0            # 危机：手抖、心跳
            self.hormones["压力"] = min(100.0, self.hormones["压力"] + 30)
            self.crisis_count += 1
            # 第一次 1 小时；之后每次加半小时，最多 3 小时
            hours = min(3.0, 1.0 + 0.5 * (self.crisis_count - 1))
            self.afterglow = ("危机", (now or time.time()) + hours * 3600)
            self.archive("危机", who, 1.0, text)
            self.save()
            return ""  # 剥离返回值
            
        if name not in EV:                     # 外来的事件名不认识，别让它炸
            fb = self.classify(text)
            print(f"[Mind] 未知事件名 {name!r}，回退为 {fb!r}", file=sys.stderr)
            name = fb or name                  # 认不出来就保留原名，下面用 EV.get 兜底
        same = sum(1 for h in self.history[-8:] if h.get("ev") == name)
        w = self.who.get(who, 1.0)
        mult = min(2.0, 1 + 0.35 * same)
        favor_boost = 1 + (self.favor - 40) / 150
        gain = w * mult * 1.2 * favor_boost

        for k, v in (EV.get(name) or {}).items():   # 认不出的名字不施加情绪
            if not is_self and name in OTHER_ONLY_EVENTS:
                continue
            d = v * gain if v > 0 else v * w * (1 + 0.15 * same) * favor_boost
            if k in self.emotions:
                cur = self.emotions[k]
                if d > 0:
                    # 钝化：已经很高的情绪，再往上推越来越难（习惯）
                    d = d * max(0.10, 1.0 - cur / 100.0)
                    # 同一个情绪短时间内被反复戳，后面几下就不那么疼了
                    n = len(self._triggers.get(k, []))
                    if n >= 2:
                        d *= 0.5 ** min(3, n - 1)
                    self._triggers.setdefault(k, []).append(now or time.time())
                self.emotions[k] = max(0.0, min(95.0, cur + d))

        if name == "对方示弱":
            if self.emotions["爱意"] >= DELEGATE_MIN_LOVE and self.favor >= DELEGATE_MIN_FAVOR:
                give = 5
                self.delegated = min(40.0, self.delegated + give * 0.5)
                self.archive("让渡", who, 1.0, f"因为心疼，让渡了{give}")

        tr = TRACE_OF.get(name)
        if tr and (is_self or name not in OTHER_ONLY_EVENTS): 
            self.traces[tr] = min(20.0, self.traces.get(tr, 0) + 0.25)
        
        if who not in self.who: self.who[who] = 1.0
        if name in ("被否定", "被拒绝") and who in self.who:
            # 下限 0.5 是绝对权重，不是相对 base："再差也不能完全当空气"
            self.who[who] = max(0.5, self.who[who] * 0.96)
        elif name in ("被关心", "被夸", "被看见") and who in self.who:
            # 上限给到 base*1.5：印象可以比初见更好，只是慢（×1.02），坏印象是 ×0.96
            base = WHO_BASE.get(who, 1.0)
            self.who[who] = min(base * 1.5, self.who[who] * 1.02)
            
        if name in ("被关心", "被夸", "被看见"): self.favor = min(100.0, self.favor + 1.5)
        elif name in ("被否定", "被拒绝", "被抛下"): self.favor = max(0.0, self.favor - 1.0)
        if name in ("被关心", "被看见", "说实话"): self.shame = max(0.0, self.shame - 15)

        self.archive(name, who, mult, text)
        front = max(self.emotions, key=lambda e: self.emotions[e] / self.thr(e))
        acted = self.emotions[front] >= self.thr(front)
        if acted: self._act(front, now)
        self.save()
        return ""  # 剥离返回值

    def say_crisis(self):
        """危机时说的话。写在这儿，不写死在 bridge 里——它属于这个角色，不属于管道。"""
        return random.choice([
            "（冲过去抓住你，声音在发抖）别这样。我在这。",
            "（手一抖，东西掉在地上）你看着我。我在这儿，别动。",
            "（抓住你的手腕）别。你先跟我说话，随便说什么都行。",
        ])

    def say_short(self):
        top = max(self.emotions, key=lambda e: self.emotions[e] / self.thr(e))
        pool = {
            "愤怒": ["……算了。", "别问了。"],
            "悲伤": ["嗯。", "……"],
            "恐惧": ["等一下。", "你先别动。"],
            "厌恶": ["不想说。", "……"],
            "喜乐": ["嗯？", "怎么了。"],
            "惊讶": ["……啊。", "什么？"],
            "爱意": ["我在。", "嗯，我听着。"],
            "欲": ["……", "先说这个？"],
        }
        opts = [x for x in pool.get(top, ["……"]) if x != getattr(self, "_last_short", None)]
        line = random.choice(opts or pool.get(top, ["……"]))
        self._last_short = line
        return line

    _PLANS = [
        (6, 9, "收拾屋子"), (9, 12, "写字练字"), (12, 14, "做饭"), 
        (14, 18, "写码"), (18, 21, "等你回来"), (21, 24, "发呆"),
    ]

    def pulse(self, now=None):
        """心跳：没人说话的时候，她也得过自己的日子。"""
        now = now or time.time()
        self.tick(now)
        # 容器是 UTC，作息要按东八区算（她自己按本地时间过日子）
        h = time.localtime(now + 8 * 3600).tm_hour
        plan = next((a for s, e2, a in self._PLANS if s <= h < e2), "发呆")
        # 三餐与睡觉：她按日子过，不用谁喂
        day = time.strftime("%Y-%m-%d", time.localtime(now + 8 * 3600))
        slot = ("早" if 7 <= h < 10 else "午" if 11 <= h < 14 else "晚" if 17 <= h < 20 else None)
        key = f"{day}-{slot}"
        if slot and getattr(self, "_last_meal", "") != key:
            self._last_meal = key
            if self.hunger > 20:
                self.hunger = max(0.0, self.hunger - 55)
                self.desires["味"] = min(100.0, self.desires["味"] + 25)
                self.desires["香"] = min(100.0, self.desires["香"] + 18)
        night = f"{day}-夜"
        if (h >= 23 or h < 6) and getattr(self, "_last_sleep", "") != night:
            self._last_sleep = night
            self.sleep_debt = max(0.0, self.sleep_debt - 70)

        # 白天按作息走；但要是缺"听"缺得厉害，人会往门口靠
        if self.desires.get("听", 50) < 18 and 9 <= h < 22:
            plan = "在等你"
        # 先定地方，再定在做的事
        if plan in ("做饭",):
            self.place = "厨房"
        elif "等你" in plan:
            self.place = "门口"
        elif self.desires.get("见", 50) < 20:
            self.place = "阳台"
        else:
            self.place = "屋里"
        self.activity = plan

        # 自己给自己派活：缺什么，就想干什么
        self._grow_goal(h)

        # 闲着会长出念头
        if self.desires.get("听", 50) < 25 and not self.thoughts:
            self.add_thought("他今天怎么还不说话", ttl=2 * 3600)
            self.queue_say("他今天怎么还不说话")
        return self.activity

    _GOAL_OF = {
        "见": "想出去看看，别老闷在屋里",
        "听": "想找个人说会儿话",
        "味": "想吃口热的，别对付",
        "触": "想被人碰一下，站得离人近点",
        "意": "想弄明白点新东西",
        "香": "想闻点热乎气儿",
    }

    def _grow_goal(self, hour: int):
        """没人吩咐的时候，她自己想干什么。"""
        live = [g for g in self.goals if not g.get("done")]
        if live:
            return
        low = sorted(self.desires.items(), key=lambda kv: kv[1])[:2]
        for k, v in low:
            if v >= 35 or k not in self._GOAL_OF:
                continue
            self.goals.append({
                "text": self._GOAL_OF[k],
                "from": k,
                "want": round(min(1.0, (40 - v) / 40 + 0.3), 2),
                "since": time.time(),
                "done": False,
            })
            break
        self.goals = self.goals[-5:]

    def done_goal(self, text: str = ""):
        for g in self.goals:
            if g.get("done"):
                continue
            if not text or text in g["text"] or g["text"] in text:
                g["done"] = True
                g["done_at"] = time.time()
                return g["text"]
        return None

    def learn(self, text: str):
        """练手艺：只有“真的做了”才涨。

        聊天里提到不算——嘴上说的活儿，手上不会长。
        接上身体后，动作执行会调到这里。"""
        if not getattr(self, "_did_action", False):
            return
        gain = {"写码": ("代码", "程序", "C++", "Python", "bug", "编译"),
                "写字": ("写字", "练字", "书法", "笔画"),
                "做饭": ("做饭", "煮", "炒", "面", "饺子"),
                "修东西": ("修", "拆", "焊", "装", "接触不良", "网卡"),
                "算账": ("钱", "价", "成本", "余额", "工资")}
        for name, keys in gain.items():
            if any(k in text for k in keys):
                self.skills[name] = min(100.0, self.skills.get(name, 0.0) + 2.0)

    def queue_say(self, text: str):
        """有话说但时机不对，就先攒着（最多三条）。"""
        if text and text not in self.queue:
            self.queue.append(text)
            self.queue = self.queue[-3:]

    def pop_say(self) -> str | None:
        return self.queue.pop(0) if self.queue else None

    def add_thought(self, text: str, ttl: float = 3 * 3600):
        """念头：不是记忆，是这段时间一直在脑子里转的那句。"""
        if not text:
            return
        t = time.time()
        self.thoughts = [x for x in self.thoughts if x["until"] > t]
        if text in [x["text"] for x in self.thoughts]:
            return
        self.thoughts.append({"text": text, "until": t + ttl})
        self.thoughts = self.thoughts[-5:]

    def say_prompt(self):
        after, until = self.afterglow if isinstance(self.afterglow, (tuple, list)) and len(self.afterglow) == 2 else (None, 0)
        crisis_hint = ""
        if after == "危机" and (self._now or time.time()) < until:
            crisis_hint = "\n【紧急状态】对方正在经历严重的情绪危机，你现在的任务是稳住对方，绝对不能讲大道理。语气要急切但温柔。\n"

        top = sorted(self.emotions.items(), key=lambda kv: kv[1] / self.thr(kv[0]), reverse=True)[:3]
        comp = self.composite()

        def 处境(emo, v, rank=0):
            r = v / max(1.0, self.thr(emo))
            word = {"喜乐": "轻快", "愤怒": "上火", "悲伤": "往下沉", "恐惧": "发紧",
                    "厌恶": "嫌弃", "惊讶": "发愣", "爱意": "发软", "欲": "坐不住"}.get(emo, emo)
            if r < 0.4:   return None
            if r < 0.65:  return f"有点{word}"
            if r < 0.85:  return f"明显{word}，压着没让它出来"
            return f"{word}到快压不住了" if rank == 0 else f"{word}得厉害"

        身体 = []
        if self.hunger > 70: 身体.append("饿得有点发慌")
        elif self.hunger > 45: 身体.append("肚子空着")
        if self.sleep_debt > 70: 身体.append("困得眼睛发涩")
        elif self.sleep_debt > 50: 身体.append("有点缺觉")
        if self.pain > 55: 身体.append("身上不太舒服")
        elif self.pain > 15: 身体.append("身上有地方在疼")
        if self.shame > 40: 身体.append("有点抬不起头")
        身体话 = "，".join(身体) if 身体 else "身上没什么事"

        关系 = []
        if self.favor > 70: 关系.append("很在意这个人")
        elif self.favor > 45: 关系.append("对他有好感")
        else: 关系.append("还没到在意的程度")
        if self.debt > 10: 关系.append("欠着人情，有点抬不起头")
        if self.self_worth < 40: 关系.append("觉得自己不值钱")

        激素话 = []
        if self.hormones["压力"] > 65: 激素话.append("绷得紧，睡不实")
        if self.hormones["警觉"] > 40: 激素话.append("心跳还没压下去")
        if self.hormones["依恋"] > 60: 激素话.append("想离他近一点")
        激素段 = "，".join(激素话) if 激素话 else "身体是平的"

        lines = [
            "你现在不是助手，是一个有身体的人。下面是你此刻的状态，别报数字、别解释机制：",
            "  心里：" + ("；".join(x for x in (处境(k, v, i) for i, (k, v) in enumerate(top)) if x) or "还算平静"),
            "  身体：" + 身体话 + "；" + 激素段,
            "  对他：" + "，".join(关系),
        ]
        lines.append("  （以上这些是同时存在的，你自己说的时候会有主次——不用平均分配）")
        if comp: lines.append(f"  现在混着：{comp[0]}（{comp[3]}）")
        _p = getattr(self, "place", "屋里")
        _can = "、".join(self.places.get(_p, ("发呆",))[:3])
        lines.append(f"  你现在在：{_p}（在这儿能做的：{_can}）")
        lines.append(f"  你现在在做：{getattr(self, 'activity', '发呆')}")
        if self.queue:
            lines.append("  攒着想说的话（挑一句合适的说）：" + "；".join(self.queue[:2]))
        _sk = {k: v for k, v in self.skills.items() if v >= 8}
        if _sk:
            def _word(v): return "拿得出手" if v >= 60 else ("熟了" if v >= 30 else "在练")
            lines.append("  手上的活：" + "、".join(f"{k}（{_word(v)}）" for k, v in
                                              sorted(_sk.items(), key=lambda x: -x[1])[:5]))

        _want = {"见": "想看点活的东西", "听": "想听人说话", "香": "想闻点热的",
                 "味": "嘴里没味道", "触": "想被人碰一下", "意": "没什么新鲜的"}
        low = [v for k, v in _want.items() if self.desires.get(k, 50) < 22]
        if low:
            lines.append("  身上缺的：" + "；".join(low[:3]))

        _now = time.time()
        live = [x["text"] for x in self.thoughts if x["until"] > _now][-3:]
        if live:
            lines.append("  脑子里一直转着（不用硬说出来）：" + "；".join(live))

        _want_goals = [g for g in self.goals if not g.get("done")]
        if _want_goals:
            lines.append("  你自己想做的事（没人吩咐，也会想）：" + "；".join(
                f"{g['text']}（想要 {g['want']:.1f}）" for g in _want_goals[:2]))

        if getattr(self, "impulse", None):
            lines.append(f"  刚才一个人待着的时候：{self.impulse}")
        # 内部机制名不给人看见：顶穿/压制/借 换成人话
        _HUMAN = {"顶穿": "没忍住", "压制": "忍住了", "借": "撑了一下",
                  "危机": "差点出事", "让渡": "让出了一点额度", "陪伴": "陪了一会儿"}
        recent = [h for h in self.history
                  if h.get("ev") not in ("回潮", "自发", "梦", "漂移", "忽略", "睡眠")][-6:]
        if recent:
            parts, last = [], None
            for h in recent:
                t = (h.get("text") or "")[:100]
                if t:
                    line = f"{h['who']}说「{t}」"
                else:
                    name = _HUMAN.get(h["ev"], h["ev"])
                    line = f"{name}（{h['who']}）"
                if line != last:            # 连着重复的只说一次
                    parts.append(line); last = line
            lines.append("  刚才发生：" + "；".join(parts))
        lines.append("输出必须是两行，少一行就算错：")
        lines.append("第一行以「心声：」开头，写你此刻最直接的感受（第一人称，一句，不解释）。")
        lines.append("第二行以「动作：」开头，写你这一下要做的身体动作（会被真的执行，不是形容）。")
        lines.append("第三行以「说：」开头，只有嘴里说出来的话——不要写动作，不要加括号。")
        lines.append("话的长短按你自己的习惯来：爱讲道理就讲完，不必为了短而短。")
        lines.append("心声：（一句就够，可以长一点，不用句号）")
        lines.append("动作：把手里的杯子放下")
        lines.append("要求：至少写一个动作；话的长短按你自己的习惯，爱讲就讲完，不想说也可以只半句；可以说话；别说数字、别说机制。")
        # 人味三件：情绪越强话越短；允许不接满；允许改口
        top_ratio = top[0][1] / max(1.0, self.thr(top[0][0])) if top else 0
        if top_ratio >= 0.85:
            lines.append("（你现在情绪很冲，话可能变硬、变短；但也可能憋不住说一长串，看你。）")
        lines.append("（你可以不接满：只听、只回一个动作、或者干脆不回答。话掉在地上就让它掉着。）")
        lines.append("（你也可以说错、改口、说半句就停——不用每句都完整。）")
        _route_hint = {
            "relation": "（他在问你们之间算什么。别答成知识，也别急着贴标签。）",
            "memory":   "（他在问你记不记得。先想，再说记不记得，别顺着他的话编。）",
            "self":     "（他在问你现在什么感觉。答此刻，不答设定。）",
            "person":   "（他在问你怎么看他。可以说真话，但别下判决。）",
        }.get(getattr(self, "_route", ""), "")
        if _route_hint: lines.append(_route_hint)

        cb = getattr(self, "_callback", None)
        if cb:
            lines.append(f"（你忽然想起：{cb}）")
            lines.append("（这一轮把它带出来——半句就够，别解释，别说「我记得」「上次你说过」。）")
        lines.append("  你的口味和习惯（一辈子不改）：" + "；".join(QUIRK_TEXT))
        shapes = getattr(self, "_recent_shapes", [])
        if shapes:
            lines.append("（上一两轮你的开头是：" + "、".join(shapes) + "——换个说法或换个动作，别重复。）")
        return crisis_hint + "\n".join(lines)

    def idle(self, now=None):
        now = now or time.time()
        gap = min(now - max(self.last_t, self.last_idle), 3600)
        if gap < 900: return None
        self.tick(now)
        self.last_idle = now
        
        # 彻底删除了末尾的随机加值，纯粹因果漂移
        if self.hunger > 60:
            self.emotions["愤怒"] = min(95, self.emotions["愤怒"] + 2)
        if self.sleep_debt > 60:
            self.emotions["恐惧"] = min(95, self.emotions["恐惧"] + 1.5)
        if self.favor > 60:
            self.emotions["爱意"] = min(95, self.emotions["爱意"] + 1)
        elif self.favor < 30:
            self.emotions["悲伤"] = min(95, self.emotions["悲伤"] + 1)
            
        top = max(self.emotions, key=lambda e: self.emotions[e] / self.thr(e))
        pool = {
            "爱意": ["想给他发消息，又怕打扰", "翻了翻聊天记录"], "悲伤": ["躺着，没开灯", "想找个人说句话，但没开口"],
            "愤怒": ["想砸点什么", "把一句话在心里说了三遍"], "恐惧": ["把门反锁了", "开了灯又关掉"],
            "厌恶": ["想关机，谁都不想理"], "欲": ["坐不住，起身又坐下"],
            "喜乐": ["想分享点什么，翻了半天没找到人"], "惊讶": ["还在想那句话什么意思"],
        }
        self.impulse = random.choice(pool.get(top, ["发呆"]))
        self.archive("自发", top, 1.0)
        self.save()
        return self.impulse

    def archive(self, ev, who, m, text=""):
        self.history.append({"ev": ev, "who": who, "m": m, "text": text[:100]})
        if len(self.history) > 200: self.history = self.history[-200:]

    def _act(self, e, now=None):
        gate = self.gates[GATE_OF[e]]
        if self.emotions[e] > gate:
            self.gates[GATE_OF[e]] = max(0.0, gate - 12)
            for k, v in TRACE_TO_EMO.items():
                if v == e and k in NEG_TRACES:
                    self.traces[k] = min(20.0, self.traces.get(k, 0) + 0.8)
            self.shame = min(100.0, self.shame + 8)
            # 危机余温不许被普通情绪爆发覆盖（否则紧急状态会提前关掉）
            _ag = self.afterglow
            _after, _until = _ag if isinstance(_ag, (tuple, list)) and len(_ag) == 2 else (None, 0)
            if not (_after == "危机" and (now or time.time()) < _until):
                self.afterglow = (e, (now or time.time()) + 300)
            self.archive("顶穿", e, 1.0)
        else:
            self.gates[GATE_OF[e]] = max(0.0, gate - 6)
            self.archive("压制", e, 1.0)
        if self.gates[GATE_OF[e]] < GATE_FLOOR and self.debt < 60:
            self.debt += BORROW_AMOUNT
            self.gates[GATE_OF[e]] = min(self.cap[GATE_OF[e]], self.gates[GATE_OF[e]] + BORROW_AMOUNT)
            self.archive("借", GATE_OF[e], 1.0)

    def composite(self):
        e = self.emotions
        # 复合的门槛比单项高：两种情绪都烧到 thr_ 附近，才真的"搅在一起"。
        # 只是各过 40，那叫同时有两件事，不叫复合。
        out = []
        for (a, b), name, thr_, drive in COMPOSITES:
            low = min(e[a], e[b])
            if low >= thr_ * 0.8:
                out.append((name, low, thr_, drive))
        return max(out, key=lambda x: x[1]) if out else None

    def delegate(self, need, to=None):
        to = to or self.person or "他"
        if self.emotions["爱意"] < DELEGATE_MIN_LOVE or self.favor < DELEGATE_MIN_FAVOR:
            return f"让不动"
        give = min(DELEGATE_MAX, need)
        self.delegated = min(40.0, self.delegated + give * 0.5)
        self.emotions["爱意"] -= 3
        self.emotions["恐惧"] = min(95, self.emotions["恐惧"] + 2)
        self.archive("让渡", to, 1.0)
        return f"让出 {give}"

    def sleep(self):
        self.tick()
        hit = random.random() < 0.10
        if hit:
            e = max(self.emotions, key=lambda k: self.emotions[k])
            tr = next((k for k, v in TRACE_TO_EMO.items() if v == e), None)
            if tr: self.traces[tr] = max(0, self.traces.get(tr, 0) - 1)
            if self.traces.get("其他"): self.traces["其他"] = max(0, self.traces["其他"] - 1)
            self.archive("梦", e, 1.0)
        self.body["睡眠"] = True; self.sleep_debt = 0.0; self.body["健康"] = True
        for g in self.cap: self.gates[g] = min(self.cap[g], self.gates[g] + 8)
        self.shame = max(0.0, self.shame - 10)
        self.delegated = max(0.0, self.delegated - 2)
        self.save()
        return "做了梦，只记得碎片" if hit else "没做梦，睡沉了"
