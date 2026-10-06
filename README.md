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
├── meta.json         人物信息：姓名、别名、生年/生月、简介、来源列表（文件、链接、许可、虚岁/周岁）
├── source/*.txt      来源文本。仅提交许可允许的（公有领域、CC BY-SA 等），其余已被 .gitignore
├── review.json       校订记录（提交这个）：剔除、合并、改年份、改摘要、校注，按条目指纹关联
├── chronology.json   生成物 = 转换结果 + review.json，不要手改
└── eval/gold.json    可选：关键事件“标准答案”，用于评测
```

```bash
# 1. 取材：从 Wikipedia / Wikisource 下载并清理，自动登记到 meta.json
python -m bio2chronology fetch people/lu-xun --site zh.wikipedia.org --title 鲁迅 --sections 生平 \
    --label 维基百科 --license "CC BY-SA 4.0"
#    也可以手动把 .txt 放进 source/，在 meta.json 的 sources 里登记

# 2. 转换（可反复执行，review.json 里的校订会自动套用）
python -m bio2chronology convert people/<slug>                                      # 离线规则引擎
ANTHROPIC_API_KEY=... python -m bio2chronology convert people/<slug> --engine llm   # 用 Claude

# 3. 评测（有 eval/gold.json 时）
python -m bio2chronology eval people/<slug>

# 4. 校订：写入 review.json
python -m bio2chronology review people/<slug>/chronology.json e0004 --year 1909 --note "据年谱改"
python -m bio2chronology review people/<slug>/chronology.json e0007 --status rejected   # 剔除，不上线
#    合并两份来源对同一件事的记述：在 review.json 里给该条加 {"merge_into": "<目标条目的 key>"}

# 5. 本地预览
python -m bio2chronology site serve          # http://127.0.0.1:8000

# 6. 提交 review.json、chronology.json，推送 main → GitHub Actions 自动构建并发布到 GitHub Pages
```

- 事件 `status`：`auto`（机器产出，网站上视为未校订）/ `confirmed`（已人工确认）/ `rejected`（不上线）。
- 重新转换后，如果某条校订对应的原句已经变了，`convert` 会提示有几条校订未能对应，请检查 `review.json`。
- 启用自动部署：仓库 Settings → Pages，Source 选 “GitHub Actions”（工作流见 `.github/workflows/pages.yml`）。

## 试点

[鲁迅试点报告](docs/pilot-lu-xun.md)：两份合法来源（Wikisource 上的自叙传略、维基百科），25 个关键节点中 23 个找到且年份正确；但机器产出的条目近一半需要人工处理。

## 转换器如何工作

章节解析 → 事件抽取（规则 / Claude）→ **模糊时间归一化** → 去重排序 → 分类与标签。

时间归一化是确定性、可审计的：支持 `同年秋`、`次年`、`第三年`、`三年后`、`数年后`、`暮春`、`光绪十九年`、`民国十二年`、`而立之年`、`三十岁`（需生年，按来源配置虚岁或周岁），繁简体皆可，并保持叙事上下文：

- 明确年份优先于相对时间，相对时间优先于年龄。
- 括号中的年份（生卒年、换算、注释）不参与定年。
- “28岁的朱安”这类他人的年龄不参与推算。
- “三年前”这类倒叙词不会拖动叙事位置。
- 没有时间词、但明显是事件的句子，沿用上文年份并标为“推断”。

LLM 引擎也只负责摘录原文时间表达，年份仍由这一步推算。

其他导出（Markdown/CSV/JSON/独立 HTML）：`python -m bio2chronology export people/<slug>/chronology.json -o out/`

## 已知局限

- 规则引擎人物/地点识别较粗、无指代消解；认真收录请用 `--engine llm` 并人工校订
- “数年”按 3 年估算；年龄按来源配置的虚岁或周岁推算；均已标注
- 年号支持乾隆至宣统及民国；干支纪年、更早的年号尚未支持
- 评论、引文类句子会被当成事件抽出，需要校订时剔除（见试点报告）
- 网站搜索不区分繁简
- 示例人物“沈砚秋”为虚构，仅用于演示

## 开发

零依赖，Python ≥ 3.9：`python -m unittest discover -s tests`
