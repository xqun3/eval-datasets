# G2 信息检索 —— 公开 benchmark 选型调研

> 调研范围：为「通用办公场景 LLM 评测 benchmark」的 **G2 信息检索** 门类选型公开数据集。
> G2 任务形态：问题 + 受控文档库快照 → 检索相关文档 + 给出带引用的答案。
> 金标：相关文档 ID 列表 + 必须引用的段落。
> 主指标 Recall@5 / nDCG@10；辅助指标：引用可溯源率、死链率、假文档率（要求 = 0）。

**核实方法与诚实声明**

- 本文所有数据集均通过 `google_search` 实际检索核实，未核实到的字段一律写「**未核实**」并说明查了什么、没查到什么。
- 许可证一栏区分「**代码许可证**」与「**数据许可证**」——这两者在 BEIR / MTEB / MS MARCO 上完全不同，是本轮调研最容易出错的地方。
- 标注「**低置信度**」的条目表示只在单一来源看到、未获得交叉印证，采用前必须自行二次核实。

---

## 1. 主表

### 1.1 基础信息表

| # | 数据集名 | 发布方 | 年份 | 查询数 | 语料规模 | 语言 | 任务形态 | 获取方式 |
|---|---|---|---|---|---|---|---|---|
| A1 | **BEIR**（18 数据集聚合） | UKP / TU Darmstadt | 2021 (NeurIPS D&B) | 各子集不同：TREC-COVID 50 / NFCorpus 323 / SciFact 300 / FiQA-2018 648 / SCIDOCS 1,000 / Touché-2020 49 / HotpotQA 7,405 / NQ 3,452 / DBPedia 400 / Climate-FEVER 1,535 / Quora 10,000 | 3.6k ~ 1500 万文档（跨子集）；单子集示例：NFCorpus 3,633 / SciFact 5,183 / SCIDOCS 25,657 / FiQA 57,638 / TREC-COVID 171,332 / Touché 382,545 / Quora 522,931 / NQ 2,681,468 / DBPedia 4,635,922 / HotpotQA 5,233,329 / Climate-FEVER 5,416,593 | 英文为主 | 零样本文档检索（9 类 IR 任务） | GitHub `beir-cellar/beir`；HF org `BeIR/*` |
| A2 | **MTEB**（检索子集 = BEIR 大部分） | HF / cohere 等社区 | 2022 (arXiv 2210.07316) | 58 数据集 / 8 类任务 / 112 语言（检索子集主要复用 BEIR） | 同 BEIR | 多语 | Embedding 统一评测，含 Retrieval 任务族 | GitHub `embeddings-benchmark/mteb`；HF leaderboard |
| A3 | **C-MTEB / CMTEB Retrieval** | BAAI（FlagEmbedding） | 2023 | 8 个中文检索集，测试样本：T2Retrieval 24,832 / MMarcoRetrieval 7,437 / DuRetrieval 4,000 / CmedqaRetrieval 3,999 / EcomRetrieval 1,000 / MedicalRetrieval 1,000 / VideoRetrieval 1,000 / CovidRetrieval 949 | **未核实**（HF `C-MTEB/*Retrieval` 各自带 corpus split，逐集规模未逐一查证） | 中文 | 中文密集检索评测 | HF org `C-MTEB/*`；GitHub `FlagOpen/FlagEmbedding` |
| A4 | **MS MARCO**（Passage / Document） | Microsoft | 2016– | Passage 训练集约百万级；官方 dev small 6,980（**未核实**，仅凭常识，未在本轮检索中确认） | Passage V1 ~880 万段落；Document V1 ~320 万文档；**V2：1.38 亿段落 / 1,190 万文档** | 英文 | 段落/文档排序 | microsoft.github.io/msmarco；HF `ms_marco` |
| A5 | **TREC Deep Learning Track** 2019–2023 | NIST | 2019–2023 | 逐年评测 query 数很小：2019 passage 43 / doc 43；2020 passage 54 / doc 45；2021 passage 53 / doc 57；2022 passage 76；2023 passage 82 | 2019–2020 用 MS MARCO V1；2021–2023 用 V2（1.38 亿段落） | 英文 | 深度标注排序（NIST graded qrels） | trec.nist.gov；`ir_datasets` |
| A6 | **TREC RAG Track** 2024–2025 | NIST | 2024– | 301 条 query（采样自 Bing 日志） | MS MARCO **V2.1** segment/document collection | 英文 | 三任务：R / AG / RAG，生成答案 ≤400 词且**要求句级 segment 归属** | trec-rag.github.io |
| A7 | **MLDR** (Multilingual Long-Doc Retrieval) | BAAI（BGE-M3 配套） | 2024 | **未核实**（未查到逐语言 query 数） | 基于 Wikipedia / Wudao / mC4 构建，13 语言 | 13 语（含中文） | 长文档检索 | HF `Shitao/MLDR`；已集成进 `mteb` |
| A8 | **T2Ranking** | THUIR（清华）+ 腾讯 | 2023 (SIGIR) | ~30.8 万 query（搜狗日志采样） | ~230 万唯一段落 | 中文 | 段落排序，**4 级相关性分级（0–3）** | GitHub `THUIR/T2Ranking`；HF `THUIR/T2Ranking` |
| A9 | **DuReader-retrieval** | 百度 | 2022 (arXiv 2203.10232) | >9 万 query | >800 万唯一段落 | 中文（含人工翻译的跨语 query 集） | 中文段落检索，含 2 个 out-of-domain 测试集 | GitHub `baidu/DuReader` (DuReader-Retrieval) |
| B1 | **RAGBench** | Galileo Technologies | 2024 | 10 万 examples | 由 12 个子集转成统一 RAG 格式：PubMedQA, CovidQA, HotpotQA, FinQA, TAT-QA, CUAD, MS MARCO, EManual, TechQA, ExpertQA, HAGRID, DelucionQA | 英文 | RAG 端到端，配 **TRACe** 评测框架（Relevance / Adherence / Completeness 等） | HF `rungalileo/ragbench`（亦见 `galileo-ai/ragbench`） |
| B2 | **CRAG** (Comprehensive RAG) | Meta AI (FAIR) + HKUST；KDD Cup 2024 | 2024 | 4,409 QA 对，5 域 8 类问题 | Mock API 模拟 web search + KG；每题最多返回 **50 个完整 HTML 页面**（Brave Search 抓取） | 英文 | RAG 端到端，含动态/时效类问题 | GitHub `facebookresearch/CRAG` |
| B3 | **FRAMES** | Google + Harvard | 2024 | 824 条多跳问题 | 每题需综合 **2–15 篇 Wikipedia 文章** | 英文 | 事实性 + 检索 + 推理联合评测 | HF `google/frames-benchmark` |
| B4 | **MultiHop-RAG** | Yixuan Tang 等 | 2024 (arXiv 2401.15391) | 2,556 条多跳 query（inference / comparison / temporal / null 四类） | **609 篇英文新闻**，平均 2,046 token/篇（2023-09-26 ~ 2023-12-26） | 英文 | 多跳 RAG，带 evidence 段落标注 | HF `yixuantt/MultiHopRAG` |
| B5 | **HotpotQA** | CMU / Stanford / MILA | 2018 (EMNLP) | ~11.3 万 QA 对 | distractor 设置：每题 10 段（2 gold + 8 distractor）；fullwiki 设置：全维基 | 英文 | 多跳 QA + **supporting facts 句级标注** | HF `hotpot_qa`；GitHub `hotpotqa/hotpot` |
| B6 | **2WikiMultihopQA** | NII (Alab-NII) | 2020 (COLING) | 192,606 问题 | Wikidata 三元组 + Wikipedia 正文 | 英文 | 多跳 QA，带 **evidence 三元组 + grounded 句子** | GitHub `Alab-NII/2wikimultihop` |
| B7 | **ClapNQ** | IBM Research (PrimeQA) | 2024 (arXiv 2404.02103) | 4,946 条 grounded 长答案 QA（含 NQ 来的不可答问题） | NQ Wikipedia passages（HF `PrimeQA/clapnq_passages`） | 英文 | 长答案 RAG，答案来自**非连续段落片段** | HF `PrimeQA/clapnq` |
| B8 | **RAGAS**（不是数据集，是评测框架） | Exploding Gradients | 2023 (arXiv 2309.15217) | — | — | — | 无参考 LLM-as-judge：faithfulness / answer relevancy / context precision | GitHub `explodinggradients/ragas` |
| C1 | **ALCE** | Princeton NLP | 2023 (EMNLP, arXiv 2305.14627) | 三子任务各采样 1,000 条 dev（ALCE-ASQA 实际 948 条 × GTR/DPR/Oracle 三种检索 split） | ASQA/QAMPARI 用 Wikipedia；ELI5 用 **Sphere 语料（8.99 亿 Common Crawl 段落）** | 英文 | **带引用的生成**，自动评 citation precision / recall（NLI 判断引用是否真支持断言） | GitHub `princeton-nlp/ALCE` |
| C2 | **AttributionBench** | OSU NLP | 2024 (arXiv 2402.15089) | HF 标注规模区间 10K–100K | 聚合多个 attribution 评测源 | 英文 | **判别式**：判断「这条引用是否支持该断言」 | HF `osunlp/AttributionBench` |
| C3 | **ExpertQA** | UPenn 等 | 2023/2024 (NAACL, arXiv 2309.07852) | 2,177 问题 / 32 个领域 / 484 位专家参与 | 专家校验过的 attributed answers + 引用 | 英文 | 专家问题 + 归属答案，人工核验引用 | GitHub `chaitanyamalaviya/ExpertQA` |
| C4 | **HAGRID** | MIRACL 团队 | 2023 (arXiv 2307.16883) | train 1,922 query / 3,214 答案；dev 716 query / 1,318 答案 | 建在 **MIRACL 英文子集**之上 | 英文 | 人机协作生成 + 归属标注 | HF `miracl/hagrid` |
| C5 | **QuoteSum / SEMQA** | Google Research | 2024 (NAACL, arXiv 2311.04886) | 1,376 唯一问题（984 来自 PAQ，392 来自 NQ/AmbigQA）/ 4,009 条半抽取式答案 | 多源段落 | 英文 | **半抽取式 QA**：答案里直接内嵌带出处的引文片段 | GitHub `google-research-datasets/QuoteSum` |
| C6 | **LFRQA / RAG-QA Arena** | Amazon | 2024 (arXiv 2407.13998) | 2.6 万 query / 7 个领域 | 基于 RobustQA 的多领域语料 | 英文 | 长答案 RAG，人写 grounded 答案作黄金 | GitHub（Apache-2.0，具体 repo 路径**未核实**） |
| C7 | **RAGTruth** | NewsBreak (ParticleMedia) + UIUC | 2024 (ACL) | ~18,000 条 LLM 生成回复 / 2,965 个 source instance | open-domain QA + data-to-text + news summarization 三类 | 英文 | **词/span 级幻觉标注**，含幻觉强度 | GitHub `ParticleMedia/RAGTruth` |
| C8 | **REASONS** | Tilwani 等 | 2024 (arXiv 2405.02228) | 句级引用标注，覆盖 12 个学科 | ~2 万篇 arXiv 论文 | 英文 | 科学句子的**来源归属 / 自动引用**（直接 query + 间接 query 两种） | arXiv 2405.02228；repo **未核实** |
| D1 | **CRUD-RAG** | IAAR-Shanghai | 2024 (arXiv 2401.17043) | Create 10,728 / Read 单文档 QA 3,199 + 双文档 QA 1,506 / Update 幻觉修正 2,960 / Delete 多文档摘要 1,343 | 中文新闻语料 | 中文 | 四类 RAG 操作综合评测 | GitHub `IAAR-Shanghai/CRUD_RAG` |
| D2 | **DomainRAG** | 人大 GSAI + 百川 | 2024 (arXiv 2406.05654) | **未核实**（论文报告六种能力划分，未查到逐项条数） | 中国高校招生官网抓取 | 中文 | 领域 RAG：对话式 RAG / 结构化 QA / 忠实性 / 去噪 / 时效性 / 多文档 | GitHub `ShootingWong/DomainRAG` |
| D3 | **FinanceBench** | Patronus AI | 2023 | 全量 10,231 条 question-answer-evidence 三元组；**开源仅 150 条** | SEC 10-K / 10-Q / 8-K / 财报电话会记录 | 英文 | 开卷金融 QA，带 evidence 页面 | HF `PatronusAI/financebench` |
| D4 | **LawBench** | OpenCompass | 2023 | 20 任务 × 500 例 = 10,000 | 中文法律 | 中文 | 法律能力评测（非纯 RAG） | GitHub `open-compass/LawBench` |
| D5 | **LexEval** | CSHaitao | 2024 | 23 任务 / 14,150 题 | 中文法律 | 中文 | 法律认知能力分层评测（非纯 RAG） | GitHub `CSHaitao/LexEval` |
| D6 | **MMDocRAG** | — | 2025 | 4,055 条专家标注 QA | 多页 PDF / 视觉富文档，跨文本-表格-图表-图像证据链 | 英文 | 多模态文档 RAG + VQA，带 quote context | HF / GitHub（Apache-2.0） |
| D7 | **EnterpriseRAG-Bench**〔低置信度〕 | Onyx (`onyx-dot-app`) | 2026-05 | 500 条多文档推理问题 / 10 类 | ~50 万合成文档，覆盖 9 个企业平台（Slack, Gmail, Linear, Google Drive, HubSpot, Fireflies, GitHub, Jira, Confluence），虚构公司 "Redwood Inference" | 英文 | 企业内部知识库 RAG | GitHub `onyx-dot-app`（MIT） |
| D8 | **EKRAG**〔低置信度〕 | NVIDIA (KnowledgeNLP @ ACL 2025) | 2025 | 1,347 条人工构造多跳问题 / 5 类 | 企业文档（产品发布、技术博客、财报） | 英文 | 企业知识 QA，含 EM-as-judge / RM-as-judge / LLM-as-judge | 论文见 ACL Anthology；公开数据**未核实** |

---

### 1.2 评估适配表

| # | 数据集 | 金标形式 | 默认判分方式 | 许可证 | 可商用？ | 污染风险 | 契合度 | 直采 / 需改造 | 一句话评价 |
|---|---|---|---|---|---|---|---|---|---|
| A1 | BEIR | qrels（doc ID + 相关性等级） | nDCG@10（官方主指标）、Recall@100、MAP | **代码 Apache-2.0；数据逐子集不同**，见下方专表。HF `BeIR/beir` 顶层卡片标 CC-BY-SA-4.0，但 BEIR 维护者明确声明「只做格式化与再分发，不转让任何版权/使用许可」 | **部分可 / 部分不可**，必须逐子集判定 | **高** — BEIR 是过去 4 年 embedding 模型（E5/BGE/GTE/Nomic/Voyage…）事实上的标准评测与调参目标，很多模型的训练数据直接或间接混入了 BEIR 子集或其上游（尤其 MS MARCO、NQ、HotpotQA、FEVER、Quora） | 中（指标对得上，场景对不上） | **需重改造** | 排序质量的行业通用标尺，但污染严重、无引用标注、语料动辄百万级，只适合做 retriever 子模块 sanity check |
| A2 | MTEB | 同 BEIR | nDCG@10 等；leaderboard 聚合 | **代码 Apache-2.0；各底层数据集许可证各异**，MTEB 靠 HF dataset card 元数据让用户按许可证过滤 | 需逐任务判定 | **极高** — leaderboard 本身就是 embedding 厂商的优化目标，过拟合公认严重 | 低 | 不建议直采 | 作为「选哪个 embedding 模型」的参考可以，作为我方 G2 评测集不行 |
| A3 | C-MTEB Retrieval | qrels | nDCG@10 | **未核实**（各 `C-MTEB/*` 卡片许可证未逐一确认；上游 T2Ranking Apache-2.0、DuReader Apache-2.0、mMARCO 继承 MS MARCO 非商用条款） | **混合**；MMarcoRetrieval 继承 MS MARCO 非商用限制 → **不可商用** | **高** — 中文 embedding 模型（BGE-zh、GTE-zh、Conan、Qwen-Embedding）普遍在此上报分，且部分训练集重叠 | 中 | 需改造 | 中文检索唯一成熟公共标尺；EcomRetrieval / MedicalRetrieval 规模小（各 1,000）适合做受控快照原型 |
| A4 | MS MARCO | 稀疏 qrels（多数 query 仅 1 条正例） | MRR@10（passage）；TREC-DL 上用 nDCG@10 | **Microsoft 自定非商用研究许可**：免费但仅限非商用研究，明确不授予商用 IP 权利。配套代码仓 MIT | **不可商用** | **最高** — 几乎所有主流 dense retriever 都在 MS MARCO 上训练；这是 IR 领域第一大污染源 | 低 | 不建议直采 | 除非只做「retriever 相对能力」对比，否则别用；商用产品评测尤其要避开许可证问题 |
| A5 | TREC-DL | NIST 人工深度标注，graded 0–3 | nDCG@10（官方）、MAP、Recall@100 | 语料继承 MS MARCO 非商用条款；qrels 由 NIST 发布 | **不可商用**（受 MS MARCO 约束） | **高**（语料同 MS MARCO） | 中 | 需改造 | 标注质量是全场最好的（深度 pooling），但 query 数极少（43–82 条），统计功效不足以单独支撑一个门类 |
| A6 | TREC RAG 2024/25 | 检索 qrels + **nugget 级答案支持度**；要求句级 segment 归属 | **AutoNuggetizer**（GPT-4o 抽 nugget → 判 supported / partially / not supported），与人工评估 Kendall's τ 相关性高 | 语料受 MS MARCO V2.1 条款约束 | **不可商用** | 高（MS MARCO 语料） | **高（方法论层面）** | 借鉴方法，不直采数据 | **最值得抄的是它的评测协议**：句级归属 + nugget 支持度，几乎就是我方「引用可溯源率」的成熟实现 |
| A7 | MLDR | qrels | nDCG@10 | **MIT**（HF `Shitao/MLDR`） | **可商用** | 中 — 与 BGE-M3 同源发布，BGE 系模型有过拟合嫌疑；对非 BAAI 模型污染较低 | 中高（长文档 = 办公场景常见） | 需改造 | 少数许可证干净 + 覆盖中文 + 长文档的检索集，适合做「长文档检索」子能力 |
| A8 | T2Ranking | **4 级分级相关性**（0–3） | nDCG@10 / MRR | **Apache-2.0** | **可商用** | 中 — 中文模型常用作训练集，需检查所选模型训练配方 | 高 | 需下采样 | **中文检索首选之一**：分级相关性天然适配 nDCG@10，许可证干净 |
| A9 | DuReader-retrieval | qrels，带 out-of-domain 测试集 | MRR@10 / Recall@1,50 | **Apache-2.0** | **可商用** | 中高 — 中文 retriever 常见训练集 | 高 | 需下采样 | 真实百度搜索日志，query 分布贴近真人提问；语料 800 万需大幅下采样 |
| B1 | RAGBench | 段落级 relevance + adherence（答案是否忠于上下文）+ completeness 标注 | **TRACe** 框架，含 token 级 support 标注 | **CC-BY-4.0** | **可商用** | 中高 — 其子集 HotpotQA / MS MARCO / ExpertQA / HAGRID 均为高曝光公开集 | **高** | **接近直采**（需重映射到我方 schema） | 规模最大、标注维度最贴近我方「引用是否真支持断言」的 RAG 集；CC-BY-4.0 是巨大优势 |
| B2 | CRAG | 参考答案 + 检索到的网页；区分 correct / incorrect / missing 三态并对错误答案**扣分** | 打分公式对 hallucination 给负分（这点很关键） | **CC BY-NC 4.0** | **不可商用** | 中 — KDD Cup 后被大量复现，2024 之后训练的模型可能见过 | 中高 | 需改造 | 「宁可说不知道也不能编」这一评分哲学与我方「假文档率 = 0」高度一致，值得借鉴；但非商用限制要评估 |
| B3 | FRAMES | 参考答案 + 所需 Wikipedia 文章列表 | Accuracy（多跳事实正确率），分 oracle / retrieval 两档 | **Apache-2.0** | **可商用** | 中高 — 2024 年 Google 发布后被广泛采用为 agentic search 评测 | 中高 | 需改造（无段落级引用金标） | 许可证干净、题目难、规模小（824）正好适合做受控快照；但只给文章级而非段落级金标 |
| B4 | MultiHop-RAG | 多跳 query + **evidence 段落列表** | Retrieval：MAP@K / MRR@K / Hit@K；Generation：答案准确率 | **ODC-BY 1.0** | **可商用**（署名即可） | **低** — 语料是 2023-09~12 的新闻，语料池只有 609 篇且非主流训练语料 | **高** | **接近直采** | **语料只有 609 篇 —— 天然就是一个「受控文档库快照」**，几乎为 G2 量身定做；含 null 类问题可直接测「不编造」 |
| B5 | HotpotQA | 答案 + **supporting facts 句级标注** | EM / F1（答案）+ supporting-fact EM / F1 | **CC BY-SA 4.0** | **可商用（但 SA 传染性）** —— 衍生数据集必须同样 CC BY-SA 授权，做闭源商用评测集时要注意 | **高** — 既在 BEIR 里，又是无数 RAG 论文的默认集，训练污染广泛 | 中 | 需改造 | 句级 supporting facts 是难得的段落引用金标，但污染太重，建议只取 distractor 设置做能力诊断 |
| B6 | 2WikiMultihopQA | 答案 + **evidence 三元组 + grounded 句子** | EM / F1 + evidence F1 | **Apache-2.0** | **可商用** | 中高 — 多跳 RAG 论文标配 | 中高 | 需下采样（192k 太多） | 结构化 evidence 三元组便于自动判「引用是否真支持断言」，许可证优于 HotpotQA |
| B7 | ClapNQ | 长答案 + **gold passages（答案来自非连续片段）** | 长答案质量（ROUGE / LLM-judge）+ 不可答判定 | **Apache-2.0** | **可商用** | 中 — NQ 上游污染存在，但 ClapNQ 的长答案标注是新的 | **高** | **接近直采** | 「答案由段落里不连续的几段拼成」正是真实办公 RAG 的形态；含不可答样本，可直接测拒答 |
| B8 | RAGAS | 无金标（reference-free） | LLM-as-judge：faithfulness / answer relevancy / context precision / context recall | 代码 Apache-2.0（具体版本**未核实**） | 代码可商用 | 不适用 | 高（作为**评分器**） | 作为工具引入 | 不是数据集。faithfulness 指标可直接当我方「引用可溯源率」的自动近似，但 LLM-judge 有偏，需人工抽检校准 |
| C1 | **ALCE** | 断言级引用列表 | **citation precision / citation recall**，用 NLI 模型判断被引段落是否真的蕴含该断言 + 答案正确率 | **MIT**（代码）；底层 ASQA Apache-2.0、ELI5 用 Sphere（Common Crawl，开放条款） | **可商用**（但 ELI5 原始 Reddit 内容的衍生使用需谨慎） | 中高 — 2023 起被引用极多，主流模型可能见过 ASQA/ELI5 | **最高** | **接近直采** | **引用可溯源率的事实标准实现**：它的 citation precision 就是「引用是否指向真实存在且确实支持该断言的段落」，与我方辅助指标一一对应 |
| C2 | AttributionBench | 二分类/多分类标签：引用是否支持断言 | 分类 Accuracy / F1 | **Apache-2.0** | **可商用** | 中 | 高（作为判别器训练/校准集） | 需改造 | 用来**校准我方的引用判定器**，而不是当主评测集 —— 这是它最大的价值 |
| C3 | ExpertQA | 专家校验的 attributed answers + 引用 | 人工/自动 attribution 评分 + 事实性 | **MIT** | **可商用** | 中 | 高 | 需改造 | 专家领域问题 + 人工核过的引用，质量极高但规模小（2,177） |
| C4 | HAGRID | query + 带归属标注的答案（informative / attributable 两维人工标注） | attribution 人工标签 | **Apache-2.0** | **可商用** | 低中 | 高 | 需改造 | 建在 MIRACL 上，语料受控；双维标注（有信息量 ≠ 有依据）很适合拆解我方指标 |
| C5 | QuoteSum | **半抽取式答案**：答案句中直接内嵌带来源标记的引文 span | 半抽取式匹配 + 归属正确率 | **Apache-2.0** | **可商用** | 低 | 高 | 需改造 | 「答案里哪一句来自哪个源」标得最细，天然零假引用（引文必须是原文 span），可直接支撑「假文档率 = 0」的判定逻辑 |
| C6 | LFRQA | 人写的长答案，grounded 在多文档 | RAG-QA Arena：model-vs-human 的 LLM pairwise 对比 | **Apache-2.0** | **可商用** | 低中 | 中高 | 需改造 | 2.6 万条人写 grounded 长答案，跨 7 领域；评测范式是 pairwise 而非绝对分，接入我方指标需改 |
| C7 | RAGTruth | **词/span 级幻觉标注** + 幻觉强度 | span 级幻觉检测 P/R/F1 | **MIT** | **可商用** | 中 | 高（作为「假引用/假文档」检测集） | 需改造 | 目前最接近「假文档率」的公开标注。注意：2025 年有重标注研究指出原标注偏松、真实幻觉率更高（GPT 系 ~50%，老开源模型 80–90%），用它设阈值时别照搬原论文数字 |
| C8 | REASONS | 句子 → 来源论文（title/abstract/author）归属 | 归属准确率 / 幻觉引用率 | **未核实**（arXiv 2405.02228，repo 与许可证未查到） | 未核实 | 低中 | 中 | 需改造 | 学术引用场景专用，与办公场景偏差大；但「给一句话找出处、并检测编造出处」的任务形态可借鉴 |
| D1 | CRUD-RAG | 各子任务不同（QA 答案 / 摘要 / 幻觉修正） | ROUGE / BLEU / bert-score / RAGQuestEval | 代码仓 **Apache-2.0**；**数据本身许可证未核实**（语料来自中文新闻，可能有第三方版权） | **需谨慎**（新闻语料版权风险） | 中 | 中高（唯一体量像样的中文 RAG 综合集） | 需改造 | 中文 RAG 首选参考，但四类任务里只有 Read（QA）直接对应 G2；缺段落级引用金标 |
| D2 | DomainRAG | 六种能力的分项标注 | **未核实** | **CC BY-NC-SA 4.0** | **不可商用**（且 SA 传染） | 低 — 高校招生官网属长尾内容，训练污染小 | 中高 | 需改造 | 「长尾领域 + 时效性 + 去噪 + 忠实性」的组合很贴近企业 RAG；但 NC-SA 许可证对商用评测是硬约束 |
| D3 | FinanceBench | 答案 + evidence（原始文件页码） | 人工/LLM 判正误，统计 hallucination / refusal 率 | 开源 150 条的许可证**未核实**（HF `PatronusAI/financebench`；SEC 原文件本身公有领域） | 需核实 | 低 — 只开源 150 条，难以被大规模训练吸收 | 中高（长文档 + 证据页 = 办公场景） | 需改造（样本太少） | 唯一带「原始文档页码级 evidence」的开源金融集；150 条只够做诊断切片 |
| D4/D5 | LawBench / LexEval | 任务标签/答案 | 各任务自带 | LawBench **Apache-2.0**；LexEval **未核实** | LawBench 可商用 | 中 | **低** | 不建议采用 | 这两个是法律**能力**评测，不是检索/RAG 评测，与 G2 不对口。中文法律 **RAG** 专用公开集：**没找到像样的**（见 §3） |
| D6 | MMDocRAG | 跨模态证据链 + quote context | 检索 + 生成联合评分 | **Apache-2.0** | **可商用** | 低 | 中高（PDF/表格/图表 = 办公文档） | 需改造 | 若 G2 要覆盖「从 PDF/表格里检索并引用」，这是目前最合适的公开集 |
| D7 | EnterpriseRAG-Bench〔低置信度〕 | 500 条多文档推理问题的参考答案 | **未核实** | **MIT**（据单一来源） | 若属实则可商用 | **极低**（全合成、2026 年新发布） | **潜在最高**（9 个企业平台 = Slack/Gmail/Drive/Jira/Confluence，正是办公场景） | 需实地验证后再定 | **若核实属实，是本轮最贴合「企业内部知识库检索」的集**。但我只在一次检索中看到它，**采用前必须亲自拉 repo 验证存在性、规模、许可证** |
| D8 | EKRAG〔低置信度〕 | 1,347 条多跳问题 | EM-as-judge / RM-as-judge / LLM-as-judge | **未核实** | 未核实 | 低 | 中高 | 先确认数据是否公开 | NVIDIA 的企业 QA 评测；论文可查，**数据是否公开发布未核实** |

---

### 1.3 BEIR 逐子集许可证专表（这一条是任务硬性要求，单独展开）

BEIR 的**代码**是 Apache-2.0，但**数据不是**。BEIR 维护者在 repo 中明确声明：他们只做格式转换与再分发，**不授予也不转让任何底层数据集的版权或使用许可**，使用者必须自行遵守每个子集的原始许可。把 BEIR 整体标成「Apache-2.0」是错误的。

| BEIR 子集 | 任务类型 | 数据许可 / 获取条件 | 可商用？ |
|---|---|---|---|
| MS MARCO | 段落检索 | Microsoft 自定**非商用研究**许可 | ❌ 否 |
| TREC-COVID | 生医 IR | CORD-19 衍生，一般视为开放研究用途（精确条款**未核实**） | ⚠️ 需核实 |
| **BioASQ** | 生医 IR | 官方称 **CC BY 2.5**，但**必须在 BioASQ 官网注册账号**才能下载原始 train/test 数据；BEIR 不直接分发 | ⚠️ 需自行获取；CC BY 2.5 本身允许商用 |
| NFCorpus | 生医 IR | 学术开放（精确许可**未核实**） | ⚠️ 需核实 |
| NQ | QA 检索 | 上游 Natural Questions 为 CC BY-SA 3.0（**未在本轮核实**） | ⚠️ 需核实（SA 传染） |
| HotpotQA | 多跳 QA | **CC BY-SA 4.0** | ⚠️ 可商用但 SA 传染 |
| FiQA-2018 | 金融 QA | 开放评测数据（精确许可**未核实**） | ⚠️ 需核实 |
| **Signal-1M (RT)** | 推文检索 | **Signal Media Data Sharing Agreement** 约束，BEIR 不自由分发 | ❌ 需签协议 |
| **TREC-NEWS** | 新闻检索 | **NIST / LDC 分发，需签署 user agreement**，限制商业再分发 | ❌ 需签协议 |
| **Robust04** | 新闻检索 | **NIST / LDC 分发（TREC disks 4&5），需签署 user agreement** | ❌ 需签协议 |
| ArguAna | 论辩检索 | 学术开放（精确许可**未核实**） | ⚠️ 需核实 |
| Touché-2020 | 论辩检索 | 学术开放（精确许可**未核实**） | ⚠️ 需核实 |
| CQADupStack | 重复问题 | 源自 StackExchange（CC BY-SA 系）；**可直接从 HF / BEIR / ir_datasets 下载，无需签协议** | ⚠️ SA 传染 |
| Quora | 重复问题 | Quora 数据集使用条款（**未核实**） | ⚠️ 需核实 |
| DBPedia-Entity | 实体检索 | DBpedia 为 CC BY-SA（**未核实**） | ⚠️ SA 传染 |
| SCIDOCS | 引文预测 | AllenAI 发布（精确许可**未核实**） | ⚠️ 需核实 |
| FEVER | 事实核查 | 上游 FEVER 为 CC BY-SA 3.0（**未核实**） | ⚠️ 需核实 |
| Climate-FEVER | 事实核查 | 同上游 FEVER 系（**未核实**） | ⚠️ 需核实 |

**结论：BEIR 18 个子集中，至少 4 个（MS MARCO / Signal-1M / TREC-NEWS / Robust04）无法直接商用或无法自由分发；BioASQ 需注册获取。若 G2 要做成可对外发布的评测集，BEIR 只能挑选子集用，不能整包用。**

---

## 2. 分层小结

### (a) 纯检索排序类

**首选：**

1. **T2Ranking**（中文，Apache-2.0，4 级分级相关性）
   - 理由：许可证干净可商用；**分级相关性（0–3）是 nDCG@10 的原生输入**，不需要把二值 qrels 硬凑成 graded；中文真实搜索日志，query 分布贴近真人。
   - 建议采样量：**200–300 条 query**（足以让 nDCG@10 的标准误降到可用范围），语料下采样到 3–5 万段落。
   - 需要的改造：无引用标注 → 只能测 retriever，不能测端到端引用。需要另配生成层金标。

2. **MLDR**（多语含中文，MIT，长文档）
   - 理由：许可证最干净的检索集之一；长文档检索是办公场景的主要形态（一份 30 页方案文档 vs 一句话段落）。
   - 建议采样量：中文 split **100–200 条 query**。
   - 改造：query 由 GPT-3.5 生成，不是真人提问，风格偏书面 —— 需人工改写一部分成办公口吻，或标注清楚这是合成 query。

3. **BEIR 的小语料子集**（SciFact 5,183 / NFCorpus 3,633 / SCIDOCS 25,657 / FiQA 57,638）——仅作 **sanity check**
   - 理由：这几个子集语料小到可以整包当「受控快照」，且是行业通用横轴，方便和外部模型对齐。
   - 但必须在报告里**明写污染警告**：BEIR 是近四年 embedding 模型的事实调参目标，分数只能横向比模型，不能当作「真实办公场景能力」的估计。

**明确不推荐：** MS MARCO / TREC-DL 作为主集（非商用许可 + 最严重污染）；MTEB leaderboard（过拟合最严重的地方）。

---

### (b) RAG 端到端类

**首选：**

1. **MultiHop-RAG**（ODC-BY，609 篇新闻语料）
   - 理由：**这是全场最接近「受控文档库快照」定义的集** —— 语料池天生只有 609 篇文档，不需要做任何下采样就能整包塞进 `context`；带 evidence 段落列表，可直接算 Recall@5；含 null 类问题，可直接测「检索不到时是否拒答」这一假文档率的关键维度；语料是 2023 年末新闻，训练污染低。
   - 建议采样量：**全量 2,556 条里分层采样 300–500 条**（按 inference / comparison / temporal / null 四类等比）。
   - 改造：英文 → 中文办公场景需翻译或重构；「新闻」文体与「内部文档」文体有差距。

2. **RAGBench**（CC-BY-4.0，10 万例，TRACe 标注）
   - 理由：唯一同时具备「规模大 + 商用许可清晰 + 段落级 relevance 与 adherence 标注」的 RAG 集；它的 adherence 标注（答案的每个 token 是否被上下文支持）**基本等价于我方的「引用可溯源率」**，可省掉大量自建标注成本。
   - 建议采样量：**500–800 例**，按 12 个子集来源分层，优先取 TechQA / EManual / CUAD / FinQA 这几个「像企业文档」的子域，避开 HotpotQA / MS MARCO 这两个高污染子域。
   - 改造：需把 TRACe 的标注体系映射到我方「相关文档 ID + 必须引用段落」的 schema。

3. **ClapNQ**（Apache-2.0，4,946 条）
   - 理由：答案由段落中**非连续片段**拼成 —— 这正是真实办公问答的形态（答案散落在文档的三个地方）；自带不可答问题，天然支撑「假文档率 = 0」的负样本。
   - 建议采样量：**200–300 条**（其中不可答样本占 20–30%）。
   - 改造：语料仍是 Wikipedia，需评估是否接受；NQ 上游有污染。

**值得借鉴但不建议直采：**
- **CRAG**：CC BY-NC 4.0 不可商用。但它的评分公式**对错误答案给负分**（correct +1 / missing 0 / incorrect −1），这个设计与我方「假文档率 = 0」的硬约束哲学完全一致，**建议直接把这套打分逻辑搬进我方 G2 的评分器**。
- **TREC RAG 2024/25 的 AutoNuggetizer**：句级 segment 归属 + nugget 支持度三档判定（supported / partially / not supported），且已验证与人工评估有高 Kendall's τ 相关性。**这是我方「引用可溯源率」最现成的工程实现参考**，比自己从零设计判分规则靠谱。
- **RAGAS**：作为自动评分器接入（faithfulness ≈ 引用可溯源率），但必须用人工抽检（建议 10%）校准 LLM-judge 的偏差，否则分数不可信。
- **FRAMES**：许可证干净、题目难，但只给文章级而非段落级金标，达不到我方「必须引用的段落」这一金标要求，需补标。

---

### (c) 引用可溯源 / 假引用检测类

**首选：**

1. **ALCE**（MIT，ASQA / QAMPARI / ELI5 各 1,000）
   - 理由：**这是「引用可溯源率」的事实标准实现**。它用 NLI 模型判断「被引段落是否真的蕴含该断言」，分别给出 citation precision（引用是否都站得住）和 citation recall（该给引用的地方是否都给了）。我方的辅助指标定义与之几乎逐字对应，可以直接复用其评测脚本。
   - 建议采样量：ASQA + QAMPARI **各 200 条**（这两个语料是 Wikipedia，可控）；**ELI5 建议放弃** —— 它依赖 Sphere 语料（8.99 亿 Common Crawl 段落），做受控快照完全不现实。
   - 改造：需把评测脚本的 NLI 判定器换成中文可用的模型；语料换成我方办公文档后需重新构造 gold citation。

2. **QuoteSum**（Apache-2.0，1,376 问题 / 4,009 半抽取式答案）
   - 理由：答案里内嵌的是**原文 span**，引用天然不可能是假的 —— 这给「假文档率 = 0」提供了一个**可机器验证的金标形式**（引文必须能在语料里精确字符串匹配上）。建议把这个「引文必须是可定位的原文 span」的约束直接写进我方 G2 的 schema。
   - 建议采样量：**150–250 条**。
   - 改造：半抽取式答案格式较特殊，需要 prompt 层适配；纯英文。

3. **RAGTruth**（MIT，~18,000 条 span 级幻觉标注）
   - 理由：目前最接近「假文档率 / 假引用检测」的公开标注资源，词级 span 粒度。
   - 用法建议：**不当主评测集，当我方幻觉检测器的训练/校准集**。
   - ⚠️ 重要提醒：2025 年有重标注研究指出原标注标准偏松，按更严标准重评时幻觉率显著更高（GPT 系约 50%，老开源模型 80–90%）。**不要照搬原论文的绝对数值来设我方阈值。**

**辅助：** AttributionBench（Apache-2.0）用于校准「引用是否支持断言」的判别器；HAGRID（Apache-2.0）的「informative / attributable」双维标注，可用来拆解「答案有用」与「答案有据」这两个常被混为一谈的维度；ExpertQA（MIT）提供专家核验过的高质量小样本。

**明确的空缺：** 「**假文档**」（模型引用了一个语料里根本不存在的文档/段落）这一失败模式，**没有找到专门的公开数据集**。RAGTruth 标的是「生成内容与上下文不符」，REASONS 标的是「学术引用来源错误」，都不完全是「凭空捏造一个不存在的文档 ID」。**这一项我方必须自建**——好消息是它最容易自建：假文档率本质是一个确定性检查（引用的 doc ID 是否在快照的 ID 集合内 + 引文 span 是否能在该文档里精确匹配），不需要标注，只需要在评分器里加一段校验代码。

---

## 2.5 受控文档库快照的可行性与下采样建议（Schema 专项）

我方 G2 的 `context` 需要携带一份完整的受控文档库快照，这直接决定了哪些集能用。

**按语料规模的可行性分档：**

| 档位 | 语料规模 | 数据集 | 结论 |
|---|---|---|---|
| ✅ 可整包做快照 | < 1 万文档 | MultiHop-RAG (609)、NFCorpus (3,633)、SciFact (5,183)、ArguAna (8,674) | 直接整包塞进 context |
| ⚠️ 需中度下采样 | 1 万–20 万 | SCIDOCS (25,657)、FiQA (57,638)、TREC-COVID (171,332) | 下采样到 1–3 万 |
| ❌ 全量不现实 | > 50 万 | Touché (382,545)、Quora (522,931)、NQ (268 万)、DBPedia (464 万)、HotpotQA (523 万)、Climate-FEVER (542 万)、MS MARCO (880 万 / V2 1.38 亿)、DuReader-retrieval (800 万)、ALCE-ELI5 的 Sphere (8.99 亿) | 必须重构语料池 |

**下采样时如何不破坏 hard negatives —— 建议流程：**

1. **不要随机采样。** 随机采样会把绝大多数 hard negatives 采掉，留下一堆与 query 毫不相关的文档，检索任务会退化成「送分题」，Recall@5 虚高到失去区分度。这是语料下采样最常见也最致命的错误。

2. **采用「gold + pooled negatives + 随机背景」三层构造：**
   - **第一层（gold）**：所有 query 的全部标注相关文档，100% 保留。
   - **第二层（hard negatives）**：对每个 query，用 **2–3 个异构检索器**（一个稀疏如 BM25，一个 dense，最好再加一个不同架构的 dense）各取 Top-100，取并集后**剔除 gold**，保留剩余部分。用异构检索器而非单一检索器是关键 —— 单检索器的 negatives 会让评测偏向与该检索器同源的模型。
   - **第三层（背景噪声）**：从原语料随机采一批无关文档，把语料撑到目标规模（建议 1–5 万），模拟真实文档库中大量不相关内容的稀释效应。
   - 建议配比：gold : hard-neg : 背景 ≈ 1 : 100 : 300 左右，按目标语料规模反推。

3. **对已有深度标注的集（TREC-DL、T2Ranking）走「pooling 原则」**：只保留进入过官方 pool 的文档 + 随机背景。这样可以保证「未标注文档 = 真不相关」这一假设成立，避免把实际相关但未标注的文档当负例，导致 nDCG 被系统性低估。

4. **快照必须冻结并带内容哈希。** 每个文档存 `doc_id + content_sha256`，评分器用它做两件事：(a) 校验引用的 doc_id 存在于快照 → 直接得出**假文档率**；(b) 校验引文 span 能在该文档正文里精确匹配 → 得出**引用可溯源率**的下界。**死链率**在离线快照场景下应恒为 0，若非 0 说明快照构建有 bug —— 建议把它当作数据质量的自检项而非模型指标。

5. **下采样后必须做一次退化检查**：用一个弱基线（如 BM25）在采样后的语料上跑一遍，如果 Recall@5 高到 0.95 以上，说明 hard negatives 被破坏了，需要提高 hard-neg 比例重来。

---

## 3. 「覆盖不到什么」的诚实说明

以下几块是公开集**结构性覆盖不到**的，不是靠多找几个数据集能补上的：

| 缺口 | 为什么公开集覆盖不到 | 现状 |
|---|---|---|
| **企业内部知识库** | 真实内部文档（内部 wiki、周报、会议纪要、项目文档、产品 PRD）涉密，不会公开。公开集的语料只有 Wikipedia / 新闻 / 学术论文 / 公开财报 / StackExchange 五类。文体、术语密度、内部缩写、跨文档指代方式都与内部文档差异巨大 | 唯一潜在候选是 **EnterpriseRAG-Bench**（合成企业数据，2026-05，MIT，〔低置信度，需自行验证〕）和 **EKRAG**（NVIDIA，1,347 题，数据是否公开**未核实**）。即便可用，也是**合成**数据，与真实内部文档的分布差异仍未知 |
| **权限隔离下的检索** | 「用户 A 能看到文档 X，用户 B 不能，检索结果必须按身份过滤，且不能通过答案泄露无权限内容」—— **没有找到任何公开数据集覆盖这一场景**。公开集全部假设单一全局可见的语料 | **完全没有。必须 100% 自建。** 这是企业 RAG 最关键、公开集覆盖为零的能力维度 |
| **中文办公文档格式**（PPT / Excel / 邮件线程 / 飞书文档 / Word 批注） | 公开集的文档单元几乎都是「纯文本段落」。PPT 的版面语义、Excel 的表格结构与跨 sheet 引用、邮件线程的回复层级与引文嵌套，这些结构信息在公开集里全部丢失 | 英文侧有 **MMDocRAG**（4,055 题，Apache-2.0，多页 PDF/表格/图表）和其他多模态文档 RAG 集可部分覆盖 PDF/表格。**专门覆盖中文 PPT / Excel / 邮件线程的公开集：没有找到。** 检索中明确显示现有企业 RAG 评测都走 OCR/多模态 PDF 管线，没有原生 .pptx/.xlsx/邮件线程的中文集 |
| **时效性内容**（"上周的会议纪要说了什么"、"最新版本的方案是哪份"） | 公开集是静态快照，没有「同一主题的多个版本，要求返回最新的那份」这种任务。CRAG 和 DomainRAG 有时效性问题类型，但都是「答案随时间变化」，不是「文档库里有多版本要选最新」 | **部分覆盖**：CRAG（CC BY-NC）、DomainRAG（CC BY-NC-SA）有 time-sensitive 子类。但「多版本文档去重与选新」这一具体形态**没有公开集** |
| **假文档 / 捏造引用的检出** | 见 §2(c) 空缺说明 | 无专门公开集，但**可用确定性规则自建**，成本低 |
| **中文法律 / 金融 RAG** | LawBench / LexEval 是法律**能力**评测（记忆/理解/推理），不是检索或 RAG 评测，喂不进 G2 的金标形式。FinanceBench 是英文且只开源 150 条 | **中文法律 RAG 专用公开集：没找到像样的。中文金融 RAG 专用公开集：没找到像样的。** 不硬凑 |

**公开集可覆盖比例估计：约 40–50%**

估计依据（按 G2 的能力维度拆解，逐项判断而非拍脑袋）：

| G2 能力维度 | 公开集覆盖度 | 依据 |
|---|---|---|
| 基础检索排序质量（Recall@5 / nDCG@10） | **~85%** | T2Ranking / DuReader / MLDR / BEIR 小子集充分覆盖，指标定义完全一致 |
| 多跳 / 跨文档检索 | **~75%** | MultiHop-RAG / FRAMES / 2WikiMultihopQA 覆盖良好 |
| 带引用的答案生成 + 引用可溯源率 | **~60%** | ALCE / QuoteSum / RAGBench 覆盖了评测方法论，但语料全是公开域文体 |
| 假文档率 = 0 | **~25%** | 无专门数据集，但判定逻辑可确定性自建；负样本（不可答问题）只有 ClapNQ / MultiHop-RAG null 类少量提供 |
| 中文办公场景适配 | **~30%** | 中文检索集有（T2Ranking / DuReader / C-MTEB），但都是搜索日志，不是办公问答；中文 RAG 只有 CRUD-RAG / DomainRAG，且都缺段落级引用金标 |
| 办公文档格式（PPT/Excel/邮件） | **~10%** | 仅 MMDocRAG 覆盖 PDF/表格，且为英文 |
| 权限隔离检索 | **0%** | 无任何公开集 |
| 时效性 / 多版本文档 | **~20%** | CRAG / DomainRAG 部分覆盖，且许可证受限 |

按维度重要性粗略加权后，**公开集能覆盖 G2 约 40–50% 的评测需求**。剩下的一半 —— 尤其是**权限隔离、中文办公文档格式、真实内部知识库文体** —— 必须自建，这三项加起来是 G2 最大的缺口。

---

## 4. 引用来源

**纯检索 / 排序**
- BEIR: NeurIPS 2021 Datasets & Benchmarks；GitHub `beir-cellar/beir`（代码 Apache-2.0 + 数据许可免责声明）；HF org `BeIR/*`
- MTEB: arXiv:2210.07316（Muennighoff et al.）；GitHub `embeddings-benchmark/mteb`
- C-MTEB: HF org `C-MTEB/*`；GitHub `FlagOpen/FlagEmbedding`
- MS MARCO: microsoft.github.io/msmarco（非商用研究许可条款）
- TREC Deep Learning Track 2019–2023: NIST TREC track overview papers (Craswell et al.)
- TREC RAG Track 2024/2025 + AutoNuggetizer: trec-rag.github.io；AutoNuggetizer 相关 arXiv 论文
- MLDR: HF `Shitao/MLDR`（MIT）；BGE-M3 论文
- T2Ranking: SIGIR 2023；GitHub `THUIR/T2Ranking`；HF `THUIR/T2Ranking`（Apache-2.0）
- DuReader-retrieval: arXiv:2203.10232；GitHub `baidu/DuReader`（Apache-2.0）

**RAG 端到端**
- RAGBench: HF `rungalileo/ragbench`（CC-BY-4.0）；TRACe 框架论文
- CRAG: GitHub `facebookresearch/CRAG`（CC BY-NC 4.0）；Meta KDD Cup 2024
- FRAMES: HF `google/frames-benchmark`（Apache-2.0）
- MultiHop-RAG: arXiv:2401.15391；HF `yixuantt/MultiHopRAG`（ODC-BY 1.0）
- HotpotQA: arXiv:1809.09600, EMNLP 2018（CC BY-SA 4.0）
- 2WikiMultihopQA: COLING 2020；GitHub `Alab-NII/2wikimultihop`（Apache-2.0）
- ClapNQ: arXiv:2404.02103；HF `PrimeQA/clapnq`, `PrimeQA/clapnq_passages`（Apache-2.0）
- RAGAS: arXiv:2309.15217；GitHub `explodinggradients/ragas`

**引用可溯源 / 假引用**
- ALCE: arXiv:2305.14627, EMNLP 2023；GitHub `princeton-nlp/ALCE`（MIT）
- AttributionBench: arXiv:2402.15089；HF `osunlp/AttributionBench`（Apache-2.0）
- ExpertQA: arXiv:2309.07852, NAACL 2024；GitHub `chaitanyamalaviya/ExpertQA`（MIT）
- HAGRID: arXiv:2307.16883；HF `miracl/hagrid`（Apache-2.0）
- QuoteSum / SEMQA: arXiv:2311.04886, NAACL 2024；GitHub `google-research-datasets/QuoteSum`（Apache-2.0）
- LFRQA / RAG-QA Arena: arXiv:2407.13998（Apache-2.0）
- RAGTruth: ACL 2024 (Niu et al.)；GitHub `ParticleMedia/RAGTruth`（MIT）；2025 年重标注研究
- REASONS: arXiv:2405.02228

**中文 / 企业场景**
- CRUD-RAG: arXiv:2401.17043；GitHub `IAAR-Shanghai/CRUD_RAG`（代码 Apache-2.0）
- DomainRAG: arXiv:2406.05654；GitHub `ShootingWong/DomainRAG`（CC BY-NC-SA 4.0）
- FinanceBench: Islam et al. 2023；HF `PatronusAI/financebench`
- LawBench: GitHub `open-compass/LawBench`（Apache-2.0）
- LexEval: GitHub `CSHaitao/LexEval`
- MMDocRAG: HF / GitHub（Apache-2.0）
- EnterpriseRAG-Bench: GitHub `onyx-dot-app`（MIT，2026-05）〔**单一来源，低置信度，采用前须自行验证**〕
- EKRAG: KnowledgeNLP @ ACL 2025 (Tan Yu et al., NVIDIA)〔**数据是否公开未核实**〕

---

## 附：未核实字段清单（便于后续补查）

1. MS MARCO 官方 dev-small 的精确 query 数（6,980 为常识记忆，本轮未确认）
2. C-MTEB 8 个检索子集各自的 corpus 规模与逐集许可证
3. MLDR 逐语言 query 数
4. BEIR 中 TREC-COVID / NFCorpus / FiQA / ArguAna / Touché / Quora / DBPedia / SCIDOCS / FEVER / Climate-FEVER / NQ 的精确原始许可证条款（只确认了「非 Apache-2.0、各自独立」）
5. DomainRAG 的样本条数与判分细则
6. CRUD-RAG **数据**（非代码）的许可证
7. LexEval 许可证
8. FinanceBench 开源 150 条的许可证
9. REASONS 的 repo 地址与许可证
10. LFRQA 的精确 GitHub repo 路径
11. EnterpriseRAG-Bench 的存在性、规模、许可证（**优先级最高，因为它潜在契合度最高**）
12. EKRAG 数据集是否公开发布
13. RAGAS 的具体许可证版本
