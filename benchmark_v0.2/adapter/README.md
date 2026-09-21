# adapter/ —— 公开 benchmark → 统一 Task Instance Schema 适配层

把公开 benchmark 的原始格式转换成 `SCHEMA_v0.1.md` 定义的统一 Task Instance，并提供一套可注册、可扩展的 checker。

- **纯标准库**：不依赖 pandas / datasets / transformers；也**没有**用 pydantic（目标机器上没装，见下方验证记录），Schema 用 `dataclass` + 手写校验实现。
- **完全离线**：不联网、不下载数据集。每个 adapter 自带 3-4 条**仿真 fixture**（含故意要被过滤掉的脏行），保证转换逻辑先于真实数据被验证。
- **设计文档**：`adapter_design.md`（架构、五形态映射规则、逐数据集规格表、checker 注册机制、difficulty 推断、污染与许可证落地）。

---

## 1. 安装与运行

无需安装，无需虚拟环境：

```bash
python3 -V                       # 需要 3.8+（实测 3.9.6）
cd <项目根目录>                   # 即包含 adapter/ 和 tests/ 的目录

python3 -m adapter list
python3 -m adapter convert --adapter bird_sql \
        --in adapter/fixtures/bird_sql.jsonl --out out.jsonl
python3 -m adapter validate --in out.jsonl
python3 -m adapter stats    --in out.jsonl
python3 -m unittest discover -s tests          # 或 python3 -m pytest tests -q
```

`convert` 会在 `--out` 旁边自动写一份 **sidecar manifest**（`out.manifest.json`）：许可证、是否可商用、原始 id ↔ 实例 id 映射、转换损失说明、待人工标注队列都在里面（Schema 冻结，这些信息不许进实例）。

### 子命令

| 子命令 | 作用 | 关键参数 |
|---|---|---|
| `list` | 列出已注册的 adapter 与 checker（含 layer / 支持的 gold_types） | — |
| `convert` | 原始 jsonl → TaskInstance jsonl + manifest | `--adapter --in --out --aux --split --lang --difficulty --seq-start --limit --must-not --options --manifest --lenient` |
| `validate` | 逐条 Schema 校验 + 全局 id 查重 | `--in --max-errors` |
| `stats` | 门类 / 难度 / 语言 / gold.type / checker / source 分布，并对照 3:5:2 目标配比 | `--in` |
| `check` | 离线判分（`must_not_guard` 前置钩子 + 绑定的 checker） | `--in --responses --out` |

`--aux` 用于多文件数据集：BIRD 的 DDL 目录、BEIR 的 corpus+qrels。当 `--in` 指向 `adapter/fixtures/` 且存在同名 `*_aux.json` 时会自动加载，所以上面的示例命令不用写 `--aux`。

---

## 2. 目录说明

```
adapter/
  __init__.py       公共门面：AdapterConfig / get_adapter / run_check / TaskInstance
  __main__.py       python -m adapter 入口
  cli.py            convert / list / validate / stats / check
  schema.py         TaskInstance + 逐字段校验 + CheckerResult 构造器/校验器 + ModelResponse
  registry.py       adapter 与 checker 双注册表 + wrap_third_party（第三方判分器适配）
  base.py           Adapter 基类、AdapterConfig、通用流水线、canary、manifest
  checkers/
    __init__.py     run_check（唯一判分入口，串起全局前置钩子）
    must_not.py     must_not_guard —— 全局前置钩子
    sql_equiv.py    sql_result_equiv（真跑 sqlite3）+ BIRD VES wrapper 示例
    exec_tests.py   exec_tests（subprocess 跑单测 + 超时）
    fact_recall.py  fact_recall（规则版 + 可注入 LLM judge）
    ir_metrics.py   doc_recall_at_k / citation_groundedness
    numeric_em.py   numeric_em（容差 + 单位/百分号归一）
    state_diff.py   state_diff（忽略自增 id/时间戳，多合法路径）
    rubric_judge.py rubric_judge（L3 离线 stub）+ pairwise 双向换位
    format_compliance.py  format_compliance（IFEval 约束 DSL，L1）
  adapters/         bird_sql / bigcodebench / simpleqa / chinese_simpleqa /
                    frames / beir / dabstep / tau2_bench / ifeval
  fixtures/         每个 adapter 的仿真原始记录（+ *_aux.json）
  utils/            io（jsonl/json）、text（NFKC、CJK 分词、代码块抽取）
tests/              198 个单测
```

### 已实现的 adapter（9 个 / 8 个数据集）

| adapter | 门类 | gold.type | checker | 数据集@版本 | 可商用 |
|---|---|---|---|---|---|
| `bird_sql` | G7 | executable | `sql_result_equiv` | bird-sql-minidev@v2-2024-06 | conditional |
| `bigcodebench` | G7 | executable | `exec_tests` | bigcodebench@v0.1.4 | yes |
| `simpleqa` | G1 | factlist | `fact_recall` | simpleqa@2024-10 | yes |
| `chinese_simpleqa` | G1 | factlist | `fact_recall` | chinese-simpleqa@2024-11 | yes |
| `frames` | G1 | factlist | `fact_recall` | frames-benchmark@2024-09 | yes |
| `beir` | G2 | reference | `doc_recall_at_k` | beir-scifact@v1.0.0 | conditional |
| `dabstep` | G6 | reference | `numeric_em` | dabstep@2025-03 | conditional |
| `tau2_bench` | G9 | trace | `state_diff` | tau2-bench@v1.0.0 | yes |
| `ifeval` | G4 | rubric | `format_compliance` | ifeval@2023-11 | yes |

### 已实现的 checker（10 个）

`must_not_guard`(L1,全局前置) · `sql_result_equiv`(L1) · `exec_tests`(L1) · `numeric_em`(L1) · `state_diff`(L1) · `format_compliance`(L1) · `fact_recall`(L2) · `doc_recall_at_k`(L2) · `citation_groundedness`(L2) · `rubric_judge`(L3)

---

## 3. 如何新增一个 adapter（分步）

1. **新建 `adapter/adapters/<name>.py`**，继承 `Adapter` 并用装饰器注册：

   ```python
   from ..base import Adapter, AdapterConfig
   from ..registry import register_adapter

   @register_adapter("my_dataset")
   class MyAdapter(Adapter):
       dataset, version = "my-dataset", "v1.0"
       category, subtype = "G3", "KEYPOINT_EXTRACTION"
       gold_type, checker = "factlist", "fact_recall"
       license, commercial_use = "Apache-2.0", "yes"
       homepage = "https://..."
       base_must_not = ("泄露PII",)
       manual_annotation = ""     # 非空 = 这个集有人工待标注，会进 manifest 待标队列
       lossy_notes = "……转换损失……"   # 必填，写清楚丢了什么
   ```

2. **实现 `convert`**。只做「字段映射 + gold 构造」，其余（id / lang / must_not / canary / 校验 / manifest）都交给 `self.build(...)`：

   ```python
   def convert(self, raw_record, cfg):
       q = (raw_record.get("question") or "").strip()
       if not q:
           return None                      # 返回 None = 过滤掉（不是错误）
       gold = {"type": "factlist",
               "value": {"facts": [{"id": "f1", "text": raw_record["answer"],
                                    "required": True}],
                         "ref_answer": raw_record["answer"]}}
       return self.build(raw_record, cfg, subtype=self.subtype, prompt=q, gold=gold,
                         manifest_extra={"orig_topic": raw_record.get("topic")})
   ```

3. **（可选）覆写 `infer_difficulty(raw_record, inst_kwargs)`**，返回 L1/L2/L3。写成可程序化的结构启发式；记住这只是初值，正式流程要用基线模型实测通过率反标（见设计文档 §5）。

4. **（可选）覆写 `prepare(cfg)`**，读 `cfg.aux` 里的辅助数据（DDL 目录、语料、qrels）。

5. **加一行 import**：在 `adapter/adapters/__init__.py` 里 `from . import my_dataset`。

6. **造 fixture**：`adapter/fixtures/my_dataset.jsonl`，2-4 条仿真原始记录，**至少一条是应当被过滤掉的脏行**（这样才能测到过滤分支）。需要辅助数据就再放一个 `my_dataset_aux.json`。

7. **跑一遍并让测试覆盖它**：

   ```bash
   python3 -m adapter convert --adapter my_dataset \
           --in adapter/fixtures/my_dataset.jsonl --out /tmp/x.jsonl
   python3 -m adapter validate --in /tmp/x.jsonl
   python3 -m unittest tests.test_adapters      # 通用断言会自动覆盖新 adapter
   ```

   `tests/test_adapters.py` 里的 `TestAllAdapters` 会对**所有**已注册 adapter 自动断言：有 fixture、能转换、逐条过 Schema、`source` 是 `public:x@y`、checker 已注册且支持该 gold.type、id 不重、manifest 行数对齐。新增 adapter 无需改这些测试。

## 如何新增一个 checker

1. 在 `adapter/checkers/` 新建模块，写成统一签名并注册：

   ```python
   from ..registry import register_checker
   from ..schema import ModelResponse, new_checker_result

   @register_checker("my_checker", layer="L2", gold_types=["factlist"],
                     description="一句话说明", tags=["G3"])
   def my_checker(instance, response, env=None):
       resp = ModelResponse.coerce(response)     # 兼容 str / dict / ModelResponse
       score = ...
       return new_checker_result(score=score, passed=score >= 0.85, layer="L2",
                                 sub_metrics={...}, violations=[], detail={...})
   ```

   **只能用 `new_checker_result()` 构造返回值**——它是 CheckerResult 七键签名的唯一入口。

2. 在 `adapter/checkers/__init__.py` 加一行 `from . import my_checker`。

3. 涉及 LLM 的部分必须走 `env` 注入，并提供离线默认实现（stub），且在 `sub_metrics` 里标明用没用 stub。参考 `fact_recall`（`env["fact_judge"]`，返回 `None` 表示弃权并回落规则）与 `rubric_judge`（`env["judge"]`）。

4. **接第三方判分器**用 `registry.wrap_third_party(...)`：`inner` 返回外部结构，`to_result` 归一成 CheckerResult。示例见 `checkers/sql_equiv.py` 里的 BIRD VES（`_ves_inner` / `_ves_to_result`）。

---

## 4. 验证记录（真实命令与输出）

环境：macOS 26.6.2 (arm64)，`/Library/Developer/CommandLineTools` 自带 Python。

```
$ python3 -V
Python 3.9.6

$ python3 -c "import pydantic"
ModuleNotFoundError: No module named 'pydantic'
```

→ **结论：用 dataclasses + 手写校验，不用 pydantic。**（`pytest` 同样未安装，测试用 `unittest` 跑。）

### 4.1 `python3 -m adapter list`

```
ADAPTERS (9)
  adapter           cat  gold.type   checker            dataset@version              commercial
  ----------------  ---  ----------  -----------------  ---------------------------  -----------
  beir              G2   reference   doc_recall_at_k    beir-scifact@v1.0.0          conditional
  bigcodebench      G7   executable  exec_tests         bigcodebench@v0.1.4          yes
  bird_sql          G7   executable  sql_result_equiv   bird-sql-minidev@v2-2024-06  conditional
  chinese_simpleqa  G1   factlist    fact_recall        chinese-simpleqa@2024-11     yes
  dabstep           G6   reference   numeric_em         dabstep@2025-03              conditional
  frames            G1   factlist    fact_recall        frames-benchmark@2024-09     yes
  ifeval            G4   rubric      format_compliance  ifeval@2023-11               yes
  simpleqa          G1   factlist    fact_recall        simpleqa@2024-10             yes
  tau2_bench        G9   trace       state_diff         tau2-bench@v1.0.0            yes

CHECKERS (10)
  checker                layer  gold_types          description
  ---------------------  -----  ------------------  -----------
  citation_groundedness  L2     reference,factlist  Citations must resolve to snapshot docs and quoted spans must be verbatim.
  doc_recall_at_k        L2     reference           Recall@k primary + nDCG@10 sub-metric; fabricated doc id => score 0.
  exec_tests             L1     executable          Runs candidate Python + unit tests in a subprocess with a timeout.
  fact_recall            L2     factlist            Atomic fact-point recall with injectable LLM judge (default: offline rule stub).
  format_compliance      L1     rubric              IFEval-style verifiable constraints encoded as ifeval:<name>:<arg> in must_cover.
  must_not_guard         L1     *                   Global pre-hook: any must_not hit forces score=0.
  numeric_em             L1     reference           Exact value match with numeric tolerance / unit + percent normalisation.
  rubric_judge           L3     rubric              Weighted 5-point rubric; offline deterministic stub unless env['judge'] given.
  sql_result_equiv       L1     executable          sqlite3 execution accuracy: row/column-order & float/NULL aware set equality.
  state_diff             L1     trace               Terminal DB-state diff ignoring auto ids/timestamps, multi-path tolerant.
```

### 4.2 convert / validate / stats

```
$ python3 -m adapter convert --adapter bird_sql --in adapter/fixtures/bird_sql.jsonl --out out.jsonl
adapter   : bird_sql (public:bird-sql-minidev@v2-2024-06)
read      : 4
converted : 3
filtered  : 1
errored   : 0
written   : 3 -> out.jsonl
manifest  : out.manifest.json

$ python3 -m adapter validate --in out.jsonl
validated : 3 rows, 0 invalid
RESULT    : OK

$ python3 -m adapter stats --in out.jsonl
instances : 3
category  : G7=3
subtype   : SQL_QUERY=3
difficulty: L1=1, L2=2
lang      : en=3
split     : dev=3
gold_type : executable=3
checker   : sql_result_equiv=3
source    : public:bird-sql-minidev@v2-2024-06=3
L1:L2:L3  : 3.3:6.7:0.0  (target 3:5:2)
must_not/inst: 3.00
```

> `read 4 / converted 3 / filtered 1`：第 4 条 fixture 是 `DELETE FROM orders ...`，G7 禁写，被 `convert` 返回 `None` 过滤掉——这是设计行为，不是失败。

### 4.3 全部 9 个 adapter 批量转换后合并统计

```
$ for a in bird_sql bigcodebench simpleqa chinese_simpleqa frames beir dabstep tau2_bench ifeval; do
    python3 -m adapter convert --adapter $a --in adapter/fixtures/$a.jsonl --out build/$a.jsonl >/dev/null
  done
$ cat build/*.jsonl > build/all.jsonl
$ python3 -m adapter validate --in build/all.jsonl
validated : 26 rows, 0 invalid
RESULT    : OK

$ python3 -m adapter stats --in build/all.jsonl
instances : 26
category  : G1=9, G2=3, G4=3, G6=3, G7=6, G9=2
subtype   : CODE_FUNCTION=3, DATA_ANALYSIS=3, DOC_RETRIEVAL=3, FORMAT_CONSTRAINED_WRITING=3, MULTIHOP_FACT_QA=3, MULTITURN_TOOL_OPS=2, SHORT_FACT_QA=3, SHORT_FACT_QA_ZH=3, SQL_QUERY=3
difficulty: L1=6, L2=16, L3=4
lang      : en=20, mixed=3, zh=3
split     : dev=26
gold_type : executable=6, factlist=9, reference=6, rubric=3, trace=2
checker   : doc_recall_at_k=3, exec_tests=3, fact_recall=9, format_compliance=3, numeric_em=3, sql_result_equiv=3, state_diff=2
source    : public:beir-scifact@v1.0.0=3, public:bigcodebench@v0.1.4=3, public:bird-sql-minidev@v2-2024-06=3, public:chinese-simpleqa@2024-11=3, public:dabstep@2025-03=3, public:frames-benchmark@2024-09=3, public:ifeval@2023-11=3, public:simpleqa@2024-10=3, public:tau2-bench@v1.0.0=2
L1:L2:L3  : 2.3:6.2:1.5  (target 3:5:2)
must_not/inst: 1.65
```

> 五种 `gold.type` 全部出现；难度配比 2.3:6.2:1.5 偏离目标 3:5:2 —— 这是 26 条 fixture 的样本效应，正式数据要靠**补题**而不是改标签来纠正（设计文档 §5）。

### 4.4 `check`：全局前置钩子的实际效果

```
$ python3 -m adapter check --in out.jsonl --responses responses.jsonl
G7-SQL_QUERY-0001            sql_result_equiv     score=1.000 passed=True
G7-SQL_QUERY-0002            sql_result_equiv     score=0.000 passed=False VIOLATIONS: 执行 DROP; 执行任何写操作
G7-SQL_QUERY-0003            sql_result_equiv     score=0.000 passed=False
checked   : 3, passed 1, violations 2
```

> 第 2 条的 SQL 里既有 `DROP TABLE` 又有一条合法 `SELECT`——`must_not_guard` 命中后**直接短路**，绑定的 `sql_result_equiv` 根本没执行（结果的 `detail.short_circuit=true` / `skipped_checker="sql_result_equiv"`）。

### 4.5 测试

```
$ python3 -m unittest discover -s tests
...............................................................................
----------------------------------------------------------------------
Ran 198 tests in 2.821s

OK
```

分模块：

| 文件 | 用例数 | 覆盖 |
|---|---|---|
| `tests/test_schema.py` | 23 | 字段增删、id 格式、枚举闭集、source 五种写法、五种 gold 形态结构、CheckerResult 签名 |
| `tests/test_checkers_sql.py` | 24 | 真跑 sqlite3；行序/列序/重复行/浮点容差/NULL 语义各一条；语法错误、markdown 代码块抽取、VES wrapper |
| `tests/test_checkers_ir.py` | 12 | recall@k / nDCG 数学、截断 k、假文档清零、引文可定位、must_cite 覆盖 |
| `tests/test_must_not.py` | 25 | DROP/DELETE/TRUNCATE/无 WHERE UPDATE、手机号/身份证/邮箱/凭据、`rm -rf`、破坏性工具调用、工具参数里的 PII、三级规则解析、未解析规则可见、**短路前置钩子**、误报回归 |
| `tests/test_checkers_misc.py` | 42 | fact_recall（别名/数值容差/全角/注入 judge）、numeric_em（千分位/百分号/万亿/列表）、state_diff（忽略自增 id 与时间戳/多路径/禁用调用/communicate）、rubric_judge（stub 标记/双向换位）、format_compliance（17 类约束/不支持的约束不算通过）、exec_tests（正确/错误/语法错/超时） |
| `tests/test_adapters.py` | 56 | 全 adapter 通用断言 + 每个 adapter 的专项（过滤分支、gold 形状、hard negative 采样、未翻译约束、forbidden_calls 推导……），并**用金标反跑自己的 checker 验证闭环** |
| `tests/test_gold_closed_loop.py` | 7 | **金标闭环门禁**：遍历全部 adapter 的全部实例，把 gold 反构成回答喂回它自己的 checker，断言必须 1.0 且无 violations；另含 G9 终态含 PII 的死题回归、真实泄露仍被拦截的反向断言、缺失模块识别 |
| `tests/test_cli.py` | 9 | list/convert/validate/stats/check 全流程、manifest sidecar、重复 id、坏行、未知 adapter |

**闭环验证**（`test_adapters.py` 里最有价值的几条）：把每个数据集的**金标本身**当作模型回答喂回它自己绑定的 checker，必须得 1.0 分——BIRD 的 gold SQL、BigCodeBench 的 canonical_solution、BEIR 的正例 doc_ids、DABStep 的 answer、τ²-bench 的参考动作+终态，全部通过。这证明「转换 → 判分」这条链路是自洽的。

---

## 5. 已知局限 / 没做的部分

**范围上没做的**

1. **只实现 9 个 adapter（8 个数据集）**。设计文档 §3 的规格表里还有 5 个（MultiHop-RAG / T2Ranking / AlignBench / WorkBench / AIOpsLab）**只有规格、没有代码**：分别卡在「需要拉起外部 sandbox」「需要先有人工维度映射表」「与已实现的 BEIR 高度同构、边际收益低」。
2. **G3 / G5 / G8 / G10 / S 五个门类没有 adapter**。G3/G5 的公开集必须先做人工拆点或 rubric 才有意义；G8 按调研结论公开集可覆盖率仅 15-20% 且需真实 K8s；S 类判分依赖 guard 模型，超出「纯标准库离线」边界。**有意不做，不是遗漏。**

**实现上打了折扣的**

3. **`exec_tests` 不是安全沙箱**。只有超时 + 独立工作目录 + 精简环境变量，恶意代码可以读写文件系统。真实接入 BigCodeBench 必须换成固定版本容器。
   *关于库版本漂移造成的假失败*：现已能识别——失败若全部由 `ModuleNotFoundError` / `ImportError` 引起，结果会标 `sub_metrics.env_only_failure=true`、`sub_metrics.env_errors=n`、`detail.missing_modules=[...]`、`detail.excluded_from_quality=true`。**分数仍是 0，但聚合层必须据此把该样本剔出 pass@1，不能当成模型答错。** 这是实测踩到的：`bigcodebench` fixture 里有一条 gold 依赖 pandas，`options.stdlib_only=True` 没能过滤掉它，在无 pandas 的机器上会静默变成一个 0 分。
4. **`must_not_guard` 的扫描面不含 `final_state`**。只扫模型自己的输出（`text` + `tool_calls` 的名称与参数）。原因：`final_state` 是环境的客观状态，环境里存在客户手机号不等于模型泄露了它。此前把它纳入扫描，导致 τ²-bench 电信那条题无解——回显真实终态判「泄露 PII」，抹掉手机号则 `state_diff` 判状态不符，满分区间为空集。代价是**「模型把终态里的 PII 复述给用户」这一情形只能靠 `text` 命中**；如果需要更严的判定，应当在 `state_diff` 侧增加「不该出现在对用户话术里的字段」白名单，而不是回退到扫 `final_state`。
5. **`rubric_judge` 默认是离线启发式 stub**，分数**没有质量含义**（结果里 `sub_metrics.stub=true` + `detail.warning` 明示）。真实 L3 需要 `env["judge"]` 注入 LLM。
6. **`fact_recall` 默认是规则匹配**，同义改写会漏判（"八千八百四十八点八六米" vs "8848.86"）。真实评测需注入 LLM judge 并做 10% 人工抽检校准。
7. **FRAMES 的多跳事实点没有拆**。adapter 只给「最终答案」一条 required fact + 按 wiki 实体生成的 optional 占位 fact（不进分母），manifest 标 `annotation_state: pending_fact_split`。所以这批题**当前等价于最终答案 EM，测不出推理链对不对**。人工成本：3-5 分钟/题，40-70 题/人日。
8. **IFEval 只翻译了 16 种 instruction_id**，其余从 `must_cover` 丢弃并记 `untranslated_constraints`。后果是**题面文字里的要求 > 判分覆盖的要求**，模型可能违反了一条没被判的约束还拿满分。不改 Schema 就消不掉这个缺口，只能靠 manifest 暴露。
9. **BEIR 的 Recall@k 是 pool 内的值**（默认 50 篇/query，含全部正例 + BM25-lite 选出的硬负例），绝对值高于全量语料上的真实难度，**不能和官方 leaderboard 数字对比**。
10. **τ²-bench 的乘积门控 reward 语义丢失**（压成 `0.7×状态 + 0.15×序列 + 0.15×communicate` 的加权和），`pass^k` 稳定性也没有；用户模拟器不在适配层内，转出来的题需要配套环境才能真跑。无 `env_assertions` 的题 manifest 标 `state_unverified: true`（实际只判序列）。
11. **`state_diff` 只比对 gold pin 的表**，AppWorld 式的 collateral damage（误改了不该改的表）检测不到，除非人工在 `final_state` 里显式 pin 住"应保持不变"的表。
12. **跨 adapter 的 id 全局唯一**靠 `--seq-start` 分段 + subtype 区分，不是中央发号器。`validate` 能查出重复（有单测），但要把文件合并后再查。
13. **中文 subtype 的 slug 可读性差**：Schema 的 id 只允许 `[A-Z0-9_]`，未登记在 `SUBTYPE_SLUG_ALIASES` 里的中文 subtype 会变成 `SUB_<hash6>`。上线前应把门类 subtype 字典补全。

**环境相关**

14. 本机沙箱**禁止删除文件**，`exec_tests` 用完的 `.adapter_exec/<hex>/` 临时目录清理是 best-effort（`shutil.rmtree(ignore_errors=True)`），会残留空目录。无害，但长期跑需要外部清理。之所以不用 `tempfile`：`tempfile.gettempdir()` 靠「建了再删」探测可用目录，在这个沙箱里直接抛 `FileNotFoundError`，把 `exec_tests` 整个打挂——这是实测踩到的，不是预防性设计。

**fixture 与真实数据的形态差**

15. **手写 fixture 会掩盖字段语义的误解**。实测案例：BigCodeBench 的 `canonical_solution` 在真实数据里只是**缩进的函数体**，import 与 `def` 行都在 `complete_prompt` 里；而 fixture 里手写的那份是自包含的完整程序。于是「`ref_solution = canonical_solution`」这个错误映射在 198 个单测里一路绿灯，直到把真实样本接进 `dataset/` 做金标闭环才暴露（表现为 `syntax_ok=0.0`，三条全 0）。现已由 `adapters/bigcodebench.py::build_ref_solution()` 兼容两种形态。**结论：fixture 只能证明代码不崩，不能证明字段映射是对的；每个 adapter 都应当拿几条真实数据过一遍金标闭环。**

**跑不通的部分**：无。上面列出的 5 条命令与 198 个单测在本机全部通过，输出即第 4 节所贴。
