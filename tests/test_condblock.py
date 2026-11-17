"""条件ブロック（{{#if:NAME}} …）と --var のテスト。

実行: python -m unittest discover -s tests
"""

import argparse
import tempfile
import textwrap
import unittest
from pathlib import Path

from md_merge import _condblock
from md_merge._condblock import is_truthy, parse_cli_vars, process_text
from md_merge.merge import _recipe


def run(text: str, vars_map: dict, **kw) -> str:
    return process_text(textwrap.dedent(text), vars_map, **kw)


class TruthyTest(unittest.TestCase):
    def test_values(self):
        for v in (None, False, "", "false", "FALSE", "0", "no", "off", " Off "):
            self.assertFalse(is_truthy(v), v)
        for v in (True, "true", "1", "yes", "x", 0.5, 1):
            self.assertTrue(is_truthy(v), v)


class ProcessTest(unittest.TestCase):
    def test_truthy_and_negation(self):
        src = """\
        a
        {{#if:X}}
        x
        {{#endif:X}}
        {{#if:!X}}
        not x
        {{#endif:X}}
        b
        """
        self.assertEqual(run(src, {"X": "on"}), "a\nx\nb\n")
        self.assertEqual(run(src, {"X": "off"}), "a\nnot x\nb\n")
        self.assertEqual(run(src, {}), "a\nnot x\nb\n")

    def test_compare_and_else(self):
        src = """\
        {{#if:ED=student}}
        S
        {{#else:ED}}
        T
        {{#endif:ED}}
        {{#if:ED!=student}}
        not S
        {{#endif:ED}}
        """
        self.assertEqual(run(src, {"ED": "student"}), "S\n")
        self.assertEqual(run(src, {"ED": "teacher"}), "T\nnot S\n")
        self.assertEqual(run(src, {}), "T\nnot S\n")

    def test_bool_compare(self):
        self.assertEqual(run("{{#if:A=true}}\nY\n{{#endif:A}}\n", {"A": True}), "Y\n")

    def test_nesting(self):
        src = """\
        {{#if:A}}
        a
          {{#if:B}}
        ab
          {{#else:B}}
        a-notb
          {{#endif:B}}
        {{#else:A}}
          {{#if:B}}
        nota-b
          {{#endif:B}}
        {{#endif:A}}
        """
        self.assertEqual(run(src, {"A": 1, "B": 1}), "a\nab\n")
        self.assertEqual(run(src, {"A": 1}), "a\na-notb\n")
        self.assertEqual(run(src, {"B": 1}), "nota-b\n")
        self.assertEqual(run(src, {}), "")

    def test_markdown_fence_is_literal(self):
        src = """\
        ```markdown
        {{#if:X}}
        shown
        {{#endif:X}}
        ```
        """
        self.assertEqual(run(src, {}, markdown=True), textwrap.dedent(src))
        # markdown=False ではフェンス内も処理する
        self.assertEqual(run(src, {}), "```markdown\n```\n")

    def test_fence_inside_false_block_is_dropped(self):
        src = "{{#if:X}}\n```\n{{#endif:X}}\n```\n{{#endif:X}}\nz\n"
        self.assertEqual(run(src, {}, markdown=True), "z\n")

    def test_errors(self):
        bad = [
            "{{#if:A}}\n",
            "{{#endif:A}}\n",
            "{{#if:A}}\n{{#endif:B}}\n",
            "{{#if:A}}\n{{#if:A}}\n{{#endif:A}}\n{{#endif:A}}\n",
            "{{#else:A}}\n",
            "{{#if:A}}\n{{#else:A}}\n{{#else:A}}\n{{#endif:A}}\n",
            "{{#if:A}} trailing\n",
            "{{#if:!A=1}}\n{{#endif:A}}\n",
            # 未定義のタグ（\b 判定をすり抜けて素通りしていた）
            "{{#if:A}}\n{{#elseif:A}}\n{{#endif:A}}\n",
            "{{#if:A}}\n{{#elif:A}}\n{{#endif:A}}\n",
            "{{#if:A}}\n{{#end:A}}\n",
            "{{#ifnot:A}}\n",
            "{{#elseA}}\n",
        ]
        for src in bad:
            with self.assertRaises(ValueError, msg=src):
                process_text(src, {}, where="f.md")

    def test_error_message_has_location(self):
        with self.assertRaisesRegex(ValueError, r"f\.md: line 2"):
            process_text("x\n{{#endif:A}}\n", {}, where="f.md")

    def test_elseif_error_hints_else(self):
        with self.assertRaisesRegex(ValueError, r"line 2: .*#elseif.*未対応"):
            process_text("{{#if:A}}\n{{#elseif:A}}\nx\n{{#endif:A}}\n", {"A": "1"}, where="f.md")

    def test_no_tags_unchanged(self):
        self.assertEqual(process_text("{{#id:image:a:b}}\n", {}), "{{#id:image:a:b}}\n")


class CliVarsTest(unittest.TestCase):
    def tearDown(self):
        _recipe._CLI_VARS.clear()

    def test_parse(self):
        self.assertEqual(parse_cli_vars(["A=1", "B", "C=", "D=x=y"]),
                         {"A": "1", "B": "true", "C": "", "D": "x=y"})
        with self.assertRaises(ValueError):
            parse_cli_vars(["bad-name=1"])

    def test_load_yaml_overrides_vars(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "r.yaml"
            p.write_text("version: 2\nvars:\n  A: recipe\n  B: keep\n", encoding="utf-8")
            _recipe.init_cli_vars({"A": "cli", "C": "new"})
            recipe = _recipe.load_yaml(p)
        self.assertEqual(recipe["vars"], {"A": "cli", "B": "keep", "C": "new"})

    def test_cli_parser_accepts_var(self):
        from md_merge.__main__ import _make_parser
        args = _make_parser().parse_args(["merge", "r.yaml", "--var", "A=1", "--var", "B"])
        self.assertEqual(args.cli_vars, ["A=1", "B"])


class MergeExpandTest(unittest.TestCase):
    def test_expand_md_cuts_include_and_lines(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            (base / "inc.md").write_text("included\n", encoding="utf-8")
            main = base / "main.md"
            main.write_text(
                "top\n{{#if:FULL}}\n!include inc.md\nfull\n{{#endif:FULL}}\nend\n",
                encoding="utf-8",
            )
            off = _recipe.expand_md(main, yaml_dir=base, cond_vars={})
            on = _recipe.expand_md(main, yaml_dir=base, cond_vars={"FULL": "yes"})
            raw = _recipe.expand_md(main, yaml_dir=base)
        self.assertNotIn("included", off)
        self.assertNotIn("full", off)
        self.assertIn("included", on)
        self.assertIn("full\n", on)
        self.assertNotIn("{{#if", on)
        self.assertIn("{{#if:FULL}}", raw)  # cond_vars 無しなら従来どおり素通し


if __name__ == "__main__":
    unittest.main()
