from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Optional

SEASON_START = {"春": 3, "夏": 6, "秋": 9, "冬": 12}


@dataclass
class Source:
    chapter: str
    paragraph: int  # 1-based paragraph index within the chapter
    quote: str


@dataclass
class Event:
    id: str = ""
    year: Optional[int] = None
    month: Optional[int] = None
    season: Optional[str] = None  # e.g. "秋", "暮春"
    time_raw: str = ""  # time expression as written in the source
    time_confidence: str = "explicit"  # explicit | relative | inferred | approx | unresolved
    time_note: str = ""  # how the date was derived
    summary: str = ""
    category: str = "其他"
    people: list = field(default_factory=list)
    places: list = field(default_factory=list)
    works: list = field(default_factory=list)
    sources: list = field(default_factory=list)  # list[Source]
    status: str = "auto"  # auto | confirmed | rejected
    note: str = ""  # reviewer's note

    def date_label(self) -> str:
        if self.year is None:
            return "年份未定"
        label = f"{self.year}年"
        if self.month:
            label += f" {self.month}月"
        elif self.season:
            label += f" {self.season}"
        return label

    def sort_key(self):
        m = self.month
        if m is None and self.season:
            m = SEASON_START.get(self.season[-1], 0)
        return (self.year if self.year is not None else 10**6, m or 0)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Event":
        d = dict(d)
        d["sources"] = [Source(**s) if isinstance(s, dict) else s for s in d.get("sources", [])]
        known = {k: v for k, v in d.items() if k in cls.__dataclass_fields__}
        return cls(**known)


@dataclass
class Chronology:
    subject: str = ""
    birth_year: Optional[int] = None
    events: list = field(default_factory=list)  # list[Event]

    def to_dict(self) -> dict:
        return {
            "subject": self.subject,
            "birth_year": self.birth_year,
            "events": [e.to_dict() for e in self.events],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Chronology":
        return cls(
            subject=d.get("subject", ""),
            birth_year=d.get("birth_year"),
            events=[Event.from_dict(e) for e in d.get("events", [])],
        )
