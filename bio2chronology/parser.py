"""Chapter and sentence parsing."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

_NUM = r"[0-9零〇一二三四五六七八九十百]+"
HEADING = re.compile(
    rf"^\s*(?:#{{1,6}}\s+.+|第{_NUM}[章节回篇卷部]\s*.*|chapter\s+\d+.*|[一二三四五六七八九十]+[、．.]\s*\S.*)$",
    re.IGNORECASE,
)
_SENT_END = re.compile(r"(?<=[。！？!?])")


@dataclass
class Chapter:
    title: str
    paragraphs: list = field(default_factory=list)


def parse_chapters(text: str) -> list:
    """Split a biography into chapters; short lines matching a heading pattern start a new one."""
    chapters = [Chapter(title="（前言）")]
    for line in text.replace("\r\n", "\n").split("\n"):
        line = line.strip()
        if not line:
            continue
        if len(line) <= 40 and HEADING.match(line):
            chapters.append(Chapter(title=line.lstrip("# ").strip()))
        else:
            chapters[-1].paragraphs.append(line)
    chapters = [c for c in chapters if c.paragraphs]
    if len(chapters) == 1 and chapters[0].title == "（前言）":
        chapters[0].title = "全文"
    return chapters


def split_sentences(paragraph: str) -> list:
    return [s.strip() for s in _SENT_END.split(paragraph) if s.strip()]
