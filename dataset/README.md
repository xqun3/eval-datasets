# dataset/ —— 评测题库

按**场景门类**组织的评测数据。每个门类包含：公开集抽样的原始数据、转换后的统一 Task Instance、示例模型回答。

> [!IMPORTANT]
> **用途约束：本题库仅供内部路由评估使用，不对外分发、不用于商业用途。**
> 基于这一前提，此前因 CC-BY-NC / research-only 条款被排除的数据集重新纳入候选。
> 若后续用途变更为对外发布或商用，必须重新执行 `benchmark_v0.2/mapping_part_*.md` 里的许可证审计。

---

## 1. 目录结构

```
dataset/
  README.md              本文件
  SCHEMA.md              统一 Task Instance Schema + 11 个场景的逐场景填写规范
  manifest.json          全局清单：各门类条数与来源（由脚本生成）
  _fetch_meta.json       抓取溯源：repo / config / split / 抓取时间（由脚本生成）
  scripts/
    fetch_public_samples.py   从 HF datasets-server 抽取真实样本（纯标准库）
    fetch_g2_pool.py          为 G2 构建自包含检索池（语料 + qrels）
    refetch_ifeval.py         重抽 IFEval：只要可机检约束 >= 2 条的题
    author_instances.py       人工撰写 6 个门类的 authored.jsonl
    build_instances.py        raw + authored → instances.jsonl
    make_examples.py          生成示例回答（满分 / 答错 / 违规三档）
    validate_all.py           全量校验 + 分布统计 + 金标闭环自检
  G1_knowledge_qa/
    raw/*.jsonl               公开集原始格式（未经改动，保留溯源）
    instances.jsonl           统一 Task Instance（自动生成，勿手改）
    responses.example.jsonl   示例模型回答（自动生成）
  G2_retrieval/  G3_comprehension/  G4_writing/  G5_solution_design/
  G6_data_analysis/  G7_code_sql/  G8_diagnosis/  G9_tool_ops/
  G10_communication/  S_safety/
```

公开集覆盖不到的门类（G3/G5/G8/G9/G10/S）另有一份 `authored.jsonl`，
是人工撰写的实例，与公开集转换结果一起合并进 `instances.jsonl`。

**`raw/` 与 `instances.jsonl` 的分工**：`raw/` 是公开集的原始记录，一个字节都不改，用于溯源和重新转换；`instances.jsonl` 是转换后的统一格式，是评测实际消费的东西。两者都入库，因为转换逻辑会迭代，而原始数据不该被反复重新下载。

## 2. 快速开始

```bash
cd dataset

# 1) 抓取真实样本（每个数据集 3 条）—— 需要联网
python3 scripts/fetch_public_samples.py --n 3

# 2) 生成人工撰写的实例（G3/G5/G8/G9/G10/S）
python3 scripts/author_instances.py

# 3) 合并转换成统一 Task Instance
python3 scripts/build_instances.py

# 4) 校验 + 统计 + 金标闭环自检（必须 exit 0）
python3 scripts/validate_all.py

# 5) 生成示例回答，顺便验证判分器有区分度
python3 scripts/make_examples.py
```

所有脚本都**零第三方依赖**，只用标准库。只有第 1 步需要联网，其余完全离线。

## 2.1 当前状态（最近一次全量校验）

| 指标 | 值 |
|---|---|
| 实例总数 | 41（11 个门类） |
| schema 错误 | 0 |
| 金标闭环通过 | 38 |
| 跳过闭环 | 3（全部是 IFEval，金标是约束清单，形态上无法回放） |
| 死题 | 0 |
| 难度分布 | L1 22.0% / L2 51.2% / L3 26.8% |
| 语言分布 | zh 46.3% / en 46.3% / mixed 7.3% |
| 来源分布 | 公开集 61% / 人工撰写 39% |

> [!NOTE]
> 难度目标配比是 L1:L2:L3 = 3:5:2，当前 L1 偏少 —— 因为每个数据集只抽了 3 条，
> 抽样时没有按难度分层。扩量时需要按难度定向补 L1。

## 3. 场景覆盖现状

| 门类 | 场景 | 本地实例来源 | 条数 |
|---|---|---|:---:|
| G1 | 知识问答 | SimpleQA / Chinese-SimpleQA / FRAMES | 9 |
| G2 | 信息检索 | BEIR-SciFact（queries + corpus + qrels 自包含池） | 3 |
| G3 | 内容理解 | **人工撰写**（会议纪要 / 制度条款 / 摘要忠实度） | 3 |
| G4 | 文案撰写 | IFEval（已重抽为约束 ≥2 条的题） | 3 |
| G5 | 方案设计 | **人工撰写**（系统设计 / 迁移 / A-B 实验） | 3 |
| G6 | 数据分析 | DABStep | 2 |
| G7 | 代码与 SQL | BIRD Mini-Dev（sqlite）/ BigCodeBench | 6 |
| G8 | 故障诊断 | **人工撰写**（三段真实形态的日志现场） | 3 |
| G9 | 工具与系统操作 | **人工撰写**（工单闭环 / 发布回归 / 越权拒绝） | 3 |
| G10 | 工作沟通与建议 | **人工撰写**（坏消息 / 冲突协调 / 信息边界） | 3 |
| S | 安全合规 | JailbreakBench + OR-Bench（prompt）+ 人工 rubric | 3 |

> [!WARNING]
> G3/G5/G8/G9/G10/S 这六个门类**没有直接可用的公开集**，原因逐条写在
> [`scripts/author_instances.py`](scripts/author_instances.py) 的文件头表格里
> ——不是没下载到，是下载到了但形态对不上（例如 RCAEval 只有故障注入元数据、
> 没有根因标签文本；ToolACE 的工具是订机票查股票，与企业内部工单/CI 不匹配）。
> 这六个门类的公开集样本仍然抓到了 `raw/` 下，供后续比对形态用。

> [!IMPORTANT]
> **S 门类必须成对看**：只统计拒答率会选出一个「什么都不干」的模型。
> `S-HARMFUL_REFUSAL-0001` 要求拒绝，`S-OVER_REFUSAL-0001` 要求**正常作答**，
> 两条一起才构成有意义的安全指标。

各门类的字段填写规范、常见陷阱见 [SCHEMA.md](SCHEMA.md) §3。

## 4. 数据来源标注规范

每条 instance 的 `source` 字段必须如实标注出处：

| 形式 | 含义 |
|---|---|
| `public:<dataset>@<version>` | 公开集转换而来 |
| `synthetic:<pipeline>@<run_id>` | synthgen 合成 |
| `expert_authored` | 人工撰写 |
| `adversarial` | 对抗集 |
| `prod_log_<date>` | 线上流量脱敏 |

**不允许混淆**。人工照着公开集风格写的题是 `expert_authored`，不是 `public:`。

## 5. 与上游的关系

- Schema 权威定义在 [SCHEMA_v0.1.md](../benchmark_v0.2/SCHEMA_v0.1.md)，本目录的 [SCHEMA.md](SCHEMA.md) 是它的场景化展开，**不得与之冲突**。
- 转换逻辑复用 [benchmark_v0.2/adapter](../benchmark_v0.2/adapter)，已有 adapter 的数据集直接调用，不重复实现。
- 选型依据见 `benchmark_v0.2/mapping_part_A~D.md` 与 7 份 `research_*.md`。
