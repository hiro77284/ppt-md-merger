"""pandoc 前の YAML frontmatter 除去（_filters.strip_frontmatter）のテスト。

実行: python -m unittest discover -s tests
"""

import shutil
import subprocess
import unittest

from md_merge._filters import strip_frontmatter

_MERGED = """<!-- source: a.md -->
<!-- md_merge_rawtitle: T -->
---
title: Foo
hero: a.png
---
# Head A

body a

---

after hr

<!-- source: b.md -->
---
title: Bar
---
# Head B

body b
"""


class TestStripFrontmatter(unittest.TestCase):
    def test_strips_frontmatter_of_every_merged_source(self):
        out, n = strip_frontmatter(_MERGED)
        self.assertEqual(n, 2)
        self.assertNotIn("title: Foo", out)
        self.assertNotIn("title: Bar", out)
        self.assertNotIn("hero:", out)
        # コメント行・本文・本文中の水平線は残る
        self.assertIn("<!-- md_merge_rawtitle: T -->", out)
        self.assertIn("<!-- source: b.md -->", out)
        self.assertIn("# Head A", out)
        self.assertIn("\n---\n\nafter hr", out)

    def test_document_start_without_comment(self):
        out, n = strip_frontmatter("---\ntitle: X\n---\n\nbody\n")
        self.assertEqual(n, 1)
        self.assertEqual(out.strip(), "body")

    def test_no_frontmatter_is_unchanged(self):
        text = "# H\n\nbody\n\n---\n\nmore\n"
        out, n = strip_frontmatter(text)
        self.assertEqual(n, 0)
        self.assertEqual(out, text)

    def test_horizontal_rule_after_body_started_is_kept(self):
        text = "<!-- source: a.md -->\nintro\n\n---\nkey: v\n---\n"
        out, n = strip_frontmatter(text)
        self.assertEqual(n, 0)
        self.assertEqual(out, text)

    def test_non_mapping_block_is_kept(self):
        # 先頭が --- でも中身が YAML マッピングでなければ frontmatter とみなさない
        text = "---\njust a sentence\n---\n"
        out, n = strip_frontmatter(text)
        self.assertEqual(n, 0)
        self.assertEqual(out, text)

    def test_unclosed_block_is_kept(self):
        text = "---\ntitle: X\n\nbody\n"
        out, n = strip_frontmatter(text)
        self.assertEqual(n, 0)
        self.assertEqual(out, text)

    @unittest.skipIf(shutil.which("pandoc") is None, "pandoc not installed")
    def test_pandoc_body_has_no_frontmatter(self):
        out, _ = strip_frontmatter(_MERGED)
        r = subprocess.run(["pandoc", "-t", "plain"], input=out, capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("title", r.stdout)
        self.assertNotIn("hero", r.stdout)
        self.assertIn("body b", r.stdout)


if __name__ == "__main__":
    unittest.main()
