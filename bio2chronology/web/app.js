"use strict";
const COLORS = {出生: "#b5651d", 教育: "#3b7dd8", 著述: "#7a4fc2", 任职: "#2f8f6b", 迁徙: "#c28a1f",
  交往: "#d1498a", 婚育: "#d9534f", 疾病: "#6c7a89", 逝世: "#444", 其他: "#999"};
const app = document.getElementById("app");
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
const cache = {};
const getJSON = p => cache[p] ||= fetch(p).then(r => { if (!r.ok) throw new Error(p); return r.json(); });
const lifespan = p => p.birth_year || p.death_year ? `${p.birth_year ?? "?"} – ${p.death_year ?? "?"}` : "";
const timeLabel = e => e.month ? e.month + "月" : (e.season || "");
const debounce = (f, ms = 180) => { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => f(...a), ms); }; };

async function route() {
  const [, kind, slug, eid] = location.hash.slice(1).split("/");
  try {
    if (kind === "p" && slug) await personPage(slug, eid); else await home();
  } catch (err) {
    app.innerHTML = '<p class="empty">加载失败。请通过 HTTP 访问（如 <code>bio2chronology site serve</code>），而不是直接打开本地文件。</p>';
  }
}

/* ---------- home ---------- */
async function home() {
  document.title = "谱成 · 人物年谱";
  const idx = await getJSON("data/index.json");
  app.innerHTML = `<h1>人物年谱</h1>
    <p class="lede">把传记里线性的叙事，整理成按年编排、可溯源的时间骨架。</p>
    <input type="search" id="q" placeholder="搜索人物，或搜索事件、地点、作品…" aria-label="搜索">
    <div id="out"></div>`;
  const out = document.getElementById("out");
  const cards = () => out.innerHTML = `<div class="grid">${idx.people.map(p => `
    <a class="card" href="#/p/${esc(p.slug)}">
      <h2>${esc(p.name)}${p.fictional ? '<span class="badge">虚构示例</span>' : ""}</h2>
      <div class="yrs">${esc(lifespan(p))}</div>
      <p>${esc(p.summary)}</p>
      <span class="n">${p.count} 条事件 · ${p.confirmed} 条已校订</span>
    </a>`).join("") || '<p class="empty">还没有收录任何人物。</p>'}</div>`;
  cards();
  document.getElementById("q").addEventListener("input", debounce(async ev => {
    const q = ev.target.value.trim();
    if (!q) return cards();
    const all = await Promise.all(idx.people.map(p => getJSON(`data/${p.slug}.json`)));
    const hits = [];
    for (const p of all) {
      if (p.name.includes(q) || (p.aliases || []).some(a => a.includes(q)))
        hits.push(`<a class="hit" href="#/p/${esc(p.slug)}"><small>人物</small>${esc(p.name)} <span class="cite">${esc(lifespan(p))}</span></a>`);
      for (const e of p.events)
        if ([e.summary, ...e.people, ...e.places, ...e.works].some(s => s.includes(q)))
          hits.push(`<a class="hit" href="#/p/${esc(p.slug)}/${e.id}"><small>${esc(p.name)} · ${e.year ?? "年份未定"}${e.year ? "年 " + esc(timeLabel(e)) : ""}</small>${esc(e.summary)}</a>`);
    }
    out.innerHTML = hits.join("") || '<p class="empty">没有找到匹配的内容。</p>';
  }));
}

/* ---------- person ---------- */
async function personPage(slug, focusId) {
  const p = await getJSON(`data/${slug}.json`);
  document.title = `${p.name}年谱 · 谱成`;
  const cats = [...new Set(p.events.map(e => e.category))];
  const state = {cat: new Set(), q: "", confirmedOnly: false};
  const years = p.events.filter(e => e.year != null).map(e => e.year);
  const [y0, y1] = [Math.min(...years), Math.max(...years)];
  const counts = {};
  years.forEach(y => counts[y] = (counts[y] || 0) + 1);
  const peak = Math.max(1, ...Object.values(counts));
  const strip = years.length ? Array.from({length: y1 - y0 + 1}, (_, i) => y0 + i).map(y =>
    `<button data-y="${y}" style="height:${counts[y] ? 12 + 88 * counts[y] / peak : 0}%" title="${y}年 · ${counts[y] || 0} 条" aria-label="跳到${y}年"></button>`).join("") : "";
  const confirmed = p.events.filter(e => e.status === "confirmed").length;

  app.innerHTML = `<a class="back" href="#/">← 全部人物</a>
    <h1>${esc(p.name)}${p.fictional ? '<span class="badge">虚构示例</span>' : ""}</h1>
    <div class="cite">${esc(lifespan(p))}</div>
    <p class="lede">${esc(p.summary)}</p>
    <div class="stats"><span>${p.events.length} 条事件</span><span>${confirmed} 条已人工校订</span>
      ${p.source ? `<span>据：${esc(p.source)}</span>` : ""}</div>
    <div class="strip">${strip}</div>
    <div class="strip-axis"><span>${years.length ? y0 : ""}</span><span>事件密度（点击跳转）</span><span>${years.length ? y1 : ""}</span></div>
    <div class="bar"><input type="search" id="q" placeholder="在 ${esc(p.name)} 的年谱中搜索…" aria-label="搜索">
      <div class="chips" id="chips"></div></div>
    <div id="tl"></div>`;

  const chips = document.getElementById("chips");
  const drawChips = () => chips.innerHTML = cats.map(c =>
    `<button class="chip${state.cat.has(c) ? " on" : ""}" data-c="${esc(c)}"><i style="background:${COLORS[c] || COLORS.其他}"></i>${esc(c)}</button>`).join("")
    + `<button class="chip${state.confirmedOnly ? " on" : ""}" data-confirmed="1">仅已校订</button>`;
  const match = e => (!state.cat.size || state.cat.has(e.category)) && (!state.confirmedOnly || e.status === "confirmed")
    && (!state.q || [e.summary, e.note || "", ...e.people, ...e.places, ...e.works].some(s => s.includes(state.q)));

  const eventHTML = e => {
    const age = e.year != null && p.birth_year != null && e.year >= p.birth_year ? `${e.year - p.birth_year}岁` : "";
    const guess = {relative: "据上下文推算", inferred: "推断", approx: "约", unresolved: "年份未定"}[e.time_confidence];
    const chipsHTML = [...e.people.map(v => ["👤", v]), ...e.places.map(v => ["📍", v]), ...e.works.map(v => ["《》", v])]
      .map(([i, v]) => `<button data-q="${esc(v)}">${i === "《》" ? `《${esc(v)}》` : i + " " + esc(v)}</button>`).join("");
    return `<article class="ev" id="ev-${e.id}" style="--c:${COLORS[e.category] || COLORS.其他}">
      <span class="when">${esc(timeLabel(e))}</span>${esc(e.summary)}
      <span class="tag">${esc(e.category)}</span>${guess ? `<span class="tag guess">${guess}</span>` : ""}
      ${e.status === "confirmed" ? '<span class="tag">✓ 已校订</span>' : ""}${age ? `<span class="tag">${age}</span>` : ""}
      ${chipsHTML ? `<div class="meta">${chipsHTML}</div>` : ""}
      ${e.note ? `<div class="note">校注：${esc(e.note)}</div>` : ""}
      <details><summary>原文出处${e.time_note ? " · " + esc(e.time_note) : ""}</summary>
        ${e.sources.map(s => `<blockquote>${esc(s.quote)}<cite>${esc(s.chapter)} · 第${s.paragraph}段</cite></blockquote>`).join("")}
      </details></article>`;
  };
  const drawTimeline = () => {
    const list = p.events.filter(match);
    let html = "", last;
    for (const e of list) {
      const key = e.year ?? "undated";
      if (key !== last) {
        const n = list.filter(x => (x.year ?? "undated") === key).length;
        html += `<div class="year" id="y-${key}"><b>${key === "undated" ? "年份未定" : key + "年"}</b><small>${key !== "undated" && p.birth_year != null && key >= p.birth_year ? key - p.birth_year + "岁 · " : ""}${n} 条</small></div>`;
        last = key;
      }
      html += eventHTML(e);
    }
    document.getElementById("tl").innerHTML = html || '<p class="empty">没有匹配的事件。</p>';
  };
  drawChips(); drawTimeline();

  const qbox = document.getElementById("q");
  qbox.addEventListener("input", debounce(() => { state.q = qbox.value.trim(); drawTimeline(); }));
  chips.addEventListener("click", ev => {
    const b = ev.target.closest("button"); if (!b) return;
    if (b.dataset.confirmed) state.confirmedOnly = !state.confirmedOnly;
    else state.cat.has(b.dataset.c) ? state.cat.delete(b.dataset.c) : state.cat.add(b.dataset.c);
    drawChips(); drawTimeline();
  });
  document.getElementById("tl").addEventListener("click", ev => {
    const b = ev.target.closest(".meta button"); if (!b) return;
    qbox.value = state.q = b.dataset.q; drawTimeline(); qbox.scrollIntoView({block: "center"});
  });
  document.querySelector(".strip").addEventListener("click", ev => {
    const b = ev.target.closest("button"); if (!b) return;
    document.getElementById("y-" + b.dataset.y)?.scrollIntoView();
  });
  if (focusId) {
    const el = document.getElementById("ev-" + focusId);
    if (el) { el.scrollIntoView({block: "center"}); el.classList.add("hl"); el.querySelector("details").open = true; }
  }
}

addEventListener("hashchange", route);
route();
