"""pptmerge chapt_section モードの章・節・小節番号付けのテスト。

実行: python -m unittest discover -s tests
"""

import unittest

from md_merge.pptmerge._slide_operation import SlideOperation
from md_merge.pptmerge._slide_titles import compute_chapt_section_titles


def _run(*items, config=None):
    """items: ("slide", 本文テキスト) または (operation 名, value)。"""
    ops = []
    texts = []
    for kind, val in items:
        if kind == "slide":
            texts.append(val)
            n = len(texts)
            ops.append(SlideOperation(
                action="insertslide", value="", source="a.pptx", slidenum=n,
                slidetitle=f"T{n}", composedslidenum=n,
            ))
        else:
            ops.append(SlideOperation(
                action=kind, value=val, source="", slidenum=0, slidetitle="", composedslidenum=0,
            ))
    return [title for _n, title in compute_chapt_section_titles(ops, texts, config)]


class TestExistingBehavior(unittest.TestCase):
    def test_chapter_and_sections(self):
        self.assertEqual(
            _run(("slide", "#CHAPT#"), ("slide", ""), ("slide", ""), ("slide", "#CHAPT#"), ("slide", "")),
            ["1) T1", "1.1) T2", "1.2) T3", "2) T4", "2.1) T5"],
        )

    def test_section_marker_resets_to_one(self):
        self.assertEqual(
            _run(("slide", "#CHAPT#"), ("slide", ""), ("slide", "#SECTION#")),
            ["1) T1", "1.1) T2", "1.1) T3"],
        )

    def test_stay_and_nonumbering(self):
        self.assertEqual(
            _run(("slide", "#CHAPT#"), ("slide", ""), ("slide", "#STAY#"), ("slide", "#NONUMBERING#"), ("slide", "")),
            ["1) T1", "1.1) T2", "1.1) T3", "1.3) T5"],
        )

    def test_operations(self):
        self.assertEqual(
            _run(("chapter", "3"), ("slide", ""), ("section", "5"), ("slide", "")),
            ["3.1) T1", "3.6) T2"],
        )


class TestSubsection(unittest.TestCase):
    def test_subsection_marker(self):
        self.assertEqual(
            _run(
                ("slide", "#CHAPT#"), ("slide", ""), ("slide", "#SUBSECTION#"), ("slide", "#SUBSECTION#"),
                ("slide", ""), ("slide", "#SUBSECTION#"), ("slide", "#CHAPT#"), ("slide", "#SUBSECTION#"),
            ),
            ["1) T1", "1.1) T2", "1.1.1) T3", "1.1.2) T4", "1.2) T5", "1.2.1) T6", "2) T7", "2.0.1) T8"],
        )

    def test_stay_keeps_subsection_number(self):
        self.assertEqual(
            _run(("slide", "#CHAPT#"), ("slide", ""), ("slide", "#SUBSECTION#"), ("slide", "#STAY#"),
                 ("slide", "#SUBSECTION# #STAY#")),
            ["1) T1", "1.1) T2", "1.1.1) T3", "1.1.1) T4", "1.1.1) T5"],
        )

    def test_freeze(self):
        self.assertEqual(
            _run(("slide", ""), ("slide", "#SUBSECTION#"), ("beginstay", ""), ("slide", "#SUBSECTION#"),
                 ("slide", ""), ("endstay", ""), ("slide", "#SUBSECTION#")),
            ["0.1) T1", "0.1.1) T2", "0.1.1) T3", "0.1.1) T4", "0.1.2) T5"],
        )

    def test_subsection_operation_sets_counter(self):
        self.assertEqual(
            _run(("slide", ""), ("subsection", "4"), ("slide", "#SUBSECTION#"), ("section", "+"),
                 ("slide", "#SUBSECTION#")),
            ["0.1) T1", "0.1.5) T2", "0.2.1) T3"],
        )

    def test_chapter_and_section_markers_win(self):
        self.assertEqual(
            _run(("slide", "#CHAPT# #SUBSECTION#"), ("slide", ""), ("slide", "#SECTION# #SUBSECTION#")),
            ["1) T1", "1.1) T2", "1.1) T3"],
        )

    def test_custom_marker_and_delimiter(self):
        cfg = {"indexer": {"subsection_marker": "@SS@", "delimiter": "-", "separator": " "}}
        self.assertEqual(
            _run(("slide", "#CHAPT#"), ("slide", ""), ("slide", "@SS@"), ("slide", "#SUBSECTION#"), config=cfg),
            ["1 T1", "1-1 T2", "1-1-1 T3", "1-2 T4"],
        )


class TestMarkerStrip(unittest.TestCase):
    def test_subsection_marker_is_removed(self):
        from pptx import Presentation
        from pptx.util import Inches
        from md_merge.pptmerge._slide_titles import _strip_chapter_section_stay_markers_from_shape

        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        box = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(3), Inches(1))
        box.text_frame.text = "keep"
        box.text_frame.add_paragraph().text = "#SUBSECTION#"
        _strip_chapter_section_stay_markers_from_shape(box)
        self.assertEqual([p.text for p in box.text_frame.paragraphs], ["keep", ""])


if __name__ == "__main__":
    unittest.main()
