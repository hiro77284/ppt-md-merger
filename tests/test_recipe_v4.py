"""recipe version 4（LaTeX 撤去後の pandoc キー）と tools/convert_recipe_v4.py。"""
import argparse
import importlib.util
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

from md_merge._pandoc_keys import deprecated_keys_warning, pandoc_key_errors, pdf_cover_key, pdf_defaults_key
from md_merge.validate import run as run_validate

_TOOL = Path(__file__).resolve().parents[1] / "tools" / "convert_recipe_v4.py"
_spec = importlib.util.spec_from_file_location("convert_recipe_v4", _TOOL)
convert_recipe_v4 = importlib.util.module_from_spec(_spec)
sys.modules["convert_recipe_v4"] = convert_recipe_v4  # dataclass が自分のモジュールを引くため
_spec.loader.exec_module(convert_recipe_v4)


class TestKeys(unittest.TestCase):
    def test_key_names_by_version(self):
        self.assertEqual((pdf_cover_key(3), pdf_defaults_key(3)), ("typst-cover-md", "typstdefaults"))
        self.assertEqual((pdf_cover_key(4), pdf_defaults_key(4)), ("cover-md", "defaults"))

    def test_v4_removed_keys_are_errors(self):
        errors = pandoc_key_errors({"typst-cover-md": "c.md", "typstdefaults": "t.yaml", "template": "t.tex"}, 4)
        self.assertTrue(any("cover-md に改名" in e for e in errors), errors)
        self.assertTrue(any("pandoc.defaults に改名" in e for e in errors), errors)
        self.assertTrue(any("pandoc.template は廃止" in e for e in errors), errors)
        self.assertTrue(any("convert_recipe_v4" in e for e in errors), errors)

    def test_v4_plain_keys_are_ok(self):
        self.assertEqual(pandoc_key_errors({"cover-md": "c.md", "defaults": ["a.yaml"], "htmlcover": "h.html"}, 4), [])

    def test_v3_keeps_old_keys(self):
        self.assertEqual(pandoc_key_errors({"typst-cover-md": "c.md", "template": "t.tex"}, 3), [])

    def test_renamed_builtin_cover(self):
        # 改名前の同梱表紙の名前はどの version でもエラー（新しい名前を案内する）
        for section, version in (
            ({"cover-md": "cover_standard_typst.md"}, 4),
            ({"cover-md": "sub/cover_standard_typst.md"}, 4),
            ({"typst-cover-md": "cover_standard_typst.md"}, 3),
            ({"typst-cover-md": "cover_standard_typst.md"}, 2),
        ):
            errors = pandoc_key_errors(section, version)
            self.assertEqual(len(errors), 1, (section, version))
            self.assertIn("cover_standard.md", errors[0])
        self.assertEqual(pandoc_key_errors({"cover-md": "cover_standard.md"}, 4), [])
        # version 3 以前の cover-md は LaTeX 用の意味なので対象外
        self.assertEqual(pandoc_key_errors({"cover-md": "cover_standard_typst.md"}, 3), [])

    def test_metadata_file(self):
        self.assertTrue(any("metadata-file は廃止" in e for e in pandoc_key_errors({"metadata-file": "m.yaml"}, 4)))
        self.assertEqual(pandoc_key_errors({"metadata-file": "m.yaml"}, 3), [])
        self.assertIn("非推奨", deprecated_keys_warning({"metadata-file": "m.yaml"}, 3))
        self.assertIsNone(deprecated_keys_warning({"metadata-file": "m.yaml"}, 4))
        self.assertIsNone(deprecated_keys_warning({}, 3))

    def test_renamed_builtin_defaults(self):
        # 改名前の同梱 defaults 名はどの version でもエラー（新しい名前を案内する）
        for section, version in (
            ({"defaults": ["typst_semantic_engine.yaml", "over.yaml"]}, 4),
            ({"defaults": "sub/typst_semantic_engine.yaml"}, 4),
            ({"typstdefaults": ["typst_semantic_engine.yaml"]}, 3),
            ({"typstdefaults": "typst_semantic_engine.yaml"}, 2),
        ):
            errors = pandoc_key_errors(section, version)
            self.assertEqual(len(errors), 1, (section, version))
            self.assertIn("report_base_defaults.yaml", errors[0])
        self.assertEqual(pandoc_key_errors({"defaults": ["report_base_defaults.yaml", "over.yaml"]}, 4), [])
        # version 3 以前の defaults は LaTeX 用の意味（PDF では読まない）なので対象外
        self.assertEqual(pandoc_key_errors({"defaults": "typst_semantic_engine.yaml"}, 3), [])


class _TmpDir(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def write(self, name: str, text: str) -> Path:
        p = self.dir / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(textwrap.dedent(text), encoding="utf-8")
        return p

    def validate(self, path: Path) -> int:
        args = argparse.Namespace(input=str(path), workdir=None, log_level="CRITICAL", json=False,
                                  strict=False, list_params=False, dry_run=False)
        return run_validate(args)


class TestValidateV4(_TmpDir):
    def test_old_key_in_v4_fails(self):
        p = self.write("r.yaml", """\
            version: 4
            pandoc:
              typst-cover-md: cover_standard.md
        """)
        self.assertNotEqual(self.validate(p), 0)

    def test_plain_keys_pass(self):
        p = self.write("r.yaml", """\
            version: 4
            pandoc:
              cover-md: cover_standard.md
        """)
        self.assertEqual(self.validate(p), 0)


    def test_old_builtin_cover_name_fails(self):
        p = self.write("r.yaml", """\
            version: 4
            pandoc:
              cover-md: cover_standard_typst.md
        """)
        self.assertNotEqual(self.validate(p), 0)

    def test_old_builtin_defaults_name_fails(self):
        p = self.write("r.yaml", """\
            version: 4
            pandoc:
              defaults:
                - typst_semantic_engine.yaml
        """)
        self.assertNotEqual(self.validate(p), 0)


class TestConvert(_TmpDir):
    def convert(self, *names: str, **kw) -> int:
        argv = [str(self.dir / n) for n in names] + ["--no-backup"]
        if kw.get("with_includers"):
            argv.append("--with-includers")
        return convert_recipe_v4.main(argv)

    def test_renames_and_deletes(self):
        p = self.write("r.yaml", """\
            version: 3  # 版
            output:
              pdffilename: a.pdf
              texfilename:           # tex
              resourcepathfilename:
            pandoc:
              engine: typst
              defaults: defaults/report.yaml   # LaTeX
              template: templates/report_template.tex
              include-in-header:
                - templates/report_header.tex
              typstdefaults:
                - typst_semantic_engine.yaml
              typst-cover-md: cover_standard_typst.md
              conditional-process-input: standard_cover.tex
              conditional-process-output:
              # include-before-body: x.tex
              resource-path:
                - build
            vars:
              A: 1
        """)
        self.assertEqual(self.convert("r.yaml"), 0)
        self.assertEqual(p.read_text(encoding="utf-8"), textwrap.dedent("""\
            version: 4  # 版
            output:
              pdffilename: a.pdf
            pandoc:
              defaults:
                - report_base_defaults.yaml
              cover-md: cover_standard.md
              # include-before-body: x.tex
              resource-path:
                - build
            vars:
              A: 1
        """))

    def test_metadata_file_is_dropped_with_notice(self):
        p = self.write("r.yaml", """\
            version: 3
            pandoc:
              metadata-file: meta.yaml  # メタ
              typst-cover-md: c.md
        """)
        import contextlib
        import io
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(self.convert("r.yaml"), 0)
        self.assertEqual(p.read_text(encoding="utf-8"), "version: 4\npandoc:\n  cover-md: c.md\n")
        self.assertIn("要手作業: metadata-file（meta.yaml）", out.getvalue())

    def test_v2_implicit_cover_is_made_explicit(self):
        p = self.write("r.yaml", """\
            version: 2
            pandoc:
              cover-md: ../common_assets/cover_type1.md
              resource-path: [build]
        """)
        self.assertEqual(self.convert("r.yaml"), 0)
        text = p.read_text(encoding="utf-8")
        self.assertIn("cover-md: cover_standard.md", text)
        self.assertNotIn("cover_type1.md", text)
        self.assertIn("version: 4", text)

    def test_v3_latex_cover_is_dropped_without_cover(self):
        p = self.write("r.yaml", """\
            version: 3
            pandoc:
              cover-md: ../common_assets/cover_type1.md
        """)
        self.assertEqual(self.convert("r.yaml"), 0)
        self.assertNotIn("cover-md", p.read_text(encoding="utf-8"))

    def test_shared_settings_need_all_includers(self):
        s = self.write("settings.yaml", """\
            defaults: defaults/report.yaml
            cover-md: ../common_assets/cover_type1.md
            htmlcover: standard_cover.html
        """)
        self.write("a/r1.yaml", """\
            version: 2
            pandoc:
              _include: ../settings.yaml
              typst-cover-md: c.md
        """)
        r2 = self.write("b/r2.yaml", """\
            version: 2
            pandoc:
              _include: ../settings.yaml
        """)
        before = s.read_text(encoding="utf-8")
        self.assertEqual(self.convert("a/r1.yaml"), 1)
        self.assertEqual(s.read_text(encoding="utf-8"), before)
        self.assertEqual(self.convert("a/r1.yaml", with_includers=True), 0)
        self.assertEqual(s.read_text(encoding="utf-8"), "htmlcover: standard_cover.html\n")
        # r2 は共有設定の LaTeX 表紙で暗黙の標準表紙が付いていたので、レシピに明示する
        self.assertIn("cover-md: cover_standard.md", r2.read_text(encoding="utf-8"))

    def test_rerun_does_not_touch_converted_settings(self):
        s = self.write("settings.yaml", """\
            cover-md: cover_standard.md
        """)
        self.write("a/r1.yaml", """\
            version: 4
            pandoc:
              _include: ../settings.yaml
        """)
        self.assertEqual(self.convert("a/r1.yaml"), 0)
        self.assertEqual(s.read_text(encoding="utf-8"), "cover-md: cover_standard.md\n")
        r2 = self.write("b/r2.yaml", """\
            version: 3
            pandoc:
              _include: ../settings.yaml
        """)
        before = r2.read_text(encoding="utf-8")
        self.assertEqual(self.convert("b/r2.yaml"), 1)
        self.assertEqual(r2.read_text(encoding="utf-8"), before)
        self.assertEqual(s.read_text(encoding="utf-8"), "cover-md: cover_standard.md\n")

    def test_version1_is_refused(self):
        self.write("r.yaml", """\
            version: 1
            pandoc:
              template: t.tex
        """)
        self.assertEqual(self.convert("r.yaml"), 1)


if __name__ == "__main__":
    unittest.main()
