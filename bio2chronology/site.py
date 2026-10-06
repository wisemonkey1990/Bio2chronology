"""Compile `people/<slug>/{meta.json,chronology.json}` into a static website."""
from __future__ import annotations

import http.server
import json
import shutil
from functools import partial
from pathlib import Path

from .models import Chronology

WEB_DIR = Path(__file__).parent / "web"


def load_person(d: Path) -> dict | None:
    cj = d / "chronology.json"
    if not cj.exists():
        return None
    mj = d / "meta.json"
    meta = json.loads(mj.read_text(encoding="utf-8")) if mj.exists() else {}
    chron = Chronology.from_dict(json.loads(cj.read_text(encoding="utf-8")))
    events = [e.to_dict() for e in chron.events if e.status != "rejected"]
    death = meta.get("death_year") or next(
        (e["year"] for e in events if e["category"] == "逝世" and e["year"]), None)
    return {
        "slug": d.name,
        "name": meta.get("name") or chron.subject or d.name,
        "aliases": meta.get("aliases", []),
        "birth_year": meta.get("birth_year") or chron.birth_year,
        "death_year": death,
        "summary": meta.get("summary", ""),
        "source": meta.get("source", ""),
        "fictional": bool(meta.get("fictional")),
        "events": events,
    }


def build_site(people_dir: str | Path, out_dir: str | Path) -> int:
    out = Path(out_dir)
    if out.exists():
        shutil.rmtree(out)
    (out / "data").mkdir(parents=True)
    for f in WEB_DIR.iterdir():
        shutil.copy2(f, out / f.name)
    (out / ".nojekyll").touch()
    index = []
    for d in sorted(Path(people_dir).iterdir()):
        person = load_person(d) if d.is_dir() else None
        if not person:
            continue
        (out / "data" / f"{d.name}.json").write_text(
            json.dumps(person, ensure_ascii=False), encoding="utf-8")
        index.append({k: person[k] for k in ("slug", "name", "birth_year", "death_year", "summary", "fictional")}
                     | {"count": len(person["events"]),
                        "confirmed": sum(e["status"] == "confirmed" for e in person["events"])})
    index.sort(key=lambda p: (p["birth_year"] is None, p["birth_year"] or 0))
    (out / "data" / "index.json").write_text(
        json.dumps({"people": index}, ensure_ascii=False), encoding="utf-8")
    return len(index)


def serve(directory: str | Path, port: int = 8000) -> None:
    handler = partial(http.server.SimpleHTTPRequestHandler, directory=str(directory))
    with http.server.ThreadingHTTPServer(("127.0.0.1", port), handler) as srv:
        print(f"http://127.0.0.1:{port}/  （Ctrl+C 退出）")
        try:
            srv.serve_forever()
        except KeyboardInterrupt:
            pass
