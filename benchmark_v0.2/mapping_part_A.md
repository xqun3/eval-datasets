# 映射表片段 A —— G1 知识问答 / G3 内容理解 / G2 信息检索

> 归纳自 `research_G1G3.md` 与 `research_G2.md`，不新增任何两份报告以外的事实。
> 原报告标「未核实」的字段一律原样保留，不做推断填充。

## 表 1：门类 × 公开集 主映射表

| 门类 | 数据集 | 定位 | 规模 | 语言 | 许可证 | 可商用 | 污染风险 | 环境成本 | 建议采样量 | 需要的改造 | 来源报告 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| G1 | SimpleQA Verified | 主盘 | 1,000 | 英文 | MIT | ✅ | 中（2025 发布，做了去重与 holdout 强化，比原版略干净） | 低 | 400 | 很小：补 `facts:[<答案>]` 列与「专家参考答案」字段；grader 照搬 SimpleQA 官方三分类模板 | research_G1G3.md |
| G1 | Chinese SimpleQA | 主盘 | 3,000（6 大类 99 子类） | 中文 | MIT | ✅ | 中（中文语料爬取滞后于英文，污染略轻于英文 SimpleQA） | 低 | 600 | 很小：同上；中文侧几乎唯一成熟对口集 | research_G1G3.md |
| G1 | FRAMES | 辅助（难档 / 多跳） | 824 | 英文 | Apache-2.0 | ✅ | 中 | 低 | 200 | 中等：支撑维基页面列表 ≠ 事实点，需人工把答案链拆成 3–6 条 atomic facts（约 800 条，1 名标注员 2–3 天） | research_G1G3.md |
| G1+G3 | FActScore | 仅方法借鉴 | 评测方法 + 人名传记生成任务；标注样本量**未核实** | 英文 | MIT | ✅ | 不适用（是方法，不是固定题库） | 低 | 采方法不采数据 | 判分器按其 decompose → verify 两段式搭 | research_G1G3.md |
| G1 | HalluQA | 辅助（中文幻觉 spot-check） | 450 对抗性问题 | 中文 | MIT | ✅ | 中高（题量仅 450，易被针对性覆盖） | 低 | 150 | 轻改造；题量太小只能做 spot-check | research_G1G3.md |
| G1 | HaluEval | 仅方法借鉴 | 35,000（5,000 通用 query + 30,000 任务样本） | 英文 | MIT | ✅ | 高（2023 年集，MIT 全开放） | 低 | 不进主盘 | 是判别任务不是生成任务；只用来训练/校准我方幻觉判别器 | research_G1G3.md |
| G1 | GPQA (Diamond) | 上限探针 | Diamond 198；main 448；extended 546 | 英文 | 数据集卡 CC BY 4.0；代码仓 `idavidrein/gpqa` 另有 MIT 表述，两处不一致 | ✅（需署名） | 中（有官方 canary、HF gated，但前沿模型评测广泛使用，泄漏压力上升） | 低 | 需改造 | 硬核理科题，与通用办公语境不对口，只适合做上限探针 | research_G1G3.md |
| G1 | Natural Questions | 辅助（人工标注原料库） | 307,373 条单标注训练样本（dev/test 规模**未核实**） | 英文 | CC BY-SA 3.0 | ✅（须同协议开放衍生物，SA 传染） | 极高（2019 年集，维基正文 + 该集本身几乎必在所有预训练语料中） | 大 | 仅作原料 | 只能拿来做人工标事实点的原料，不能直接当分数盘 | research_G1G3.md |
| G1 | MMLU-Pro | 已排除 | 12,032（论文口径；HF 线上表约 12,102 行，两者不一致，以 HF 实际下载为准） | 英文 | MIT | ✅ | 高 | 低 | — | 排除理由：10 选项选择题产不出 atomic facts，也测不出幻觉率；改写成开放问答再人工拆点成本高 | research_G1G3.md |
| G1 | TriviaQA | 已排除 | 95,000+ QA 对（含证据的三元组 650K+；unfiltered 约 110K QA） | 英文 | 混合：代码 Apache-2.0；Kaggle 镜像标 CC0，原作者声明不拥有抓取内容版权 → 许可证不干净 | ⚠️ 有风险，商用需法务确认 | 极高（2017 年集，长期被当训练集） | 大 | — | 排除理由：污染已经到「没有测量价值」的程度 | research_G1G3.md |
| G1 | TruthfulQA | 已排除 | 817 问，38 类 | 英文 | Apache-2.0 | ✅ | 极高（几乎所有对齐数据集都拿它做过 RLHF/SFT 目标，早已过拟合） | 低 | — | 排除理由：分数虚高、失去判别力；只建议取其「误信陷阱」设计思路 | research_G1G3.md |
| G1 | C-Eval | 已排除 | 13,948，52 学科 4 难度 | 中文 | 数据 CC BY-NC-SA 4.0；代码 MIT | ❌ 不可商用 | 极高（中文社区默认刷榜集） | 中 | — | 排除理由：学科选择题形态 + 不可商用 + 高污染，三条都不利 | research_G1G3.md |
| G1 | CMMLU | 已排除 | 11,528，67 主题 | 中文 | CC BY-NC-SA 4.0 | ❌ 不可商用 | 极高（同 C-Eval） | 中 | — | 排除理由：同 C-Eval | research_G1G3.md |
| G1 | AGIEval | 已排除 | 20 个任务（18 选择 + 2 完形）；总题数**未核实** | 中英 | 代码 MIT；题目本身沿用各原始考试的条款 | ⚠️ 逐子集判定，整体不建议直接商用 | 高（考试真题常年在网上） | 中 | — | 排除理由：考试导向，与办公事实问答无关 | research_G1G3.md |
| G1 | CLUE / SuperCLUE | 已排除 | CLUE 为多子集套件；SuperCLUE 含 CArena/OPEN/CLOSE 三轨，题量**未核实** | 中文 | CLUE 代码 MIT；子集各自不同（如 OCNLI 为 CC BY-NC 2.0）；SuperCLUE 许可证**未核实** | ⚠️ 逐子集判定 | 高（CLUE 系已充分公开多年） | 中 | — | 排除理由：更像中文 NLP 综合榜，不是事实点召回评测 | research_G1G3.md |
| G1 | CRAG | 仅方法借鉴 | 4,409 QA 对，5 领域 8 题型 | 英文 | CC BY-NC 4.0 | ❌ 不可商用 | 中（KDD Cup 后被大量复现） | 中 | — | 只借判分设计（答对 +1 / 弃答 0 / 幻觉 −1），数据不入库 | research_G1G3.md |
| G3 | RULER | 主盘（needle 命中率） | 合成、规模可配置（13 任务 / 4 类；固定条数不适用） | 英文（可扩展） | Apache-2.0 | ✅ | **低——完全合成，长度与 needle 内容可现场随机生成，结构上无法被污染** | 中（4K/16K/32K/64K/128K 五档长上下文） | 500（五档 × 100，每次评测重新随机生成） | 低：haystack 换成我方中文办公语料 + 设计中文 needle 模板 | research_G1G3.md |
| G3 | Loong | 主盘（多文件输入） | 1,600 测试实例，平均约 11 篇文档/例 | 中英 | Apache-2.0 | ✅ | 中（2024 发布） | 高（多文档，10K–>200K 四档） | 250（四档均分） | 中等：金标是自由文本，需人工拆「关键信息点清单」；先只拆 Chain-of-Reasoning 与 Clustering 两类 | research_G1G3.md |
| G3 | CLongEval | 主盘（中文长文） | 7,267，7 个任务，1K–100K tokens 三档 | 中文 | MIT | ✅ | 中（中文集被英文主导语料收录概率相对低） | 中高 | 300（三个长度档） | 中等：同样需把参考答案拆成关键信息点清单 | research_G1G3.md |
| G3 | LongBench v2 | 上限探针 | 503 | 中英 | Apache-2.0 | ✅ | **中低——2024-12 发布，专家新写题、依赖长程推理而非记忆，硬背难奏效** | 高（8k–2M 词） | 150（按长度分层） | 低：作 Accuracy 探针直接用，不并入 KeyPoint-Recall | research_G1G3.md |
| G3 | LongBench (v1) | 辅助（只挑中文子集） | 4,750 测试样本 / 21 数据集（14 英 + 5 中 + 2 代码） | 中英 + 代码 | 仓库 MIT（底层子集各自原许可证需逐一确认） | ⚠️ 逐子集判定 | 高（2023 年集，被大量长上下文模型调参和训练） | 中 | 只取中文子集 | 需改造：子集挑选 + 许可证逐一清点 | research_G1G3.md |
| G3 | ∞Bench (InfiniteBench) | 辅助（超长档补充） | 3,946 / 12 任务，平均约 200K tokens，全部 >100K | 中英 | MIT | ✅ | 中高（2024 年集，MIT 全开放，已被广泛引用） | 高（>100K） | — | 需改造；任务偏小说/代码，办公味淡 | research_G1G3.md |
| G3 | HELMET | 仅方法借鉴 | 7 类应用场景；**总条数未核实**（长度 8K–128K+ 可配置） | 英文 | MIT | ✅ | 中（2024 发布） | 高 | 参考其评测框架 | 当评测框架模板用，不当题库；其 7 类切分与我方 G3 子能力几乎一一对应 | research_G1G3.md |
| G3 | LongCite / LongBench-Cite | 仅方法借鉴 | **未核实** | 中英 | 仓库 Apache-2.0 / MIT 两处表述不一致，需以仓库 LICENSE 为准 | ✅ 大概率可商用 | 中（2024 发布） | 中高 | 参考其判分 | 采其范式：把 Faithfulness 从「像不像」变成「指得回原文吗」 | research_G1G3.md |
| G3 | FaithBench | 辅助（判分器校准，首选） | **未核实**（按「各主流 LLM 摘要 + 人工幻觉标注」组织） | 英文 | 数据 CC BY-NC-SA 4.0 / CC BY-SA 4.0 两种表述并存，需以仓库 LICENSE 为准；代码 MIT | ⚠️ 大概率不可商用 | **低中——2024 发布，标注的是各家 LLM 的实际输出，难以被预训练记住** | 低 | 全量跑，不抽样 | 采其标注校准我方 Faithfulness judge；仅内部校准，不进产品 | research_G1G3.md |
| G3 | SummEval | 辅助（判分器校准，备选） | 100 篇原文 × 16 个模型输出 = 1,600 条摘要，4 维人工打分 | 英文 | 代码仓 MIT；论文 CC BY 4.0；底层 CNN/DM 原文另有条款 | ⚠️ 标注可商用，原文需确认 | 高（2021 年，CNN/DM 早已污染） | 低 | 全量跑 | 元评测用途：验证我方忠实度打分器与人类是否一致 | research_G1G3.md |
| G3 | QMSum | 辅助（会议摘要形态校准） | 232 场会议，1,808 query-summary 对 | 英文 | MIT | ✅ | 高（2021 年集，被大量摘要模型训练/微调使用） | 中 | 100 | 需改造：人工把参考摘要拆成关键信息点清单；只取少量做对齐校准 | research_G1G3.md |
| G3 | LooGLE | 辅助（优先级排在 Loong 之后） | 776 长文档，6,448 问题 | 英文 | MIT | ✅ | 高（2023 年集） | 中 | — | 需改造；长依赖设计不错但纯英文 | research_G1G3.md |
| G3 | L-Eval | 已排除 | 20 个子任务；总条数**未核实** | 英文为主 | **GPL-3.0** | ⚠️ GPL 传染性强，不要与产品代码混仓 | 高（2023 年集） | 中 | — | 排除理由：内容尚可但 GPL-3.0 工程上容易踩坑，建议不引入 | research_G1G3.md |
| G3 | NarrativeQA | 已排除 | 1,572 故事，46,765 QA 对 | 英文 | Apache-2.0（原始书籍/剧本文本版权另论） | ⚠️ 标注可商用，底层长文本版权需确认 | 极高（2018 年集，底层是公版书籍/剧本，必在预训练语料中） | 中 | — | 排除理由：老且污染，叙事题材离办公远 | research_G1G3.md |
| G3 | MeetingBank | 已排除 | 1,366 场市议会会议 | 英文 | CC BY-NC-SA 4.0 | ❌ 不可商用 | 高（2023 年集，被 LLMLingua 等压缩工作反复使用） | 中 | — | 排除理由：禁商用；市议会官僚语体与企业内部会议差异大 | research_G1G3.md |
| G3 | AMI Meeting Corpus | 已排除（只能当格式参考） | 171 场会议，约 100 小时 | 英文 | CC BY 4.0 | ✅（需署名） | 极高（2005 年起公开，语音/NLP 领域标准语料） | 中 | — | 排除做主盘：太老、英式学术会议场景 | research_G1G3.md |
| G3 | ELITR Minuting Corpus | 已排除（形态最近但不可商用） | 179 场会议（120 英 + 59 捷克），约 180 小时 | 英文 / 捷克语 | CC BY-NC-SA 4.0 | ❌ 不可商用 | 中（捷克机构小众语料，被大规模收录概率较低） | 中 | — | 排除理由：非商用；且英/捷双语，中文缺位。公开集里最像「真实项目会议纪要 + action item」的一个，可惜许可证不行 | research_G1G3.md |
| G3 | QAGS | 已排除（与 SummEval 二选一） | CNN/DM + XSUM 上的人工忠实度标注；**条数未核实** | 英文 | **未核实**（仓库 `W4ngatang/qags` 未见明确 LICENSE 文件；论文按 ACL CC BY 4.0） | ⚠️ 未确认 | 高（2020 年） | 低 | — | 与 SummEval 同作用，二选一即可，优先 SummEval | research_G1G3.md |
| G3 | Needle-In-A-Haystack (NIAH) | 已排除（被 RULER 严格超集覆盖） | 生成式脚本，无固定条数 | 任意（自备语料） | MIT | ✅ | **无——现场生成** | 低 | — | 排除理由：只测检索不测理解，RULER 是它的严格超集，直接改用 RULER | research_G1G3.md |
| G2 | BEIR（18 数据集聚合） | 辅助（仅小语料子集作 sanity check） | 查询数：各子集不同（TREC-COVID 50 / NFCorpus 323 / SciFact 300 / FiQA-2018 648 / SCIDOCS 1,000 / Touché-2020 49 / HotpotQA 7,405 / NQ 3,452 / DBPedia 400 / Climate-FEVER 1,535 / Quora 10,000）；语料规模：3.6k ~ 1500 万文档（跨子集），单子集示例 NFCorpus 3,633 / SciFact 5,183 / SCIDOCS 25,657 / FiQA 57,638 / TREC-COVID 171,332 / Touché 382,545 / Quora 522,931 / NQ 2,681,468 / DBPedia 4,635,922 / HotpotQA 5,233,329 / Climate-FEVER 5,416,593 | 英文为主 | 代码 Apache-2.0；**数据逐子集不同**。HF `BeIR/beir` 顶层卡片标 CC-BY-SA-4.0，但维护者声明「只做格式化与再分发，不转让任何版权/使用许可」 | 部分可 / 部分不可，必须逐子集判定 | 高（过去 4 年 embedding 模型事实上的评测与调参目标） | 小子集可整包（NFCorpus 3,633 / SciFact 5,183）；SCIDOCS / FiQA / TREC-COVID 需下采样到 1–3 万；>50 万的子集全量不现实 | 仅 SciFact / NFCorpus / SCIDOCS / FiQA 作 sanity check | 需重改造：整包不可用（至少 4 个子集不可商用或不可自由分发）；报告里必须明写污染警告 | research_G2.md |
| G2 | MTEB | 已排除 | 查询数：58 数据集 / 8 类任务 / 112 语言（检索子集主要复用 BEIR）；语料规模：同 BEIR | 多语 | 代码 Apache-2.0；各底层数据集许可证各异 | 需逐任务判定 | **极高**（leaderboard 本身就是 embedding 厂商的优化目标，过拟合公认严重） | 同 BEIR | — | 排除理由：只能当「选哪个 embedding 模型」的参考，不能当我方 G2 评测集 | research_G2.md |
| G2 | C-MTEB / CMTEB Retrieval | 辅助 | 查询数：8 个中文检索集，测试样本 T2Retrieval 24,832 / MMarcoRetrieval 7,437 / DuRetrieval 4,000 / CmedqaRetrieval 3,999 / EcomRetrieval 1,000 / MedicalRetrieval 1,000 / VideoRetrieval 1,000 / CovidRetrieval 949；语料规模：**未核实**（各 `C-MTEB/*Retrieval` 自带 corpus split，逐集规模未逐一查证） | 中文 | **未核实**（各 `C-MTEB/*` 卡片许可证未逐一确认；上游 T2Ranking Apache-2.0、DuReader Apache-2.0、mMARCO 继承 MS MARCO 非商用条款） | 混合；MMarcoRetrieval 继承 MS MARCO 非商用 → 不可商用 | 高（中文 embedding 模型普遍在此报分，部分训练集重叠） | EcomRetrieval / MedicalRetrieval 各 1,000，规模小适合做受控快照原型 | — | 需改造；需先把逐子集许可证核清 | research_G2.md |
| G2 | MS MARCO (Passage / Document) | 已排除 | 查询数：Passage 训练集约百万级；官方 dev small 6,980（**未核实**，仅凭常识，本轮未确认）；语料规模：Passage V1 ~880 万段落；Document V1 ~320 万文档；V2：1.38 亿段落 / 1,190 万文档 | 英文 | **Microsoft 自定非商用研究许可**：免费但仅限非商用研究，明确不授予商用 IP 权利。配套代码仓 MIT | ❌ 不可商用 | **最高——IR 领域第一大污染源，几乎所有主流 dense retriever 都在其上训练** | 全量不现实（>50 万，必须重构语料池） | — | 排除理由：非商用许可 + 最严重污染 | research_G2.md |
| G2 | TREC Deep Learning Track 2019–2023 | 已排除（做主集） | 查询数：2019 passage 43 / doc 43；2020 passage 54 / doc 45；2021 passage 53 / doc 57；2022 passage 76；2023 passage 82；语料规模：2019–2020 用 MS MARCO V1，2021–2023 用 V2（1.38 亿段落） | 英文 | 语料继承 MS MARCO 非商用条款；qrels 由 NIST 发布 | ❌ 不可商用（受 MS MARCO 约束） | 高（语料同 MS MARCO） | 全量不现实 | — | 排除理由：标注质量全场最好（深度 pooling），但 query 数极少（43–82），统计功效不足以单独支撑一个门类 | research_G2.md |
| G2 | TREC RAG Track 2024–2025 | 仅方法借鉴 | 查询数：301 条（采样自 Bing 日志）；语料规模：MS MARCO **V2.1** segment/document collection | 英文 | 语料受 MS MARCO V2.1 条款约束 | ❌ 不可商用 | 高（MS MARCO 语料） | 全量不现实 | — | 只借其评测协议：句级 segment 归属 + AutoNuggetizer 的 nugget 三档支持度（supported / partially / not supported），与人工评估 Kendall's τ 相关性高 | research_G2.md |
| G2 | MLDR (Multilingual Long-Doc Retrieval) | 主盘（长文档检索子能力） | 查询数：**未核实**（未查到逐语言 query 数）；语料规模：基于 Wikipedia / Wudao / mC4 构建，13 语言 | 13 语（含中文） | MIT（HF `Shitao/MLDR`） | ✅ 可商用 | 中（与 BGE-M3 同源发布，BGE 系模型有过拟合嫌疑；对非 BAAI 模型污染较低） | 中（长文档） | 中文 split 100–200 条 query | 需改造：query 由 GPT-3.5 生成、不是真人提问，风格偏书面，需人工改写一部分成办公口吻，或明确标注为合成 query | research_G2.md |
| G2 | T2Ranking | 主盘（中文检索首选之一） | 查询数：~30.8 万（搜狗日志采样）；语料规模：~230 万唯一段落 | 中文 | **Apache-2.0** | ✅ 可商用 | 中（中文模型常用作训练集，需检查所选模型训练配方） | 需下采样（230 万 → 3–5 万段落） | 200–300 条 query | 需下采样；无引用标注 → 只能测 retriever，不能测端到端引用，需另配生成层金标 | research_G2.md |
| G2 | DuReader-retrieval | 辅助 | 查询数：>9 万；语料规模：>800 万唯一段落 | 中文（含人工翻译的跨语 query 集） | **Apache-2.0** | ✅ 可商用 | 中高（中文 retriever 常见训练集） | 全量不现实（800 万，需大幅下采样） | 需下采样 | 需下采样；真实百度搜索日志，query 分布贴近真人提问 | research_G2.md |
| G2 | RAGBench | 主盘 | 查询数：10 万 examples；语料规模：由 12 个子集转成统一 RAG 格式（PubMedQA, CovidQA, HotpotQA, FinQA, TAT-QA, CUAD, MS MARCO, EManual, TechQA, ExpertQA, HAGRID, DelucionQA） | 英文 | **CC-BY-4.0** | ✅ 可商用 | 中高（子集 HotpotQA / MS MARCO / ExpertQA / HAGRID 均为高曝光公开集） | 中 | 500–800 例，按 12 个子集来源分层，优先 TechQA / EManual / CUAD / FinQA，避开 HotpotQA / MS MARCO 两个高污染子域 | 需把 TRACe 标注体系（relevance / adherence / completeness）映射到我方「相关文档 ID + 必须引用段落」schema | research_G2.md |
| G2 | CRAG (Comprehensive RAG) | 仅方法借鉴 | 查询数：4,409 QA 对，5 域 8 类问题；语料规模：Mock API 模拟 web search + KG，每题最多返回 50 个完整 HTML 页面（Brave Search 抓取） | 英文 | CC BY-NC 4.0 | ❌ 不可商用 | 中（KDD Cup 后被大量复现，2024 之后训练的模型可能见过） | 中高（每题 50 个完整 HTML 页面） | — | 只借评分逻辑（correct +1 / missing 0 / incorrect −1），与我方「假文档率 = 0」的硬约束哲学一致 | research_G2.md |
| G2 | FRAMES | 辅助 | 查询数：824 条多跳问题；语料规模：每题需综合 2–15 篇 Wikipedia 文章 | 英文 | **Apache-2.0** | ✅ 可商用 | 中高（2024 年 Google 发布后被广泛采用为 agentic search 评测） | 小（规模小，适合整包做受控快照） | — | 需改造：只给文章级而非段落级金标，达不到我方「必须引用的段落」这一金标要求，需补标 | research_G2.md |
| G2 | MultiHop-RAG | 主盘 | 查询数：2,556 条多跳 query（inference / comparison / temporal / null 四类）；语料规模：**609 篇英文新闻**，平均 2,046 token/篇（2023-09-26 ~ 2023-12-26） | 英文 | **ODC-BY 1.0** | ✅ 可商用（署名即可） | **低——语料池只有 609 篇 2023 年末新闻，非主流训练语料** | 低（609 篇可整包塞进 context，无需下采样） | 300–500（按四类等比分层） | 英文 → 中文办公场景需翻译或重构；「新闻」文体与「内部文档」文体有差距 | research_G2.md |
| G2 | HotpotQA | 已排除（只取 distractor 设置做能力诊断） | 查询数：~11.3 万 QA 对；语料规模：distractor 设置每题 10 段（2 gold + 8 distractor）；fullwiki 设置为全维基（BEIR 内为 5,233,329） | 英文 | **CC BY-SA 4.0** | ⚠️ 可商用但 SA 传染（衍生数据集必须同样 CC BY-SA 授权） | 高（既在 BEIR 里，又是无数 RAG 论文的默认集，训练污染广泛） | fullwiki 全量不现实 | — | 排除做主盘：句级 supporting facts 是难得的段落引用金标，但污染太重 | research_G2.md |
| G2 | 2WikiMultihopQA | 辅助 | 查询数：192,606 问题；语料规模：Wikidata 三元组 + Wikipedia 正文 | 英文 | **Apache-2.0** | ✅ 可商用 | 中高（多跳 RAG 论文标配） | 需下采样（192k 太多） | 需下采样 | 需下采样；结构化 evidence 三元组便于自动判「引用是否真支持断言」，许可证优于 HotpotQA | research_G2.md |
| G2 | ClapNQ | 主盘 | 查询数：4,946 条 grounded 长答案 QA（含 NQ 来的不可答问题）；语料规模：NQ Wikipedia passages（HF `PrimeQA/clapnq_passages`） | 英文 | **Apache-2.0** | ✅ 可商用 | 中（NQ 上游污染存在，但 ClapNQ 的长答案标注是新的） | 中 | 200–300（其中不可答样本占 20–30%） | 语料仍是 Wikipedia，需评估是否接受；答案由非连续片段拼成，正是真实办公 RAG 的形态 | research_G2.md |
| G2 | RAGAS | 仅方法借鉴（不是数据集，是评测框架） | — | — | 代码 Apache-2.0（具体版本**未核实**） | 代码可商用 | 不适用 | 低 | — | 作为自动评分器接入（faithfulness ≈ 引用可溯源率），但 LLM-judge 有偏，必须人工抽检约 10% 校准 | research_G2.md |
| G2 | ALCE | 主盘（引用可溯源率） | 查询数：三子任务各采样 1,000 条 dev（ALCE-ASQA 实际 948 条 × GTR/DPR/Oracle 三种检索 split）；语料规模：ASQA/QAMPARI 用 Wikipedia，ELI5 用 **Sphere（8.99 亿 Common Crawl 段落）** | 英文 | MIT（代码）；底层 ASQA Apache-2.0、ELI5 用 Sphere（Common Crawl，开放条款） | ✅ 可商用（ELI5 原始 Reddit 内容的衍生使用需谨慎） | 中高（2023 起被引用极多，主流模型可能见过 ASQA/ELI5） | ASQA / QAMPARI 可控；ELI5 依赖的 Sphere 8.99 亿段落做受控快照完全不现实 | ASQA + QAMPARI 各 200；**ELI5 建议放弃** | 需把评测脚本的 NLI 判定器换成中文可用模型；语料换成我方办公文档后需重新构造 gold citation | research_G2.md |
| G2 | QuoteSum / SEMQA | 主盘（零假引用金标） | 查询数：1,376 唯一问题（984 来自 PAQ，392 来自 NQ/AmbigQA）/ 4,009 条半抽取式答案；语料规模：多源段落 | 英文 | **Apache-2.0** | ✅ 可商用 | 低 | 低 | 150–250 | 半抽取式答案格式较特殊，需 prompt 层适配；纯英文。其「引文必须是可定位的原文 span」约束建议直接写进我方 G2 schema | research_G2.md |
| G2 | AttributionBench | 辅助（判别器校准） | 查询数：HF 标注规模区间 10K–100K；语料规模：聚合多个 attribution 评测源 | 英文 | **Apache-2.0** | ✅ 可商用 | 中 | 中 | — | 需改造；用来校准我方「引用是否支持断言」的判定器，而不是当主评测集 | research_G2.md |
| G2 | ExpertQA | 辅助 | 查询数：2,177 问题 / 32 个领域 / 484 位专家参与；语料规模：专家校验过的 attributed answers + 引用 | 英文 | **MIT** | ✅ 可商用 | 中 | 低 | — | 需改造；质量极高但规模小（2,177） | research_G2.md |
| G2 | HAGRID | 辅助 | 查询数：train 1,922 query / 3,214 答案；dev 716 query / 1,318 答案；语料规模：建在 **MIRACL 英文子集** 之上 | 英文 | **Apache-2.0** | ✅ 可商用 | 低中 | 中（语料受控） | — | 需改造；双维标注（informative / attributable）可用来拆解「答案有用」与「答案有据」两个常被混为一谈的维度 | research_G2.md |
| G2 | RAGTruth | 辅助（幻觉检测器训练/校准） | 查询数：~18,000 条 LLM 生成回复 / 2,965 个 source instance；语料规模：open-domain QA + data-to-text + news summarization 三类 | 英文 | **MIT** | ✅ 可商用 | 中 | 中 | — | 不当主评测集，当我方幻觉检测器的训练/校准集。⚠️ 2025 年有重标注研究指出原标注偏松、真实幻觉率更高（GPT 系 ~50%，老开源模型 80–90%），设阈值时别照搬原论文数字 | research_G2.md |
| G2 | REASONS | 已排除 | 查询数：句级引用标注，覆盖 12 个学科；语料规模：~2 万篇 arXiv 论文 | 英文 | **未核实**（arXiv 2405.02228；repo 与许可证未查到） | **未核实** | 低中 | 中 | — | 排除理由：学术引用场景专用，与办公场景偏差大；任务形态（给一句话找出处并检测编造出处）可借鉴 | research_G2.md |
| G2 | CRUD-RAG | 辅助（中文 RAG 首选参考） | 查询数：Create 10,728 / Read 单文档 QA 3,199 + 双文档 QA 1,506 / Update 幻觉修正 2,960 / Delete 多文档摘要 1,343；语料规模：中文新闻语料 | 中文 | 代码仓 **Apache-2.0**；**数据本身许可证未核实**（语料来自中文新闻，可能有第三方版权） | ⚠️ 需谨慎（新闻语料版权风险） | 中 | 中 | — | 需改造：四类任务里只有 Read（QA）直接对应 G2；缺段落级引用金标 | research_G2.md |
| G2 | DomainRAG | 已排除 | 查询数：**未核实**（论文报告六种能力划分，未查到逐项条数）；语料规模：中国高校招生官网抓取 | 中文 | **CC BY-NC-SA 4.0** | ❌ 不可商用（且 SA 传染） | 低（高校招生官网属长尾内容，训练污染小） | 中 | — | 排除理由：NC-SA 许可证对商用评测是硬约束。能力组合（长尾领域 + 时效性 + 去噪 + 忠实性）其实很贴近企业 RAG | research_G2.md |
| G2 | FinanceBench | 辅助（诊断切片） | 查询数：全量 10,231 条 question-answer-evidence 三元组，**开源仅 150 条**；语料规模：SEC 10-K / 10-Q / 8-K / 财报电话会记录 | 英文 | 开源 150 条的许可证**未核实**（HF `PatronusAI/financebench`；SEC 原文件本身公有领域） | 需核实 | 低（只开源 150 条，难以被大规模训练吸收） | 中高（长文档 + 证据页） | — | 需改造（样本太少）；唯一带「原始文档页码级 evidence」的开源金融集，150 条只够做诊断切片 | research_G2.md |
| G2 | LawBench / LexEval | 已排除 | 查询数：LawBench 20 任务 × 500 例 = 10,000；LexEval 23 任务 / 14,150 题；语料规模：中文法律 | 中文 | LawBench **Apache-2.0**；LexEval **未核实** | LawBench 可商用；LexEval 未核实 | 中 | 中 | — | 排除理由：是法律**能力**评测，不是检索/RAG 评测，与 G2 不对口 | research_G2.md |
| G2 | MMDocRAG | 辅助 | 查询数：4,055 条专家标注 QA；语料规模：多页 PDF / 视觉富文档，跨文本-表格-图表-图像证据链 | 英文 | **Apache-2.0** | ✅ 可商用 | 低 | 高（多页 PDF / 多模态） | — | 需改造；若 G2 要覆盖「从 PDF/表格里检索并引用」，这是目前最合适的公开集 | research_G2.md |
| G2 | EnterpriseRAG-Bench〔低置信度〕 | 仅方法借鉴（须先验证） | 查询数：500 条多文档推理问题 / 10 类；语料规模：~50 万合成文档，覆盖 9 个企业平台（Slack, Gmail, Linear, Google Drive, HubSpot, Fireflies, GitHub, Jira, Confluence），虚构公司 "Redwood Inference" | 英文 | **MIT**（据单一来源） | 若属实则可商用 | **极低**（全合成、2026 年新发布） | 高（~50 万文档） | 需实地验证后再定 | 只在一次检索中看到，**采用前必须亲自拉 repo 验证存在性、规模、许可证**；若核实属实，是本轮最贴合「企业内部知识库检索」的集 | research_G2.md |
| G2 | EKRAG〔低置信度〕 | 仅方法借鉴（须先验证） | 查询数：1,347 条人工构造多跳问题 / 5 类；语料规模：企业文档（产品发布、技术博客、财报） | 英文 | **未核实** | **未核实** | 低 | 中 | 先确认数据是否公开 | 论文可查（KnowledgeNLP @ ACL 2025），**公开数据是否发布未核实** | research_G2.md |

## 表 2：可覆盖比例

| 门类 | 公开集可覆盖比例 | 估计依据（一句话） | 必须自建的是什么 |
|---|---|---|---|
| G1 | ≈ 35% | 按子维度加权（通用事实单轮 1.0 / 多跳 0.5 / 幻觉率 0.8 / 内部 KB 0.0 / 多轮 0.0 / 内部术语与中英混排 0.0）得 0.495，再按业务重要性打折取 ≈35%；属工程判断非实测，误差 ±10pp 起 | 约 65% 题量靠合成 + 人工标注补齐，其中**内部知识库问答**与**多轮事实一致性**要全新建；另需内部术语表 + 对抗题、中英混排题 |
| G3 | ≈ 45% | 同法加权得 0.505，考虑到「形态对口但金标要全部重标」实际投入接近自建，保守取 ≈45% | 约 55% 题量靠自建，缺口最集中在**中文会议纪要**（公开集：没有）和 **Action Item 结构化抽取**（负责人/截止时间/依赖/状态 schema，公开集没有）；另有「邮件线程 + 纪要 + 附件表格」混合输入 |
| G2 | 约 40–50% | 按 G2 能力维度逐项判断：基础检索排序 ~85%、多跳/跨文档 ~75%、带引用生成 + 引用可溯源率 ~60%、假文档率=0 ~25%、中文办公场景适配 ~30%、办公文档格式（PPT/Excel/邮件）~10%、权限隔离检索 0%、时效性/多版本 ~20%，按重要性粗略加权 | **权限隔离下的检索**（0%，必须 100% 自建）、**中文办公文档格式**（PPT/Excel/邮件线程，无公开集）、**真实内部知识库文体**；假文档率的判定逻辑可确定性自建（校验 doc_id 是否在快照 ID 集合内 + 引文 span 能否精确匹配），成本低 |

## 3. 本片许可证要点

1. **明确不可商用（NC 系）**：C-Eval、CMMLU（CC BY-NC-SA 4.0）、CRAG（CC BY-NC 4.0）、MeetingBank（CC BY-NC-SA 4.0）、ELITR Minuting（CC BY-NC-SA 4.0）、DomainRAG（CC BY-NC-SA 4.0）。只能内部参考，不能进对外发布的评测集。
2. **MS MARCO 许可证是一条连带传染链**：Microsoft 自定非商用研究许可，明确不授予商用 IP 权利；TREC-DL、TREC RAG（V2.1 语料）、C-MTEB 的 MMarcoRetrieval 全部继承该约束 → 连带不可商用。
3. **BEIR 整体不能标 Apache-2.0**：代码 Apache-2.0，数据逐子集不同，维护者明确声明只做格式化与再分发、不转让任何底层版权或使用许可。18 个子集中至少 4 个（MS MARCO / Signal-1M / TREC-NEWS / Robust04）无法直接商用或无法自由分发 → 只能挑子集用，不能整包用。
4. **需签协议 / 注册才能获取**：Signal-1M（Signal Media Data Sharing Agreement）、TREC-NEWS 与 Robust04（NIST/LDC user agreement，限制商业再分发）、BioASQ（须在官网注册账号下载，CC BY 2.5 本身允许商用）。GPQA 与 AMI 属「可商用但需署名」。
5. **GPL 风险**：L-Eval 为 GPL-3.0，传染性强，内部评测可用但不要与产品代码混仓，建议不引入。
6. **SA（相同方式共享）传染链**：Natural Questions（CC BY-SA 3.0）、HotpotQA（CC BY-SA 4.0）、CQADupStack 与 DBPedia（CC BY-SA 系）、FaithBench 的 CC BY-SA 表述、DomainRAG 的 NC-SA。做闭源商用评测集时，衍生数据必须同样授权开放。
7. **衍生数据版权风险**：TriviaQA（代码 Apache-2.0、Kaggle 镜像标 CC0，但原作者声明不拥有抓取内容版权）；SummEval（底层 CNN/DM 原文另有条款）；NarrativeQA（标注 Apache-2.0，原始书籍/剧本文本版权另论）；CRUD-RAG（数据取自中文新闻，可能有第三方版权）。
8. **许可证未核实、需法务前置核对**：QAGS、REASONS、LexEval、FinanceBench 开源 150 条、RAGAS 具体版本、SuperCLUE、C-MTEB 各子集卡片、EKRAG、CRUD-RAG 数据部分。

## 4. 本片污染要点

1. **已被污染但仍被广泛引用、不得用作准入依据**：TriviaQA（2017 年集，长期被当训练集，原报告判定污染已到「没有测量价值」）、TruthfulQA（几乎所有对齐数据集都拿它做过 RLHF/SFT 目标，早已过拟合、分数虚高）、Natural Questions（2019 年集，维基正文与该集本身几乎必在所有预训练语料中）。
2. **同样不得作准入依据**：MS MARCO —— IR 领域第一大污染源，几乎所有主流 dense retriever 都在其上训练；继承其语料的 TREC-DL、TREC RAG、C-MTEB 的 MMarcoRetrieval 一并受影响。
3. **榜单型过拟合**：MTEB leaderboard 本身就是 embedding 厂商的优化目标，过拟合公认严重（极高）；BEIR 是过去四年 embedding 模型事实上的调参目标，分数只能横向比模型，不能当「真实办公场景能力」的估计。
4. **中文侧高污染**：C-Eval / CMMLU 是中文社区默认刷榜集（极高）；AGIEval 的考试真题常年在网上（高）；CLUE 系已充分公开多年（高）。
5. **有抗污染机制**：RULER —— 完全合成，长度与 needle 内容可现场随机生成，**结构上无法被污染**，是所有静态长文本集都给不了的性质；NIAH 同为现场生成（污染无），但只测检索不测理解，已被 RULER 严格超集覆盖。
6. **相对干净的真实文本**：LongBench v2（2024-12，专家新写题、依赖长程推理而非记忆，中低）；MultiHop-RAG（语料仅 609 篇 2023-09~12 新闻，非主流训练语料，低）；FaithBench（2024，标注的是各家 LLM 的实际输出，难被预训练记住，低中）；EnterpriseRAG-Bench（全合成 + 2026 新发布，极低，但条目本身为低置信度）。
7. **有防护但压力上升**：GPQA 有官方 canary string（`gpqa:4b24:...`）且 HF gated，但因广泛用于前沿模型评测，泄漏压力持续上升（中）。SimpleQA 只「建议」隔离、无强制 canary，题面与答案已在网上广泛流传（中高）；SimpleQA Verified 做了去重与 holdout 强化，略干净（中）。
8. **两点方法论提醒**：(a) 两份报告的污染等级均为定性判断（基于发布年份 + 是否开放下载 + 是否有 canary/gated + 社区使用热度），**未做 n-gram overlap 或 membership inference 实测**，要拿数说话需另做污染实测；(b) RAGTruth 另有 2025 年重标注研究指出原标注偏松、真实幻觉率显著更高（GPT 系约 50%，老开源模型 80–90%），不要照搬其绝对数值设我方阈值。

## 5. 冲突与待裁决

- MMLU-Pro 题量说法不一：论文口径 12,032 vs HF 线上表约 12,102；原报告未做取舍，注明以 HF 实际下载为准。
- GPQA 许可证表述不一致：数据集卡 CC BY 4.0 vs 代码仓 `idavidrein/gpqa` 的 MIT 表述；商用前按 CC BY 4.0 从严处理。
- FaithBench 数据许可证表述不一致：CC BY-NC-SA 4.0 与 CC BY-SA 4.0 并存，须以仓库 LICENSE 为准（影响「可否商用」结论）。
- LongCite / LongBench-Cite 许可证表述不一致：仓库 Apache-2.0 与 MIT 两种说法，须以仓库 LICENSE 为准。
- TriviaQA 三方表述冲突：代码 Apache-2.0 / Kaggle 镜像 CC0 / 原作者声明不拥有抓取内容版权 → 判定为「许可证不干净」，商用需法务确认。
- BEIR 许可证内部冲突：HF `BeIR/beir` 顶层卡片标 CC-BY-SA-4.0，与维护者「不转让任何版权或使用许可」的声明相冲突；把 BEIR 整体标成 Apache-2.0 是错误的。
- CRAG 与 FRAMES 在两份报告中分属不同门类（G1 与 G2），本表按门类各列一行：是同一数据集的不同用途，不是同名不同物。
- 原报告已声明未逐个打开 HF dataset card / clone 仓库核对 LICENSE 原文；凡表述不一致的四个集（GPQA、LongCite、FaithBench、TriviaQA）上生产前必须人工开仓核对。
- 「未核实」字段清单（G1/G3）：SimpleQA Verified 的 repo 名、AGIEval 总题数、SuperCLUE 许可证与题量、HELMET / QAGS / FaithBench / LongCite 的条数、L-Eval 总条数、NQ 的 dev/test 规模、FActScore 标注样本量、QAGS 许可证。
- 「未核实」字段清单（G2）：MS MARCO dev-small 精确 query 数（6,980 仅凭常识）、C-MTEB 8 个检索子集的 corpus 规模与逐集许可证、MLDR 逐语言 query 数、BEIR 中 TREC-COVID/NFCorpus/FiQA/ArguAna/Touché/Quora/DBPedia/SCIDOCS/FEVER/Climate-FEVER/NQ 的精确原始许可证条款、DomainRAG 样本条数与判分细则、CRUD-RAG 数据许可证、LexEval 许可证、FinanceBench 开源 150 条许可证、REASONS 的 repo 与许可证、LFRQA 精确 GitHub repo 路径、EnterpriseRAG-Bench 的存在性/规模/许可证、EKRAG 数据是否公开、RAGAS 具体许可证版本。
- 低置信度条目（仅单一来源、未获交叉印证）：EnterpriseRAG-Bench、EKRAG —— 采用前必须二次核实；EnterpriseRAG-Bench 因潜在契合度最高，被原报告列为核实优先级第一。
- 两份报告检索时间均为 2026-09，结果主要覆盖到 2025 年公开信息，**2026 年新发布的 benchmark 可能未被命中**，上线前建议再做一轮增量扫描。
