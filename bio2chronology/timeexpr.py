"""Time-expression scanning and normalisation.

`TimeResolver` is stateful: it remembers the year last mentioned in the
narrative, so that "同年秋", "次年", "三年后" or a bare "暮春" resolve against
context, and (given a birth year) ages such as "而立之年" become calendar years.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

_DIG = {"〇": 0, "零": 0, "○": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
        "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
_MONTH_WORD = {"正": 1, "冬": 11, "腊": 12}
IDIOM_AGE = {"弱冠": 20, "及冠": 20, "而立": 30, "不惑": 40, "知天命": 50,
             "知命": 50, "耳顺": 60, "花甲": 60, "古稀": 70}
# offset of the month inside a season, by modifier
_MOD_OFFSET = {"初": 0, "孟": 0, "早": 0, "仲": 1, "": 0, "盛": 1, "暮": 2, "季": 2, "晚": 2, "深": 2}


def cn_to_int(s: str) -> Optional[int]:
    s = s.strip()
    if not s:
        return None
    if s.isdigit():
        return int(s)
    if s == "元":
        return 1
    if all(c in _DIG for c in s):
        return int("".join(str(_DIG[c]) for c in s))
    if "十" in s:
        head, _, tail = s.partition("十")
        tens = 1 if head == "" else _DIG.get(head)
        if tens is None:
            return None
        if tail == "":
            return tens * 10
        unit = _DIG.get(tail)
        return None if unit is None else tens * 10 + unit
    return None


_NUM = r"(?:[0-9]+|[〇零○一二两三四五六七八九十]+)"
_MASTER = re.compile("|".join([
    r"(?P<mg>民国(?P<mgn>[0-9十一二三四五六七八九元]+)年)",
    r"(?P<abs>(?P<absn>[0-9]{3,4}|[〇零○一二三四五六七八九]{4})年)(?![之以]?[后前])",
    r"(?P<vague>[数几多]年(?:之?后|以后))",
    rf"(?P<after>(?P<an>{_NUM})年(?:之?后|以后))",
    rf"(?P<before>(?P<bn>{_NUM})年(?:之?前|以前))",
    r"(?P<same>同年|当年|是年|该年|本年|这一年|那一年)",
    r"(?P<next>次年|翌年|第二年|来年|隔年)",
    r"(?P<prev2>前年)",
    r"(?P<prev>前一年|上一年|去年)",
    r"(?P<idiom>弱冠|及冠|而立|不惑|知天命|知命|耳顺|花甲|古稀)(?:之年)?",
    rf"(?P<age>(?P<agen>{_NUM})岁)",
    r"(?P<month>闰?(?P<monn>[0-9]{1,2}|[一二三四五六七八九十]{1,3}|正|腊|冬)月)",
    r"(?P<season>(?P<mod>[初仲暮晚孟季盛深早])?(?P<sea>[春夏秋冬])(?:天|季)?)",
]))
_PREV_OK = set("，,；;：:、 \n（(“\"")
_NEXT_OK = set("，,。；;：:、时间之末初天季 \n）)”\"")


@dataclass
class TimeRef:
    kind: str
    start: int
    end: int
    text: str
    value: object = None


@dataclass
class TimeInfo:
    year: Optional[int]
    month: Optional[int]
    season: Optional[str]
    raw: str
    confidence: str  # explicit | relative | inferred | approx | unresolved
    note: str = ""


def scan(text: str) -> list:
    """Find time expressions in `text` (no state, no resolution)."""
    refs = []
    for m in _MASTER.finditer(text):
        kind = m.lastgroup
        # lastgroup is the innermost last-matched group; map back to the outer kind.
        for k in ("mg", "abs", "vague", "after", "before", "same", "next", "prev2",
                  "prev", "idiom", "age", "month", "season"):
            if m.group(k) is not None:
                kind = k
                break
        value = None
        if kind == "mg":
            value = cn_to_int(m.group("mgn"))
        elif kind == "abs":
            value = cn_to_int(m.group("absn"))
        elif kind == "after":
            value = cn_to_int(m.group("an"))
        elif kind == "before":
            value = cn_to_int(m.group("bn"))
        elif kind == "idiom":
            value = IDIOM_AGE[m.group("idiom")]
        elif kind == "age":
            value = cn_to_int(m.group("agen"))
        elif kind == "month":
            w = m.group("monn")
            value = _MONTH_WORD.get(w) or cn_to_int(w)
            if value is None or not 1 <= value <= 12:
                continue
        elif kind == "season":
            prev = text[m.start() - 1] if m.start() > 0 else ""
            nxt = text[m.end()] if m.end() < len(text) else ""
            contiguous = bool(refs) and refs[-1].end == m.start()
            prev_ok = m.start() == 0 or prev in _PREV_OK or contiguous
            next_ok = m.end() == len(text) or nxt in _NEXT_OK
            # a bare "春/秋/…" must stand alone (guards "夏衍", "秋瑾", "春风"); a modifier ("暮春") only needs a clean tail
            if not (next_ok and (prev_ok or m.group("mod"))):
                continue
            value = (m.group("mod") or "", m.group("sea"))
        if kind in ("mg", "abs") and (value is None):
            continue
        if kind in ("after", "before") and (value is None or value >= 100):
            continue
        if kind == "age" and (value is None or value > 110 or value == 0):
            continue
        refs.append(TimeRef(kind, m.start(), m.end(), m.group(0), value))
    return refs


class TimeResolver:
    def __init__(self, birth_year: Optional[int] = None):
        self.birth_year = birth_year
        self.current_year: Optional[int] = None

    def resolve(self, text: str) -> Optional[TimeInfo]:
        refs = scan(text)
        if not refs:
            return None
        raw = text[refs[0].start:refs[-1].end] if refs[-1].end - refs[0].start <= 16 \
            else "、".join(r.text for r in refs)
        year = month = season = None
        conf, notes = "explicit", []
        moves_cursor = True
        for r in refs:
            if r.kind == "abs":
                year = r.value
            elif r.kind == "mg":
                year = 1911 + r.value
                notes.append(f"民国{r.value}年=公元{year}年")
            elif r.kind in ("same", "next", "prev", "prev2", "after", "before", "vague"):
                if self.current_year is None:
                    notes.append(f"“{r.text}”缺少可参照的上文年份")
                    continue
                delta = {"same": 0, "next": 1, "prev": -1, "prev2": -2,
                         "after": r.value, "before": -(r.value or 0), "vague": 3}[r.kind]
                year = self.current_year + delta
                conf = "approx" if r.kind == "vague" else "relative"
                if r.kind in ("prev", "prev2", "before"):
                    moves_cursor = False  # flashback: don't drag the narrative cursor back
                notes.append(f"以上文{self.current_year}年为基准，“{r.text}”{delta:+d}年" if delta
                             else f"“{r.text}”指上文{self.current_year}年")
                if r.kind == "vague":
                    notes.append("“数年”按3年估算，请核对")
            elif r.kind in ("age", "idiom"):
                if self.birth_year is None:
                    notes.append(f"“{r.text}”需要传主生年才能推算")
                    continue
                year = self.birth_year + r.value
                conf = "inferred"
                notes.append(f"生年{self.birth_year}+{r.value}岁（按周岁；若为虚岁则早一年）")
            elif r.kind == "month":
                month = r.value
            elif r.kind == "season":
                mod, sea = r.value
                season = mod + sea
        if year is None and (month or season):
            if self.current_year is not None:
                year, conf = self.current_year, "inferred"
                notes.append(f"沿用上文{self.current_year}年")
        if year is None:
            return TimeInfo(None, month, season, raw, "unresolved", "；".join(notes) or "无法确定年份")
        if moves_cursor:
            self.current_year = year
        return TimeInfo(year, month, season, raw, conf, "；".join(notes))
