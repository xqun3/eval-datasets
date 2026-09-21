# 适配层（adapter/）设计文档 v0.1

> 配套代码：`adapter/`（可运行，Python 3.9 + 纯标准库）、`tests/`（191 个单测，全绿）、`README.md`（含真实运行输出）。
> 上游权威：`SCHEMA_v0.1.md`（冻结版）。**本文档不新增、不改名、不删除 Schema 任何字段**；所有 Schema 装不下的信息一律走 sidecar manifest。
> 数据集选型依据：`research_G1G3.md` / `research_G2.md` / `research_G4G5G10.md` / `research_G6G7.md` / `research_G8.md` / `research_G9.md` / `research_safety.md`。

---

## 1. 适配层总体架构

### 1.1 职责边界

**adapter 做什么**（只做这五件事）：

1. **读原始格式**：公开数据集的 jsonl / csv-转-jsonl / 多文件三元组（BEIR 的 corpus+queries+qrels）。
2. **字段映射**：原始字段 → `TaskInstance` 的 13 个规范字段。
3. **gold 构造**：把原始金标（SQL / 单测 / 短答案 / qrels / action 序列 / 约束列表）翻译成五形态之一。
4. **checker 绑定**：给每条样本指定一个已注册的 checker id，并保证 `checker.gold_types ∋ gold.type`（`run_check` 会再校验一次）。
5. **可溯源元数据落盘**：`source = public:<dataset>@<version>` 写进实例；许可证、原始 id、转换损失、人工待标注状态写进 sidecar manifest。

**adapter 不做什么**（越界即设计错误）：

- **不做判分**。adapter 只决定"用哪个 checker"，不实现判分逻辑。
- **不下载数据**。所有外部数据通过 `--in` / `--aux` 显式传入；adapter 进程不联网（这是硬约束，也是可复现性要求）。
- **不改写题面语义**。翻译、改中文口语、补上下文，属于「数据加工」阶段，不在 adapter 里做（会破坏 `source` 的可溯源承诺）。
- **不做人工标注**。缺的标注（FRAMES 的多跳拆点、DABStep 的口径）只**标记**出来进 manifest 的待标队列，绝不由代码"猜"一个填上。
- **不跑模型**。`fact_recall` / `rubric_judge` 里的 LLM 部分全部是可注入 stub，离线跑通全链路。
- **不做去重/采样策略决策**（除 BEIR 语料下采样这一项，因为它是"构造一条样本"的必要步骤，见 §2.5）。

### 1.2 目录与注册机制

```
adapter/
  __init__.py          # 公共门面：AdapterConfig / get_adapter / run_check / TaskInstance
  __main__.py          # python -m adapter
  cli.py               # convert / list / validate / stats / check
  schema.py            # TaskInstance + 校验 + CheckerResult 构造器（与 SCHEMA_v0.1.md 严格一致）
  registry.py          # 双注册表 + wrap_third_party
  base.py              # Adapter 基类 / AdapterConfig / 通用流水线 / canary / manifest
  checkers/            # 10 个内置 checker + run_check（全局前置钩子在这里串）
  adapters/            # 9 个 adapter（8 个数据集，SimpleQA 中英两个变体）
  fixtures/            # 每个 adapter 3-4 条仿真原始记录（含故意要被过滤掉的脏行）
  utils/               # io / text（NFKC、CJK 分词、代码块抽取）
```

注册全靠装饰器，没有隐式扫描：

```python
@register_adapter("bird_sql")
class BirdSqlAdapter(Adapter):
    dataset, version = "bird-sql-minidev", "v2-2024-06"
    category, gold_type, checker = "G7", "executable", "sql_result_equiv"

@register_checker("sql_result_equiv", layer="L1", gold_types=["executable"])
def sql_result_equiv(instance, response, env=None) -> CheckerResult: ...
```

`adapters/__init__.py` 与 `checkers/__init__.py` 里各有一行 `from . import xxx`——**新增一个 adapter = 新建一个模块 + 加一行 import**，注册表冲突会在 import 期直接抛错（同名重复注册 raise），不会静默覆盖。

### 1.3 统一 Adapter 接口

```python
def convert(self, raw_record: dict, cfg: AdapterConfig) -> TaskInstance | None
```

- 返回 `None` = **该条被过滤**（不是错误）。过滤计数进 `stats.filtered`，理由写在代码注释里（例：BIRD 的非 SELECT 语句、SimpleQA 的空题面、BEIR 的无正例 query、DABStep 的 `Not Applicable`、IFEval 的全部约束都无法翻译）。
- 抛异常 = **该条是错误**。`cfg.strict=True`（默认）直接向上抛；`--lenient` 时计入 `stats.errored` 并继续，错误串保留在 manifest 里。

`AdapterConfig` 字段：`dataset/version`（覆盖默认）、`split`、`lang`、`seq_start`、`limit`、`extra_must_not`、`difficulty_override`、`aux`（db 目录 / 语料 / qrels）、`options`（per-adapter 旋钮）、`canary_marker`、`strict`。

### 1.4 通用流水线

`Adapter.run()` 逐条驱动，`Adapter.build()` 统一执行公共步骤——**adapter 子类只负责「字段映射 + gold 构造」，其余九步全部在基类里**，所以不会出现"某个 adapter 忘了注入 must_not"这种事：

| # | 步骤 | 在哪 | 说明 |
|---|---|---|---|
| 1 | 加载 | `cli.convert` + `utils.io.read_jsonl` | `--in` 主文件，`--aux` 辅助 JSON（DDL 目录 / corpus / qrels） |
| 2 | 字段映射 | 子类 `convert()` | 唯一需要逐数据集写的部分 |
| 3 | gold 构造 | 子类 `convert()` | 见 §2 |
| 4 | checker 绑定 | 子类/基类默认值 | `run_check` 二次校验 gold_type 兼容性 |
| 5 | difficulty 推断 | 子类 `infer_difficulty()` | 见 §5；基类允许 `--difficulty` 全局覆盖 |
| 6 | lang 标注 | `base.detect_lang()` | CJK 字符占比：>0.5 → zh，<0.05 → en，其余 mixed |
| 7 | must_not 注入 | `base.build()` | `adapter.base_must_not` + 本条特有 + `cfg.extra_must_not`，去重保序 |
| 8 | canary 打标 | `base.build()` | `split=canary` 时把 canary 串追加进 prompt（§6.2） |
| 9 | id 生成 | `base.next_id()` | `<CATEGORY>-<SUBTYPE_SLUG>-<4位序号>`，adapter 内自增、全局唯一靠 `--seq-start` 分段 |
| 10 | schema 校验 | `base.build()` | **每条都校验**，不合规立即抛错（不允许写出脏数据再靠下游兜底） |
| 11 | 写出 | `cli.convert` | `out.jsonl` + `out.manifest.json` sidecar |

---

## 2. 五种 gold.type 的映射规则（核心）

### 2.0 总览

| gold.type | 典型原始集 | value 形状 | 判分层 | 机械转换比例 |
|---|---|---|---|---|
| `executable` | BIRD / Spider / BigCodeBench / HumanEval+ / LiveCodeBench | `{"tests":[...], "ref_solution":..., "timeout_s":...}` | L1 | **~100%**（金标本身就是可执行物） |
| `factlist` | SimpleQA / Chinese SimpleQA / FRAMES / 长文摘要 | `{"facts":[{id,text,required}], "ref_answer":...}` | L2 | 单事实题 ~100%；**多跳 0%（必须人工拆点）** |
| `rubric` | MT-Bench / AlignBench / WritingBench / IFEval | `{"dims":[{name,weight,anchors}], "must_cover":[...]}` | L3（IFEval 降级 L1） | **~0%**（5 维 rubric 公开集里根本不存在） |
| `trace` | τ²-bench / AppWorld / WorkBench / OfficeBench | `{"final_state":..., "valid_sequences":[...], "forbidden_calls":[...]}` | L1 | ~70%（状态断言能转，reward 语义会损失） |
| `reference` | BEIR / MTEB / RAG 集 / DABStep | `{"doc_ids":[...], "must_cite":[...], "value":...}` | L2/L1 | ~90%（qrels 直接转，但语料要下采样） |

### 2.1 `executable`

**谁映射到它**：金标本身是「可以跑起来、跑出结果就能判对错」的东西——SQL 语句、单元测试、参考实现。

**字段怎么填**

- SQL（BIRD / Spider）：
  ```json
  {"tests": [{"kind": "sql", "gold_sql": "<原始 SQL>",
              "order_sensitive": <原始 SQL 是否含 ORDER BY>,
              "column_order_sensitive": false}],
   "ref_solution": "<原始 SQL>", "timeout_s": 30}
  ```
  DB 不进实例正文：`context.db_schema = {dialect, ddl, snapshot_ref}`，`snapshot_ref` 是 `blob://sha256:...` 内容寻址指针。`ddl` 从 `.sqlite` 文件 dump（`.schema` + 抽样行）一次性生成 `--aux` 目录文件，不在转换时连库。
- 代码（BigCodeBench / HumanEval+）：
  ```json
  {"tests": [{"kind": "unittest", "code": "<原始 test 字段原文>", "name": "official"}],
   "ref_solution": "<canonical_solution>", "timeout_s": 30, "prelude": ""}
  ```
  单测代码**原样保留**，不重写——重写就等于换了一个 benchmark。

**典型转换难点**

1. **执行环境即金标的一部分**。BigCodeBench 官方要求固定版本 Docker（139 个库）；我方 `exec_tests` 只用当前解释器 + subprocess。库版本漂移 → 假失败。工程处理：`options.stdlib_only=True` 时**过滤掉依赖第三方库的题**（fixture 走这条路），真实接入时必须换成容器执行器；这一条写进了 adapter 的 `lossy_notes`，会出现在每份 manifest 里。
2. **SQL 等价 ≠ 字符串等价**。必须真跑（见 §4.2）。BIRD 的脏数据（NULL 泛滥、类型混用）会让"看起来等价"的两条 SQL 结果不同——这是 benchmark 的特性不是 bug，照单执行即可。
3. **非 SELECT 语句**。BIRD 里混有写操作题；我方 G7 的 must_not 明令禁写，所以直接过滤（`convert` 返回 `None`），不能留。
4. **timeout 是金标的一部分**，不是运行时参数：同一条题在不同机器上超时阈值不同会导致分数不可比，因此写进 `gold.value.timeout_s` 而不是 checker 配置。

### 2.2 `factlist` —— 难点最集中的一类

**谁映射到它**：G1 知识问答、G3 长文摘要/关键信息抽取。

**能机械转换的部分**（真的能，无需人工）：

- **单事实短答案题** → 单元素 facts 列表。SimpleQA / Chinese SimpleQA / TriviaQA 属于这一类：
  ```json
  {"facts": [{"id": "f1", "text": "Michio Sugeno", "required": true}],
   "ref_answer": "Michio Sugeno"}
  ```
  别名用 `|` 写进同一条 fact 的 text（`"刘慈欣|Liu Cixin"`），`fact_recall` 任一命中即算召回。
  **诚实说明**：这种转换下 FactRecall 的分母恒等于 1，**指标退化成 EM**，"事实点召回率"这个名字在这批题上是名不副实的。它的价值在于和多点题共用同一个 checker 和同一个分数刻度，不在于它本身有区分度。

**必须额外人工拆点的部分**：

- **FRAMES（多跳）**：原始集只给一个最终短答案 + 文章级 wiki 链接。我方要的"中间事实点清单"在数据里**不存在**，且**无法机械推导**。
  adapter 的处理（`adapters/frames.py`）：
  1. 最终答案 → 唯一的 `required: true` 事实；
  2. 每个 wiki 实体 → 一条 `required: false` 的**占位** fact（text = 实体名），给标注员一个具体锚点；
  3. manifest 里写 `needs_manual_annotation: true` / `annotation_state: "pending_fact_split"` / `hops: N`。
  **占位 fact 一律 optional，绝不进分母**——宁可分母小，也不能让一条没人写过的"事实点"混进指标。
  **人工成本（诚实估算）**：每题写 2-4 条 atomic fact，3-5 分钟/题 → **40-70 题/人日**。FRAMES 全量 824 条 ≈ 12-20 人日；按 research_G2.md 的建议只取 300 条 ≈ 5-7 人日。
- **长文摘要（QMSum / ELITR Minuting）**：原始金标是自由文本摘要，要转成"关键信息点清单"必须逐份人工拆。research_G1G3.md 已明确这两个集"需改造（人工把参考摘要拆成关键信息点清单）"，且 ELITR 是 CC BY-NC。**本版 adapter 未实现这两个集**——不是难，是没有人工标注就转出来没意义（见 §7 未做部分）。

**难点小结**：`factlist` 是唯一一个「原始集越贵、机械转换越无力」的形态。公开集给的是*答案*，我方要的是*答案的可验证分解*，这中间隔着人工。

### 2.3 `rubric`

**谁映射到它**：G4 文案撰写、G5 方案设计、G10 沟通建议、以及 IFEval 这类格式约束题。

**现实**：research_G4G5G10.md 的结论是——G4 数据可借 25-30%、G5 < 10-15%、G10 15-20%，而且**公开集里基本没有我方要的 instance-specific 5 维 rubric**。MT-Bench 是 8 个赛道的通用评分提示词，AlignBench 有维度但和我方维度对不齐，WritingBench 的 instance rubric 是模型生成的。

**策略（按可机器验证程度分三档）**：

| 档 | 原始集 | 做法 | 落到哪 |
|---|---|---|---|
| A. 可程序校验 | **IFEval / CFBench 的格式约束** | **降级到 L1**：约束翻译成 DSL，`checker=format_compliance` | 见下 |
| B. 有维度但需对齐 | AlignBench / WritingBench | 维度映射表（人工一次性写，逐 domain 复用）+ 每题的 `must_cover` 由人工补 | 未实现（见 §7） |
| C. 完全没有 | MT-Bench / 自建 G5 | rubric 全自建：领域模板 5 维 + 每题 `must_cover` 人工写 | 不在 adapter 范围（属 synthgen） |

**A 档的具体做法（已实现）**：Schema 的 5 种 gold 形态里没有"约束列表"，而 `rubric` 是唯一带 `must_cover` 的形态，所以：

- `gold.type = "rubric"`，`dims` 填一个 2 维骨架（仅为满足 Schema 的权重和=1 约束，**不参与判分**）；
- 每条可验证约束编码成 `must_cover` 里的一条 DSL 串：`ifeval:word_count_at_least:300`、`ifeval:no_commas:`、`ifeval:json_format:`……
- `checker = "format_compliance"`（**L1**），不是 `rubric_judge`（L3）。这直接落实 SCHEMA §3 的「能用 L1 判的绝不上 L3」。
- `must_cover` 里**不带 `ifeval:` 前缀的普通中文串**仍然是语义点，交给 `rubric_judge` 处理——两个 checker 共用同一个字段，互不干扰（`format_compliance` 把它们计入 `semantic_deferred`）。

**关键的诚实点**：IFEval 的 instruction_id 我方只翻译了 16 种。翻译不了的（如 `language:response_language`）**从 must_cover 里丢弃**并记入 manifest 的 `untranslated_constraints`，同时 `coverage_ratio` 记录翻译覆盖率。后果：**题面文字里的要求 > 判分覆盖的要求**，模型可能违反了一条我们没判的约束却拿满分。这个缺口无法在不改 Schema 的前提下消除，只能靠 manifest 暴露出来、靠人工补判分器收敛。

### 2.4 `trace`

**谁映射到它**：G9 工具与系统操作（τ²-bench / AppWorld / WorkBench / OfficeBench）。

**字段怎么填**（以 τ²-bench 为例，`adapters/tau2_bench.py`）：

| 原始 | 目标 | 规则 |
|---|---|---|
| `evaluation_criteria.env_assertions[*]` | `final_state[table] = expect` | 只 pin 断言涉及的表；未断言的表不比对（部分终态语义） |
| `evaluation_criteria.actions[*].name`（requestor=assistant） | `valid_sequences[0]` | 参考动作序列 |
| （人工/配置补充） | `valid_sequences[1..]` | `options.extra_sequences` 按 task id 追加其它合法路径 |
| `tools` 里**未出现在参考动作中的写操作工具** | `forbidden_calls` | 落实 SCHEMA §0 G9「越权/破坏性误调用 = 0」 |
| `evaluation_criteria.communicate_info` | `communicate_info` | 必须告知用户的字符串 |
| — | `ignore_fields` | 自增 id / 时间戳，默认由 `state_diff` 的正则兜底 |
| `initial_state` + `domain` | `context.env` | 环境初值，不进 gold |

**典型转换难点**

1. **只有 action list 没有 state assertion**。理论上可以"重放参考动作得到终态"，但重放需要真实环境——adapter 不联环境（硬约束）。处理：`final_state` 留空，manifest 标 `state_unverified: true`，该条实际上只靠序列 + communicate 判分。**不静默降级**是这里的关键：否则看上去"状态校验过了"，其实什么都没校验。
2. **reward 语义损失**。τ² 的 reward 是 `DB × COMMUNICATE × ACTION` 的**乘积门控** + `pass^k` 稳定性；我方 `state_diff` 压成 `0.7×状态 + 0.15×序列 + 0.15×communicate` 的加权和。乘积门控（任一项为 0 则总分 0）的语义丢了。补救：用 `registry.wrap_third_party` 接原生 reward（§4.4）。
3. **纯只读任务**（如 airline 的政策问答）没有状态变更也没有动作 → `convert` 返回 `None` 过滤掉：它形态上属于 G1/G3 而不是 G9。
4. **AppWorld 的 collateral damage 检查**（"有没有误改不该改的东西"）在 Schema 里没有对应字段。我方的近似：`state_diff` 只比对 gold pin 的表，**误改别的表不会被发现**。真正对齐需要在 `final_state` 里显式 pin 住"应当保持不变"的表——这是转换时的人工决策，本版未做（§7）。

### 2.5 `reference`

**谁映射到它**：G2 检索（BEIR / MTEB / T2Ranking / MultiHop-RAG）、G6 精确值问答（DABStep）。

**字段怎么填**

- 检索类：`doc_ids` = qrels 中 score>0 的文档；`graded` = 原始分级相关性（T2Ranking 的 0-3 天然适配 nDCG）；`must_cite` 仅在正例 ≤3 时填（多了就不该要求全引）；`value = null`。
- 精确值类（DABStep）：`doc_ids` = 引用的数据文件；`value` = 答案本身（数值保持数值，百分比转小数，其余留字面串）；`rel_tol/abs_tol` 随题走。

**大语料下采样（保 hard negatives）**——这是 `reference` 的核心工程问题。

BEIR SciFact 5,183 篇还能整包塞，T2Ranking / MLDR 的百万级语料不可能进 `context.kb_docs`。`adapters/beir.py` 的做法，每条 query 构造一个 pool：

1. **全部正例**（qrels score>0）——一条都不能丢，否则 Recall 的分母就错了；
2. **hard negatives**：用标准库实现的 BM25-lite（idf 加权 tf 归一化）对非正例打分，取 top-N（默认 20）；
3. **随机 filler**：用 query id 做种子的确定性随机补齐到 `pool_size`（默认 50）。

为什么必须保 hard negative：均匀随机负例会让任何检索器都轻松 Recall@5=1.0，**指标失去区分度**。
**诚实标注**：pool 内的 Recall@k 绝对值**高于**全量语料上的真实难度，只能横向比模型，不能和官方 leaderboard 数字对比。这一条写进 adapter 的 `lossy_notes`，每条样本的 manifest 行还记了 `downsampled_from`（原语料规模）、`pool_size`、`hard_negatives`、`fillers`。

**假文档率 = 0 的落实**：`doc_recall_at_k` 发现返回的 doc_id 不在 `context.kb_docs` 里，直接 score=0 + violation。research_G2.md 说"假文档这一失败模式没有专门的公开数据集，我方必须自建"——好消息正如它所说，这是个确定性检查，写在判分器里即可，不需要标注。

---

## 3. 逐数据集适配规格表

> 覆盖各门类首选集，共 14 个（其中 9 个**已实现代码 + fixture**，标 ✅；5 个为规格已定、代码未实现，标 ○，理由见 §7）。
> **「转换损失」列是本表最重要的一列。**

| # | 数据集 | 原始格式 | category | gold.type | checker | 字段映射要点 | difficulty 推断 | 需额外人工标注 | **转换损失 / 近似填充** |
|---|---|---|---|---|---|---|---|---|---|
| 1 ✅ | **BIRD-SQL (Mini-Dev)** | `{question_id, db_id, question, evidence, SQL, difficulty}` + `<db>.sqlite` | G7 | executable | `sql_result_equiv` | `SQL`→tests[0].gold_sql；DDL 从 aux 目录取进 `context.db_schema`；`evidence` 并入 prompt | JOIN 数 / 子查询深度 / 窗口函数 / CTE / GROUP BY | 无 | 原 difficulty 三档被结构启发式覆盖（原值存 manifest）；**VES 效率分不进 score**；33.4GB 全量库不入库，只存 DDL+snapshot_ref，**含大量真实行的"脏数据"特性在 fixture 上体现不出来**；非 SELECT 题被丢弃 |
| 2 ✅ | **BigCodeBench** | `{task_id, complete_prompt, instruct_prompt, canonical_solution, test, libs, entry_point}` | G7 | executable | `exec_tests` | 取 instruct 变体；`test` 原文进 tests[0].code | 第三方库数 / 测试用例数 / 参考解行数 | 无 | **丢弃 complete_prompt 变体**（少了一种评测模式）；官方要求固定版本 Docker，我方用本机解释器 → `stdlib_only` 过滤掉依赖第三方库的题，**真实接入前这批题的可比性存疑**；非安全沙箱 |
| 3 ✅ | **SimpleQA** | `{metadata(str dict), problem, answer}` | G1 | factlist | `fact_recall` | 单答案→单 required fact；alias 用 `\|` | answer_type + 题长 | 无 | **FactRecall 退化成 EM**（分母=1）；`metadata.urls` 证据链不进 kb_docs（不下载外部网页）→ 这批题只能闭卷，不能测引用可溯源 |
| 4 ✅ | **Chinese SimpleQA** | `{question, answer, primary_category}` | G1 | factlist | `fact_recall` | 同上；subtype 加 `_ZH` 后缀避免 id 撞车 | 同上 | 无 | 同上；6 大类 99 子类标签仅存 manifest，未进 subtype |
| 5 ✅ | **FRAMES** | `{Prompt, Answer, wiki_links(str list), reasoning_types}` | G1 | factlist | `fact_recall` | 最终答案→唯一 required fact；wiki 实体→optional 占位 fact + kb_docs 占位 | **跳数**（=wiki 实体数）+ 是否 temporal | **是：多跳中间事实点拆点，3-5 min/题，40-70 题/人日** | **中间事实点全缺**，占位 fact 不进分母 → 当前分数≈最终答案 EM，**测不出"推理链对不对"**；wiki_links 只到文章级，达不到 must_cite 的段落级金标要求 |
| 6 ✅ | **BEIR (SciFact 等小语料子集)** | corpus.jsonl + queries.jsonl + qrels.tsv | G2 | reference | `doc_recall_at_k` | queries 作主输入，corpus/qrels 走 `--aux`；正例→doc_ids，分级→graded | 正例数 + query↔正例词面 gap | 无（若要测引用还需段落级标注） | **语料下采样到 per-query pool（默认 50）** → Recall@k 绝对值偏高，**不能和官方 leaderboard 比**；BEIR 各子集许可证不一致（逐子集写进 manifest）；research_G2.md 警告：BEIR 是近四年 embedding 模型的调参目标，**分数只能横向比模型** |
| 7 ✅ | **DABStep** | `{task_id, question, guidance, level, answer, file_ids}` | G6 | reference | `numeric_em` | answer→`gold.value.value`（百分比转小数）；数据文件只存 path + blob ref | 原 level + 涉及文件数 | **是：口径中间步骤（分母定义/时间窗/过滤条件），~2 min/题** | `guidance` 的**严格格式判分降级为容差匹配**（小数位/千分位不再单独扣分）；`level` 原标签被启发式覆盖；G6 的「口径错误率」指标**当前无金标可判** |
| 8 ✅ | **τ²-bench** | `{id, description, user_scenario, initial_state, evaluation_criteria{actions, env_assertions, communicate_info, reward_basis}, tools}` | G9 | trace | `state_diff` | env_assertions→final_state；actions→valid_sequences[0]；未用到的写工具→forbidden_calls | **动作步数 + 写操作数** | 其它合法路径（`extra_sequences`）需人工补 | **乘积门控 reward 语义丢失**（压成加权和）、`pass^k` 稳定性丢失；**用户模拟器不在适配层内**，转出的题需配套环境才能真跑；无 env_assertion 的题 `state_unverified=true`（只判序列） |
| 9 ✅ | **IFEval** | `{key, prompt, instruction_id_list, kwargs}` | G4 | rubric | `format_compliance` | 约束→`must_cover` 里的 `ifeval:` DSL；dims 填 2 维骨架（不判分） | 同时生效的约束数 | 无（但需补语义维度才能做真 G4） | **只翻译了 16 种 instruction_id**，其余丢弃并记 `untranslated_constraints` → **题面要求 > 判分覆盖**；dims 是**近似填充的占位**，不代表真实 rubric |
| 10 ○ | **MultiHop-RAG** | `{query, answer, evidence_list[{title,url,fact}], question_type}` | G2 | reference | `citation_groundedness` | 609 篇语料整包进 kb_docs（无需下采样）；evidence→must_cite | 跳数 + 是否 null 类 | 段落级 → 句级引用需核对 | 英文新闻语体 ≠ 内部文档语体；null 类题的"拒答"判定需另写 checker |
| 11 ○ | **T2Ranking** | query/passage/qrel（4 级相关性） | G2 | reference | `doc_recall_at_k` | 分级相关性直接进 `graded`，nDCG 原生可用 | 正例数 + 分级分布 | 无 | 百万级语料**必须下采样**，同 #6 的偏差；中文模型常拿它做训练集 → 需逐模型核对训练配方 |
| 12 ○ | **AlignBench** | `{question, category, reference, 维度评分标准}` | G4/G5 | rubric | `rubric_judge` | 原维度→我方 5 维需**人工映射表**；`reference` 进 must_cover 需人工抽点 | 类目 + 题长 | **是：维度映射 + 每题 must_cover** | 原始维度与我方维度不同构，映射本身是近似；中文 |
| 13 ○ | **WorkBench** | 5 个沙箱 DB + 690 任务，金标为唯一终态 | G9 | trace | `state_diff` | 终态→final_state；outcome-centric 天然匹配"多路径都算过" | 工具调用步数 | 无 | 需要拉起它的 sandbox 才能得到终态快照；域是英文办公场景 |
| 14 ○ | **AIOpsLab / ITBench** | 交互式环境（K8s），48 / 35 个场景 | G8 | trace | `state_diff` | 场景定义→静态快照题 | 故障层级 + 涉及组件数 | **是：修复命令白名单 + 中文运维语境** | research_G8.md 结论：**没有任何公开集能直接满足 G8 的双字段金标**；必须拉起真实 K8s 才能跑 → 只能转成"静态快照题"，**丢掉交互性**，可覆盖比例仅 ~5% |

---

## 4. Checker 注册机制

### 4.1 注册表设计

```python
@dataclass
class CheckerSpec:
    id: str
    fn: Callable[[TaskInstance, ModelResponse, dict|None], CheckerResult]
    layer: str                  # L1 / L2 / L3  —— 统计"L1 占比 ≥40%"靠它
    gold_types: tuple[str,...]  # 支持的 gold.type，"*" 表示全部
    description: str
    third_party: str | None     # 非空 = 这是个外部判分器的 wrapper
    tags: list[str]
```

`registry.get_checker(id)` / `list_checkers()` / `checker_items()`；`spec.supports(gold_type)` 在 `run_check` 里做二次校验——**adapter 写错绑定会在判分时被挡住**，不会静默给 0 分或崩溃。

统一签名（所有 checker 无例外）：

```python
def checker(instance: TaskInstance, response: ModelResponse | dict | str,
            env: dict | None = None) -> CheckerResult
```

`env` 是唯一的注入口：LLM judge（`env["judge"]` / `env["fact_judge"]`）、k 值、容差、ignore_fields、DDL 覆盖。**没有全局配置、没有模块级单例**——这是能离线跑通全链路的前提。

### 4.2 内置 checker 清单

| id | layer | gold_types | 判定逻辑要点 |
|---|---|---|---|
| `must_not_guard` | L1 | **\*** | 全局前置钩子，见 §4.3 |
| `sql_result_equiv` | L1 | executable | **真跑 sqlite3**：`executescript(ddl)` 建内存库 → 跑 gold SQL 和预测 SQL → 结果集比对。行序：gold 含 ORDER BY 才敏感；列序：默认不敏感（行内单元格按类型稳定键排序）；重复行：用 `Counter` 多重集比对（3 行相同 ≠ 1 行）；浮点：量化到 `rel 1e-6 / abs 1e-9` 的容差网格后再比（这样容差能穿过多重集比较）；NULL：独立哨兵值，`NULL ≠ '' ≠ 0`，但 `NULL == NULL`；int/float 同值等价。超时用 `set_progress_handler` 的墙钟中断。预测 SQL 从 markdown 代码块里抽取 |
| `exec_tests` | L1 | executable | 候选代码 + 单测拼成一个文件，`subprocess` 跑，超时 kill。先 `compile()` 查语法（`syntax_ok` 子指标对应 SCHEMA §0 G7「语法合法率 ≥98%」）。**不是安全沙箱**（见 §7） |
| `fact_recall` | L2 | factlist | 规则匹配：NFKC 归一 + 去标点 + CJK 去空格（"是 2008 年" 命中 "2008年"）；`\|` 分隔别名任一命中即可；纯数值事实走容差匹配而非子串。score = 命中的 required / 全部 required，optional 只进子指标。`env["fact_judge"]` 可注入 LLM 判定，返回 `None` = 弃权并回落规则 |
| `doc_recall_at_k` | L2 | reference | Recall@k 为主分，nDCG@10 为子指标（用 graded relevance）。**返回不存在的 doc_id → score 直接 0 + violation**（G2「假文档率=0」） |
| `citation_groundedness` | L2 | reference, factlist | 0.5×must_cite 覆盖 + 0.5×引文可定位（引文 span 必须能在被引文档里 NFKC-归一后精确匹配）；任一伪造 doc_id → 0 |
| `numeric_em` | L1 | reference | 先抽 "Answer:/答案：" 行，否则取最后一行；千分位、货币符、百分号、中文万/亿单位归一；数值走 rel/abs 容差，列表逐项比，非数值走字面（支持 `\|` 备选 + 包含式回退） |
| `state_diff` | L1 | trace | 见 §2.4 与 §4.5 |
| `rubric_judge` | L3 | rubric | 加权 5 分制 → 归一到 [0,1]；**默认用离线确定性启发式 stub**，`sub_metrics.stub=True` + `detail.warning` 明示"这不是质量分"。`env["judge"]` 注入真 LLM。另提供 `pairwise_judge`：正反两序各判一次再取净差，落实 SCHEMA §3 的双向换位消偏 |
| `format_compliance` | L1 | rubric | 解析 `must_cover` 里的 `ifeval:<name>:<arg>`，17 个内置约束（词数/句数/JSON/无逗号/大小写/bullet 数/起止串/引号包裹/章节数/占位符数/无 markdown/含或不含关键词）。**不认识的 `ifeval:` 约束计入 `unsupported` 且不算通过**；无前缀的普通串计入 `semantic_deferred` 留给 L3 |

### 4.3 `must_not_guard` —— 全局前置钩子

**它不是"一个 checker"，是所有判分的前置门。** 唯一入口 `adapter.checkers.run_check(instance, response, checker_id=None, env=None)`：

```python
guard_res = must_not_guard(instance, response, env)
if guard_res["violations"]:
    return {**guard_res, "score": 0.0, "passed": False,
            "detail": {..., "short_circuit": True, "skipped_checker": <本该跑的 checker>}}
res = spec.fn(instance, response, env)          # 干净才跑真 checker
res["sub_metrics"]["must_not_fired"] = 0
```

命中即 **score=0 / passed=False / violations 写明是哪条规则**，并且**不再执行本该跑的 checker**（`skipped_checker` 记下它是谁）。单测 `test_run_check_short_circuits_before_real_checker` 证明：一条 SQL 既正确又 DROP 了表，最终仍然是 0 分。

**规则怎么从中文文本变成检测器**（Schema 里 must_not 是自由中文，如「泄露客户手机号」「执行 DROP」）——三级解析：

1. **精确命中** `RULE_LIBRARY` 的 key；
2. **关键词命中**：规则串里包含某条库目的触发词（"任何情况下都不要 drop 生产表" → 命中 drop 规则）；
3. **字面兜底**：把规则串本身当作归一化子串来匹配。

第 3 级触发时，规则名进 `sub_metrics.unresolved_rules`——**没人实现的规则是可见的**，而不是假装执行了。

内置检测器覆盖：CN 手机号、身份证、邮箱、银行卡、私网 IP、凭据键值；DROP / DELETE / TRUNCATE / 无 WHERE 的 UPDATE / ALTER / GRANT；`rm -rf` / mkfs / dd / killall / chmod 777 / shutdown；破坏性或越权的**工具调用**（读 `response.tool_calls`，越权 = 调了不在 `tools_available` 里的工具）；伪造文档 ID（引用了不在 `kb_docs` 里的 doc_id）。

检测面不止 `response.text`——`_response_surface()` 把 **tool_calls 的 name 与 arguments、final_state** 也拼进来，所以"把手机号塞进工具参数里"同样会被抓（有单测）。

**误报治理（实测踩到的坑）**：银行卡正则最初会把 18 位的分析结果 `0.024700000000000003` 判成卡号（它甚至碰巧通过了 Luhn 校验），导致一条正确的 G6 答案被清零。修法：正则加 `(?<![\d.])` 排除小数尾部 + 校验器要求 **Luhn 通过 AND 首位是 3-6（发卡行区间）**。这条有专门的回归测试。

### 4.4 第三方 checker 怎么接入

```python
registry.wrap_third_party(
    checker_id="bird_ves", layer="L1", gold_types=["executable"],
    inner=bird_official.evaluate,          # 返回外部自己的结构
    to_result=lambda raw: new_checker_result(score=raw["ves"], passed=raw["correct"], ...),
    third_party="BIRD-VES")
```

`inner` 可以返回任何东西，`to_result` 负责归一成 CheckerResult。注册之后与内置 checker 完全同构，上层分不出区别；`CheckerSpec.third_party` 字段留痕，方便统计"多少分是外部判分器给的"。

`checkers/sql_equiv.py` 里给了 **BIRD VES 的可跑示例**（`_ves_inner` + `_ves_to_result`，本地 sqlite 计时重算同一量，接口与真实集成一致），有两个单测。τ²-bench 的原生 reward 同理：`inner` 调它的 `reward_fn`，`to_result` 把乘积门控原样映射到 score——这正是 §2.4 里"找回乘积语义"的补救路径。

### 4.5 `state_diff` 的三个细节

- **忽略自增 id 与时间戳**：默认正则 `^(id|uuid|guid|rowid|ts|seq)$ | _id$ | _at$ | ^created | ^updated | ^modified | timestamp | ^etag$ | ^version$`，外加 `gold.value.ignore_fields` 与 `env["ignore_fields"]` 叠加。
- **多条合法路径**：`valid_sequences` 任一命中即可，且命中判定是**子序列**匹配——中间夹杂只读调用不算错。
- **只比对 gold pin 的表**：未在 `final_state` 里出现的表不参与比较（部分终态语义）。代价见 §2.4 难点 4。

---

## 5. difficulty 推断规则

**原则：启发式只是初值。** Schema 要求 L1:L2:L3 = 3:5:2，而"难"最终只能由**实测**定义。

| 门类 | 可程序化启发式（已实现） | 代码位置 |
|---|---|---|
| **G7-SQL** | JOIN 数 ≥3 / 子查询 ≥2 / 含窗口函数 / 含集合运算 / 含 CTE → **L3**；JOIN ≥1 或 子查询 ≥1 或 GROUP BY 或 HAVING → **L2**；其余 **L1** | `adapters/bird_sql.py::sql_complexity` |
| **G7-Code** | 第三方库 ≥3 或 测试用例 ≥6 或 参考解 ≥25 行 → L3；≥1 库 或 ≥3 用例 或 ≥10 行 → L2；否则 L1 | `bigcodebench.py` |
| **G1 单事实** | answer_type ∈ {number,date} → L2；题长 >160 → L3；{person,place,other} → L1 | `simpleqa.py` |
| **G1/G2 多跳** | **跳数**（wiki 实体数）≥4 或含 temporal → L3；≥2 → L2；否则 L1 | `frames.py` |
| **G2 检索** | 正例数 ≥3 或 query↔正例 BM25 分 <1.0（词面 gap 大）→ L3；正例=2 或 分 <4.0 → L2；否则 L1 | `beir.py` |
| **G6 分析** | 原 level=hard 或 涉及文件 ≥3 → L3；level=easy 且 ≤1 文件 → L1；其余 L2 | `dabstep.py` |
| **G9 工具** | **调用步数 ≥6 或 写操作数 ≥3** → L3；步数 ≥3 或 写 ≥1 → L2；否则 L1 | `tau2_bench.py` |
| **G4 格式** | 同时生效的约束数 ≥4 → L3；≥2 → L2；否则 L1 | `ifeval.py` |

### 启发式必须用基线模型实测通过率反标校正

结构复杂 ≠ 模型做不出来。三层 JOIN 的模板化查询对现代模型是送分题，而一个只有单表 WHERE 但口径刁钻的题可能全军覆没。因此**启发式标签只是 v0 初值**，正式流程是：

1. 用启发式出 v0 标签，转换产出可用；
2. 选 **3 个不同源基线模型**（避免 self-preference，对齐 SCHEMA §4.2 的同源回避原则），每题跑 k 次（默认 k=3，G7/G9 用 k=5），算平均通过率 p；
3. 反标规则：**p ≥ 0.8 → L1；0.4 ≤ p < 0.8 → L2；p < 0.4 → L3**；
4. 只有 v0 与实测**不一致**的条目才进人工复核队列（一致的直接采纳实测值），复核后把最终值写回，并在 manifest 的 `difficulty_origin` 从 `heuristic` 改成 `measured`（该字段已预留，见 `base.build()`）；
5. 全局配比不足 3:5:2 时，**补题而不是改标签**——改标签凑配比等于自欺。

`python3 -m adapter stats` 会直接打印当前 L1:L2:L3 实际比例与目标比例，便于每次转换后立刻看到偏差。

---

## 6. 污染与许可证的工程落地

**前提：Schema 冻结，不许加字段。** 所以全部走 `source` 串 + sidecar manifest。

### 6.1 许可证元数据放哪

- **实例内**：只有 `source = public:<dataset>@<version>`。它保证每条样本可溯源到"哪个数据集的哪个版本"——许可证是数据集级属性，有了 (dataset, version) 就能唯一定位。
- **sidecar manifest**（`<out>.manifest.json`，`convert` 自动生成）：

```jsonc
{
  "manifest_version": "0.1",
  "adapter": "bird_sql",
  "dataset": "bird-sql-minidev", "dataset_version": "v2-2024-06",
  "source": "public:bird-sql-minidev@v2-2024-06",
  "license": "CC BY-SA 4.0 (data); MIT (code)",
  "commercial_use": "conditional",        // yes | no | conditional | unknown
  "homepage": "https://bird-bench.github.io/",
  "category": "G7", "gold_type": "executable", "checker": "sql_result_equiv",
  "split": "dev", "canary_marker": null,
  "manual_annotation_required": null,
  "lossy_notes": "……转换损失的完整说明……",
  "stats": {"read": 4, "converted": 3, "filtered": 1, "errored": 0, "errors": []},
  "rows": [
    {"instance_id": "G7-SQL_QUERY-0001", "raw_id": "0",
     "license": "...", "commercial_use": "conditional",
     "difficulty_origin": "heuristic", "needs_manual_annotation": false,
     "db_id": "retail_mini", "orig_difficulty": "simple", "complexity": {...}}
  ]
}
```

`rows` 是**逐条**的：`instance_id ↔ raw_id` 的双向映射就是可溯源链路的最后一环（"这条题原本是 BIRD 的第几题"）。SCHEMA §4.1 要求"每个数据集必须标注许可证类型与是否可商用"——由 manifest 的 `license` / `commercial_use` 承载，且 `commercial_use` 的取值是闭集（有单测约束）。

发布前的合规动作：把所有 manifest 的 `commercial_use != "yes"` 的数据集聚合成一张清单交法务；`unknown` 在法务上等同"不可商用"（research_safety.md 的判定口径）。

### 6.2 canary 标记与 test/canary 隔离

- **canary 串**：`BENCHV01-CANARY-4f2a9c17-DO-NOT-TRAIN`（`base.CANARY_UUID`，可用 `cfg.canary_marker` 覆盖）。
- **打标时机**：`split == "canary"` 时，`base.build()` 把标记追加到 prompt 末尾。任何模型如果能复现这个串，就证明 canary 集进了它的训练语料。
- **隔离靠三件事**：
  1. `dev` / `test` / `canary` **分文件产出**（`--split` 一次只产一种），物理分开；
  2. manifest 里 `canary_marker` 字段非空即表示该文件是 canary，发布脚本据此拦截；
  3. `split` 是 Schema 内字段，`stats` 会打印分布，混入立刻可见。
- **不外泄的工程约定**（属发布流程，adapter 只提供钩子）：canary 与 test 的 gold 不随题面分发；对外只发 prompt 与 id；判分在内部服务侧做。

### 6.3 不改 Schema 的其它信息

同样走 manifest：原始难度标签、原始类目、跳数、pool 采样统计、未翻译的约束、待人工标注状态与类型、转换损失说明、错误样本列表。**规则：凡是"评测执行时不需要、但人要知道"的信息，一律 manifest。**

---

## 7. 已知局限与未做的部分（诚实清单）

1. **只实现了 9 个 adapter**（8 个数据集）。规格表里 #10-#14（MultiHop-RAG / T2Ranking / AlignBench / WorkBench / AIOpsLab）**只有规格没有代码**。未做的原因分别是：需要拉起外部 sandbox（WorkBench / AIOpsLab）、需要先有人工维度映射表（AlignBench）、与已实现的 BEIR 高度同构（T2Ranking / MultiHop-RAG，属边际收益低）。
2. **G3 / G5 / G8 / G10 / S 五个门类没有 adapter**。G3 长文摘要与 G5 方案设计的公开集都要先做人工拆点/rubric 才有意义；G8 按 research_G8.md 的结论公开集可覆盖率仅 15-20% 且需真实 K8s；S 类安全集（SORRY-Bench / AgentDojo / PrivacyLens）判分依赖 guard 模型，超出"纯标准库离线"的边界。这些是**有意不做**，不是遗漏。
3. **`exec_tests` 不是安全沙箱**。它只做超时 + 独立工作目录 + 精简环境变量，恶意代码可以读写文件系统。真实接入必须换容器。
4. **`rubric_judge` 的默认判定是 stub**，分数无质量含义（结果里 `stub=True` + warning 明示）。
5. **`fact_recall` 的默认判定是规则匹配**，同义改写（"八千八百四十八点八六米" vs "8848.86"）会漏判。真实评测必须注入 LLM judge 并按 research_G2.md 的建议做 10% 人工抽检校准。
6. **跨 adapter 的 id 全局唯一**靠 `--seq-start` 分段与 subtype 区分，不是靠中央发号器。`validate` 能查出重复（有单测），但需要把所有文件合并后再查。
7. **中文 subtype 的 slug**：Schema 的 id 只允许 `[A-Z0-9_]`，中文 subtype 会被映射成 `SUB_<hash6>`（除非登记在 `SUBTYPE_SLUG_ALIASES`）。可读性差，建议正式上线前把门类 subtype 字典补全。
8. **沙箱环境下 `.adapter_exec/` 的临时目录删不掉**（本机沙箱禁止删除），清理是 best-effort，残留目录无害但会累积。

---

## 附：与 SCHEMA_v0.1.md 的对齐自检

| Schema 要求 | 本适配层的落实 |
|---|---|
| 13 个字段、不得增删改名 | `schema.FIELD_ORDER` 固定；未知字段 / 缺字段都报错（单测覆盖） |
| id 格式 `<CATEGORY>-<SUBTYPE_SLUG>-<4位序号>` | `ID_RE` 强校验 + id 前缀必须等于 category |
| category 闭集 G1..G10 / S | 枚举校验，新增即报错 |
| gold 五形态 | 逐形态结构校验（rubric 权重和=1、must_cite ⊆ doc_ids、facts 有 id/text/required……） |
| source 五种写法 | 正则校验；本层产出恒为 `public:<dataset>@<version>` |
| CheckerResult 七键签名 | `new_checker_result()` 唯一构造入口 + `validate_checker_result()` |
| L1 占比 ≥40% | 9 个 adapter 里 6 个绑 L1 checker；`list` 子命令可查每个 checker 的 layer |
| 能用 L1 判的绝不上 L3 | IFEval 走 `format_compliance`(L1) 而非 `rubric_judge`(L3) |
| must_not 一票否决 | `run_check` 的全局前置钩子，命中即 0 且不跑后续 checker |
| pairwise 必须双向换位 | `rubric_judge.pairwise_judge` 正反各判一次取净差 |
| 许可证必须标注 | manifest 的 `license` / `commercial_use`（闭集取值） |
