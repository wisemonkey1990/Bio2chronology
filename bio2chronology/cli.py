from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .export import EXPORTERS, to_json
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

    r = sub.add_parser("review", help="校订单条事件（记录到同目录 review.json，重新转换后仍保留）")
    r.add_argument("input", help="chronology.json")
    r.add_argument("id", help="事件 id，如 e0003")
    r.add_argument("--status", choices=["confirmed", "rejected", "auto"])
    r.add_argument("--year", type=int)
    r.add_argument("--month", type=int)
    r.add_argument("--summary")
    r.add_argument("--note")

    c = sub.add_parser("convert", help="people/<slug>/ 下的传记 → chronology.json（离线管线，产物需人工校订后提交）")
    c.add_argument("dir", help="人物目录，如 people/lu-xun（含 meta.json 与其中列出的来源文本）")
    c.add_argument("--engine", choices=["rules", "llm"], default="rules")
    c.add_argument("--model", default="claude-sonnet-5-5")

    f = sub.add_parser("fetch", help="从 Wikipedia / Wikisource 下载来源文本，登记到 meta.json")
    f.add_argument("dir", help="人物目录")
    f.add_argument("--site", required=True, help="如 zh.wikipedia.org、zh.wikisource.org")
    f.add_argument("--title", required=True, help="页面标题")
    f.add_argument("--label", default="", help="来源简称，显示在出处中，如“维基百科”")
    f.add_argument("--sections", default="", help="只保留这些二级章节，逗号分隔（如：生平）")
    f.add_argument("--start", default="", help="正文从此标记开始（Wikisource 多篇合刊时用）")
    f.add_argument("--license", default="", help="许可，如 CC BY-SA 4.0、公有领域")
    f.add_argument("--age-reckoning", choices=["周岁", "虚岁"], default="周岁")

    ev = sub.add_parser("eval", help="用 eval/gold.json 评测某人物的年谱")
    ev.add_argument("dir")

    st = sub.add_parser("site", help="网站：build 构建静态站 / serve 本地预览")
    st.add_argument("action", choices=["build", "serve"])
    st.add_argument("--people", default="people", help="人物数据目录")
    st.add_argument("-o", "--out", default="site", help="站点输出目录")
    st.add_argument("--port", type=int, default=8000)

    a = p.parse_args(argv)

    if a.cmd == "convert":
        from .project import convert_person
        chron, applied, orphaned = convert_person(Path(a.dir), a.engine, a.model)
        low = sum(1 for x in chron.events if x.time_confidence in ("inferred", "approx"))
        print(f"{chron.subject}：{len(chron.events)} 条事件（{low} 条推断/估算）；套用校订 {applied} 条"
              + (f"；{orphaned} 条校订未能对应（原文或抽取结果已变，请检查 review.json）" if orphaned else ""))
        return 0

    if a.cmd == "fetch":
        from .sources import fetch_raw, page_url, wikisource_body, wikitext_to_text
        d = Path(a.dir)
        raw = fetch_raw(a.site, a.title)
        sections = tuple(x for x in a.sections.split(",") if x)
        text = wikisource_body(raw, a.start) if "wikisource" in a.site else wikitext_to_text(raw, sections)
        fname = f"source/{a.site.split('.')[1]}-{a.label or 'text'}.txt"
        (d / "source").mkdir(parents=True, exist_ok=True)
        (d / fname).write_text(text, encoding="utf-8")
        meta_path = d / "meta.json"
        meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {"name": d.name}
        entry = {"file": fname, "label": a.label, "title": a.title, "url": page_url(a.site, a.title),
                 "license": a.license, "age_reckoning": a.age_reckoning}
        meta["sources"] = [s for s in meta.get("sources", []) if s.get("file") != fname] + [entry]
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"{len(text)} 字 → {d / fname}；已登记到 meta.json")
        return 0

    if a.cmd == "eval":
        from .evaluate import evaluate, format_report
        d = Path(a.dir)
        chron = Chronology.from_dict(json.loads((d / "chronology.json").read_text(encoding="utf-8")))
        gold = json.loads((d / "eval" / "gold.json").read_text(encoding="utf-8"))
        print(format_report(evaluate(chron, gold)))
        return 0

    if a.cmd == "site":
        from .site import build_site, serve
        if a.action == "build" or not Path(a.out, "index.html").exists():
            print(f"已构建 {build_site(a.people, a.out)} 位人物 → {a.out}/")
        if a.action == "serve":
            serve(a.out, a.port)
        return 0

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

    from .project import review_event
    edits = {"status": a.status or "confirmed", "year": a.year, "month": a.month,
             "summary": a.summary, "note": a.note}
    try:
        key = review_event(Path(a.input), a.id, edits)
    except KeyError:
        print(f"找不到事件 {a.id}", file=sys.stderr)
        return 1
    print(f"已更新 {a.id}（review.json 键 {key}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
