"""blockindent.lua: indent 属性の扱い（既定・指定・不正値の警告）。"""

import shutil
import subprocess
import unittest
from pathlib import Path

FILTER = Path(__file__).resolve().parents[1] / "src" / "md_merge" / "filters" / "blockindent.lua"


def _run(md: str, fmt: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["pandoc", "-f", "markdown", "-t", fmt, "--lua-filter", str(FILTER)],
        input=md, capture_output=True, text=True, encoding="utf-8", check=True,
    )


@unittest.skipUnless(shutil.which("pandoc"), "pandoc がありません")
class TestBlockindentFilter(unittest.TestCase):
    def test_default_has_no_indent_and_no_warning(self):
        r = _run("::: {.blockindent}\nA\n:::\n", "typst")
        self.assertIn("#semblockindent[", r.stdout)
        self.assertEqual(r.stderr, "")

    def test_valid_indent_typst_and_html(self):
        r = _run("::: {.blockindent indent=6em}\nA\n:::\n", "typst")
        self.assertIn("#semblockindent(indent: 6em)[", r.stdout)
        self.assertEqual(r.stderr, "")
        r = _run("::: {.blockindent indent=.5em}\nA\n:::\n", "html")
        self.assertIn('style="margin-left:.5em"', r.stdout)
        self.assertEqual(r.stderr, "")

    def test_invalid_indent_warns_and_falls_back(self):
        for bad in ("6", "50%", "abc"):
            with self.subTest(bad=bad):
                r = _run(f'::: {{.blockindent indent="{bad}"}}\nA\n:::\n', "typst")
                self.assertIn("#semblockindent[", r.stdout)
                self.assertNotIn("indent:", r.stdout)
                self.assertIn("[blockindent]", r.stderr)
                self.assertIn(f"indent={bad}", r.stderr)
                r = _run(f'::: {{.blockindent indent="{bad}"}}\nA\n:::\n', "html")
                self.assertNotIn("margin-left", r.stdout)
                self.assertIn("[blockindent]", r.stderr)


if __name__ == "__main__":
    unittest.main()
