# G6（数据分析）/ G7（代码与 SQL）公开数据集选型调研

调研范围：为「通用办公场景 LLM 评测 benchmark」的两个可确定性判分门类选型公开集。

- **G6 数据分析**：数据表 + 分析问题 → 结论。金标 = 精确数值 + 推导步骤要点。主指标 EM ≥ 0.9，辅助推导步骤正确率、单位/口径错误率 ≤ 3%。
- **G7 代码与 SQL**：Schema / 仓库快照 + 需求 → SQL / 代码。金标 = 可执行测试用例 / 参考结果集。主指标 pass@1 ≥ 0.8（另报 pass@3），辅助 AST 合法率、结果集等价率、执行计划代价比。

**核实方式**：本文每个数据集的规模 / 许可证 / 环境要求均通过 `google_search` 实际检索核实，来源见第 6 节。**凡检索未能确认的字段一律写「未核实」并注明查了什么**，没有凭记忆补全。

**一句话结论（先说）**：G6 主用 **DABStep + InfiAgent-DABench(DAEval) + TableBench(数值推理/数据分析子集)**；G7-SQL 主用 **BIRD(Mini-Dev 起步) + BIRD-CRITIC**，Spider 2.0 只作上限压力测试；G7-Code 主用 **BigCodeBench + LiveCodeBench(时间切片) + SWE-bench Verified(小样本)**。**HumanEval / MBPP / Spider 1.0 全部降级为 dev 集，不得单独作为准入门槛依据。**

---

## 1. 主表

### 1.1 基础信息表

| # | 数据集 | 发布方 | 年份 | 规模(条) | 语言 | 任务形态 | 金标形式 | 默认判分方式 | 许可证 | 可商用 | 获取方式 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | **DABStep** | Adyen × Hugging Face | 2025 | 450+ 任务（easy / hard 两档） | 英文 | 多步数据分析（多个结构化数据文件 + 异构文档/口径说明） | 客观 factoid 答案（数值/字符串） | 二元精确匹配（binary factoid check），官方 leaderboard | CC-BY-4.0 | ✅ 可商用（需署名） | HF `adyen/DABstep` |
| 2 | **InfiAgent-DABench (DAEval)** | InfiAgent | 2024 | 257 问 / 52 个 CSV | 英文 | CSV 数据分析，开放式问题经 format-prompting 转闭式 | 闭式答案（数值等）+ Python 沙箱执行 | 自动化闭式匹配 + 沙箱执行 | Apache-2.0 | ✅ 可商用 | HF `infiagent/DABench` / GitHub InfiAgent |
| 3 | **TableBench** | Multilingual-Multimodal-NLP 组 | 2024（AAAI） | 886 条人工标注测试集（配套训练集 TableInstruct 19,661） | 英文 | 表格 QA，4 类：事实核查 / 数值推理 / 数据分析 / 可视化 | 参考答案（文本 + 数值）；可视化子集为代码 | 混合：数值子集执行解析 + 准确率；文本子集 ROUGE-L；可视化 pass@1 | Apache-2.0（HF） | ✅ 可商用 | HF `Multilingual-Multimodal-NLP/TableBench` |
| 4 | **DS-1000** | xlang-ai（HKU） | 2022/2023 | 1,000 题（源自 451 个唯一 StackOverflow 问题，扰动生成） | 英文 | 数据科学代码补全（NumPy/Pandas/SciPy/sklearn/PyTorch/TF/Matplotlib） | 测试用例 + surface-form 约束（19.4% 题目有 API 限制） | 执行判分；官方报 FDR 1.8% / FOR 0.5% | CC-BY-SA-4.0（检索亦见 CC BY 4.0 表述，两说并存，**以仓库 LICENSE 为准，待二次确认**） | ⚠️ 可商用但 SA 传染（衍生数据需同许可证） | HF `xlangai/DS-1000` |
| 5 | **DSBench** | LiqiangJing 等 | 2024 | 540 题 = 466 数据分析（源自 38 场 ModelOff 财务建模赛）+ 74 数据建模（Kaggle） | 英文 | Excel(.xlsx) / 多 GB CSV / 文本 / 图片 上的分析与建模 | 数值答案 / 提交结果 | 答案匹配（分析）+ 指标评分（建模） | **Non-commercial only**（商用需书面授权） | ❌ 不可商用 | GitHub `LiqiangJing/DSBench` |
| 6 | **TabFact** | UCSB 等 | 2019 | 16k 表 / 118k 陈述 | 英文 | 表格事实核查（entail / refute） | 二分类标签 | 准确率 | CC BY 4.0 | ✅ | HF `tab_fact` / GitHub TabFact |
| 7 | **WikiTableQuestions** | Stanford | 2015 | 22,033 问 | 英文 | 单表 QA | 短答案字符串 | EM | CC BY-SA 4.0 | ⚠️ SA 传染 | GitHub `ppasupat/WikiTableQuestions` |
| 8 | **FinQA** | 多机构（EMNLP 2021） | 2021 | 8,281 问 | 英文 | 金融报表数值推理（表 + 文本） | 数值答案 + **推导程序（program）** | 执行准确率 + program 准确率 | MIT | ✅ | GitHub `czyssrs/FinQA` |
| 9 | **TAT-QA** | NExT++ | 2021 | 16,552 问 | 英文 | 表 + 文本混合金融 QA | 数值/字符串答案 + **scale（单位口径）标注** | EM + F1，**含 scale 判定** | 数据集 CC BY 4.0；代码 MIT（另有资料提及 NC 表述，**以仓库 LICENSE 为准**） | ✅（按 CC BY 4.0） | GitHub `NExTplusplus/TAT-QA` |
| 10 | **ConvFinQA** | 同 FinQA 团队 | 2022 | 3,892 段对话 | 英文 | 多轮金融数值推理 | 数值答案 + 推导程序 | 执行准确率 + program 准确率 | MIT | ✅ | GitHub `czyssrs/ConvFinQA` |
| 11 | **HiTab** | Microsoft Research | 2022（ACL） | 10,686 QA/描述句 / 3,597 层次表 | 英文 | 层次表头表格 QA + NLG | 答案 + 聚合算子标注 | EM / 执行 | 未核实（查了 "HiTab license"，检索回执只确认来源为 StatCan/NSF/Wikipedia，未给出明确 LICENSE 文本） | 未核实 | GitHub `microsoft/HiTab` |
| 12 | **AIT-QA** | IBM Research | 2022（ACL） | 515 问 / 116 表（SEC 10-K 航空业） | 英文 | 复杂层次表头领域 QA | 短答案 | EM | CDLA-Sharing-1.0 | ✅（共享类许可证，衍生需同条款） | GitHub `IBM/AITQA` |
| 13 | **Tapilot-Crossing** | 学术（OpenReview/arXiv） | 2024 | 1,024 轮多轮交互，4 类场景 | 英文 | 多轮对话式表格数据分析（Kaggle 种子） | 代码 + 执行结果 | 执行判分 + 决策判分 | 未核实（查了 "Tapilot-Crossing license"，仅确认构造方式与规模，未取到许可证声明） | 未核实 | GitHub Tapilot-Crossing |
| 14 | **Spider 1.0** | Yale | 2018 | 10,181 问 / 5,693 SQL / 200 库 / 138 域 | 英文 | Text-to-SQL（跨域，小而干净 schema） | 参考 SQL | EM + 执行准确率（EX） | CC BY-SA 4.0 | ⚠️ SA 传染 | GitHub `taoyds/spider` |
| 15 | **Spider 2.0** | XLANG Lab, HKU | 2024/2025（ICLR 2025 Oral） | 632 个真实企业级工作流任务（子集：Spider2-lite 547、Spider2-snow 547、Spider2-dbt 68） | 英文 | 企业级 Text-to-SQL / 数据工程工作流（schema 常 1000+ 列） | 参考结果集 / 参考答案 | 执行匹配 | Spider 1.0 血统为 CC BY-SA 4.0；Spider 2.0 仓库许可证**未核实**（查了 "Spider 2.0 license Apache GitHub xlang-ai"，只确认了 Spider 1.0 的 CC BY-SA 4.0） | ⚠️ 未定 | GitHub `xlang-ai/Spider2` |
| 16 | **BIRD-SQL (BIRD 1.0)** | BIRD team（NeurIPS 2023 Spotlight） | 2023 | 12,751 question-SQL 对 / 95 个真实库 / **33.4 GB** / 37 领域；Mini-Dev V2 780 条（含 500 条 SELECT-only） | 英文（库内字段多为英文） | Text-to-SQL，含脏数据、外部知识、效率维度 | 参考 SQL + 结果集 | 执行准确率 EX + VES（有效效率分，即**执行代价比**） | CC BY-SA 4.0（官方已更新为此） | ⚠️ SA 传染 | GitHub `AlibabaResearch/DAMO-ConvAI/bird` / bird-bench.github.io |
| 17 | **BIRD-CRITIC (SWE-SQL)** | BIRD team | 2025 | 600 开发任务 + 200 held-out OOD 测试；子集 `bird-critic-1.0-open`（~570–600，跨方言）、`-postgresql`（~530–600）、`-flash-exp`（200 PG） | 英文 | 真实用户报障 SQL 调试（PostgreSQL / MySQL / SQL Server / Oracle 四方言） | 可执行测试 + 参考结果 | 执行判分（Docker 环境） | 未核实（查了 BIRD-CRITIC 环境与规模，检索回执未给出独立 LICENSE；推测随 BIRD 主仓） | ⚠️ 未定 | GitHub `bird-bench/BIRD-CRITIC`（含 docker-compose） |
| 18 | **KaggleDBQA** | Microsoft（ACL 2021） | 2021 | 272 评测问 / 8 个 SQLite 真实库（原始标注 400 问） | 英文 | Text-to-SQL，真实未归一化 Web 库 + 库文档 | 参考 SQL | EX | 未核实（查了 KaggleDBQA license，仅确认规模与来源） | 未核实 | GitHub `Chia-Hsuan-Lee/KaggleDBQA` |
| 19 | **WikiSQL** | Salesforce | 2017 | 80,654 条 / 24,241 张 Wikipedia 表 | 英文 | 单表简单 SQL 生成 | 参考 SQL | 逻辑形式 + 执行准确率 | BSD 3-Clause | ✅ | GitHub `salesforce/WikiSQL` |
| 20 | **CSpider** | Min et al. | 2019 | 与 Spider 1.0 同规模：10,181 问 / 5,693 SQL / 200 库（中文翻译版） | **中文问句 + 英文 schema** | Text-to-SQL | 参考 SQL | EM / EX | 随 Spider 1.0（CC BY-SA 4.0） | ⚠️ SA 传染 | GitHub `taolusi/chisp` / CSpider 官网 |
| 21 | **DuSQL** | Baidu（ACL 2020） | 2020 | 23,797 问/SQL 对 / 200 库 / 813 表 / 160+ 域 | **中文（含中文字段名）** | 实用化中文 Text-to-SQL（含计算类问题） | 参考 SQL | EM / EX | 未核实（查了 DuSQL license，仅确认规模来源为百度 ACL 2020） | 未核实 | 百度 LUGE / DuSQL 官方页 |
| 22 | **Chase** | 学术（ACL 2021） | 2021 | 规模**未核实**（查了 "Chase Chinese context-dependent text-to-SQL size"，仅确认它是中文上下文相关多轮 Text-to-SQL 集，未取到确切题量） | 中文 | 多轮上下文相关 Text-to-SQL | 参考 SQL | EM / EX | 未核实 | GitHub `xjtu-intsoft/chase` |
| 23 | **Archer** | 学术 | 2024 | 1,042 英文问 + 1,042 中文问 / 521 条唯一 SQL / 20 库 / 20 域 | **中英双语** | 复杂推理 Text-to-SQL（算术比率/百分比、常识推断、假设推理） | 参考 SQL | EX | 未核实（查了 Archer 许可证，仅确认规模与评测指标） | 未核实 | Archer 官方 GitHub Pages |
| 24 | **HumanEval** | OpenAI | 2021 | 164 题 | 英文/Python | 函数级代码生成 | 单元测试 | pass@k | MIT | ✅ | HF `openai_humaneval` |
| 25 | **HumanEval+ / MBPP+ (EvalPlus)** | EvalPlus | 2023 | HumanEval+ = 164 题、测试量 ×80；MBPP+ 测试量 ×35 | 英文/Python | 同上，强化测试 | 强化单元测试 | pass@k | HF 仓库 Apache-2.0 | ✅ | HF `evalplus/humanevalplus`、`evalplus/mbppplus` |
| 26 | **MBPP** | Google Research | 2021 | 974 题（500 训练 + 474 test/sanitized） | 英文/Python | 入门级函数生成 | 3 条断言 | pass@k | CC-BY-4.0 | ✅ | HF `mbpp` |
| 27 | **BigCodeBench** | BigCode Project | 2024 | 1,140 函数级任务；调用 723 个唯一函数、139 个库（77 标准库 + 62 第三方）、7 个领域 | 英文/Python | 复合库调用的实用代码生成 | 单元测试（含分支覆盖） | pass@1（Complete / Instruct 两种） | Apache-2.0 | ✅（但被调用的**第三方库许可证混合**，见注） | HF `bigcode/bigcodebench` |
| 28 | **LiveCodeBench** | UC Berkeley / MIT / Cornell 等 | 2024– | 滚动更新：v1 400 / v2 511 / v3 612 / v4 713 / v5 880 / v6 1,055 题（v6 覆盖 2023-05 ~ 2025-04） | 英文/Python | 竞赛题代码生成 + 自修复 + 执行预测 + 测试输出预测 | 竞赛测试用例 | pass@1，**按题目发布日期切片** | 数据集 CC BY 4.0；站点代码 CC BY-SA 4.0 | ✅（数据集按 CC BY 4.0） | HF `livecodebench/code_generation_lite` |
| 29 | **SWE-bench** | Princeton NLP | 2023 | 2,294 个 task instance / 12 个 Python 仓库 | 英文/Python | 真实 issue → 补丁 | FAIL_TO_PASS / PASS_TO_PASS 测试 | resolved rate（等价 pass@1） | 评测代码 MIT；数据元信息 CC BY 4.0；**被测仓库各自的上游开源许可证不同（混合）** | ⚠️ harness 可商用，**仓库代码需逐一看上游许可证** | GitHub `princeton-nlp/SWE-bench` |
| 30 | **SWE-bench Verified** | OpenAI × Princeton | 2024 | **500** 条人工校验子集 | 英文/Python | 同上 | 同上 | resolved rate | MIT | ⚠️ 同上（底层仓库混合） | HF `princeton-nlp/SWE-bench_Verified` |
| 31 | **SWE-bench Multimodal** | Princeton NLP | 2024 | 617 个 instance / 17 个可视化前端仓库 | 英文/JS-TS | 带 UI 截图的 issue 修复 | 测试 | resolved rate | 未核实（查了 SWE-bench Multimodal license，检索只确认规模与语言） | ⚠️ 未定 | GitHub SWE-bench（multimodal split） |
| 32 | **Multi-SWE-bench** | ByteDance Seed | 2025 | 1,632 个 instance（2,456 候选中由 68 名专家筛出）/ 7 语言：Java, TS, JS, Go, Rust, C, C++ | 英文/多语言 | 多语言真实 issue 修复 | 测试 | resolved rate | 未核实（查了 Multi-SWE-bench license，检索只确认规模与语言构成） | ⚠️ 未定 | GitHub `multi-swe-bench/multi-swe-bench` |
| 33 | **CodeContests** | Google DeepMind | 2022 | ~13,500 题（Codeforces/AtCoder/CodeChef/CodeNet/Description2Code） | 英文/多语言 | 竞赛编程 | 大量测试用例（含生成的对抗测试） | pass@k / n@k | 代码与执行脚本 Apache-2.0；题面等非代码内容 CC BY 4.0 | ✅ | HF `deepmind/code_contests` |
| 34 | **ClassEval** | 复旦 FudanSELab | 2023 | 100 个类级任务 / 100 类 / 410 方法 / 平均 33.1 条测试 | 英文/Python | 类级（多方法依赖）代码生成 | 单元测试 | pass@k（类级 + 方法级） | 代码 MIT；**数据集 CC BY-NC 4.0** | ❌ 数据集不可商用 | GitHub `FudanSELab/ClassEval` |
| 35 | **CRUXEval** | Meta (facebookresearch) | 2024 | 800 个短 Python 函数（CRUXEval-I 输入预测 / -O 输出预测） | 英文/Python | 代码**执行推理**（非生成） | 输入/输出对 | pass@1（等价判定） | MIT | ✅ | GitHub `facebookresearch/cruxeval` |
| 36 | **Aider Polyglot** | Aider | 2024 | 225 道 Exercism 练习 / 6 语言（C++, Go, Java, JS, Python, Rust） | 英文/多语言 | **代码编辑**（在编辑循环里改现有文件，含 diff 格式正确性） | Exercism 测试 | 通过率 + 编辑格式合规率 | harness Apache-2.0 / 开源；**练习内容版权归 Exercism，按其 track 许可证使用** | ⚠️ 需逐 track 确认 | GitHub `Aider-AI/polyglot-benchmark` |

> **关于「底层代码许可证混合」的要点（任务点名要说清）**：
> - **SWE-bench / SWE-bench Verified / Multi-SWE-bench / SWE-bench Multimodal**：harness 是 MIT，但每个 instance 都是从**真实 GitHub 仓库**切出来的代码快照（Django、sympy、scikit-learn、matplotlib…）。这些仓库各自有 BSD-3 / MIT / Apache-2.0 / LGPL 等**不同**许可证。若我方要**对外发布**含仓库快照的评测包或把补丁作为训练/展示材料，必须逐仓库过许可证；仅**内部执行评测**风险低。
> - **BigCodeBench**：任务定义与测试是 Apache-2.0，但任务会 `import` 139 个库（62 个第三方）。评测镜像里会打包这些库，其许可证同样混合（含 GPL 类的可能性需在打包前扫一遍）。
> - **Aider Polyglot**：练习题面与测试来自 Exercism，版权归 Exercism，不是我方可任意再分发的内容。
> - **CodeContests**：题面是 CC BY 4.0，但原始题目来自 Codeforces 等平台，二次分发受 CC BY 约束（署名即可），代码部分 Apache-2.0。

### 1.2 环境与适配表

| # | 数据集 | 门类 | 数据污染风险（高/中/低 + 理由） | **环境搭建成本（低/中/高 + 说明）** | 契合度 | 直采 / 需改造 | 一句话评价 |
|---|---|---|---|---|---|---|---|
| 1 | **DABStep** | G6 | **低–中**：2025 年发布，源自 Adyen 内部真实支付分析工作负载，非公开题库改写；但已上 HF leaderboard，随时间推移会被吸入训练语料 | **低**：纯 CSV/Markdown 文档 + Python 沙箱，无数据库、无云账号，本地几 GB 以内即可跑 | **高** | 需改造（答案对齐我方 EM 判定 + 补推导步骤标注） | G6 的**首选**：唯一同时满足「多步聚合 + 口径判断 + 客观 factoid 金标 + 轻环境」的集 |
| 2 | **InfiAgent-DABench** | G6 | **中**：2024 年发布，已被广泛引用；闭式格式使记忆化收益明显 | **低**：52 个 CSV + Python 沙箱，官方就是沙箱执行评测 | **高** | 直采为主，需把沙箱对接我方统一 checker | 轻量、闭式、天然 EM，最省接入成本的 G6 补充集 |
| 3 | **TableBench** | G6 | **中–高**：886 条已完全公开，且配套训练集 TableInstruct 公开，交叉污染面大 | **低**：纯表格 JSON，无外部依赖 | **中**（需只取「数值推理」+「数据分析」子集） | 需改造（**丢弃 ROUGE-L 判分，只留数值精确匹配**；丢弃可视化子集或单独归入 G7） | 好用但判分口径太杂：ROUGE-L 与我方 EM 主指标不兼容，必须裁剪后用 |
| 4 | **DS-1000** | G6/G7 交界 | **中–高**：源自 StackOverflow 公开问答，原题在预训练语料中大量存在（扰动只降低表面匹配，不消除语义记忆） | **低**：Python 执行 + 若干科学计算库，pip 即可 | **中** | 需改造 | 更像「Pandas API 代码题」而非「业务口径分析题」，可作 G6→G7 的过渡集，不宜作 G6 主力 |
| 5 | **DSBench** | G6 | **中**：源自 ModelOff 历年赛题与 Kaggle，题面公开；但答案与 Excel 工作簿相对稀缺 | **中–高**：需处理 `.xlsx` 工作簿与多 GB CSV，Excel 解析链路（openpyxl/LibreOffice）是额外依赖 | **中–高**（最贴近「办公场景」：Excel + 财务建模） | 需改造，且**许可证不可商用** | **办公场景契合度最高，但 non-commercial 是硬限制** —— 只能内部研究用，不能进对外发布的商用 benchmark |
| 6 | **TabFact** | G6 | **高**：2019 年经典集，彻底公开 | **低** | **低**：二分类，非数值分析 | 不建议采用 | 不符合「精确数值金标」，最多作 sanity check |
| 7 | **WikiTableQuestions** | G6 | **高**：2015 年集，污染彻底 | **低** | **低** | 不建议采用 | 单跳表格查询，**属于任务书点名的「太简单」那一类**，见第 2.0 节 |
| 8 | **FinQA** | G6 | **高**：2021 年集，广泛用于微调 | **低**：纯 JSON | **中–高**（有 program 金标，正好对应我方「推导步骤要点」） | 需改造（program DSL → 我方步骤格式） | **唯一自带「推导程序」金标的集**，对辅助指标「推导步骤正确率」价值最大 |
| 9 | **TAT-QA** | G6 | **高**：2021 年集，污染彻底 | **低** | **中–高**（**自带 scale 单位标注**，直击「单位/口径错误率 ≤3%」） | 需改造 | 做「单位/口径」这条辅助指标的最佳现成标注源 |
| 10 | **ConvFinQA** | G6 | **高**：同 FinQA 血统 | **低** | **中**（多轮） | 需改造 | 多轮场景补充，量小（3,892 段） |
| 11 | **HiTab** | G6 | **高**：2022 年集 | **低** | **中**（层次表头 ≈ 真实报表结构） | 需改造 | 层次表头是办公报表的常见形态，作为难度补充有价值 |
| 12 | **AIT-QA** | G6 | **中**：领域窄、引用少 | **低** | **中**（515 条，量太小） | 需改造 | 小而干净，可作 held-out 抽检 |
| 13 | **Tapilot-Crossing** | G6 | **中**：合成生成（Decision Company 多智能体） | **中**：需 Kaggle 数据 + Python 执行 | **中** | 需改造 | 多轮交互式分析的少数选择，但合成味重、许可证未核实 |
| 14 | **Spider 1.0** | G7-SQL | **高（已饱和）**：o1-preview 类 agent 达 **91.2% EX**、GPT-4o 达 **86.6%**，schema 小而干净，题库与标注 SQL 全网可见 | **低**：200 个小 SQLite，几百 MB | **低–中** | **仅作 dev/回归集** | 已饱和 + 已污染，**不能作为准入依据**（详见第 4 节） |
| 15 | **Spider 2.0** | G7-SQL | **低**：2024/2025 新集，且 GPT-4o 仅 **10.1% EX**、o1-preview agent **21.3%**、Spider2.0-lite 上标准 parser 仅 **5.7%** —— 远未饱和 | **高（关键阻碍）**：完整评测需注册 **BigQuery（GCP service account JSON key）、Snowflake、ServiceNow、dbt Cloud** 账号并填 `settings.json`。仅 lite 中的 SQLite/DuckDB 部分可纯本地跑，**全量评测无法脱离云账号** | **中–高**（企业级 schema 1000+ 列，最像真实业务） | 需大改造 | **最能区分强模型，但云账号依赖是现实障碍**：建议只取本地可跑的 SQLite/DuckDB 子集做「上限压力测试」，不纳入主指标 |
| 16 | **BIRD-SQL** | G7-SQL | **中**：2023 年集，已上主流 leaderboard 被广泛微调；但库大、脏数据多、需外部知识，纯记忆收益低于 Spider | **中**：全量 95 库 **33.4 GB** SQLite 下载 + 本地存储；**Mini-Dev V2 仅 780 条（含 500 条 SELECT-only）可轻量本地跑**。无云账号需求 | **高** | 需改造（EX/VES → 我方 checker） | G7-SQL 的**首选**：自带 **VES（有效效率分）**，正好对接我方「执行计划代价比」辅助指标；Mini-Dev 让冷启动只要几百 MB |
| 17 | **BIRD-CRITIC** | G7-SQL | **低**：2025 年新题，600 dev + **200 held-out OOD 测试**（held-out 是明确抗污染设计） | **中**：官方给 `docker-compose.yml` + 四方言 dump（`postgre/mysql/mssql/oracle_table_dumps`）；PG-only 的 `flash-exp`（200 条）最轻。**Oracle/MSSQL 镜像体量与授权是额外负担** | **高** | 需改造 | 真实报障 SQL 调试，题型最贴近「办公场景里改坏掉的 SQL」；**建议只上 PostgreSQL 分支** |
| 18 | **KaggleDBQA** | G7-SQL | **中**：量小、引用中等 | **低**：8 个 SQLite | **中**（仅 272 条） | 需改造 | 真实未归一化 schema + 库文档，做「schema 理解」小抽检不错 |
| 19 | **WikiSQL** | G7-SQL | **高**：2017 年集，早已饱和 | **低** | **低** | 不建议采用 | 单表单条件，过于简单 |
| 20 | **CSpider** | G7-SQL | **高**：Spider 1.0 的中文翻译，继承其全部污染 | **低** | **中**（中文问句，但 **schema 仍是英文**） | 需改造 | 中文覆盖的**廉价方案**，但解决不了「中文字段名」这个真问题 |
| 21 | **DuSQL** | G7-SQL | **中–高**：2020 年百度公开集 | **中**：需从 LUGE 获取，格式非标准 Spider | **高（中文侧最相关）**：**含中文字段名与中文业务表**，还覆盖计算类问题 | 需改造 | **中文 Text-to-SQL 的最佳公开起点**，但需自建 DB 与执行环境 |
| 22 | **Chase** | G7-SQL | 未核实（规模未取到，污染程度无法定量） | **中** | **中**（中文多轮） | 需改造 | 中文上下文相关场景的少数选择，信息待补 |
| 23 | **Archer** | G7-SQL | **低–中**：2024 年新集，引用少 | **中**：20 库，未核实是否自带 DB 文件 | **高**（中英双语 + **算术比率/百分比推理**，直接命中「口径判断」） | 需改造 | 中英双语 + 复杂算术推理，**G6/G7 交界处最有价值的中文相关集** |
| 24 | **HumanEval** | G7-Code | **极高**：每条 prompt 在 GitHub 上中位数 **99 次命中**；The Pile 中 12.2%、The Stack 中 18.9% 样本重合；RedPajama-1T / StarCoder-Data 与其重合 **8–18%** | **低** | **低** | **仅 dev** | **已彻底污染，禁止单独作准入依据** |
| 25 | **HumanEval+ / MBPP+** | G7-Code | **高**：测试加强了，但**题面不变**，记忆化路径完全保留 | **低** | **中**（测试质量显著更好） | 仅 dev / 回归 | 测试变严不等于抗污染；只解决「假阳性」不解决「见过题」 |
| 26 | **MBPP** | G7-Code | **极高**：同上，且题目更简单 | **低** | **低** | **仅 dev** | 同 HumanEval |
| 27 | **BigCodeBench** | G7-Code | **中**：2024 年集，任务是新写的复合库调用；但已公开一年以上，需配合时间监测 | **中**：需装 139 个库（62 个第三方），**必须用固定版本的 Docker 镜像**，否则库版本漂移直接导致假失败 | **高**（多库组合调用 ≈ 办公自动化脚本的真实形态） | 需改造 | G7-Code **首选**：最贴近「写个脚本处理文件/调接口」的办公需求 |
| 28 | **LiveCodeBench** | G7-Code | **低（最佳抗污染设计）**：每题带**精确发布日期**，可只取模型训练截止日之后的题。已实证：DeepSeek-Instruct-33B 在其 2023-09 发布日之后的 LeetCode 题上性能显著下滑，GPT-4o 在 2023-11 截止后的题上同样下滑 | **低**：只需 Python 执行 + 测试用例，无外部服务 | **中–高**（竞赛题 ≠ 办公任务，但作为**保鲜探针**不可替代） | 直采 + 时间切片策略 | **持续保鲜的核心工具**；题型偏竞赛，权重不宜过高 |
| 29 | **SWE-bench** | G7-Code | **高（隐性污染严重）**：Verified 全部 500 条中 **97.8%** 的评测用测试文件在 `base_commit` 时点前已公开；**92.8%** 的修复 commit 可用 issue 号直接在公开 GitHub 历史搜到；**60.83%** 已解决 issue 存在「解法泄漏」（issue 正文/评论里写了做法）。过滤泄漏题与弱测试后（SWE-bench+），平均解决率从 51.7% 跌到 **25.9%** | **极高**：`--cache_level=env` 至少需 **120 GB** 可用磁盘；全量 instance 镜像缓存需 **240–684 GB**（优化层注册表如 Epoch Research / LogicStar 可压到 30–67 GB）。镜像托管在 Docker Hub `swebench/sweb.eval` 与 `ghcr.io/epoch-research/swe-bench.eval`，**长期可得性依赖第三方托管，需自建私有 registry 镜像备份** | **中**（仓库级修复 ≫ 办公场景需求强度） | 需大改造 | 信号强但成本极高、污染隐性；**只取小样本（如 100 条）作能力上限探针** |
| 30 | **SWE-bench Verified** | G7-Code | 同上（上述 97.8% / 92.8% / 60.83% 数据即针对 Verified 500 条） | **极高**：同上 | **中** | 需大改造 | 人工校验过的 500 条，质量最好但**泄漏问题并未因人工校验而消除** |
| 31 | **SWE-bench Multimodal** | G7-Code | **中**：617 条 JS/TS，较新 | **极高**：前端仓库 + 浏览器/截图链路，比 Python 版更重 | **低**（多模态前端修复超出本 benchmark 范围） | 不建议采用 | 超纲 |
| 32 | **Multi-SWE-bench** | G7-Code | **中**：2025 年新集，1,632 条 7 语言 | **极高**：7 种语言 × 各自工具链的 Docker 镜像 | **低–中** | 不建议采用（本期） | 多语言覆盖好，但环境成本对我方不划算 |
| 33 | **CodeContests** | G7-Code | **高**：2022 年集，题面来自公开竞赛平台，全网可见 | **中**：测试用例体量大（含生成的对抗测试），执行耗时长 | **低–中** | 不建议作主力 | 竞赛题，与办公场景相关性低；且已被 LiveCodeBench 在保鲜维度上取代 |
| 34 | **ClassEval** | G7-Code | **中**：100 条，人工新写 | **低**：Python + 测试 | **中**（类级多方法依赖，接近真实模块开发） | 需改造，**CC BY-NC 数据集不可商用** | 质量高但量小 + NC 限制 |
| 35 | **CRUXEval** | G7-Code | **中**：2024 年集 | **低**：纯 Python 执行 | **中**（测的是**读代码/预测执行**，是「AST 合法率」之外另一条诊断维度） | 直采 | 便宜的诊断集：模型是否真懂自己写的代码 |
| 36 | **Aider Polyglot** | G7-Code | **中**：Exercism 练习题公开可见，但**编辑循环 + diff 格式**这层不易被记忆绕过 | **中**：6 种语言工具链 | **中–高**（**代码编辑**比从零生成更贴近真实工作） | 需改造 | 唯一直接测「编辑既有文件 + diff 格式合规」的集，对 agent 形态评测有独特价值 |

---

## 2. 分门类小结

### 2.0 先划清一条线：「表格问答」≠「数据分析」（任务点名要求点明）

这两件事在公开集里被混为一谈，但对 G6 是致命区别：

| | 表格问答（TableQA） | 真正的数据分析 |
|---|---|---|
| 典型集 | WikiTableQuestions、TabFact、WikiSQL、TableBench 事实核查子集 | DABStep hard、DSBench、InfiAgent-DABench、FinQA、Archer |
| 输入规模 | 单张小表，通常 < 50 行，全部塞进 prompt | 多个文件 / 多 GB，必须写代码聚合 |
| 推理深度 | 单跳查找 / 最多一次比较 | 多步聚合 + join + 过滤 + 口径选择 |
| 口径歧义 | 无（答案唯一且字面存在于表中） | **核心难点**：「活跃用户」按哪天算？金额含不含税？月份按自然月还是账期？ |
| 我方指标适配 | EM 容易刷到很高 → **区分度接近 0** | EM 有区分度，且能测出「单位/口径错误率」 |

**结论**：WikiTableQuestions / TabFact / WikiSQL 这一类**不纳入 G6 主集**。它们的 EM 早已接近饱和，塞进来只会稀释区分度、把 EM 均值人为抬高到 0.9 以上，让「EM ≥ 0.9」这个门槛失去意义。TableBench 也必须**只取数值推理 + 数据分析两个子集**。

判断一条题该不该进 G6 的操作性准则（建议写进标注规范）：
1. 答案能否仅靠在表里「找到」得到？能 → 剔除。
2. 是否需要 ≥ 2 步聚合（group by / join / 窗口 / 比率）？否 → 降权。
3. 题面是否存在口径歧义、且金标隐含一个特定口径？是 → **优先保留**，这是最有价值的题。

### 2.1 G6 数据分析

**首选推荐（3 个）**

1. **DABStep（450+，CC-BY-4.0，可商用）** — 首推。理由：① 源自 Adyen 真实支付分析工作负载，天然带「口径判断」（需要读异构文档才知道某字段怎么算）；② 金标是客观 factoid，**原生适配 EM 主指标**，无需 LLM judge；③ 环境成本低（CSV + Python，无 DB 无云账号）；④ 2025 年发布，污染低；⑤ hard 档顶尖系统仅 14.55–16%，天花板极高，区分度不会近期失效。
2. **InfiAgent-DABench / DAEval（257 问 / 52 CSV，Apache-2.0，可商用）** — 补充。理由：闭式格式 + 官方 Python 沙箱评测，接入成本最低，可作为 pipeline 联调的第一个集；缺点是量小、2024 年集有中度污染，**建议只作 dev**。
3. **FinQA + TAT-QA（金融数值推理，MIT / CC BY 4.0）** — 定向补齐**辅助指标**。理由：FinQA 是少数自带**推导程序（program）**金标的集，直接映射我方「推导步骤正确率」；TAT-QA 自带 **scale（单位口径）标注**，直接映射「单位/口径错误率 ≤ 3%」。这两条辅助指标如果不用它们，就得全部自标。**但两者污染都是高，只能作为辅助指标的标注参考源与 dev 集，不进 test。**

**备选说明**
- **DSBench** 办公契合度最高（Excel + 财务建模，466 条分析题），**但 non-commercial 是硬限制**。如果本 benchmark 会对外发布或商用，直接排除；如果纯内部评测，强烈建议纳入 —— 它是唯一大规模覆盖 `.xlsx` 的集。这条决策需要上游明确。
- **Archer**（中英双语、算术比率/假设推理）横跨 G6/G7，是目前找到的**中文侧最相关**的数值推理集，建议纳入观察名单（许可证待核实）。

**建议采样量（G6 总计 ~600 条 test + ~400 条 dev）**

| 来源 | test | dev | 说明 |
|---|---|---|---|
| DABStep hard | 200 | 50 | 主力，区分度最高 |
| DABStep easy | 80 | 30 | 保底档，防止全 0 分无法区分弱模型 |
| 自建办公场景题（见第 5 节） | 250 | 100 | **必须自建**，公开集覆盖不到中文/Excel/业务口径 |
| InfiAgent-DABench | 0 | 100 | 只作 dev（污染中） |
| FinQA / TAT-QA 抽样 | 70（改写后） | 120（原题） | 原题污染高；**改写数字与实体后**方可进 test |

**需要的改造**
1. **统一答案规范化层**：数值容差（相对 1e-6 或绝对 0.01，二者取宽）、千分位/货币符号/百分号剥离、单位换算（万/亿/K/M、元/分）、日期格式归一 —— 否则 EM 会被格式噪声拉低 3–5 个点，指标失真。
2. **补「推导步骤要点」金标**：DABStep 只有最终答案。建议对 test 集人工补 3–5 条 key steps（如「按 merchant_id 分组」「排除 refund 行」「用 settlement 口径而非 authorization」），用关键词/结构化命中率打分，而非 LLM judge。
3. **补「口径」标签**：给每条题打一个 `caliber` 字段（时间口径 / 去重口径 / 含税口径 / 统计对象口径），才能算出「单位/口径错误率」这条辅助指标。TAT-QA 的 scale 标注可作模板。
4. **执行沙箱对接**：InfiAgent 与 DABStep 的评测都假定有 Python 执行环境，统一接到第 3 节的沙箱。

### 2.2 G7-SQL

**首选推荐（2 + 1 个）**

1. **BIRD-SQL（12,751 对 / 95 库 / 33.4 GB，CC BY-SA 4.0）** — 首推。理由：① 真实脏数据库 + 需外部知识，远比 Spider 难被记忆；② **自带 VES（有效效率分）**，是唯一现成对接我方「执行计划代价比」辅助指标的集；③ 全 SQLite，**本地可跑、零云账号**；④ 有 **Mini-Dev V2（780 条，含 500 条 SELECT-only）** 支持轻量冷启动，不必一上来就下 33.4 GB。注意 **CC BY-SA 的传染性**：我方若发布衍生数据集需同许可证开放。
2. **BIRD-CRITIC（600 dev + 200 held-out OOD）** — 次推。理由：① 2025 年新题，**held-out OOD 测试集是明确的抗污染设计**；② 题型是「修一条报错/结果不对的真实 SQL」，比从零写 SQL 更贴近办公日常；③ 官方给 docker-compose。**建议只上 PostgreSQL 分支（`flash-exp` 200 条或 `-postgresql` 530–600 条）**，跳过 Oracle/MSSQL —— 那两个方言的镜像体量和授权是纯负担。
3. **Spider 2.0（632，仅作上限探针）** — 理由：GPT-4o 仅 10.1%、o1-preview agent 21.3%、lite 上标准 parser 5.7%，是目前区分度最高的 SQL 集。**但全量评测必须注册 BigQuery / Snowflake / ServiceNow / dbt Cloud 账号并填 service account key —— 这是现实阻碍，不适合作常态化主指标。** 建议只取 Spider2-lite 中可本地 SQLite/DuckDB 执行的部分，季度性跑一次作天花板参考。

**明确降级**
- **Spider 1.0 / CSpider / WikiSQL**：已饱和（Spider 1.0 上 o1-preview agent 91.2%、GPT-4o 86.6%）+ 已彻底公开。**只作 dev / 回归冒烟测试，绝不作准入依据。**

**建议采样量（G7-SQL 总计 ~500 条 test + ~300 条 dev）**

| 来源 | test | dev | 说明 |
|---|---|---|---|
| BIRD dev（去 Mini-Dev 重叠） | 200 | 100 | 主力 |
| BIRD Mini-Dev | 0 | 80 | 联调用，跑得快 |
| BIRD-CRITIC PostgreSQL（含 held-out OOD 200） | 150 | 60 | **held-out 200 条整体放进 test** |
| 自建中文 schema 题（见第 5 节） | 150 | 40 | 中文字段名 + 中文业务口径，公开集无覆盖 |
| Spider 1.0 | 0 | 20 | 仅冒烟 |
| Spider2-lite 本地可执行子集 | 季度专项 | — | 不进常态主指标 |
| DuSQL / Archer 中文抽样 | 观察 | 观察 | 许可证与 DB 构建成本待评估 |

**需要的改造**
1. **统一 checker 接口**：BIRD 的 EX + VES、BIRD-CRITIC 的 Docker 判分、Spider 的 EX 三套脚本口径不一，必须收敛成一个 `check(sql, db, gold_result) -> {exec_ok, ast_ok, result_equiv, cost_ratio}` 接口（实现要点见第 3 节）。
2. **AST 合法率单独拆出**：现有集都只报执行通过率。需接一个方言感知的 parser（如 `sqlglot`，支持 SQLite/PG/MySQL 多方言）在执行前先判 AST 合法，才能区分「语法错」与「语义错」。
3. **执行计划代价比**：BIRD 的 VES 是基于**执行时间**的，噪声大（受机器负载影响）。建议改成 `EXPLAIN QUERY PLAN`（SQLite）/ `EXPLAIN (FORMAT JSON)`（PG）抽取的估算代价比值，并保留 VES 作对照。
4. **磁盘策略**：全量 BIRD 33.4 GB 建议放共享只读卷 + 每次评测 copy-on-write 挂载，不要每个 worker 各存一份。

### 2.3 G7-Code

**首选推荐（3 个）**

1. **BigCodeBench（1,140 任务 / 723 函数调用 / 139 库，Apache-2.0）** — 首推。理由：① 任务形态是「组合调用多个库完成一件实际的事」，与办公自动化脚本（读文件、转格式、调 API、画图）的真实需求最接近；② 有 Complete / Instruct 两种模式，可分别测补全与指令遵循；③ Apache-2.0 可商用。风险：**依赖 139 个库的版本，必须锁死在固定镜像里**，否则第三方库升级会造成大量假失败。
2. **LiveCodeBench（v6 已 1,055 题，CC BY 4.0）** — 必选，但**定位是保鲜探针而非主力**。理由：唯一带**精确发布日期**的集，可按「模型训练截止日之后」切片，实证有效（DeepSeek-33B、GPT-4o 在各自截止日后的题上明显下滑）。缺点：竞赛题与办公任务分布差距大，权重建议 ≤ 20%。
3. **SWE-bench Verified（500，MIT harness）小样本** — 作能力上限探针。理由：仓库级真实修复是最强信号。**但必须知道它的两个坑**：污染是隐性的（97.8% 的评测测试文件在 base_commit 前已公开、92.8% 修复 commit 可由 issue 号搜到、60.83% 的题 issue 正文里就写了解法；过滤后平均解决率从 51.7% 掉到 25.9%），且环境极重（≥120 GB，全缓存 240–684 GB）。**建议只抽 100 条、季度跑一次。**

**补充（低成本高信息量）**
- **CRUXEval（800，MIT）**：测「读代码预测执行结果」，几乎零环境成本，能诊断模型是不是只会套模板。
- **Aider Polyglot（225）**：唯一直接测「编辑既有文件 + diff 格式合规」的集，若我方 benchmark 含 agent 形态，这条不可替代。练习内容版权归 Exercism，注意再分发限制。

**明确降级**
- **HumanEval / MBPP / HumanEval+ / MBPP+**：**只作 dev 与回归冒烟**。理由见第 4 节。EvalPlus 的强化测试解决的是「假阳性」，**不解决「模型见过题」**。

**建议采样量（G7-Code 总计 ~450 条 test + ~350 条 dev）**

| 来源 | test | dev | 说明 |
|---|---|---|---|
| BigCodeBench（Instruct 为主） | 250 | 150 | 主力 |
| LiveCodeBench（仅取评测发起日前 6 个月内发布的题） | 100 | 50 | **滚动更新，每季度重切** |
| 自建办公脚本题（见第 5 节） | 100 | 50 | Excel/PDF/邮件处理等 |
| CRUXEval | 0 | 60 | 诊断用 |
| SWE-bench Verified 抽样 100 | 季度专项 | — | 不进常态主指标 |
| HumanEval+ / MBPP+ | 0 | 40 | 仅冒烟 |

**需要的改造**
1. **pass@1 / pass@3 checker 统一**：BigCodeBench、LiveCodeBench、EvalPlus 各有自己的 runner。收敛成 `run_tests(code, test_suite, limits) -> {pass, ast_ok, stderr, wall_ms, peak_mem}`，pass@3 用 n=3 独立采样（温度 > 0）而非 best-of-3 重排。
2. **AST 合法率**：执行前跑 `ast.parse`（Python）/ tree-sitter（多语言），把「语法错」从「运行时错」里分离出来。
3. **LiveCodeBench 时间切片自动化**：把「当前评测的时间窗口」做成配置项，每季度自动拉新 release 并重算基线（详见第 4 节）。
4. **镜像固化**：BigCodeBench 的 139 个库、SWE-bench 的 instance 镜像，全部 pull 到**我方私有 registry** 并打 digest 锁定 —— 公开镜像的长期可得性不能依赖第三方。

---

## 3. 沙箱选型建议（可照做）

### 3.1 总体架构：两个沙箱，一个 checker 接口

不要试图用一个沙箱同时满足 SQL 和 Python。建议：

```
                 ┌──────────────────────────────┐
  评测编排器 ──▶ │ 统一 Checker 接口            │
                 │  check(task, output) -> Result│
                 └───────┬──────────────┬────────┘
                         │              │
              ┌──────────▼───┐   ┌──────▼──────────┐
              │ SQL 沙箱      │   │ Python 沙箱      │
              │ (轻，秒级重置) │   │ (中，镜像级重置) │
              └──────────────┘   └─────────────────┘
```

`Result` 统一字段：`exec_ok / ast_ok / result_equiv / pass / cost_ratio / wall_ms / peak_mem / err_class`。

### 3.2 SQL 沙箱：以 BIRD 的 SQLite 为底座

**为什么选 BIRD 的 SQLite 而不是 SWE-bench 的 Docker**：
- BIRD 全部是 SQLite 单文件库，**重置 = 复制一个文件**，毫秒级；33.4 GB 是全量上限，Mini-Dev 只要几百 MB。
- SWE-bench 的 Docker 方案 ≥120 GB 起、全缓存 240–684 GB，重置是重建容器，秒级到分钟级 —— 对 SQL 这种高频短查询完全不划算。
- Spider 2.0 的 BigQuery/Snowflake 路线**需要外部云账号**，既有成本又有配额风险，不能作底座。

**具体做法**：

1. **底座分三层**
   - L1（默认）：**SQLite**，承载 BIRD、Spider 1.0、KaggleDBQA、自建中文库。只读母本放共享卷，每个任务用 **`ATTACH` 只读 + 临时可写 overlay** 或直接 `cp` 到 tmpfs。
   - L2（可选）：**PostgreSQL in Docker**，承载 BIRD-CRITIC 的 PG 分支与需要窗口函数/CTE 高级特性的自建题。
   - L3（专项）：**DuckDB**，承载 Spider2-lite 里本地可执行的部分与 Parquet/CSV 直查场景。**不上 BigQuery/Snowflake。**

2. **状态重置策略**
   - SQLite：母本 `chmod 444` 放共享只读目录；每个 task 起一个 tmpfs 目录，`cp --reflink=auto` 复制（支持 CoW 的文件系统近乎零成本），task 结束整个目录 `rm -rf`。**绝不允许任务间共享同一个 db 文件句柄。**
   - PostgreSQL：用 **template database** —— `CREATE DATABASE task_x TEMPLATE bird_critic_base`，跑完 `DROP DATABASE`。比重启容器快一到两个数量级。容器本身每 N 个任务（建议 200）回收一次防止连接泄漏。
   - 每个 task 前**强制校验母本 checksum**，防止上一个任务写穿。

3. **超时与资源限制**
   - 单条 SQL 硬超时 **30 s**（SQLite 用 `progress_handler` 中断，PG 用 `statement_timeout = 30000`）。
   - 单 task 总超时 **120 s**（含多次交互）。
   - 内存：容器 `--memory=2g --memory-swap=2g`。
   - **只读执行原则**：默认以只读连接执行；仅当任务本身是 DDL/DML 类（BIRD-CRITIC 里有）才开放写，且写在 CoW 副本上。
   - 禁用危险扩展：SQLite 关掉 `load_extension`；PG 用受限角色，禁 `COPY ... TO PROGRAM`、`pg_read_file`、大对象、`dblink`。
   - 网络：**默认 `--network=none`**。

4. **结果集等价判定（实现要点 —— 这是最容易出错的地方）**

   建议实现成一个 `result_equiv(pred_rows, gold_rows, mode)` 函数，默认 `mode="bag"`：

   | 维度 | 规则 | 理由 |
   |---|---|---|
   | **行序** | 默认**忽略行序**（多重集比较，把每行 tuple 规范化后排序再比）。**除非**金标 SQL 里出现 `ORDER BY` 且该 `ORDER BY` 影响输出语义（配合 `LIMIT`/`TOP`），此时严格比较行序 | 绝大多数问题不关心行序；但 "top 5 by revenue" 类问题行序就是答案 |
   | **列序** | 默认**忽略列序**：按「列值多重集」做二分图匹配。同时保留严格模式作对照，报两个数 | 模型经常调换 `SELECT a, b` 为 `SELECT b, a`，语义等价 |
   | **列名** | **忽略列名/别名**（`AS` 随意） | 别名不影响正确性 |
   | **列数** | 严格相等。多选一列（如多带一个 id）判**错**，但单独统计成 `extra_column` 错误类，便于分析 | 多带列会误导下游 |
   | **浮点** | `abs(a-b) <= max(atol, rtol*abs(b))`，建议 `atol=1e-6, rtol=1e-6`。**金额类**单独一档 `atol=0.01`（分）。比较前统一 round 到金标的有效位数 | 浮点直接 `==` 会造成大量假阴性 |
   | **整数 vs 浮点** | `5` 与 `5.0` 判**等** | 方言差异，非模型错误 |
   | **Decimal** | 用 `decimal.Decimal` 解析后比，不走 float，避免 `0.1+0.2` 问题 | 金融口径必须 |
   | **NULL** | `NULL == NULL` 在比较中判**等**（与 SQL 三值逻辑相反 —— 这是**结果集比较**不是 SQL 求值）。`NULL` 与 `0`、`''`、`'NULL'` 字符串判**不等** | 最常见的隐蔽 bug：把 NULL 当空串 |
   | **字符串** | 默认 `strip()` 两端空白；大小写**敏感**（除非金标全大写/全小写且任务无关大小写）；Unicode 做 NFKC 归一化 | 中文全角/半角是真实坑 |
   | **日期/时间** | 统一 parse 成 UTC datetime 再比；`'2024-01-01'` 与 `'2024-01-01 00:00:00'` 判等 | 方言差异 |
   | **布尔** | `True/1/'t'/'true'` 视为等价 | SQLite 无 bool 类型 |
   | **空结果集** | 金标为空、预测为空 → 判**对**；但单独统计比例，**若某题 > 30% 模型都返回空集，标记该题可疑** | 防止「全空集刷分」 |
   | **大结果集** | 超过 10 万行时只比 checksum（对规范化后的行做排序 + SHA256） | 性能 |

   **强烈建议**：把上面每一条写成独立单元测试（构造 pred/gold 对），因为 checker 自身的 bug 会系统性污染所有指标，而且极难事后发现。

5. **执行计划代价比**
   - SQLite：`EXPLAIN QUERY PLAN`，抽扫描类型（SCAN vs SEARCH）、是否用到索引、是否有 TEMP B-TREE。定义 `cost_ratio = cost(pred) / cost(gold)`，用启发式打分（全表扫描记高代价）。
   - PostgreSQL：`EXPLAIN (FORMAT JSON)` 取 `Total Cost`，直接做比值。
   - 同时保留 BIRD 的 **VES**（基于实测时间）作对照，但**报告时以计划代价比为主** —— 实测时间受机器负载影响，跨次不可比。
   - 报告 `cost_ratio` 的中位数与 P90，不报均值（长尾会毁掉均值）。

### 3.3 Python 沙箱：以 BigCodeBench / DABStep 的依赖集为底座

**为什么不用 SWE-bench 的 Docker 作底座**：SWE-bench 的镜像是**每个 instance 一个**（因为每个仓库的依赖不同），240–684 GB 全缓存。这个模式只适合 SWE-bench 本身，不适合作通用底座。

**具体做法**：

1. **镜像分两个**
   - `sandbox-py-analysis`：pandas / numpy / scipy / matplotlib / openpyxl / pyarrow / duckdb —— 服务 G6（DABStep、InfiAgent、DSBench、DS-1000）。
   - `sandbox-py-code`：BigCodeBench 的全部 139 个库（77 标准 + 62 第三方）**版本锁死**，`pip freeze` 产物入版本控制。服务 G7-Code。
   - 两个镜像都 **pull 到我方私有 registry 并按 digest 引用**，不用 tag（tag 会被覆盖）。

2. **状态重置**
   - 每个 task 一个**全新容器**（不是复用容器 + 清目录 —— 后者清不掉内存态、环境变量、后台进程、pip 副作用）。
   - 容器根文件系统 `--read-only`，只挂一个 tmpfs 的 `/workspace`（建议 1–2 GB）作可写区。
   - 数据文件以 `:ro` 挂载。
   - 容器生命周期 ≤ task 超时，到点 `docker kill`。
   - 预热池：常驻 N 个 paused 容器，减少冷启动（BigCodeBench 导入 139 个库的冷启动不可忽略）。

3. **超时与资源限制**
   - 单次代码执行 **60 s**（数据分析类可放宽到 180 s，按 task 类型配置）。
   - 单 task 总墙钟 **300 s**。
   - `--memory=4g --memory-swap=4g --cpus=2 --pids-limit=256`。
   - `ulimit -f`（文件大小）限制 1 GB，防止写爆 tmpfs。
   - **网络 `--network=none`**（LiveCodeBench、BigCodeBench 均不需要联网；若某题需要，单独白名单并标记）。
   - `--security-opt no-new-privileges`、`--cap-drop=ALL`、非 root 用户运行。
   - 捕获并分类 stderr：`syntax_error / import_error / timeout / oom / assertion_fail / runtime_error`，这套分类是后续归因分析的基础。

4. **pass@k 的正确做法**
   - pass@1：温度按被测配置（通常 0），n=1。
   - pass@3：**独立采样 3 次**（温度 > 0，如 0.6），任一通过即算通过。用 Chen et al. 的无偏估计式而非朴素比例。
   - 每次采样独立起容器，**禁止复用执行结果缓存** —— 缓存会让 pass@3 退化成 pass@1。

5. **判分确定性**
   - 固定随机种子（`PYTHONHASHSEED=0`、numpy/random seed）。
   - 固定时区 `TZ=UTC`、locale `C.UTF-8`。
   - 冻结系统时间（部分题会用 `datetime.now()`）—— 用 `libfaketime` 或在 harness 里 monkeypatch。
   - **同一份提交跑两遍必须得到相同分数**，把这条做成 CI 检查。

### 3.4 落地顺序建议

| 阶段 | 做什么 | 能跑通什么 |
|---|---|---|
| 第 1 周 | SQLite 沙箱 + `result_equiv` + AST 检查 | BIRD Mini-Dev 780 条 |
| 第 2 周 | Python 分析镜像 + EM 规范化层 | InfiAgent-DABench 257 条、DABStep easy |
| 第 3 周 | Python 代码镜像（BigCodeBench 依赖锁定）+ pass@k | BigCodeBench、LiveCodeBench |
| 第 4 周 | PG template DB + BIRD-CRITIC | BIRD-CRITIC PG 分支 |
| 第 5–6 周 | 执行计划代价比、DABStep hard、自建题接入 | 全量常态化 |
| 季度专项 | SWE-bench Verified 100 条、Spider2-lite 本地子集 | 上限探针 |

---

## 4. 抗污染方案

### 4.1 为什么污染是这两个门类的头号问题

代码与 SQL 的题面**天然以纯文本形式存在于 GitHub 与 StackOverflow**，正好是所有 LLM 预训练语料的核心来源。这不是「可能被污染」，而是「已被证实污染」：

| 集 | 已核实的污染证据 |
|---|---|
| **HumanEval** | 每条 prompt 在 GitHub 上中位数 **99 次**命中；The Pile 中 **12.2%** 样本重合、The Stack 中 **18.9%**；RedPajama-1T / StarCoder-Data 与其重合 **8–18%**。更隐蔽的是**间接泄漏**：Evol-Instruct 等由 GPT-3.5/4 生成的合成微调集里重现了语义等价的 HumanEval 题目。在受污染合成集上训练可让 HumanEval pass@1 虚高 **最多 14 个绝对点**，而在未污染的 LBPP 上几乎不变；顶尖模型换到新鲜集上掉幅可达 **43%** |
| **MBPP** | 同源同理，且题目更简单，饱和更早 |
| **Spider 1.0** | 已饱和：o1-preview 类 agent **91.2% EX**、GPT-4o **86.6%**。schema 小而干净、标注 SQL 全网可见 |
| **SWE-bench Verified** | 隐性污染最重：**97.8%** 的评测测试文件在 `base_commit` 时点前已公开；**92.8%** 的修复 commit 可用 issue 号在公开 GitHub 历史直接搜到；**60.83%** 的已解决 issue 存在「解法泄漏」（issue 正文/评论里写明了做法）。过滤泄漏题与弱测试后（SWE-bench+），平均解决率从 **51.7% 掉到 25.9%** |

**为什么不能单独用作准入依据**：我方 G7 门槛是 **pass@1 ≥ 0.8**。在 HumanEval 上，这个数字今天连中型开源模型都能达到 —— 不是因为它们会写代码，而是因为它们背过这 164 道题。**用一个已被背过的集设门槛，等于门槛不存在。** 同理 Spider 1.0 的 EX ≥ 0.8 早已被跨过。这两个集只能回答「模型有没有基本能力」，不能回答「模型有多强」。

### 4.2 分级：哪些只能当 dev，哪些能当 test

| 等级 | 集 | 用途 | 规则 |
|---|---|---|---|
| **禁入 test（仅 dev / 冒烟）** | HumanEval、HumanEval+、MBPP、MBPP+、Spider 1.0、CSpider、WikiSQL、WikiTableQuestions、TabFact、DS-1000、CodeContests | pipeline 联调、回归冒烟、快速 sanity check | 分数**不进任何对外报告**；只用来判断「评测链路是否坏了」 |
| **改写后可入 test** | FinQA、TAT-QA、ConvFinQA、HiTab、TableBench 数值子集 | 辅助指标标注源 + 改写题 | 必须**改数字 + 换实体 + 变问法**（见 4.3），改写后重新人工验答案 |
| **可直接入 test（需时间监测）** | BIRD、BIRD-CRITIC、BigCodeBench、DABStep、Archer、CRUXEval、ClassEval、Aider Polyglot | 常态化主指标 | 每季度复检一次饱和度；任一集顶尖模型超过 85% 即降级 |
| **入 test 且自带抗污染机制** | LiveCodeBench（时间切片）、BIRD-CRITIC held-out OOD 200 条 | 保鲜探针 | LiveCodeBench 每季度重切窗口 |
| **专项探针（不进常态主指标）** | SWE-bench Verified、Spider 2.0 | 能力上限参考 | 季度跑一次，单独报告，**必须同时报「泄漏过滤后」的分数** |

### 4.3 Canary 集怎么构造

目标：一批**保证从未公开**的题，用来测量「模型在公开集上的分数有多少来自记忆」。

**构造方法（G6）**
1. **数据替换法**：取 DABStep / FinQA 的题型骨架，换成我方自造的合成数据表（字段名、实体名、数值全部重新生成，保持分布相似）。答案由我方脚本算出（脚本即金标，天然正确）。
2. **口径扰动法**：同一张表、同一个问题，构造 3 个口径变体（「本月」= 自然月 / 账期 / 滚动 30 天），金标不同。模型如果靠记忆答，三个变体会给同一个答案 —— 这是**极灵敏的记忆探针**。
3. **中文化 + 业务化**：字段名改成 `订单金额_含税`、`退款标志`、`渠道编码` 等真实中文字段，业务规则写在附带的口径文档里（模仿 DABStep 的异构文档设计）。

**构造方法（G7）**
1. **SQL**：自建 3–5 个中文 schema 的 SQLite/PG 库（电商订单、HR 花名册、报销单、CRM 线索、库存），每库 30–50 题。schema 与数据全部自造，绝不来自公开源。
2. **Code**：从我方内部真实脚本需求里抽题（读 Excel 生成汇总、解析 PDF 表格、批量重命名、调内部 API 格式化输出），测试用例自写。
3. **变异法**：对 BigCodeBench 题目做**语义保持变异**（改函数名、改参数顺序、改库组合），保留原测试的等价改写。若模型在原题上 pass 而在变异题上 fail，即为记忆信号。

**Canary 集的使用纪律**
- **绝不公开发布**，绝不放进任何会被爬取的地方（不上 GitHub public、不上 HF public、不贴进任何 LLM 对话除评测本身）。
- 每条题带一个唯一的 canary GUID 字符串（BIG-bench 式），日后可用它检索判断是否泄漏。
- **每年轮换 1/3**，防止通过 API 评测被反向收集。
- 报告时给出 **Δ = score(公开集) − score(canary 集)**。**Δ 越大，说明该模型在公开集上的分数越依赖记忆。** 这个 Δ 本身应作为一项报告指标。

### 4.4 用 LiveCodeBench 式时间切片做持续保鲜

**机制核心**：LiveCodeBench 给每道题打上**精确的平台发布日期**，评测时只取「模型训练截止日之后」发布的题。已实证有效 —— DeepSeek-Instruct-33B 在其 2023-09 发布日之后的 LeetCode 题上性能显著下滑，GPT-4o 在 2023-11 训练截止之后的题上同样下滑。

**我方落地方案**

1. **给所有题加 `publish_date` 字段**（公开集用原始日期，自建题用创建日期），做成评测配置的一等公民。
2. **评测时双轨报告**：
   - `score_all`：全量分数（可与外部 leaderboard 对齐）。
   - `score_fresh`：只算 `publish_date > model.training_cutoff` 的题。
   - **`score_fresh` 是我方准入的唯一依据**，`score_all` 仅供参考。
   - 若模型未公开训练截止日，按「模型发布日 − 6 个月」保守估计，并在报告中注明该估计。
3. **滚动窗口**：每季度拉一次 LiveCodeBench 新 release（v1→v6 的节奏约 2–4 个月一版，v6 已覆盖到 2025-04），把窗口右移，保持 test 集里始终有 ≥ 100 条「近 6 个月内发布」的题。
4. **饱和度熔断**：任一集上，排名前 3 的模型平均分 **> 85%** 时自动标记「该集已饱和」，下一季度降级为 dev。把这条做成自动检查，不靠人记。
5. **SQL 侧的等价做法**：BIRD-CRITIC 的 200 条 held-out OOD 直接对应「新题」角色；此外每季度从真实报障场景（内部 DBA 工单）新造 30–50 条，形成滚动补充。
6. **同题双版本对照**：对关键题维持「原版 / 变异版」两份，长期跟踪两者分差。分差扩大 = 污染加剧的早期信号。

---

## 5. 「覆盖不到什么」的诚实说明

公开集能覆盖**能力**，但覆盖不了**我方的办公场景形态**。下面是明确覆盖不到的部分：

### 5.1 G6 覆盖不到的

| 缺口 | 说明 | 为什么公开集补不上 |
|---|---|---|
| **中文字段名与中文业务口径** | `本月GMV`、`去重活跃用户`、`签约口径收入` 这类字段名 + 随之而来的口径歧义 | 检索到的中文表格分析集极少：DuSQL / Archer 偏 SQL 不偏分析，中文侧**没有找到 DABStep 级别的多步分析集**（查了「中文 表格问答 数据集」「中文 数据分析 benchmark」，未找到对应物） |
| **Excel / 在线表格形态** | 合并单元格、多 sheet 交叉引用、公式列、透视表、隐藏行、格式即语义（红字=异常） | 只有 **DSBench** 覆盖 `.xlsx`（466 条分析题），**而它 non-commercial 不可商用**。其余全是干净 CSV/JSON |
| **办公场景的轻量分析** | 「这个月报销超标的有几个人」「把这三张表按部门合一下」—— 数据量小、步骤少但口径杂 | 公开集要么太简单（WikiTableQuestions 单跳）要么太难（DABStep hard / DSBench 财务建模），**中间这一档空白** |
| **数据质量问题** | 空值、重复行、编码错乱、日期格式混杂、单位不一致（元/万元混用） | BIRD 有部分脏数据，但 G6 侧的分析集普遍数据干净 |
| **口径需要问人** | 真实办公里正确行为常是「反问澄清」，而非直接给数 | 所有公开集都假定问题定义完整，**无法评测「该不该反问」** |
| **多轮追问** | 「再按渠道拆一下」「上个月呢」 | 只有 ConvFinQA（3,892）和 Tapilot-Crossing（1,024）覆盖，量小且英文 |

### 5.2 G7 覆盖不到的

| 缺口 | 说明 | 为什么公开集补不上 |
|---|---|---|
| **企业内部 DB schema** | 几百张表、命名不规范、无外键约束、有历史遗留字段、口径藏在数仓文档里 | Spider 1.0 schema 太干净；BIRD 好一些但仍是公开域库；**Spider 2.0 最接近（1000+ 列）但绑定 BigQuery/Snowflake 账号** |
| **中文 schema** | 中文表名/字段名/注释、中英混排 | DuSQL 是唯一大规模中文字段名集（23,797 对），但**需自建 DB 环境**、格式非标准 Spider；CSpider 只是问句中文、schema 仍英文 |
| **内部方言与平台** | Hive / MaxCompute / Doris / ClickHouse / StarRocks 等国内常见数仓方言 | 公开集覆盖 SQLite / PG / MySQL / BigQuery / Snowflake / Oracle / MSSQL；**国内数仓方言零覆盖** |
| **内部代码库与私有 API** | 调用内部 SDK、遵守内部编码规范、对接内部服务 | SWE-bench 系全是公开 OSS 仓库 |
| **办公自动化脚本** | 读 Excel 出周报、解析 PDF 发票、批处理文件、对接内部审批系统 | BigCodeBench 最接近（多库组合调用），但任务是通用的、非办公语境 |
| **代码评审 / 重构** | 「这段代码有什么问题」「按新规范重写」 | 几乎无覆盖；Aider Polyglot 沾边（编辑形态）但内容是练习题 |

### 5.3 「公开集可覆盖比例」估计

**这是估计值，不是核实值 —— 下面写清依据。**

| 门类 | 公开集可覆盖比例（估计） | 依据 |
|---|---|---|
| **G6 数据分析** | **35–45%** | 拆维度：①「多步聚合推理能力」覆盖良好（DABStep + InfiAgent + FinQA 合计 ~900 条可用题，约占能力面 60%）；②「Excel/在线表格形态」仅 DSBench 覆盖且不可商用 → 可商用前提下近 **0%**；③「中文字段名 + 中文业务口径」检索未找到对应集 → 近 **0%**；④「办公轻量分析」中间档空白 → ~20%；⑤「口径澄清/反问」→ 0%。五个维度按 30/20/20/20/10 权重加权约 38%。**依据是上表 5.1 逐项检索结果，不是拍脑袋的总数** |
| **G7-SQL** | **45–55%** | ①「SQL 语法与多表推理能力」BIRD 覆盖充分 → ~75%；②「真实脏 schema」BIRD + KaggleDBQA 部分覆盖 → ~50%；③「企业级超大 schema」Spider 2.0 覆盖但**被云账号门槛挡住** → 实际可用 ~20%；④「中文 schema」DuSQL 部分覆盖但需自建环境 → ~30%；⑤「国内数仓方言」→ 0%；⑥「SQL 调试修复」BIRD-CRITIC 覆盖好 → ~70%。按 25/20/15/20/10/10 加权约 49% |
| **G7-Code** | **50–60%** | ①「函数级生成」HumanEval/MBPP/BigCodeBench 覆盖过剩，但前两者已污染 → 有效 ~60%；②「多库组合调用」BigCodeBench 覆盖好 → ~70%；③「保鲜/抗污染」LiveCodeBench 覆盖好 → ~80%；④「仓库级修复」SWE-bench 覆盖但环境重 + 泄漏严重 → 有效 ~35%；⑤「代码编辑/diff」Aider Polyglot → ~40%；⑥「办公自动化脚本语境」→ ~15%；⑦「内部 API / 私有库」→ 0%。按 20/20/15/15/10/15/5 加权约 53% |

**推论**：**G6 需要自建的比例最高（约 60%）**，G7 约 45–50%。上表第 2 节的采样建议里，自建题占比已按此设定（G6 test 约 42% 自建，G7-SQL 约 30%，G7-Code 约 22%）。如果上游希望减少自建工作量，最有效的单点是**确认 DSBench 的商用授权可否谈下来** —— 它一家就能补上 G6 的 Excel 形态缺口。

---

## 6. 引用来源

以下为本文各字段的核实依据（均通过 `google_search` 检索获得，来源按检索回执中标注的出处列出）：

**G6 表格 / 数据分析**
1. TableBench — 886 条测试集 / TableInstruct 19,661 / 4 类任务 / ROUGE-L 与执行判分 / 人类 86.3% vs GPT-4-Turbo 51.32%：TableBench 项目页、AAAI 论文、alphaXiv、HF `Multilingual-Multimodal-NLP/TableBench`（Apache-2.0）
2. DABStep — 450+ 任务 / Adyen × Hugging Face / CC-BY-4.0 / easy-hard 分档 / hard 档顶尖 14.55–16%、human expert easy 62%：HF `adyen/DABstep` 数据集页与 leaderboard、OpenReview、srao.blog
3. DS-1000 — 1,000 题 / 451 个唯一 StackOverflow 源题 / 7 库 / 19.4% 含 surface-form 约束 / FDR 1.8%、FOR 0.5% / Codex-002 pass@1 43.3% / CC-BY-SA-4.0：HF `xlangai/DS-1000`、MLR Press (ICML)、arXiv、alphaXiv
4. DSBench — 540 题（466 分析 + 74 建模）/ 38 场 ModelOff / Kaggle / Excel + 多 GB CSV / non-commercial：GitHub `LiqiangJing/DSBench`
5. InfiAgent-DABench — 257 问 / 52 CSV / DAEval / format-prompting 闭式化 / Python 沙箱 / Apache-2.0：GitHub InfiAgent、HF `infiagent/DABench`
6. TabFact（16k 表 / 118k 陈述 / CC BY 4.0）、WikiTableQuestions（22,033 问 / CC BY-SA 4.0）、FinQA（8,281 问 / MIT）、TAT-QA（16,552 问 / 数据 CC BY 4.0、代码 MIT）、ConvFinQA（3,892 对话 / MIT）：各自 GitHub 仓库与 HF 数据集页
7. HiTab — 10,686 QA / 3,597 层次表 / StatCan、NSF、Wikipedia 来源：ACL 2022、GitHub `microsoft/HiTab`
8. AIT-QA — 515 问 / 116 表 / SEC 10-K 航空业 / CDLA-Sharing-1.0：ACL 2022、GitHub `IBM/AITQA`
9. Tapilot-Crossing — 1,024 轮交互 / 4 场景 / Decision Company 多智能体构造 / ACR 提升最多 44.5%：OpenReview、arXiv

**G7 Text-to-SQL**
10. Spider 1.0 — 10,181 问 / 5,693 SQL / 200 库 / 138 域 / CC BY-SA 4.0 / o1-preview agent 91.2% EX、GPT-4o 86.6%：EMNLP 2018、GitHub `taoyds/spider`、Medium/Colrows 对比分析
11. Spider 2.0 — 632 任务 / 1000+ 列 schema / Spider2-lite 547、Spider2-snow 547、Spider2-dbt 68 / GPT-4o 10.1%、o1-preview 21.3%、lite 上标准 parser 5.7% / 需 BigQuery(GCP service account JSON) + Snowflake + ServiceNow + dbt Cloud 凭据填入 `evaluation_examples/settings/settings.json`：ICLR 2025、arXiv、GitHub `xlang-ai/Spider2`、Medium/Colrows
12. BIRD-SQL — 12,751 question-SQL 对 / 95 库 / **33.4 GB** / 37 领域 / Mini-Dev V2 780 条（含 500 SELECT-only）/ bird23-train-filtered 9,428→6,601 / CC BY-SA 4.0：NeurIPS 2023 Spotlight、bird-bench.github.io、BIRD-SQL GitHub、HF
13. BIRD-CRITIC (SWE-SQL) — 600 dev + 200 held-out OOD / 四方言 PG·MySQL·MSSQL·Oracle / `bird-critic-1.0-open` ~570–600、`-postgresql` ~530–600、`-flash-exp` 200 / docker-compose + `*_table_dumps` 挂载：BIRD-CRITIC GitHub 与项目页
14. KaggleDBQA — 272 评测问 / 8 个 SQLite / 含库文档 / 原始标注 400 问：ACL 2021（Microsoft）、GitHub
15. WikiSQL — 80,654 条 / 24,241 表 / BSD 3-Clause：GitHub `salesforce/WikiSQL`
16. CSpider（10,181 问 / 5,693 SQL / 200 库，Spider 中文译本）、DuSQL（23,797 问/SQL 对 / 200 库 / 813 表 / 160+ 域，百度 ACL 2020）、Chase（中文上下文相关多轮）：各自论文与项目页
17. Archer — 1,042 英文 + 1,042 中文问 / 521 唯一 SQL / 20 库 / 20 域 / 算术·常识·假设推理 / EX 评测：Archer 项目页、Oracle 技术文章

**G7 代码**
18. HumanEval（164 题 / MIT）、MBPP（974 题 = 500 训练 + 474 test/sanitized / CC-BY-4.0）、HumanEval+（测试 ×80）、MBPP+（测试 ×35 / HF 仓库 Apache-2.0）：OpenAI HumanEval 仓库、Google Research MBPP、EvalPlus GitHub 与 HF
19. BigCodeBench — 1,140 任务 / 723 唯一函数调用 / 139 库（77 标准 + 62 第三方）/ 7 域 / Apache-2.0：GitHub `bigcode-project/bigcodebench`、HF
20. LiveCodeBench — 题目带精确发布日期 / v1 400、v2 511、v3 612、v4 713、v5 880、v6 1,055（2023-05 ~ 2025-04）/ 数据集 CC BY 4.0、站点代码 CC BY-SA 4.0 / DeepSeek-33B 与 GPT-4o 在各自截止日后掉分：arXiv、LiveCodeBench GitHub 与 HF
21. SWE-bench — 2,294 instance / 12 个 Python 仓库 / harness MIT / 元数据 CC BY 4.0：GitHub `princeton-nlp/SWE-bench`、ModelScope
22. SWE-bench Verified — 500 条人工校验 / MIT：OpenAI × Princeton、HF `princeton-nlp/SWE-bench_Verified`
23. SWE-bench Docker 环境 — `--cache_level=env` ≥ **120 GB**；全量 instance 镜像 **240–684 GB**（2,290 个未压缩镜像）；优化层注册表（Epoch Research / LogicStar）可压到 **30–67 GB**；镜像托管 Docker Hub `swebench/sweb.eval`、`ghcr.io/epoch-research/swe-bench.eval`：SWE-bench 官方文档与第三方镜像仓库说明
24. SWE-bench Multimodal — 617 instance / 17 个可视化前端仓库 / JS-TS：SWE-bench Multimodal 论文与仓库
25. Multi-SWE-bench — 1,632 instance（2,456 候选 / 68 名专家标注）/ Java·TS·JS·Go·Rust·C·C++：ByteDance Seed 论文与 GitHub
26. CodeContests — ~13,500 题 / Codeforces·AtCoder·CodeChef·CodeNet·Description2Code / 代码 Apache-2.0、题面 CC BY 4.0：DeepMind AlphaCode、HF `deepmind/code_contests`
27. ClassEval — 100 类 / 410 方法 / 平均 33.1 条测试 / 代码 MIT、数据集 CC BY-NC 4.0：GitHub `FudanSELab/ClassEval`
28. CRUXEval — 800 个 Python 函数 / CRUXEval-I 与 -O / MIT：GitHub `facebookresearch/cruxeval`
29. Aider Polyglot — 225 道 Exercism 练习 / 6 语言（C++·Go·Java·JS·Python·Rust）/ harness Apache-2.0、练习内容 © Exercism：Aider 官方 benchmark 说明与 GitHub

**污染证据**
30. HumanEval 泄漏 — GitHub 上每条 prompt 中位数 99 次命中；RedPajama-1T / StarCoder-Data 重合 8–18%；The Pile 12.2%、The Stack 18.9%（Riddell et al.）；受污染合成集使 HumanEval pass@1 虚高最多 14 点而 LBPP 不变；顶尖模型换新鲜集掉幅最多 43%（Matton et al.）：Cohere / ACL Anthology、arXiv
31. Spider 饱和 — o1-preview agent 91.2%、GPT-4o 86.6%；Spider 2.0 上分别跌至 21.3% / 10.1%，lite 上标准 parser 5.7%：Medium/Colrows、arXiv
32. LiveCodeBench 时间切片有效性 — DeepSeek-Instruct-33B 在 2023-09 发布日后的 LeetCode 题上显著下滑；GPT-4o 在 2023-11 训练截止后的题上下滑：arXiv、LiveCodeBench 项目页
33. SWE-bench 泄漏取证 — Verified 500 条中 97.8% 的评测测试文件在 base_commit 前已公开；92.8% 修复 commit 可由 issue 号在公开历史搜到；problem_statement 逐字泄漏 0.0%；60.83% 已解决 issue 存在解法泄漏；SWE-bench+ 过滤后平均解决率由 51.7% 降至 25.9%：DEV Community 取证分析、OpenReview（SWE-bench+）

**未核实字段清单（明确说明查了什么但没查到）**
- HiTab 许可证 —— 查询「HiTab license」，检索回执只确认数据来源（StatCan / NSF / Wikipedia）与规模，未返回明确 LICENSE 文本。
- Tapilot-Crossing 许可证 —— 查询「Tapilot-Crossing license」，只返回构造方法与规模。
- Spider 2.0 仓库许可证 —— 查询「Spider 2.0 license Apache 2.0 GitHub xlang-ai Spider2」，检索只确认了 Spider **1.0** 的 CC BY-SA 4.0，未确认 2.0 自身条款。
- BIRD-CRITIC 独立许可证 —— 查询中只取到环境与规模，未取到独立 LICENSE 声明（推测随 BIRD 主仓 CC BY-SA 4.0，但**未证实**）。
- KaggleDBQA 许可证 —— 查询「KaggleDBQA license」，只确认规模与来源。
- DuSQL 许可证 —— 查询「DuSQL license」，只确认规模与发布方（百度 ACL 2020）。
- Chase 规模 —— 查询「Chase Chinese context-dependent text-to-SQL size」，只确认任务形态，未取到确切题量。
- Archer 许可证 —— 查询中只取到规模、语言构成与评测指标。
- SWE-bench Multimodal / Multi-SWE-bench 许可证 —— 查询中只取到规模与语言构成。
- DS-1000 许可证的两种表述（CC-BY-SA-4.0 与 CC BY 4.0）并存，检索未能唯一确定，需以仓库 LICENSE 文件为准。
- TAT-QA 许可证亦见 NC 表述与 CC BY 4.0 表述并存，需以仓库 LICENSE 文件为准。
- 第 5.3 节的「公开集可覆盖比例」是**本文的估计值，非检索结果**，依据已在该节逐维度写明。
