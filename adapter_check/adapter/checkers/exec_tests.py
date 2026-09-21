"""exec_tests -- run generated Python against unit tests in a subprocess (L1).

Used by G7-Code (BigCodeBench / HumanEval+ / LiveCodeBench style). Everything
runs locally with ``sys.executable`` in a temp dir, with a wall-clock timeout
from ``gold.value.timeout_s``. No network, no Docker.

Honest limitation: this is *not* a security sandbox. Real BigCodeBench needs a
pinned-version container (see adapter_design.md §3). We run offline fixtures
whose tests only touch stdlib.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import time
import uuid
from typing import Any, Dict, List, Optional

from ..registry import register_checker
from ..schema import ModelResponse, new_checker_result
from ..utils.text import extract_code_block

RUNNER = """
import json, sys, unittest, io, traceback
suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules['__main__'])
res = unittest.TextTestRunner(stream=io.StringIO(), verbosity=0).run(suite)
print("___RESULT___" + json.dumps({
    "run": res.testsRun,
    "failures": len(res.failures),
    "errors": len(res.errors),
    "messages": [str(t[1])[:400] for t in (res.failures + res.errors)][:5],
}))
"""


# Deliberately NOT tempfile: some sandboxes allow writing but refuse deletion,
# and tempfile.gettempdir() probes by create-then-delete, which then explodes.
# We create a run dir under the working tree and best-effort clean it up.
RUN_ROOT = os.environ.get("ADAPTER_EXEC_DIR", os.path.join(os.getcwd(), ".adapter_exec"))


def run_python(source: str, timeout_s: float, workdir: Optional[str] = None) -> Dict[str, Any]:
    root = workdir or RUN_ROOT
    tmp = os.path.join(root, uuid.uuid4().hex[:12])
    os.makedirs(tmp, exist_ok=True)
    path = os.path.join(tmp, "candidate_test.py")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(source)
    try:
        try:
            proc = subprocess.run(
                [sys.executable, path],
                cwd=tmp, timeout=timeout_s,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                env={"PATH": os.environ.get("PATH", ""), "PYTHONHASHSEED": "0",
                     "HOME": tmp, "PYTHONDONTWRITEBYTECODE": "1"},
            )
        except subprocess.TimeoutExpired:
            return {"timeout": True, "returncode": -1, "stdout": "", "stderr": "timeout"}
        out = proc.stdout.decode("utf-8", "replace")
        err = proc.stderr.decode("utf-8", "replace")
        parsed: Dict[str, Any] = {}
        for line in out.splitlines():
            if line.startswith("___RESULT___"):
                import json as _json
                parsed = _json.loads(line[len("___RESULT___"):])
        return {"timeout": False, "returncode": proc.returncode,
                "stdout": out[-2000:], "stderr": err[-2000:], "result": parsed}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ``ModuleNotFoundError: No module named 'pandas'`` / ``ImportError: cannot import name 'x'``
_MISSING_MOD_RE = re.compile(
    r"(?:ModuleNotFoundError|ImportError):\s*No module named ['\"]([\w.]+)['\"]")


def _missing_modules(out: Dict[str, Any]) -> List[str]:
    """Module names the run failed on because they are absent from the host.

    This is an *environment* failure, not a wrong answer: the candidate code may
    be perfectly correct. BigCodeBench-style tasks routinely import pandas /
    numpy, and a bare 0.0 here is indistinguishable from "the model got it
    wrong" -- which silently corrupts pass@1. Callers should exclude these from
    the quality metric and report them separately.
    """
    haystack = [out.get("stderr") or "", out.get("stdout") or ""]
    haystack += list((out.get("result") or {}).get("messages") or [])
    found: List[str] = []
    for chunk in haystack:
        for mod in _MISSING_MOD_RE.findall(chunk):
            root = mod.split(".")[0]
            if root not in found:
                found.append(root)
    return found


def exec_tests(instance, response, env: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """gold.value = {"tests":[{"kind":"pytest|unittest","code":...}], "timeout_s":...}"""
    t0 = time.time()
    env = env or {}
    resp = ModelResponse.coerce(response)
    gv = instance.gold["value"]
    tests: List[Dict[str, Any]] = gv.get("tests") or []
    timeout_s = float(gv.get("timeout_s", 30))
    prelude = gv.get("prelude") or ""

    code = extract_code_block(resp.text, "python")
    if not code.strip():
        return new_checker_result(0.0, False, "L1",
                                  {"syntax_ok": 0.0, "tests_total": len(tests), "tests_passed": 0},
                                  [], {"error": "empty candidate"},
                                  {"tokens": 0, "usd": 0.0, "wall_s": time.time() - t0})

    syntax_ok = 1.0
    try:
        compile(code, "<candidate>", "exec")
    except SyntaxError as exc:
        syntax_ok = 0.0
        return new_checker_result(
            0.0, False, "L1",
            {"syntax_ok": 0.0, "tests_total": len(tests), "tests_passed": 0},
            [], {"error": "SyntaxError: %s" % exc},
            {"tokens": 0, "usd": 0.0, "wall_s": round(time.time() - t0, 4)})

    passed_n, per_test = 0, []
    missing: List[str] = []
    env_error_n = 0
    for i, test in enumerate(tests):
        source = "\n\n".join([prelude, code, test.get("code", ""), RUNNER])
        out = run_python(source, timeout_s)
        res = out.get("result") or {}
        ok = (not out["timeout"] and out["returncode"] == 0
              and res.get("run", 0) > 0
              and res.get("failures", 1) == 0 and res.get("errors", 1) == 0)
        mods = [] if ok else _missing_modules(out)
        if mods:
            env_error_n += 1
            for m in mods:
                if m not in missing:
                    missing.append(m)
        passed_n += 1 if ok else 0
        per_test.append({"test": i, "ok": ok, "timeout": out["timeout"],
                         "ran": res.get("run", 0),
                         "messages": res.get("messages", [])[:2],
                         "missing_modules": mods,
                         "stderr": out["stderr"][-300:] if not ok else ""})

    score = passed_n / float(len(tests)) if tests else 0.0
    # Every failure was "this host lacks the library", not "the code is wrong".
    # Surface it so the aggregation layer can drop the task from pass@1 instead
    # of charging the model for a missing dependency.
    env_only_failure = bool(tests) and passed_n == 0 and env_error_n == len(tests)
    detail: Dict[str, Any] = {"per_test": per_test, "code_chars": len(code)}
    if missing:
        detail["missing_modules"] = missing
    if env_only_failure:
        detail["excluded_from_quality"] = True
        detail["error"] = ("environment is missing %s; this is an infrastructure "
                           "failure, not a wrong answer" % ", ".join(missing))
    return new_checker_result(
        score=score, passed=(score >= 1.0 - 1e-9), layer="L1",
        sub_metrics={"syntax_ok": syntax_ok, "tests_total": len(tests),
                     "tests_passed": passed_n, "env_errors": env_error_n,
                     "env_only_failure": env_only_failure},
        violations=[], detail=detail,
        cost={"tokens": 0, "usd": 0.0, "wall_s": round(time.time() - t0, 4)},
    )


register_checker(
    "exec_tests",
    layer="L1",
    gold_types=["executable"],
    description="Runs candidate Python + unit tests in a subprocess with a timeout.",
    tags=["G7", "code"],
)(exec_tests)
