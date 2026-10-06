"""Exporters: Markdown, CSV (Excel-friendly), JSON, standalone HTML timeline.
Events with status "rejected" are always omitted."""
from __future__ import annotations

import csv
import html
import io
import json
from itertools import groupby

from .models import Chronology

_CONF = {"explicit": "", "relative": "（据上下文推算）", "inferred": "（推断）",
         "approx": "（约）", "unresolved": ""}


def _live(chron: Chronology) -> list:
    return [e for e in chron.events if e.status != "rejected"]


def _when(e) -> str:
    return e.date_label().replace("年 ", "年 ")


def to_markdown(chron: Chronology, with_quotes: bool = False) -> str:
    out = [f"# {chron.subject or '传主'}年谱", ""]
    if chron.birth_year:
        out += [f"> 生年：{chron.birth_year}", ""]
    events = _live(chron)
    dated = [e for e in events if e.year is not None]
    for year, grp in groupby(dated, key=lambda e: e.year):
        out += [f"## {year}年", ""]
        for e in grp:
            sub = e.month and f"{e.month}月" or e.season or ""
            src = "；".join(f"{s.chapter}·第{s.paragraph}段" for s in e.sources)
            out.append(f"- {('**' + sub + '** ') if sub else ''}{e.summary}{_CONF[e.time_confidence]}"
                       f" `[{e.category}]` _[{src}]_")
            if e.note:
                out.append(f"  - 校注：{e.note}")
            if with_quotes:
                out += [f"  > {s.quote}" for s in e.sources if s.quote]
        out.append("")
    undated = [e for e in events if e.year is None]
    if undated:
        out += ["## 年份未定", ""]
        for e in undated:
            out.append(f"- {e.summary}（{e.time_raw or '无时间线索'}；{e.time_note}）")
    return "\n".join(out).rstrip() + "\n"


def to_csv(chron: Chronology) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["id", "年", "月", "季节", "原文时间", "置信度", "推理说明", "事件", "类别",
                "人物", "地点", "作品", "出处", "引文", "状态", "校注"])
    for e in _live(chron):
        w.writerow([e.id, e.year or "", e.month or "", e.season or "", e.time_raw,
                    e.time_confidence, e.time_note, e.summary, e.category,
                    "、".join(e.people), "、".join(e.places), "、".join(e.works),
                    "；".join(f"{s.chapter}·第{s.paragraph}段" for s in e.sources),
                    " ‖ ".join(s.quote for s in e.sources), e.status, e.note])
    return "﻿" + buf.getvalue()  # BOM so Excel opens UTF-8 correctly


def to_json(chron: Chronology) -> str:
    return json.dumps(chron.to_dict(), ensure_ascii=False, indent=2) + "\n"


_HTML = """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>__TITLE__年谱</title>
<style>
:root{--bg:#faf7f2;--fg:#2b2622;--mute:#8a8178;--line:#d8cfc2;--accent:#9c4a2f;--card:#fff}
@media(prefers-color-scheme:dark){:root{--bg:#1e1b18;--fg:#ece6dd;--mute:#9a9187;--line:#3a352f;--accent:#e08a66;--card:#27231f}}
body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.7 "Noto Serif SC","Songti SC",serif}
header,main{max-width:760px;margin:0 auto;padding:0 16px}
h1{margin:32px 0 4px}.sub{color:var(--mute);margin:0 0 16px}
.bar{position:sticky;top:0;background:var(--bg);padding:10px 0;display:flex;gap:8px;flex-wrap:wrap;border-bottom:1px solid var(--line)}
input{flex:1;min-width:140px;padding:6px 10px;border:1px solid var(--line);border-radius:6px;background:var(--card);color:var(--fg)}
.chip{padding:3px 10px;border:1px solid var(--line);border-radius:99px;cursor:pointer;background:var(--card);color:var(--fg);font:inherit;font-size:14px}
.chip.on{background:var(--accent);color:#fff;border-color:var(--accent)}
.year{margin:28px 0 8px;font-size:22px;color:var(--accent);border-bottom:1px solid var(--line)}
.ev{position:relative;margin:10px 0 10px 18px;padding:8px 12px;background:var(--card);border-left:3px solid var(--accent);border-radius:4px}
.when{font-weight:600;margin-right:6px}.tag{font-size:12px;color:var(--mute);margin-left:6px}
.meta{font-size:13px;color:var(--mute)}details summary{cursor:pointer;font-size:13px;color:var(--mute)}
blockquote{margin:6px 0;padding-left:10px;border-left:2px solid var(--line);color:var(--mute);font-size:14px}
.low .when::after{content:" ?";color:var(--accent)}
</style></head><body>
<header><h1>__TITLE__年谱</h1><p class="sub" id="sub"></p>
<div class="bar"><input id="q" placeholder="搜索事件、人物、地点…"><span id="chips"></span></div></header>
<main id="main"></main>
<script id="data" type="application/json">__DATA__</script>
<script>
const D=JSON.parse(document.getElementById('data').textContent);
const evs=D.events.filter(e=>e.status!=='rejected');
const cats=[...new Set(evs.map(e=>e.category))];let cat=null,q='';
const esc=s=>String(s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
document.getElementById('sub').textContent=(D.birth_year?'生于'+D.birth_year+' · ':'')+evs.length+' 条事件';
function chips(){const el=document.getElementById('chips');el.innerHTML='';
 ['全部',...cats].forEach(c=>{const b=document.createElement('button');b.className='chip'+((c==='全部'?cat===null:cat===c)?' on':'');
  b.textContent=c;b.onclick=()=>{cat=c==='全部'?null:c;chips();draw()};el.appendChild(b)})}
function draw(){let last=null,h='';
 for(const e of evs){
  if(cat&&e.category!==cat)continue;
  const hay=[e.summary,...e.people,...e.places,...e.works].join(' ');
  if(q&&!hay.includes(q))continue;
  const y=e.year==null?'年份未定':e.year+'年';
  if(y!==last){h+='<div class="year">'+esc(y)+'</div>';last=y}
  const sub=e.month?e.month+'月':(e.season||'');
  const low=['inferred','approx','unresolved'].includes(e.time_confidence)?' low':'';
  const meta=[...e.people.map(p=>'👤'+p),...e.places.map(p=>'📍'+p),...e.works.map(p=>'《'+p+'》')].join('  ');
  h+='<div class="ev'+low+'"><span class="when">'+esc(sub)+'</span>'+esc(e.summary)+'<span class="tag">'+esc(e.category)+'</span>'
   +(meta?'<div class="meta">'+esc(meta)+'</div>':'')
   +'<details><summary>出处'+(e.time_note?' · '+esc(e.time_note):'')+'</summary>'
   +e.sources.map(s=>'<blockquote>'+esc(s.quote)+'<br><span class="meta">'+esc(s.chapter)+' · 第'+s.paragraph+'段</span></blockquote>').join('')
   +'</details></div>'}
 document.getElementById('main').innerHTML=h||'<p class="sub">没有匹配的事件。</p>'}
document.getElementById('q').oninput=e=>{q=e.target.value.trim();draw()};
chips();draw();
</script></body></html>
"""


def to_html(chron: Chronology) -> str:
    data = json.dumps(chron.to_dict(), ensure_ascii=False).replace("</", "<\\/")
    return _HTML.replace("__TITLE__", html.escape(chron.subject or "传主")).replace("__DATA__", data)


EXPORTERS = {"md": ("md", to_markdown), "csv": ("csv", to_csv),
             "json": ("json", to_json), "html": ("html", to_html)}
