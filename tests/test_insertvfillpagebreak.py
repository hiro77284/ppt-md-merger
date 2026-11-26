"""procedure の insertvfillpagebreak（insertvfill + insertpagebreak の 1 行略記）のテスト。

実行: python -m unittest tests.test_insertvfillpagebreak
"""

import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

from md_merge._procedure import (
    ProcedureNotationError,
    check_procedure_notation,
    normalize_recipe,
)
from md_merge.validate import validate_recipe

_SRC = Path(__file__).resolve().parents[1] / "src"

VF = {"operation": "insertvfill"}
PB = {"operation": "insertpagebreak"}


def _norm(*items, version=4):
    return normalize_recipe({"version": version, "procedure": list(items)})["procedure"]


def _run(*args: str, cwd: Path) -> subprocess.CompletedProcess:
    env = dict(os.environ, PYTHONPATH=str(_SRC))
    return subprocess.run(
        [sys.executable, "-m", "md_merge", *args],
        cwd=cwd, env=env, capture_output=True, text=True,
        encoding="utf-8", stdin=subprocess.DEVNULL,
    )


class TestExpand(unittest.TestCase):
    def test_bare_string_expands(self):
        self.assertEqual(_norm("insertvfillpagebreak"), [VF, PB])

    def test_empty_value_expands(self):
        self.assertEqual(_norm({"insertvfillpagebreak": None}), [VF, PB])

    def test_same_as_hand_written_pair(self):
        self.assertEqual(
            _norm({"insertmd": "a.md"}, "insertvfillpagebreak", {"insertmd": "b.md"}),
            _norm({"insertmd": "a.md"}, "insertvfill", "insertpagebreak", {"insertmd": "b.md"}),
        )

    def test_value_is_error(self):
        with self.assertRaises(ProcedureNotationError):
            _norm({"insertvfillpagebreak": "x"})

    def test_when_applies_to_both(self):
        when = {"var": "PRINT"}
        self.assertEqual(_norm({"insertvfillpagebreak": None, "when": when}), [
            {**VF, "when": when}, {**PB, "when": when},
        ])

    def test_description_stays_on_first(self):
        self.assertEqual(_norm({"insertvfillpagebreak": None, "description": "memo"}), [
            {**VF, "description": "memo"}, PB,
        ])

    def test_inside_group(self):
        items = _norm({"group": ["insertvfillpagebreak"], "when": {"var": "X"}})
        self.assertEqual([i["operation"] for i in items], ["insertvfill", "insertpagebreak"])
        self.assertTrue(all(i.get("_group_when") == [("procedure[0]", {"var": "X"})] for i in items))

    def test_v1_is_error(self):
        for item in ({"operation": "insertvfillpagebreak"}, {"insertvfillpagebreak": None}):
            errors = check_procedure_notation({"version": 1, "procedure": [item]})
            self.assertTrue(errors and "version 2" in errors[0], (item, errors))

    def test_validate_has_no_warning(self):
        r = normalize_recipe({"version": 4, "procedure": [
            {"insertmd": "a.md"},
            {"insertvfillpagebreak": None, "when": {"var": "X"}, "description": "memo"},
        ]})
        self.assertEqual([w for w in validate_recipe(r) if "procedure" in w], [])


class TestMergeEndToEnd(unittest.TestCase):
    def test_merge_output_matches_hand_written_pair(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for n in (1, 2):
                (root / f"src{n}.md").write_text(f"# S{n}\n", encoding="utf-8")
            outputs = {}
            for base, sep in (("r", "  - insertvfillpagebreak\n"),
                              ("h", "  - insertvfill\n  - insertpagebreak\n")):
                recipe = root / f"{base}_recipe.yaml"
                recipe.write_text(textwrap.dedent(f"""\
                    version: 4
                    output:
                      targetbasefilename: {base}
                    procedure:
                      - insertmd: src1.md
                    """) + sep + "  - insertmd: src2.md\n", encoding="utf-8")
                res = _run("merge", str(recipe), "--force", cwd=root)
                self.assertEqual(res.returncode, 0, res.stderr)
                outputs[base] = (root / f"work_{base}_merged.md").read_text(encoding="utf-8")
            self.assertEqual(outputs["r"], outputs["h"])
            merged = outputs["r"]
            self.assertLess(merged.index("# S1"), merged.index("{{vfill}}"))
            self.assertLess(merged.index("{{vfill}}"), merged.index("{{pagebreak}}"))
            self.assertLess(merged.index("{{pagebreak}}"), merged.index("# S2"))


if __name__ == "__main__":
    unittest.main()
