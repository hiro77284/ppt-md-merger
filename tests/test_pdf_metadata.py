"""PDF の文書プロパティ（COVER_* を流用し、defaults の metadata: で上書き）のテスト。

実行: python -m unittest discover -s tests
"""

import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from md_merge._pdf_metadata import collect_metadata, document_properties, typst_document_code

COVER = {
    "COVER_TITLE": "報告書",
    "COVER_SUBTITLE": "副題",
    "COVER_AUTHOR": "山田太郎",
    "COVER_DATE": "2026年1月1日",
}


class TestDocumentProperties(unittest.TestCase):
    def test_cover_vars_are_used(self):
        p = document_properties(COVER, {})
        self.assertEqual(p, {"title": "報告書", "author": ["山田太郎"], "subject": "副題"})

    def test_cover_linebreaks_become_spaces(self):
        cases = {
            "一行目{{br}}二行目": "一行目 二行目",
            "一行目{{BR}}二行目": "一行目 二行目",
            "一行目{{ Br }}二行目": "一行目 二行目",
            "一行目\\\n二行目": "一行目 二行目",
            "一行目\\\r\n二行目{{br}}": "一行目 二行目",
            "パス C:\\dir": "パス C:\\dir",  # 行末でない \ は残す
        }
        for src, want in cases.items():
            with self.subTest(src=src):
                p = document_properties({"COVER_SUBTITLE": src, "COVER_TITLE": src}, {})
                self.assertEqual(p["subject"], want)
                self.assertEqual(p["title"], want)

    def test_cover_date_is_not_used(self):
        code = typst_document_code(document_properties(COVER, {}))
        self.assertNotIn("date", code)
        self.assertNotIn("2026", code)

    def test_metadata_overrides(self):
        p = document_properties(COVER, {"title": "別名", "author": ["A", "B"], "keywords": "k1", "lang": "en"})
        self.assertEqual(p["title"], "別名")
        self.assertEqual(p["author"], ["A", "B"])
        self.assertEqual(p["subject"], "副題")
        self.assertEqual(p["keywords"], ["k1"])
        self.assertEqual(p["lang"], "en")

    def test_empty_metadata_value_clears(self):
        p = document_properties(COVER, {"subject": ""})
        self.assertNotIn("subject", p)

    def test_no_keywords_or_lang_from_vars(self):
        p = document_properties({"COVER_KEYWORDS": "x", "COVER_LANG": "en"}, {})
        self.assertEqual(p, {})

    def test_typst_code(self):
        code = typst_document_code({
            "title": 'a "b" \\c', "author": ["山田"], "subject": "s", "keywords": ["k1", "k2"], "lang": "en-US",
        })
        self.assertEqual(code.splitlines(), [
            '#set document(title: "a \\"b\\" \\\\c", author: ("山田",), description: "s", keywords: ("k1", "k2"))',
            '#set text(lang: "en", region: "us")',
        ])

    def test_bad_lang_is_ignored(self):
        with self.assertLogs(level="WARNING"):
            self.assertEqual(typst_document_code({"lang": "Japanese"}), "")

    def test_nothing(self):
        self.assertEqual(typst_document_code({}), "")


class TestCollectMetadata(unittest.TestCase):
    def test_order(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "mf.yaml").write_text("title: MF\nkeywords: [m]\n", encoding="utf-8")
            (d / "a.yaml").write_text("metadata:\n  title: A\n  lang: ja\n", encoding="utf-8")
            (d / "b.yaml").write_text("metadata:\n  lang: en\n", encoding="utf-8")
            m = collect_metadata([d / "a.yaml", d / "b.yaml"], d / "mf.yaml")
            self.assertEqual(m, {"title": "A", "keywords": ["m"], "lang": "en"})


@unittest.skipIf(shutil.which("pandoc") is None, "pandoc not installed")
class TestPandocTyp(unittest.TestCase):
    """pandoc サブコマンドが .typ に文書プロパティを書くこと（typst compile は差し替える）。"""

    def _run(self, extra_defaults: str | None):
        from md_merge import pandoc as pandoc_mod
        from md_merge.__main__ import _make_parser

        d = Path(self._tmp.name)
        (d / "rendered.md").write_text("# 見出し\n\n本文\n", encoding="utf-8")
        defaults = "[report_base_defaults.yaml" + (", over.yaml]" if extra_defaults else "]")
        if extra_defaults:
            (d / "over.yaml").write_text(extra_defaults, encoding="utf-8")
        (d / "r.yaml").write_text(
            "version: 4\n"
            "vars:\n  COVER_TITLE: 報告書\n  COVER_AUTHOR: 山田太郎\n  COVER_SUBTITLE: 副題\n  COVER_DATE: 昔\n"
            "output:\n  renderedfilename: rendered.md\n  pdffilename: out.pdf\n"
            f"pandoc:\n  defaults: {defaults}\n",
            encoding="utf-8",
        )
        args = _make_parser().parse_args(["pandoc", str(d / "r.yaml"), "--force"])
        real_which = shutil.which
        with mock.patch.object(pandoc_mod.shutil, "which", side_effect=lambda n: "/x/typst" if n == "typst" else real_which(n)), \
                mock.patch.object(pandoc_mod, "_compile_typst", return_value=0):
            self.assertEqual(pandoc_mod.run(args), 0)
        self.assertEqual(list(d.glob(".sem_document_*")), [])
        return (d / "out.typ").read_text(encoding="utf-8")

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self._tmp.cleanup()

    def test_cover_vars(self):
        typ = self._run(None)
        self.assertIn('#set document(title: "報告書", author: ("山田太郎",), description: "副題")', typ)
        self.assertIn('#set text(lang: "ja")', typ)
        self.assertNotIn("昔", typ)

    def test_metadata_override(self):
        typ = self._run("metadata:\n  title: 別のタイトル\n  keywords: [a, b]\n  lang: en\n")
        self.assertIn('title: "別のタイトル"', typ)
        self.assertIn('keywords: ("a", "b")', typ)
        self.assertIn('#set text(lang: "en")', typ)
        # 言語の指定は report_style.typ（lang: "ja"）より後ろに来る
        self.assertGreater(typ.index('#set text(lang: "en")'), typ.index('lang: "ja"'))


if __name__ == "__main__":
    unittest.main()
