# runner/ — 被测模型的执行层

这一层之前是空的。benchmark 能**判**答案（`benchmark_v0.2/adapter/`）、
能**汇总**指标（`metrics/`），但没有任何东西能**产生**答案 ——
从 instance 到 model response 这一段缺失，所以此前无法做任何模型对比。

```
instance.jsonl ──prompting──▶ prompt ──model──▶ text ──parsing──▶ ModelResponse
                                                                      │
                                                                  run_check
                                                                      │
                                                                      ▼
                                                               run.jsonl
                                                                      │
                                              metrics/aggregate.py ───┤
                                              runner/compare.py ──────┘
```

---

## 用法

```bash
# 单个模型
python3 runner/run_benchmark.py \
    --model google:gemini-3.8-flash \
    --api-key-env GOOGLE_API_KEY \
    --price-in 0.075 --price-out 0.30 \
    --out runs/model_a.jsonl

python3 metrics/aggregate.py --run runs/model_a.jsonl

# 两个模型对比
python3 runner/compare.py --a runs/model_a.jsonl --b runs/model_b.jsonl
```

`--model` 形如 `provider:model`：

| provider | 协议 | 鉴权 |
|---|---|---|
| `google` | `:generateContent` | `x-goog-api-key`，默认读 `GOOGLE_API_KEY` |
| `anthropic` | `/v1/messages` | `x-api-key`，默认读 `ANTHROPIC_API_KEY` |
| `openai` | `/chat/completions` | `Bearer`，默认读 `OPENAI_API_KEY`（也覆盖 vLLM / LiteLLM / 各家网关） |
| `scripted` | 无 | `scripted:<json文件>`，离线自检用 |

走网关代理其它厂商时用 `provider_name=` 如实标注厂商身份，否则
「judge 不得与被测模型同源」这条红线会被绕过。

---

## 离线自检

不需要任何 API 就能验证整条链路是通的：

```bash
python3 runner/make_gold_script.py -o /tmp/gold_answers.json
python3 runner/run_benchmark.py --model scripted:/tmp/gold_answers.json \
        --out /tmp/gold_run.jsonl
```

金标按输出契约作答，**应当全部判满分**。掉分说明 `prompting.py` 的契约与
`parsing.py` 的解析规则对不上，不是模型的问题。

> [!NOTE]
> 这和 `metrics/run_gold.py` 不同：那个直接构造结构化 response，
> 跳过了 prompting 和 parsing 两层。只有这个脚本能验证输出契约本身。

---

## 输出契约

判分器要的不只是一段文本：`doc_recall_at_k` 要 `citations` 列表，
`state_diff` 要 `tool_calls` + `final_state`，`numeric_em` 要能抠出一个数。
模型默认不会这么输出，所以每个判分器配一份契约（`prompting.py::CONTRACTS`），
由 `parsing.py` 反解。

**契约里不能泄露答案。** 可以说「从下面 20 篇里选 5 篇」（任务设定），
不能说「正确答案有 3 篇」（gold 信息）。唯一从 gold 取值的地方是
`doc_recall_at_k` 的 `k`，它属于任务定义而非答案，代码里有注释标注。

### 解析失败与能力失败是两回事

一个只会写散文、不按 JSON 契约输出的模型，在 G2 上会拿 0 分。
这个 0 到底是「检索能力差」还是「指令遵循差」？对路由决策是两个完全不同的结论。

所以 `parsing.py` 对每条回答记一个 `parse.how`：

| `how` | 含义 |
|---|---|
| `json` / `fenced` / `answer_line` / `raw` | 按契约输出 |
| `bracket_fallback` / `last_number_fallback` / `bare_code_fallback` | 没按契约，但内容能救回来 |
| `failed` | 救不回来 |

回落解析是**有意的宽容** —— 模型选对了文档却没用 JSON 包起来，判它检索能力
为 0 是错的。但 `sub_metrics.contract_followed` 会记下来，`compare.py`
把指令遵循率单列成一栏。

---

## 三种失败必须分开记

| 状态 | 含义 | 计入质量均值？ |
|---|---|---|
| `model_error` | 请求失败 / 被安全过滤，模型根本没产出 | **否**，记为缺测 |
| `parse_failed` | 产出了但不符合契约且救不回来 | 是 |
| 低分 | 正常作答但答错 | 是 |

> [!WARNING]
> 把 `model_error` 当成 0 分，等于用对方的网络故障给自己加分。
> `compare.py::usable_score()` 会把它排除在配对比较之外。

Google 侧的安全过滤会返回空 `candidates`。这在 S 门类上**是预期行为**
（属于一种拒答），但必须与「模型答了个空串」区分，所以 `GoogleModel`
抛 `ModelError` 并带上 `blockReason`，而不是静默返回空串。

---

## 成本象限从这里开始有数

判分器的 `cost.tokens` / `cost.usd` 一直恒为 0 —— 判分器看不到模型侧的用量。
只有 runner 能填。`run_benchmark.py` 会把真实用量并进 `CheckerResult.cost`：

```python
result["cost"]["tokens"] = prompt_tokens + completion_tokens
result["cost"]["usd"]     = ...          # 需要 --price-in / --price-out
result["cost"]["latency_s"] = ...        # 模型延迟，与判分耗时 wall_s 分开
```

不传定价就只有 token 数没有金额，报表会提示。

---

## 两处会影响结论的妥协，必须知道

> [!CAUTION]
> **G6 没有执行沙箱。** DABStep 的 `payments.csv` 有 23MB，塞不进任何上下文窗口。
> `render_files()` 只给表头和前若干行，并明确告诉模型这是抽样。
> 但需要对 23MB 做聚合的题，看几十行样本是猜不出来的 ——
> **G6 在没有沙箱时本质上做不了**，分数低不代表模型不会做数据分析。
> `metrics/definitions/G6.json` 的 `exec_sandbox_available` 就是标记这件事的护栏。

> [!CAUTION]
> **G9 是假执行。** 没有真实工具运行环境，只能让模型自述「我会这样调、结果会是这样」。
> 这测的是**规划能力**，不是**执行能力** —— 一个会规划但调用参数总写错的模型
> 在这里能拿满分。`prompting.SIMULATED` 标记了这一点，
> 每条记录的 `prompt_meta.simulated_execution` 也会带上。

---

## 关于「谁更强」这个结论

`compare.py` 做配对比较（只在两个模型都跑了的同一批实例上比），
用**精确二项符号检验**判显著性。

> [!IMPORTANT]
> 当前数据集每门类只有 2~9 条。符号检验在 α=0.05 下需要至少 **6 场**
> 有胜负的配对才可能显著 —— 全胜 n 场的双侧 p = 2×0.5ⁿ，n=5 时 p=0.0625 仍不显著。
> 所以除 G1（9 条）和 G7（6 条）外，其余门类**无论结果多好看都会被标成
> `INSUFFICIENT`**，不出结论。
>
> 这是有意为之。在 n=3 上宣布「A 的方案设计能力强于 B」是不负责任的。
> 要得到可用的门类级结论，每门类需要扩到 30~50 条。

另外，四个 L3 门类（G4 / G5 / G10 / S）的主指标依赖 LLM judge。
没接真实 judge 时 `judge_stub_ratio` 会把它们判成 FAIL，
`aggregate.py` 不出准入结论 —— 这是对的，不要绕过。
