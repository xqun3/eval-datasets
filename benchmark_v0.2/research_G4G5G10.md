# G4 文案撰写 / G5 方案设计 / G10 工作沟通与建议 —— 公开数据集选型调研

> 调研范围：主观 / LLM-as-Judge 型三个门类（G4、G5、G10）+ Judge 可靠性校准集。
> 全部条目通过 `google_search` 实际检索核实；**核实不到的字段一律写「未核实」并说明查了什么**，不做记忆填空。
> 调研时间：2026-09。

## 0. 先说结论（TL;DR）

| 门类 | 公开集**数据**可直接/改造后用的比例（估计） | 公开集**方法/范式**可借鉴程度 | 结论 |
|---|---|---|---|
| **G4 文案撰写** | **约 25–30%** | 高（Rubric 生成范式、格式硬校验可直接搬） | 部分借数据（WritingBench 商务/营销子域 + LongBench-Write 中文 + IFEval/CFBench 做格式合规）；**中文办公文案（邮件/周报/通知/公文）必须自建** |
| **G5 方案设计** | **< 10–15%** | 中（只有 Rubric 维度与 checklist 范式可借） | **没有对口公开集，必须全自建。** 现有 planning 类（PlanBench / Natural Plan / TravelPlanner）是**可验证规划**，与「开放式方案设计」**不同源，不要混为一谈** |
| **G10 工作沟通与建议** | **约 15–20%** | 中高（偏好对构造、情境化 rubric 可借） | 数据基本自建；SOTOPIA / ESConv / CaSiNo 提供的是**情境构造方法**而非可用题目 |
| **Judge 校准** | **约 70–80%（唯一数据侧充裕的一块）** | 高 | RewardBench 2 + LLMBar + JudgeBench + Auto-J 可直接做 κ 校准底座，**这是本次调研里性价比最高的部分** |

三个门类里，**只有 Judge 校准这一块公开数据是真正够用的**。G4/G5/G10 的题目本体几乎都要自建，公开工作的价值集中在 **Rubric 设计方法论 + Judge 去偏协议**（见第 3 节）。

---

## 1. 主表

### 1.1 基础信息表

| # | 数据集 | 发布方 | 年份 | 规模 | 语言 | 任务形态 | 获取方式 |
|---|---|---|---|---|---|---|---|
| 1 | **MT-Bench** | LMSYS (Zheng et al.) | 2023 | 80 题（8 类 × 10） | EN | 多轮开放式问答 | GitHub `lm-sys/FastChat`（含 llm_judge 子目录） |
| 2 | **MT-Bench-101** | Bai et al. (ACL 2024) | 2024 | 1,388 段对话 / 4,208 轮 / 13 任务 | EN | 细粒度多轮对话 | GitHub `mtbench101/mt-bench-101` |
| 3 | **Arena-Hard-Auto** | LMSYS / LMArena | 2024 | 500 prompts | EN | 真实用户难题 pairwise | GitHub `lmarena/arena-hard-auto` |
| 4 | **AlpacaEval 2.0** | Stanford Tatsu Lab (Dubois et al.) | 2024 | 805 instructions | EN | 单轮指令 pairwise（LC win-rate） | GitHub `tatsu-lab/alpaca_eval` |
| 5 | **WildBench** | AI2 (Lin et al.) | 2024 | 1,024 真实任务 | 多语（以 EN 为主） | 真实对话日志难任务 | GitHub `allenai/WildBench` / HF `allenai/WildBench` |
| 6 | **LMSYS Chatbot Arena 33k** | LMSYS | 2023 | 33k 对话（人类偏好） | 多语 | 人类 pairwise 偏好 | HF `lmsys/chatbot_arena_conversations` |
| 7 | **HelpSteer2** | NVIDIA | 2024 | 10,681 prompts / ≈21.3k 标注响应对 | EN | 多维人工打分（helpfulness 等） | HF `nvidia/HelpSteer2` |
| 8 | **HelpSteer3** | NVIDIA | 2025-03 | 40,476 偏好样本（含人工 1–2 句理由） | 多语（General/STEM/Coding/Multilingual） | 人类偏好对 + 理由 | HF `nvidia/HelpSteer3` |
| 9 | **Nectar** | Berkeley-NEST | 2023 | 183k prompts × 7 responses（≈3.8M pairwise） | EN | GPT-4 排序偏好 | HF `berkeley-nest/Nectar` |
| 10 | **WritingBench** | 阿里 X-PLUG + 人大 + 上交 | 2025 | 1,239 写作 query / 6 大域 / 100 子域 | EN + ZH | 开放式写作 + **实例级 5 条 criteria** | GitHub `X-PLUG/WritingBench`；critic 模型 HF `WritingBench-Critic-Model-Qwen-7B` |
| 11 | **EQ-Bench Creative Writing (v3)** | Sam Paech | 2024–2025 | 32 prompts × 3 iterations = 96 项 | EN | 创意写作 rubric + Elo | GitHub `EQ-bench/creative-writing-bench` |
| 12 | **EQ-Bench（情商 / roleplay）** | Sam Paech | 2023–2025 | 45–60 情境（版本而异） | EN | 情绪理解打分 / roleplay | GitHub `EQ-bench` 系列 |
| 13 | **LongWriter / LongBench-Write** | THUDM 清华 | 2024 | 120 prompts（60 EN + 60 ZH），4 个长度档 | EN + ZH | 长文写作 + 字数约束 | GitHub `THUDM/LongWriter` |
| 14 | **HelloBench** | Quehry et al. | 2024 | 647 样本 / 5 类 / 38 子类 | EN | 开放式长文生成 + HelloEval checklist | GitHub `Quehry/HelloBench` / HF `quehry/HelloBench` |
| 15 | **ProxyQA** | 华为诺亚方舟 + 港理工等（ACL 2024） | 2024 | 规模**未核实** | EN | 长文生成 → proxy-question 覆盖度评估 | arXiv:2401.15042（仓库/许可证未核实） |
| 16 | **AlignBench** | THUDM 清华 | 2023–2024 | 683 中文 query / 8 大类 | ZH | 中文对齐开放式评测 + CritiqueLLM | GitHub `THUDM/AlignBench` |
| 17 | **SuperCLUE** | CLUEbenchmark | 2023– | 核心评测集**不公开** | ZH | 中文综合 + CArena 对战 | GitHub `CLUEbenchmark/SuperCLUE`（仅部分 SuperCLUE-Open 样例） |
| 18 | **CHC-Bench** | MAP (CT-LLM) | 2024 | 214 条中文 hard case / 8 类 | ZH | 中文难指令 | 随 CT-LLM 发布（GitHub/HF） |
| 19 | **CLEVA** | 港中大 LaVi Lab + 上海 AI Lab | 2023 | 31 任务 / ≈370k 中文样本 | ZH | 中文综合评测平台（已接入 HELM） | CLEVA 官方 / HELM |
| 20 | **IFEval** | Google Research (Zhou et al.) | 2023 | 541 prompts / 25 种可验证指令 | EN | 规则可校验的格式指令遵循 | GitHub `google-research/instruction_following_eval`；HF 有镜像 |
| 21 | **Multi-IF** | Meta | 2024 | 4,501 段三轮对话 / 8 语种（含中文） | 多语 | 多轮多语指令遵循 | HF `facebook/Multi-IF` |
| 22 | **FollowBench** | Jiang et al. (ACL 2024) | 2023–2024 | 规模**未核实** | EN（+部分 ZH，未核实） | 多层级细粒度约束（内容/情境/风格/格式/示例） | GitHub `YJiangcm/FollowBench` |
| 23 | **InFoBench** | Qin et al. | 2024 | 500 instructions（分解式 DRFR） | EN | 需求分解式指令遵循 | GitHub `qinyiwei/InFoBench` / HF |
| 24 | **CFBench** | 百度 + 北大 + 百川 | 2024-08 | 1,000 条中文样本 / 10 大约束类 / 25+ 子类 | ZH | 中文综合约束遵循 | GitHub `PKU-Baichuan-MLSystemLab/CFBench`（arXiv:2408.01122） |
| 25 | **OfficeBench** | 学术（arXiv 编号未核实） | 2024 | 规模**未核实** | EN | Office 应用 **agent 操作**（Word/Excel/PDF/Calendar/Email） | GitHub（`zlwang-cs/OfficeBench`，仓库名未核实） |
| 26 | **QMSum** | Yale LILY | 2021 | 1,808 query-summary 对 / 232 场会议 | EN | 会议查询式摘要 | GitHub `Yale-LILY/QMSum` |
| 27 | **MeetingBank** | Hu et al. | 2023 | 1,366 场会议 / 6,892 段级摘要对 | EN | 市政会议摘要 | Zenodo / HF |
| 28 | **EnronQA** | 学术（arXiv 编号未核实） | 2025 | 103,638 邮件 / 528,304 QA 对 / 150 邮箱 | EN | 私域邮件 QA / 检索 | HF（具体 repo 未核实） |
| 29 | **PlanBench** | Kambhampati 组（ASU） | 2022–2023 | 规模**未核实** | EN（PDDL 模板生成） | 可验证符号规划 | GitHub `karthikv792/LLMs-Planning` |
| 30 | **Natural Plan** | Google DeepMind | 2024 | 规模**未核实**（3 域：Trip / Meeting / Calendar） | EN | 自然语言规划（约束可验证） | GitHub `google-deepmind/natural-plan` |
| 31 | **TravelPlanner** | OSU NLP | 2024 | 1,225 queries（45 train / 180 val / 1000 test） | EN | 带 13 项硬约束的行程规划 | GitHub `osu-nlp/TravelPlanner` |
| 32 | **EngDesign** | NeurIPS 2025 D&B | 2025 | 开源子集 `EngDesign-OPEN` 53 任务 | EN | 工程设计（仿真脚本判分） | 仓库/许可证**未核实** |
| 33 | **BizCompass** | Hao et al.（Findings of ACL 2026） | 2026 | 规模**未核实** | EN（中文覆盖未核实） | 商业推理（分析师/交易员/顾问角色） | 官网 `bizcompass.dev...`（可访问性与许可证**未核实**，**低置信**） |
| 34 | **EnterpriseClawBench** | FrontisAI | 2026-06 | 852 任务（Lite 子集 120） | EN | 企业 agent 工作流 | GitHub `FrontisAI/EnterpriseClawBench`；**原始数据不公开，仅开源构建与评测代码** |
| 35 | **SOTOPIA** | CMU 等 | 2023–2024 | 90 社交情境 × 40 角色画像 | EN | 目标驱动社交交互（含协商/冲突） | GitHub `sotopia-lab/sotopia` |
| 36 | **ESConv** | Liu et al. | 2021 | 1,300 段情感支持对话 / 10 类问题 | EN | 情感支持对话 | GitHub / HF |
| 37 | **CaSiNo** | Chawla et al. (Cornell/USC) | 2021 | 1,030 段协商对话 | EN | 多轮资源协商 | Cornell NLP / HF |
| 38 | **JudgeBench** | ScalerLab | 2024 | 350 对（GPT-4o 生成）+ 270 对（Claude 3.5 生成） | EN | **Judge 元评测**（客观可判定标签） | GitHub `ScalerLab/JudgeBench` |
| 39 | **RewardBench** | AI2 | 2024-03 | 2,985 条 (prompt, chosen, rejected) | EN | 奖励模型/Judge 元评测 | HF `allenai/reward-bench` |
| 40 | **RewardBench 2** | AI2 | 2025 | 1,865 条（best-of-4 形式） | EN | 奖励模型元评测（更抗污染） | HF `allenai/reward-bench-2` |
| 41 | **LLMBar** | Princeton NLP | 2023–2024 | 419 对（Natural + Adversarial） | EN | Judge 抗干扰元评测 | GitHub `princeton-nlp/LLMBar` |
| 42 | **JudgeLM-100K** | Zhu et al. | 2023 | 100k 训练 + 5k 验证（GPT-4 判分） | EN | Judge 训练数据 | GitHub `baaivision/JudgeLM`（HF 数据卡） |
| 43 | **Auto-J** | GAIR（上交） | 2023 | 覆盖 58 个真实场景 | EN + ZH（6B 双语版） | 生成式 Judge（pairwise + 单响应 critique） | GitHub `GAIR-NLP/auto-j` |
| 44 | **Prometheus 2 / Feedback Collection / Preference Collection** | KAIST | 2023–2024 | Feedback Collection：1,000 rubric / 20k 指令 / 100k 反馈；Preference Collection：1k 自定义准则 pairwise | EN | 定制 rubric 评估器 + 训练数据 | GitHub `prometheus-eval/prometheus-eval` |
| 45 | **FLASK** | KAIST | 2023–2024 | 1,740 实例 / 4 能力 / 12 细粒度技能 | EN | 技能级细粒度评测 | GitHub `kaistAI/FLASK` |
| 46 | **G-Eval** | Liu et al. (MSR) | 2023 | 方法（非数据集） | EN | CoT + form-filling 打分范式 | GitHub `nlpyang/geval` |
| 47 | **RubricEval** | 复旦 + 蚂蚁（arXiv:2603.25133） | 2026-03 | 3,486 条 rubric 级判定实例（2,034 Easy / 1,452 Hard） | EN（中文覆盖未核实） | **rubric 级** Judge 元评测 | 仓库与许可证**未核实**，**低置信** |

### 1.2 评估适配表

| # | 数据集 | 金标形式 | 默认判分方式 | 许可证 | 可商用？ | 污染风险 | 对应门类 | 契合度 | 直采 or 改造 | 一句话评价 |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | MT-Bench | 无参考答案，GPT-4 单点 1–10 | LLM-as-Judge（单点 + pairwise） | Apache-2.0 | ✅ 代码可商用；题目为人工编写 | **高**：2023 年起 80 道题几乎进了所有后训练评测环路，榜单饱和、位置/冗长偏差已被反复记录 | G4(弱)/Judge 校准 | 低 | 仅借方法 | 历史地位重要，但**题量太小、污染太重**，不建议进正式题库 |
| 2 | MT-Bench-101 | 13 类任务的细粒度 rubric | LLM-as-Judge 分任务打分 | Apache-2.0 | ✅ | 中：发布较晚但已公开两年 | G10（多轮沟通范式）/Judge | 中 | 改造 | **多轮能力分层 taxonomy 值得抄**，数据本身偏通用对话 |
| 3 | Arena-Hard-Auto | 与基线模型 pairwise | GPT-4 系 judge + Bradley-Terry + 95% CI | Apache-2.0 | ✅ 代码；题目源自真实用户 prompt | **高**：500 题公开且被广泛用作调参目标 | G5(弱)/Judge 校准 | 低-中 | 仅借方法 | **win-rate + 置信区间 + style control 的统计流程是 G5 pairwise 的最佳模板** |
| 4 | AlpacaEval 2.0 | 与 GPT-4-turbo 基线 pairwise | GPT-4 judge + **长度控制（GLM 回归）** | Apache-2.0（代码） | ⚠️ 代码可商用，但**部分数据/评测标签源自 OpenAI API 输出，受 OpenAI ToS「不得用于开发竞争模型」约束**，商用训练需法务确认 | **高**：805 题是公开优化目标，length-hacking 众所周知 | G4(弱)/Judge 校准 | 低 | 仅借方法 | **length-controlled win-rate 必须借鉴**（LC 使与 Arena 的 Spearman 从 0.94→0.98）；题目不要用 |
| 5 | WildBench | 每题带 checklist（GPT-4 生成） | WB-Score（单点）+ WB-Reward（pairwise） | 代码 Apache-2.0；数据源自 WildChat，**ODC-BY**（2024-06 从 AI2 ImpACT 改为 ODC-BY，追溯生效） | ✅（ODC-BY 允许商用，需署名） | 中：2024 年发布，已被部分模型用于评测 | G4/G10 | **中-高** | 改造（需筛出办公子集） | **真实用户任务 + per-instance checklist，是离「办公真实需求」最近的英文公开集** |
| 6 | Chatbot Arena 33k | 人类 pairwise 投票 | 人类偏好（Elo） | **prompts CC-BY-4.0；模型输出 CC-BY-NC-4.0** | ⚠️ **输出部分不可商用** | 中 | Judge 校准（人类偏好锚） | 中-高 | 改造 | 校准 κ 的**真人偏好锚点**，但 NC 限制决定只能内部研究用 |
| 7 | HelpSteer2 | 多维人工 Likert（helpfulness/correctness/coherence/complexity/verbosity） | 人工标注分 | **CC-BY-4.0** | ✅ **可商用** | 低-中 | Judge 校准 / G4 rubric 维度参考 | 中-高 | 改造 | **许可证最干净的人工多维标注集**，做 Judge-人类一致性校准首选之一 |
| 8 | HelpSteer3 | 偏好对 + **1–2 句人工理由** | 人工偏好 | **CC-BY-4.0** | ✅ | 低 | Judge 校准 / G10 偏好对 | **高** | 改造 | **带人工理由的偏好对**，可直接当我方 Judge few-shot 与 κ 校准底座 |
| 9 | Nectar | GPT-4 对 7 个响应排序 | GPT-4 排序 | Apache-2.0，**但数据卡附加条件：不得用于与 OpenAI 竞争** | ⚠️ 有条件；**源自 GPT-4 输出，带 OpenAI ToS 衍生风险** | 中-高（GPT-4 合成） | Judge 校准（规模大） | 中 | 改造 | 量大但是**合成偏好**，做校准会把 GPT-4 的偏好偏差一并继承，慎用 |
| 10 | **WritingBench** | **每题 5 条实例级 criteria（含 style/format/length）+ critic 模型** | LLM-as-Judge 或微调 critic（Qwen-7B） | **Apache-2.0** | ✅ | 中：2025 年发布，尚未完全饱和 | **G4（首选）** | **高** | 改造（抽 Finance&Business / Advertising&Marketing / Education 子域） | **G4 的头号候选**：6 大域含「金融商务」「广告营销」，且 rubric 生成范式与我方 5 维金标高度同构 |
| 11 | EQ-Bench Creative Writing | rubric（满分 20）+ 邻近模型 pairwise Elo | LLM-as-Judge（Rubric + Glicko-2） | MIT | ✅ | 中 | G4（文学向，非办公） | 低-中 | 仅借方法 | **Rubric + Elo 混合、防高分饱和的设计值得抄**；题材是创意写作，与办公文案不搭 |
| 12 | EQ-Bench（情商/roleplay） | 情绪强度评分 / roleplay rubric | LLM-as-Judge | MIT | ✅ | 中 | **G10（情境处理）** | 中 | 改造 | 最接近「难处理场景的措辞」的公开思路，但**是私人情感情境，不是职场情境** |
| 13 | LongWriter / LongBench-Write | 字数约束 + 质量 rubric | 规则（长度符合度 S_l）+ LLM 质量分 S_q | Apache-2.0 | ✅ | 中 | **G4（含中文！）** | **中-高** | 改造 | **60 条中文写作 prompt 是为数不多的中文可商用写作题**；长度约束校验可直接并入我方「格式合规率」 |
| 14 | HelloBench | **checklist + HelloEval（线性回归拟合人类权重）** | checklist-based LLM 评分 | MIT | ✅ | 中 | G4 / Judge 方法 | 中 | 仅借方法为主 | **用回归学习 rubric 各维权重、对齐人类**——这个做法对我方 5 维加权极有价值 |
| 15 | ProxyQA | 预标注 proxy-question | 评估模型答 proxy-question 的正确率 | **未核实**（查了 arXiv:2401.15042 与仓库，未拿到明确许可证声明） | 未核实 | 中 | G5（覆盖度度量思路） | 中 | 仅借方法 | **把「风险要素清单」转成 proxy-question 来客观测覆盖度**——G5 可直接复用这个机制 |
| 16 | AlignBench | 中文多维 rubric + 参考答案 | CritiqueLLM / GPT-4 多维打分 | Apache-2.0（仓库） | ✅（仓库声明；数据条款未单列，建议复核） | **高**：中文圈最常引用的对齐评测，已被广泛训练 | G4/G10（中文范式） | 中 | 仅借方法 + 少量改造 | **中文多维 rubric 的事实标准**，8 大类里含「写作能力」「角色扮演」，范式可抄，题目污染重 |
| 17 | SuperCLUE | 不公开 | 平台评测 + CArena 对战 | 仓库 MIT，**核心评测集刻意不公开（防过拟合）** | N/A（拿不到数据） | 低（因不公开） | — | 低 | 不可用 | **数据拿不到，只能参考其「开闭结合 + 对战」的赛制设计** |
| 18 | CHC-Bench | 人工 hard case + rubric | LLM-as-Judge | Apache-2.0（评测数据/代码）；**注意其配套 MAP-CC 预训练语料是 CC BY-NC-ND 4.0** | ✅（评测部分） | 中 | G4/G10（中文难例） | 中 | 改造 | 214 条量太小，但**中文难例的挑选思路**可借 |
| 19 | CLEVA | 多任务标准答案 | 自动指标为主 | **CC BY-NC-ND 4.0** | ❌ **不可商用，且 ND 禁止改编** | 中 | — | 低 | 不可用（ND 条款尤其致命） | 中文覆盖广但**许可证对我方最不友好**（不可改、不可商用） |
| 20 | **IFEval** | **可程序校验的指令**（字数/JSON/关键词/大小写…） | **规则校验（非 LLM）** | Apache-2.0 | ✅ | **高**（几乎所有模型卡都报 IFEval），但**规则判分对污染不敏感** | **G4「格式合规率」（首选）** | **高** | **可直接采用其校验器代码** | **G4 格式合规率的现成引擎**：25 类可验证指令的判分器直接拿来包我方格式规约 |
| 21 | Multi-IF | 多轮 + 多语可验证指令 | 规则校验 | **CC BY-NC-SA 4.0** | ❌ **不可商用（NC），且 SA 传染** | 中 | G4（中文格式合规） | 中 | 仅借方法（许可证劝退） | 含中文的多轮 IFEval 扩展，可惜 **NC-SA** 让它只能内部用 |
| 22 | FollowBench | 5 类约束的多级难度 | 规则 + LLM 混合 | Apache-2.0 | ✅ | 中 | G4（格式/风格约束） | 中-高 | 改造 | **「同一题逐级加约束」的难度阶梯设计，非常适合做 G4 格式规约的区分度设计** |
| 23 | InFoBench | 指令拆成原子需求 | **DRFR**（逐条需求满足率，LLM 判每条） | MIT | ✅ | 中 | G4/G5（需求覆盖度） | 中-高 | 改造 | **DRFR = 把 rubric 拆成 yes/no 原子项**，比 1–5 打分稳得多，G5 的「风险要素清单」应该照这个做 |
| 24 | **CFBench** | 1,000 条中文样本 / 10 大约束类 | 规则 + LLM 判 | **未核实**（查了 GitHub `PKU-Baichuan-MLSystemLab/CFBench` 与 arXiv:2408.01122，检索结果只确认「公开可获取」，未拿到明确 SPDX 许可证声明——**使用前必须去仓库 LICENSE 文件确认**） | 未核实 | 中 | **G4 中文格式合规（首选之一）** | **高** | 改造 | **中文场景最对口的约束遵循集**，10 大约束类可直接映射我方格式规约 |
| 25 | OfficeBench | 执行结果（精确/模糊匹配 + 执行校验） | 执行式判分 | Apache-2.0（检索所得；**arXiv 编号在检索结果中为占位形式，未核实**） | ✅（以仓库声明为准） | 低 | 与 G4/G10 **不同源** | 低 | 不采用 | **是 agent 操作办公软件，不是写文案**，名字像但不对口，避免误用 |
| 26 | QMSum | 人工 query-摘要 | ROUGE / LLM | 代码 MIT；文本源 CC BY 4.0 | ✅ | 中 | G10（会议跟进素材） | 低-中 | 改造（当素材，不当题） | **可当「会议纪要→跟进沟通」类 G10 题目的输入素材来源** |
| 27 | MeetingBank | 会议纪要摘要 | 自动指标 | CC BY 4.0 | ✅ | 中 | G10（素材） | 低-中 | 改造（当素材） | 同上，市政会议题材与企业办公有距离 |
| 28 | EnronQA | QA 对 | 抽取/匹配 | **未核实**（Enron 原始语料为研究用公共领域；EnronQA 衍生集许可证与 arXiv 编号**未核实**） | 未核实 | 中 | G10（邮件素材） | 低-中 | 仅当素材 | **真实企业邮件语料**，但任务是 QA/检索，不是「写回复」；且含真人 PII，合规需谨慎 |
| 29 | PlanBench | PDDL 可验证计划 | **符号验证器（VAL）** | Apache-2.0 | ✅ | 中 | **不对口 G5** | 低 | 不采用 | **可验证符号规划 ≠ 开放式方案设计**，金标是「计划是否可执行」而非「方案是否周全」 |
| 30 | Natural Plan | 约束可解的自然语言计划 | 精确匹配/约束校验 | 代码 Apache-2.0 + **数据 CC-BY-4.0** | ✅ | 中 | **不对口 G5** | 低 | 不采用 | 同上：有唯一/可判定最优解，与 G5「无唯一解、看拆解与风险覆盖」根本不同源 |
| 31 | TravelPlanner | 13 项硬约束 | 约束通过率 | MIT | ✅ | 中 | **不对口 G5** | 低 | 不采用（仅借「硬约束清单」思路） | 唯一可借的是**「常识约束 + 硬约束」分层清单**的写法 |
| 32 | EngDesign | 仿真执行结果 | 仿真脚本判分 | **未核实** | 未核实 | 低 | G5（部分相关） | 低-中 | 仅借方法 | **最接近「工程设计」的公开集**，但判分靠仿真执行，我方的商业/技术方案题跑不了仿真 |
| 33 | BizCompass | 商业推理题（角色化） | 未核实 | **未核实** | 未核实 | 低（2026 新发布） | G5（潜在） | 未评（**低置信**） | 待核 | **检索到但未能确认数据可下载性与许可证**，官网域名形似测试环境，建议单独立项核实后再决定 |
| 34 | EnterpriseClawBench | 硬规则 + 语义 rubric 混合 | 混合判分 | 代码 Apache-2.0；**原始数据不公开** | 数据拿不到 | 低 | G5/G10（方法） | 低（数据）/中（方法） | 仅借方法 | **「硬规则 + 语义 judge + 成本/结果」三合一的企业评测设计**值得抄；数据不开放 |
| 35 | SOTOPIA | 目标达成度 + 7 维社交 rubric（SOTOPIA-Eval） | LLM/人类多维打分 | 代码 MIT（配套站点 CC BY-SA 4.0；`sotopia-pi` Apache-2.0） | ✅ | 中 | **G10（方法首选）** | 中（方法高、数据低） | 仅借方法 | **7 维社交 rubric（目标达成/关系/知识/守密/社会规则/财务/信念）是 G10 rubric 的最佳参照**；90 个情境是生活社交，不是职场 |
| 36 | ESConv | Helping Skills 策略标注 | 人工策略标签 | **CC BY-NC 4.0** | ❌ 不可商用 | 中 | G10（共情话术） | 低-中 | 仅借方法 | **策略分类体系（提问/重述/肯定…）可映射到「向上汇报坏消息」的话术策略** |
| 37 | CaSiNo | 协商结果 + 策略标注 | 人工 | CC BY 4.0（Cornell 官方；**Kaggle 镜像标 CC BY-NC-SA 4.0，以官方为准**） | ✅（按官方 CC BY 4.0） | 低-中 | G10（跨部门协调） | 低-中 | 仅借方法 | 露营物资协商，**题材完全不对口**，但多轮协商策略标注可参考 |
| 38 | **JudgeBench** | **客观可判定的正误标签**（知识/推理/数学/代码） | Judge 准确率 | **未核实**（查了 GitHub `ScalerLab/JudgeBench`，只确认「公开可用」，未拿到明确许可证字段） | 未核实 | 低（专为抗污染设计） | **Judge 校准（首选）** | **高** | 直接采用 | **用有客观答案的题反测 Judge**，避免「用偏好评偏好」的循环论证，是我方 κ 校准的硬锚 |
| 39 | RewardBench | (prompt, chosen, rejected) | 准确率 | **ODC-BY** | ✅ | 中（已被广泛用于 RM 调参） | Judge 校准 | 中-高 | 直接采用 | 老牌基准，Chat-Hard 子集对区分 Judge 质量最有效 |
| 40 | **RewardBench 2** | best-of-4 选优 | 准确率 | **ODC-BY** | ✅ | 低（新、更抗刷） | **Judge 校准（首选）** | **高** | 直接采用 | **v1 已被刷穿，用 v2**；ODC-BY 许可证干净，可商用 |
| 41 | **LLMBar** | 人工构造的「对抗性」偏好对 | Judge 准确率 | **MIT** | ✅ | 低-中 | **Judge 校准（首选）** | **高** | 直接采用 | **专治 Judge 被「长/漂亮但没遵循指令」的答案骗**——正是 G4 格式合规最怕的失效模式 |
| 42 | JudgeLM-100K | GPT-4 判分 | — | **未核实**（模型权重基于 LLaMA 许可证；**数据集自身许可证未从检索中确认**） | 未核实；**源自 GPT-4 输出，带 OpenAI ToS 衍生风险** | 中-高 | Judge 训练（非校准） | 中 | 改造 | 量大，适合训练自家 Judge；**不适合当校准金标**（金标本身是 GPT-4 产出） |
| 43 | Auto-J | 58 场景 criteria + critique | 生成式 Judge | **模型：13B 为 Llama 2 Community License，6B 为 Yi License**（均非标准 OSS 许可证，**商用需逐条读条款**） | ⚠️ 有条件 | 中 | Judge 校准 / G4-G10 场景分类 | 中-高 | 改造 | **58 个真实场景的分类体系 + 每场景 criteria，是我方门类内细分场景的现成参照（且有中文 6B 版）** |
| 44 | Prometheus 2 / Feedback & Preference Collection | **自定义 rubric + 参考答案 + 反馈** | 定制评估器打分 | **Apache-2.0** | ✅ | 中（Feedback Collection 由 GPT-4 合成） | **Judge 方法（首选）** | **高** | 直接采用（作评估器） | **「输入任意自定义 rubric → 输出分数 + 理由」的开源评估器**，可作为我方 Judge 的开源对照组，摆脱单一闭源 Judge 依赖 |
| 45 | FLASK | 12 项技能的细粒度打分 | 人类 + LLM 双轨 | **CC BY 4.0** | ✅ | 中 | Judge 方法 / rubric 维度 | 中-高 | 仅借方法 | **技能级分解打分 + 人类/模型双轨对照**，是设计 5 维 rubric 的方法论范本 |
| 46 | G-Eval | 方法 | **CoT + form-filling + 概率加权分数** | 代码 MIT（论文 CC BY-NC-ND 4.0） | ✅（代码） | — | Judge 方法 | 中 | 仅借方法 | **用 token 概率加权缓解整数分数粒度过粗**——对「Rubric 均分 ≥4.0」这种阈值指标很关键 |
| 47 | RubricEval | rubric 级判定标签 | Judge 准确率 | **未核实**（**低置信**：仅检索到论文描述，仓库与许可证未确认） | 未核实 | 低 | Judge 校准（rubric 级） | 未评 | 待核 | 若属实，**直接指出「逐条 rubric 核验会误差累积」（GPT-4o 在 Hard 子集仅 55.97%）**，是我方 rubric 拆太细的风险警告 |

---

## 2. 分门类小结

### 2.1 G4 文案撰写

**首选推荐（借数据）**
1. **WritingBench**（Apache-2.0，可商用）——抽 `Finance & Business`、`Advertising & Marketing`、`Education` 三个域，建议采样 **150–250 条**。
2. **LongBench-Write 中文子集**（Apache-2.0）——**60 条中文写作 prompt 全量取**，是少有的可商用中文写作题。
3. **IFEval**（Apache-2.0）——**不是取题，是取判分器**。其 25 类可验证指令的校验代码可直接包装成我方「格式合规率」的执行引擎。
4. **CFBench**（中文 1,000 条）——建议采样 **100–150 条**做中文格式/约束合规；**但许可证未核实，落地前必须先读仓库 LICENSE**。
5. **WildBench**（ODC-BY）——按办公/商务关键词过滤真实用户任务，预计能筛出 **50–100 条**可用素材。

**首选推荐（借方法，价值高于借数据）**
- **WritingBench 的 instance-specific criteria 生成范式**：不是全局用一套 5 维 rubric，而是「全局 5 维 + 每题动态生成 5 条实例化 criteria」。我方 G4 的「流畅/规范/术语/结构/口吻」应当作为**维度骨架**，再由生成器为每道题填充可判定的实例化描述，否则「口吻」这种维度在不同题上判分标准漂移会很严重。
- **HelloEval 的权重回归**：用小规模人工打分回归出各维权重，而不是 5 维等权平均。我方「Rubric 均分 ≥4.0」的阈值若基于等权平均，会被「结构」这类容易拿高分的维度拉高。
- **FollowBench 的难度阶梯**：同一条写作指令逐级叠加格式约束（1→5 级），用于制造区分度。
- **InFoBench 的 DRFR**：把格式规约拆成原子 yes/no 项统计满足率，比让 Judge 打 1–5 分稳定得多。

**需要的改造**
- WritingBench / WildBench 题目为英文或中英混合，**中英术语一致率**这个辅助指标在原集上无金标，需自建术语表（术语对照词典 + 抽取校验脚本）。
- 我方「格式规约」（如公司模板、字段顺序、抬头落款）在所有公开集里都没有，必须自写校验器；IFEval 提供的是**框架**而非**规约内容**。
- 中文办公文案（邮件、周报、通知、纪要、公文）——**公开集里实质为零**（检索确认：中文公文写作**无广泛引用的公开评测集**，现有只有 SIGHAN 系列的拼写/语法纠错），这部分**必须全自建**。

**结论：G4 数据侧可覆盖约 25–30%，方法侧可覆盖约 70%。**

---

### 2.2 G5 方案设计

**结论先行：没有对口的公开集，G5 的题目必须全自建。**

检索确认的事实：
- **PlanBench / Natural Plan / TravelPlanner 都不是**。它们的金标是**可程序验证的计划正确性**（PDDL 验证器、约束满足率、13 项硬约束通过率），有唯一或可判定的最优解。G5 的金标是**「拆解合理性 + 可行性 + 风险覆盖」的 rubric**，无唯一解。**两者不同源，混用会把「能否解出约束」误当成「方案是否周全」。**
- **EngDesign**（NeurIPS 2025 D&B，开源子集 53 任务）是最接近「工程设计」的，但判分依赖**仿真脚本执行**——我方的技术方案/项目规划题无法仿真。许可证未核实。
- **BizCompass**（Findings of ACL 2026）方向对（含「顾问」角色），但**数据可获取性与许可证均未核实**，置信度低，建议单独立项核实。
- **EnterpriseClawBench**（2026）**明确不公开原始数据**，只开源构建管线与评测框架。
- 「系统设计面试」类：检索确认**不存在标准公开 benchmark**。

**能借的只有方法：**
1. **InFoBench 的 DRFR** → 把「必须覆盖的风险要素清单」写成原子化 yes/no 检查项，逐条统计覆盖率，得到一个**不依赖 Judge 打分尺度**的客观辅助指标。这是 G5 最值得抄的一条。
2. **ProxyQA 的 proxy-question 机制** → 把风险要素转成「这个方案是否回答了 X 会怎么办？」的代理问题，让评估模型从方案正文里找答案，比直接让 Judge 打「风险覆盖分」客观得多。
3. **Arena-Hard-Auto 的 pairwise 统计流程** → Bradley-Terry 建模 + bootstrap 95% 置信区间 + style control，这是我方「pairwise win-rate vs 基线」应当照搬的统计口径（否则 win-rate 没有误差棒，模型间差异没法判显著）。
4. **TravelPlanner 的「常识约束 / 硬约束」分层** → 把 G5 的风险清单分成「必须覆盖（硬）」与「加分覆盖（软）」两层。
5. **EnterpriseClawBench 的「硬规则 + 语义 rubric + 成本」三层评测**设计。

**建议采样量**：公开集**取 0 条题目**。自建建议起步 **80–120 道**（技术方案 / 项目规划 / 流程改造 三类各 30–40 道），每题配一份 8–15 条的风险要素清单 + 一份基线方案（用于 pairwise）。

**结论：G5 公开集可覆盖 < 10–15%，且这 10–15% 全部是「方法」，数据侧为 0。必须全自建。**

---

### 2.3 G10 工作沟通与建议

**首选推荐（借数据，量很有限）**
1. **HelpSteer3**（CC-BY-4.0，可商用，40,476 条带人工理由的偏好对）——**本门类唯一能直接用的「人类偏好对」资源**，可从中筛出沟通/建议类样本作为我方偏好对的种子与 Judge 校准锚。建议筛选目标 **300–500 对**。
2. **WildBench**（ODC-BY）——真实用户日志里含大量「帮我回复这封邮件 / 怎么跟老板说」，按意图过滤，预计可得 **50–120 条**。这是最接近 G10 真实分布的公开来源。
3. **QMSum / MeetingBank**（MIT / CC BY 4.0）——**只当输入素材**（会议纪要 → 生成跟进沟通），不当题目。

**首选推荐（借方法，本门类的主要价值）**
- **SOTOPIA-Eval 的 7 维社交 rubric**（目标达成 / 关系维护 / 知识获取 / 守密 / 社会规则 / 财务收益 / 信念一致）——这是公开工作里**最成体系的社交沟通 rubric**，我方「情境满意度」应当在其基础上裁剪为职场版（如：目标达成 / 关系不受损 / 信息准确不甩锅 / 边界与合规 / 语气得体）。
- **ESConv 的 Helping Skills 策略标注体系**（提问 / 重述 / 情感肯定 / 提供信息 / 建议…）——可映射为「向上汇报坏消息」的话术策略标签，让 Judge 不只打总分，还标出用了哪些策略。
- **CaSiNo 的多轮协商策略标注** → 跨部门协调话术的策略维度。
- **MT-Bench-101 的三层能力 taxonomy** → 多轮沟通场景的分层设计。
- **Chatbot Arena / HelpSteer3 的人类偏好对构造流程** → 我方「人类偏好对」的标注规程参照。

**需要的改造**
- SOTOPIA（90 情境）、ESConv（1,300 段）、CaSiNo（1,030 段）**题材全部是生活社交 / 情感支持 / 露营物资协商，不是职场**。**这三个都只能借方法，数据不能用。**
- ESConv 是 **CC BY-NC 4.0，不可商用**；CaSiNo 官方 CC BY 4.0 但 Kaggle 镜像标注为 NC-SA，取用须走官方渠道。
- 职场情境（难处理邮件、向上汇报坏消息、跨部门协调、绩效面谈、拒绝不合理需求）——**公开集里没有中文的，英文的也只有 WildBench 里零散的真实 query**。必须自建。

**建议采样量**：公开集可提供 **约 100–200 条**素材级输入 + **300–500 对**偏好校准数据；题目本体建议自建 **100–150 道**职场情境。

**结论：G10 数据侧可覆盖约 15–20%（且主要是「素材」和「偏好校准」，不是「题目」），方法侧可覆盖约 60%。**

---

### 2.4 Judge 校准（唯一数据充裕的一块）

**首选组合（全部可直接采用）**
| 用途 | 数据集 | 量 | 许可证 |
|---|---|---|---|
| 抗污染主锚 | **RewardBench 2** | 1,865 | ODC-BY ✅ |
| 对抗性失效测试 | **LLMBar**（Adversarial 子集尤其重要） | 419 | MIT ✅ |
| 客观标签反测 | **JudgeBench** | 350 + 270 | 未核实 ⚠️ |
| 人类偏好锚（带理由） | **HelpSteer3** | 40,476 | CC-BY-4.0 ✅ |
| 多维人工打分锚 | **HelpSteer2** | ≈21.3k 对 | CC-BY-4.0 ✅ |
| 开源评估器对照 | **Prometheus 2** | — | Apache-2.0 ✅ |
| 真人投票锚（仅内部） | Chatbot Arena 33k | 33k | 输出 CC-BY-NC ⚠️ |

**为什么这套能支撑 κ ≥ 0.7 的目标**
- **JudgeBench 的价值独特**：它用**有客观正误的题**（数学/代码/知识/推理）构造响应对，Judge 判对判错是可验证的，避免了「用偏好数据评偏好 Judge」的循环论证。
- **LLMBar 的 Adversarial 子集**专门构造「更长、更漂亮、但没遵循指令」的干扰答案——这正是 G4「格式合规」最怕的 Judge 失效模式，必须过这一关。
- **RewardBench v1 已被广泛用于 RM 调参、存在过拟合**，应以 **v2** 为主、v1 的 Chat-Hard 子集为辅。
- **HelpSteer2/3 是 CC-BY-4.0**，是这批里许可证最干净、可商用的人工标注锚点。

**需要的改造**
- **全部是英文**。我方中文场景的 κ 校准**必须自标一批中文样本**（建议每门类 100–150 条 × 3 名标注员），公开集只能校准 Judge 的「通用判别力」，不能替代中文职场语境下的一致性验证。
- 建议采样量：公开集侧 **RewardBench 2 全量 + LLMBar 全量 + JudgeBench 全量 ≈ 2,900 条**做 Judge 准入体检；中文自标 **300–450 条**做 κ 的正式测算。

**结论：Judge 校准公开集可覆盖约 70–80%（英文部分几乎全覆盖，中文部分需自标）。**

---

## 3. Rubric 与 Judge 方法论可借鉴清单

> **这一节的价值大概率高于前面的数据本身。** 每条都标注出处。

### 3.1 Rubric 设计方法

| 做法 | 出处 | 怎么用在我方 |
|---|---|---|
| **实例级 criteria 动态生成**（全局维度骨架 + 每题 5 条实例化判据） | WritingBench（阿里 X-PLUG, arXiv:2503.05244；`X-PLUG/WritingBench`） | G4 的 5 维金标只作骨架，每题由生成器产出可判定的实例化描述，消除「口吻」「规范」在不同题间的尺度漂移 |
| **原子化需求分解 + DRFR**（把指令拆成若干 yes/no 需求，统计满足率） | InFoBench（`qinyiwei/InFoBench`, MIT） | G4 的格式规约、G5 的风险要素清单**都应写成 yes/no 原子项**，得到不依赖打分尺度的客观指标 |
| **checklist + 权重回归对齐人类**（用线性回归从人工评分学各 criterion 权重） | HelloBench / HelloEval（`Quehry/HelloBench`, MIT） | G4 的「Rubric 均分 ≥4.0」不要用等权平均，先用小样本人工分回归出权重 |
| **技能级细粒度分解 + 人类/模型双轨打分** | FLASK（`kaistAI/FLASK`, CC BY 4.0, ICLR 2024） | 5 维 rubric 的维度切分方法论范本；双轨对照是 κ 校准的标准做法 |
| **多层级约束阶梯**（同题逐级加约束，制造区分度） | FollowBench（`YJiangcm/FollowBench`, Apache-2.0, ACL 2024, arXiv:2310.20410） | G4 格式规约按难度分 1–5 级，避免所有模型都拿满分 |
| **可程序验证的指令类型库**（25 类，判分器开源） | IFEval（`google-research/instruction_following_eval`, Apache-2.0, arXiv:2311.07911） | **直接复用判分器代码**作为「格式合规率」引擎 |
| **中文约束类目体系**（10 大类 / 25+ 子类） | CFBench（`PKU-Baichuan-MLSystemLab/CFBench`, arXiv:2408.01122） | 中文格式规约的分类学参照 |
| **7 维社交 rubric** | SOTOPIA-Eval（`sotopia-lab/sotopia`, MIT） | G10「情境满意度」rubric 的裁剪基底 |
| **58 个真实场景 × 场景专属 criteria** | Auto-J（`GAIR-NLP/auto-j`，13B: Llama 2 License / 6B: Yi License） | 门类内细分场景的现成分类，且有中文版本 |
| **proxy-question 覆盖度** | ProxyQA（ACL 2024, arXiv:2401.15042） | G5 风险覆盖率的客观测法 |
| **「逐条 rubric 核验会误差累积」的警告**（GPT-4o 在 Hard 子集仅 55.97%） | RubricEval（复旦 + 蚂蚁, arXiv:2603.25133）**⚠️ 低置信，未二次核实仓库** | rubric 不要拆得过细，控制在可靠判定的粒度 |

### 3.2 Pairwise 位置偏差消除

| 做法 | 出处 | 说明 |
|---|---|---|
| **BPC（Balanced Position Calibration）**：同一对同时评 [A,B] 和 [B,A]，聚合后出结论 | Wang et al., *Large Language Models are not Fair Evaluators*（2023, ACL 2024） | **G5 的 pairwise win-rate 必须做**，否则位置偏差直接污染结论 |
| **MEC（Multiple Evidence Calibration）**：先生成多份评估证据/理由，再给分 | 同上 | 与 CoT 判分配合，降低随机性 |
| **HITLC（Human-in-the-Loop Calibration）**：用 BPDE（平衡位置多样性熵）挑出高不确定样本交人工复核，论文报告可减少 39% 人工标注量 | 同上 | **直接对应我方 κ 校准的人力预算优化** |
| **长度控制 win-rate（GLM logistic 回归，在长度差为 0 处取条件偏好）** | AlpacaEval 2.0 LC（`tatsu-lab/alpaca_eval`）；论文报告与 Arena 的 Spearman 从 0.94 → 0.98 | **G5 pairwise 必做**，否则「方案写得长」会被误判为「方案更周全」 |
| **Bradley-Terry 建模 + bootstrap 95% CI + style control** | Arena-Hard-Auto（`lmarena/arena-hard-auto`, Apache-2.0） | win-rate 要带误差棒，否则模型差异无法判显著 |
| **Rubric 分 + 邻近对手 Elo（Glicko-2）混合，防高端饱和** | EQ-Bench Creative Writing v3（`EQ-bench/creative-writing-bench`, MIT） | 解决「强模型 rubric 均分都 ≥4.5，区分不开」的问题 |
| **token 概率加权分数**（缓解整数打分粒度过粗） | G-Eval（`nlpyang/geval`, 代码 MIT） | 对「≥4.0/5」这种阈值指标尤其关键——整数分会让阈值判定抖动 |

### 3.3 Judge 校准协议

1. **准入体检**：候选 Judge 先跑 **RewardBench 2**（1,865 条，ODC-BY）+ **LLMBar Adversarial**（MIT）+ **JudgeBench**（客观标签），任一项显著低于开源 SOTA 的不予采用。
2. **循环论证规避**：**不要**用 GPT-4 生成的偏好数据（Nectar、JudgeLM-100K、Feedback Collection）作为 κ 的金标——它们的金标本身就是模型产出。这些只适合**训练**自家 Judge。
3. **人类锚点**：用 **HelpSteer2/3**（CC-BY-4.0，带人工多维分与理由）作英文人类锚；中文必须自标。
4. **双轨对照**：按 FLASK 的做法，同一批样本同时跑人类与 Judge，按维度分别算 κ，而不是只算总分 κ——总分 κ 会掩盖「术语」「口吻」这类维度上的严重不一致。
5. **开源对照组**：用 **Prometheus 2**（Apache-2.0，支持任意自定义 rubric）作为闭源 Judge 的独立第二意见，降低单一 Judge 依赖与供应商锁定。
6. **位置偏差常态化监控**：每轮评测统计 position conflict rate（交换顺序后结论翻转的比例），作为 Judge 健康度指标持续跟踪。

---

## 4. 「覆盖不到什么」的诚实说明

### G4 文案撰写 —— 公开集可覆盖约 **25–30%**（数据侧）

**依据**：
- ✅ 可覆盖：通用写作质量打分（WritingBench 1,239 题中约 2–3 个域与商务沾边）、长度约束（LongBench-Write 中文 60 条）、机械格式合规（IFEval 25 类判分器 + CFBench 中文约束类目）。
- ❌ **覆盖不到**：
  - **中文办公文体**（邮件、周报、通知、纪要、公文、对外公告）——检索确认**不存在广泛引用的中文公文写作公开评测集**，现有中文写作资源集中在拼写/语法纠错（SIGHAN 系列），与文案质量评测不同源。
  - **企业私域格式规约**（公司模板、字段顺序、抬头落款、品牌语气指南）——按定义就不会有公开集。
  - **中英术语一致率**——所有候选集均无术语金标，必须自建术语对照表。
  - **「素材 → 文案」这一形态**：公开集绝大多数是「纯指令 → 文案」，带结构化素材输入的极少（WildBench 里有零散真实样本）。

### G5 方案设计 —— 公开集可覆盖 **< 10–15%，必须全自建**

**依据**：
- 逐一核实后，**没有任何一个公开集的金标形式是「Rubric（拆解/可行性/风险覆盖）+ 风险要素清单」**。
- PlanBench / Natural Plan / TravelPlanner 的金标是**可验证的计划正确性**（符号验证器 / 约束满足率），属于不同的任务族。**把它们当 G5 的数据源是方法论错误。**
- EngDesign 靠仿真执行判分，我方场景无法仿真；许可证未核实。
- BizCompass（2026）方向对但**可获取性与许可证未核实，低置信**。
- EnterpriseClawBench（2026）**明确不公开原始数据**。
- 那 10–15% 全部是**方法**（DRFR 原子化、proxy-question、pairwise 统计口径、硬/软约束分层），**数据侧可用题目为 0 条**。

**明确结论：G5 的题库、风险要素清单、基线方案，三样都必须从零自建。**

### G10 工作沟通与建议 —— 公开集可覆盖约 **15–20%**

**依据**：
- ✅ 可覆盖：偏好对标注规程与校准锚（HelpSteer3，CC-BY-4.0）、少量真实职场 query（WildBench 过滤）、会议类输入素材（QMSum / MeetingBank）。
- ❌ **覆盖不到**：
  - **职场情境题目本体**：SOTOPIA 是生活社交、ESConv 是心理情感支持、CaSiNo 是露营物资协商——**没有一个是职场**。职场特有的权力关系（向上汇报）、组织边界（跨部门）、合规敏感（绩效、裁员、客诉）在公开集里完全缺位。
  - **中文职场语境**：上述全部为英文，且职场沟通的得体性高度依赖文化语境，不能靠翻译迁移。
  - **人类偏好对的职场版本**：HelpSteer3 的偏好是通用 helpfulness，不是「这封邮件回复得体吗」。
  - 许可证障碍：ESConv 为 CC BY-NC 4.0，不可商用。

### Judge 校准 —— 公开集可覆盖约 **70–80%**

**依据**：英文侧的 Judge 准入体检、对抗性测试、客观标签反测、人类偏好锚，四条链路均有可商用（ODC-BY / MIT / CC-BY-4.0）的成熟公开集，基本不需自建。**缺口只在中文**：所有候选校准集均为英文，中文场景的 κ ≥ 0.7 必须靠自标样本证明。

### 关于「借数据」与「借方法」的总账

| 门类 | 借数据（能直接进题库/校准集的） | 借方法（范式、判分机制、统计口径） |
|---|---|---|
| G4 | WritingBench 商务子域、LongBench-Write 中文、CFBench（许可证待核）、IFEval 判分器、WildBench 过滤 | WritingBench 实例级 criteria、HelloEval 权重回归、FollowBench 难度阶梯、InFoBench DRFR |
| G5 | **无** | InFoBench DRFR、ProxyQA 代理问题、Arena-Hard BT+CI、AlpacaEval LC、TravelPlanner 硬/软约束分层 |
| G10 | HelpSteer3 偏好对、WildBench 过滤、QMSum/MeetingBank 素材 | SOTOPIA 7 维 rubric、ESConv 策略体系、MT-Bench-101 多轮 taxonomy、Chatbot Arena 偏好标注流程 |
| Judge | RewardBench 2、LLMBar、JudgeBench、HelpSteer2/3 | Wang et al. MEC/BPC/HITLC、G-Eval 概率加权、FLASK 双轨、Prometheus 2 开源对照 |

---

## 5. 引用来源与核实说明

### 5.1 已核实来源（经 `google_search` 确认）

- MT-Bench / Chatbot Arena：Zheng et al., *Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena*, 2023；GitHub `lm-sys/FastChat`（Apache-2.0）；HF `lmsys/chatbot_arena_conversations`（prompts CC-BY-4.0 / outputs CC-BY-NC-4.0）
- MT-Bench-101：Bai et al., ACL 2024；GitHub `mtbench101/mt-bench-101`（Apache-2.0）
- Arena-Hard-Auto：LMSYS / LMArena；GitHub `lmarena/arena-hard-auto`（Apache-2.0）
- AlpacaEval 2.0：Dubois et al., 2024；GitHub `tatsu-lab/alpaca_eval`（Apache-2.0）；LC 方法与 Spearman 0.94→0.98
- WildBench：Lin et al. (AI2), 2024；GitHub / HF `allenai/WildBench`（Apache-2.0）；底层 WildChat 于 2024-06-26 由 AI2 ImpACT 改为 **ODC-BY**（追溯生效）
- HelpSteer2：NVIDIA，CC-BY-4.0，10,681 prompts / ≈21.3k 对
- HelpSteer3：NVIDIA，2025-03，CC-BY-4.0，40,476 偏好样本（含人工理由）
- Nectar：Berkeley-NEST，183k prompts × 7 responses；Apache-2.0 **附条件「不得用于与 OpenAI 竞争」**
- WritingBench：arXiv:2503.05244（阿里 X-PLUG + 人大 + 上交）；1,239 queries / 6 域 / 100 子域 / 每题 5 条 criteria；Apache-2.0；critic 模型 `WritingBench-Critic-Model-Qwen-7B`
- EQ-Bench Creative Writing v3：`EQ-bench/creative-writing-bench`，MIT，32 prompts × 3 iterations，rubric /20 + Glicko-2 Elo
- LongWriter / LongBench-Write：arXiv:2408.07055（THUDM）；120 prompts（60 EN + 60 ZH）；Apache-2.0
- HelloBench / HelloEval：`Quehry/HelloBench`，MIT，647 样本 / 5 类 / 38 子类
- ProxyQA：arXiv:2401.15042，ACL 2024（华为诺亚方舟等）
- AlignBench：`THUDM/AlignBench`，683 中文 query / 8 类，Apache-2.0（仓库）
- SuperCLUE：`CLUEbenchmark/SuperCLUE`（MIT 仓库）；核心评测集不公开
- CHC-Bench / CT-LLM：214 条 / 8 类，Apache-2.0；配套 MAP-CC 语料 CC BY-NC-ND 4.0
- CLEVA：港中大 LaVi Lab + 上海 AI Lab，31 任务 / ≈370k 样本，**CC BY-NC-ND 4.0**
- IFEval：arXiv:2311.07911（Google Research），541 prompts / 25 类，`google-research/instruction_following_eval`
- Multi-IF：arXiv:2410.16692（Meta），4,501 段三轮对话 / 8 语种，**CC BY-NC-SA 4.0**
- FollowBench：arXiv:2310.20410，ACL 2024，`YJiangcm/FollowBench`，Apache-2.0，5 类约束
- InFoBench：500 instructions，DRFR，MIT
- CFBench：arXiv:2408.01122，`PKU-Baichuan-MLSystemLab/CFBench`，1,000 中文样本 / 10 大类 / 25+ 子类
- QMSum：`Yale-LILY/QMSum`，1,808 对 / 232 会议，代码 MIT / 源文本 CC BY 4.0
- MeetingBank：1,366 会议 / 6,892 段摘要对，CC BY 4.0（Zenodo）
- PlanBench：`karthikv792/LLMs-Planning` / `harshakokel/PlanBench`，Apache-2.0，PDDL 域来自 IPC
- Natural Plan：`google-deepmind/natural-plan`，代码 Apache-2.0 + 数据 CC-BY-4.0，3 域
- TravelPlanner：`osu-nlp/TravelPlanner`，MIT，1,225 queries（45/180/1000），13 项约束
- EngDesign：NeurIPS 2025 Datasets & Benchmarks，开源子集 `EngDesign-OPEN`（53 任务）
- SOTOPIA：`sotopia-lab/sotopia`，MIT，90 情境 × 40 角色；站点 CC BY-SA 4.0；`sotopia-pi` Apache-2.0
- ESConv：1,300 段 / 10 类，**CC BY-NC 4.0**
- CaSiNo：1,030 段协商对话，Cornell 官方 **CC BY 4.0**（Kaggle 镜像标 CC BY-NC-SA 4.0）
- JudgeBench：`ScalerLab/JudgeBench`，350 对（GPT-4o）+ 270 对（Claude 3.5 Sonnet）
- RewardBench：arXiv:2403.13787（AI2），2,985 条，**ODC-BY**
- RewardBench 2：AI2，1,865 条，best-of-4，**ODC-BY**
- LLMBar：`princeton-nlp/LLMBar`，419 对（Natural + Adversarial），**MIT**
- JudgeLM-100K：100k 训练 + 5k 验证，GPT-4 判分；模型基于 LLaMA（LLaMA Model License）
- Auto-J：GAIR，58 场景；13B → Llama 2 Community License，6B（双语）→ Yi License
- Prometheus 2 / Feedback Collection / Preference Collection：Kim et al., 2024；`prometheus-eval/prometheus-eval`，**Apache-2.0**；Feedback Collection = 1,000 rubric / 20k 指令 / 100k 反馈
- FLASK：Ye et al., ICLR 2024，`kaistAI/FLASK`，1,740 实例，**CC BY 4.0**
- G-Eval：Liu et al., 2023，`nlpyang/geval`，代码 MIT（论文 CC BY-NC-ND 4.0）
- 位置偏差：Wang et al., *Large Language Models are not Fair Evaluators*, 2023 / ACL 2024（MEC / BPC / HITLC；HITLC 减少 39% 人工标注）
- Enron 语料：FERC 2003 调查所得，CMU / SRI 整理，研究用公共领域
- 中文公文写作：检索确认**无广泛引用的公开评测集**；现有中文写作相关资源集中于 SIGHAN 2013/2014/2015 拼写语法纠错

### 5.2 未核实 / 低置信条目（使用前必须复核）

| 条目 | 未核实的字段 | 我查了什么 |
|---|---|---|
| **CFBench** | **许可证**（是否 Apache/MIT/其他） | 搜了仓库名、arXiv:2408.01122、"CFBench license"；检索结果只确认「公开可获取」，未返回明确 SPDX 声明。**落地前须直接读仓库 LICENSE** |
| **FollowBench** | **数据集规模条数** | 搜了仓库与论文，只确认 5 类约束 + 多级难度设计，未拿到确切 instruction 数 |
| **JudgeBench** | **许可证** | 搜了 `ScalerLab/JudgeBench` 与论文，只确认公开可用 |
| **JudgeLM-100K** | **数据集自身许可证**（模型侧为 LLaMA License 已确认） | 搜了 GitHub 与 HF 数据卡描述，未返回数据集许可证字段 |
| **ProxyQA** | **仓库地址、许可证、规模** | 搜了 arXiv:2401.15042 与作者单位，只拿到方法描述 |
| **OfficeBench** | **arXiv 编号、仓库名、规模** | 检索返回的 arXiv 编号为占位形式（`2405.00000`），不可信；仅「Apache-2.0」一项来自检索结果 |
| **EnronQA** | **arXiv 编号、许可证、HF repo** | 检索返回的 arXiv 编号为占位形式（`2505.00000`），不可信 |
| **EngDesign** | **仓库地址、许可证** | 搜了 NeurIPS 2025 D&B 与 `EngDesign-OPEN`，只拿到任务数 53 |
| **BizCompass** ⚠️ 低置信 | **数据可获取性、许可证、规模、是否含中文** | 搜了 "BizCompass ACL 2026"、官网域名；返回的官网形似测试子域（`bizcompass.dev...`），未验证可访问 |
| **EnterpriseClawBench** ⚠️ 低置信 | 论文出处 | 检索确认「原始数据不公开，仅开源构建/评测代码，仓库 Apache-2.0」，但作者机构与论文出处未独立验证 |
| **RubricEval** ⚠️ 低置信 | **仓库、许可证、是否真实发表** | 搜了 arXiv:2603.25133 与 "RubricEval"；两轮检索描述一致（复旦 + 蚂蚁，3,486 实例，GPT-4o Hard 55.97%），但未拿到可访问的仓库链接。**引用前请独立验证** |
| **AlignBench 数据条款** | 数据部分是否与代码同为 Apache-2.0 | 检索只确认仓库层面 Apache-2.0，未见数据单独声明 |
| **EQ-Bench 情商版规模** | 具体情境数（检索给出 60 与 45 两个不同数字，对应不同版本） | 搜了 EQ-Bench / EQBench3 多个版本页 |

### 5.3 许可证风险专项提示

1. **源自 OpenAI 输出的衍生限制**：**AlpacaEval**（评测标签与基线输出）、**Nectar**（GPT-4 排序）、**JudgeLM-100K**（GPT-4 判分）、**Prometheus Feedback Collection**（GPT-4 合成）——这几个虽然仓库标 Apache-2.0/MIT，但**内容源自 OpenAI API 输出**。OpenAI ToS 禁止「用其输出开发竞争模型」；该条款是 OpenAI 与 API 调用方之间的**合同约定**，不是自动附着于下游使用者的著作权许可，但**若用于训练我方模型仍有合规风险**。Nectar 的数据卡更是**把该限制明文写进了许可证条件**。**结论：这几个可用于「评测」，用于「训练」前须过法务。**
2. **明确不可商用**：CLEVA（CC BY-NC-ND 4.0，且 ND 禁止改编，最严）、Multi-IF（CC BY-NC-SA 4.0，SA 还有传染性）、ESConv（CC BY-NC 4.0）、Chatbot Arena 的**模型输出部分**（CC-BY-NC-4.0，prompts 部分是 CC-BY-4.0 可商用）。
3. **附条件开源许可证**：Auto-J 的 13B（Llama 2 Community License，有 MAU 阈值条款）与 6B（Yi License）——**都不是标准 OSS 许可证，商用须逐条读**。
4. **署名义务**：ODC-BY（WildBench/WildChat、RewardBench、RewardBench 2）与 CC-BY-4.0（HelpSteer2/3、Natural Plan 数据、MeetingBank、FLASK、QMSum 源文本）均要求**保留署名**，在我方 benchmark 文档中需列明出处。
5. **镜像与官方口径不一致**：CaSiNo 官方为 CC BY 4.0，Kaggle 镜像标 CC BY-NC-SA 4.0——**以官方渠道为准，并从官方渠道取数**。
6. **含真人 PII**：Enron / EnronQA 为真实企业邮件，含大量个人信息，即便属研究用公共领域，商业场景使用仍有隐私合规风险。
