#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
archive.py —— 档案（开源简化版）

完整版有：按整条消息切块、倒排索引、罕见词加权、同分决胜、缓存。
这一份只做最朴素的事：按行读，两字重合打分，命中行带前后各一行。

接口和完整版一致（search(path, query, k, min_hit, context)），所以 pcm_bridge.py 不用改。
"""
from __future__ import annotations

import os
import re


def _grams(text: str) -> set:
    t = re.sub(r"[\s，。！？、,.!?；;：:“”\"'（）()\[\]【】…—·*~`]", "", text)
    return {t[i:i + 2] for i in range(len(t) - 1)} if len(t) > 1 else ({t} if t else set())


def search(path: str, query: str, k: int = 3, min_hit: int = 2, context: int = 0) -> list:
    """去档案里翻跟这个问题最像的几句原文。翻不到就返回空。"""
    if not path or not query or not os.path.exists(path):
        return []
    q = _grams(query)
    if not q:
        return []

    lines = []
    with open(path, encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = re.sub(r"\s+", " ", line).strip()
            if len(line) >= 4:
                lines.append(line)

    scored = []
    for i, line in enumerate(lines):
        hit = len(q & _grams(line))
        if hit >= min_hit:
            scored.append((hit, i))
    scored.sort(key=lambda x: (-x[0], len(lines[x[1]])))

    out, seen = [], set()
    for _, i in scored:
        block = lines[max(0, i - context): i + context + 1]
        text = "\n".join(block)
        key = text[:40]
        if key in seen:
            continue
        seen.add(key)
        out.append(text)
        if len(out) >= k:
            break
    return out


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print('用法：python3 archive.py 档案.txt "关键词"')
        sys.exit(1)
    hits = search(sys.argv[1], " ".join(sys.argv[2:]), k=3)
    for i, h in enumerate(hits, 1):
        print(f"{i}. {h[:200]}")
