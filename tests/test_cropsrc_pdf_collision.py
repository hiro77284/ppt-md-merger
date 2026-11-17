"""cropsrc のスライド PDF と ppt_to_pdf の成果物 PDF の衝突回避テスト。

pptx の stem と output.targetbasefilename が同じだと、自動生成のスライド PDF
（旧: <outputdir>/<stem>.pdf）が成果物 PDF と同じパスになり、pandoc の出力で
上書きされていた。次回の pptimgexport が成果物 PDF からスライドを切り出そうとして
「PDF にページ N が存在しません」で失敗していた不具合の再現。

実行: python -m unittest discover -s tests
"""

import argparse
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from md_merge._cropsrc import auto_cropsrc_pdf_path, cropsrc_pdf_paths  # noqa: E402
from md_merge._output import EXIT_BAD_INPUT, EXIT_OK  # noqa: E402
from md_merge.merge._recipe import load_yaml, resolve_out_file  # noqa: E402
from md_merge.ppt_to_pdf import _check_pdf_collision  # noqa: E402


def _write(root: Path, cropsrc_pdf: str = "") -> Path:
    recipe = root / "doc.yaml"
    recipe.write_text(textwrap.dedent(f"""\
        version: 2
        output:
          outputdir: build
          targetbasefilename: 強調表示
        input:
          cropsrc:
            - pptx: src/強調表示.pptx
              pdf: {cropsrc_pdf}
        procedure:
          - insertmd: a.md
        """), encoding="utf-8")
    return recipe


class TestCropsrcPdfCollision(unittest.TestCase):
    def test_auto_name_differs_from_output_pdf(self):
        with tempfile.TemporaryDirectory() as d:
            recipe = _write(Path(d))
            r = load_yaml(recipe)
            slide_pdf = cropsrc_pdf_paths(r, recipe, None)[0]
            out_pdf = resolve_out_file(r, "pdffilename", recipe, None)
            self.assertEqual(slide_pdf.name, "強調表示_slides.pdf")
            self.assertNotEqual(slide_pdf.resolve(), out_pdf.resolve())
            self.assertEqual(
                auto_cropsrc_pdf_path("src/強調表示.pptx", r["output"], recipe, None), slide_pdf)

    def test_pipeline_ok_with_auto_name(self):
        with tempfile.TemporaryDirectory() as d:
            recipe = _write(Path(d))
            self.assertEqual(_check_pdf_collision(argparse.Namespace(input=str(recipe), workdir=None)), EXIT_OK)

    def test_pipeline_rejects_explicit_collision(self):
        with tempfile.TemporaryDirectory() as d:
            recipe = _write(Path(d), cropsrc_pdf="build/強調表示.pdf")
            with self.assertLogs(level="ERROR"):
                code = _check_pdf_collision(argparse.Namespace(input=str(recipe), workdir=None))
            self.assertEqual(code, EXIT_BAD_INPUT)


if __name__ == "__main__":
    unittest.main()
