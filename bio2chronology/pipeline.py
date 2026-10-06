"""text → Chronology."""
from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Iterable, Optional

from .classify import classify, find_people, find_places, find_works
from .extract import LLMExtractor, RuleExtractor
from .models import Chronology, Event, Source
from .parser import parse_chapters
from .timeexpr import TimeResolver, scan

_BIRTH = re.compile(r"(?:出生于|生于|诞生于)[^，。；]{0,12}?(\d{4}|[〇零○一二三四五六七八九]{4})年|"
                    r"(\d{4}|[〇零○一二三四五六七八九]{4})年[^。；]{0,10}?(?:出生|诞生|降生)")


def detect_birth_year(text: str) -> Optional[int]:
    from .timeexpr import cn_to_int
    m = _BIRTH.search(text)
    if not m:
        return None
    return cn_to_int(m.group(1) or m.group(2))


def build_chronology(text: str, subject: str = "", birth_year: Optional[int] = None,
                     extractor=None, known_people: Iterable[str] = (),
                     dedupe: bool = True) -> Chronology:
    if birth_year is None:
        birth_year = detect_birth_year(text)
    extractor = extractor or RuleExtractor(known_people)
    resolver = TimeResolver(birth_year)
    events = []
    for chapter in parse_chapters(text):
        for raw in extractor.extract(chapter):
            info = resolver.resolve(raw.time_text) if raw.time_text else None
            ev = Event(
                summary=raw.summary,
                category=raw.category or classify(raw.summary),
                people=raw.people or find_people(raw.summary, known_people),
                places=raw.places or find_places(raw.summary),
                works=raw.works or find_works(raw.summary),
                sources=[Source(chapter.title, raw.paragraph, raw.quote)],
            )
            if info is None:
                ev.time_confidence, ev.time_note = "unresolved", "原文无时间线索"
            else:
                ev.year, ev.month, ev.season = info.year, info.month, info.season
                ev.time_raw, ev.time_confidence, ev.time_note = info.raw, info.confidence, info.note
            events.append(ev)
    if dedupe:
        events = merge_duplicates(events)
    events.sort(key=lambda e: e.sort_key())  # stable: narrative order within the same date
    for i, ev in enumerate(events, 1):
        ev.id = f"e{i:04d}"
    return Chronology(subject=subject, birth_year=birth_year, events=events)


def _same_time(a: Event, b: Event) -> bool:
    return a.year == b.year and (a.month == b.month or not (a.month and b.month))


def merge_duplicates(events: list, threshold: float = 0.75) -> list:
    """Merge events that share a date and have near-identical summaries; keep every source."""
    kept = []
    for ev in events:
        for k in kept:
            if _same_time(k, ev) and SequenceMatcher(None, k.summary, ev.summary).ratio() >= threshold:
                k.sources.extend(ev.sources)
                for attr in ("people", "places", "works"):
                    for v in getattr(ev, attr):
                        if v not in getattr(k, attr):
                            getattr(k, attr).append(v)
                break
        else:
            kept.append(ev)
    return kept
