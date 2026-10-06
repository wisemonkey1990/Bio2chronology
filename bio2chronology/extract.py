"""Event extractors. Each yields `RawEvent`s in narrative order; the pipeline
resolves their time expressions with a shared, stateful `TimeResolver`."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable, Optional

from .classify import classify, find_people, find_places, find_works
from .parser import Chapter, split_sentences
from .timeexpr import scan

_CLAUSE_SPLIT = re.compile(r"(?<=[，,；;])")


@dataclass
class RawEvent:
    time_text: str  # text the resolver scans for time expressions
    summary: str
    quote: str  # source sentence(s)
    paragraph: int
    category: Optional[str] = None
    people: list = field(default_factory=list)
    places: list = field(default_factory=list)
    works: list = field(default_factory=list)


def _clean(summary: str) -> str:
    return summary.strip("，,；;。 　")


class RuleExtractor:
    """Offline baseline: every clause group that carries a time expression becomes an event."""

    def __init__(self, known_people: Iterable[str] = ()):
        self.known_people = list(known_people)

    def extract(self, chapter: Chapter) -> list:
        events = []
        for pi, para in enumerate(chapter.paragraphs, 1):
            for sentence in split_sentences(para):
                for group in self._groups(sentence):
                    refs = scan(group)
                    if not refs:
                        continue
                    events.append(RawEvent(
                        time_text=group, summary=_clean(group), quote=sentence, paragraph=pi,
                        category=classify(group),
                        people=find_people(group, self.known_people),
                        places=find_places(group), works=find_works(group)))
        return events

    @staticmethod
    def _groups(sentence: str) -> list:
        """Split a sentence into clause groups, one per time anchor.
        "1918年入学，1922年毕业" → two groups; "1918年，考入某校" → one."""
        groups, prefix = [], ""
        for clause in _CLAUSE_SPLIT.split(sentence):
            if not clause:
                continue
            if scan(clause):
                groups.append(prefix + clause)
                prefix = ""
            elif groups:
                groups[-1] += clause
            else:
                prefix += clause
        if prefix and groups:
            groups[-1] += prefix
        return groups


LLM_PROMPT = """你是史料整理助手。下面是一部传记的一章，请抽取传主生平中的重要事件。
只输出 JSON 数组，按原文叙述顺序排列，每个元素字段如下：
- time_expr: 原文中的时间表达，逐字摘录（如“同年秋”“而立之年”“暮春”）；原文无时间线索则为空字符串
- summary: 一句话事件概述（不含时间词）
- quote: 支撑该事件的原文引文，逐字摘录
- category: 出生/逝世/婚育/著述/教育/任职/迁徙/交往/疾病/其他 之一
- people: 涉及的人名数组
- places: 涉及的地名数组
- works: 涉及的作品名数组（不含书名号）
- paragraph: 引文所在段落序号（从1开始）
不要自行推算年份，只摘录原文时间表达。

传主：{subject}

章节《{title}》：
{body}
"""


class LLMExtractor:
    """Claude-backed extractor. `complete(prompt) -> str` is injectable for tests."""

    def __init__(self, subject: str = "", complete=None, model: str = "claude-sonnet-5-5",
                 max_chars: int = 6000):
        self.subject = subject
        self.model = model
        self.max_chars = max_chars
        self.complete = complete or self._anthropic_complete

    def extract(self, chapter: Chapter) -> list:
        out = []
        for offset, paras in self._chunks(chapter):
            body = "\n".join(f"[{offset + i}] {p}" for i, p in enumerate(paras, 1))
            prompt = LLM_PROMPT.format(subject=self.subject or "（未指定）", title=chapter.title, body=body)
            out.extend(self._parse(self.complete(prompt)))
        return out

    def _chunks(self, chapter: Chapter):
        buf, size, start = [], 0, 0
        for i, p in enumerate(chapter.paragraphs):
            if buf and size + len(p) > self.max_chars:
                yield start, buf
                buf, size, start = [], 0, i
            buf.append(p)
            size += len(p)
        if buf:
            yield start, buf

    @staticmethod
    def _parse(reply: str) -> list:
        import json
        a, b = reply.find("["), reply.rfind("]")
        if a < 0 or b < a:
            return []
        try:
            items = json.loads(reply[a:b + 1])
        except json.JSONDecodeError:
            return []
        events = []
        for it in items:
            if not isinstance(it, dict) or not it.get("summary"):
                continue
            events.append(RawEvent(
                time_text=it.get("time_expr") or "", summary=it["summary"],
                quote=it.get("quote") or "", paragraph=int(it.get("paragraph") or 0),
                category=it.get("category") or None, people=list(it.get("people") or []),
                places=list(it.get("places") or []), works=list(it.get("works") or [])))
        return events

    def _anthropic_complete(self, prompt: str) -> str:
        import json, os, urllib.request
        key = os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise RuntimeError("使用 --engine llm 需要设置环境变量 ANTHROPIC_API_KEY")
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=json.dumps({"model": self.model, "max_tokens": 8000,
                             "messages": [{"role": "user", "content": prompt}]}).encode(),
            headers={"x-api-key": key, "anthropic-version": "2023-06-01",
                     "content-type": "application/json"})
        with urllib.request.urlopen(req, timeout=300) as resp:
            data = json.load(resp)
        return "".join(b.get("text", "") for b in data.get("content", []))
