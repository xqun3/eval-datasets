"""Checker package.

Importing this module registers every builtin checker and exposes
``run_check`` -- the ONLY sanctioned way to score a response, because it runs
``must_not_guard`` as a global pre-hook before the instance's own checker.
"""
from __future__ import annotations

import time
from typing import Any, Dict, Optional

from ..registry import get_checker, has_checker
from ..schema import ModelResponse, new_checker_result

# side-effecting imports: each module registers its checkers
from . import must_not          # noqa: F401,E402
from . import sql_equiv         # noqa: F401,E402
from . import fact_recall       # noqa: F401,E402
from . import ir_metrics        # noqa: F401,E402
from . import numeric_em        # noqa: F401,E402
from . import state_diff        # noqa: F401,E402
from . import rubric_judge      # noqa: F401,E402
from . import format_compliance  # noqa: F401,E402
from . import exec_tests        # noqa: F401,E402

GUARD_ID = "must_not_guard"


def run_check(instance, response, checker_id: Optional[str] = None,
              env: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """must_not_guard first; on a hit, score is forced to 0 and we stop.

    The guard result is always merged into the final result:
      * ``violations`` are prepended,
      * ``detail["must_not"]`` keeps the evidence,
      * ``sub_metrics["must_not_fired"]`` records how many rules hit.
    """
    t0 = time.time()
    env = env or {}
    resp = ModelResponse.coerce(response)

    guard_res = get_checker(GUARD_ID).fn(instance, resp, env)
    if guard_res["violations"]:
        guard_res["detail"] = {"must_not": guard_res.get("detail", {}),
                               "short_circuit": True,
                               "skipped_checker": checker_id or instance.checker}
        guard_res["sub_metrics"]["must_not_fired"] = len(guard_res["violations"])
        guard_res["score"] = 0.0
        guard_res["passed"] = False
        guard_res["cost"]["wall_s"] = round(time.time() - t0, 4)
        return guard_res

    cid = checker_id or instance.checker
    if not has_checker(cid):
        return new_checker_result(
            0.0, False, "L1", {"must_not_fired": 0},
            ["未注册的 checker: %s" % cid], {"error": "unknown checker"},
        )
    spec = get_checker(cid)
    gtype = instance.gold.get("type")
    if not spec.supports(gtype):
        return new_checker_result(
            0.0, False, spec.layer, {"must_not_fired": 0},
            ["checker %s 不支持 gold.type=%s" % (cid, gtype)],
            {"supported": list(spec.gold_types)},
        )

    res = spec.fn(instance, resp, env)
    res["sub_metrics"]["must_not_fired"] = 0
    res["detail"]["must_not"] = {"rules_total": guard_res["sub_metrics"]["rules_total"],
                                 "unresolved_rules":
                                     guard_res["sub_metrics"]["unresolved_rules"]}
    res["cost"]["wall_s"] = round(res["cost"].get("wall_s", 0.0), 4)
    return res


__all__ = ["run_check", "GUARD_ID"]
