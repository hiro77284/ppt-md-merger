"""置換抑制範囲 {{noref:begin}} … {{noref:end}} のテスト。

実行: python -m unittest discover -s tests
"""

import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

from pptx import Presentation

from md_merge._filters import replace_slide_placeholders
from md_merge._inventory import extract_entries
from md_merge._noref import MARKER, PLAIN, PROTECTED, apply_outside_noref, classify_lines
from md_merge._procedure import normalize_recipe
from md_merge._render import build_resolved_map, render_content
from md_merge._resolve import expand_title_label_refs, resolve_entries
from md_merge.pptmerge._merger import _replace_note_placeholders
from md_merge.validate._lint import Source, lint

_SRC = Path(__file__).resolve().parents[1] / "src"

_MD = """\
{{#id:chapter:p:c}}
# 章 {{v:NAME}}

前 {{v:NAME}} / {{num:chapter:p:c}}

{{noref:begin}}
記法例: {{v:NAME}} / {{num:chapter:p:c}} / {{sectionlist}}

{{#id:section:p:s}}
## 節 {{v:NAME}}
{{noref:end}}

後 {{v:NAME}} / {{label:section:p:s}}
"""


def _render(md: str) -> str:
    base = Path("/tmp")
    entries = extract_entries(md, base / "merged.md", base)
    resolve_entries(entries, ".", ") ")
    expand_title_label_refs(entries, ") ")
    return render_content(md, build_resolved_map({"entries": entries}), {"NAME": "値"})


class ClassifyTest(unittest.TestCase):
    def test_kinds(self):
        lines = ["a", "{{noref:begin}}", "b", "  {{noref:end}}  ", "c"]
        self.assertEqual(classify_lines(lines), [PLAIN, MARKER, PROTECTED, MARKER, PLAIN])

    def test_marker_must_be_alone_on_line(self):
        self.assertEqual(classify_lines(["x {{noref:begin}}", "y"]), [PLAIN, PLAIN])

    def test_fenced_marker_ignored(self):
        lines = ["```", "{{noref:begin}}", "```", "z"]
        self.assertEqual(classify_lines(lines), [PLAIN] * 4)

    def test_fence_inside_range(self):
        lines = ["{{noref:begin}}", "```", "{{noref:end}}", "```", "{{noref:end}}", "z"]
        self.assertEqual(
            classify_lines(lines),
            [MARKER, PROTECTED, PROTECTED, PROTECTED, MARKER, PLAIN],
        )

    def test_unclosed_and_stray(self):
        with self.assertLogs(level="WARNING") as cm:
            kinds = classify_lines(["{{noref:end}}", "a", "{{noref:begin}}", "b"])
        self.assertEqual(kinds, [MARKER, PLAIN, MARKER, PROTECTED])
        self.assertEqual(len(cm.output), 2)


class ApplyOutsideTest(unittest.TestCase):
    def test_only_outside_replaced(self):
        text = "<__TITLE__>\n{{noref:begin}}\n<__TITLE__>\n{{noref:end}}\n<__TITLE__>"
        out = apply_outside_noref(
            text, lambda t: replace_slide_placeholders(t, Path("deck.pptx"), "T", 3)
        )
        self.assertEqual(out, "T\n{{noref:begin}}\n<__TITLE__>\n{{noref:end}}\nT")

    def test_no_marker_is_identity_of_fn(self):
        self.assertEqual(apply_outside_noref("a{{v:X}}", lambda t: t.upper()), "A{{V:X}}")

    def test_pptmerge_notes(self):
        info = {"basefilename": "deck", "filename": "deck.pptx", "slidenum": "2",
                "title": "T", "vars": {"X": "1"}, "composedslidenum": 5}
        text = "{{v:X}} <__SLIDENUM__>\n{{noref:begin}}\n{{v:X}} <__SLIDENUM__>\n{{noref:end}}"
        out = apply_outside_noref(text, lambda t: _replace_note_placeholders(t, info, None))
        self.assertEqual(out, "1 2\n{{noref:begin}}\n{{v:X}} <__SLIDENUM__>\n{{noref:end}}")


class RenderTest(unittest.TestCase):
    def setUp(self):
        self.out = _render(_MD)

    def test_markers_removed(self):
        self.assertNotIn("{{noref:", self.out)

    def test_outside_replaced(self):
        self.assertIn("前 値 / 1", self.out)
        self.assertIn("後 値 / 1.1) 節 値", self.out)

    def test_inside_kept(self):
        self.assertIn("記法例: {{v:NAME}} / {{num:chapter:p:c}} / {{sectionlist}}", self.out)

    def test_id_inside_range_labelled_without_substitution(self):
        # {{#id:}} は HTML コメント化、見出しは番号付け（{{noref}} 相当でラベルの var は未置換のまま）
        self.assertIn("<!-- #id:section:p:s -->", self.out)
        self.assertIn("## 1.1) 節 {{v:NAME}}", self.out)


def _lint(text: str):
    recipe = {"version": 2, "procedure": [{"insertmd": "a.md"}]}
    normalized = normalize_recipe(dict(recipe), warn_deprecated=False)
    return lint(recipe, normalized, Path("r.yaml"), None, sources=[Source("a.md", text)])


class LintTest(unittest.TestCase):
    def test_undefined_var_inside_range_not_reported(self):
        res = _lint("{{noref:begin}}\n{{v:UNDEF}}\n{{noref:end}}\n")
        self.assertEqual(res.warnings, [])

    def test_undefined_var_outside_range_reported(self):
        res = _lint("{{noref:begin}}\n{{noref:end}}\n{{v:UNDEF}}\n")
        self.assertTrue(any("UNDEF" in w for w in res.warnings))

    def test_unbalanced_markers(self):
        res = _lint("{{noref:end}}\n{{noref:begin}}\nx\n")
        joined = "\n".join(res.warnings)
        self.assertIn("a.md line 1", joined)
        self.assertIn("閉じていません", joined)


class PptmdexportEndToEndTest(unittest.TestCase):
    def test_placeholders_kept_inside_range(self):
        note = textwrap.dedent("""\
            NOTE_CONTENT_FORMAT: 1.0
            ===BLOCK===
            {{BLOCK:MD:LONG}}

            export-note: ../mds/s<__SLIDENUM__>.md
            外 <__SLIDENUM__> {{v:X}}
            {{noref:begin}}
            内 <__SLIDENUM__> {{v:X}}
            {{noref:end}}
            """)
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "src").mkdir()
            prs = Presentation()
            slide = prs.slides.add_slide(prs.slide_layouts[6])
            slide.notes_slide.notes_text_frame.text = note
            prs.save(str(root / "src" / "deck.pptx"))
            recipe = root / "r_recipe.yaml"
            recipe.write_text(
                "version: 2\nvars:\n  X: v\nsource:\n  cropsrc:\n    pptx: src/deck.pptx\n",
                encoding="utf-8",
            )
            env = dict(os.environ, PYTHONPATH=str(_SRC))
            r = subprocess.run(
                [sys.executable, "-m", "md_merge", "pptmdexport", str(recipe), "--force"],
                cwd=root, env=env, capture_output=True, text=True, encoding="utf-8",
                stdin=subprocess.DEVNULL,
            )
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            md = (root / "mds" / "s1.md").read_text(encoding="utf-8")
        # pptmdexport はプレースホルダーのみ置換（{{v:}} は render 段）。マーカーは残す。
        self.assertIn("外 1 {{v:X}}\n{{noref:begin}}\n内 <__SLIDENUM__> {{v:X}}\n{{noref:end}}", md)


if __name__ == "__main__":
    unittest.main()
