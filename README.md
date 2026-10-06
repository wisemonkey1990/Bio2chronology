# 谱成 · Bio2Chronology

**人物年谱网站**：把一本本人物传记整理成按年编排、可溯源、可校订的年谱，供人浏览、搜索与核查。

> Bio2Chronology is a website of chronological biographies. Each chronology is derived from a biography: dated events, people, places and works are extracted, vague time expressions ("同年秋", "而立之年") are resolved, and every entry keeps its citation.

网站是产品本身；“传记 → 年谱”的转换只是内容生产的**离线管线**，在本地运行（或接入 CI），产物是提交进仓库的数据文件。

## 网站功能

- **人物馆**：人物卡片；全站搜索人物、事件、地点、作品，结果可直达某一条
- **人物年谱页**：按年分组的时间线，显示传主当年岁数；事件密度条可点击跳转；按类别筛选；页内搜索；点击人物/地点/作品标签即按其过滤；“仅已校订”开关
- **可溯源**：每条事件可展开原文引文与章节段落；年份是推算得来的会标注“据上下文推算 / 推断 / 约”，并写明推理依据
- 事件可分享链接：`#/p/<人物>/<事件id>`
- 纯静态站点（原生 JS，无框架、无构建工具），亮/暗色自适应，手机可用

## 内容生产流程

```
people/<slug>/
├── meta.json            人物信息：姓名、生年、简介、依据的传记…
├── source/biography.txt 传记原文（仅本地，已被 .gitignore；版权材料不要提交）
└── chronology.json      转换产物 + 人工校订（提交这个）
```

```bash
# 1. 放好 meta.json 和 source/biography.txt，然后转换
python -m bio2chronology convert people/<slug>                                      # 离线规则引擎
ANTHROPIC_API_KEY=... python -m bio2chronology convert people/<slug> --engine llm   # 用 Claude，质量更高

# 2. 校订：直接编辑 chronology.json，或用命令行
python -m bio2chronology review people/<slug>/chronology.json e0004 --year 1909 --note "据年谱改"
python -m bio2chronology review people/<slug>/chronology.json e0007 --status rejected   # 剔除，不上线

# 3. 本地预览
python -m bio2chronology site serve          # http://127.0.0.1:8000

# 4. 提交 chronology.json 并推送 main → GitHub Actions 自动构建并发布到 GitHub Pages
```

- `convert` 不会覆盖已有的 `chronology.json`（以免丢失人工校订），需要重来请加 `--force`。
- 事件 `status`：`auto`（机器产出，网站上视为未校订）/ `confirmed`（已校订）/ `rejected`（不上线）。
- 启用自动部署：仓库 Settings → Pages，Source 选 “GitHub Actions”（工作流见 `.github/workflows/pages.yml`）。

## 转换器如何工作

章节解析 → 事件抽取（规则 / Claude）→ **模糊时间归一化** → 去重排序 → 分类与标签。

时间归一化是确定性、可审计的：支持 `同年秋`、`次年`、`三年后`、`数年后`、`暮春`、`民国十二年`、`而立之年`、`三十岁`（需生年），并保持叙事上下文；“三年前”这类倒叙词不会拖动叙事位置。LLM 引擎也只负责摘录原文时间表达，年份仍由这一步推算。

其他导出（Markdown/CSV/JSON/独立 HTML）：`python -m bio2chronology export people/<slug>/chronology.json -o out/`

## 已知局限

- 规则引擎人物/地点识别较粗、无指代消解；认真收录请用 `--engine llm` 并人工校订
- “数年”按 3 年估算；年龄按周岁推算（虚岁差一年）；均已标注
- 暂不支持年号、干支纪年（目前支持公元与民国）
- 示例人物“沈砚秋”为虚构，仅用于演示

## 开发

零依赖，Python ≥ 3.9：`python -m unittest discover -s tests`
