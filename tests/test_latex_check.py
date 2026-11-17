"""pptmdexport latex_check（フェンスなし LaTeX コマンド検出）のテスト。

実行: python -m pytest tests/test_latex_check.py
"""

import unittest

from md_merge.pptmdexport import _find_bare_latex


class FindBareLatexTest(unittest.TestCase):
    def test_detects_bare_commands(self):
        md = "本文\\hspace*{4em}です\n\n{\\bfseries 太字}\n\\vspace{5mm}\n"
        self.assertEqual(
            _find_bare_latex(md),
            [(1, "\\hspace"), (3, "\\bfseries"), (4, "\\vspace")],
        )

    def test_fenced_code_block_skipped(self):
        md = (
            "説明\n\n"
            "```bash\n"
            "pptmdmerge pptmerge PROJECT_ROOT\\examples\\pm1_recipe.yaml --force\n"
            "\\hspace{1em}\n"
            "```\n"
        )
        self.assertEqual(_find_bare_latex(md), [])

    def test_inline_code_skipped(self):
        self.assertEqual(_find_bare_latex("`\\vspace{5mm}` と書く\n"), [])

    def test_windows_paths_skipped(self):
        # 2026-11: 本文のパス表記（データフォルダ: PROJECT_ROOT\examples\pm1_...）が
        # \examples \pm として誤検出されていた。
        md = (
            "データフォルダ:  PROJECT_ROOT\\examples\\pm1_simple_ppt_merge\n"
            "C:\\Users\\hiro\\docs と ..\\images\\fig.png と ~\\work\n"
            "D:\\work\\project\\new_md_merge\n"
        )
        self.assertEqual(_find_bare_latex(md), [])

    def test_command_after_japanese_or_space_still_detected(self):
        md = "文字\\hspace{1em}あと \\textbf{x}\n"
        self.assertEqual(
            _find_bare_latex(md), [(1, "\\hspace"), (1, "\\textbf")],
        )

    def test_attribute_group_skipped(self):
        md = '::: {.widequote width="0.6\\linewidth"}\n本文\n:::\n'
        self.assertEqual(_find_bare_latex(md), [])


if __name__ == "__main__":
    unittest.main()
