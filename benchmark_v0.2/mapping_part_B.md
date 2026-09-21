# 映射表片段 B —— G4 文案撰写 / G5 方案设计 / G10 工作沟通与建议（含 Judge 校准集）

> 全部字段归纳自 `research_G4G5G10.md`，不补充报告外数字。原报告标「未核实」的一律原样保留。
> 两个列级说明：①「环境成本」原报告未设该字段，故全列写「未核实」，不做推断；②「建议采样量」原报告只给了部分条目，其余写「未给出」（≠未核实）。

## 表 1：门类 × 公开集 主映射表

| 门类 | 数据集 | 定位 | 规模 | 语言 | 许可证 | 可商用 | 污染风险 | 环境成本 | 建议采样量 | 需要的改造 | 来源报告 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| G4 / Judge校准 | MT-Bench | 已排除 | 80 题（8 类 × 10） | EN | Apache-2.0 | ✅ 代码可商用；题目为人工编写 | 高（2023 年起几乎进了所有后训练评测环路，榜单饱和） | 未核实 | 未给出 | 理由：题量太小、污染太重，不进正式题库；仅借其 LLM-as-Judge 单点+pairwise 范式 | research_G4G5G10.md |
| G10 / Judge校准 | MT-Bench-101 | 仅方法借鉴 | 1,388 段对话 / 4,208 轮 / 13 任务 | EN | Apache-2.0 | ✅ | 中 | 未核实 | 未给出 | 借的是「多轮能力分层 taxonomy」；数据本身偏通用对话 | research_G4G5G10.md |
| G5 / Judge校准 | Arena-Hard-Auto | 仅方法借鉴 | 500 prompts | EN | Apache-2.0 | ✅ | 高（500 题公开且被广泛用作调参目标） | 未核实 | 未给出 | 借 Bradley-Terry 建模 + bootstrap 95% CI + style control 的统计口径 | research_G4G5G10.md |
| G4 / Judge校准 | AlpacaEval 2.0 | 已排除 | 805 instructions | EN | Apache-2.0（代码） | ⚠️ 代码可商用，但部分数据/评测标签源自 OpenAI API 输出，受 ToS 约束 | 高（公开优化目标，length-hacking 众所周知） | 未核实 | 未给出 | 理由：题目污染+length-hacking，不进题库；只借 length-controlled win-rate | research_G4G5G10.md |
| G4 / G10 | WildBench | 辅助 | 1,024 真实任务 | 多语（以 EN 为主） | 代码 Apache-2.0；数据源自 WildChat，ODC-BY | ✅（ODC-BY 允许商用，需署名） | 中 | 未核实 | G4 50–100 条；G10 50–120 条 | 需按办公/商务关键词过滤出办公子集 | research_G4G5G10.md |
| Judge校准 | LMSYS Chatbot Arena 33k | 辅助 | 33k 对话 | 多语 | prompts CC-BY-4.0；模型输出 CC-BY-NC-4.0 | ⚠️ 输出部分不可商用 | 中 | 未核实 | 未给出 | 只能内部研究用作真人偏好锚；另借其人类偏好对构造/标注流程 | research_G4G5G10.md |
| Judge校准 | HelpSteer2 | 辅助 | 10,681 prompts / ≈21.3k 标注响应对 | EN | CC-BY-4.0 | ✅ | 低-中 | 未核实 | 未给出（表列 ≈21.3k 对作多维人工打分锚） | 作 Judge-人类一致性校准锚；亦可作 G4 rubric 维度参考 | research_G4G5G10.md |
| Judge校准 / G10 | HelpSteer3 | 主盘 | 40,476 偏好样本（含人工 1–2 句理由） | 多语 | CC-BY-4.0 | ✅ | 低 | 未核实 | G10 筛 300–500 对 | 需从中筛出沟通/建议类样本；偏好是通用 helpfulness，非「这封邮件回复得体吗」 | research_G4G5G10.md |
| Judge校准 | Nectar | 已排除 | 183k prompts × 7 responses（≈3.8M pairwise） | EN | Apache-2.0，但数据卡附加条件「不得用于与 OpenAI 竞争」 | ⚠️ 有条件 | 中-高（GPT-4 合成） | 未核实 | 未给出 | 理由：源自 GPT-4 输出、带 OpenAI ToS 衍生风险，不得当 κ 金标；只适合训练自家 Judge | research_G4G5G10.md |
| G4 | WritingBench | 主盘 | 1,239 写作 query / 6 大域 / 100 子域 | EN + ZH | Apache-2.0 | ✅ | 中（2025 发布，尚未完全饱和） | 未核实 | 150–250 条 | 抽 Finance & Business / Advertising & Marketing / Education 三域；中英术语一致率无金标，需自建术语对照表+抽取校验脚本 | research_G4G5G10.md |
| G4 | EQ-Bench Creative Writing (v3) | 仅方法借鉴 | 32 prompts × 3 iterations = 96 项 | EN | MIT | ✅ | 中 | 未核实 | 未给出 | 题材是创意写作、与办公文案不搭；借 Rubric 分 + 邻近对手 Glicko-2 Elo 的防饱和设计 | research_G4G5G10.md |
| G10 | EQ-Bench（情商 / roleplay） | 辅助 | 45–60 情境（版本而异） | EN | MIT | ✅ | 中 | 未核实 | 未给出 | 是私人情感情境、不是职场，需情境替换（注：原报告「借数据」总账的 G10 未列入此集，见第 6 节） | research_G4G5G10.md |
| G4 | LongWriter / LongBench-Write | 主盘 | 120 prompts（60 EN + 60 ZH），4 个长度档 | EN + ZH | Apache-2.0 | ✅ | 中 | 未核实 | 中文 60 条全量取 | 长度约束校验（S_l）可直接并入我方「格式合规率」 | research_G4G5G10.md |
| G4 / Judge校准 | HelloBench | 仅方法借鉴 | 647 样本 / 5 类 / 38 子类 | EN | MIT | ✅ | 中 | 未核实 | 未给出 | 借 HelloEval 的权重回归：用小样本人工分线性回归学各 criterion 权重，替代等权平均 | research_G4G5G10.md |
| G5 | ProxyQA | 仅方法借鉴 | 未核实 | EN | 未核实 | 未核实 | 中 | 未核实 | 未给出 | 借 proxy-question 覆盖度机制：把风险要素清单转成代理问题，客观测覆盖率 | research_G4G5G10.md |
| G4 / G10 | AlignBench | 仅方法借鉴 | 683 中文 query / 8 大类 | ZH | Apache-2.0（仓库；数据条款未单列，建议复核） | ✅（按仓库声明） | 高（中文圈最常引用的对齐评测，已被广泛训练） | 未核实 | 未给出 | 题目污染重，只借中文多维 rubric 范式（含「写作能力」「角色扮演」类目）+ 少量改造 | research_G4G5G10.md |
| —（原报告门类列为「—」） | SuperCLUE | 已排除 | 核心评测集不公开 | ZH | 仓库 MIT；核心评测集刻意不公开（防过拟合） | N/A（拿不到数据） | 低（因不公开） | 未核实 | 未给出 | 理由：数据拿不到；仅参考其「开闭结合 + 对战」的赛制设计 | research_G4G5G10.md |
| G4 / G10 | CHC-Bench | 辅助 | 214 条中文 hard case / 8 类 | ZH | Apache-2.0（评测数据/代码）；配套 MAP-CC 预训练语料为 CC BY-NC-ND 4.0 | ✅（评测部分） | 中 | 未核实 | 未给出 | 214 条量太小，借的是「中文难例挑选思路」；勿把 MAP-CC 语料混入 | research_G4G5G10.md |
| —（原报告门类列为「—」） | CLEVA | 已排除 | 31 任务 / ≈370k 中文样本 | ZH | CC BY-NC-ND 4.0 | ❌ 不可商用，且 ND 禁止改编 | 中 | 未核实 | 未给出 | 理由：ND 条款尤其致命，不可改不可商用，中文覆盖再广也不可用 | research_G4G5G10.md |
| G4 | IFEval | 主盘（取判分器，不取题） | 541 prompts / 25 种可验证指令 | EN | Apache-2.0 | ✅ | 高（几乎所有模型卡都报），但规则判分对污染不敏感 | 未核实 | 不取题，取判分器 | 直接复用其 25 类校验器代码做「格式合规率」引擎；它给的是框架而非规约内容，企业私域规约仍须自写 | research_G4G5G10.md |
| G4 | Multi-IF | 已排除 | 4,501 段三轮对话 / 8 语种（含中文） | 多语 | CC BY-NC-SA 4.0 | ❌ 不可商用（NC），且 SA 传染 | 中 | 未核实 | 未给出 | 理由：许可证劝退，只能内部用；仅借其多轮多语指令遵循方法 | research_G4G5G10.md |
| G4 | FollowBench | 仅方法借鉴 | 未核实 | EN（+部分 ZH，未核实） | Apache-2.0 | ✅ | 中 | 未核实 | 未给出 | 借「同题逐级加约束」1→5 级难度阶梯设计，用于制造格式规约的区分度 | research_G4G5G10.md |
| G4 / G5 | InFoBench | 仅方法借鉴 | 500 instructions | EN | MIT | ✅ | 中 | 未核实 | 未给出 | 借 DRFR：把 G4 格式规约、G5 风险要素清单拆成 yes/no 原子项统计满足率 | research_G4G5G10.md |
| G4 | CFBench | 主盘 | 1,000 条中文样本 / 10 大约束类 / 25+ 子类 | ZH | 未核实 | 未核实 | 中 | 未核实 | 100–150 条 | 落地前必须先直接读仓库 LICENSE；10 大约束类可直接映射我方格式规约分类学 | research_G4G5G10.md |
| —（原报告：与 G4/G10 不同源） | OfficeBench | 已排除 | 未核实 | EN | Apache-2.0（检索所得；arXiv 编号未核实） | ✅（以仓库声明为准） | 低 | 未核实 | 未给出 | 理由：是 agent 操作办公软件、不是写文案，名字像但不对口，避免误用 | research_G4G5G10.md |
| G10 | QMSum | 辅助（仅当输入素材） | 1,808 query-summary 对 / 232 场会议 | EN | 代码 MIT；文本源 CC BY 4.0 | ✅ | 中 | 未核实 | 与 MeetingBank 合计约 100–200 条素材级输入 | 只当「会议纪要 → 跟进沟通」的输入素材，不当题目 | research_G4G5G10.md |
| G10 | MeetingBank | 辅助（仅当输入素材） | 1,366 场会议 / 6,892 段级摘要对 | EN | CC BY 4.0 | ✅ | 中 | 未核实 | 同上（合计约 100–200 条） | 市政会议题材与企业办公有距离，只当素材 | research_G4G5G10.md |
| G10 | EnronQA | 辅助（仅当素材） | 103,638 邮件 / 528,304 QA 对 / 150 邮箱 | EN | 未核实 | 未核实 | 中 | 未核实 | 未给出 | 任务是 QA/检索不是「写回复」；含真人 PII，商业使用合规需谨慎 | research_G4G5G10.md |
| G5 | PlanBench | 已排除 | 未核实 | EN（PDDL 模板生成） | Apache-2.0 | ✅ | 中 | 未核实 | 0 条 | 理由：可验证符号规划 ≠ 开放式方案设计，金标是「计划是否可执行」而非「方案是否周全」，混用属方法论错误 | research_G4G5G10.md |
| G5 | Natural Plan | 已排除 | 未核实（3 域：Trip / Meeting / Calendar） | EN | 代码 Apache-2.0 + 数据 CC-BY-4.0 | ✅ | 中 | 未核实 | 0 条 | 理由：有唯一/可判定最优解，与 G5「无唯一解、看拆解与风险覆盖」根本不同源 | research_G4G5G10.md |
| G5 | TravelPlanner | 已排除 | 1,225 queries（45 train / 180 val / 1000 test） | EN | MIT | ✅ | 中 | 未核实 | 0 条 | 理由：不对口 G5；唯一可借的是「常识约束 + 硬约束」分层清单写法 | research_G4G5G10.md |
| G5 | EngDesign | 仅方法借鉴 | 开源子集 `EngDesign-OPEN` 53 任务 | EN | 未核实 | 未核实 | 低 | 未核实 | 未给出 | 判分依赖仿真脚本执行，我方商业/技术方案题跑不了仿真；只借其工程设计评测思路 | research_G4G5G10.md |
| G5 | BizCompass | 未核实（原报告定位列为「待核」，低置信） | 未核实 | EN（中文覆盖未核实） | 未核实 | 未核实 | 低（2026 新发布） | 未核实 | 未给出 | 方向对（含「顾问」角色），但数据可获取性与许可证均未核实，建议单独立项核实后再决定 | research_G4G5G10.md |
| G5 / G10 | EnterpriseClawBench | 仅方法借鉴 | 852 任务（Lite 子集 120） | EN | 代码 Apache-2.0；原始数据不公开 | 数据拿不到 | 低 | 未核实 | 未给出 | 借「硬规则 + 语义 judge + 成本/结果」三合一的企业评测设计；数据不开放 | research_G4G5G10.md |
| G10 | SOTOPIA | 仅方法借鉴 | 90 社交情境 × 40 角色画像 | EN | 代码 MIT（配套站点 CC BY-SA 4.0；`sotopia-pi` Apache-2.0） | ✅ | 中 | 未核实 | 未给出 | 借 SOTOPIA-Eval 7 维社交 rubric 并裁剪为职场版；90 个情境是生活社交，题目不能直接用 | research_G4G5G10.md |
| G10 | ESConv | 仅方法借鉴 | 1,300 段情感支持对话 / 10 类问题 | EN | CC BY-NC 4.0 | ❌ 不可商用 | 中 | 未核实 | 未给出 | 借 Helping Skills 策略分类体系（提问/重述/肯定/提供信息/建议…）映射为话术策略标签；数据本身不可用 | research_G4G5G10.md |
| G10 | CaSiNo | 仅方法借鉴 | 1,030 段协商对话 | EN | Cornell 官方 CC BY 4.0（Kaggle 镜像标 CC BY-NC-SA 4.0，以官方为准） | ✅（按官方） | 低-中 | 未核实 | 未给出 | 露营物资协商，题材完全不对口；借多轮协商策略标注维度 | research_G4G5G10.md |
| Judge校准 | JudgeBench | 主盘 | 350 对（GPT-4o 生成）+ 270 对（Claude 3.5 生成） | EN | 未核实 | 未核实 | 低（专为抗污染设计） | 未核实 | 全量（与 RewardBench 2、LLMBar 合计 ≈2,900 条） | 直接采用：用有客观正误的题反测 Judge，规避「用偏好评偏好」的循环论证 | research_G4G5G10.md |
| Judge校准 | RewardBench | 辅助 | 2,985 条 (prompt, chosen, rejected) | EN | ODC-BY | ✅ | 中（已被广泛用于 RM 调参、存在过拟合） | 未核实 | Chat-Hard 子集为辅 | 以 v2 为主、v1 的 Chat-Hard 子集为辅 | research_G4G5G10.md |
| Judge校准 | RewardBench 2 | 主盘 | 1,865 条（best-of-4 形式） | EN | ODC-BY | ✅ | 低（新、更抗刷） | 未核实 | 全量 1,865 条 | 直接采用，作抗污染主锚 | research_G4G5G10.md |
| Judge校准 | LLMBar | 主盘 | 419 对（Natural + Adversarial） | EN | MIT | ✅ | 低-中 | 未核实 | 全量 419 条（Adversarial 子集尤其重要） | 直接采用：专治 Judge 被「长/漂亮但没遵循指令」的答案骗——正是 G4 格式合规最怕的失效模式 | research_G4G5G10.md |
| Judge校准 | JudgeLM-100K | 已排除（作校准金标） | 100k 训练 + 5k 验证 | EN | 未核实（模型权重基于 LLaMA 许可证；数据集自身许可证未核实） | 未核实；源自 GPT-4 输出，带 OpenAI ToS 衍生风险 | 中-高 | 未核实 | 未给出 | 理由：金标本身是 GPT-4 产出，不适合当校准金标；只适合训练自家 Judge | research_G4G5G10.md |
| Judge校准 | Auto-J | 辅助 | 覆盖 58 个真实场景 | EN + ZH（6B 双语版） | 13B: Llama 2 Community License；6B: Yi License（均非标准 OSS，商用需逐条读条款） | ⚠️ 有条件 | 中 | 未核实 | 未给出 | 借 58 场景分类体系 + 每场景 criteria，作门类内细分场景的现成参照（且有中文 6B 版） | research_G4G5G10.md |
| Judge校准 | Prometheus 2 / Feedback & Preference Collection | 主盘（开源对照组） | Feedback Collection：1,000 rubric / 20k 指令 / 100k 反馈；Preference Collection：1k 自定义准则 pairwise | EN | Apache-2.0 | ✅ | 中（Feedback Collection 由 GPT-4 合成） | 未核实 | 未给出 | 作闭源 Judge 的独立第二意见（支持任意自定义 rubric）；其 Feedback Collection 属 GPT-4 合成，不得当 κ 金标 | research_G4G5G10.md |
| Judge校准 | FLASK | 仅方法借鉴 | 1,740 实例 / 4 能力 / 12 细粒度技能 | EN | CC BY 4.0 | ✅ | 中 | 未核实 | 未给出 | 借技能级细粒度分解打分 + 人类/模型双轨对照（按维度分别算 κ） | research_G4G5G10.md |
| Judge校准 | G-Eval | 仅方法借鉴 | 方法（非数据集） | EN | 代码 MIT（论文 CC BY-NC-ND 4.0） | ✅（代码） | —（原报告污染风险列为「—」） | 未核实 | 未给出 | 借 CoT + form-filling + token 概率加权分数，缓解整数分粒度过粗 | research_G4G5G10.md |
| Judge校准 | RubricEval | 未核实（原报告定位列为「待核」，低置信） | 3,486 条 rubric 级判定实例（2,034 Easy / 1,452 Hard） | EN（中文覆盖未核实） | 未核实 | 未核实 | 低 | 未核实 | 未给出 | 若属实，取其「逐条 rubric 核验会误差累积」的警告（GPT-4o 在 Hard 子集仅 55.97%）；引用前须独立验证 | research_G4G5G10.md |

## 表 2：可覆盖比例

| 门类 | 公开集可覆盖比例 | 估计依据（一句话） | 必须自建的是什么 |
|---|---|---|---|
| G4 文案撰写 | 约 25–30%（数据侧）；方法侧约 70% | 可覆盖的只有通用写作质量打分（WritingBench 1,239 题中约 2–3 个域与商务沾边）、长度约束（LongBench-Write 中文 60 条）、机械格式合规（IFEval 25 类判分器 + CFBench 中文约束类目） | 中文办公文体（邮件/周报/通知/纪要/公文/对外公告）——检索确认不存在广泛引用的公开评测集；企业私域格式规约（公司模板、字段顺序、抬头落款、品牌语气指南）；中英术语一致率金标（术语对照表）；「素材 → 文案」这一形态 |
| G5 方案设计 | **< 10–15%，且这 10–15% 全部是「方法」，数据侧可用题目为 0 条 —— 必须全自建** | 逐一核实后，没有任何一个公开集的金标形式是「Rubric（拆解/可行性/风险覆盖）+ 风险要素清单」；PlanBench / Natural Plan / TravelPlanner 属可验证规划的不同任务族，EngDesign 靠仿真判分，BizCompass 未核实，EnterpriseClawBench 原始数据不公开 | **题库、风险要素清单、基线方案，三样都必须从零自建**：建议起步 80–120 道（技术方案 / 项目规划 / 流程改造 各 30–40 道），每题配 8–15 条风险要素清单 + 一份基线方案（用于 pairwise） |
| G10 工作沟通与建议 | 约 15–20%（且主要是「素材」和「偏好校准」，不是「题目」）；方法侧约 60% | 可覆盖偏好对标注规程与校准锚（HelpSteer3，CC-BY-4.0）、少量真实职场 query（WildBench 过滤）、会议类输入素材（QMSum / MeetingBank） | 职场情境题目本体（难处理邮件、向上汇报坏消息、跨部门协调、绩效面谈、拒绝不合理需求）——SOTOPIA 是生活社交、ESConv 是心理情感支持、CaSiNo 是露营物资协商，没有一个是职场；中文职场语境（不能靠翻译迁移）；人类偏好对的职场版；自建建议 100–150 道 |
| Judge 校准 | 约 70–80%（英文部分几乎全覆盖，中文部分需自标） | 英文侧的准入体检、对抗性测试、客观标签反测、人类偏好锚四条链路均有可商用（ODC-BY / MIT / CC-BY-4.0）的成熟公开集，基本不需自建 | 缺口只在中文：中文场景 κ ≥ 0.7 必须靠自标样本证明，建议每门类 100–150 条 × 3 名标注员，中文自标 300–450 条做 κ 的正式测算 |

## 3. Rubric 与 Judge 方法论可借鉴清单

1. **实例级 criteria 动态生成**：全局维度骨架 + 每题生成 5 条实例化判据，消除「口吻」「规范」在不同题间的尺度漂移 —— WritingBench（阿里 X-PLUG，arXiv:2503.05244）。
2. **原子化需求分解 DRFR**：把 rubric 拆成若干 yes/no 需求项统计满足率，比让 Judge 打 1–5 分稳得多 —— InFoBench（MIT）。
3. **checklist + 权重回归对齐人类**：用小样本人工打分线性回归学各 criterion 权重，不要等权平均（否则「结构」这类易得分维度会拉高均分） —— HelloBench / HelloEval（MIT）。
4. **技能级细粒度分解 + 人类/模型双轨打分**：同一批样本同时跑人类与 Judge，**按维度分别算 κ 而非只算总分 κ** —— FLASK（CC BY 4.0，ICLR 2024）。
5. **多层级约束阶梯**：同题逐级叠加约束（1→5 级）制造区分度，避免所有模型拿满分 —— FollowBench（Apache-2.0，ACL 2024，arXiv:2310.20410）。
6. **BPC 平衡位置校准**：同一对同时评 [A,B] 与 [B,A] 后聚合出结论，pairwise 必做，否则位置偏差直接污染结论；配套 **MEC 多证据校准**（先生成多份评估理由再给分）与 **HITLC**（用 BPDE 挑高不确定样本交人工复核，论文报告减少 39% 人工标注量） —— Wang et al., *Large Language Models are not Fair Evaluators*（2023 / ACL 2024）。
7. **长度控制 win-rate**：GLM logistic 回归，在长度差为 0 处取条件偏好；论文报告与 Arena 的 Spearman 从 0.94 → 0.98。不做则「方案写得长」会被误判为「方案更周全」 —— AlpacaEval 2.0 LC。
8. **pairwise 统计口径**：Bradley-Terry 建模 + bootstrap 95% CI + style control，win-rate 必须带误差棒，否则模型差异判不出显著 —— Arena-Hard-Auto（Apache-2.0）。
9. **防高端饱和**：Rubric 分 + 邻近对手 Elo（Glicko-2）混合，解决「强模型 rubric 均分都 ≥4.5 区分不开」 —— EQ-Bench Creative Writing v3（MIT）；配合 **G-Eval 的 token 概率加权分数**缓解整数分粒度过粗（对「≥4.0/5」这类阈值指标尤其关键，代码 MIT）。
10. **Judge 校准协议（四步）**：① 准入体检——候选 Judge 先跑 RewardBench 2（1,865 条，ODC-BY）+ LLMBar Adversarial（MIT）+ JudgeBench（客观标签），任一项显著低于开源 SOTA 不予采用；② 循环论证规避——**不得**用 GPT-4 生成的偏好数据（Nectar、JudgeLM-100K、Prometheus Feedback Collection）作 κ 金标，它们只适合训练；③ 人类锚——英文用 HelpSteer2/3（CC-BY-4.0，带多维分与理由），中文必须自标；④ 开源对照组 Prometheus 2（Apache-2.0）作第二意见，并把 position conflict rate（交换顺序后结论翻转的比例）作为 Judge 健康度指标常态化监控。

## 4. 本片许可证要点

1. **明确不可商用**：CLEVA（CC BY-NC-ND 4.0，ND 还禁止改编，最严）、Multi-IF（CC BY-NC-SA 4.0，SA 有传染性）、ESConv（CC BY-NC 4.0）、Chatbot Arena 的**模型输出部分**（CC-BY-NC-4.0；prompts 部分是 CC-BY-4.0 可商用）。
2. **GPT-4 输出衍生数据的 ToS 风险**：AlpacaEval（评测标签与基线输出）、Nectar（GPT-4 排序）、JudgeLM-100K（GPT-4 判分）、Prometheus Feedback Collection（GPT-4 合成）。仓库虽标 Apache-2.0/MIT，但内容源自 OpenAI API 输出；该条款是 OpenAI 与 API 调用方之间的合同约定，不自动附着于下游使用者的著作权许可，但**用于训练我方模型仍有合规风险**。Nectar 更是把该限制明文写进了数据卡条件。结论：可用于「评测」，用于「训练」前须过法务。
3. **附条件开源许可证**：Auto-J 的 13B（Llama 2 Community License，有 MAU 阈值条款）与 6B（Yi License）——都不是标准 OSS 许可证，商用须逐条读。
4. **署名义务**：ODC-BY（WildBench/WildChat、RewardBench、RewardBench 2）与 CC-BY-4.0（HelpSteer2/3、Natural Plan 数据、MeetingBank、FLASK、QMSum 源文本）均要求保留署名，需在我方 benchmark 文档中列明出处。
5. **镜像与官方口径不一致**：CaSiNo 官方为 CC BY 4.0，Kaggle 镜像标 CC BY-NC-SA 4.0 —— 以官方为准，并从官方渠道取数。
6. **许可证未核实、落地前必须复核**：CFBench（须直接读仓库 LICENSE 文件）、ProxyQA、JudgeBench、JudgeLM-100K 数据集自身、EnronQA、EngDesign、BizCompass、RubricEval；AlignBench 仅确认仓库层面 Apache-2.0，数据条款未单列。
7. **数据根本拿不到**：SuperCLUE 核心评测集刻意不公开（仓库 MIT）；EnterpriseClawBench 原始数据不公开，仅开源构建与评测代码（Apache-2.0）。
8. **PII 与配套语料冲突**：Enron / EnronQA 为真实企业邮件，含大量个人信息，即便属研究用公共领域，商业场景仍有隐私合规风险；CHC-Bench 评测部分 Apache-2.0，但配套 MAP-CC 预训练语料为 CC BY-NC-ND 4.0，不可混用。

## 5. 本片污染要点

1. **MT-Bench（80 题）——高污染，不得作准入依据**：2023 年起几乎进了所有后训练评测环路，榜单饱和、位置/冗长偏差已被反复记录。
2. **AlpacaEval 2.0（805 题）——高污染**：题目是公开优化目标，length-hacking 众所周知；题目不要用，只借 LC 方法。
3. **Arena-Hard-Auto（500 题）——高污染**：500 题公开且被广泛用作调参目标；只借统计方法，不进题库。
4. **AlignBench——污染高**：中文圈最常引用的对齐评测，已被广泛训练，题目污染重，只借范式。
5. **IFEval——污染标为「高」但性质不同**：几乎所有模型卡都报 IFEval，然而规则判分对污染不敏感，因此仍可作格式合规率引擎；但不宜作区分度依据。
6. **Judge 校准侧**：RewardBench v1 已被广泛用于 RM 调参、存在过拟合，应以 RewardBench 2（污染低）为主、v1 的 Chat-Hard 子集为辅；Nectar、JudgeLM-100K 为 GPT-4 合成（中-高），不得当校准金标。

## 6. 冲突与待裁决

- 许可证表述不一致：CaSiNo 官方 CC BY 4.0 vs Kaggle 镜像 CC BY-NC-SA 4.0（原报告裁定以官方为准）。
- 许可证层级不一致：AlignBench 仓库 Apache-2.0，数据条款未单列，原报告建议复核。
- 许可证层级不一致：CHC-Bench 评测数据/代码 Apache-2.0，配套 MAP-CC 语料 CC BY-NC-ND 4.0。
- 许可证层级不一致：SOTOPIA 代码 MIT / 配套站点 CC BY-SA 4.0 / `sotopia-pi` Apache-2.0。
- 许可证层级不一致：Chatbot Arena prompts CC-BY-4.0 vs 模型输出 CC-BY-NC-4.0。
- 许可证层级不一致：QMSum 代码 MIT / 文本源 CC BY 4.0；Natural Plan 代码 Apache-2.0 / 数据 CC-BY-4.0；G-Eval 代码 MIT / 论文 CC BY-NC-ND 4.0。
- 许可证与附加条件冲突：Nectar 标 Apache-2.0，但数据卡附加「不得用于与 OpenAI 竞争」的条件。
- 规模说法不一：EQ-Bench 情商版情境数，检索给出 60 与 45 两个不同数字（对应不同版本），原报告写「45–60（版本而异）」。
- 定位待裁决：EQ-Bench（情商/roleplay）在原报告适配表标「改造」，但「借数据 / 借方法」总账的 G10 借数据未列入它；本表暂列「辅助」，需确认是否降为「仅方法借鉴」。
- 定位待裁决：BizCompass、RubricEval 原报告标「待核 / 低置信」，本表定位列保留「未核实」，不强行归类。
- 门类待裁决：SuperCLUE、CLEVA 原报告「对应门类」列为「—」，本表原样保留，未强行归入 G4/G5/G10/Judge校准。
- 未核实字段清单（原样保留，使用前必须复核）：CFBench 许可证；FollowBench 数据集规模条数；JudgeBench 许可证；JudgeLM-100K 数据集自身许可证；ProxyQA 仓库地址/许可证/规模；OfficeBench arXiv 编号/仓库名/规模；EnronQA arXiv 编号/许可证/HF repo；EngDesign 仓库地址/许可证；BizCompass 数据可获取性/许可证/规模/是否含中文；EnterpriseClawBench 论文出处；RubricEval 仓库/许可证/是否真实发表；AlignBench 数据条款；EQ-Bench 情商版规模。
- 列级缺口：「环境成本」原报告未设该字段，故表 1 全列一律「未核实」，未做任何推断；「建议采样量」原报告只给了 G4/G10/Judge 的部分条目与 G5 的「取 0 条」，其余记「未给出」。
