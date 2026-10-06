"""Rule-based tagging: category, people, places, works."""
from __future__ import annotations

import re

from .zh import to_simplified

CATEGORIES = [
    ("出生", ["出生", "生于", "诞生", "降生"]),
    ("逝世", ["逝世", "去世", "病逝", "病故", "卒于", "辞世", "殁", "牺牲", "遇害"]),
    ("婚育", ["结婚", "成婚", "娶", "嫁", "完婚", "生子", "生女", "丧妻", "丧偶", "离婚"]),
    ("著述", ["发表", "出版", "著有", "著成", "著述", "撰写", "撰成", "写成", "完成", "译", "创作",
             "付梓", "连载", "笔名", "《"]),
    ("教育", ["考入", "入学", "就读", "毕业", "留学", "求学", "师从", "肄业", "升入", "考取"]),
    ("任职", ["担任", "出任", "就任", "受聘", "聘为", "供职", "任教", "辞去", "调任", "升任",
             "当选", "创办", "创立", "加入", "任"]),
    ("迁徙", ["迁居", "移居", "搬", "前往", "赴", "抵达", "返回", "回到", "旅居", "流亡", "出走",
             "避难", "启程", "南下", "北上", "东渡"]),
    ("交往", ["结识", "相识", "会见", "拜访", "重逢", "相遇", "交往", "通信", "论战", "订交", "结交", "引荐"]),
    ("疾病", ["患", "病", "咯血", "住院", "手术", "疗养"]),
]
CATEGORY_NAMES = [c for c, _ in CATEGORIES] + ["其他"]

_PEOPLE_PATTERNS = [
    re.compile(r"(?:结识|相识|拜访|会见|重逢|师从|师事|遇见|结交|引荐)[了过]?([一-鿿]{2,3})"),
    re.compile(r"与([一-鿿]{2,3}?)(?:重逢|相识|结识|结婚|论战|合作|通信|订交|相遇)"),
]
_PLACE_PATTERN = re.compile(
    r"(?:迁居|移居|搬至|搬到|前往|赴|抵达|抵|返回|回到|旅居|流亡|北上|南下|东渡|出生于|生于)"
    r"([一-鿿]{2,10})")
_PLACE_STOP = set("求任读就定担以为工办参开治避讲学从做当与会探访而并后时的城里内一家，")
_WORK = re.compile(r"《([^》]{1,30})》")


def classify(text: str) -> str:
    text = to_simplified(text)
    for name, kws in CATEGORIES:
        if any(k in text for k in kws):
            return name
    if any(k in text for k in ("学校", "学堂", "书院", "私塾")):
        return "教育"  # weak signal, so only as a fallback
    return "其他"


def find_people(text: str, known=()) -> list:
    folded = to_simplified(text)
    found = [n for n in known if n and to_simplified(n) in folded]
    for pat in _PEOPLE_PATTERNS:
        for m in pat.finditer(folded):
            name = re.sub(r"^(?:同窗|同学|好友|友人|朋友|老师|恩师|诗人|作家)", "", m.group(1))
            name = re.split(r"先生|女士|并|后|于|在|和|与", name)[0]
            start = m.start(1) + m.group(1).find(name)
            name = text[start:start + len(name)]  # keep the source's characters
            if len(name) >= 2 and to_simplified(name) not in {to_simplified(f) for f in found}:
                found.append(name)
    return found


def find_places(text: str) -> list:
    out = []
    for m in _PLACE_PATTERN.finditer(to_simplified(text)):
        n = 0
        for ch in m.group(1):
            if ch in _PLACE_STOP:
                break
            n += 1
        name = text[m.start(1):m.start(1) + min(n, 9)]
        if len(name) >= 2 and name not in out:
            out.append(name)
    return out


def find_works(text: str) -> list:
    return list(dict.fromkeys(_WORK.findall(text)))
