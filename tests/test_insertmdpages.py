"""procedure の insertmdpages（MD ごとに改ページして insertmd を並べる略記）のテスト。

実行: python -m unittest tests.test_insertmdpages
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


def _md(name, **extra):
    return {"operation": "insertmd", "mdfilename": name, **extra}


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
    def test_range_is_separated_by_vfill_and_pagebreak(self):
        self.assertEqual(_norm({"insertmdpages": "sourcemd[1-3].md"}), [
            _md("sourcemd1.md"), VF, PB,
            _md("sourcemd2.md"), VF, PB,
            _md("sourcemd3.md"),
        ])

    def test_same_as_hand_written_sequence(self):
        hand = _norm(
            {"insertmd": "sourcemd1.md"}, "insertvfill", "insertpagebreak",
            {"insertmd": "sourcemd2.md"}, "insertvfill", "insertpagebreak",
            {"insertmd": "sourcemd3.md"},
        )
        self.assertEqual(_norm({"insertmdpages": "sourcemd[1-3].md"}), hand)

    def test_single_file_is_plain_insertmd(self):
        self.assertEqual(_norm({"insertmdpages": "sourcemd1.md"}), [_md("sourcemd1.md")])
        self.assertEqual(_norm({"insertmdpages": "a[1-1].md"}), [_md("a1.md")])

    def test_alpha_and_zero_padded_ranges(self):
        self.assertEqual(
            [i.get("mdfilename") for i in _norm({"insertmdpages": "p[a-b].md"})],
            ["pa.md", None, None, "pb.md"],
        )
        self.assertEqual(
            [i["mdfilename"] for i in _norm({"insertmdpages": "s[08-10].md"}) if "mdfilename" in i],
            ["s08.md", "s09.md", "s10.md"],
        )

    def test_no_trailing_separator(self):
        items = _norm({"insertmdpages": "a[1-2].md"}, {"insertmd": "z.md"})
        self.assertEqual(items, [_md("a1.md"), VF, PB, _md("a2.md"), _md("z.md")])

    def test_when_applies_to_every_expanded_item(self):
        when = {"var": "PRINT"}
        items = _norm({"insertmdpages": "a[1-2].md", "when": when})
        self.assertEqual(len(items), 4)
        self.assertTrue(all(i.get("when") == when for i in items), items)

    def test_other_keys_stay_on_first_item(self):
        items = _norm({"insertmdpages": "a[1-2].md", "description": "memo"})
        self.assertEqual(items[0], _md("a1.md", description="memo"))
        self.assertTrue(all("description" not in i for i in items[1:]), items)

    def test_inside_group(self):
        items = _norm({"group": [{"insertmdpages": "a[1-2].md"}], "when": {"var": "X"}})
        self.assertEqual(len(items), 4)
        self.assertTrue(all(i.get("_group_when") == [("procedure[0]", {"var": "X"})] for i in items))

    def test_bad_range_falls_back_to_single_insertmd(self):
        # insertmd と同じく、レンジの誤りは merge の警告 / validate に任せる
        self.assertEqual(_norm({"insertmdpages": "a[1-x].md"}), [_md("a[1-x].md")])

    def test_bare_string_is_error(self):
        errors = check_procedure_notation({"version": 4, "procedure": ["insertmdpages"]})
        self.assertTrue(errors and "値が必要" in errors[0], errors)

    def test_non_string_value_is_error(self):
        with self.assertRaises(ProcedureNotationError):
            _norm({"insertmdpages": ["a.md", "b.md"]})

    def test_mdfilename_key_not_allowed(self):
        with self.assertRaises(ProcedureNotationError):
            _norm({"insertmdpages": "a.md", "mdfilename": "b.md"})

    def test_two_op_keys_is_error(self):
        with self.assertRaises(ProcedureNotationError):
            _norm({"insertmdpages": "a.md", "insertmd": "b.md"})

    def test_v1_is_error(self):
        for item in ({"operation": "insertmdpages", "mdfilename": "a.md"}, {"insertmdpages": "a.md"}):
            errors = check_procedure_notation({"version": 1, "procedure": [item]})
            self.assertTrue(errors and "version 2" in errors[0], (item, errors))

    def test_validate_has_no_unknown_key_warning(self):
        r = normalize_recipe({"version": 4, "procedure": [
            {"insertmdpages": "a[1-3].md", "when": {"var": "X"}},
        ]})
        self.assertEqual([w for w in validate_recipe(r) if "procedure" in w], [])


class TestMergeEndToEnd(unittest.TestCase):
    def test_merge_inserts_vfill_and_pagebreak_between_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for n in (1, 2, 3):
                (root / f"src{n}.md").write_text(f"# S{n}\n", encoding="utf-8")
            recipe = root / "r_recipe.yaml"
            recipe.write_text(textwrap.dedent("""\
                version: 4
                output:
                  targetbasefilename: r
                procedure:
                  - insertmdpages: src[1-3].md
                """), encoding="utf-8")
            res = _run("merge", str(recipe), "--force", cwd=root)
            self.assertEqual(res.returncode, 0, res.stderr)
            merged = (root / "work_r_merged.md").read_text(encoding="utf-8")

            hand = root / "h_recipe.yaml"
            hand.write_text(textwrap.dedent("""\
                version: 4
                output:
                  targetbasefilename: h
                procedure:
                  - insertmd: src1.md
                  - insertvfill
                  - insertpagebreak
                  - insertmd: src2.md
                  - insertvfill
                  - insertpagebreak
                  - insertmd: src3.md
                """), encoding="utf-8")
            res = _run("merge", str(hand), "--force", cwd=root)
            self.assertEqual(res.returncode, 0, res.stderr)
            self.assertEqual(merged, (root / "work_h_merged.md").read_text(encoding="utf-8"))
            self.assertEqual(merged.count("{{vfill}}"), 2)
            self.assertEqual(merged.count("{{pagebreak}}"), 2)
            self.assertLess(merged.index("# S1"), merged.index("{{pagebreak}}"))
            self.assertLess(merged.rindex("{{pagebreak}}"), merged.index("# S3"))


if __name__ == "__main__":
    unittest.main()
