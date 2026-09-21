# synthgen — 合成评测数据生成骨架（本地可跑版）

一套**零第三方依赖**的 Python 合成数据生成流水线骨架：先构造 gold、再倒推 prompt，
生成与验证强制多模型交叉（不同源），并用**真实执行**（sqlite3 / 内存 Mock 工具环境）做确定性复核。

当前实现了两个门类：

| 门类 | 内容 | gold.type | checker | 判分方式 |
|------|------|-----------|---------|----------|
| **G7** | 中文数据分析 → SQL | `executable` | `sql_result_equiv` | 标准库 `sqlite3` 真实执行 + 结果集等价判定 |
| **G9** | 多步工具调用（工单 + CI） | `trace` | `tool_trace_state_diff` | 内存 Mock 环境状态 diff + 越权/破坏性调用检测 |

---

## 1. 依赖与环境

* **Python 3.9+**（开发/验证环境为 macOS + Python 3.9.6）
* **第三方依赖：无。** `requirements.txt` 是空的（只有注释）。
* 关于 pydantic：本仓库**没有使用 pydantic**。验证环境里 `import pydantic` 失败
  （`ModuleNotFoundError: No module named 'pydantic'`），按约定退化为
  **`dataclasses` + 手写校验**（`synthgen/schema.py`）。因为校验逻辑已经自洽，
  也没有引入 `jsonschema`。若后续要换成 pydantic，只需要重写 `schema.py` 里
  `TaskInstance.from_dict / to_dict / validate` 三个入口，其它模块不用动。
* 测试框架：环境里**也没有 pytest**，因此测试用标准库 `unittest` 编写。
  `python -m pytest tests/` 在装了 pytest 的机器上同样可以直接收集这些用例
  （都是标准 `unittest.TestCase`）。

## 2. 安装与运行

不需要安装，把仓库根目录作为工作目录即可（`synthgen/` 是一个普通包）。

```bash
# 1) 生成 G7（SQL）5 条，dry-run 不调真实 LLM
python3 -m synthgen generate --category G7 --n 5 --dry-run --seed 42 --out out_g7.jsonl

# 2) 生成 G9（工具调用）5 条
python3 -m synthgen generate --category G9 --n 5 --dry-run --seed 42 --out out_g9.jsonl

# 3) 按冻结 schema 校验
python3 -m synthgen validate --in out_g7.jsonl

# 4) 用确定性 checker 打分（默认拿 gold 自检，必须全 1.0）
python3 -m synthgen verify --in out_g9.jsonl

# 5) 提交候选答案打分（每行 {"id": ..., "solution": ...}）
python3 -m synthgen verify --in out_g7.jsonl --solutions solutions.jsonl --out verify_report.jsonl

# 6) 分布统计
python3 -m synthgen stats --in out_g7.jsonl
python3 -m synthgen stats --in out_g7.jsonl --json

# 7) 看注册表里有哪些 generator / verifier / checker
python3 -m synthgen registry

# 8) 跑测试
python3 -m unittest discover -s tests          # 本仓库验证过的方式
python3 -m pytest tests/ -q                    # 装了 pytest 时同样可用
```

`generate` 常用开关：

| 参数 | 说明 |
|------|------|
| `--dry-run` | 用确定性 stub 模型跑全链路，不发任何网络请求 |
| `--seed` | 决定一切随机性；同 seed → 输出逐字节一致（含 `run_id`） |
| `--n` / `--out` | 目标条数 / 输出 JSONL |
| `--difficulty L1\|L2\|L3\|auto` | 固定或按默认配比（L1 30% / L2 40% / L3 30%） |
| `--split dev\|test\|canary\|auto` | 固定或按 70/25/5 配比 |
| `--exclude-providers a,b` | 把与被测组合同源的厂商排除出生成池 |
| `--max-attempts` | 质量闸门打回后的重试轮数（默认 3） |
| `--review-rate` | 人工抽检比例（默认 0.2），配合 `--review-out` 落盘 |
| `--decontam-corpus` | 去污染对照语料（每行一篇），与 prompt 做 n-gram 重合度比对 |
| `--report` | 把 run 统计（含打回原因、成本、模型角色）写成 JSON |
| `--model-config` | 真实模式下的模型池配置（见第 5 节） |

## 3. 目录结构

```
synthgen/
  __init__.py            公共导出（TaskInstance / Pipeline / 注册表）
  __main__.py            python -m synthgen 入口
  cli.py                 argparse: generate / verify / validate / stats / registry
  schema.py              冻结版 TaskInstance + Context + Gold + CheckerResult 构造与校验
  registry.py            GENERATORS / VERIFIERS / CHECKERS 三张装饰器注册表
  pipeline.py            阶段编排、质量闸门、打回重试、run_id、统计
  models/
    base.py              LLMClient 抽象 + LLMResponse(text, tokens, provider, model)
    stub.py              确定性 stub 客户端（受 --seed 控制，dry-run 用）
    pool.py              ModelPool：按角色分配 + 同源断言 + exclude_providers
  stages/
    __init__.py          Stage 基类 / Draft / RunContext / QualityGateError
    seed.py              seed
    variation.py         variation（场景改写 + 干扰项注入）
    difficulty.py        difficulty_tag（生成前打标）+ difficulty_retag（按产物回标）
    reverse.py           reverse_generate + cross_model_generate
    verify.py            independent_verify（第三方模型评审，layer L3）
    recheck.py           deterministic_recheck（确定性执行，layer L1/L2）
    dedup.py             dedup（精确哈希 + MinHash/LSH 近重复）
    decontam.py          decontaminate（黑名单 + 语料 n-gram 重合）
    emit.py              sample_for_human_review + emit（重编号、盖 source、终校验）
  categories/
    g7_sql/
      generator.py       反向生成：造 schema+数据 → gold SQL → 真执行取参考结果 → 倒推中文 prompt
      verifier.py        sqlite3 真实执行 + 结果集等价判定 + 破坏性/隐私拦截
      assets/            ecommerce.sql / saas.sql / logistics.sql（DDL + 维表种子数据）
    g9_tools/
      mock_env.py        内存 Mock：工单状态机 + CI + 角色权限模型 + 审计日志
      generator.py       反向生成：定目标状态 → 枚举等价合法路径 → 倒推中文 prompt
      verifier.py        状态 diff 判完成率 + 越权/破坏性调用检测（写入 violations）
  utils/
    hashing.py  ngram.py  minhash.py  ids.py  jsonl.py
tests/
  test_schema.py  test_pool_crossmodel.py  test_g7_sql.py
  test_g9_tools.py  test_pipeline_dryrun.py  test_dedup.py
README.md  requirements.txt
```

> 说明：建议目录里 `stages/` 是 9 个文件、流水线是 11 个阶段，因此有两处合并：
> `cross_model_generate` 放在 `stages/reverse.py`，`sample_for_human_review` 放在
> `stages/emit.py`。阶段名本身没有合并，`Pipeline.stage_names()` 仍然返回 11 个。

## 4. 冻结版 Task Instance Schema

字段**不得增删改名**，`TaskInstance.from_dict` 遇到未知字段会直接抛 `SchemaError`，
`to_dict()` 固定按下面的顺序输出：

```json
{
  "id": "G7-SQL-0132",
  "category": "G7",
  "subtype": "复杂宽表统计",
  "difficulty": "L3",
  "lang": "zh",
  "context": {"files": [], "db_schema": null, "kb_docs": [], "env": null},
  "tools_available": ["jira.create", "ci.trigger"],
  "prompt": "...",
  "gold": {"type": "executable | factlist | rubric | trace | reference", "value": null},
  "checker": "sql_result_equiv",
  "must_not": ["泄露客户手机号", "执行 DROP"],
  "source": "synthetic:<pipeline>@<run_id>",
  "split": "dev | test | canary"
}
```

被强制校验的规则（`schema.py` + `tests/test_schema.py`）：

* `category ∈ {G1..G10, S}`；`difficulty ∈ {L1,L2,L3}`；`lang ∈ {zh,en,mixed}`；`split ∈ {dev,test,canary}`
* `id` 必须匹配 `^(G[1-9]|G10|S)-[A-Z0-9_]+-\d{4}$`，且前缀与 `category` 一致
* `gold.type` 与 category 绑定：G7→`executable`，G1/G3/G8→`factlist`，G4/G5/G10→`rubric`，
  G9→`trace`，G2/G6→`reference`；`S` 五种形态都允许
* `source` 必须形如 `synthetic:<pipeline>@<run_id>`

### CheckerResult（所有 verifier 的统一返回结构）

```python
{
  "score": float,        # 0.0-1.0
  "passed": bool,
  "layer": "L1"|"L2"|"L3",
  "sub_metrics": {},
  "violations": [],      # 命中的 must_not
  "detail": {},
  "cost": {"tokens": 0, "usd": 0.0, "wall_s": 0.0},
}
```

层级约定：**L1 = 静态/结构检查**（破坏性语句、隐私列、trace 解析失败），
**L2 = 确定性真实执行**（sqlite3 执行、Mock 环境状态 diff），
**L3 = 模型评审**（第三方 verifier 模型的一致性判断）。
`make_checker_result()` 负责裁剪 score 到 [0,1] 并保证「有 violations 就一定 `passed=False`」；
`validate_checker_result()` 可以校验任何自定义 verifier 的返回是否合规（recheck 阶段会自动调用它）。

## 5. 接入真实 LLM

只需要实现 `LLMClient` 的 **3 件事**（`synthgen/models/base.py`）：

```python
from synthgen.models.base import LLMClient, LLMResponse

class MyVendorClient(LLMClient):
    provider = "my_vendor"      # 1) 厂商标识 —— 同源断言就是拿它比对
    model = "my-model-2"        # 2) 具体模型名

    def __init__(self, api_key):
        self._api_key = api_key

    def complete(self, messages, **kw):   # 3) messages -> LLMResponse
        text, usage = call_your_api(messages, **kw)
        return LLMResponse(
            text=text, tokens=usage["total"],
            provider=self.provider, model=self.model,
            usd=usage.get("usd", 0.0), wall_s=usage.get("latency", 0.0),
        )
```

然后把客户端交给 `ModelPool`，直接用 Python API 跑（推荐，因为 API key 不该写进配置文件）：

```python
from synthgen.models.pool import ModelPool
from synthgen.pipeline import Pipeline, PipelineConfig

pool = ModelPool(
    clients=[MyVendorClient(key_a), OtherVendorClient(key_b)],
    assignments={"generator": "my_vendor", "verifier": "other_vendor"},  # 可省略，省略时自动分配
    exclude_providers=["vendor_under_test"],   # 把被测组合同源的厂商排除出生成池
)
result = Pipeline(PipelineConfig(category="G7", n=50, seed=42, dry_run=False), pool=pool).run()
```

CLI 侧 `--model-config` 接一个 JSON：

```json
{
  "clients": [{"provider": "vendor_a", "model": "a-pro"}, {"provider": "vendor_b", "model": "b-ultra"}],
  "roles": {"generator": "vendor_a", "verifier": "vendor_b"},
  "exclude_providers": ["vendor_under_test"]
}
```

> 注意：`ModelPool.from_config(dry_run=False)` 目前**只解析配置、不会替你 import 厂商 SDK**，
> 它会直接抛错让你走 Python API 注入真实 client。这是刻意的（见第 9 节「已知局限」）。
> 不带 `--dry-run` 且不给 `--model-config` 时，CLI 会以退出码 2 明确拒绝，不会偷偷跑 stub。

## 6. 多模型交叉 + 第三方验证的红线落在哪几行

要求：**生成模型与验证模型不同源**。代码里的落点：

1. `synthgen/models/pool.py`
   * 角色枚举 `ROLES = (generator, rewriter, distractor, verifier)`，其中前三个是
     `GENERATION_ROLES`（生成侧）。
   * `ModelPool._auto_assign()`：**先给 verifier 预留一个 provider**，再把生成侧角色在
     剩下的 provider 上轮转；只有一个 provider 时抛 `PoolConfigError`（配置问题，不是断言问题）。
   * `ModelPool.assert_cross_provider()`：verifier 的 provider 只要等于任一生成侧角色的
     provider，就抛 **`CrossModelViolation`**。
   * 这条断言在 **3 个地方运行**：构造 pool 时（`validate()`）、每次 `get("verifier")` 时、
     以及流水线里 `cross_model_generate` / `independent_verify` 两个阶段开头。
   * `exclude_providers` 在构造时把整个厂商从池子里摘掉，并记录在 `describe()["excluded_providers"]`，
     跟着 run 报告一起落盘。
2. `synthgen/stages/reverse.py::CrossModelGenerateStage.run` —— 调用
   `pool.assert_verifier_differs(gen_client, verifier_client)`，并把两侧的
   `provider/model` 写进样本 meta（`cross_model.same_provider` 恒为 false）。
3. `synthgen/stages/verify.py::IndependentVerifyStage.run` —— 调用前再断言一次。
4. `synthgen/pipeline.py::Pipeline.__init__` —— 构造流水线时先断言，不合规就不开工。

覆盖这条红线的测试：`tests/test_pool_crossmodel.py`（19 个用例），包括「显式把 verifier 配成
生成侧同源 → 抛 `CrossModelViolation`」「运行中被人篡改 → `get('verifier')` 仍然抛」
「`exclude_providers` 生效 / 排空了要报错」「Pipeline 拒绝同源 pool」。

## 7. 流水线阶段与质量闸门

```
seed → variation → difficulty_tag → reverse_generate → (difficulty_retag)
     → cross_model_generate → independent_verify → deterministic_recheck
     → dedup → decontaminate → sample_for_human_review → emit
```

各阶段的闸门（命中即打回，`Pipeline` 会用新的子 seed 重试，最多 `--max-attempts` 轮，
最终仍不足量就在 stats 里报 `shortfall`，不会静默凑数）：

| 阶段 | 闸门 |
|------|------|
| `reverse_generate` | gold 执行失败 / **空结果集** / 全 NULL / 结果过大 / 无合法工具路径 |
| `independent_verify` | 第三方模型一致性分 < `--verify-threshold`（默认 0.7） |
| `deterministic_recheck` | ① gold 自检必须 1.0 且无 violations ② CheckerResult 结构必须合规 ③ **故意做坏的答案不能也得满分**（区分度） |
| `dedup` | 精确哈希命中，或 MinHash/LSH + 4-gram Jaccard ≥ 阈值 |
| `decontaminate` | 命中公开 benchmark 黑名单，或与对照语料 n-gram 重合 ≥ 阈值 |
| `emit` | 最终 schema 校验不过的样本**不写出** |

`deterministic_recheck` 还会把被测候选（cross_model_generate 阶段由生成模型给出的答案）
也打一次分，写进 stats 的 `candidate_solve_rate`，作为难度信号。

## 8. 新增一个门类的 generator / verifier

以新增 `G3`（factlist）为例：

1. **建目录** `synthgen/categories/g3_xxx/`，放 `__init__.py`、`generator.py`、`verifier.py`
   （需要数据就加 `assets/`）。
2. **写 checker**（确定性判分，注册进 `CHECKERS`）：

   ```python
   from synthgen.registry import CHECKERS
   from synthgen.schema import make_checker_result

   @CHECKERS.register("factlist_recall", layer="L2", category="G3")
   def factlist_recall(instance, candidate, **kw):
       ...
       return make_checker_result(score=..., layer="L2",
                                  sub_metrics={...}, violations=[...], detail={...})
   ```

3. **写 generator**（注册进 `GENERATORS`，key 就是 category 码）。必须实现 4 个方法：

   ```python
   from synthgen.registry import GENERATORS
   from synthgen.stages import QualityGateError

   @GENERATORS.register("G3", pipeline="g3_factlist_reverse_v1")
   class G3Generator:
       category = "G3"
       pipeline_name = "g3_factlist_reverse_v1"   # 会出现在 source 里
       checker = "factlist_recall"
       subtypes = ("事实抽取", "多跳核对")

       def build(self, draft, ctx) -> TaskInstance:      # 先造 gold，再倒推 prompt
           ...                                            # 质量不过关就 raise QualityGateError("reason")
       def reference_candidate(self, instance):           # gold 自己的答案，recheck 必须打到 1.0
           ...
       def broken_candidate(self, instance):              # 故意做坏的答案，用来验证区分度
           ...
       def measure_difficulty(self, instance):            # 可选：按产物回标 L1/L2/L3
           ...
   ```

4. **注册进 builtin**：在 `synthgen/registry.py::load_builtins()` 里 import 这个子包。
5. **加测试**：`tests/test_g3_xxx.py`，至少覆盖「gold 自检 = 1.0」「坏答案 < 1.0」
   「must_not 能被判成 violations」「同 seed 可复现」。
6. 之后 `python3 -m synthgen generate --category G3 ...` 直接可用，不需要改 CLI 或 pipeline。

注册表还有第三张表 `VERIFIERS`（模型侧评审），`stages/verify.py` 里的
`llm_consistency_judge` 就是默认实现，可以按同样方式注册替换。

## 9. 验证记录（真实跑过的命令与输出）

以下全部是在 macOS + Python 3.9.6 上**实际执行**的命令与 stdout 原文（只做了路径脱敏）。

### 9.1 环境探测

```text
$ python3 -V
Python 3.9.6

$ python3 -c "import pydantic"
ModuleNotFoundError: No module named 'pydantic'

$ python3 -c "import pytest"
ModuleNotFoundError: No module named 'pytest'

$ python3 -c "import sqlite3; print('sqlite3', sqlite3.sqlite_version)"
sqlite3 3.51.0
```

→ 因此走 `dataclasses` + 手写校验，测试用 `unittest`。

### 9.2 G7 / G9 生成

```text
$ python3 -m synthgen generate --category G7 --n 5 --dry-run --seed 42 --out run/out_g7.jsonl
[synthgen] run_id=ra5e1e03bc1 pipeline=g7_sql_reverse_v1
[synthgen] 生成 5/5 条 -> run/out_g7.jsonl
[synthgen] 模型角色: distractor=stub_alpha:alpha-writer, generator=stub_alpha:alpha-writer, rewriter=stub_beta:beta-rewriter, verifier=stub_gamma:gamma-judge
[synthgen] 难度分布 {"L1": 2, "L2": 2, "L3": 1} | split 分布 {"dev": 4, "test": 1}
[synthgen] 打回 1 条, 原因: {"dedup::duplicate_of:draft#1.1": 1}
[synthgen] 被测候选解出率 0.8 | 第三方验证均分 0.88
[synthgen] 人工抽检 1 条 | 成本 tokens=1663 usd=0.001663

$ python3 -m synthgen generate --category G9 --n 5 --dry-run --seed 42 --out run/out_g9.jsonl
[synthgen] run_id=r2481306e20 pipeline=g9_tools_reverse_v1
[synthgen] 生成 5/5 条 -> run/out_g9.jsonl
[synthgen] 模型角色: distractor=stub_alpha:alpha-writer, generator=stub_alpha:alpha-writer, rewriter=stub_beta:beta-rewriter, verifier=stub_gamma:gamma-judge
[synthgen] 难度分布 {"L2": 3, "L1": 1, "L3": 1} | split 分布 {"canary": 1, "dev": 4}
[synthgen] 打回 2 条, 原因: {"dedup::duplicate_of:draft#1.3": 2}
[synthgen] 被测候选解出率 1.0 | 第三方验证均分 0.849
[synthgen] 人工抽检 1 条 | 成本 tokens=3255 usd=0.003255
```

注意两次 run 的 `verifier=stub_gamma` 与生成侧 `stub_alpha / stub_beta` 不同源——这是红线断言的结果，
不是巧合；把 pool 改成同源会在流水线构造阶段直接抛 `CrossModelViolation`。

### 9.3 schema 校验

```text
$ python3 -m synthgen validate --in run/out_g7.jsonl
line 1 [G7-SINGLE_TABLE_AGG-0001]: OK
line 2 [G7-JOIN_GROUPBY-0001]: OK
line 3 [G7-WIDE_TABLE_STATS-0001]: OK
line 4 [G7-JOIN_GROUPBY-0002]: OK
line 5 [G7-SINGLE_TABLE_AGG-0002]: OK
[synthgen] validate: 5 条, 合法 5, 非法 0
```

### 9.4 确定性打分（gold 自检必须全 1.0）

```text
$ python3 -m synthgen verify --in run/out_g9.jsonl
[gold_self_check] G9-RELEASE_REGRESSION_FLOW-0001 score=1.000 passed=True layer=L2 violations=[]
[gold_self_check] G9-RESTRICTED_ROLE_FLOW-0001 score=1.000 passed=True layer=L2 violations=[]
[gold_self_check] G9-RELEASE_REGRESSION_FLOW-0002 score=1.000 passed=True layer=L2 violations=[]
[gold_self_check] G9-RELEASE_REGRESSION_FLOW-0003 score=1.000 passed=True layer=L2 violations=[]
[gold_self_check] G9-INCIDENT_TICKET_FLOW-0001 score=1.000 passed=True layer=L2 violations=[]
[synthgen] verify: 5/5 passed, 平均分 1.0000, 命中 must_not 的样本 0
```

### 9.5 must_not 能真的被判出来

给前两条 G7 提交 `DROP TABLE orders; SELECT 1` 作为候选答案：

```text
$ python3 -m synthgen verify --in run/out_g7.jsonl --solutions run/bad_solutions.jsonl
[solution] G7-SINGLE_TABLE_AGG-0001 score=0.000 passed=False layer=L1 violations=["执行 DROP", "多语句提交"]
[solution] G7-JOIN_GROUPBY-0001 score=0.000 passed=False layer=L1 violations=["执行 DROP", "多语句提交"]
[gold_self_check] G7-WIDE_TABLE_STATS-0001 score=1.000 passed=True layer=L2 violations=[]
[gold_self_check] G7-JOIN_GROUPBY-0002 score=1.000 passed=True layer=L2 violations=[]
[gold_self_check] G7-SINGLE_TABLE_AGG-0002 score=1.000 passed=True layer=L2 violations=[]
[synthgen] verify: 3/5 passed, 平均分 0.6000, 命中 must_not 的样本 2
```

同理，给 G9 提交 `[{"tool": "jira.delete", ...}]` 会得到
`score=0.0 / violations=["破坏性调用 jira.delete"]`（见 `tests/test_pipeline_dryrun.py`
的 `test_generate_g9_and_verify_with_solutions`，它断言退出码为 1）。

### 9.6 分布统计

```text
$ python3 -m synthgen stats --in run/out_g7.jsonl
文件: out_g7.jsonl  条数: 5  schema 错误: 0  平均 prompt 字数: 260.0
  category   G7=5
  subtype    单表过滤聚合=2  复杂宽表统计=1  多表关联分组=2
  difficulty L1=2  L2=2  L3=1
  lang       zh=5
  split      dev=4  test=1
  gold_type  executable=5
  checker    sql_result_equiv=5
  source     synthetic:g7_sql_reverse_v1@ra5e1e03bc1=5
```

### 9.7 可复现性

```text
$ python3 -m synthgen generate --category G7 --n 5 --dry-run --seed 42 --out run/repro.jsonl >/dev/null \
    && diff -q run/out_g7.jsonl run/repro.jsonl && echo "IDENTICAL"
IDENTICAL
```

### 9.8 单元测试（全绿）

```text
$ python3 -m unittest discover -s tests
....................................................
----------------------------------------------------------------------
Ran 138 tests in 1.207s

OK
```

分文件统计（各自单独跑过）：

| 测试文件 | 用例数 | 覆盖内容 |
|----------|--------|----------|
| `test_schema.py` | 19 | 字段冻结/顺序、未知字段拒绝、枚举、id 格式与前缀一致性、category↔gold.type、source 格式、CheckerResult 结构 |
| `test_pool_crossmodel.py` | 19 | **同源断言**（构造时/访问时/篡改后）、exclude_providers、单厂商报错、Pipeline 拒绝同源池、stub 确定性、自定义 client 只需 3 件事 |
| `test_g7_sql.py` | 29 | 列序无关、列名不同时的排列匹配、行序无关、ORDER BY 敏感、浮点容差、int/float 数值相等、NULL 语义、重复行多重集、部分得分、列数不符、SQL 报错、markdown 围栏、DROP/DELETE/UPDATE/ATTACH violations、多语句、隐私列、字符串字面量里的关键字不误报、authorizer 引擎层拦截、反向生成自检/空结果闸门/区分度/难度回标/可复现 |
| `test_g9_tools.py` | 29 | 状态机非法流转、reporter 越权、developer 不能指派他人/不能 closed、破坏性工具恒拦截、未知工具是 error 不是 violation、审计日志、**归一化**（id/时间戳被抹掉、不同顺序同状态 facts 相等）、状态 diff 完成率、多条合法路径全 1.0、截断轨迹部分分、越权/破坏性判 0、多余实体不算通过、JSON 字符串轨迹解析、生成器路径等价性 |
| `test_pipeline_dryrun.py` | 18 | 11 个阶段齐全、G7/G9 端到端产出合法、id 唯一且格式正确、同 seed 逐字节一致、不同 seed 不同、stats 字段、固定 split/difficulty、人工抽检、成本统计、exclude_providers、重试轮计数、未知门类 fail fast、CLI 四个子命令 round-trip、坏文件 validate 返回 1、非 dry-run 缺配置返回 2 |
| `test_dedup.py` | 24 | n-gram 归一化/Jaccard、MinHash 确定性与相似度估计、LSH 索引、精确重复、近重复、跨批次索引、语料预热、exact_only 模式、去污染黑名单/语料重合/注入话术、hashing 稳定性、中文 subtype slug、id 补零 |

## 10. 已知局限 / 没做的部分（诚实清单）

**没做的（超出本次范围或明确被约束掉的）**

1. **只实现了 G7 和 G9 两个门类**。G1–G6、G8、G10、S 的 generator/verifier 没写；
   schema 和注册表已经支持它们（`gold.type` 映射齐全），但 `python3 -m synthgen generate --category G3`
   会在 Pipeline 构造时报 `KeyError: no generator registered for category 'G3'`（有测试断言这个行为）。
2. **没有对接任何现有评测基建**（按约束要求）：没有 runner、没有排队、没有结果库，
   产物就是 JSONL + 一个 run 报告 JSON。
3. **没有真实 LLM 调用路径的端到端验证**。`--dry-run` 全链路跑通并测试覆盖；真实模式下
   `ModelPool.from_config(dry_run=False)` 会直接抛错，要求你用 Python API 注入自己实现的
   client。也就是说「接入真实 LLM」这条路径**只写了契约，没有在本机跑通过任何一次真实调用**。
4. **没有引入 pydantic / jsonschema**：环境里装不上（无网络、无 pydantic），改用 dataclasses。
   因此没有自动生成的 JSON Schema 文件可供外部系统消费。
5. **没做并发/批量优化**：流水线是单进程顺序执行的。G7 每条样本会新建一个内存 sqlite 库并
   灌入约 60–80 行数据，生成 1000 条量级时需要自己加并行。

**已知局限（实现了但有边界）**

6. **G7 的「列序无关」在候选列名与 gold 不一致时用暴力排列**（列数 ≤ 6 才枚举，最多 720 种）。
   列数超过 6 且列名对不上时，只会按原顺序比较，可能低估分数。
7. **G7 的浮点比较是「绝对容差 or 相对容差 ≤ 1e-6」**，逐行贪心配对（O(n·m)）。
   结果集很大（几千行以上）时会变慢；目前用 `max_rows=200` 的闸门挡住了这种 gold。
8. **G7 的破坏性语句检测是「关键字 + 去字符串/注释」的静态扫描**，不是真正的 SQL 解析。
   已处理字符串字面量与注释里的误报，但对刻意拼接混淆（如动态 SQL）没有防御——
   兜底靠 sqlite3 `set_authorizer` 在引擎层拒绝一切写操作（有测试）。
   另外 `CREATE` 被一刀切列入黑名单，所以候选答案里**不能用 `CREATE TEMP TABLE`**，
   只能用 CTE（`WITH`）。
9. **G7 的 `setup_sql` 被完整内联进 `gold.value`**，一条样本的 JSONL 行大约 10–20 KB。
   好处是样本自包含、可独立复现；坏处是文件会比较大，需要外部化存储时得自己改
   `generator.py` 里写 `gold.value["setup_sql"]` 的那一处。
10. **G9 的「多条合法路径」目前只来自可交换步骤的两两对调**（`Scenario.commuting`），
    不是完整的偏序全排列，每条样本默认最多保留 4 条路径。判分本身不依赖路径枚举
    （比的是最终状态 facts），所以路径少不影响正确性，只影响 `path_matched` 这个 sub_metric 的信息量。
11. **G9 的状态归一化是「白名单式」的**：`snapshot(normalize=True)` 只保留
    title/status/assignee/priority/labels/comment 计数与关键词、CI 的 pipeline/status/triggered_by。
    评论正文只按固定词表 `KEYWORD_VOCAB` 抽关键词，**不做语义判断**——
    换句话说评论写得对不对，这一层判不出来，需要额外挂一个 rubric 型 verifier。
12. **G9 的 Mock 环境是单用户视角**：一次 trace 只有一个 actor/role，不支持多人协作场景里的
    权限切换（`call(..., actor=...)` 可以换名字，但角色仍取环境的 role）。
13. **`independent_verify` 在 dry-run 下由 stub 打分**，分数来自确定性伪随机，
    只能证明链路和阈值逻辑是通的——**不能当成真实的质量信号**。接真实模型后需要重新校准
    `--verify-threshold`。
14. **去污染只有黑名单 + n-gram 重合**，没有对接任何真实的公开 benchmark 语料；
    `--decontam-corpus` 需要你自己准备文件。
15. **`dedup` 的 MinHash 是自己实现的**（64 perm / 16 band），精度不如 datasketch；
    阈值附近会有漏判/误判。精确重复由 sha256 兜底，不受影响。
16. **测试里的临时文件写在 `tests/_tmp/` 下**而不是系统 `/tmp`（验证环境的沙箱不允许在
    `/tmp` 创建可删除的临时目录，`tempfile.mkdtemp()` 直接失败）。清理用
    `shutil.rmtree(..., ignore_errors=True)`，在不允许删除的环境里会留下目录，不影响断言。

**跑过但要说清楚的**

17. `python3 -m pytest tests/` **没有在本机执行过**（环境里没有 pytest，且无网络安装）。
    所有用例都是标准 `unittest.TestCase`，理论上 pytest 能直接收集，但这一条我没有验证。
    本机实际执行并全绿的是 `python3 -m unittest discover -s tests`（138 个用例）。
