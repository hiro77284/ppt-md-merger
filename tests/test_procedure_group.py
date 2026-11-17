"""procedure の group（複数項目への when: の一括適用）のテスト。

実行: python -m unittest discover -s tests
"""

import argparse
import tempfile
import unittest
from pathlib import Path

from md_merge._conditions import check_when_errors, filter_procedure
from md_merge._procedure import (
    INHERITED_WHEN_KEY,
    ProcedureNotationError,
    check_procedure_notation,
    normalize_recipe,
)
from md_merge.validate import check_group_when, validate_recipe
from md_merge.validate import run as validate_run


def _recipe(*items, version=2, vars=None):
    r = {"version": version, "procedure": list(items)}
    if vars is not None:
        r["vars"] = vars
    return r


def _kept(recipe, cmd="merge"):
    """正規化 → 条件適用後の (operation, 主引数) 一覧。"""
    procedure = filter_procedure(normalize_recipe(recipe), argparse.Namespace(subcommand=cmd))["procedure"]
    out = []
    for item in procedure:
        assert INHERITED_WHEN_KEY not in item, item
        op = item["operation"]
        out.append(item.get({"insertmd": "mdfilename", "insertpptx": "pptxfilename"}.get(op, ""), op))
    return out


ANSWERS = {
    "group": [
        {"insertmd": "q2.md"},
        {"insertvspace": 2},
        {"insertmd": "q3.md"},
        "insertvfill",
    ],
    "when": {"var": "TARGET!=RECIPRO"},
}


class TestGroupFlatten(unittest.TestCase):
    def test_flattened_in_place(self):
        r = normalize_recipe(_recipe({"insertmd": "a.md"}, ANSWERS, {"insertmd": "z.md"}))
        ops = [i["operation"] for i in r["procedure"]]
        self.assertEqual(ops, ["insertmd", "insertmd", "insertvspace", "insertmd", "insertvfill", "insertmd"])
        self.assertNotIn(INHERITED_WHEN_KEY, r["procedure"][0])
        self.assertEqual(r["procedure"][2][INHERITED_WHEN_KEY], [("procedure[1]", {"var": "TARGET!=RECIPRO"})])
        self.assertNotIn("group", r["procedure"][1])

    def test_group_without_when_is_plain_bundle(self):
        r = normalize_recipe(_recipe({"group": [{"insertmd": "a.md"}], "description": "見出し"}))
        self.assertEqual(r["procedure"], [{"operation": "insertmd", "mdfilename": "a.md"}])

    def test_nested_groups_accumulate(self):
        r = normalize_recipe(_recipe({
            "group": [{"group": [{"insertmd": "a.md"}], "when": {"var": "B"}}],
            "when": {"var": "A"},
        }))
        self.assertEqual(r["procedure"][0][INHERITED_WHEN_KEY], [
            ("procedure[0]", {"var": "A"}),
            ("procedure[0].group[0]", {"var": "B"}),
        ])


class TestGroupWhen(unittest.TestCase):
    def test_whole_group_toggles(self):
        r = _recipe({"insertmd": "a.md"}, ANSWERS, vars={"TARGET": "RECIPRO"})
        self.assertEqual(_kept(r), ["a.md"])
        r["vars"] = {"TARGET": "OTHER"}
        self.assertEqual(_kept(r), ["a.md", "q2.md", "insertvspace", "q3.md", "insertvfill"])

    def test_item_when_is_anded(self):
        r = _recipe({
            "group": [{"insertmd": "a.md"}, {"insertmd": "b.md", "when": {"command": "ppt_to_pdf"}}],
            "when": {"var": "X"},
        }, vars={"X": "1"})
        self.assertEqual(_kept(r, "ppt_to_pdf"), ["a.md", "b.md"])
        self.assertEqual(_kept(r, "merge"), ["a.md"])
        r["vars"] = {}
        self.assertEqual(_kept(r, "ppt_to_pdf"), [])

    def test_nested_all_must_match(self):
        r = _recipe({
            "group": [{"group": [{"insertmd": "a.md"}], "when": {"var": "B"}}, {"insertmd": "c.md"}],
            "when": {"var": "A"},
        })
        for vars, expected in (({"A": 1, "B": 1}, ["a.md", "c.md"]), ({"A": 1}, ["c.md"]), ({"B": 1}, [])):
            r["vars"] = vars
            self.assertEqual(_kept(r), expected, vars)

    def test_bad_group_condition_is_error_once(self):
        r = normalize_recipe(_recipe({"group": [{"insertmd": "a.md"}, {"insertmd": "b.md"}], "when": {"var": "a b"}}))
        errors = check_when_errors(r)
        self.assertEqual(len(errors), 1)
        self.assertTrue(errors[0].startswith("procedure[0]:"), errors)
        with self.assertRaises(ProcedureNotationError):
            filter_procedure(r, argparse.Namespace(subcommand="merge"))

    def test_raw_recipe_errors_point_into_group(self):
        r = _recipe({"group": [{"insertmd": "a.md", "when": {"tag": "x"}}], "when": {"not_tag": "y"}})
        errors = check_when_errors(r)
        self.assertEqual([e.split(":")[0] for e in errors], ["procedure[0]", "procedure[0].group[0]"])


class TestGroupNotation(unittest.TestCase):
    def test_errors(self):
        cases = [
            ({"group": []}, "リスト"),
            ({"group": None}, "リスト"),
            ({"group": [{"insertmd": "a"}], "insertmd": "b"}, "同じ要素"),
            ({"group": [{"insertmd": "a"}], "slides": "all"}, "書けないキー"),
        ]
        for item, needle in cases:
            errors = check_procedure_notation(_recipe(item))
            self.assertTrue(errors and needle in errors[0], (item, errors))
            with self.assertRaises(ProcedureNotationError):
                normalize_recipe(_recipe(item))

    def test_child_errors_have_path(self):
        errors = check_procedure_notation(_recipe({"insertmd": "a"}, {"group": [{"insertmd": "a"}, {"operation": "insertmd"}]}))
        self.assertEqual(len(errors), 1)
        self.assertTrue(errors[0].startswith("procedure[1].group[1]:"), errors)

    def test_v1_is_error(self):
        errors = check_procedure_notation(_recipe({"group": [{"operation": "insertmd"}]}, version=1))
        self.assertTrue(errors and "version 2" in errors[0], errors)


class TestGroupValidate(unittest.TestCase):
    def test_group_when_warnings(self):
        raw = _recipe({"group": [{"group": [{"insertmd": "a"}], "when": {"commnad": "x"}}], "when": {"command": "nosuch"}})
        warnings = check_group_when(raw["procedure"])
        self.assertEqual(len(warnings), 2, warnings)
        self.assertTrue(warnings[0].startswith("procedure[0](group):"))
        self.assertTrue(warnings[1].startswith("procedure[0].group[0](group):"))

    def test_flattened_items_have_no_unknown_key_warning(self):
        r = normalize_recipe(_recipe(ANSWERS))
        self.assertEqual([w for w in validate_recipe(r) if "procedure" in w], [])

    def test_validate_command(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "r.yaml"
            p.write_text(
                "version: 2\nparams:\n  TARGET:\n    values: [PDF, RECIPRO]\n    default: PDF\n"
                "procedure:\n"
                "  - group:\n      - insertmd: a.md\n      - insertvfill\n"
                "    when:\n      var: TARGET!=RECIPRO\n",
                encoding="utf-8",
            )
            args = argparse.Namespace(log_level="ERROR", json=False, strict=True,
                                      input=str(p), yaml=None, subcommand="validate")
            self.assertEqual(validate_run(args), 0)


if __name__ == "__main__":
    unittest.main()
