"""puremd のリーフ記法 lower（_transform_leaves）のテスト。

実行: python -m unittest discover -s tests
"""

import unittest

from md_merge._semantics import load_semantics
from md_merge.puremd import _transform_leaves


class TestPuremdLeaves(unittest.TestCase):
    def setUp(self):
        self.sem = load_semantics()

    def test_pagebreak_dropped(self):
        # GFM に改ページは無いので破棄する（以前は --- に変換していた）
        out = _transform_leaves("A\n\n{{pagebreak}}\n\nB\n", self.sem)
        self.assertNotIn("{{pagebreak}}", out)
        self.assertNotIn("---", out)
        self.assertEqual(out, "A\n\n\n\nB\n")

    def test_pagebreak_at_top_does_not_look_like_frontmatter(self):
        out = _transform_leaves("{{pagebreak}}\n\nkey: value\n\n---\n", self.sem)
        self.assertFalse(out.lstrip().startswith("---"))

    def test_vspace_and_vfill_dropped(self):
        out = _transform_leaves("{{vspace:2}}\n{{vspace:5mm}}\n{{vfill}}\n", self.sem)
        self.assertEqual(out, "\n\n\n")


if __name__ == "__main__":
    unittest.main()
