"""insertmd / insertmdpages の終端開放レンジ ``[from-END]`` と ``range-max`` のテスト。

実行: python -m unittest tests.test_mdrange_end
"""

import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

from md_merge._mdrange import DEFAULT_RANGE_MAX, expand_mdfilename, is_open_range
from md_merge._procedure import MDPAGES_INTERNAL_KEY, normalize_recipe
from md_merge.validate import validate_recipe

_SRC = Path(__file__).resolve().parents[1] / "src"


def _run(*args: str, cwd: Path) -> subprocess.CompletedProcess:
    env = dict(os.environ, PYTHONPATH=str(_SRC))
    return subprocess.run(
        [sys.executable, "-m", "md_merge", *args],
        cwd=cwd, env=env, capture_output=True, text=True,
        encoding="utf-8", stdin=subprocess.DEVNULL,
    )


class TestExpandEnd(unittest.TestCase):
    def test_existing_files_only_and_log(self):
        present = {"a1.md", "a2.md", "a3.md", "a5.md"}
        with self.assertLogs(level="INFO") as cm:
            names = expand_mdfilename("a[1-END].md", exists=present.__contains__)
        self.assertEqual(names, ["a1.md", "a2.md", "a3.md", "a5.md"])
        log = "\n".join(cm.output)
        self.assertIn("見つかった最大番号 5", log)
        self.assertIn("探索上限 99", log)
        self.assertIn("スキップした番号: 4", log)
        self.assertNotIn("6", log.split("スキップした番号:")[1])

    def test_skipped_numbers_are_compressed(self):
        present = {"a1.md", "a5.md", "a7.md"}
        with self.assertLogs(level="INFO") as cm:
            expand_mdfilename("a[1-END].md", exists=present.__contains__)
        self.assertIn("スキップした番号: 2-4, 6", "\n".join(cm.output))

    def test_range_max_limits_search(self):
        present = {f"a{n}.md" for n in (1, 2, 3, 5)}
        names = expand_mdfilename("a[1-END].md", exists=present.__contains__, range_max=3, log=False)
        self.assertEqual(names, ["a1.md", "a2.md", "a3.md"])
        present = {"a150.md"}
        self.assertEqual(expand_mdfilename("a[1-END].md", exists=present.__contains__, log=False), [])
        self.assertEqual(
            expand_mdfilename("a[1-END].md", exists=present.__contains__, range_max=200, log=False),
            ["a150.md"],
        )

    def test_zero_padded_from(self):
        present = {"s01.md", "s02.md", "s10.md"}
        self.assertEqual(
            expand_mdfilename("s[01-END].md", exists=present.__contains__, log=False),
            ["s01.md", "s02.md", "s10.md"],
        )

    def test_no_file_found_warns(self):
        with self.assertLogs(level="WARNING") as cm:
            self.assertEqual(expand_mdfilename("a[1-END].md", exists=lambda _: False), [])
        self.assertIn("1 つもありません", "\n".join(cm.output))

    def test_without_exists_returns_all_candidates(self):
        names = expand_mdfilename("a[3-END].md")
        self.assertEqual(len(names), DEFAULT_RANGE_MAX - 2)
        self.assertEqual(names[0], "a3.md")
        self.assertEqual(names[-1], "a99.md")

    def test_lowercase_end(self):
        self.assertTrue(is_open_range("a[1-end].md"))
        self.assertEqual(expand_mdfilename("a[1-end].md", range_max=2), ["a1.md", "a2.md"])

    def test_errors(self):
        for val, kw in (
            ("a[x-END].md", {}),
            ("a[5-END].md", {"range_max": 4}),
            ("a[1-END].md", {"range_max": 0}),
            ("a[1-END].md", {"range_max": "ten"}),
            ("a[1-END].md", {"range_max": True}),
        ):
            with self.assertRaises(ValueError, msg=(val, kw)):
                expand_mdfilename(val, **kw)

    def test_closed_range_unchanged(self):
        self.assertEqual(expand_mdfilename("a[1-3].md", exists=lambda _: False), ["a1.md", "a2.md", "a3.md"])
        self.assertFalse(is_open_range("a[1-3].md"))
        self.assertFalse(is_open_range("a.md"))


class TestNormalize(unittest.TestCase):
    def _norm(self, *items):
        return normalize_recipe({"version": 4, "procedure": list(items)})["procedure"]

    def test_insertmd_keeps_range_max(self):
        self.assertEqual(
            self._norm({"insertmd": "a[1-END].md", "range-max": 20}),
            [{"operation": "insertmd", "mdfilename": "a[1-END].md", "range-max": 20}],
        )

    def test_insertmdpages_open_range_stays_single_item(self):
        when = {"var": "X"}
        items = self._norm({"insertmdpages": "a[1-END].md", "when": when, "range-max": 9})
        self.assertEqual(items, [{
            "operation": "insertmd", "mdfilename": "a[1-END].md", "when": when,
            "range-max": 9, MDPAGES_INTERNAL_KEY: True,
        }])

    def test_validate(self):
        def proc_warnings(*items):
            r = normalize_recipe({"version": 4, "procedure": list(items)})
            return [w for w in validate_recipe(r) if "procedure" in w]

        self.assertEqual(proc_warnings({"insertmd": "a[1-END].md", "range-max": 30}), [])
        self.assertEqual(proc_warnings({"insertmdpages": "a[1-END].md"}), [])
        w = proc_warnings({"insertmd": "a[1-3].md", "range-max": 30})
        self.assertTrue(any("[from-END] レンジのときだけ" in x for x in w), w)
        w = proc_warnings({"insertmd": "a[1-END].md", "range-max": "x"})
        self.assertTrue(any("レンジが不正" in x for x in w), w)


class TestMergeEndToEnd(unittest.TestCase):
    def _setup(self, root: Path, body: str) -> Path:
        for n in (1, 2, 3, 5, 120):
            (root / f"src{n}.md").write_text(f"# S{n}\n", encoding="utf-8")
        recipe = root / "r_recipe.yaml"
        recipe.write_text(textwrap.dedent("""\
            version: 4
            output:
              targetbasefilename: r
            procedure:
            """) + body, encoding="utf-8")
        return recipe

    def test_insertmd_end(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            recipe = self._setup(root, "  - insertmd: src[1-END].md\n")
            res = _run("merge", str(recipe), "--force", cwd=root)
            self.assertEqual(res.returncode, 0, res.stderr)
            merged = (root / "work_r_merged.md").read_text(encoding="utf-8")
            for n in (1, 2, 3, 5):
                self.assertIn(f"# S{n}\n", merged)
            self.assertNotIn("# S120", merged)  # 既定の上限 99 を超える
            self.assertIn("スキップした番号: 4", res.stderr)
            self.assertIn("見つかった最大番号 5", res.stderr)

    def test_insertmd_end_with_range_max(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            recipe = self._setup(root, "  - insertmd: src[1-END].md\n    range-max: 200\n")
            res = _run("merge", str(recipe), "--force", cwd=root)
            self.assertEqual(res.returncode, 0, res.stderr)
            merged = (root / "work_r_merged.md").read_text(encoding="utf-8")
            self.assertIn("# S120", merged)
            self.assertIn("見つかった最大番号 120", res.stderr)

    def test_insertmdpages_end_separates_found_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            recipe = self._setup(root, "  - insertmdpages: src[1-END].md\n")
            res = _run("merge", str(recipe), "--force", cwd=root)
            self.assertEqual(res.returncode, 0, res.stderr)
            merged = (root / "work_r_merged.md").read_text(encoding="utf-8")
            self.assertEqual(merged.count("{{vfill}}"), 3)
            self.assertEqual(merged.count("{{pagebreak}}"), 3)
            self.assertLess(merged.rindex("{{pagebreak}}"), merged.index("# S5"))
            self.assertFalse(merged.rstrip().endswith("{{pagebreak}}"))


if __name__ == "__main__":
    unittest.main()
