"""Score a chronology against a hand-made gold list of key events.

Gold items are not exhaustive, so this measures recall and date accuracy on the
items, not precision. An item is "found" when any of its keywords appears in an
event summary (both sides folded to simplified characters); it is "dated
correctly" when at least one matching event carries an accepted year.
"""
from __future__ import annotations

from collections import Counter

from .models import Chronology
from .zh import to_simplified


def evaluate(chron: Chronology, gold: dict) -> dict:
    events = [e for e in chron.events if e.status != "rejected"]
    folded = [(e, to_simplified(e.summary)) for e in events]
    rows = []
    for item in gold["items"]:
        keys = [to_simplified(k) for k in item["any"]]
        hits = [e for e, s in folded if any(k in s for k in keys)]
        years = sorted({e.year for e in hits}, key=lambda y: (y is None, y or 0))
        if not hits:
            status = "missed"
        elif any(e.year in item["years"] for e in hits):
            status = "correct"
        else:
            status = "wrong_year"
        rows.append({"desc": item["desc"], "gold": item["years"], "status": status, "got": years})
    n = len(rows)
    found = sum(r["status"] != "missed" for r in rows)
    correct = sum(r["status"] == "correct" for r in rows)
    conf = Counter(e.time_confidence for e in events)
    birth = chron.birth_year
    return {
        "items": rows,
        "recall": found / n if n else 0.0,
        "dated_correctly": correct / n if n else 0.0,
        "year_accuracy_when_found": correct / found if found else 0.0,
        "events": len(events),
        "by_confidence": dict(conf),
        "before_birth": sum(1 for e in events if birth and e.year and e.year < birth),
    }


def format_report(r: dict) -> str:
    mark = {"correct": "✓", "wrong_year": "✗", "missed": "·"}
    lines = [f"{mark[x['status']]} {x['desc']}（应为 {'/'.join(map(str, x['gold']))}）"
             + (f" ← 得到 {x['got']}" if x["status"] == "wrong_year" else "") for x in r["items"]]
    lines += [
        "",
        f"召回：{r['recall']:.0%}　年份正确（占全部关键事件）：{r['dated_correctly']:.0%}　"
        f"找到者中年份正确：{r['year_accuracy_when_found']:.0%}",
        f"事件总数 {r['events']}；按置信度 {r['by_confidence']}；早于生年的事件 {r['before_birth']}",
    ]
    return "\n".join(lines)
