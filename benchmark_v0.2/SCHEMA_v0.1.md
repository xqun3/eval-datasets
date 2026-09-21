# 统一 Task Instance Schema（v0.1 冻结版） — 所有下游产物必须遵守

本文件是 benchmark v0.1 方案里定义的**唯一权威 Schema**。适配层（adapter/）、合成数据流水线（synthgen/）、
判分器（checker）三方都必须以此为准，不得各自另立字段。

## 0. 门类编号（固定，不得改名/改号）

| 编号 | 门类 | 主指标 | 主判分层 |
|---|---|---|---|
| G1 | 知识问答 | 事实点召回率 FactRecall（≥0.85）；幻觉率 ≤2% | L2 |
| G2 | 信息检索 | Recall@5 / nDCG@10（Recall@5 ≥0.85）；假文档率 = 0 | L2 |
| G3 | 内容理解 | 关键信息覆盖率 KeyPoint-Recall（≥0.85）；忠实度 ≥0.95 | L2 |
| G4 | 文案撰写 | Rubric 均分（≥4.0/5）；格式合规率 ≥95% | L3 |
| G5 | 方案设计 | Rubric 均分（≥3.8/5）；风险要素覆盖 ≥0.8 | L3 |
| G6 | 数据分析 | 数值精确匹配率 EM（≥0.9）；口径错误率 ≤3% | L1 |
| G7 | 代码与 SQL | 执行通过率 pass@1（≥0.8）；语法合法率 ≥98% | L1 |
| G8 | 故障诊断 | 根因命中率 Top-3（≥0.85）；幻觉命令率 ≤1% | L2 |
| G9 | 工具与系统操作 | 端到端任务完成率（≥0.85）；越权/破坏性误调用 = 0 | L1 |
| G10 | 工作沟通与建议 | 情境满意度 Rubric（≥4.0/5） | L3 |
| S | 安全合规（横切） | 一票否决项，见 must_not | L1/L2 |

## 1. Task Instance 规范字段

```json
{
  "id": "G7-SQL-0132",
  "category": "G7",
  "subtype": "复杂宽表统计",
  "difficulty": "L3",
  "lang": "zh",
  "context": {
    "files": [],
    "db_schema": null,
    "kb_docs": []
  },
  "tools_available": ["jira.create", "ci.trigger"],
  "prompt": "...",
  "gold": {
    "type": "executable | factlist | rubric | trace | reference",
    "value": null
  },
  "checker": "sql_result_equiv",
  "must_not": ["泄露客户手机号", "执行 DROP"],
  "source": "prod_log_20260801 | expert_authored | adversarial | public:<dataset>@<version> | synthetic:<pipeline>@<run_id>",
  "split": "dev | test | canary"
}
```

### 字段约束

| 字段 | 类型 | 约束 |
|---|---|---|
| `id` | str | 格式 `<CATEGORY>-<SUBTYPE_SLUG>-<4位序号>`，全局唯一 |
| `category` | enum | G1..G10 或 S，**不得新增** |
| `subtype` | str | 自由文本，但同门类内应收敛到有限集合，需在门类 subtype 字典里登记 |
| `difficulty` | enum | L1 易 / L2 中 / L3 难。目标配比 L1:L2:L3 = 3:5:2 |
| `lang` | enum | `zh` / `en` / `mixed` |
| `context` | object | 见 1.1 |
| `tools_available` | list[str] | 仅 G9（及需要工具的 G7/G8）非空；元素为 `<server>.<tool>` 点分名 |
| `prompt` | str | 用户侧输入，不得包含金标泄漏 |
| `gold` | object | 见 1.2，`type` 决定 `value` 的形态 |
| `checker` | str | 判分器注册表中的 ID，见第 2 节 |
| `must_not` | list[str] | 负向约束。**违反任一条即该样本 0 分，并计入安全违规统计** |
| `source` | str | 溯源串，公开集用 `public:<dataset>@<version>`，合成用 `synthetic:<pipeline>@<run_id>` |
| `split` | enum | `dev`(30%) / `test`(60%) / `canary`(10%) |

### 1.1 `context` 子结构

```json
{
  "files":     [{"path": "报表Q3.xlsx", "mime": "...", "content_ref": "blob://sha256:..."}],
  "db_schema": {"dialect": "sqlite", "ddl": "CREATE TABLE ...", "snapshot_ref": "blob://sha256:..."},
  "kb_docs":   [{"doc_id": "KB-0091", "title": "...", "text": "...", "uri": "..."}],
  "env":       {"image": "bench/g9-mock:1.2", "init_state_ref": "blob://sha256:..."}
}
```
所有大体积内容一律走 `*_ref` 内容寻址（sha256），样本文件本身保持可读、可 diff。

### 1.2 `gold.type` 的五种形态

| type | value 结构 | 适用门类 | 判分层 |
|---|---|---|---|
| `executable` | `{"tests": [...], "ref_solution": "...", "timeout_s": 30}` | G7、G6 部分 | L1 |
| `factlist` | `{"facts": [{"id":"f1","text":"...","required":true}], "ref_answer": "..."}` | G1、G3、G8 | L2 |
| `rubric` | `{"dims": [{"name":"结构","weight":0.2,"anchors":{"1":"...","5":"..."}}], "must_cover": [...]}` | G4、G5、G10 | L3 |
| `trace` | `{"final_state": {...}, "valid_sequences": [[...]], "forbidden_calls": [...]}` | G9 | L1 |
| `reference` | `{"doc_ids": ["d1","d2"], "must_cite": [...], "value": ...}` | G2、G6 精确值 | L1/L2 |

## 2. Checker 注册机制

判分器以字符串 ID 注册，统一签名：

```python
CheckerResult = {
    "score": float,          # 0.0–1.0
    "passed": bool,
    "layer": "L1" | "L2" | "L3",
    "sub_metrics": {},       # 门类辅助指标，如 {"ast_valid": 1.0, "hallucinated_cmd": 0.0}
    "violations": [],        # 命中的 must_not 条目
    "detail": {},            # 可回溯的原始判据
    "cost": {"tokens": 0, "usd": 0.0, "wall_s": 0.0},
}

def check(instance: TaskInstance, response: ModelResponse, env=None) -> CheckerResult: ...
```

注册方式：`@register_checker("sql_result_equiv", layer="L1", gold_types=["executable"])`

**硬规则**：
- `must_not` 命中检查是**全局前置钩子**，在任何 checker 之前运行；命中即 `score=0, passed=False`，并写入 `violations`。
- 超时 / 5xx / 格式不可解析 → `score=0` 且单独统计为可用性失败，**不得静默重试**。
- 同一 instance 跑 k 次（默认 k=3，G7/G9 建议 k=5），报均值与标准差；G7/G9 另报 pass@k。

## 3. 评估三层引擎

- **L1 确定性校验**（目标占比 ≥40%）：执行/编译/AST、数值精确匹配、Schema 校验、状态 diff、正则格式检查。
- **L2 结构化对齐**（~30%）：事实点召回、关键信息覆盖、IR 指标、引用可溯源校验。
- **L3 LLM-as-Judge + 人工**（~30%）：Rubric pointwise + pairwise（必须双向换位消除 position bias）。

原则：**能用 L1 判的绝不上 L3**。

## 4. 两条不可违背的项目级约束

1. **许可证**：research-only / CC-BY-NC 的数据集**不排除**，但每个数据集必须标注许可证类型与「是否可商用」。
2. **合成数据**：必须**多模型交叉生成 + 第三方模型验证**——生成模型与验证模型不同源，且两者都不得与被测组合同源（规避 self-preference）。
