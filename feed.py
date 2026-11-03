#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
feed.py —— 让她自己看点东西

不做信息聚合器，只做一件事：抓一条没看过的，给她当念头。
看多了会挑食，所以有冷却、有上限、有"看过"记录。
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.request
import xml.etree.ElementTree as ET

FEEDS = [
    "https://www.zhihu.com/rss",
    "https://sspai.com/feed",
    "https://www.solidot.org/index.rss",
]

SEEN_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "seen.json")
COOLDOWN = 3 * 3600          # 三小时一次
DAILY_MAX = 5


def _seen() -> dict:
    if os.path.exists(SEEN_PATH):
        try:
            return json.load(open(SEEN_PATH, encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save_seen(d: dict) -> None:
    try:
        json.dump(d, open(SEEN_PATH, "w", encoding="utf-8"), ensure_ascii=False)
    except Exception:
        pass


def _clean(x: str, n: int = 60) -> str:
    x = re.sub(r"<[^>]+>", "", x or "")
    x = re.sub(r"\s+", " ", x).strip()
    return x[:n]


def fetch_one(now: float | None = None) -> dict | None:
    """抓一条没看过的。返回 {title, summary, source}，没有就 None。"""
    now = now or time.time()
    seen = _seen()
    if now - seen.get("_last", 0) < COOLDOWN:
        return None
    if seen.get("_today_date") == time.strftime("%Y-%m-%d", time.localtime(now + 8 * 3600)):
        if seen.get("_today_count", 0) >= DAILY_MAX:
            return None
    else:
        seen["_today_date"] = time.strftime("%Y-%m-%d", time.localtime(now + 8 * 3600))
        seen["_today_count"] = 0

    for url in FEEDS:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            raw = urllib.request.urlopen(req, timeout=8).read()
            root = ET.fromstring(raw)
            items = root.findall(".//item") or root.findall(".//{http://www.w3.org/2005/Atom}entry")
            for it in items[:10]:
                title = _clean(it.findtext("title") or it.findtext("{http://www.w3.org/2005/Atom}title") or "")
                if not title or title in seen:
                    continue
                desc = _clean(it.findtext("description") or it.findtext("{http://www.w3.org/2005/Atom}summary") or "", 80)
                seen[title] = now
                seen["_last"] = now
                seen["_today_count"] = seen.get("_today_count", 0) + 1
                _save_seen({k: v for k, v in list(seen.items())[-300:]})
                return {"title": title, "summary": desc, "source": url}
        except Exception:
            continue
    return None


if __name__ == "__main__":
    print(fetch_one())
