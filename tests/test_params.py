"""params:（分岐用変数の宣言）と validate の変数・条件・マーカー検査のテスト。

実行: python -m pytest tests/test_params.py
"""

import argparse
import tempfile
import unittest
from pathlib import Path

from md_merge._condblock import DeclaredVars, process_text
from md_merge._params import ParamsError, apply_params, check_params_schema, condition_vars
from md_merge.validate import run as validate_run
from md_merge.validate._lint import Source, lint
from md_merge._procedure import normalize_recipe

PARAMS = {
    "TARGET": {"values": ["PDF", "RECIPRO"], "default": "PDF"},
    "MULTISTEP": {"type": "bool", "default": False},
}


def _recipe(*items, params=PARAMS, vars=None):
    r = {"version": 2, "procedure": list(items)}
    if params is not None:
        r["params"] = {k: dict(v) for k, v in params.items()}
    if vars is not None:
        r["vars"] = dict(vars)
    return r


class TestSchema(unittest.TestCase):
    def test_ok(self):
        self.assertEqual(check_params_schema(PARAMS), [])

    def test_errors(self):
        cases = {
            "unknown key": {"X": {"vals": ["a"]}},
            "bad type": {"X": {"type": "int"}},
            "type and values": {"X": {"type": "bool", "values": ["a"]}},
            "default outside values": {"X": {"values": ["a", "b"], "default": "c"}},
            "yaml bool value": {"X": {"values": [True, False]}},
            "not a mapping": {"X": ["a", "b"]},
            "bad name": {"X-Y": {}},
        }
        for label, params in cases.items():
            with self.subTest(label):
                self.assertTrue(check_params_schema(params))

    def test_yaml_bool_hint(self):
        msg = "".join(check_params_schema({"V": {"values": [True, False]}}))
        self.assertIn("引用符", msg)


class TestApply(unittest.TestCase):
    def test_defaults(self):
        r = apply_params(_recipe())
        self.assertEqual(r["vars"], {"TARGET": "PDF", "MULTISTEP": "false"})

    def test_cli_overrides_and_bool_normalized(self):
        r = apply_params(_recipe(vars={"COVER": "x"}), {"TARGET": "RECIPRO", "MULTISTEP": "yes", "COVER": "y"})
        self.assertEqual(r["vars"], {"COVER": "y", "TARGET": "RECIPRO", "MULTISTEP": "true"})

    def test_cli_undeclared_name(self):
        with self.assertRaisesRegex(ParamsError, "TAGRET"):
            apply_params(_recipe(), {"TAGRET": "RECIPRO"})

    def test_cli_value_outside(self):
        with self.assertRaisesRegex(ParamsError, "RECIPLO"):
            apply_params(_recipe(), {"TARGET": "RECIPLO"})

    def test_bool_value(self):
        with self.assertRaises(ParamsError):
            apply_params(_recipe(), {"MULTISTEP": "maybe"})

    def test_name_in_both(self):
        with self.assertRaisesRegex(ParamsError, "両方"):
            apply_params(_recipe(vars={"TARGET": "PDF"}))

    def test_when_undeclared(self):
        r = _recipe({"insertmd": "a.md", "when": {"var": "TAGRET=RECIPRO"}})
        with self.assertRaisesRegex(ParamsError, "TAGRET"):
            apply_params(r)

    def test_when_value_outside_in_group(self):
        r = _recipe({"group": [{"insertmd": "a.md"}], "when": {"var": "TARGET=RECIPLO"}})
        with self.assertRaisesRegex(ParamsError, r"procedure\[0\]"):
            apply_params(r)

    def test_without_params_unchanged(self):
        r = apply_params({"vars": {"A": "1"}, "procedure": []}, {"B": "2"})
        self.assertEqual(r["vars"], {"A": "1", "B": "2"})
        self.assertNotIsInstance(condition_vars(r), DeclaredVars)


class TestIfBlocks(unittest.TestCase):
    def _cv(self, **cli):
        return condition_vars(apply_params(_recipe(vars={"COVER": "c"}), cli))

    def test_declared(self):
        text = "{{#if:TARGET=RECIPRO}}\nA\n{{#else:TARGET}}\nB\n{{#endif:TARGET}}\n"
        self.assertEqual(process_text(text, self._cv()), "B\n")
        self.assertEqual(process_text(text, self._cv(TARGET="RECIPRO")), "A\n")

    def test_vars_names_are_declared(self):
        self.assertEqual(process_text("{{#if:COVER}}\nA\n{{#endif:COVER}}\n", self._cv()), "A\n")

    def test_undeclared_is_error(self):
        with self.assertRaisesRegex(ValueError, "line 1: 未宣言"):
            process_text("{{#if:TAGRET}}\nA\n{{#endif:TAGRET}}\n", self._cv())

    def test_value_outside_is_error(self):
        with self.assertRaisesRegex(ValueError, "取りうる値"):
            process_text("{{#if:TARGET=RECIPLO}}\nA\n{{#endif:TARGET}}\n", self._cv())

    def test_without_params_undefined_is_false(self):
        self.assertEqual(process_text("{{#if:X}}\nA\n{{#endif:X}}\n", {}), "")


def _lint(recipe, *sources):
    normalized = normalize_recipe(dict(recipe), warn_deprecated=False)
    return lint(recipe, normalized, Path("r.yaml"), None,
                sources=[Source(label, text) for label, text in sources])


class TestLint(unittest.TestCase):
    def test_undefined_without_params_is_warning(self):
        r = _recipe({"insertmd": "a.md", "when": {"var": "TARGET=RECIPRO"}}, params=None)
        res = _lint(r, ("a.md", "{{#if:MULTISTEP}}\nx\n{{#endif:MULTISTEP}}\n{{v:TITLE}}\n"))
        self.assertEqual(res.errors, [])
        joined = "\n".join(res.warnings)
        for name in ("TARGET", "MULTISTEP", "{{v:TITLE}}"):
            self.assertIn(name, joined)

    def test_undefined_if_with_params_is_error(self):
        res = _lint(_recipe(), ("a.md", "{{#if:TAGRET}}\nx\n{{#endif:TAGRET}}\n"))
        self.assertEqual(len(res.errors), 1)
        self.assertIn("a.md line 1", res.errors[0])

    def test_if_value_outside_with_params_is_error(self):
        res = _lint(_recipe(), ("a.md", "{{#if:TARGET=RECIPLO}}\nx\n{{#endif:TARGET}}\n"))
        self.assertTrue(any("取りうる値" in e for e in res.errors))

    def test_fenced_tags_ignored(self):
        res = _lint(_recipe(params=None), ("a.md", "```\n{{#if:X}}\n{{v:Y}}\n```\n"))
        self.assertEqual(res.warnings, [])

    def test_unused_param(self):
        res = _lint(_recipe({"insertmd": "a.md", "when": {"var": "TARGET=PDF"}}))
        self.assertEqual([w for w in res.warnings if "参照されていません" in w][0][:16], "params.MULTISTEP")

    def test_constant_when(self):
        r = _recipe(
            {"insertmd": "a.md", "when": {"var": ["TARGET=PDF", "TARGET=RECIPRO"]}},  # 常に真
            {"insertmd": "b.md", "when": {"var": "MULTISTEP"}},                       # 変わる
            {"group": [{"insertmd": "c.md", "when": {"var": "TARGET=PDF"}}],
             "when": {"var": "TARGET=RECIPRO"}},                                      # 常に偽
        )
        warnings = [w for w in _lint(r).warnings if "when.var" in w]
        self.assertEqual(len(warnings), 2, warnings)
        self.assertIn("常に適用", warnings[0])
        self.assertIn("適用されません", warnings[1])

    def test_if_depth(self):
        text = "".join(f"{{{{#if:{n}}}}}\n" for n in "ABC") + "x\n" + "".join(
            f"{{{{#endif:{n}}}}}\n" for n in "CBA")
        res = _lint(_recipe(params=None, vars={"A": 1, "B": 1, "C": 1}), ("a.md", text))
        self.assertEqual(len([w for w in res.warnings if "入れ子" in w]), 1)

    def test_group_depth(self):
        r = _recipe({"group": [{"group": [{"insertmd": "a.md"}]}]}, params=None)
        self.assertTrue(any("group の入れ子" in w for w in _lint(r).warnings))

    def test_markers(self):
        text = (
            "{{nolabel}}\n## no id\n"
            "{{#id:section:p:a}} {{nolabel}} {{nonum}}\n## both\n"
            "{{#id:section:p:b}} {{noref}}\n## ok\n"
        )
        warnings = _lint(_recipe(params=None), ("a.md", text)).warnings
        self.assertEqual(len(warnings), 2, warnings)
        self.assertIn("line 1", warnings[0])
        self.assertIn("line 3", warnings[1])

    def test_repeated_when_suggestion(self):
        w = {"var": "TARGET=RECIPRO"}
        r = _recipe(
            {"insertmd": "a.md", "when": w}, {"insertvfill": None},
            {"insertmd": "b.md", "when": w}, {"insertmd": "c.md", "when": w},
            {"insertmd": "d.md"},
        )
        info = _lint(r).info
        self.assertEqual(len(info), 1)
        self.assertIn("procedure[0]〜[3]", info[0])


class TestValidateCommand(unittest.TestCase):
    def _run(self, text, **kw):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "r.yaml"
            p.write_text(text, encoding="utf-8")
            args = argparse.Namespace(log_level="ERROR", json=False, strict=True, input=str(p),
                                      yaml=None, subcommand="validate", workdir=None, **kw)
            return validate_run(args)

    def test_params_error_exit_1(self):
        self.assertEqual(self._run(
            "version: 2\nparams:\n  T:\n    values: [a]\n    default: b\nprocedure: []\n"), 1)

    def test_list_params(self):
        self.assertEqual(self._run(
            "version: 2\nparams:\n  T:\n    values: [a, b]\nprocedure: []\n", list_params=True), 0)

    def test_ok(self):
        self.assertEqual(self._run(
            "version: 2\nparams:\n  T:\n    values: [a, b]\n    default: a\n"
            "procedure:\n  - insertmd: x.md\n    when:\n      var: T=b\n"), 0)


if __name__ == "__main__":
    unittest.main()
