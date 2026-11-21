"""clear-dir-before-merge が merge 自身のコピー元画像を消さないことのテスト。

pptimgexport の書き出し先（export-image: ../images/...）と merge の image-dir
（outputdir 未指定時はレシピと同じフォルダの images/）が一致する構成で、
merge 前の全削除によって抽出済み画像がすべて消えていた不具合の再現。

実行: python -m unittest discover -s tests
"""

import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

_SRC = Path(__file__).resolve().parents[1] / "src"


def _run_merge(recipe: Path, *extra: str) -> subprocess.CompletedProcess:
    env = dict(os.environ, PYTHONPATH=str(_SRC))
    return subprocess.run(
        [sys.executable, "-m", "md_merge", "merge", str(recipe), "--force", *extra],
        cwd=recipe.parent, env=env, capture_output=True, text=True,
        encoding="utf-8", stdin=subprocess.DEVNULL,
    )


class TestClearDirGuard(unittest.TestCase):
    def _make_project(self, root: Path, *, outputdir: str | None) -> Path:
        (root / "mds").mkdir()
        (root / "mds" / "a_md.md").write_text(
            "## A\n\n![](../images/fig.png)\n", encoding="utf-8")
        recipe = root / "r_recipe.yaml"
        out = f"  outputdir: {outputdir}\n" if outputdir else ""
        recipe.write_text(textwrap.dedent("""\
            version: 2
            output:
              force: true
              targetbasefilename: r
            """) + out + textwrap.dedent("""\
            input:
              dirs:
                - .
                - mds
            procedure:
              - insertmd: a_md.md
            """), encoding="utf-8")
        return recipe

    def test_sources_inside_image_dir_are_kept(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            recipe = self._make_project(root, outputdir=None)
            (root / "images").mkdir()
            (root / "images" / "fig.png").write_bytes(b"png")
            r = _run_merge(recipe)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertTrue((root / "images" / "fig.png").exists())
            self.assertFalse((root / "images" / "images").exists())
            merged = next(root.glob("*merged*.md")).read_text(encoding="utf-8")
            self.assertIn("](images/fig.png)", merged)
            self.assertIn("削除をスキップ", r.stderr)

    def test_stale_images_still_cleared_when_sources_outside(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            recipe = self._make_project(root, outputdir="build")
            (root / "images").mkdir()
            (root / "images" / "fig.png").write_bytes(b"png")
            (root / "build" / "images").mkdir(parents=True)
            (root / "build" / "images" / "stale.png").write_bytes(b"old")
            r = _run_merge(recipe, "--yes-clear-dir")
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertFalse((root / "build" / "images" / "stale.png").exists())
            self.assertTrue((root / "images" / "fig.png").exists())
            self.assertTrue(any((root / "build" / "images").rglob("fig.png")))


class TestYesClearDirSeparateFromForce(unittest.TestCase):
    """--force（上書き）は image-dir 全削除の承認にならず、--yes-clear-dir だけが承認になる。"""

    def _project_with_stale(self, root: Path) -> Path:
        recipe = TestClearDirGuard()._make_project(root, outputdir="build")
        (root / "images").mkdir()
        (root / "images" / "fig.png").write_bytes(b"png")
        (root / "build" / "images").mkdir(parents=True)
        (root / "build" / "images" / "stale.png").write_bytes(b"old")
        return recipe

    def test_force_alone_does_not_clear(self):
        # recipe は output.force: true、CLI も --force。非対話なので確認できず中止する。
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            recipe = self._project_with_stale(root)
            r = _run_merge(recipe)
            self.assertEqual(r.returncode, 1, r.stderr)
            self.assertTrue((root / "build" / "images" / "stale.png").exists())
            self.assertIn("--yes-clear-dir", r.stderr)

    def test_yes_clear_dir_clears_without_prompt(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            recipe = self._project_with_stale(root)
            r = _run_merge(recipe, "--yes-clear-dir")
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertFalse((root / "build" / "images" / "stale.png").exists())

    def test_pipeline_preflight_honors_yes_clear_dir_only(self):
        sys.path.insert(0, str(_SRC))
        try:
            from md_merge.__main__ import _make_parser
            from md_merge._pipeline import _fill_defaults
            from md_merge.merge import preflight_clear_confirm
        finally:
            sys.path.pop(0)
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            recipe = self._project_with_stale(root)

            def ns(*flags):
                a = _make_parser().parse_args(["ppt_to_pdf", str(recipe), *flags])
                _fill_defaults(a, None)
                return a

            import io
            from contextlib import redirect_stderr
            from unittest import mock
            with mock.patch("builtins.input", side_effect=EOFError), redirect_stderr(io.StringIO()):
                self.assertNotEqual(preflight_clear_confirm(ns("--force")), 0)
                args = ns("--yes-clear-dir")
                self.assertEqual(preflight_clear_confirm(args), 0)
            self.assertTrue(args.clear_dir_confirmed)
            # 事前確認だけで、削除は後段 merge が行う
            self.assertTrue((root / "build" / "images" / "stale.png").exists())

    def test_yes_clear_dir_ignored_with_warning_elsewhere(self):
        env = dict(os.environ, PYTHONPATH=str(_SRC))
        with tempfile.TemporaryDirectory() as d:
            r = subprocess.run(
                [sys.executable, "-m", "md_merge", "validate", str(Path(d) / "none.yaml"), "--yes-clear-dir"],
                env=env, capture_output=True, text=True, encoding="utf-8", stdin=subprocess.DEVNULL,
            )
        self.assertIn("--yes-clear-dir は validate では効果がありません", r.stderr)


if __name__ == "__main__":
    unittest.main()
