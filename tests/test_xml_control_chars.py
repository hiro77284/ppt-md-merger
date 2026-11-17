"""タイトルのソフト改行（Shift+Enter → \\x0b）で pptmerge が
"All strings must be XML compatible" で落ちないことのテスト。

実行: python -m unittest discover -s tests
"""

import tempfile
import unittest
from pathlib import Path

from pptx import Presentation
from pptx.util import Inches

from md_merge.pptmerge._merger import _apply_notes_replacements
from md_merge.pptmerge._slide_operation import _slide_title_text
from md_merge.pptmerge._slide_titles import load_slide_titles, replace_slide_title
from md_merge.pptmerge._xmltext import multiline_text, single_line_text

_TITLE = "エンジニアの仕事の生産性を高める \x0b\x0b文書作成のための情報整理術"
_EXPECTED = "エンジニアの仕事の生産性を高める 文書作成のための情報整理術"


def _make_prs(notes: str | None = None) -> Presentation:
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[0])
    # python-pptx の text setter は \x0b を <a:br/> にする（PowerPoint の Shift+Enter と同じ）
    slide.shapes.title.text = _TITLE
    if notes is not None:
        slide.notes_slide.notes_text_frame.text = notes
    return prs


class XmlTextHelpersTest(unittest.TestCase):
    def test_single_line(self):
        self.assertEqual(single_line_text(_TITLE), _EXPECTED)
        self.assertEqual(single_line_text("a\x00b\x1fc\r\nd"), "abc d")

    def test_multiline(self):
        self.assertEqual(multiline_text("a\x0bb\x00c\nd"), "a\nbc\nd")


class SoftBreakTitleTest(unittest.TestCase):
    def test_title_read_is_single_line(self):
        prs = _make_prs()
        self.assertIn("\x0b", prs.slides[0].shapes.title.text)
        self.assertEqual(load_slide_titles(prs), [(1, _EXPECTED)])
        self.assertEqual(_slide_title_text(prs.slides[0]), _EXPECTED)

    def test_replace_slide_title_with_soft_break(self):
        prs = _make_prs()
        replace_slide_title(prs, 1, "(1) " + prs.slides[0].shapes.title.text)
        self.assertEqual(prs.slides[0].shapes.title.text, "(1) " + _EXPECTED)

    def test_notes_title_placeholder_with_soft_break(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "t.pptx"
            _make_prs(notes="# <__TITLE__>\nvar: {{v:X}}").save(str(path))
            _apply_notes_replacements(path, [{
                "composedslidenum": 1, "basefilename": "b", "filename": "f",
                "slidenum": "1", "title": _TITLE, "vars": {"X": "p\x0bq\x00"},
                "skip": False,
            }])
            notes = Presentation(str(path)).slides[0].notes_slide.notes_text_frame.text
            self.assertEqual(notes, f"# {_EXPECTED}\nvar: p\nq")


if __name__ == "__main__":
    unittest.main()
