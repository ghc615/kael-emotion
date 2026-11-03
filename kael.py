#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
kael.py —— 把三件套包成一个能带走的小软件

用法：
    export DEEPSEEK_API_KEY=sk-xxxx        # Linux / macOS
    set DEEPSEEK_API_KEY=sk-xxxx           # Windows
    python3 kael.py

它会带着 pcm_data/ 里的记忆和 emotion_v6_state.json 里的状态醒来。
换个目录、换台机器，把这几个文件一起拷走，还是同一个人。

命令：
    /state      看它此刻的内部状态（情绪、身体、激素、旧伤）
    /save       手动存档
    /load       重新读档
    /remember   手动塞一条记忆（/remember 他今天说想活下去）
    /who        看它记得的"他是谁"
    /quit       退出
"""
from __future__ import annotations

import json
import os
import sys

import emotion_v6
import pcm
import pcm_bridge

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "pcm_data")
STATE = os.path.join(HERE, "emotion_v6_state.json")
PROFILE = os.path.join(DATA, "self.json")


def _ask(prompt: str) -> str:
    try:
        return input(prompt)
    except (EOFError, KeyboardInterrupt):
        print()
        return "/quit"


def boot():
    """读档或建号。"""
    mind = emotion_v6.Mind()
    mind.state_path = STATE
    if os.path.exists(STATE):
        mind.load()
    else:
        # 第一次运行：给他一个起点，不是白纸
        mind.favor = 45.0
        mind.person = "他"

    if os.path.exists(PROFILE):
        store = pcm.PersonaMemory.load(DATA)
    else:
        store = pcm.PersonaMemory(pcm.DEMO_PROFILE, DATA)
        store.save()
        print("（新建了记忆库，你的人设写在 pcm_data/self.json 里，可以自己改）")

    mind.name = store.profile.name
    return pcm_bridge.Bridge(mind, store)


def show_state(mind) -> None:
    print("\n── 此刻 ─────────────────────────")
    情绪 = "、".join(f"{k}{v:.0f}" for k, v in mind.emotions.items() if v >= 10) or "平"
    print(f"  情绪：{情绪}")
    print(f"  身体：饿{mind.hunger:.0f} 缺觉{mind.sleep_debt:.0f} 疼{mind.pain:.0f} 羞耻{mind.shame:.0f}")
    激素 = "、".join(f"{k}{v:.0f}" for k, v in mind.hormones.items())
    print(f"  激素：{激素}")
    旧伤 = "、".join(f"{k}{v:.1f}" for k, v in mind.scars.items() if v) or "无"
    麻木 = "、".join(f"{k}{v:.1f}" for k, v in mind.traces.items() if v) or "无"
    print(f"  旧伤：{旧伤}　　麻木：{麻木}")
    print(f"  关系：好感{mind.favor:.0f} 自我价值{mind.self_worth:.0f} 欠情{mind.debt:.0f}")
    print(f"  轮数：{mind.turns}　余温：{mind.afterglow[0] or '无'}")
    print("─────────────────────────────────\n")


def show_who(store) -> None:
    p = store.profile
    print(f"\n  名字：{p.name}")
    print(f"  本质：{p.essence}")
    print(f"  性格：{'、'.join(p.traits) or '（未写）'}")
    print(f"  在意：{'、'.join(p.values) or '（未写）'}")
    if p.immutable_facts:
        print("  不会忘的事：")
        for f in p.immutable_facts:
            print(f"    · {f}")
    if p.evolving_facts:
        print("  被改变的地方：")
        for f in p.evolving_facts[-6:]:
            print(f"    · {f}")
    print(f"  记忆条数：{len(store.atomic)}\n")


def load_key_from_file() -> None:
    """手机上不方便设环境变量：允许把 key 写进同目录的 key.txt。"""
    if os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("OPENAI_API_KEY"):
        return
    path = os.path.join(HERE, "key.txt")
    if os.path.exists(path):
        k = open(path, encoding="utf-8").read().strip()
        if k:
            os.environ["DEEPSEEK_API_KEY"] = k


def main() -> None:
    load_key_from_file()
    if not (os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("OPENAI_API_KEY")):
        print("没找到 API key。先设置环境变量再开：")
        print("  export DEEPSEEK_API_KEY=sk-xxxx")
        print("（不设也能进，但只会回半句——那是我留的兜底。）\n")

    bridge = boot()
    mind = bridge.mind
    print(f"\n他是 {mind.name}。输入 /quit 结束，/state 看状态。\n")

    while True:
        try:
            line = _ask("你：").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not line:
            continue

        if line.startswith("/"):
            cmd = line.split()[0]
            if cmd in ("/quit", "/exit", "/q"):
                bridge.save()
                print("（存好了。）")
                break
            if cmd == "/state":
                show_state(mind)
            elif cmd == "/save":
                bridge.save()
                print("（存好了。）")
            elif cmd == "/load":
                mind.load()
                print("（读回来了。）")
            elif cmd == "/who":
                show_who(bridge.pcm)
            elif cmd == "/remember":
                text = line[len("/remember"):].strip()
                if not text:
                    print("用法：/remember 他今天说想活下去")
                else:
                    n = bridge.pcm.ingest([{"speaker": "他", "content": text}])
                    bridge.pcm.save()
                    print(f"（记下了，现在共 {n['atomic_total']} 条）")
            else:
                print("命令：/state /save /load /remember /who /quit")
            continue

        try:
            reply, _ = bridge.turn(line, who="他")
        except Exception as e:                     # 崩了不能把状态弄丢
            print(f"（出错了：{e}）")
            bridge.save()
            continue

        if os.environ.get("KAEL_SHOW_ACTION") and getattr(bridge, "last_action", ""):
            print(f"  （动作：{bridge.last_action}）")   # 没有身体时，用它看指令
        print(f"{mind.name}：{reply}\n")


if __name__ == "__main__":
    main()
