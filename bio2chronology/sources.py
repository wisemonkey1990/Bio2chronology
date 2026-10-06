"""Source ingestion: fetch a biography from Wikipedia / Wikisource and clean it to plain text.

Only `action=raw` is used (one request per page); the MediaWiki API is heavily
rate-limited for anonymous clients.
"""
from __future__ import annotations

import re
import urllib.parse
import urllib.request

USER_AGENT = "Bio2Chronology/0.1 (https://github.com/wisemonkey1990/Bio2chronology)"


def fetch_raw(site: str, title: str) -> str:
    """site: e.g. "zh.wikipedia.org" or "zh.wikisource.org"."""
    url = f"https://{site}/w/index.php?title={urllib.parse.quote(title)}&action=raw"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read().decode("utf-8")


def page_url(site: str, title: str) -> str:
    return f"https://{site}/wiki/{urllib.parse.quote(title)}"


def _strip_templates(text: str) -> str:
    """Remove {{...}} (nested) — infoboxes, citation templates, notes."""
    out, depth, i = [], 0, 0
    while i < len(text):
        two = text[i:i + 2]
        if two == "{{":
            depth += 1
            i += 2
        elif two == "}}" and depth:
            depth -= 1
            i += 2
        else:
            if not depth:
                out.append(text[i])
            i += 1
    return "".join(out)


def _strip_tables(text: str) -> str:
    out, depth = [], 0
    for line in text.split("\n"):
        s = line.lstrip()
        if s.startswith("{|"):
            depth += 1
        elif s.startswith("|}") and depth:
            depth -= 1
            continue
        if not depth:
            out.append(line)
    return "\n".join(out)


def _conv(m: re.Match) -> str:
    """-{zh-hans:甲;zh-hant:乙}- → 甲 ; -{文字}- → 文字"""
    body = m.group(1)
    if ":" in body and ";" in body or re.match(r"\s*zh-", body):
        for part in body.split(";"):
            if ":" in part:
                lang, _, val = part.partition(":")
                if lang.strip() in ("zh-hans", "zh-cn", "zh"):
                    return val
        return body.split(";")[0].partition(":")[2]
    return body


def wikitext_to_text(wikitext: str, sections: tuple = (), stop_at_level: int = 2) -> str:
    """Convert wikitext to plain text. Headings become `# 标题` lines so the chapter
    parser can pick them up. If `sections` is given, keep only those level-2 sections
    (and their subsections)."""
    t = wikitext
    t = re.sub(r"<!--.*?-->", "", t, flags=re.S)
    t = re.sub(r"<ref[^>/]*/>", "", t)
    t = re.sub(r"<ref[^>]*>.*?</ref>", "", t, flags=re.S)
    t = re.sub(r"<(gallery|timeline|math|score)[^>]*>.*?</\1>", "", t, flags=re.S | re.I)
    t = _strip_tables(_strip_templates(t))
    t = re.sub(r"-\{(.*?)\}-", _conv, t, flags=re.S)
    t = re.sub(r"\[\[(?:File|Image|文件|檔案|图像|圖像|Category|分类|分類):[^\[\]]*(?:\[\[[^\]]*\]\][^\[\]]*)*\]\]", "", t, flags=re.I)
    t = re.sub(r"\[\[([^\]|]*)\|([^\]]*)\]\]", r"\2", t)
    t = re.sub(r"\[\[([^\]]*)\]\]", r"\1", t)
    t = re.sub(r"\[https?://\S+\s([^\]]*)\]", r"\1", t)
    t = re.sub(r"\[https?://\S+\]", "", t)
    t = re.sub(r"'{2,}", "", t)
    t = re.sub(r"<br\s*/?>", "\n", t, flags=re.I)
    t = re.sub(r"</?[a-zA-Z][^>]*>", "", t)
    t = re.sub(r"〔[０-９0-9]+〕", "", t)  # footnote markers in Wikisource texts
    t = t.replace("&nbsp;", " ")

    lines, keep = [], not sections
    for line in t.split("\n"):
        m = re.match(r"^(={2,6})\s*(.*?)\s*\1\s*$", line)
        if m:
            level, title = len(m.group(1)), m.group(2)
            if sections and level <= stop_at_level:
                keep = title in sections
            if keep:
                lines.append("#" * (level - 1) + " " + title)
            continue
        if not keep:
            continue
        line = line.strip().lstrip("*#:;").strip()
        if line:
            lines.append(line)
    return "\n".join(lines).strip() + "\n"


def wikisource_body(wikitext: str, start_marker: str = "", drop_notes: bool = True) -> str:
    """Wikisource pages: drop the header template and the 注释 section; optionally start at a marker."""
    if drop_notes:
        wikitext = re.split(r"^==\s*(?:注释|注釋|註釋)\s*==", wikitext, flags=re.M)[0]
    text = wikitext_to_text(wikitext)
    if start_marker and start_marker in text:
        text = text[text.index(start_marker):]
    return text
