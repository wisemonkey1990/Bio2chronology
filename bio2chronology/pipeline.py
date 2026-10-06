"""text → Chronology."""
from __future__ import annotations

import hashlib
import re
from difflib import SequenceMatcher
from typing import Iterable, Optional

from .classify import classify, find_people, find_places, find_works
from .extract import RuleExtractor
from .models import Chronology, Event, Source
from .parser import parse_chapters
from .timeexpr import TimeResolver
from .zh import to_simplified

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
                     dedupe: bool = True, age_reckoning: str = "周岁",
                     aliases: Iterable[str] = (), birth_month: Optional[int] = None) -> Chronology:
    return build_from_sources([{"text": text, "age_reckoning": age_reckoning}], subject, birth_year,
                              extractor, known_people, dedupe, aliases, birth_month)


def build_from_sources(sources: list, subject: str = "", birth_year: Optional[int] = None,
                       extractor=None, known_people: Iterable[str] = (), dedupe: bool = True,
                       aliases: Iterable[str] = (), birth_month: Optional[int] = None) -> Chronology:
    """sources: [{"text", "label"?, "age_reckoning"?}]. Each source is read with its own
    narrative context (a year mentioned in one text says nothing about the next)."""
    if birth_year is None:
        birth_year = next((y for y in (detect_birth_year(s["text"]) for s in sources) if y), None)
    extractor = extractor or RuleExtractor(known_people)
    names = [subject, *aliases]
    events = []
    for src in sources:
        resolver = TimeResolver(birth_year, src.get("age_reckoning", "周岁"), birth_month, names)
        label = src.get("label", "")
        for chapter in parse_chapters(src["text"]):
            where = chapter.title if not label else (label if chapter.title == "全文" else f"{label}·{chapter.title}")
            for raw in extractor.extract(chapter):
                info = resolver.resolve(raw.time_text) if raw.time_text else None
                if info is None:
                    info = resolver.inherit()
                ev = Event(
                    summary=raw.summary,
                    category=raw.category or classify(raw.summary),
                    people=raw.people or find_people(raw.summary, known_people),
                    places=raw.places or find_places(raw.summary),
                    works=raw.works or find_works(raw.summary),
                    sources=[Source(where, raw.paragraph, raw.quote)],
                )
                if info is None:
                    ev.time_confidence, ev.time_note = "unresolved", "原文无时间线索"
                else:
                    ev.year, ev.month, ev.season = info.year, info.month, info.season
                    ev.time_raw, ev.time_confidence, ev.time_note = info.raw, info.confidence, info.note
                    if not (ev.month or ev.season):
                        ev.month_hint = resolver.current_month
                ev.key = event_key(raw.summary)
                events.append(ev)
    if dedupe:
        events = merge_duplicates(events)
    events.sort(key=lambda e: e.sort_key())  # stable: narrative order within the same date
    for i, ev in enumerate(events, 1):
        ev.id = f"e{i:04d}"
    return Chronology(subject=subject, birth_year=birth_year, events=events)


def event_key(summary: str) -> str:
    """Fingerprint of an extracted clause, stable across re-runs of the converter."""
    norm = re.sub(r"\s+", "", to_simplified(summary))
    return hashlib.sha1(norm.encode("utf-8")).hexdigest()[:12]


REVIEW_FIELDS = ("status", "year", "month", "season", "summary", "category", "note", "merge_into")


def apply_review(chron: Chronology, overlay: dict) -> int:
    """Apply a review overlay {key: {field: value}} (see review.json); returns how many matched.
    Besides field edits, {"merge_into": <key>} folds an event (sources included) into another,
    for the same happening told by two texts."""
    n = 0
    by_key = {e.key: e for e in chron.events}
    for ev in chron.events:
        edit = overlay.get(ev.key)
        if not edit:
            continue
        n += 1
        for f in REVIEW_FIELDS:
            if f in edit:
                setattr(ev, f, edit[f])
        if "year" in edit or "month" in edit:
            ev.time_confidence, ev.time_note = "explicit", "校订：" + (edit.get("note") or "人工修正日期")
    merged = set()
    for ev in chron.events:
        target = by_key.get((overlay.get(ev.key) or {}).get("merge_into"))
        if target is None or target is ev or target.key in merged:
            continue
        target.sources.extend(ev.sources)
        for attr in ("people", "places", "works"):
            for v in getattr(ev, attr):
                if v not in getattr(target, attr):
                    getattr(target, attr).append(v)
        merged.add(ev.key)
    chron.events = [e for e in chron.events if e.key not in merged]
    chron.events.sort(key=lambda e: e.sort_key())
    for i, ev in enumerate(chron.events, 1):
        ev.id = f"e{i:04d}"
    return n


def _same_time(a: Event, b: Event) -> bool:
    return a.year == b.year and (a.month == b.month or not (a.month and b.month))


def merge_duplicates(events: list, threshold: float = 0.75) -> list:
    """Merge events that share a date and have near-identical summaries; keep every source."""
    kept = []
    for ev in events:
        for k in kept:
            if _same_time(k, ev) and SequenceMatcher(
                    None, to_simplified(k.summary), to_simplified(ev.summary)).ratio() >= threshold:
                k.sources.extend(ev.sources)
                for attr in ("people", "places", "works"):
                    for v in getattr(ev, attr):
                        if v not in getattr(k, attr):
                            getattr(k, attr).append(v)
                break
        else:
            kept.append(ev)
    return kept
