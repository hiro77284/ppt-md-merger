"""merge の ``<!-- source: -->`` コメントのパス表記（レシピ基点の相対パス）。"""

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from md_merge.merge import _recipe
from md_merge.merge._recipe import _source_display, expand_md


class TestSourceDisplay(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name).resolve()
        (self.root / "src").mkdir()
        (self.root / "mds" / "sub").mkdir(parents=True)

    def tearDown(self):
        self._tmp.cleanup()

    def test_file_under_recipe_dir(self):
        f = self.root / "src" / "a.md"
        self.assertEqual(_source_display(f, self.root / "src"), "a.md")

    def test_sibling_dir_uses_dotdot(self):
        f = self.root / "mds" / "sub" / "b.md"
        self.assertEqual(_source_display(f, self.root / "src"), "../mds/sub/b.md")

    def test_no_yaml_dir_is_absolute(self):
        f = self.root / "mds" / "b.md"
        self.assertEqual(_source_display(f, None), f.as_posix())

    def test_unrelatable_falls_back_to_absolute(self):
        # Windows で別ドライブのとき os.path.relpath は ValueError を出す
        f = self.root / "mds" / "b.md"
        with mock.patch.object(_recipe.os.path, "relpath", side_effect=ValueError):
            self.assertEqual(_source_display(f, self.root / "src"), f.as_posix())

    def test_expand_md_comment(self):
        f = self.root / "mds" / "c.md"
        f.write_text("# C\n", encoding="utf-8")
        out = expand_md(f, yaml_dir=self.root / "src")
        self.assertTrue(out.startswith("<!-- source: ../mds/c.md -->\n"), out)


if __name__ == "__main__":
    unittest.main()
