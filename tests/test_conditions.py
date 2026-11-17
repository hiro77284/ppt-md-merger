"""procedure の条件付き適用（when:）のテスト。

実行: python -m unittest discover -s tests
"""

import argparse
import unittest

from md_merge._conditions import check_when, check_when_errors, filter_procedure
from md_merge._procedure import ProcedureNotationError


def _args(cmd="merge"):
    return argparse.Namespace(subcommand=cmd)


def _recipe(*items, vars=None):
    r = {"procedure": list(items)}
    if vars is not None:
        r["vars"] = vars
    return r


def _kept(recipe, cmd="merge"):
    return [i["insertmd"] for i in filter_procedure(recipe, _args(cmd))["procedure"]]


class TestWhenVar(unittest.TestCase):
    def test_truthy(self):
        r = _recipe({"insertmd": "a"}, {"insertmd": "b", "when": {"var": "extra"}},
                    vars={"extra": "true"})
        self.assertEqual(_kept(r), ["a", "b"])

    def test_undefined_and_falsy(self):
        for v in ({}, {"extra": "off"}, {"extra": False}, {"extra": ""}):
            r = _recipe({"insertmd": "b", "when": {"var": "extra"}}, vars=v)
            self.assertEqual(_kept(r), [], v)

    def test_negation(self):
        r = _recipe({"insertmd": "b", "when": {"var": "!draft"}})
        self.assertEqual(_kept(r), ["b"])
        r["vars"] = {"draft": "true"}
        self.assertEqual(_kept(r), [])

    def test_compare(self):
        items = ({"insertmd": "p", "when": {"var": "EDITION=print"}},
                 {"insertmd": "w", "when": {"var": "EDITION!=print"}})
        self.assertEqual(_kept(_recipe(*items, vars={"EDITION": "print"})), ["p"])
        self.assertEqual(_kept(_recipe(*items, vars={"EDITION": "web"})), ["w"])
        self.assertEqual(_kept(_recipe(*items)), ["w"])

    def test_list_is_or_and_keys_are_and(self):
        item = {"insertmd": "b", "when": {"var": ["a", "b"], "command": "ppt_to_pdf"}}
        self.assertEqual(_kept(_recipe(item, vars={"b": "1"}), "ppt_to_pdf"), ["b"])
        self.assertEqual(_kept(_recipe(item, vars={"b": "1"}), "merge"), [])
        self.assertEqual(_kept(_recipe(item), "ppt_to_pdf"), [])


class TestRemovedTag(unittest.TestCase):
    def test_tag_is_error(self):
        for key in ("tag", "not_tag"):
            r = _recipe({"insertmd": "b", "when": {key: "x"}})
            self.assertEqual(len(check_when_errors(r)), 1)
            with self.assertRaises(ProcedureNotationError):
                filter_procedure(r, _args())
            # check_when（warning）では二重に報告しない
            self.assertEqual(check_when({key: "x"}), [])

    def test_unknown_key_is_error(self):
        for key in ("VAR", "Var", "vars", "commnad"):
            r = _recipe({"insertmd": "b", "when": {key: "x"}})
            errors = check_when_errors(r)
            self.assertEqual(len(errors), 1, key)
            with self.assertRaises(ProcedureNotationError):
                filter_procedure(r, _args())
            # check_when（warning）では二重に報告しない
            self.assertEqual(check_when({key: "x"}), [])
        self.assertIn("'var'", check_when_errors(_recipe({"insertmd": "b", "when": {"VAR": "x"}}))[0])

    def test_bad_expression_is_error(self):
        for expr in ("a b", "!a=1", "a==1"):
            r = _recipe({"insertmd": "b", "when": {"var": expr}})
            self.assertTrue(check_when_errors(r), expr)


if __name__ == "__main__":
    unittest.main()
