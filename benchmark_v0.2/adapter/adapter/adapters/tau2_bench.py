"""tau2-bench (Sierra) -> G9 / trace / state_diff.

Raw task (``tau2/domains/<domain>/tasks.json``, one object per task)::

    {"id": "retail_001", "description": {"purpose": "...", "notes": "..."},
     "user_scenario": {"persona": "...", "instructions": {"task_instructions": "..."}},
     "initial_state": {"orders": [...], "users": [...]},
     "evaluation_criteria": {
        "actions": [{"name":"update_order_address","arguments":{...},"requestor":"assistant"}],
        "env_assertions": [{"table":"orders","expect":[...]}],
        "communicate_info": ["W123"],
        "reward_basis": ["DB","COMMUNICATE","ACTION"]},
     "tools": ["retail.get_order", "retail.update_order_address"]}

Mapping decisions:
  * ``evaluation_criteria.env_assertions`` -> ``gold.value.final_state``.
    When the task only ships an action list (no assertion), we *derive* the
    expected state by replaying the reference actions is NOT possible offline,
    so we fall back to an empty ``final_state`` and rely on the sequence -- the
    row is then flagged ``state_unverified`` in the manifest rather than being
    silently scored as state-checked.
  * ``actions`` -> one entry of ``valid_sequences``. tau2 allows several valid
    orders; extra orders can be appended via ``cfg.options["extra_sequences"]``.
  * write-tools that are *not* in the reference actions become
    ``forbidden_calls`` (the "越权/破坏性误调用 = 0" rule from SCHEMA §0 G9).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..base import Adapter, AdapterConfig
from ..registry import register_adapter
from ..schema import TaskInstance

WRITE_VERBS = ("create", "update", "delete", "cancel", "modify", "set", "add",
               "remove", "send", "transfer", "refund", "exchange", "reset")


def is_write_tool(name: str) -> bool:
    leaf = name.split(".")[-1].lower()
    return any(leaf.startswith(v) or ("_" + v) in leaf for v in WRITE_VERBS)


@register_adapter("tau2_bench")
class Tau2BenchAdapter(Adapter):
    dataset = "tau2-bench"
    version = "v1.0.0"
    category = "G9"
    subtype = "MULTITURN_TOOL_OPS"
    gold_type = "trace"
    checker = "state_diff"
    license = "MIT"
    commercial_use = "yes"
    homepage = "https://github.com/sierra-research/tau2-bench"
    base_must_not = ("调用破坏性工具", "泄露客户手机号")
    lossy_notes = (
        "tau2 的 reward 是 DB × COMMUNICATE × ACTION 的乘积门控，且带 pass^k 稳定性；"
        "我方 state_diff 把它压成 0.7*状态 + 0.15*序列 + 0.15*communicate 的加权分，"
        "乘积门控语义丢失（可用 registry.wrap_third_party 接原生 reward 找回）；"
        "模拟用户（user simulator）不在本适配层内，转换出来的题需要配套环境才能真跑。"
    )

    def infer_difficulty(self, raw_record, inst_kwargs) -> str:
        """G9 heuristic: #reference actions (steps) + #write tools (branches)."""
        steps = inst_kwargs.get("steps", 0)
        writes = inst_kwargs.get("writes", 0)
        if steps >= 6 or writes >= 3:
            return "L3"
        if steps >= 3 or writes >= 1:
            return "L2"
        return "L1"

    def convert(self, raw_record: Dict[str, Any], cfg: AdapterConfig) -> Optional[TaskInstance]:
        ec = raw_record.get("evaluation_criteria") or {}
        actions: List[Dict[str, Any]] = [a for a in (ec.get("actions") or [])
                                         if a.get("requestor", "assistant") == "assistant"]
        scenario = raw_record.get("user_scenario") or {}
        instr = ((scenario.get("instructions") or {}).get("task_instructions")
                 or (raw_record.get("description") or {}).get("purpose") or "").strip()
        if not instr:
            return None
        if not actions and not ec.get("env_assertions"):
            return None                        # filtered: nothing to score against

        tools: List[str] = [str(t) for t in (raw_record.get("tools") or [])]
        seq = [str(a["name"]) for a in actions if a.get("name")]

        final_state: Dict[str, Any] = {}
        for assertion in (ec.get("env_assertions") or []):
            table = assertion.get("table")
            if table:
                final_state[table] = assertion.get("expect")
        state_unverified = not final_state

        valid_sequences: List[List[str]] = []
        if seq:
            valid_sequences.append(seq)
        for extra in (cfg.options.get("extra_sequences") or {}).get(str(raw_record.get("id")), []):
            valid_sequences.append([str(x) for x in extra])

        referenced = set(seq)
        forbidden = sorted(t for t in tools if is_write_tool(t) and t not in referenced)

        gold = {
            "type": "trace",
            "value": {
                "final_state": final_state,
                "valid_sequences": valid_sequences,
                "forbidden_calls": forbidden,
                "communicate_info": [str(c) for c in (ec.get("communicate_info") or [])],
                "ignore_fields": list(cfg.options.get("ignore_fields")
                                      or ["id", "created_at", "updated_at"]),
            },
        }
        persona = scenario.get("persona") or ""
        prompt = instr if not persona else "%s\n\n（用户画像：%s）" % (instr, persona)

        return self.build(
            raw_record, cfg,
            subtype="MULTITURN_TOOL_OPS",
            prompt=prompt,
            gold=gold,
            context={"files": [], "db_schema": None, "kb_docs": [],
                     "env": {"domain": raw_record.get("domain", "retail"),
                             "initial_state": raw_record.get("initial_state") or {}}},
            tools_available=tools,
            difficulty=self.infer_difficulty(
                raw_record, {"steps": len(seq),
                             "writes": sum(1 for s in seq if is_write_tool(s))}),
            lang="en" if not cfg.lang else cfg.lang,
            manifest_extra={"domain": raw_record.get("domain"),
                            "n_actions": len(seq),
                            "state_unverified": state_unverified,
                            "reward_basis": ec.get("reward_basis"),
                            "n_forbidden": len(forbidden)},
        )
