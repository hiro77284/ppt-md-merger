"""LaTeX（lualatex）経路の撤去（docs/design_typst_migration.md Phase 7）。"""
import argparse
import tempfile
import textwrap
import unittest
from pathlib import Path

from md_merge._conditions import check_when
from md_merge._pandoc_keys import engine_error, removed_latex_keys, removed_latex_keys_warning
from md_merge._procedure import normalize_recipe
from md_merge.pandoc import run as run_pandoc
from md_merge.validate import validate_recipe


class TestEngine(unittest.TestCase):
    def test_typst_or_absent_is_ok(self):
        self.assertIsNone(engine_error({}))
        self.assertIsNone(engine_error({"engine": "typst"}))
        self.assertIsNone(engine_error({"engine": " Typst "}))

    def test_latex_is_error(self):
        self.assertIn("撤去しました", engine_error({"engine": "latex"}))

    def test_pandoc_run_rejects_latex_engine(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "r.yaml"
            p.write_text(textwrap.dedent("""\
                version: 3
                output:
                  targetbasefilename: r
                pandoc:
                  engine: latex
            """), encoding="utf-8")
            args = argparse.Namespace(input=str(p), workdir=None, force=False, dry_run=True,
                                      log_level="WARNING", html=False, reveal=False)
            with self.assertLogs(level="ERROR") as cm:
                self.assertNotEqual(run_pandoc(args), 0)
            self.assertTrue(any("撤去しました" in m for m in cm.output))


class TestRemovedKeys(unittest.TestCase):
    def test_lists_latex_only_keys(self):
        sec = {"template": "t.tex", "include-in-header": ["h.tex"], "conditional-process-input": "c.tex",
               "include-before-body": "b.tex", "resource-path": ["build"]}
        self.assertEqual(removed_latex_keys(sec),
                         ["template", "include-in-header", "include-before-body", "conditional-process-input"])

    def test_latex_defaults_only_when_typstdefaults_given(self):
        self.assertEqual(removed_latex_keys({"defaults": "a.yaml"}), [])
        self.assertEqual(removed_latex_keys({"defaults": "a.yaml", "typstdefaults": "t.yaml"}), ["defaults"])

    def test_warning_text(self):
        self.assertIsNone(removed_latex_keys_warning({}))
        self.assertIn("pandoc.template", removed_latex_keys_warning({"template": "t.tex"}))

    def test_validate_reports_removed_keys(self):
        w = validate_recipe(normalize_recipe({"version": 3, "pandoc": {"template": "t.tex"}}))
        self.assertTrue(any("pandoc.template" in m and "使いません" in m for m in w), w)

    def test_validate_drops_latex_output_keys(self):
        w = validate_recipe(normalize_recipe({"version": 3, "output": {"texfilename": "a.tex"}}))
        self.assertTrue(any("texfilename" in m for m in w), w)


class TestCondblockprocessRemoved(unittest.TestCase):
    def test_when_command_condblockprocess_is_error(self):
        errors = check_when({"command": "condblockprocess"})
        self.assertTrue(any("condblockprocess は廃止しました" in e for e in errors), errors)

    def test_cli_has_no_condblockprocess(self):
        import contextlib
        import io

        from md_merge.__main__ import _make_parser
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            _make_parser().parse_args(["condblockprocess", "x.yaml"])


if __name__ == "__main__":
    unittest.main()
