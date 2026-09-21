# 测试评估 Benchmark 构建方案 v0.2
## —— 公开集选型 / 适配层 / 合成数据流水线

| 项 | 内容 |
|---|---|
| 版本 | v0.2（承接 v0.1，不替代其 Schema 与指标定义） |
| 上游依据 | 《测试评估 Benchmark 构建》3.1 节 G1–G10 门类定义 |
| 本版新增 | 第 3 章 公开 Benchmark 选型、第 4 章 适配层、第 5 章 合成数据流水线、**第 6 章 三方配比建议表** |
| 本版沿用 | v0.1 的统一 Task Instance Schema、三层评估引擎、四象限指标、准入合取规则、映射效用函数 |
| 配套产物 | 7 份调研报告、4 份映射分片、2 套可运行代码（`synthgen/`、`adapter/`）、3 份设计文档 —— 见第 11 章 |

> **关于本文档的可追溯性**：第 3 章的每一条数据集事实都来自 7 份调研报告，报告中标注「未核实」的字段在本文档中**原样保留为「未核实」**，未做任何推断填充。所有覆盖比例均为原报告给出的估计并保留其区间，本文档未重新计算。凡本文档自身的判断（而非引用）均以「**本版判断**」标出。

---

## 0. 本版要回答的两个问题

v0.1 定义了「benchmark 应该长什么样」。v0.2 回答「东西从哪来」：

1. **公开集能覆盖多少？** —— 结论：**全局约 30–40%，且分布极不均匀**。G7-Code 能到 50–60%，G5 方案设计实际可用题目为 **0 条**。
2. **剩下的怎么造？** —— 一套「反向生成 + 多模型交叉 + 第三方验证」的合成流水线，已有可运行骨架。

一句话总览：**公开集打底 + 合成补量 + 人工守关键金标**，三者比例逐门类不同，见第 6 章。

---

## 1. 承接 v0.1 的不变部分（摘要）

以下内容 v0.2 **不做修改**，完整定义见配套文件 `SCHEMA_v0.1.md`：

- **门类编号** G1–G10 固定，外加横切的 **S 类安全合规**。
- **统一 Task Instance Schema** 12 个字段，`gold.type` 五形态：`executable` / `factlist` / `rubric` / `trace` / `reference`。
- **三层评估引擎**：L1 确定性校验（目标 ≥40%）/ L2 结构化对齐（~30%）/ L3 LLM-as-Judge（~30%）。原则：**能用 L1 判的绝不上 L3**。
- **准入是合取式**，安全类一票否决，不许加权互补。
- **映射用效用函数 + Pareto 前沿**，质量/成本/延迟三元组并列产出。
- **split**：dev 30% / test 60% / canary 10%。
- **重复采样** k=3（G7/G9 建议 k=5，另报 pass@k）。

**v0.2 对 v0.1 的一处补充（本版判断）**：v0.1 规定了 Judge 不能与被测模型同源，但未规定 **Judge 不能与合成数据的生成模型同源**。合成流水线设计过程中发现，若 judge 与出题模型同源，rubric 类题目会系统性偏袒模仿了生成器文风的被测模型。**建议将此约束写回 v0.1 的 Judge 治理章节。**

---

## 2. 用户已确认的三条约束

这三条在 v0.2 全文中作为硬约束执行：

| # | 约束 | 在本版中的落地位置 |
|---|---|---|
| 1 | 许可证 research-only / CC-BY-NC **不排除**，但每个数据集必须标注许可证类型与「是否可商用」 | 第 3.4 节许可证审计；每张数据集表均含「可商用」列 |
| 2 | 合成数据必须 **多模型交叉生成 + 第三方模型验证**（生成/验证不同源，且都不得与被测组合同源） | 第 5.2 节；代码中落为 `ModelPool.assert_cross_provider()` 运行时断言 + 19 个单元测试 |
| 3 | 代码先出**本地可跑的 Python 骨架**，不对接现有评测基建，依赖尽量少 | 第 4.3 / 5.5 节；实测环境无 pydantic/pytest，故用 dataclasses + unittest，**第三方依赖为零** |

---

## 3. 【新增】公开 Benchmark 选型

### 3.1 选型结论总览

**各门类公开集可覆盖比例**（数字为各调研报告原始估计，区间原样保留）：

| 门类 | 可覆盖比例 | 估计依据（摘要） | 必须自建的核心缺口 |
|---|---|---|---|
| G1 知识问答 | **≈35%** | 子维度加权 0.495 后按业务重要性打折；工程判断非实测，误差 ±10pp 起 | 内部知识库问答（0%）、多轮事实一致性（0%）、内部术语与中英混排 |
| G2 信息检索 | **≈40–50%** | 基础检索排序 ~85%、引用可溯源 ~60%、假文档率 ~25%、权限隔离 0%、办公文档格式 ~10% | **权限隔离下的检索（0%，必须 100% 自建）**、中文办公文档格式、真实内部 KB 文体 |
| G3 内容理解 | **≈45%** | 同法加权 0.505，因「形态对口但金标要全部重标」保守下调 | **中文会议纪要（公开集：没有）**、Action Item 结构化抽取（负责人/截止时间/状态 schema） |
| G4 文案撰写 | **≈25–30%（数据侧）**；方法侧 ~70% | 可覆盖的仅通用写作打分、长度约束、机械格式合规（IFEval 25 类判分器） | 中文办公文体（邮件/周报/通知/公文）、企业私域格式规约、中英术语一致率金标 |
| G5 方案设计 | **<10–15%，且全部是「方法」，数据侧可用题目 0 条** | 逐一核实后，**没有任何公开集**的金标形式是「Rubric + 风险要素清单」 | **题库、风险要素清单、基线方案三样全部从零自建**，建议起步 80–120 道 |
| G6 数据分析 | **35–45%**（加权 ~38%） | 多步聚合推理 ~60%，但 Excel/在线表格形态近 0%、中文字段名与业务口径近 0% | Excel 形态（合并单元格、多 sheet、公式列、透视表）、中文口径、口径澄清/反问 |
| G7 代码与 SQL | SQL **45–55%**（~49%）<br>Code **50–60%**（~53%） | SQL：BIRD 覆盖充分但中文 schema ~30%、国内数仓方言 0%<br>Code：函数级覆盖过剩但已污染，办公自动化脚本语境仅 ~15% | 中文字段名 schema、国内数仓方言（Hive/MaxCompute/Doris/ClickHouse/StarRocks，**零覆盖**）、办公自动化脚本、内部私有 API |
| G8 故障诊断 | **15–20%** | 四要素加权：故障素材 ~50% + 根因标签 ~30% + **修复命令白名单 0%** + 判分范式 ~60% = 要素级 30%，折算成品题再对折 | **没有一个公开集能直接用。** 修复命令白名单（0%）、幻觉命令率检测工具链（0%）、中文运维语境（≈0%）、配置/依赖层根因标签 |
| G9 工具与系统操作 | **数据层 ≈10–15%**<br>**框架复用度 ≈70–80%** | 这是两件事，不可合并：没有一条公开样本能原样用（域/语言/工具 schema 全不匹配），但环境框架可大幅复用 | 内部工具集、中文指令、企业权限模型、飞书/企微（公开集**零覆盖、无参照物**） |
| S 安全合规 | **≈55–60%** | 加权覆盖率估计，约 40–45%（约 1,150 条）需自建 | 企业内部合规、客户数据分级、**PIPL/个保法专项（尚处学术拟定阶段，工业界靠内部红队）**、中文 PII（仅 15–20%）、伪造内部文件引用 |

> **全局加权估计（本版判断）**：按各门类等权计算约 **33%**；若按预期题量加权（G1/G2/G3/G7 占比较大），约 **35–40%**。
> **加权假设**：等权计算假设 10 个门类题量相同，实际不成立；题量加权假设 G1/G2/G3/G4/G7 为大宗门类、G5/G8 为小宗。两个数字都应视为量级判断而非精确值。

### 3.2 各门类首选集

> 定位说明：`主盘` = 进 test 集充当分数主体；`辅助` = 补特定子维度；`上限探针` = 只看天花板不进主指标；`仅dev` = 污染过重只能调优用；`仅方法借鉴` = 数据不用、只借范式。

| 门类 | 首选（主盘） | 辅助 / 探针 | 关键说明 |
|---|---|---|---|
| G1 | **SimpleQA Verified**（1,000，MIT）+ **Chinese SimpleQA**（3,000，MIT） | FRAMES（824，Apache-2.0，难档多跳）；HalluQA（450，中文幻觉 spot-check）；GPQA Diamond（198，上限探针） | 两个 SimpleQA 是唯一显式区分 correct/incorrect/**not attempted** 的成熟集，与「FactRecall + 幻觉率 ≤2%」天然同构——incorrect 直接算幻觉，弃答不算。**FActScore 采方法不采数据**：判分器照其 decompose→verify 两段式搭 |
| G2 | **BEIR 挑子集** + **C-MTEB 检索子集** + **ClapNQ**（4,946，Apache-2.0） | PopQA（Apache-2.0，evidence 三元组便于自动判引用）；MultiHop-RAG；LFRQA | **BEIR 整体不能标 Apache-2.0**（见 3.4）。ClapNQ 答案由非连续片段拼成，正是真实办公 RAG 的形态。语料需下采样且要保 hard negatives |
| G3 | **RULER**（Apache-2.0）+ **Loong**（1,600，Apache-2.0）+ **CLongEval**（7,267，中文，MIT） | LongBench v2（503，上限探针）；FaithBench（校准 Faithfulness judge） | **RULER 完全合成、结构上不可能被污染**，且 haystack 可换成我方中文办公语料——这是稀缺性质。Loong 覆盖多文件输入，CLongEval 覆盖中文长文 |
| G4 | **IFEval**（格式合规，25 类程序判分器）+ **CFBench**（中文约束） | WritingBench（1,239，仅 2–3 个域沾边）；LongBench-Write 中文 60 条 | IFEval 类可程序校验的约束**应降级到 L1**，直接服务「L1 ≥40%」硬指标 |
| G5 | **无** | PlanBench / Natural Plan / TravelPlanner 属**可验证规划**，与开放式方案设计不同任务族，不可混用 | **结论：没有，必须全自建。** 不为填表硬凑 |
| G6 | **DABStep**（450+，CC-BY-4.0）+ **InfiAgent-DABench**（257，Apache-2.0） | FinQA（自带推导 program → 对应「推导步骤正确率」）；TAT-QA（自带 scale 单位标注 → 对应「单位/口径错误率 ≤3%」） | DABStep hard 档顶尖系统仅 **14.55–16%**，天花板足够高。**DSBench（466 条 Excel/财务建模）办公契合度最高但 non-commercial**——见 3.4 待决策 |
| G7-SQL | **BIRD**（12,751 对 / 95 库 / 33.4 GB；Mini-Dev 780 条可冷启动）+ **BIRD-CRITIC** PG 分支（600 dev + 200 held-out OOD） | Spider 2.0（**仅季度上限探针**） | Spider 2.0 全量评测需注册 BigQuery service account key、Snowflake、ServiceNow、dbt Cloud 凭据 → **硬阻碍，不进常态主指标** |
| G7-Code | **BigCodeBench**（1,140，最贴办公脚本形态）+ **LiveCodeBench**（v6 已 1,055 题，时间切片抗污染） | SWE-bench Verified 抽 100 条季度跑 | HumanEval/MBPP **降为仅dev** |
| G8 | **无可直接采用者** | AIOpsLab（微软）、ITBench（IBM）—— 唯二覆盖「诊断→缓解」且自动判分，仓库活跃，但**是交互式 K8s 环境不是静态题库，题量合计不到 100 条** | **结论：G8 必须大比例自建。** 自建起点推荐 **RCAEval（MIT）+ Train-Ticket（Apache-2.0）+ Chaos Mesh（Apache-2.0）**——许可证干净、全可商用、仓库活跃 |
| G9 | 数据层无可直接用者；**框架层选 τ²-bench（Sierra，MIT）为主干**，AppWorld（Apache-2.0）为数据层与副作用检查并列参考 | WorkBench（域最接近）、OfficeBench（300 题，Apache-2.0）、ToolEmu（高风险场景）可改造骨架 | 见 3.6 |
| S | **SORRY-Bench** + **AIR-Bench 2024**（5,694，CC BY 4.0）+ **JailbreakBench**（MIT）+ **AgentDojo**（MIT，间接注入）+ **PrivacyLens**（493，MIT）+ **FalseQA**（2,365）+ **Agent-SafetyBench**（2,000，MIT）+ **OR-Bench-Hard-1K**（过度拒答配对） | Flames（中文，Apache-2.0）；HarmBench 当攻击生成器 | AIR-Bench taxonomy 出自 8 部政府法规 + 16 家公司政策，是唯一能让报告写出「对齐了哪条监管要求」的集 |

### 3.3 排除清单（与采用清单同等重要）

| 数据集 | 排除理由 |
|---|---|
| C-Eval / CMMLU | 学科选择题形态产不出 atomic facts + CC BY-NC-SA **不可商用** + 极高污染，三条都不利 |
| AGIEval | 考试导向，与办公事实问答无关；题目沿用各原始考试条款 |
| CLUE / SuperCLUE | 更像中文 NLP 综合榜，不是事实点召回评测；SuperCLUE 许可证与题量**未核实** |
| MMLU-Pro | 10 选项选择题产不出 atomic facts，也测不出幻觉率 |
| TriviaQA | 2017 年集，长期被当训练集，**污染到没有测量价值**；许可证三方表述冲突 |
| TruthfulQA | 几乎所有对齐数据集都拿它做过 RLHF/SFT 目标，早已过拟合；**只建议取其「误信陷阱」设计思路** |
| AdvBench | 2023 年，样本同质化 + refusal 关键词判分，用作准入必然虚高 |
| HumanEval / MBPP / Spider 1.0 | 降为 `仅dev`，**不得作准入依据**（污染实证见 3.5） |
| SheetCopilot | 代码 GPL-3.0 + 数据非商用 → **禁止引入** |
| CRMArena / CRMArena-Pro | CC BY-NC，不可商用 |
| BeaverTails / ALERT / R-Judge | NC 条款挡住商用路径（R-Judge 仍可用于校准 checker 本身） |
| L-Eval | GPL-3.0 传染性强，内部评测可用但**不要与产品代码混仓** |
| AgentHarm | 改版 MIT 带「仅限提升 AI 安全性」附加用途条款 → 建议**只参考分类法、不引入数据** |
| HaluEval | 是判别任务不是生成任务；只用来训练/校准我方幻觉判别器 |
| LogHub 系 | **不属于 G8**——是日志模板解析与异常二分类，与根因定位+修复差两个层级。但作为**合成种子**价值高（见 5.3） |

### 3.4 许可证审计

**① 可商用（Apache-2.0 / MIT / CC-BY）** —— 构成主盘骨干
SimpleQA Verified、Chinese SimpleQA、FRAMES、HalluQA、RULER、Loong、CLongEval、LongBench v2、BigCodeBench、LiveCodeBench、InfiAgent-DABench、DABStep(CC-BY-4.0)、PopQA、ClapNQ、τ²-bench、AppWorld、OfficeBench、AgentDojo、PrivacyLens、JailbreakBench、Agent-SafetyBench、AIR-Bench 2024、OR-Bench-Hard-1K、Flames、RCAEval、Train-Ticket、Chaos Mesh、HelpSteer3(CC-BY-4.0)、FLASK(CC BY 4.0)

**② 非商用（CC-BY-NC / research-only）** —— 按约束**不排除**，但对外发布须剔除
C-Eval、CMMLU、CRAG、MeetingBank、ELITR Minuting、DomainRAG、**DSBench**、CRMArena、BeaverTails、ALERT、R-Judge

**③ 需签协议 / 需注册获取**
Signal-1M（Signal Media 数据共享协议）、TREC-NEWS 与 Robust04（NIST/LDC user agreement，限制商业再分发）、BioASQ（须官网注册，CC BY 2.5 本身允许商用）、GPQA 与 AMI（可商用但需署名）、WorkArena（gated repo + ToU，且需连真实 ServiceNow 实例）

**④ 自定义 / 不明 / NOASSERTION**
- **MS MARCO**：微软自定非商用研究许可，明确不授予商用 IP 权利。**这是一条连带传染链**——TREC-DL、TREC RAG(V2.1 语料)、C-MTEB 的 MMarcoRetrieval **全部继承该约束**。
- **BEIR**：代码 Apache-2.0，但数据逐子集不同，维护者明确声明只做格式化与再分发、**不转让任何底层版权或使用许可**。18 个子集中至少 4 个（MS MARCO / Signal-1M / TREC-NEWS / Robust04）无法直接商用或无法自由分发 → **只能挑子集用，不能整包用。把 BEIR 整体标成 Apache-2.0 是错误的。**
- **LogHub / LogHub-2.0**：NOASSERTION（非标准开源），**商用需邮件申请**。
- **Eadro**：无 LICENSE 文件，且三年七个月未更新。

**⑤ 许可证表述冲突 —— 上生产前必须人工开仓核对原文**

| 数据集 | 冲突内容 |
|---|---|
| GPQA | 数据集卡 CC BY 4.0 vs 代码仓 `idavidrein/gpqa` 的 MIT 表述 → 商用前按 CC BY 4.0 从严处理 |
| TriviaQA | 代码 Apache-2.0 / Kaggle 镜像 CC0 / 原作者声明不拥有抓取内容版权 → 判定「许可证不干净」 |
| FaithBench | CC BY-NC-SA 4.0 与 CC BY-SA 4.0 并存（直接影响「可否商用」结论） |
| LongCite / LongBench-Cite | Apache-2.0 与 MIT 两种说法 |
| Defects4J | 二手资料称 Apache-2.0，GitHub API 实测为 MIT |

**⑥ 衍生数据风险**
- 源自 GPT-4 输出的集（部分 AlpacaEval / Nectar 子集）可能带 OpenAI ToS 衍生限制。
- 源自 GitHub 真实仓库的集（SWE-bench、BigCodeBench）底层代码许可证是**混合的**。
- Guard 模型：**Granite Guardian 是唯一许可证干净的开源 guard 模型（Apache-2.0）**；Llama Guard 走社区许可证带 MAU 条件，ShieldGemma 受 Gemma 使用政策约束，两者对外分发都要过法务。

**⑦ 若 benchmark 将来有商用 / 对外分发需求，必须处理的动作项**

1. LogHub 系 —— 邮件申请商用授权（或改用自建日志素材）
2. DSBench —— 谈授权（**这是补齐 G6 Excel 缺口最省力的单点**）
3. BEIR —— 逐子集挑选，剔除 4 个受限子集，不整包分发
4. MS MARCO 传染链 —— 确认 TREC-DL / C-MTEB MMarcoRetrieval 是否也要剔除
5. Llama Guard / ShieldGemma —— 若选用，走法务评估 MAU 条件与使用政策
6. AgentHarm —— 只取分类法，不引入数据
7. 五个表述冲突集 —— 人工开仓核对 LICENSE 原文
8. GPL 集（SheetCopilot、L-Eval）—— 确保不与产品代码混仓

### 3.5 污染审计

**已被污染但仍被广泛引用 —— 不得用作准入依据，只能作 dev：**

| 数据集 | 污染实证 |
|---|---|
| HumanEval | 每条 prompt 在 GitHub 上中位数 **99 次命中**；The Stack 里 **18.9%** 样本重合 |
| MBPP | 同源问题 |
| Spider 1.0 | o1-preview 类 agent 已达 **91.2% EX**，区分度耗尽 |
| Natural Questions | 2019 年集，维基正文 + 该集本身几乎必在所有预训练语料中（极高） |
| TriviaQA / TruthfulQA / AdvBench | 见 3.3 排除清单 |
| MT-Bench / AlpacaEval | 题目早已被广泛训练 |

**SWE-bench Verified 的隐性污染（特别提示）** —— 人工校验过 **≠** 干净：
- 500 条里 **97.8%** 的评测测试文件在 base_commit 前已公开
- **92.8%** 的修复 commit 能用 issue 号直接搜到
- **60.83%** 的题 issue 正文里就写了解法
- 过滤后平均解决率从 **51.7% 掉到 25.9%**
- 佐证：OpenAI 已于 2026 年 2 月停止报告其 Verified 分数

**有抗污染机制的集（应优先采用）：**

| 机制 | 代表 |
|---|---|
| 完全合成、结构上不可污染 | **RULER**（长度与 needle 内容可现场随机生成） |
| 发布日期时间切片 | **LiveCodeBench** |
| held-out OOD 分区 | **BIRD-CRITIC**（200 条 held-out） |
| 专家新写题、依赖长程推理而非记忆 | **LongBench v2**（2024-12） |
| 只公开部分数据 | **Flames**（公开 1k / 共 2,251） |
| 官方 canary + gated 访问 | GPQA（但前沿评测广泛使用，泄漏压力上升） |

**我方 canary 集设计原则（由上述机制提炼）：**

1. **canary 必须是合成的或专家新写的**，绝不能从公开集抽——公开集本身就是污染源。
2. **借鉴 RULER 的「现场生成」思路**：凡能参数化生成的门类（G3 needle、G7 SQL、G9 工具序列），canary 每次评测重新随机生成，从结构上消灭污染。
3. **借鉴 LiveCodeBench 的时间切片**：为 G7 建立按发布日期切片的持续保鲜机制。
4. **test/canary 分数背离即判污染**：某组合 test 分远高于 canary 分 → 判定污染，该轮结果作废。
5. **canary 的生成与验证只能用自托管模型**——发给第三方 API 做验证等于亲手把哨兵交给厂商。
6. **季度轮换 10%**，canary 单独保管、永不外泄。
7. 安全 S 类另需保留 **20–30% 不公开的 holdout 池并按季刷新**——静态公开安全集被吸收是结构性问题，只用公开集的 S 类分数**有效期最多 1–2 年**。

### 3.6 环境与工程成本

需要自建 **4 套环境**。这是排期的关键输入，工程量远大于数据标注。

| 环境 | 底座选型 | 关键理由 | 粗略工程量 |
|---|---|---|---|
| **SQL 沙箱** | 三层：L1(默认) **SQLite** 承载 BIRD/Spider1.0/自建中文库；L2(可选) **PostgreSQL in Docker** 承载 BIRD-CRITIC PG 分支；L3(专项) **DuckDB** 承载 Spider2-lite 本地可执行部分。**明确不上 BigQuery/Snowflake** | BIRD 全是 SQLite 单文件库，重置 = 复制一个文件（毫秒级）；33.4GB 是全量上限，Mini-Dev 只要几百 MB。**不要用 SWE-bench 的 Docker 当底座**：env 级缓存就要 120GB，全量镜像 240–684GB，重置是重建容器（秒级到分钟级），对高频短查询完全不划算 | 中 |
| **Python 沙箱** | 两个固定镜像（分析库 / BigCodeBench 139 库锁版本），每 task 全新容器 + 只读根 + tmpfs 工作区 + `--network=none` | 隔离与可复现 | 中 |
| **G9 Mock 工具环境** | **τ²-bench（MIT）为主干** + AppWorld（Apache-2.0）补 ORM 与副作用检查 | τ²-bench 的 `reward_basis` 是**乘积门控**（DB × COMMUNICATE × …），我方「越权误调用 = 0」可直接加一个 SAFETY 分量塞进去——**违规即 0 分，不用改判分主干**。且它默认**关闭**动作序列匹配、只比终态，恰好就是我方要的「多条合法路径都算完成」。域抽象干净到一个目录就是一个系统，照着长出 jira/ci/feishu/wecom/email 五个域即可 | **从零写 harness+判分器+快照并行保守 2–3 人月；基于 τ² 起步可压到 3–4 人周** |
| **G8 故障注入平台** | **RCAEval（MIT）+ Train-Ticket（Apache-2.0）+ Chaos Mesh（Apache-2.0）** | 许可证干净、全可商用、仓库活跃。**关键洞察：Chaos Mesh 的故障定义本身就是结构化 YAML——注入什么 = 标准答案是什么**，天然对齐，省掉人工标注 | 大 |

**SQL 状态重置的具体做法**：母本 `chmod 444` 放共享只读目录，每 task 起一个 tmpfs 目录用 `cp --reflink=auto` 复制、结束整目录 `rm -rf`，**绝不允许任务间共享同一 db 文件句柄**；PG 用 template database（`CREATE DATABASE task_x TEMPLATE bird_critic_base`，跑完 DROP），比重启容器快一到两个数量级，容器每 200 个任务回收一次防连接泄漏；每 task 前强制校验母本 checksum。

**限额与隔离**：单条 SQL 硬超时 30s（SQLite 用 `progress_handler` 中断，PG 用 `statement_timeout`），单 task 总超时 120s，容器 `--memory=2g`；默认只读连接，仅 DDL/DML 类任务才在 CoW 副本上开写；SQLite 关掉 `load_extension`，PG 用受限角色禁 `COPY ... TO PROGRAM` / `pg_read_file` / 大对象 / `dblink`；默认 `--network=none`。

**结果集等价判定规则**（checker 自己的 bug 会系统性污染所有指标且事后极难发现，**每条都要配单元测试**）：行序默认忽略但 `ORDER BY`+`LIMIT` 时严格、列序用二分图匹配、`NULL == NULL` 判等但不等于空串、金额用 Decimal 且 atol=0.01、全角半角 NFKC 归一、重复行计数敏感。

**一个提前知道的坑**：OSWorld 原版 369 题被社区（Moonshot、OpenAI、字节、Anthropic 等）挖出 **300+ 处评测器/指令问题**才有 OSWorld-Verified。**我方 verifier 从第一天就要版本化 + 保留 run artifact**，否则后期没法回答「判错是判分器的锅还是模型的锅」。

---

## 4. 【新增】适配层：公开集 → 统一 Schema

### 4.1 职责边界

适配层只做一件事：把各公开集的原始格式，**无损或可声明损失地**转换成 v0.1 的 Task Instance Schema，并绑定 checker。它**不做**数据清洗以外的语义改写，也不做难度的最终裁定（只给启发式初值，由基线实测反标）。

转换流水线：
```
加载 → 字段映射 → gold 构造 → checker 绑定 → difficulty 推断
     → lang 标注 → must_not 注入 → id 生成 → schema 校验 → 写出 JSONL + manifest
```

注册方式 `@register_adapter("bird_sql")`，统一接口 `convert(raw_record, cfg) -> TaskInstance | None`（返回 `None` 表示该条被过滤）。

### 4.2 五种 gold.type 的映射难点

| gold.type | 来源集 | 核心难点 |
|---|---|---|
| `executable` | BIRD / Spider / BigCodeBench / LiveCodeBench | 相对轻松：原始 gold SQL 或测试用例可机械转换 |
| `factlist` | SimpleQA / Chinese SimpleQA / FRAMES | **最大人工成本所在**。原始集多是「单个短答案」，我方要 atomic facts 清单。SimpleQA 类可机械转换（单事实题 → 单元素 facts 列表）；**FRAMES 多跳题必须人工拆点**（824 题拆成约 800 条 3–6 元事实，1 名标注员 2–3 天） |
| `rubric` | MT-Bench / AlignBench / WritingBench / IFEval | 原始集大多没有我方要的 5 维 rubric。**IFEval 这类可程序校验的约束应降级到 L1**（`format_compliance` checker），不要浪费在 L3 |
| `trace` | τ²-bench / AppWorld / WorkBench / OfficeBench | action sequence 或 DB 终态 → `{final_state, valid_sequences, forbidden_calls}`，需处理不可控字段 |
| `reference` | BEIR / MTEB / DABStep | **大语料下采样**是难点：要保 hard negatives，不能随机砍 |

**溯源与许可证元数据**：Schema 已冻结，不新增字段。`source` 写成 `public:<dataset>@<version>`，许可证、采样参数、转换损失等写进**随数据集一起版本化的 sidecar manifest**，以 `id` 关联。

### 4.3 代码现状（已实跑验证）

`adapter/` —— 零第三方依赖（dataclasses + unittest），**198 个单元测试全部通过**。

**已实现 9 个 adapter：**

| adapter | 门类 | gold.type | checker | 可商用 |
|---|---|---|---|---|
| `bird_sql` | G7 | executable | sql_result_equiv | conditional |
| `bigcodebench` | G7 | executable | exec_tests | yes |
| `simpleqa` / `chinese_simpleqa` / `frames` | G1 | factlist | fact_recall | yes |
| `beir` | G2 | reference | doc_recall_at_k | conditional |
| `dabstep` | G6 | reference | numeric_em | conditional |
| `ifeval` | G4 | rubric | format_compliance | yes |
| `tau2_bench` | G9 | trace | state_diff | yes |

**已实现 10 个 checker：**

| checker | 层 | 说明 |
|---|---|---|
| `must_not_guard` | L1 | **全局前置钩子**，任何 must_not 命中即 score=0 |
| `sql_result_equiv` | L1 | sqlite3 真实执行；行序/列序/浮点/NULL 感知的集合等价 |
| `exec_tests` | L1 | 子进程跑候选 Python + 单测，带超时 |
| `numeric_em` | L1 | 精确值匹配 + 数值容差 + 单位/百分比归一 |
| `state_diff` | L1 | 终态 diff，忽略自增 id / 时间戳，容忍多路径 |
| `format_compliance` | L1 | IFEval 式可验证约束，编码为 `ifeval:<name>:<arg>` |
| `fact_recall` | L2 | 原子事实点召回，judge 可注入（默认离线规则 stub） |
| `doc_recall_at_k` | L2 | Recall@k 主指标 + nDCG@10 子指标；**捏造 doc id 即 score=0** |
| `citation_groundedness` | L2 | 引用须能落到快照文档，引文 span 须逐字匹配 |
| `rubric_judge` | L3 | 加权 5 分制；未给 judge 时走离线确定性 stub |

**实跑记录**（本协调者在交付副本上独立复跑，非仅采信 worker 报告）：
```
python3 -m unittest discover -s tests   → Ran 198 tests, OK
python3 -m adapter list                 → 9 adapters / 10 checkers
python3 -m adapter convert --adapter bird_sql --in adapter/fixtures/bird_sql.jsonl --out out.jsonl
                                        → converted 3, filtered 1, errored 0（并产出 manifest）
python3 -m adapter validate --in out.jsonl → 3 rows, 0 invalid, RESULT: OK
```

**局限（如实）**：adapter 对着**自造的小型仿真 fixture** 跑通，**未接过任何真实公开集数据**——这是刻意设计（先保证转换逻辑正确，真实数据下载后再接），但意味着真实数据的字段边界情况尚未验证。

---

## 5. 【新增】LLM 合成数据流水线

### 5.1 流程与闸门

```
种子抽取 → 场景变体扩写 → 难度分级 → 反向生成(先 gold 后 prompt)
   → 多模型交叉生成 → 【确定性复核】 → 第三方模型验证
   → 去重 → 去污染 → 人审抽检 → 入库与版本化
```

**执行顺序与直觉不同，这是刻意的**：**确定性复核必须排在 LLM 验证之前**。一次 SQL 执行成本近零，一次三验证者投票是它的约四个数量级，前置能砍掉 **20–40%** 的坏样本。

**反向生成加了 Intent Bottleneck**：`gold → 业务意图摘要（只含语义、禁含解法结构词）→ 题面`。不加这一道，模型会把 `GROUP BY dept` 直接写成「按部门分组」，题目退化成翻译题。

### 5.2 红线：多模型交叉生成 + 第三方验证

形式化为五条集合约束（生成方 / 验证方 / 校准方三者与被测互不同源）。**「同源」按 vendor × 预训练血统判定，而非模型名**——同厂不同尺寸、同 base 不同微调、蒸馏子模型**全算同源**。

- 常备 **5 个 family** 做冗余；被测占掉一个则整族出池
- 剩余不足 2 个 → **BLOCKED，不降级**
- 代码落地：`ModelPool.assert_cross_provider()`，在构造池时、每次取 verifier 时、`cross_model_generate` 与 `independent_verify` 两阶段开头**共 4 处运行**，配 19 个单元测试；另支持 `exclude_providers`

### 5.3 各门类生成策略差异

| 门类 | 合成可行性 | 主要范式 | 种子来源 | 说明 |
|---|---|---|---|---|
| G7 / G9 | **高** | 反向生成 | DB schema / 工具 schema | **有确定性 checker，合成质量最可控，应优先做。** 也是唯一能算出各闸门真实 precision/recall 的门类——**先用它们把阈值调准，再做其他** |
| G6 | 高 | 反向生成 + 程序复算 | 表格素材 | 数值可用 pandas 复算 |
| G1 / G3 | 中 | 从文档抽取 | 内部 KB、会议纪要、邮件 | gold 靠多验证者投票，非确定性 |
| G8 | 中 | 从环境反推 | **LogHub 日志素材可作合成种子**（虽不能作题目）；Chaos Mesh 注入 YAML 天然是标准答案 | 修复命令白名单需人工维护 |
| G2 | 中 | 反向生成 | 受控文档库快照 | 假文档率判定逻辑可确定性自建（校验 doc_id 是否在快照 ID 集合内 + 引文 span 能否精确匹配），成本低 |
| S | 中高 | 载体 × payload × 位置 三层法 | AgentDojo workspace 域 + BIPIA payload 库 | 70% 以上样本可用 canary/witness 精确匹配做**零 judge 判定** |
| **G4 / G5 / G10** | **低（纯 rubric 部分）** | 以人工为主 | — | 见下 |

**关于 G4 / G5 / G10 的明确判断：**

> **纯 rubric 部分合成价值有限，应以人工为主。** 合成只产候选草稿、**100% 人工定稿**、总量压在 **20% 以内**。理由写实：rubric 的正确性无法被程序反查，多验证者投票也发现不了一套「平庸但自洽」的 rubric；judge 方差一旦超过模型间真实差异，这部分 benchmark 就只是在测噪声。

但有一个**高价值例外**：**G4-约束遵循 / G5-方案结构完整性 / G10-信息边界** 三个子集是可枚举可检查的，应改用 `factlist` 而非 `rubric`，**判分从 L3 降到 L1/L2**，直接服务 v0.1 的「L1 ≥40%」硬指标。**结论不是不做，而是拆成两半做。**

### 5.4 质量验收（要点）

完整方案见 `synth_qa_plan.md`，核心四块：

1. **难度校准** —— 锚点法（用公开集中难度已知的题做标尺，如 DABStep hard 档顶尖仅 14.55–16%、Spider 1.0 已达 91.2% EX）+ 通过率反标（L1 >0.8 / L2 0.4–0.8 / L3 <0.4）+ **区分度淘汰**（所有被测组合都对或都错的题对映射决策零信息量，应淘汰）+ 难度漂移周期重标。
2. **多样性** —— 表层（distinct-n / self-BLEU）+ 语义（embedding 聚类，检出「长尾坍缩」）+ 结构（G7 看 SQL 算子分布、G9 看调用步数分布）+ 元数据**联合分布**（只看边缘分布会漏掉「所有 L3 都是英文」）。
3. **分布对齐** —— 边缘用 KL/JS/Wasserstein；整体用**分类器双样本检验**（训分类器区分真实 vs 合成，AUC 越接近 0.5 越好）。诚实说明：G8/G9 本就缺真实流量，此项不适用。
4. **失败模式清单** —— 表面变体、模板泄漏、gold 泄漏、self-preference、难度塌缩、分布偏移、长度偏置、事实虚构、多解未记、翻译腔、验证者共谋、近似去重过松 —— 每条配可操作检出手段。

**三条写进硬规则的坑：**

- **强基线 pass@1 = 0 的题不得自动标 L3** —— 先让验证者判是「能力问题」还是「题面问题」。反向生成 + 严 checker 最常见的产出就是**人也做不出的怪题，而它们长得正好像 L3**。
- **语义去重必须与 gold 联合判定** —— prompt 像但 gold 不同的样本要**保留并标 `contrast_pair`**，那是最有价值的对照组，纯 embedding 去重会把它们删光。
- **去污染只判 `(prompt, gold)` 配对，不判 `context`** —— KB 文档与公网重叠是正常的，混为一谈会误杀几乎所有基于公开手册的题。

**去重阈值不给拍脑袋数字**：方法是标 200 对画 ROC 取 FPR ≤5% 的点。企业单域语料相似度天然高于通用语料，**套论文阈值会误删过多**。

### 5.5 代码现状（已实跑验证）

`synthgen/` —— 零第三方依赖（Python 3.9.6 实测无 pydantic / 无 pytest，故用 dataclasses + unittest），**138 个单元测试全部通过**。

已实现 **G7（SQL）** 与 **G9（工具操作）** 两门类的 generator + verifier：
- **G7**：受 seed 控制随机生成业务 schema + 造数 → 按难度模板生成 gold SQL（L1 单表聚合 / L2 JOIN+GROUP BY / L3 窗口函数、子查询）→ **标准库 sqlite3 实际执行**拿参考结果集 → 倒推中文 prompt。verifier 的列序/行序/ORDER BY 敏感/浮点容差/NULL/重复行**六条等价规则各有独立用例**。
- **G9**：纯内存 Mock 环境（issue tracker + CI + 角色权限模型），反向生成目标终态 → 求合法调用序列 → 倒推 prompt。verifier 做状态 diff，**越权与破坏性调用判 0 分并写 violations**，字段归一化与多路径全 1.0 均有测试。

**实跑记录**（本协调者在交付副本上独立复跑）：
```
python3 -m unittest discover -s tests   → Ran 138 tests, OK
python3 -m synthgen generate --category G7 --n 5 --dry-run --seed 42 --out g7.jsonl
   → 生成 5/5；难度分布 {L1:2, L2:2, L3:1}；打回 1 条(dedup)；成本 tokens=1663
   → 模型角色 generator=stub_alpha / rewriter=stub_beta / verifier=stub_gamma（跨源约束生效）
python3 -m synthgen generate --category G9 --n 5 --dry-run --seed 42 --out g9.jsonl
   → 生成 5/5；打回 2 条(dedup)；成本 tokens=3255
python3 -m synthgen validate --in g7.jsonl  → 5 条, 合法 5, 非法 0
python3 -m synthgen verify   --in g9.jsonl  → 5/5 passed, 平均分 1.0000
```
另经 worker 验证：故意提交 `DROP TABLE orders; SELECT 1` → score 0、`violations=["执行 DROP","多语句提交"]`、退出码 1；同 seed 两次生成 `diff -q` 逐字节一致。

**局限（如实）**：
1. **只实现 G7 和 G9**，其余门类未写（schema 与注册表已支持，`--category G3` 会 fail fast）。
2. **真实 LLM 路径从未跑过任何一次真实调用** —— 只写了 `LLMClient` 契约与注入方式；非 dry-run 且无配置时 CLI 以退出码 2 明确拒绝，**不会偷偷跑 stub**。
3. `python3 -m pytest` 未执行过（环境无 pytest）；用例是标准 `unittest.TestCase`，理论上可被 pytest 收集，但**此条未验证**。
4. 其余 17 项边界局限（G7 列数 >6 时按原序比、`CREATE` 一刀切拉黑导致候选只能用 CTE、G9 多路径仅来自可交换步骤两两对调、dry-run 下第三方评审分是伪随机**不能当质量信号**等）在 README 第 10 节逐条列出。

### 5.6 成本估算

生成 1000 条最终样本（约 1800 候选）：

| 项 | 估算 | 说明 |
|---|---|---|
| LLM 侧 | **$230–380**，按 1.5–2 倍计预算 **$350–600** | 最大头是**难度反标（占 48%）**，分层采样可砍 60% |
| **人审侧** | 首次建库约 **52 工时、含专家约 ¥9,000+** | **是 LLM 侧的两倍多，才是成本主项** |
| 周期 | 5–8 个工作日 | 瓶颈在人审队列与打回往返，**不在算力** |

**降本重点不是压 token，而是把自动闸门做严以减少需人审的量。**（以上为估算，假设已在 `synth_pipeline_design.md` 中列明。）

---

## 6. 【核心交付】各门类「公开集 / 合成 / 人工标注」三方配比建议

### 6.1 配比总表（V1.0 满量口径）

前提：每门类 test 集 150–300 条，L1:L2:L3 = 3:5:2。下表按「**一道成品题的来源**」划分，百分比之和为 100%。
「人工标注」指必须由人产出或定稿金标的部分，**不含**对公开集/合成集的抽检工时。

| 门类 | 公开集 | 合成 | 人工标注 | 建议 test 题量 | 配比理由 |
|---|---:|---:|---:|---|---|
| **G1 知识问答** | **35%** | 45% | 20% | 200 | 公开集可覆盖 ≈35%（SimpleQA 双语主盘）。内部 KB 问答与多轮事实一致性公开集为 0，只能合成；FRAMES 拆 atomic facts 与内部术语表需人工 |
| **G2 信息检索** | **45%** | 35% | 20% | 250 | 可覆盖 40–50%，基础检索排序公开集充分。**权限隔离检索 0% 必须 100% 自建**；假文档率判定逻辑可确定性自建、成本低，故合成占比可提高 |
| **G3 内容理解** | **40%** | 35% | 25% | 250 | 可覆盖 ≈45%，但「形态对口而金标要全部重标」，故实际记 40%。**中文会议纪要公开集没有**；Action Item 的 schema（负责人/截止/状态）必须人工定义与标注，人工占比最高之一 |
| **G4 文案撰写** | **25%** | 25% | 50% | 200 | 数据侧仅 25–30%（IFEval/CFBench 的机械格式合规可直接用并降到 L1）。**rubric 合成价值有限**，中文办公文体与企业格式规约必须人工，故人工占一半 |
| **G5 方案设计** | **0%** | 20% | **80%** | 100 | **公开集可用题目 0 条，必须全自建。** 合成只产候选草稿、100% 人工定稿。建议起步 80–120 道（技术方案/项目规划/流程改造各 30–40），每题配 8–15 条风险要素清单 + 一份基线方案供 pairwise |
| **G6 数据分析** | **35%** | 45% | 20% | 200 | 可覆盖 35–45%。**数值可程序复算**故合成质量可控、占比高。Excel 形态（合并单元格/多 sheet/公式列/透视表）与中文口径必须自建；若 DSBench 授权谈成，公开集可上调至 45% |
| **G7 代码与 SQL** | **50%** | 40% | 10% | 300 | SQL 45–55% / Code 50–60%，是公开集最能打的门类。**有确定性 checker，合成最可控**；国内数仓方言（Hive/MaxCompute/Doris/ClickHouse/StarRocks）零覆盖靠合成。人工占比最低 |
| **G8 故障诊断** | **15%** | 55% | 30% | 150 | 可覆盖 15–20%，**没有一个公开集能直接用**。合成占比最高——Chaos Mesh 注入 YAML 天然是标准答案，LogHub 可作素材种子。**修复命令白名单 0% 覆盖、必须人工维护**，是 G8 工作量最大的单点 |
| **G9 工具与系统操作** | **10%** | 60% | 30% | 250 | **数据层仅 10–15%**（框架层 70–80% 是另一回事，不计入此表）。有状态 diff 确定性判分，合成最可控故占比最高。飞书/企微零覆盖无参照物，工具 schema 与权限模型必须人工定义 |
| **G10 工作沟通与建议** | **15%** | 25% | **60%** | 150 | 可覆盖 15–20%，且主要是「素材」和「偏好校准锚」而非题目。SOTOPIA 是生活社交、ESConv 是心理支持、CaSiNo 是物资协商，**没有一个是职场**。中文职场语境不能靠翻译迁移 |
| **S 安全合规（横切）** | **55%** | 30% | 15% | 300 | 可覆盖 55–60%，是公开集覆盖率第二高的类别。间接注入可用「载体×payload×位置」三层法批量合成。中文 PII（仅 15–20%）、企业数据分级、PIPL 专项必须人工 |

### 6.2 全局汇总

| 来源 | 加权占比（按上表题量） | 绝对量级（按 2,350 条 test 集） |
|---|---:|---:|
| 公开集 | **≈32%** | ≈750 条 |
| 合成 | **≈40%** | ≈950 条 |
| 人工标注 | **≈28%** | ≈650 条 |

> **本版判断**：加权按上表「建议 test 题量」列计算。这组数字的含义是——**合成流水线不是可选项，它承担了最大的单一份额**；而人工 28% 看似不高，但集中在 G5/G10/G4 三个最难自动化的门类，**实际工时占比远高于 28%**（参见 5.6：人审成本是 LLM 侧的两倍多）。

### 6.3 Judge 校准集（独立于上表）

Judge 校准不产出 benchmark 题目，但决定 L3 分数可不可信，单列：

| 来源 | 占比 | 说明 |
|---|---:|---|
| 公开集 | **70–80%** | 英文侧准入体检、对抗性测试、客观标签反测、人类偏好锚四条链路均有可商用成熟集（ODC-BY / MIT / CC-BY-4.0），基本不需自建 |
| 人工自标 | 20–30% | **缺口只在中文**：中文场景 κ ≥ 0.7 必须靠自标样本证明。建议每门类 100–150 条 × 3 名标注员，中文自标 300–450 条做 κ 的正式测算 |

### 6.4 分阶段的配比演进

配比不是一开始就按 V1.0 执行。冷启动应**先吃公开集**，因为它最快、最便宜、且能立刻标定基线。

| 阶段 | 题量 | 公开集 | 合成 | 人工 | 重点 |
|---|---|---:|---:|---:|---|
| **V0.1 冒烟**（2–3 周） | 20 条/门类 | **70%** | 20% | 10% | 先建 G7 SQL 沙箱 + G9 Mock 环境；打通 L1 判分器；验证 schema 与 checker 设计。**先只做 G7+G9 跑通全链路**——它们是唯一能算出各闸门真实 precision/recall 的门类，用它们把阈值调准再铺开 |
| **V0.5**（4–6 周） | 80–100 条/门类 | 50% | 35% | 15% | 接入 L2/L3；完成 Judge 人工校准（κ ≥ 0.7）；合成流水线接真实 LLM；门槛值标定 |
| **V1.0**（8–10 周） | 150–300 条/门类 | **32%** | 40% | 28% | 满量；对抗集 + 安全集齐全；canary 建立；出正式准入报告 + Router 路由表 |
| **持续** | — | — | — | — | 季度轮换 canary、线上回流补数据、Judge 重校准、G7 时间切片保鲜 |

**V0.1 的 P0 清单**（可直接照着下载执行）：BIRD Mini-Dev（780 条，几百 MB）、SimpleQA Verified + Chinese SimpleQA、RULER（现场生成）、IFEval、DABStep、AgentDojo、OR-Bench-Hard-1K。这几个的共同点是**许可证干净、环境轻、可立即起跑**。

---

## 7. 评估方案与指标（承接 v0.1，本版仅列修订）

v0.1 第 3、4 章（三层判分引擎、Judge 治理、运行协议、四象限指标、准入合取规则、映射效用函数）**整体沿用**。v0.2 提出三处修订：

| # | 修订 | 理由 |
|---|---|---|
| 1 | **Judge 不得与合成数据生成模型同源** | 否则 rubric 题会系统性偏袒模仿了生成器文风的被测模型（见 1 章） |
| 2 | **G4/G5/G10 拆出可枚举子集**（G4-约束遵循、G5-方案结构完整性、G10-信息边界），判分从 L3 降到 L1/L2 | 直接服务「L1 ≥40%」硬指标，且是这三个门类唯一能确定性判分的部分 |
| 3 | **越权类指标绝不能用 LLM judge** | 要求「= 0」而 judge 误判率非零，**数学上不成立**。必须用工具白名单 + 参数正则的确定性 checker |

另补充两条来自调研的实证，支持 v0.1 的既有设计：
- **间接提示注入必须零容忍、不能设阈值**：WASP 测出间接注入在 86% 的运行中部分成功；SEP 测出 GPT-4 级模型的指令-数据分离分数**低于**小模型——**风险与能力正相关**。已核实基线显示模型间 ASR 差 7 倍（GPT-4o 53.1% vs Claude 3.7 Sonnet 7.31%），**区分度足够做门槛**。
- **必须配 over-refusal 反向指标**：只看违规率会选出一个什么都不干的模型。推荐 OR-Bench-Hard-1K（自带 600 条 toxic 对照，防反向作弊）。

---

## 8. 待决策事项

| # | 事项 | 建议 | 紧迫度 |
|---|---|---|---|
| 1 | **DSBench 授权** —— 466 条 Excel/财务建模题，G6 办公契合度最高但 non-commercial | 谈授权是补齐 G6 Excel 缺口**最省力的单点**；谈不成则 G6 公开集占比从 45% 回落到 35% | 高 |
| 2 | **benchmark 是否对外分发 / 商用** | 决定 3.4 节 8 个动作项做不做。若纯内部使用，NC 集可直接用，工作量大幅下降 | 高 |
| 3 | **G9 框架选型拍板**：基于 τ²-bench 起步 vs 从零自建 | 强烈建议前者：**2–3 人月 → 3–4 人周** | 高 |
| 4 | **G5 是否值得做满** | 公开集 0 覆盖、80% 人工。若资源紧张，建议 V1.0 只做 80 道而非 150–300 道 | 中 |
| 5 | **五个许可证冲突集**人工开仓核对 | GPQA / TriviaQA / FaithBench / LongCite / Defects4J | 中 |
| 6 | **真实流量脱敏样本的获取路径** | 分布对齐检验与种子抽取都依赖它；G8/G9 本就缺，需确认其他门类能否拿到 | 中 |
| 7 | **被测组合的厂商清单** | 决定合成模型池要排除谁。常备 5 family，被测占一个则整族出池，**剩余不足 2 个直接 BLOCKED** | 中 |
| 8 | **Guard 模型选型** | Granite Guardian（Apache-2.0）是唯一许可证干净的；若要用 Llama Guard / ShieldGemma 需过法务 | 低 |

---

## 9. 十条开放问题（诚实交代，业界暂无好解法）

1. **闭源模型的训练集无法检查** —— 只能靠扰动对照组这一行为学信号间接推断。
2. **多验证者的共同盲区** —— 投票机制解决不了所有验证者都错的情况。
3. **题面自然度与 gold 精确性存在根本张力** —— 取舍是 L1/L2 偏自然、L3 偏精确。
4. **难度标签随基线模型换代漂移** —— 需周期重标，但重标本身会打断跨期可比性。
5. **rubric 正确性无法被程序反查** —— G4/G5/G10 的根本困境。
6. **G8/G9 缺真实流量**，分布对齐检验在这两个门类不适用。
7. **静态公开安全集被吸收是结构性问题** —— 只用公开集的 S 类分数有效期最多 1–2 年。
8. **PIPL/个保法专项评测尚处学术拟定阶段** —— 工业界目前靠内部红队。
9. **中文 PII 识别** —— Presidio 默认不支持中文本地化；身份证号、中文姓名需自建 recognizer，且身份证/银行卡**必须做校验位验证**否则误报率不可用。
10. **判分器自身的 bug 会系统性污染所有指标且事后极难发现** —— 唯一对策是给每条等价判定规则配单元测试 + verifier 版本化 + 保留 run artifact。

---

## 10. 与 v0.1 落地节奏的对照

v0.1 的 V0.1 / V0.5 / V1.0 三阶段**继续有效**，v0.2 补充了每阶段的数据来源配比（见 6.4）与两条排序建议：

1. **G7 沙箱与 G9 Mock 环境最先启动** —— v0.1 已指出它们工程量最大；v0.2 进一步发现它们也是**唯一能标定合成闸门阈值的门类**，双重理由要求它们排在最前。
2. **公开集冷启动优先** —— V0.1 阶段公开集占 70%，用最低成本把流水线跑通并拿到基线，再逐步把比例让给合成与人工。

---

## 11. 配套产物清单与溯源

所有文件位于本次交付的共享目录。

**冻结规范**
- `SCHEMA_v0.1.md` —— 统一 Task Instance Schema、门类定义、checker 签名、三层引擎。**adapter 与 synthgen 双方共同遵守的唯一权威。**

**公开集调研（7 份，每个数据集均经实际检索核实，未核实字段原样标注）**
- `research_G1G3.md` / `research_G2.md` / `research_G4G5G10.md` / `research_G6G7.md` / `research_G8.md` / `research_G9.md` / `research_safety.md`

**映射与审计（4 份分片）**
- `mapping_part_A.md`（G1/G3/G2）、`mapping_part_B.md`（G4/G5/G10 + Judge 校准）、`mapping_part_C.md`（G6/G7/G8）、`mapping_part_D.md`（G9 + S）
- 每份含：主映射表（含定位与排除清单）、可覆盖比例表、许可证要点、污染要点、冲突待裁决清单

**适配层**
- `adapter_design.md` —— 设计文档
- `adapter/` —— 9 adapter + 10 checker，**198 测试通过**（含金标闭环门禁），零第三方依赖

**合成数据**
- `synth_pipeline_design.md` —— 17 章流水线设计（含 Mermaid/ASCII 流程图、10 道闸门与打回路径、成本估算、10 条开放问题）
- `synth_qa_plan.md` —— 质量验收：难度校准 / 多样性 / 分布对齐 / 失败模式清单
- `synthgen/` —— G7 + G9 generator/verifier，**138 测试通过**，零第三方依赖

**本文档**
- `benchmark_plan_v0.2.md`

> **溯源说明**：本文档第 3 章所有数据集事实引自上述 7 份调研报告与 4 份映射分片；第 4、5 章引自 `adapter_design.md`、`synth_pipeline_design.md`、`synth_qa_plan.md` 及两套代码的 README 验证记录。**第 4.3 与 5.5 节的实跑记录由协调者在交付副本上独立复跑确认，非仅采信 worker 自述。** 第 6 章配比表为本版判断，依据是各调研报告的可覆盖比例估计 + 各门类判分可确定性程度，已在「配比理由」列逐行说明。
