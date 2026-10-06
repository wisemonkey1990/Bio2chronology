# 谱成 · Bio2Chronology

把一本人物传记，自动重构为一部按年编排、可溯源、可校订的人物年谱。

> Bio2Chronology is a tool that transforms a biography into a chronological biography. It extracts dated events, people, places, and works from the source text, resolves vague temporal expressions, and generates a traceable, editable chronology with citations.

它不替代研究者的判断，而是把几十万字的线性叙事，整理成可检索、可核查、可继续写作的时间骨架。

## 功能

- 传记文本导入与章节解析（`第X章`、`# 标题` 等）
- 时间、事件、人物、地点、作品抽取；事件分类（出生/教育/著述/任职/迁徙/交往/婚育/疾病/逝世）
- **模糊时间归一化**：`同年秋`、`次年`、`三年后`、`数年后`、`暮春`、`民国十二年`、`而立之年`、`三十岁`（需生年）→ 具体年份/月份；每条都附推理说明与置信度（`explicit / relative / inferred / approx / unresolved`）
- 事件去重（同期近似事件合并，保留全部出处）与排序
- 原文溯源：每条保留章节、段落与引文
- 人工校订：编辑 JSON 或用 `review` 命令；`rejected` 条目不会被导出
- 导出：Markdown、CSV（Excel 可直接打开）、JSON、可搜索/筛选的单文件时间轴网页

## 用法

零依赖，Python ≥ 3.9。

```bash
python -m bio2chronology build examples/sample_biography.txt --subject 沈砚秋 -o out/
# 可选：--birth-year 1895  --people 林远山,苏婉清  --formats md,html  --quotes

# 校订
python -m bio2chronology review out/chronology.json e0004 --year 1909 --note "据年谱改"
python -m bio2chronology review out/chronology.json e0007 --status rejected

# 校订后重新导出
python -m bio2chronology export out/chronology.json -o final/ --formats md,csv,html
```

输出示例：

```
## 1923年
- **3月** 民国十二年三月，沈砚秋北上抵达北平，任教于某大学 [任职]
- **暮春** 暮春，他与林远山重逢（推断） [交往]
- **冬** 同年冬，《寒夜集》付梓出版，……（据上下文推算） [著述]
```

## 抽取引擎

| 引擎 | 说明 |
|---|---|
| `rules`（默认） | 离线规则：按子句拆分、逐个时间锚点成事件。快、可复现，适合作为基线与测试 |
| `llm` | 用 Claude 抽取事件、人物、地点与作品，设置 `ANTHROPIC_API_KEY`，`--model` 可选。模型只摘录原文时间表达，**年份仍由同一个确定性的时间归一化器推算**，因此推理可审计 |

## 已知局限

- 规则引擎不做指代消解，人物/地点识别较粗；高质量抽取请用 `llm` 引擎。
- “数年”按 3 年估算；年龄默认按周岁推算（虚岁会差一年），均已标注，需人工核对。
- 倒叙/插叙靠“前一年”“三年前”等显式词处理，否则默认按叙述顺序推进。
- 历史纪年（年号、干支）尚未支持；目前支持公元与民国。

## 开发

```bash
python -m unittest discover -s tests
```
