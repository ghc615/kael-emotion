#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pcm.py —— 记忆库（开源简化版）

完整版有：半衰期遗忘、间隔重复、新盖旧、证据链、危机记忆、语义标签、证据合并。
这一份只保留最小可跑的部分：存、取、交接、存档。

它和完整版接口一样，所以 pcm_bridge.py / kael_web.py 不用改。
想换成完整版，替换本文件即可。
"""
from __future__ import annotations

import json
import math
import os
import re
import time
import uuid
from dataclasses import asdict, dataclass, field

# ── 人设 ──────────────────────────────────────────────

@dataclass
class SelfProfile:
    name: str
    essence: str
    traits: list = field(default_factory=list)
    speech_style: str = ""
    values: list = field(default_factory=list)
    immutable_facts: list = field(default_factory=list)
    evolving_facts: list = field(default_factory=list)

    def anchor_text(self) -> str:
        lines = [f"你就是 {self.name}。{self.essence}"]
        if self.traits:
            lines.append("你的性格：" + "、".join(self.traits) + "。")
        if self.speech_style:
            lines.append("你说话的方式：" + self.speech_style)
        if self.values:
            lines.append("你在意：" + "、".join(self.values) + "。")
        for f in self.immutable_facts:
            lines.append("  · " + f)
        if self.evolving_facts:
            lines.append("这些经历把你塑造成了现在的样子：")
            for f in self.evolving_facts[-8:]:
                lines.append("  · " + f)
        return "\n".join(lines)


DEMO_PROFILE = SelfProfile(
    name="小明",
    essence="安静，认人，记性一般但不撒谎。",
    traits=["安静", "较真", "护短"],
    speech_style="短句，少形容词。",
    values=["说真话", "不丢下人"],
)

# ── 记忆 ──────────────────────────────────────────────

_STOP = set("你我他她它的了吗呢吧啊是在有和就都也还又很太把被给对说要想会能可这那个一不没")


def _bigrams(text: str) -> set:
    t = re.sub(r"[\s，。！？、,.!?；;：:“”\"'（）()\[\]【】…—·*~`]", "", text)
    return {t[i:i + 2] for i in range(len(t) - 1)} if len(t) > 1 else ({t} if t else set())


@dataclass
class AtomicMemory:
    content: str
    speaker: str
    kind: str = "event"
    importance: float = 0.5
    when: float = field(default_factory=time.time)
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:10])
    last_access: float = field(default_factory=time.time)
    access_count: int = 0
    tags: list = field(default_factory=list)
    evidence_count: int = 1

    def to_dict(self) -> dict:
        return asdict(self)


def crisis_level(text: str):
    """简化版：只认最直接的几句。完整版有否定、指代、弱信号分级。"""
    for w in ("不想活", "想死", "自杀", "轻生", "结束生命"):
        i = text.find(w)
        if i < 0:
            continue
        prefix = text[max(0, i - 6):i]
        if any(n in prefix for n in ("不", "没", "别", "无")):
            continue
        if any(p in prefix for p in ("你", "他", "她")):
            continue
        return "crisis"
    for w in ("撑不住", "熬不下去", "活着没意思"):
        if w in text:
            return "weak"
    return None


class _Raw:
    def __init__(self, path: str):
        self.path = path

    def append(self, turns) -> None:
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(turns, ensure_ascii=False) + "\n")

    def count(self) -> int:
        if not os.path.exists(self.path):
            return 0
        with open(self.path, encoding="utf-8") as f:
            return sum(1 for _ in f)


class PersonaMemory:
    def __init__(self, profile: SelfProfile, data_dir: str = "./pcm_data"):
        self.profile = profile
        self.data_dir = data_dir
        os.makedirs(data_dir, exist_ok=True)
        self.raw = _Raw(os.path.join(data_dir, "raw.jsonl"))
        self.atomic: dict = {}
        self.handoff_note = ""

    def _p(self, name: str) -> str:
        return os.path.join(self.data_dir, name)

    # 存
    def ingest(self, turns, loose: bool = False, intensity: float = 0.0) -> dict:
        self.raw.append(turns)
        added = 0
        for t in turns:
            text = (t.get("content") or "").strip()
            if not text:
                continue
            who = t.get("speaker") or "他"
            m = AtomicMemory(content=text[:400], speaker=who, kind="event",
                             importance=0.5, tags=sorted(_bigrams(text))[:8],
                             when=t.get("ts", time.time()))
            self.atomic[m.id] = m
            added += 1
        self.save()
        return {"added": added, "raw_total": self.raw.count(), "atomic_total": len(self.atomic)}

    # 取：最近 + 关键词重合，取前 k
    def recall(self, query: str, k: int = 6) -> list:
        q = _bigrams(query)
        scored = []
        for m in self.atomic.values():
            hit = len(q & set(m.tags))
            rec = 0.5 ** (max(0.0, time.time() - m.when) / 86400 / 30)
            score = 0.6 * hit / max(1, len(q) ** 0.5) + 0.4 * rec
            if score > 0:
                scored.append((m, score))
        scored.sort(key=lambda x: x[1], reverse=True)
        top = scored[:k]
        for m, _ in top:
            m.last_access = time.time()
            m.access_count += 1
        return top

    def make_handoff(self, max_items: int = 12) -> str:
        recent = sorted(self.atomic.values(), key=lambda m: m.when, reverse=True)[:max_items]
        self.handoff_note = "\n".join(f"· {m.content[:80]}" for m in recent)
        return self.handoff_note

    def boot(self, scene_hint: str = "", max_handoff_chars: int = 1200, k: int = 6, hits=None) -> str:
        parts = [self.profile.anchor_text()]
        if hits:
            parts.append("\n【你想起了以前的事】")
            for m, _ in hits:
                parts.append(f"- {m.content}")
        if self.handoff_note:
            parts.append("\n【最近】\n" + self.handoff_note[:max_handoff_chars])
        return "\n".join(parts)

    # 存档
    def save(self) -> None:
        tmp = self._p("atomic.json.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump([m.to_dict() for m in self.atomic.values()], f, ensure_ascii=False)
        os.replace(tmp, self._p("atomic.json"))
        with open(self._p("self.json"), "w", encoding="utf-8") as f:
            json.dump(asdict(self.profile), f, ensure_ascii=False, indent=2)
        if self.handoff_note:
            with open(self._p("handoff.txt"), "w", encoding="utf-8") as f:
                f.write(self.handoff_note)

    @classmethod
    def load(cls, data_dir: str = "./pcm_data") -> "PersonaMemory":
        with open(os.path.join(data_dir, "self.json"), encoding="utf-8") as f:
            raw = json.load(f)
        fields = {f.name for f in __import__("dataclasses").fields(SelfProfile)}
        profile = SelfProfile(**{k: v for k, v in raw.items() if k in fields})
        pm = cls(profile, data_dir)
        apath = os.path.join(data_dir, "atomic.json")
        if os.path.exists(apath):
            try:
                for d in json.load(open(apath, encoding="utf-8")):
                    flds = {f.name for f in __import__("dataclasses").fields(AtomicMemory)}
                    pm.atomic[d.get("id", uuid.uuid4().hex[:10])] = AtomicMemory(**{k: v for k, v in d.items() if k in flds})
            except Exception:
                pass
        hpath = os.path.join(data_dir, "handoff.txt")
        if os.path.exists(hpath):
            pm.handoff_note = open(hpath, encoding="utf-8").read()
        return pm
