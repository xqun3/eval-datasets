"""Adapter package -- importing it registers every builtin adapter.

Adding a new dataset = drop a module here + add one import line below.
"""
from __future__ import annotations

from . import bird_sql        # noqa: F401  G7 executable   sql_result_equiv
from . import bigcodebench    # noqa: F401  G7 executable   exec_tests
from . import simpleqa        # noqa: F401  G1 factlist     fact_recall
from . import frames          # noqa: F401  G1 factlist     fact_recall
from . import beir            # noqa: F401  G2 reference    doc_recall_at_k
from . import dabstep         # noqa: F401  G6 reference    numeric_em
from . import tau2_bench      # noqa: F401  G9 trace        state_diff
from . import ifeval          # noqa: F401  G4 rubric       format_compliance
