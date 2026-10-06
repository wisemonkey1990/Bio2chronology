from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .export import EXPORTERS, to_markdown
from .extract import LLMExtractor, RuleExtractor
from .models import Chronology
from .pipeline import build_chronology


def _write_exports(chron: Chronology, outdir: Path, formats, quotes: bool):
    outdir.mkdir(parents=True, exist_ok=True)
    for f in formats:
        ext, fn = EXPORTERS[f]
        content = fn(chron, with_quotes=quotes) if f == "md" else fn(chron)
        path = outdir / f"chronology.{ext}"
        path.write_text(content, encoding="utf-8")
        print(f"  → {path}")


def _formats(s: str):
    fs = [x.strip() for x in s.split(",") if x.strip()]
    bad = [x for x in fs if x not in EXPORTERS]
    if bad:
        raise argparse.ArgumentTypeError(f"未知格式 {bad}，可选：{','.join(EXPORTERS)}")
    return fs


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="bio2chronology", description="谱成：把传记重构为年谱")
    sub = p.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build", help="传记文本 → 年谱")
    b.add_argument("input", help="传记 .txt/.md 文件")
    b.add_argument("-o", "--out", default="out", help="输出目录（默认 out/）")
    b.add_argument("--subject", default="", help="传主姓名")
    b.add_argument("--birth-year", type=int, help="传主生年（用于“而立之年”“三十岁”等推算；缺省则尝试自动识别）")
    b.add_argument("--people", default="", help="已知人名，逗号分隔，用于人物识别")
    b.add_argument("--engine", choices=["rules", "llm"], default="rules",
                   help="rules=离线规则；llm=Claude（需 ANTHROPIC_API_KEY）")
    b.add_argument("--model", default="claude-sonnet-5-5")
    b.add_argument("--formats", type=_formats, default=list(EXPORTERS), help="md,csv,json,html")
    b.add_argument("--quotes", action="store_true", help="Markdown 中附带原文引文")

    e = sub.add_parser("export", help="校订后的 chronology.json → 各格式（rejected 条目不会导出）")
    e.add_argument("input")
    e.add_argument("-o", "--out", default="out")
    e.add_argument("--formats", type=_formats, default=["md", "csv", "html"])
    e.add_argument("--quotes", action="store_true")

    r = sub.add_parser("review", help="命令行校订单条事件")
    r.add_argument("input", help="chronology.json")
    r.add_argument("id", help="事件 id，如 e0003")
    r.add_argument("--status", choices=["confirmed", "rejected", "auto"])
    r.add_argument("--year", type=int)
    r.add_argument("--month", type=int)
    r.add_argument("--summary")
    r.add_argument("--note")

    a = p.parse_args(argv)

    if a.cmd == "build":
        text = Path(a.input).read_text(encoding="utf-8")
        people = [x for x in a.people.split(",") if x]
        ex = LLMExtractor(a.subject, model=a.model) if a.engine == "llm" else RuleExtractor(people)
        chron = build_chronology(text, a.subject, a.birth_year, ex, people)
        unresolved = sum(1 for ev in chron.events if ev.year is None)
        low = sum(1 for ev in chron.events if ev.time_confidence in ("inferred", "approx"))
        print(f"抽取 {len(chron.events)} 条事件；{low} 条为推算/估算，{unresolved} 条年份未定，建议人工核对。")
        _write_exports(chron, Path(a.out), a.formats, a.quotes)
        return 0

    if a.cmd == "export":
        chron = Chronology.from_dict(json.loads(Path(a.input).read_text(encoding="utf-8")))
        _write_exports(chron, Path(a.out), a.formats, a.quotes)
        return 0

    path = Path(a.input)
    chron = Chronology.from_dict(json.loads(path.read_text(encoding="utf-8")))
    ev = next((x for x in chron.events if x.id == a.id), None)
    if ev is None:
        print(f"找不到事件 {a.id}", file=sys.stderr)
        return 1
    if a.year is not None:
        ev.year, ev.time_confidence, ev.time_note = a.year, "explicit", "人工校订"
    if a.month is not None:
        ev.month = a.month
    if a.summary:
        ev.summary = a.summary
    if a.note:
        ev.note = a.note
    ev.status = a.status or ("confirmed" if a.status is None else ev.status)
    chron.events.sort(key=lambda x: x.sort_key())
    path.write_text(json.dumps(chron.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"已更新 {a.id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
