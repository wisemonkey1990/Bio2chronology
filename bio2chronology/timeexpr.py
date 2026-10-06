"""Time-expression scanning and normalisation.

`TimeResolver` is stateful: it remembers the year last mentioned in the
narrative, so that "同年秋", "次年", "三年后" or a bare "暮春" resolve against
context, and (given a birth year) ages such as "而立之年" become calendar years.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from .models import SEASON_START
from .zh import to_simplified

_DIG = {"〇": 0, "零": 0, "○": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
        "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
_MONTH_WORD = {"正": 1, "冬": 11, "腊": 12}
IDIOM_AGE = {"弱冠": 20, "及冠": 20, "而立": 30, "不惑": 40, "知天命": 50,
             "知命": 50, "耳顺": 60, "花甲": 60, "古稀": 70}
# offset of the month inside a season, by modifier
_MOD_OFFSET = {"初": 0, "孟": 0, "早": 0, "仲": 1, "": 0, "盛": 1, "暮": 2, "季": 2, "晚": 2, "深": 2}


ERA_BASE = {"乾隆": 1736, "嘉庆": 1796, "道光": 1821, "咸丰": 1851, "同治": 1862,
            "光绪": 1875, "宣统": 1909, "民国": 1912}


def cn_to_int(s: str) -> Optional[int]:
    s = s.strip().replace("廿", "二十").replace("卅", "三十")
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


_NUM = r"(?:[0-9]+|[〇零○一二两三四五六七八九十廿卅]+)"
_MASTER = re.compile("|".join([
    r"(?P<era>清?(?P<eraname>乾隆|嘉庆|道光|咸丰|同治|光绪|宣统|民国)(?P<eran>[0-9十一二三四五六七八九元廿卅]+)年)",
    r"(?P<abs>(?P<absn>[0-9]{3,4}|[〇零○一二三四五六七八九]{4})年)(?![之以]?[后前])",
    r"(?P<vague>[数几多]年(?:之?后|以后))",
    rf"(?P<after>(?P<an>{_NUM})年(?:之?后|以后))",
    rf"(?P<before>(?P<bn>{_NUM})年(?:之?前|以前))",
    r"(?P<same>同年|当年|是年|该年|本年|这一年|那一年)",
    rf"(?P<ord>第(?P<on>{_NUM})年)",
    r"(?P<next>次年|翌年|来年|隔年)",
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


_PAREN = re.compile(r"（[^（）]*）|\([^()]*\)")


def _prepare(text: str) -> str:
    """Fold to simplified characters and blank out parenthesised asides — lifespans,
    calendar conversions, "（1912年改制…）" — so they are not read as the event's date.
    Every step is length-preserving, so offsets still index the original text."""
    text = to_simplified(text)
    return _PAREN.sub(lambda m: " " * len(m.group(0)), text)


def scan(text: str) -> list:
    """Find time expressions in `text` (no state, no resolution)."""
    original, text = text, _prepare(text)
    refs = []
    for m in _MASTER.finditer(text):
        kind = m.lastgroup
        # lastgroup is the innermost last-matched group; map back to the outer kind.
        for k in ("era", "abs", "vague", "after", "before", "same", "ord", "next", "prev2",
                  "prev", "idiom", "age", "month", "season"):
            if m.group(k) is not None:
                kind = k
                break
        value = None
        if kind == "era":
            n = cn_to_int(m.group("eran"))
            value = None if n is None else ERA_BASE[m.group("eraname")] + n - 1
        elif kind == "ord":
            value = cn_to_int(m.group("on"))
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
        if kind in ("era", "abs", "ord") and (value is None):
            continue
        if kind in ("after", "before") and (value is None or value >= 100):
            continue
        if kind == "age" and (value is None or value > 110 or value == 0):
            continue
        refs.append(TimeRef(kind, m.start(), m.end(), original[m.start():m.end()], value))
    return refs


_RELATIVE = ("same", "next", "prev", "prev2", "after", "before", "vague")


class TimeResolver:
    """Resolves time expressions against narrative context.

    age_reckoning: "周岁" (age N → birth+N; with a known birth month and event month,
    an event before the birthday falls in birth+N+1) or "虚岁" (age N → birth+N-1,
    the traditional count used in most pre-1949 Chinese writing).
    subject_names: names/aliases of the subject; an age phrase like "28岁的朱安" that
    describes someone else is ignored.
    """

    def __init__(self, birth_year: Optional[int] = None, age_reckoning: str = "周岁",
                 birth_month: Optional[int] = None, subject_names=()):
        self.birth_year = birth_year
        self.birth_month = birth_month
        self.age_reckoning = age_reckoning
        self.subject_names = [n for n in subject_names if n]
        self.current_year: Optional[int] = None
        self.anchor_year: Optional[int] = None  # base for "第二年/第三年" sequences
        self.current_month: Optional[int] = None  # month in context, for ordering only

    def _age_is_subjects(self, text: str, ref: TimeRef) -> bool:
        tail = to_simplified(text[ref.end:ref.end + 12])
        tail = tail.lstrip("时之")
        if not tail.startswith("的"):
            return True
        tail = tail[1:]
        return any(tail.startswith(to_simplified(n)) for n in self.subject_names) \
            or tail.startswith(("他", "她", "传主"))

    def _age_year(self, age: int, month: Optional[int]) -> tuple:
        if self.age_reckoning == "虚岁":
            return self.birth_year + age - 1, f"生年{self.birth_year}+{age}岁−1（按虚岁）"
        year = self.birth_year + age
        if month and self.birth_month and month < self.birth_month:
            return year + 1, f"生年{self.birth_year}+{age}周岁，事在{month}月、生日（{self.birth_month}月）前，故为次年"
        return year, f"生年{self.birth_year}+{age}岁（按周岁；生日前的事件可能在次年）"

    def resolve(self, text: str) -> Optional[TimeInfo]:
        refs = scan(text)
        if not refs:
            return None
        raw = text[refs[0].start:refs[-1].end] if refs[-1].end - refs[0].start <= 16 \
            else "、".join(r.text for r in refs)
        month = next((r.value for r in refs if r.kind == "month"), None)
        season = next((r.value[0] + r.value[1] for r in refs if r.kind == "season"), None)
        notes = []

        # Precedence: an explicit calendar year beats a relative expression, which beats an age.
        explicit = next((r for r in refs if r.kind in ("abs", "era")), None)
        relative = next((r for r in refs if r.kind in _RELATIVE or r.kind == "ord"), None)
        ages = [r for r in refs if r.kind in ("age", "idiom")]
        year, conf, moves_cursor, sets_anchor = None, "explicit", True, True
        if explicit:
            year = explicit.value
            if explicit.kind == "era":
                notes.append(f"{explicit.text}=公元{year}年")
        elif relative:
            if relative.kind == "ord":
                base = self.anchor_year if self.anchor_year is not None else self.current_year
                if base is None:
                    notes.append(f"“{relative.text}”缺少可参照的上文年份")
                else:
                    year, conf, sets_anchor = base + relative.value - 1, "relative", False
                    notes.append(f"以{base}年为第一年，“{relative.text}”为{year}年")
            elif self.current_year is None:
                notes.append(f"“{relative.text}”缺少可参照的上文年份")
            else:
                delta = {"same": 0, "next": 1, "prev": -1, "prev2": -2, "after": relative.value,
                         "before": -(relative.value or 0), "vague": 3}[relative.kind]
                year = self.current_year + delta
                conf = "approx" if relative.kind == "vague" else "relative"
                if relative.kind in ("prev", "prev2", "before"):
                    moves_cursor = False  # flashback: don't drag the narrative cursor back
                notes.append(f"以上文{self.current_year}年为基准，“{relative.text}”{delta:+d}年" if delta
                             else f"“{relative.text}”指上文{self.current_year}年")
                if relative.kind == "vague":
                    notes.append("“数年”按3年估算，请核对")
        else:
            for r in ages:
                if not self._age_is_subjects(text, r):
                    notes.append(f"“{r.text}”指他人年龄，未用于推算")
                    continue
                if self.birth_year is None:
                    notes.append(f"“{r.text}”需要传主生年才能推算")
                    continue
                year, note = self._age_year(r.value, month)
                conf = "approx" if r.kind == "idiom" else "inferred"
                notes.append(note)
                break

        if year is None and not (explicit or relative or month or season) \
                and all(not self._age_is_subjects(text, r) for r in ages):
            return None  # only someone else's age was mentioned
        if year is None and (month or season):
            if self.current_year is not None:
                year, conf = self.current_year, "inferred"
                notes.append(f"沿用上文{self.current_year}年")
        if year is None:
            return TimeInfo(None, month, season, raw, "unresolved", "；".join(notes) or "无法确定年份")
        if moves_cursor:
            if year != self.current_year:
                self.current_month = None
            self.current_year = year
            if sets_anchor:
                self.anchor_year = year
            if month or season:
                self.current_month = month or SEASON_START.get(season[-1])
        return TimeInfo(year, month, season, raw, conf, "；".join(notes))

    def inherit(self) -> Optional[TimeInfo]:
        """Date for an event-bearing clause with no time expression: the narrative's current year."""
        if self.current_year is None or (self.birth_year and self.current_year < self.birth_year):
            return None  # background before the subject's birth (a grandfather's degree…) dates nothing
        return TimeInfo(self.current_year, None, None, "", "inferred",
                        f"原文无时间词，沿用上文{self.current_year}年")
