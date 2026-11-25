"""見出し内強制改行 {{br}} の大文字小文字を区別しないことのテスト。

実行: python -m unittest discover -s tests
"""

import shutil
import subprocess
import unittest
from pathlib import Path

from md_merge._semantics import load_semantics
from md_merge.pptmerge._slide_titles import _BR_MARKER_RE
from md_merge.puremd import _transform_leaves

_FILTER = Path(__file__).resolve().parent.parent / "src" / "md_merge" / "filters" / "semantic-break.lua"
_VARIANTS = ("{{br}}", "{{BR}}", "{{Br}}", "{{bR}}")


def _run(md: str, fmt: str) -> str:
    r = subprocess.run(
        ["pandoc", "-f", "markdown", "-t", fmt, "--lua-filter", str(_FILTER)],
        input=md, capture_output=True, text=True, encoding="utf-8", check=True,
    )
    return r.stdout


@unittest.skipUnless(shutil.which("pandoc"), "pandoc がありません")
class TestSemanticBreakFilter(unittest.TestCase):
    def test_typst_any_case(self):
        for mark in _VARIANTS:
            with self.subTest(mark=mark):
                out = _run(f"# 前半{mark}後半\n\n本文A{mark}本文B\n", "typst")
                self.assertEqual(out.count("#linebreak();"), 2)
                self.assertNotIn(mark, out)

    def test_html_any_case(self):
        for mark in _VARIANTS:
            with self.subTest(mark=mark):
                out = _run(f"前半{mark}後半\n", "html")
                self.assertIn("前半<br>後半", out)

    def test_other_text_untouched(self):
        out = _run("{{brx}} と {{b r}}\n", "typst")
        self.assertNotIn("#linebreak", out)


class TestPuremdDropsBr(unittest.TestCase):
    def test_any_case_dropped(self):
        sem = load_semantics()
        for mark in _VARIANTS:
            with self.subTest(mark=mark):
                self.assertEqual(_transform_leaves(f"# 前半{mark}後半\n", sem), "# 前半後半\n")

    def test_other_leaves_stay_case_sensitive(self):
        sem = load_semantics()
        self.assertIn("{{PAGEBREAK}}", _transform_leaves("{{PAGEBREAK}}\n", sem))


class TestSlideTitleBr(unittest.TestCase):
    def test_any_case_removed(self):
        for mark in (*_VARIANTS, "{{ BR }}"):
            with self.subTest(mark=mark):
                self.assertEqual(_BR_MARKER_RE.sub("", f"前半{mark}後半"), "前半後半")


if __name__ == "__main__":
    unittest.main()
