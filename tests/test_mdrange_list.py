"""insertmd / insertmdpages のカンマ区切りレンジ ``[1,2,4-END]`` のテスト。

実行: python -m unittest tests.test_mdrange_list
"""

import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

from md_merge._mdrange import expand_mdfilename, is_open_range
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


class TestExpandList(unittest.TestCase):
    def test_numbers_and_open_range(self):
        present = {"a1.md", "a2.md", "a3.md", "a4.md", "a6.md"}
        names = expand_mdfilename("a[1,2,4-END].md", exists=present.__contains__, log=False)
        self.assertEqual(names, ["a1.md", "a2.md", "a4.md", "a6.md"])

    def test_written_order_kept(self):
        self.assertEqual(
            expand_mdfilename("a[5,1-2,9].md"),
            ["a5.md", "a1.md", "a2.md", "a9.md"],
        )

    def test_spaces_allowed(self):
        self.assertEqual(expand_mdfilename("a[1, 3 ,5-6].md"), ["a1.md", "a3.md", "a5.md", "a6.md"])

    def test_explicit_numbers_kept_even_if_missing(self):
        # 明示した番号・閉じたレンジは従来どおり実在を問わない（後段で見つからない警告）
        present = {"a5.md"}
        names = expand_mdfilename("a[1,2,4-END].md", exists=present.__contains__, log=False)
        self.assertEqual(names, ["a1.md", "a2.md", "a5.md"])

    def test_duplicates_kept_with_warning(self):
        # insertpptx の slides と同じく重複は除かない（警告のみ）
        present = {f"a{n}.md" for n in range(1, 5)}
        with self.assertLogs(level="WARNING") as cm:
            names = expand_mdfilename("a[1,2,1-END].md", exists=present.__contains__)
        self.assertEqual(names, ["a1.md", "a2.md", "a1.md", "a2.md", "a3.md", "a4.md"])
        self.assertIn("複数回挿入", "\n".join(cm.output))
        self.assertIn("a1.md, a2.md", "\n".join(cm.output))

    def test_open_part_without_files_is_info(self):
        present = {"a1.md", "a2.md"}
        with self.assertLogs(level="INFO") as cm:
            names = expand_mdfilename("a[1,2,4-END].md", exists=present.__contains__)
        self.assertEqual(names, ["a1.md", "a2.md"])
        self.assertTrue(all(r.startswith("INFO") for r in cm.output), cm.output)
        self.assertIn("[4-END] に該当するファイルが 1 つもありません", "\n".join(cm.output))

    def test_open_part_log_names_element(self):
        present = {"a4.md", "a6.md"}
        with self.assertLogs(level="INFO") as cm:
            expand_mdfilename("a[1,4-END].md", exists=present.__contains__)
        log = "\n".join(cm.output)
        self.assertIn("[4-END] → 2 件", log)
        self.assertIn("スキップした番号: 5", log)

    def test_zero_padding_per_element(self):
        self.assertEqual(
            expand_mdfilename("s[01,03-04].md"),
            ["s01.md", "s03.md", "s04.md"],
        )

    def test_letters(self):
        self.assertEqual(expand_mdfilename("p[a,c-d].md"), ["pa.md", "pc.md", "pd.md"])

    def test_range_max_applies_to_open_part(self):
        present = {f"a{n}.md" for n in range(1, 10)}
        names = expand_mdfilename("a[1,5-END].md", exists=present.__contains__, range_max=6, log=False)
        self.assertEqual(names, ["a1.md", "a5.md", "a6.md"])

    def test_is_open_range(self):
        self.assertTrue(is_open_range("a[1,2,4-END].md"))
        self.assertTrue(is_open_range("a[1, 4-end].md"))
        self.assertFalse(is_open_range("a[1,2,4-6].md"))

    def test_errors(self):
        for val in ("a[1,,2].md", "a[1,].md", "a[,1].md", "a[1,x-3].md", "a[1,ab].md", "a[1,2-3-4].md", "a[1，2].md"):
            with self.assertRaises(ValueError, msg=val):
                expand_mdfilename(val)

    def test_single_element_without_dash_still_error(self):
        # 従来どおり: カンマなしの [3] は書式エラー
        with self.assertRaises(ValueError):
            expand_mdfilename("a[3].md")


class TestNormalize(unittest.TestCase):
    def _norm(self, *items):
        return normalize_recipe({"version": 4, "procedure": list(items)})["procedure"]

    def test_insertmdpages_closed_list_expands(self):
        items = self._norm({"insertmdpages": "a[1,3].md"})
        self.assertEqual([i["operation"] for i in items],
                         ["insertmd", "insertvfill", "insertpagebreak", "insertmd"])
        self.assertEqual([i.get("mdfilename") for i in items if i["operation"] == "insertmd"],
                         ["a1.md", "a3.md"])

    def test_insertmdpages_open_list_stays_single_item(self):
        items = self._norm({"insertmdpages": "a[1,2,4-END].md"})
        self.assertEqual(items, [{
            "operation": "insertmd", "mdfilename": "a[1,2,4-END].md", MDPAGES_INTERNAL_KEY: True,
        }])

    def test_validate(self):
        def proc_warnings(*items):
            r = normalize_recipe({"version": 4, "procedure": list(items)})
            return [w for w in validate_recipe(r) if "procedure" in w]

        self.assertEqual(proc_warnings({"insertmd": "a[1,2,4-END].md", "range-max": 30}), [])
        w = proc_warnings({"insertmd": "a[1,2,4-6].md", "range-max": 30})
        self.assertTrue(any("[from-END] レンジのときだけ" in x for x in w), w)
        w = proc_warnings({"insertmd": "a[1,,2].md"})
        self.assertTrue(any("レンジが不正" in x for x in w), w)


class TestMergeEndToEnd(unittest.TestCase):
    def _setup(self, root: Path, body: str) -> Path:
        for n in (1, 2, 3, 4, 6):
            (root / f"src{n}.md").write_text(f"# S{n}\n", encoding="utf-8")
        recipe = root / "r_recipe.yaml"
        recipe.write_text(textwrap.dedent("""\
            version: 4
            output:
              targetbasefilename: r
            procedure:
            """) + body, encoding="utf-8")
        return recipe

    def test_insertmd_list(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            recipe = self._setup(root, "  - insertmd: src[1,2,4-END].md\n")
            res = _run("merge", str(recipe), "--force", cwd=root)
            self.assertEqual(res.returncode, 0, res.stderr)
            merged = (root / "work_r_merged.md").read_text(encoding="utf-8")
            for n in (1, 2, 4, 6):
                self.assertIn(f"# S{n}\n", merged)
            self.assertNotIn("# S3", merged)
            self.assertLess(merged.index("# S2"), merged.index("# S4"))
            self.assertLess(merged.index("# S4"), merged.index("# S6"))

    def test_insertmdpages_list(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            recipe = self._setup(root, "  - insertmdpages: src[1,2,4-END].md\n")
            res = _run("merge", str(recipe), "--force", cwd=root)
            self.assertEqual(res.returncode, 0, res.stderr)
            merged = (root / "work_r_merged.md").read_text(encoding="utf-8")
            self.assertEqual(merged.count("{{pagebreak}}"), 3)
            self.assertEqual(merged.count("{{vfill}}"), 3)
            self.assertNotIn("# S3", merged)

    def test_insertmd_list_duplicates_inserted_twice(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            recipe = self._setup(root, "  - insertmd: src[1,2,1].md\n")
            res = _run("merge", str(recipe), "--force", cwd=root)
            self.assertEqual(res.returncode, 0, res.stderr)
            merged = (root / "work_r_merged.md").read_text(encoding="utf-8")
            self.assertEqual(merged.count("# S1\n"), 2)
            self.assertIn("複数回挿入", res.stderr)


if __name__ == "__main__":
    unittest.main()
