#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
import_memories.py —— 把旧聊天记录灌进记忆库

用法：
    python3 import_memories.py 记录.txt --who 他 --name 小名 --data ./pcm_data --dry
    python3 import_memories.py 记录.txt --who 他 --name 小名 --data ./pcm_data

它做四件事：
1. 认格式（DeepSeek 分享页 / 纯文本 / "你：/我：" / "User:/Assistant:"）
2. 切成"一问一答"
3. 按顺序补时间（从最早到最晚，默认一天一条）
4. 交给 pcm.ingest 打标签、去重、入库

不加 --dry 就会真的写进去。写之前会先备份原来的 atomic.json。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import time

import pcm

# 行首的角色标记：尽量宽容
_ROLE = re.compile(
    r"^\s*(?:"
    r"(?P<user>用户|User|USER|Human|HUMAN|提问)\s*[:：]"
    r"|(?P<ai>助手|AI|Assistant|ASSISTANT|回答|DeepSeek|深度求索)\s*[:：]"
    r")",
)


def _norm(s: str) -> str:
    s = s.replace("\u200b", "").replace("\r\n", "\n").replace("\r", "\n")
    return re.sub(r"[ \t]+\n", "\n", s)


def parse(text: str) -> list[tuple[str, str]]:
    """返回 [(role, content)]，role 是 'user' / 'ai' / 'unknown'。"""
    text = _norm(text)
    # 有人用「我：/你：」记对话：出现「我：」时，「你：」就是对面
    has_wo = bool(re.search(r"^\s*我\s*[:：]", text, re.M))
    role = re.compile(
        r"^[*#>\s-]{0,4}(?:"
        r"(?P<user>用户|User|USER|Human|HUMAN|提问|我)[\*\s]*[:：]"
        r"|(?P<ai>助手|AI|Assistant|ASSISTANT|回答|DeepSeek|深度求索" + ("|你" if has_wo else "") + r")[\*\s]*[:：]"
        r")"
    )
    out: list[list] = []
    cur_role, buf = None, []

    def flush():
        nonlocal buf
        body = "\n".join(buf).strip()
        if body:
            out.append([cur_role or "unknown", body])
        buf = []

    for line in text.split("\n"):
        m = role.match(line)
        if m:
            flush()
            cur_role = "user" if m.group("user") else "ai"
            rest = line[m.end():].strip()
            if rest:
                buf.append(rest)
        else:
            buf.append(line)
    flush()
    return [(r, c) for r, c in out]


def pair(turns: list[tuple[str, str]]) -> list[dict]:
    """把一问一答拼成 ingest 要的样子。"""
    pairs, pending = [], None
    for role, content in turns:
        if role == "user":
            if pending:
                pairs.append({"user": pending, "ai": ""})
            pending = content
        elif role == "ai":
            pairs.append({"user": pending or "", "ai": content})
            pending = None
        else:
            # 没有角色标记的段落：当成"对方说的话"，别丢
            if pending:
                pending += "\n" + content
            else:
                pending = content
    if pending:
        pairs.append({"user": pending, "ai": ""})
    return pairs


def build_batches(pairs: list[dict], who: str, me: str, start: float, step: float) -> list[list[dict]]:
    batches = []
    t = start
    for p in pairs:
        turns = []
        if p["user"]:
            turns.append({"speaker": who, "content": p["user"], "ts": t})
            t += step / 2
        if p["ai"]:
            turns.append({"speaker": me, "content": p["ai"], "ts": t})
            t += step / 2
        if turns:
            batches.append(turns)
    return batches


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="把旧聊天记录导入记忆库")
    ap.add_argument("files", nargs="+", help="txt 或 md 文件（PDF 先转成 txt）")
    ap.add_argument("--who", default="他", help="对方叫什么（默认：他）")
    ap.add_argument("--name", default=None, help="AI 叫什么（默认：用 self.json 里的名字）")
    ap.add_argument("--data", default="./pcm_data", help="记忆库目录")
    ap.add_argument("--start", default="", help="最早时间，如 2026-10-01")
    ap.add_argument("--step", type=float, default=1800, help="每半轮间隔多少秒（默认 1800）")
    ap.add_argument("--max-lines", type=int, default=0, help="只导入前 N 行（调试用）")
    ap.add_argument("--dry", action="store_true", help="只看看，不写库")
    ap.add_argument("--profile", default=None,
                    help="人设 JSON（可选）：里面有 name/essence/traits/speech_style/values")
    ap.add_argument("--essence", default=None,
                    help="一句话人设，比如：一条鲸，安静，认人")
    ap.add_argument("--loose", action="store_true",
                    help="导入旧记录时用：少合并，尽量一句一条（推荐）")
    args = ap.parse_args(argv)

    exists = os.path.exists(os.path.join(args.data, "self.json"))
    store = pcm.PersonaMemory.load(args.data) if exists else pcm.PersonaMemory(pcm.DEMO_PROFILE, args.data)
    # 新库默认拿的是 DEMO_PROFILE（示例人设），导别人之前必须换掉，
    # 不然它开口会以为自己是边境佣兵
    if args.profile and os.path.exists(args.profile):
        raw = json.load(open(args.profile, encoding="utf-8-sig"))
        from pcm import SelfProfile, _filter_kwargs
        store.profile = SelfProfile(**_filter_kwargs(SelfProfile, raw))
    elif args.essence and not exists:
        store.profile.essence = args.essence
    me = args.name or store.profile.name
    who = args.who
    # 名字要对上：新库默认是示例名字，导谁就该换成谁的名字
    if args.name and store.profile.name != args.name:
        store.profile.name = args.name

    start = time.time() - 86400 * 30
    if args.start:
        try:
            start = time.mktime(time.strptime(args.start, "%Y-%m-%d"))
        except Exception:
            print(f"时间格式不对：{args.start}，用默认（30 天前）")

    total_pairs = 0
    for path in args.files:
        if not os.path.exists(path):
            print(f"跳过（不存在）：{path}")
            continue
        raw = open(path, encoding="utf-8-sig", errors="ignore").read()
        if args.max_lines:
            raw = "\n".join(raw.split("\n")[:args.max_lines])
        turns = parse(raw)
        pairs = pair(turns)
        if not pairs:
            print(f"没认出对话（{path}）：可能格式不一样，先给我看两行")
            continue
        batches = build_batches(pairs, who, me, start, args.step)
        if batches:
            # 下一份接着这份的时间往后排，不然几份记录会全挤在同一个时刻
            start = batches[-1][-1]["ts"] + args.step
        added = 0
        if args.dry:
            for b in batches[:3]:
                for t in b:
                    print(f"  [{t['speaker']}] {t['content'][:60]}")
            print(f"（试运行）这份能切出 {len(batches)} 段，例如上面这些。没有写库。")
        else:
            for b in batches:
                r = store.ingest(b, loose=args.loose)
                added += r.get("added", 0)
            print(f"{os.path.basename(path)}：{len(batches)} 段 → 新增 {added} 条记忆")
        total_pairs += len(batches)

    if not args.dry:
        if total_pairs:
            bak = os.path.join(args.data, "atomic.json.before-import")
            src = os.path.join(args.data, "atomic.json")
            if os.path.exists(src):
                shutil.copy2(src, bak)
            store.save()
            print(f"完成：共处理 {total_pairs} 段，当前记忆 {len(store.atomic)} 条。原库备份在 atomic.json.before-import")
        else:
            print("什么都没导入。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
