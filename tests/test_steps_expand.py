"""``<!-- #steps -->`` セクションの ``[all]`` 等の展開と、p:timing のクリック数のテスト。

実行: python -m unittest discover -s tests
"""

import logging
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

from lxml import etree
from pptx import Presentation

from md_merge._steps import count_click_steps, expand_steps_sections

_SRC = Path(__file__).resolve().parents[1] / "src"
_P = "http://schemas.openxmlformats.org/presentationml/2006/main"


def _timing_xml(clicks: int, with_effects: int = 0) -> str:
    """メインシーケンスに clickEffect を *clicks* 個、withEffect を *with_effects* 個持つ p:timing。"""
    def par(node_type: str, i: int) -> str:
        return (
            f'<p:par><p:cTn id="{100 + i}" fill="hold"><p:childTnLst>'
            f'<p:par><p:cTn id="{200 + i}" presetID="1" presetClass="entr" nodeType="{node_type}"/></p:par>'
            f'</p:childTnLst></p:cTn></p:par>'
        )
    effects = "".join(par("clickEffect", i) for i in range(clicks))
    effects += "".join(par("withEffect", 50 + i) for i in range(with_effects))
    return (
        f'<p:timing xmlns:p="{_P}"><p:tnLst><p:par><p:cTn id="1" dur="indefinite" nodeType="tmRoot">'
        f'<p:childTnLst><p:seq><p:cTn id="2" dur="indefinite" nodeType="mainSeq">'
        f'<p:childTnLst>{effects}</p:childTnLst></p:cTn></p:seq>'
        # 対話型シーケンス（トリガー付き）は数えない
        f'<p:seq><p:cTn id="3" nodeType="interactiveSeq"><p:childTnLst>{par("clickEffect", 90)}</p:childTnLst></p:cTn></p:seq>'
        f'</p:childTnLst></p:cTn></p:par></p:tnLst></p:timing>'
    )


def _add_slide(prs, note: str, clicks: int | None):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    if clicks is not None:
        slide._element.append(etree.fromstring(_timing_xml(clicks, with_effects=2)))
    slide.notes_slide.notes_text_frame.text = note
    return slide


class _FakeSlide:
    def __init__(self, clicks: int):
        root = etree.fromstring(f'<p:sld xmlns:p="{_P}"/>')
        root.append(etree.fromstring(_timing_xml(clicks, with_effects=1)))
        self._element = root


class TestCountClickSteps(unittest.TestCase):
    def test_counts_main_sequence_click_effects_only(self):
        self.assertEqual(count_click_steps(_FakeSlide(3)), 3)

    def test_no_timing_is_zero(self):
        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        self.assertEqual(count_click_steps(slide), 0)


def _img(step: str, out: str) -> dict:
    return {"export-image-mode": "slide", "export-image-step": step, "export-image": out}


class TestExpandStepsSections(unittest.TestCase):
    A = "../images/steps-slide3_step<__STEP__>.png"
    B = "../images/other-slide3_step<__STEP__>.png"

    def _expand(self, md: str, blocks: list[dict], clicks: int = 3) -> str:
        return expand_steps_sections(textwrap.dedent(md), blocks, lambda: clicks, 3)

    def test_all_expands_to_every_exported_step(self):
        md = """\
            <!-- #steps -->
            ![](../images/steps-slide3_step[all].png){ width=80% }
            <!-- /steps -->"""
        got = self._expand(md, [_img("all", self.A)])
        self.assertEqual(got.splitlines(), [
            "<!-- #steps -->",
            "![](../images/steps-slide3_step0.png){ width=80% }",
            "![](../images/steps-slide3_step1.png){ width=80% }",
            "![](../images/steps-slide3_step2.png){ width=80% }",
            "![](../images/steps-slide3_step3.png){ width=80% }",
            "<!-- /steps -->",
        ])

    def test_path_selects_the_matching_block(self):
        md = """\
            <!-- #steps -->
            ![](../images/other-slide3_step[all].png)
            <!-- /steps -->"""
        got = self._expand(md, [_img("all", self.A), _img("1-2", self.B)])
        self.assertEqual(got.splitlines()[1:-1], [
            "![](../images/other-slide3_step1.png)",
            "![](../images/other-slide3_step2.png)",
        ])

    def test_numeric_spec_is_capped_by_click_count(self):
        md = "<!-- #steps -->\n![](../images/steps-slide3_step[all].png)\n<!-- /steps -->"
        got = self._expand(md, [_img("1-9", self.A)], clicks=2)
        self.assertEqual(got.splitlines()[1:-1], [
            "![](../images/steps-slide3_step1.png)",
            "![](../images/steps-slide3_step2.png)",
        ])

    def test_last_and_subset(self):
        md = """\
            <!-- #steps -->
            ![](../images/steps-slide3_step[last].png)
            ![ステップ<__STEP__>](../images/steps-slide3_step[0, 2].png)
            <!-- /steps -->"""
        got = self._expand(md, [_img("all", self.A)])
        self.assertEqual(got.splitlines()[1:-1], [
            "![](../images/steps-slide3_step3.png)",
            "![ステップ0](../images/steps-slide3_step0.png)",
            "![ステップ2](../images/steps-slide3_step2.png)",
        ])

    def test_subset_drops_steps_not_exported(self):
        md = "<!-- #steps -->\n![](../images/steps-slide3_step[0-2].png)\n<!-- /steps -->"
        with self.assertLogs(level=logging.WARNING):
            got = self._expand(md, [_img("1-3", self.A)])
        self.assertEqual(got.splitlines()[1:-1], [
            "![](../images/steps-slide3_step1.png)",
            "![](../images/steps-slide3_step2.png)",
        ])

    def test_filename_fallback_when_dirs_differ(self):
        md = "<!-- #steps -->\n![](images/steps-slide3_step[all].png)\n<!-- /steps -->"
        got = self._expand(md, [_img("0-1", self.A)])
        self.assertEqual(got.splitlines()[1:-1], [
            "![](images/steps-slide3_step0.png)",
            "![](images/steps-slide3_step1.png)",
        ])

    def test_unmatched_line_is_kept_with_warning(self):
        md = "<!-- #steps -->\n![](../images/nope_step[all].png)\n<!-- /steps -->"
        with self.assertLogs(level=logging.WARNING):
            got = self._expand(md, [_img("all", self.A)])
        self.assertEqual(got, md)

    def test_outside_section_and_alt_text_untouched(self):
        md = "![1](../images/steps-slide3_step[all].png)\n<!-- #steps -->\n![2](x.png)\n<!-- /steps -->"
        self.assertEqual(self._expand(md, [_img("all", self.A)]), md)

    def test_unclosed_section_is_not_expanded(self):
        md = "<!-- #steps -->\n![](../images/steps-slide3_step[all].png)"
        with self.assertLogs(level=logging.WARNING):
            got = self._expand(md, [_img("all", self.A)])
        self.assertEqual(got, md)

    def test_click_count_not_needed_without_sections(self):
        def boom():
            raise AssertionError("should not count clicks")
        md = "![](../images/steps-slide3_step[all].png)"
        self.assertEqual(expand_steps_sections(md, [_img("all", self.A)], boom, 3), md)


class TestPptmdexportEndToEnd(unittest.TestCase):
    def test_export_expands_steps(self):
        note = textwrap.dedent("""\
            NOTE_CONTENT_FORMAT: 1.0
            ===BLOCK===
            {{BLOCK:IMAGE}}

            export-image-mode: slide
            export-image-step: all
            export-image: ../images/steps-slide<__SLIDENUM__>_step<__STEP__>.png
            ===BLOCK===
            {{BLOCK:IMAGE}}

            export-image-mode: slide
            export-image-step: 1-2
            export-image: ../images/zoom-slide<__SLIDENUM__>_step<__STEP__>.png
            ===BLOCK===
            {{BLOCK:MD:LONG}}

            export-note: ../mds/s<__SLIDENUM__>.md
            ## 手順

            <!-- #steps -->
            ![](../images/steps-slide<__SLIDENUM__>_step[all].png){ width=80% }
            <!-- /steps -->

            <!-- #steps -->
            ![](../images/zoom-slide<__SLIDENUM__>_step[all].png)
            <!-- /steps -->
            """)
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "src").mkdir()
            prs = Presentation()
            _add_slide(prs, "", None)
            _add_slide(prs, note, 2)
            prs.save(str(root / "src" / "deck.pptx"))
            recipe = root / "r_recipe.yaml"
            recipe.write_text("version: 2\nsource:\n  cropsrc:\n    pptx: src/deck.pptx\n", encoding="utf-8")
            env = dict(os.environ, PYTHONPATH=str(_SRC))
            r = subprocess.run(
                [sys.executable, "-m", "md_merge", "pptmdexport", str(recipe), "--force"],
                cwd=root, env=env, capture_output=True, text=True, encoding="utf-8",
                stdin=subprocess.DEVNULL,
            )
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            md = (root / "mds" / "s2.md").read_text(encoding="utf-8")
        self.assertIn(
            "<!-- #steps -->\n"
            "![](../images/steps-slide2_step0.png){ width=80% }\n"
            "![](../images/steps-slide2_step1.png){ width=80% }\n"
            "![](../images/steps-slide2_step2.png){ width=80% }\n"
            "<!-- /steps -->", md)
        self.assertIn(
            "<!-- #steps -->\n"
            "![](../images/zoom-slide2_step1.png)\n"
            "![](../images/zoom-slide2_step2.png)\n"
            "<!-- /steps -->", md)


if __name__ == "__main__":
    unittest.main()
