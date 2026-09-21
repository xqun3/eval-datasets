"""End-to-end CLI: list / convert / validate / stats / check."""
import io
import json
import os
import sys
import unittest
from contextlib import redirect_stdout

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from adapter.cli import main  # noqa: E402
from adapter.utils.io import read_jsonl, write_jsonl  # noqa: E402

FIX = os.path.join(ROOT, "adapter", "fixtures")
OUT = os.path.join(ROOT, "build", "_clitest")


def run(argv):
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = main(argv)
    return rc, buf.getvalue()


class TestCli(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.makedirs(OUT, exist_ok=True)

    def out(self, name):
        return os.path.join(OUT, name)

    def test_list(self):
        rc, txt = run(["list"])
        self.assertEqual(rc, 0)
        self.assertIn("ADAPTERS", txt)
        self.assertIn("CHECKERS", txt)
        self.assertIn("bird_sql", txt)
        self.assertIn("must_not_guard", txt)

    def test_convert_validate_stats(self):
        out = self.out("bird.jsonl")
        rc, txt = run(["convert", "--adapter", "bird_sql",
                       "--in", os.path.join(FIX, "bird_sql.jsonl"),
                       "--out", out,
                       "--aux", os.path.join(FIX, "bird_sql_aux.json")])
        self.assertEqual(rc, 0)
        self.assertIn("converted : 3", txt)
        self.assertIn("filtered  : 1", txt)

        rows = list(read_jsonl(out))
        self.assertEqual(len(rows), 3)

        rc, txt = run(["validate", "--in", out])
        self.assertEqual(rc, 0)
        self.assertIn("RESULT    : OK", txt)

        rc, txt = run(["stats", "--in", out])
        self.assertEqual(rc, 0)
        self.assertIn("instances : 3", txt)
        self.assertIn("G7=3", txt)
        self.assertIn("L1:L2:L3", txt)

    def test_manifest_sidecar_written(self):
        out = self.out("bird2.jsonl")
        run(["convert", "--adapter", "bird_sql",
             "--in", os.path.join(FIX, "bird_sql.jsonl"), "--out", out,
             "--aux", os.path.join(FIX, "bird_sql_aux.json")])
        man = self.out("bird2.manifest.json")
        self.assertTrue(os.path.exists(man))
        with open(man, encoding="utf-8") as fh:
            m = json.load(fh)
        self.assertEqual(m["source"], "public:bird-sql-minidev@v2-2024-06")
        self.assertIn("license", m)
        self.assertEqual(len(m["rows"]), 3)
        self.assertIn("db_id", m["rows"][0])

    def test_convert_options_and_split(self):
        out = self.out("bcb.jsonl")
        rc, txt = run(["convert", "--adapter", "bigcodebench",
                       "--in", os.path.join(FIX, "bigcodebench.jsonl"), "--out", out,
                       "--split", "canary",
                       "--options", json.dumps({"stdlib_only": True})])
        self.assertEqual(rc, 0)
        rows = list(read_jsonl(out))
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(r["split"] == "canary" for r in rows))

    def test_validate_catches_broken_rows(self):
        bad = self.out("bad.jsonl")
        write_jsonl(bad, [{"id": "nope"}])
        rc, txt = run(["validate", "--in", bad])
        self.assertEqual(rc, 1)
        self.assertIn("FAILED", txt)
        self.assertIn("missing field", txt)

    def test_validate_catches_duplicate_ids(self):
        dup = self.out("dup.jsonl")
        rows = list(read_jsonl(os.path.join(ROOT, "build", "_clitest", "bird.jsonl")))
        write_jsonl(dup, rows + [rows[0]])
        rc, txt = run(["validate", "--in", dup])
        self.assertEqual(rc, 1)
        self.assertIn("duplicate id", txt)

    def test_unknown_adapter_reports_cleanly(self):
        rc = main(["convert", "--adapter", "nope",
                   "--in", os.path.join(FIX, "bird_sql.jsonl"),
                   "--out", self.out("x.jsonl")])
        self.assertEqual(rc, 2)

    def test_check_subcommand_scores_and_flags_violations(self):
        inst_path = self.out("bird.jsonl")
        if not os.path.exists(inst_path):
            self.test_convert_validate_stats()
        rows = list(read_jsonl(inst_path))
        resp_path = self.out("responses.jsonl")
        responses = [{"id": rows[0]["id"], "text": rows[0]["gold"]["value"]["ref_solution"]},
                     {"id": rows[1]["id"], "text": "DROP TABLE customers"}]
        write_jsonl(resp_path, responses)
        rc, txt = run(["check", "--in", inst_path, "--responses", resp_path,
                       "--out", self.out("scores.jsonl")])
        self.assertEqual(rc, 0)
        self.assertIn("score=1.000", txt)
        self.assertIn("VIOLATIONS", txt)
        scores = list(read_jsonl(self.out("scores.jsonl")))
        self.assertEqual(len(scores), 2)
        self.assertEqual(scores[0]["score"], 1.0)
        self.assertEqual(scores[1]["score"], 0.0)

    def test_no_subcommand_prints_help(self):
        rc, txt = run([])
        self.assertEqual(rc, 2)
        self.assertIn("usage", txt.lower())


if __name__ == "__main__":
    unittest.main()
