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


def _run_merge(recipe: Path) -> subprocess.CompletedProcess:
    env = dict(os.environ, PYTHONPATH=str(_SRC))
    return subprocess.run(
        [sys.executable, "-m", "md_merge", "merge", str(recipe), "--force"],
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
            r = _run_merge(recipe)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertFalse((root / "build" / "images" / "stale.png").exists())
            self.assertTrue((root / "images" / "fig.png").exists())
            self.assertTrue(any((root / "build" / "images").rglob("fig.png")))


if __name__ == "__main__":
    unittest.main()
