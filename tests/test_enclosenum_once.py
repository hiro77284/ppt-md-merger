"""{{enclosenum:}} が 1 スライドにつき 1 回だけ適用されることのテスト。

実行: python -m unittest discover -s tests
"""

import tempfile
import unittest
from pathlib import Path

import yaml
from pptx import Presentation

from md_merge.pptmerge._slide_titles import postprocess_idresolve


def _make_pptx(path: Path, slides: list[tuple[str, str]]) -> None:
    prs = Presentation()
    layout = prs.slide_layouts[5]  # Title Only
    for title, notes in slides:
        slide = prs.slides.add_slide(layout)
        slide.shapes.title.text = title
        slide.notes_slide.notes_text_frame.text = notes
    prs.save(str(path))


def _titles(path: Path) -> list[str]:
    return [s.shapes.title.text for s in Presentation(str(path)).slides]


class EncloseNumOncePerSlideTest(unittest.TestCase):
    def _run(self, slides: list[tuple[str, str]]) -> list[str]:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            pptx_path = tmp / "merged.pptx"
            resolved = tmp / "resolved.yaml"
            _make_pptx(pptx_path, slides)
            resolved.write_text(yaml.safe_dump({"entries": [
                {"full_id": "section:p:s1", "number": "1", "label": "1) 節1"},
                {"full_id": "section:p:s2", "number": "2", "label": "2) 節2"},
            ]}, allow_unicode=True), encoding="utf-8")
            postprocess_idresolve(pptx_path, resolved, tmp / "log.txt")
            return _titles(pptx_path)

    def test_same_id_twice_applied_once(self):
        notes = "{{enclosenum:section:p:s1}}\n本文\n{{enclosenum:section:p:s1}}"
        self.assertEqual(self._run([("タイトル", notes)]), ["(1) タイトル"])

    def test_different_ids_first_match_wins(self):
        notes = "{{enclosenum:section:p:s2}}\n{{enclosenum:section:p:s1}}"
        self.assertEqual(self._run([("タイトル", notes)]), ["(2) タイトル"])

    def test_unresolved_first_falls_through_to_next(self):
        notes = "{{enclosenum:section:p:missing}}\n{{enclosenum:section:p:s1}}"
        self.assertEqual(self._run([("タイトル", notes)]), ["(1) タイトル"])

    def test_once_per_slide_not_per_deck(self):
        notes = "{{enclosenum:section:p:s1}}\n{{enclosenum:section:p:s1}}"
        self.assertEqual(
            self._run([("A", notes), ("B", notes)]), ["(1) A", "(1) B"],
        )


if __name__ == "__main__":
    unittest.main()
