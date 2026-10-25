"""procedure 記法（version 1 / 2）の検査と正規化のテスト。

実行: python -m unittest discover -s tests
"""

import unittest

from md_merge._procedure import (
    ProcedureNotationError,
    check_procedure_notation,
    normalize_recipe,
    to_notation,
)


def _recipe(version, *items):
    r = {"procedure": list(items)}
    if version is not None:
        r["version"] = version
    return r


class TestVersion2(unittest.TestCase):
    def test_normalize_to_internal_form(self):
        r = normalize_recipe(_recipe(
            2,
            {"insertpptx": "a.pptx", "slides": "2-5", "description": "memo"},
            {"insertmd": "a_slide[1-3]_md.md"},
            {"chapter": "+", "title": "背景", "id": "PART:intro"},
            {"section": 1},
            {"subsection": 2},
            {"insertvspace": "5mm"},
            "beginstay",
            {"endstay": None},
            "insertpagebreak",
            {"insertvfill": None},
        ))
        self.assertEqual(r["procedure"], [
            {"operation": "insertpptx", "pptxfilename": "a.pptx", "slides": "2-5", "description": "memo"},
            {"operation": "insertmd", "mdfilename": "a_slide[1-3]_md.md"},
            {"operation": "chapter", "chapter": "+", "title": "背景", "id": "PART:intro"},
            {"operation": "section", "section": 1},
            {"operation": "subsection", "subsection": 2},
            {"operation": "insertvspace", "lines": "5mm"},
            {"operation": "beginstay"},
            {"operation": "endstay"},
            {"operation": "insertpagebreak"},
            {"operation": "insertvfill"},
        ])

    def test_empty_value_omits_primary_key(self):
        r = normalize_recipe(_recipe(2, {"chapter": None, "title": "おまけ"}))
        self.assertEqual(r["procedure"], [{"operation": "chapter", "title": "おまけ"}])

    def test_when_key_is_kept(self):
        r = normalize_recipe(_recipe(2, {"insertpptx": "a.pptx", "when": {"tags": ["x"]}}))
        self.assertEqual(r["procedure"][0]["when"], {"tags": ["x"]})

    def test_errors(self):
        cases = [
            {"operation": "insertpptx", "pptxfilename": "a.pptx"},  # 旧記法
            {"pptxfilename": "a.pptx"},                            # 操作キーなし
            {"section": 2, "chapter": 1},                          # 操作キーが複数
            {"insertpptx": "a.pptx", "pptxfilename": "b.pptx"},    # 主引数の二重指定
            {"beginstay": True},                                   # 引数なし操作に値
            "insertpptx",                                          # 値が必要な操作を文字列で
            "unknownop",
            {"insertpptx": False},                                 # YAML の no → False
        ]
        for item in cases:
            with self.subTest(item=item):
                self.assertTrue(check_procedure_notation(_recipe(2, item)))
                with self.assertRaises(ProcedureNotationError):
                    normalize_recipe(_recipe(2, item))

    def test_error_lists_every_item(self):
        errs = check_procedure_notation(_recipe(
            2, {"operation": "chapter", "chapter": 1}, {"insertmd": "a.md"}, {"pptxfilename": "x"},
        ))
        self.assertEqual(len(errs), 2)
        self.assertTrue(errs[0].startswith("procedure[0]"))
        self.assertTrue(errs[1].startswith("procedure[2]"))


class TestVersion1(unittest.TestCase):
    def test_legacy_notation_is_accepted(self):
        items = [
            {"operation": "insertpptx", "pptxfilename": "a.pptx"},
            {"operation": "chapter", "chapter": "+", "section": 0},
            {"operation": "section", "section": 1, "chapter": 2},
            {"operation": "beginstay"},
        ]
        for version in (1, None):
            with self.subTest(version=version):
                r = _recipe(version, *items)
                self.assertEqual(check_procedure_notation(r), [])
                self.assertEqual(normalize_recipe(r)["procedure"], items)

    def test_implicit_insertpptx_is_made_explicit(self):
        r = normalize_recipe(_recipe(1, {"pptxfilename": "a.pptx", "slides": "all"}))
        self.assertEqual(r["procedure"], [{"pptxfilename": "a.pptx", "slides": "all", "operation": "insertpptx"}])

    def test_new_notation_is_an_error(self):
        cases = [
            {"insertpptx": "a.pptx"},
            {"chapter": "+"},
            {"operation": "insertpptx", "insertpptx": "a.pptx"},
            {"operation": "subsection", "subsection": 1, "chapter": 1},
            "beginstay",
        ]
        for item in cases:
            with self.subTest(item=item):
                self.assertTrue(check_procedure_notation(_recipe(1, item)))
                with self.assertRaises(ProcedureNotationError):
                    normalize_recipe(_recipe(1, item))


class TestVersionValue(unittest.TestCase):
    def test_unsupported_version(self):
        for version in (3, "2", True):
            with self.subTest(version=version):
                with self.assertRaises(ProcedureNotationError):
                    normalize_recipe(_recipe(version, {"insertpptx": "a.pptx"}))


class TestToNotation(unittest.TestCase):
    def test_round_trip(self):
        internal = [
            {"operation": "insertpptx", "pptxfilename": "a.pptx", "slides": 3, "description": "t"},
            {"operation": "insertmd", "mdfilename": "a.md"},
            {"operation": "beginstay"},
        ]
        v2 = [to_notation(e, 2) for e in internal]
        self.assertEqual(v2[0], {"insertpptx": "a.pptx", "slides": 3, "description": "t"})
        self.assertEqual(v2[2], {"beginstay": None})
        self.assertEqual(normalize_recipe(_recipe(2, *v2))["procedure"], internal)
        self.assertEqual([to_notation(e, 1) for e in internal], internal)


if __name__ == "__main__":
    unittest.main()
