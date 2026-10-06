"""A person's folder: people/<slug>/

    meta.json         name, aliases, birth year/month, summary, sources (file/url/license/age_reckoning)
    source/*.txt      biography texts (only commit texts whose licence allows it)
    review.json       review overlay {event key: {status, year, month, summary, note, …}}
    chronology.json   generated: converter output with review.json applied — do not hand-edit
    eval/gold.json    optional: key events for `bio2chronology eval`
"""
from __future__ import annotations

import json
from pathlib import Path

from .export import to_json
from .extract import LLMExtractor, RuleExtractor
from .models import Chronology
from .pipeline import REVIEW_FIELDS, apply_review, build_from_sources, event_key


def _read_json(path: Path, default):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def _write_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_meta(d: Path) -> dict:
    meta = _read_json(d / "meta.json", None)
    if meta is None:
        raise FileNotFoundError(f"{d / 'meta.json'} 不存在")
    if "sources" not in meta:  # older layout: a single "biography" file
        meta["sources"] = [{"file": meta.get("biography", "source/biography.txt"),
                            "title": meta.get("source", "")}]
    return meta


def load_review(d: Path) -> dict:
    return _read_json(d / "review.json", {})


def _migrate_inline_edits(d: Path, review: dict) -> int:
    """Edits made directly in an older chronology.json move into review.json before it is regenerated."""
    old = _read_json(d / "chronology.json", None)
    if not old:
        return 0
    n = 0
    for e in old.get("events", []):
        key = e.get("key") or event_key(e.get("summary", ""))
        if key in review:
            continue
        edit = {}
        if e.get("status", "auto") != "auto":
            edit["status"] = e["status"]
        if e.get("note"):
            edit["note"] = e["note"]
        if str(e.get("time_note", "")).startswith(("人工校订", "校订")):
            edit["year"], edit["month"] = e.get("year"), e.get("month")
        if edit:
            review[key] = edit
            n += 1
    return n


def convert_person(d: Path, engine: str = "rules", model: str = "claude-sonnet-5-5") -> tuple:
    """Regenerate chronology.json from the sources, then re-apply review.json.
    Returns (chronology, number of review entries applied, number of review entries orphaned)."""
    meta = load_meta(d)
    review = load_review(d)
    migrated = _migrate_inline_edits(d, review)
    if migrated:
        _write_json(d / "review.json", review)
    people = meta.get("known_people", [])
    ex = LLMExtractor(meta["name"], model=model) if engine == "llm" else RuleExtractor(people)
    sources = [{"text": (d / s["file"]).read_text(encoding="utf-8"),
                "label": s.get("label", ""),
                "age_reckoning": s.get("age_reckoning", meta.get("age_reckoning", "周岁"))}
               for s in meta["sources"]]
    chron = build_from_sources(sources, meta["name"], meta.get("birth_year"), ex, people,
                               aliases=meta.get("aliases", []), birth_month=meta.get("birth_month"))
    applied = apply_review(chron, review)
    _write_json_text(d / "chronology.json", to_json(chron))
    return chron, applied, len(review) - applied


def _write_json_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def review_event(chron_path: Path, event_id: str, edits: dict) -> str:
    """Record a reviewer's edit in the sibling review.json and apply it to chronology.json."""
    d = chron_path.parent
    chron = Chronology.from_dict(_read_json(chron_path, {}))
    ev = next((x for x in chron.events if x.id == event_id), None)
    if ev is None:
        raise KeyError(event_id)
    key = ev.key or event_key(ev.summary)
    ev.key = key
    review = load_review(d)
    entry = review.setdefault(key, {})
    entry.update({k: v for k, v in edits.items() if k in REVIEW_FIELDS and v is not None})
    entry.setdefault("_summary", ev.summary[:60])  # human-readable anchor for the JSON file
    _write_json(d / "review.json", review)
    apply_review(chron, {key: entry})
    _write_json_text(chron_path, to_json(chron))
    return key
