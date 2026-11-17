"""PDF（typst）の表紙の選び方（version 3 で明示だけにし、version 4 で cover-md に改名した）。"""
import unittest

from md_merge._procedure import normalize_recipe
from md_merge._typst_cover import TYPST_DEFAULT_COVER, select_typst_cover
from md_merge.validate import validate_recipe


class TestSelectTypstCover(unittest.TestCase):
    def test_explicit_wins_in_every_version(self):
        for version in (1, 2, 3):
            with self.subTest(version=version):
                self.assertEqual(
                    select_typst_cover({"typst-cover-md": "c.md", "cover-md": "x.md"}, version),
                    ("c.md", False, None),
                )

    def test_no_cover_keys_means_no_cover(self):
        for version in (1, 2, 3):
            with self.subTest(version=version):
                self.assertEqual(select_typst_cover({}, version), (None, False, None))

    def test_v2_latex_cover_implies_bundled_cover_with_warning(self):
        for key in ("cover-md", "conditional-process-input"):
            with self.subTest(key=key):
                cover, builtin, warn = select_typst_cover({key: "x"}, 2)
                self.assertEqual((cover, builtin), (TYPST_DEFAULT_COVER, True))
                self.assertIn("cover-md: cover_standard.md", warn)

    def test_v3_latex_cover_gives_no_cover_with_warning(self):
        cover, builtin, warn = select_typst_cover({"conditional-process-input": "standard_cover.tex"}, 3)
        self.assertEqual((cover, builtin), (None, False))
        self.assertIn("表紙は付きません", warn)

    def test_v4_reads_cover_md(self):
        self.assertEqual(select_typst_cover({"cover-md": "c.md"}, 4), ("c.md", False, None))
        self.assertEqual(select_typst_cover({"typst-cover-md": "c.md"}, 4), (None, False, None))

    def test_v4_has_no_implicit_cover(self):
        self.assertEqual(select_typst_cover({"conditional-process-input": "a.tex"}, 4), (None, False, None))

    def test_empty_latex_key_is_ignored(self):
        self.assertEqual(select_typst_cover({"conditional-process-input": None}, 2), (None, False, None))


class TestValidateTypstCover(unittest.TestCase):
    def _warnings(self, recipe):
        return validate_recipe(normalize_recipe(recipe))

    def test_v2_implicit_cover_warns(self):
        w = self._warnings({"version": 2, "pandoc": {"conditional-process-input": "a.tex"}})
        self.assertTrue(any(TYPST_DEFAULT_COVER in m and "version 2" in m for m in w), w)

    def test_v3_latex_only_cover_warns(self):
        w = self._warnings({"version": 3, "pandoc": {"cover-md": "a.md"}})
        self.assertTrue(any("表紙は付きません" in m for m in w), w)

    def test_explicit_cover_is_silent(self):
        w = self._warnings({"version": 3, "pandoc": {
            "conditional-process-input": "a.tex", "typst-cover-md": TYPST_DEFAULT_COVER}})
        self.assertFalse(any("表紙" in m for m in w), w)

    def test_latex_engine_still_reports_cover(self):
        w = self._warnings({"version": 3, "pandoc": {"engine": "latex", "cover-md": "a.md"}})
        self.assertTrue(any("表紙は付きません" in m for m in w), w)


if __name__ == "__main__":
    unittest.main()
