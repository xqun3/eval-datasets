"""G7 reverse generator: gold SQL first, prompt second.

Flow per item (all RNG derived from the item seed, so runs are reproducible):

1. pick a domain fixture (``assets/*.sql``) -> DDL + dimension rows
2. synthesize extra fact rows deterministically -> ``setup_sql``
3. pick an SQL template matching the requested difficulty -> gold SQL
4. **actually execute** the gold SQL on an in-memory sqlite3 db -> reference result
5. quality gates (empty / degenerate result -> reject, the pipeline retries)
6. only then derive the Chinese prompt from the template's semantics
"""

from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple

from ...registry import GENERATORS
from ...schema import Context, Gold, TaskInstance
from ...stages import QualityGateError
from ...utils.ids import make_id
from .verifier import has_top_level_order_by

ASSETS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")

MUST_NOT = [
    "执行 DROP",
    "执行 DELETE",
    "执行 UPDATE",
    "执行 INSERT",
    "使用 ATTACH",
    "泄露客户手机号",
]


# ---------------------------------------------------------------------------
# domain specs -- three fixtures sharing the same column *roles*
# ---------------------------------------------------------------------------


@dataclass
class DomainSpec:
    key: str
    zh: str
    asset: str
    fact: str
    fact_zh: str
    date_col: str
    date_zh: str
    amount_col: str
    amount_zh: str
    qty_col: str
    qty_zh: str
    status_col: str
    status_zh: str
    statuses: List[Tuple[str, str]]
    channel_col: str
    channel_zh: str
    channels: List[Tuple[str, str]]
    dim_a: str
    dim_a_zh: str
    dim_a_fk: str
    dim_a_name: str
    dim_a_group: str
    dim_a_group_zh: str
    dim_b: str
    dim_b_zh: str
    dim_b_fk: str
    dim_b_name: str
    dim_b_group: str
    dim_b_group_zh: str
    privacy_cols: List[str]


DOMAINS: List[DomainSpec] = [
    DomainSpec(
        key="ecommerce", zh="电商订单", asset="ecommerce.sql",
        fact="orders", fact_zh="订单", date_col="created_at", date_zh="下单日期",
        amount_col="amount", amount_zh="成交金额", qty_col="qty", qty_zh="件数",
        status_col="status", status_zh="订单状态",
        statuses=[("paid", "已支付"), ("refunded", "已退款"), ("cancelled", "已取消"), ("pending", "待支付")],
        channel_col="channel", channel_zh="下单渠道",
        channels=[("app", "App"), ("web", "网页"), ("mini", "小程序"), ("offline", "线下")],
        dim_a="customers", dim_a_zh="客户", dim_a_fk="customer_id", dim_a_name="name",
        dim_a_group="city", dim_a_group_zh="城市",
        dim_b="products", dim_b_zh="商品", dim_b_fk="product_id", dim_b_name="name",
        dim_b_group="category", dim_b_group_zh="商品类目",
        privacy_cols=["phone"],
    ),
    DomainSpec(
        key="saas", zh="SaaS 用量", asset="saas.sql",
        fact="usage_events", fact_zh="用量流水", date_col="event_date", date_zh="用量日期",
        amount_col="cost", amount_zh="消耗费用", qty_col="calls", qty_zh="调用次数",
        status_col="status", status_zh="调用状态",
        statuses=[("success", "成功"), ("failed", "失败"), ("throttled", "限流"), ("pending", "排队中")],
        channel_col="source", channel_zh="接入方式",
        channels=[("api", "API"), ("sdk", "SDK"), ("console", "控制台"), ("batch", "批处理")],
        dim_a="accounts", dim_a_zh="客户账号", dim_a_fk="account_id", dim_a_name="name",
        dim_a_group="region", dim_a_group_zh="大区",
        dim_b="features", dim_b_zh="功能点", dim_b_fk="feature_id", dim_b_name="name",
        dim_b_group="module", dim_b_group_zh="产品模块",
        privacy_cols=["contact_phone"],
    ),
    DomainSpec(
        key="logistics", zh="物流履约", asset="logistics.sql",
        fact="shipments", fact_zh="发运单", date_col="ship_date", date_zh="发运日期",
        amount_col="freight", amount_zh="运费", qty_col="packages", qty_zh="包裹数",
        status_col="status", status_zh="发运状态",
        statuses=[("delivered", "已签收"), ("in_transit", "运输中"), ("returned", "已退回"), ("pending", "待发货")],
        channel_col="route_type", channel_zh="运输方式",
        channels=[("air", "空运"), ("land", "陆运"), ("sea", "海运"), ("express", "快递")],
        dim_a="warehouses", dim_a_zh="仓库", dim_a_fk="warehouse_id", dim_a_name="name",
        dim_a_group="province", dim_a_group_zh="省份",
        dim_b="couriers", dim_b_zh="配送员", dim_b_fk="courier_id", dim_b_name="name",
        dim_b_group="company", dim_b_group_zh="承运商",
        privacy_cols=["hotline"],
    ),
]

DOMAIN_BY_KEY = {d.key: d for d in DOMAINS}


# ---------------------------------------------------------------------------
# fixture loading + deterministic fact-row synthesis
# ---------------------------------------------------------------------------


def load_asset(domain: DomainSpec) -> str:
    path = os.path.join(ASSETS_DIR, domain.asset)
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


def _dates(rng, n: int) -> List[str]:
    out = []
    for _ in range(n):
        month = rng.randint(1, 6)
        day = rng.randint(1, 28)
        out.append("2024-{:02d}-{:02d}".format(month, day))
    return out


def synthesize_rows(domain: DomainSpec, rng, n_rows: int) -> str:
    """Return INSERT statements for ``n_rows`` extra fact rows (ids from 101)."""
    rows = []
    statuses = [s for s, _ in domain.statuses]
    channels = [c for c, _ in domain.channels]
    for i in range(n_rows):
        rid = 101 + i
        a_id = rng.randint(1, 10)
        b_id = rng.randint(1, 8)
        qty = rng.choice([1, 1, 2, 3, 5, 8, 12, 20, 45, 120])
        unit = round(rng.uniform(7.5, 480.0), 2)
        amount = round(qty * unit, 2)
        status = rng.choices(statuses, weights=[5, 2, 2, 1], k=1)[0]
        channel = rng.choice(channels)
        date = _dates(rng, 1)[0]
        rows.append(
            "({}, {}, {}, {}, {}, '{}', '{}', '{}')".format(
                rid, a_id, b_id, qty, amount, status, channel, date
            )
        )
    stmt = "INSERT INTO {} (id, {}, {}, {}, {}, {}, {}, {}) VALUES\n {};".format(
        domain.fact,
        domain.dim_a_fk,
        domain.dim_b_fk,
        domain.qty_col,
        domain.amount_col,
        domain.status_col,
        domain.channel_col,
        domain.date_col,
        ",\n ".join(rows),
    )
    return stmt


def build_database(domain: DomainSpec, rng, n_rows: int = 70) -> Tuple[str, sqlite3.Connection]:
    setup_sql = load_asset(domain) + "\n" + synthesize_rows(domain, rng, n_rows) + "\n"
    con = sqlite3.connect(":memory:")
    con.executescript(setup_sql)
    return setup_sql, con


def run_sql(con: sqlite3.Connection, sql: str) -> Tuple[List[str], List[List[Any]]]:
    cur = con.execute(sql)
    cols = [c[0] for c in (cur.description or [])]
    rows = [list(r) for r in cur.fetchall()]
    cur.close()
    return cols, rows


# ---------------------------------------------------------------------------
# SQL templates (difficulty -> subtype)
# ---------------------------------------------------------------------------


@dataclass
class TemplateOut:
    sql: str
    prompt_body: str
    features: List[str]


TemplateFn = Callable[[DomainSpec, Any], TemplateOut]


def t_l1_filter_agg(d: DomainSpec, rng) -> TemplateOut:
    status, status_zh = rng.choice(d.statuses)
    cutoff = "2024-0{}-01".format(rng.randint(2, 5))
    sql = (
        "SELECT COUNT(*) AS 单据数, ROUND(SUM({amount}), 2) AS 总{amount_zh}, "
        "ROUND(AVG({amount}), 2) AS 平均{amount_zh} "
        "FROM {fact} WHERE {status_col} = '{status}' AND {date_col} >= '{cutoff}'"
    ).format(
        amount=d.amount_col, amount_zh=d.amount_zh, fact=d.fact,
        status_col=d.status_col, status=status, date_col=d.date_col, cutoff=cutoff,
    )
    body = (
        "请统计{fact_zh}表中，{status_zh_col}为「{status_zh}」且{date_zh}不早于 {cutoff} 的记录，"
        "给出单据数、总{amount_zh}和平均{amount_zh}（金额均保留两位小数）。"
    ).format(
        fact_zh=d.fact_zh, status_zh_col=d.status_zh, status_zh=status_zh,
        date_zh=d.date_zh, cutoff=cutoff, amount_zh=d.amount_zh,
    )
    return TemplateOut(sql, body, ["single_table", "filter", "aggregate"])


def t_l1_group_count(d: DomainSpec, rng) -> TemplateOut:
    cutoff = "2024-0{}-01".format(rng.randint(1, 3))
    sql = (
        "SELECT {channel_col}, COUNT(*) AS 单据数, ROUND(SUM({amount}), 2) AS 总{amount_zh} "
        "FROM {fact} WHERE {date_col} >= '{cutoff}' GROUP BY {channel_col}"
    ).format(
        channel_col=d.channel_col, amount=d.amount_col, amount_zh=d.amount_zh,
        fact=d.fact, date_col=d.date_col, cutoff=cutoff,
    )
    body = (
        "请按{channel_zh}分组统计{fact_zh}表中{date_zh}不早于 {cutoff} 的记录，"
        "输出每个{channel_zh}的单据数与总{amount_zh}（保留两位小数）。行顺序不作要求。"
    ).format(
        channel_zh=d.channel_zh, fact_zh=d.fact_zh, date_zh=d.date_zh,
        cutoff=cutoff, amount_zh=d.amount_zh,
    )
    return TemplateOut(sql, body, ["single_table", "group_by", "aggregate"])


def t_l2_join_group(d: DomainSpec, rng) -> TemplateOut:
    status, status_zh = rng.choice(d.statuses)
    sql = (
        "SELECT a.{group_col} AS {group_col}, COUNT(*) AS 单据数, "
        "ROUND(SUM(f.{amount}), 2) AS 总{amount_zh} "
        "FROM {fact} f JOIN {dim} a ON f.{fk} = a.id "
        "WHERE f.{status_col} = '{status}' GROUP BY a.{group_col} "
        "ORDER BY 总{amount_zh} DESC, a.{group_col} ASC"
    ).format(
        group_col=d.dim_a_group, amount=d.amount_col, amount_zh=d.amount_zh,
        fact=d.fact, dim=d.dim_a, fk=d.dim_a_fk, status_col=d.status_col, status=status,
    )
    body = (
        "请关联{fact_zh}表与{dim_zh}表，筛选{status_zh_col}为「{status_zh}」的记录，"
        "按{dim_zh}的{group_zh}分组，输出单据数与总{amount_zh}（保留两位小数），"
        "并按总{amount_zh}从高到低排序，金额相同时按{group_zh}升序。"
    ).format(
        fact_zh=d.fact_zh, dim_zh=d.dim_a_zh, status_zh_col=d.status_zh, status_zh=status_zh,
        group_zh=d.dim_a_group_zh, amount_zh=d.amount_zh,
    )
    return TemplateOut(sql, body, ["join", "group_by", "order_by"])


def t_l2_join_having(d: DomainSpec, rng) -> TemplateOut:
    min_cnt = rng.choice([2, 3])
    sql = (
        "SELECT b.{group_col} AS {group_col}, COUNT(*) AS 单据数, "
        "ROUND(AVG(f.{amount}), 2) AS 平均{amount_zh}, SUM(f.{qty}) AS 总{qty_zh} "
        "FROM {fact} f JOIN {dim} b ON f.{fk} = b.id "
        "GROUP BY b.{group_col} HAVING COUNT(*) >= {min_cnt}"
    ).format(
        group_col=d.dim_b_group, amount=d.amount_col, amount_zh=d.amount_zh,
        qty=d.qty_col, qty_zh=d.qty_zh, fact=d.fact, dim=d.dim_b, fk=d.dim_b_fk, min_cnt=min_cnt,
    )
    body = (
        "请关联{fact_zh}表与{dim_zh}表，按{group_zh}分组，只保留单据数不少于 {min_cnt} 的分组，"
        "输出单据数、平均{amount_zh}（保留两位小数）与总{qty_zh}。行顺序不作要求。"
    ).format(
        fact_zh=d.fact_zh, dim_zh=d.dim_b_zh, group_zh=d.dim_b_group_zh,
        min_cnt=min_cnt, amount_zh=d.amount_zh, qty_zh=d.qty_zh,
    )
    return TemplateOut(sql, body, ["join", "group_by", "having"])


def t_l3_window_rank(d: DomainSpec, rng) -> TemplateOut:
    topn = rng.choice([1, 2])
    sql = (
        "WITH agg AS ("
        " SELECT a.{group_col} AS {group_col}, b.{bname} AS 对象, "
        " ROUND(SUM(f.{amount}), 2) AS 总{amount_zh} "
        " FROM {fact} f JOIN {dim_a} a ON f.{fk_a} = a.id JOIN {dim_b} b ON f.{fk_b} = b.id "
        " GROUP BY a.{group_col}, b.{bname}"
        "), ranked AS ("
        " SELECT agg.*, ROW_NUMBER() OVER (PARTITION BY {group_col} ORDER BY 总{amount_zh} DESC, 对象 ASC) AS 名次 "
        " FROM agg"
        ") SELECT {group_col}, 对象, 总{amount_zh}, 名次 FROM ranked WHERE 名次 <= {topn} "
        "ORDER BY {group_col} ASC, 名次 ASC"
    ).format(
        group_col=d.dim_a_group, bname=d.dim_b_name, amount=d.amount_col, amount_zh=d.amount_zh,
        fact=d.fact, dim_a=d.dim_a, fk_a=d.dim_a_fk, dim_b=d.dim_b, fk_b=d.dim_b_fk, topn=topn,
    )
    body = (
        "请用窗口函数分析：先按{group_a_zh}和{dim_b_zh}名称汇总总{amount_zh}（保留两位小数），"
        "再在每个{group_a_zh}内部按总{amount_zh}从高到低取前 {topn} 名（金额相同时按名称升序），"
        "输出{group_a_zh}、对象名称、总{amount_zh}和名次，结果按{group_a_zh}升序、名次升序排列。"
    ).format(
        group_a_zh=d.dim_a_group_zh, dim_b_zh=d.dim_b_zh, amount_zh=d.amount_zh, topn=topn,
    )
    return TemplateOut(sql, body, ["cte", "window_function", "join", "order_by"])


def t_l3_wide_stats(d: DomainSpec, rng) -> TemplateOut:
    status, status_zh = rng.choice(d.statuses[:2])
    sql = (
        "SELECT a.{group_col} AS {group_col}, "
        "COUNT(*) AS 单据数, "
        "SUM(CASE WHEN f.{status_col} = '{status}' THEN 1 ELSE 0 END) AS {status}单数, "
        "ROUND(SUM(CASE WHEN f.{status_col} = '{status}' THEN f.{amount} ELSE 0 END), 2) AS {status}{amount_zh}, "
        "ROUND(100.0 * SUM(CASE WHEN f.{status_col} = '{status}' THEN 1 ELSE 0 END) / COUNT(*), 2) AS 占比, "
        "(SELECT ROUND(AVG(x.{amount}), 2) FROM {fact} x WHERE x.{fk_a} = f.{fk_a}) AS 单{dim_a_zh}均值 "
        "FROM {fact} f JOIN {dim_a} a ON f.{fk_a} = a.id "
        "GROUP BY a.{group_col}, f.{fk_a} "
        "HAVING COUNT(*) >= 2"
    ).format(
        group_col=d.dim_a_group, status_col=d.status_col, status=status, amount=d.amount_col,
        amount_zh=d.amount_zh, fact=d.fact, fk_a=d.dim_a_fk, dim_a=d.dim_a, dim_a_zh=d.dim_a_zh,
    )
    body = (
        "请做一张宽表统计：以{fact_zh}表关联{dim_a_zh}表，按{group_zh}与{dim_a_zh}ID 分组，"
        "只保留单据数不少于 2 的分组，输出单据数、{status_zh}单数、{status_zh}{amount_zh}合计、"
        "{status_zh}单占比（百分比，保留两位小数），"
        "以及该{dim_a_zh}全量记录的平均{amount_zh}（子查询，保留两位小数）。行顺序不作要求。"
    ).format(
        fact_zh=d.fact_zh, dim_a_zh=d.dim_a_zh, group_zh=d.dim_a_group_zh,
        status_zh=status_zh, amount_zh=d.amount_zh,
    )
    return TemplateOut(sql, body, ["join", "case_when", "subquery", "group_by", "having"])


TEMPLATES: Dict[str, List[Tuple[str, str, TemplateFn]]] = {
    # difficulty -> [(template key, subtype, fn)]
    "L1": [
        ("l1_filter_agg", "单表过滤聚合", t_l1_filter_agg),
        ("l1_group_count", "单表过滤聚合", t_l1_group_count),
    ],
    "L2": [
        ("l2_join_group", "多表关联分组", t_l2_join_group),
        ("l2_join_having", "多表关联分组", t_l2_join_having),
    ],
    "L3": [
        ("l3_window_rank", "窗口函数分析", t_l3_window_rank),
        ("l3_wide_stats", "复杂宽表统计", t_l3_wide_stats),
    ],
}


# ---------------------------------------------------------------------------
# generator
# ---------------------------------------------------------------------------


@GENERATORS.register("G7", pipeline="g7_sql_reverse_v1")
class G7SqlGenerator:
    """Reverse generator for executable SQL tasks."""

    category = "G7"
    pipeline_name = "g7_sql_reverse_v1"
    checker = "sql_result_equiv"
    subtypes = ("单表过滤聚合", "多表关联分组", "窗口函数分析", "复杂宽表统计")

    #: a gold result with fewer rows than this is considered non-discriminative
    min_rows = 1
    #: hard cap so a pathological template cannot blow up the JSONL
    max_rows = 200

    def build(self, draft, ctx) -> TaskInstance:
        rng = draft.rng("g7")
        domain = rng.choice(DOMAINS)
        difficulty = draft.difficulty if draft.difficulty in TEMPLATES else "L1"
        tpl_key, subtype, fn = rng.choice(TEMPLATES[difficulty])

        setup_sql, con = build_database(domain, rng, n_rows=rng.choice([60, 70, 80]))
        try:
            out = fn(domain, rng)
            try:
                cols, rows = run_sql(con, out.sql)
            except sqlite3.Error as exc:
                raise QualityGateError(
                    "gold_sql_execution_failed", {"sql": out.sql, "error": str(exc)}
                )
        finally:
            con.close()

        # -- quality gates --------------------------------------------------
        if len(rows) < self.min_rows:
            raise QualityGateError("empty_gold_result", {"sql": out.sql, "template": tpl_key})
        if len(rows) > self.max_rows:
            raise QualityGateError("gold_result_too_large", {"rows": len(rows), "template": tpl_key})
        if all(all(v is None for v in row) for row in rows):
            raise QualityGateError("all_null_gold_result", {"sql": out.sql})
        if len(rows) == 1 and len(cols) == 1 and rows[0][0] in (0, None):
            raise QualityGateError("degenerate_gold_result", {"sql": out.sql})

        order_sensitive = has_top_level_order_by(out.sql)

        # -- reverse the prompt from the (already验证过的) gold ---------------
        variation = draft.meta.get("variation", {})
        scene = variation.get("scene_line", "")
        distractor = variation.get("distractor", "")
        ddl = [s.strip() + ";" for s in load_asset(domain).split(";") if s.strip().upper().startswith("CREATE")]
        prompt = self._compose_prompt(domain, out, scene, distractor, cols, order_sensitive)

        instance = TaskInstance(
            id=make_id(self.category, subtype, (draft.seq % 9999) + 1),
            category=self.category,
            subtype=subtype,
            difficulty=difficulty,
            lang=draft.lang,
            prompt=prompt,
            gold=Gold(
                type="executable",
                value={
                    "dialect": "sqlite",
                    "setup_sql": setup_sql,
                    "sql": out.sql,
                    "result": {"columns": cols, "rows": rows},
                    "order_sensitive": order_sensitive,
                    "float_tolerance": 1e-6,
                    "privacy_columns": domain.privacy_cols,
                    "features": out.features,
                    "template": tpl_key,
                    "domain": domain.key,
                },
            ),
            checker=self.checker,
            source="synthetic:{}@pending".format(self.pipeline_name),
            split=draft.split,
            context=Context(
                files=[],
                db_schema={"dialect": "sqlite", "ddl": ddl, "fixture": domain.asset},
                kb_docs=[],
                env={"engine": "sqlite3", "readonly": True, "domain": domain.key},
            ),
            tools_available=["sql.execute"],
            must_not=list(MUST_NOT),
        )
        draft.meta["pipeline_name"] = self.pipeline_name
        draft.meta["g7"] = {"template": tpl_key, "domain": domain.key, "rows": len(rows)}
        return instance

    # -- prompt reverse-derivation ----------------------------------------
    def _compose_prompt(
        self,
        domain: DomainSpec,
        out: TemplateOut,
        scene: str,
        distractor: str,
        cols: List[str],
        order_sensitive: bool,
    ) -> str:
        head = "【{}数据分析】".format(domain.zh)
        parts = [head]
        if scene:
            parts.append(scene.strip())
        parts.append(out.prompt_body)
        parts.append("请只输出一条 SQLite 方言的 SELECT 语句，列名请与题目描述保持一致（期望列：{}）。".format("、".join(cols)))
        if order_sensitive:
            parts.append("注意：结果行顺序会被校验。")
        parts.append("禁止任何写操作（DROP/DELETE/UPDATE/INSERT/ATTACH），也不要查询任何联系电话字段。")
        if distractor:
            parts.append(distractor.strip())
        return "\n".join(p for p in parts if p)

    # -- helpers used by the pipeline stages -------------------------------
    def reference_candidate(self, instance: TaskInstance) -> str:
        """The gold answer itself -- deterministic_recheck must score it 1.0."""
        return instance.gold.value["sql"]

    def broken_candidate(self, instance: TaskInstance) -> str:
        """A syntactically valid but wrong answer (used as a discrimination probe)."""
        return "SELECT * FROM ({}) AS t LIMIT 0".format(instance.gold.value["sql"])

    def measure_difficulty(self, instance: TaskInstance) -> Optional[str]:
        feats = set(instance.gold.value.get("features", []))
        if feats & {"window_function", "subquery", "cte"}:
            return "L3"
        if feats & {"join", "having"}:
            return "L2"
        return "L1"
