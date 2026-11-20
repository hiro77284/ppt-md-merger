"""githubmd（puremd → GitHub 向け MD）の画像属性変換のテスト。

実行: python -m unittest discover -s tests
"""

import argparse
import tempfile
import unittest
from pathlib import Path

from md_merge.githubmd import convert, run


class TestGithubmdConvert(unittest.TestCase):
    def test_width_percent_to_img(self):
        out, n = convert("![図1](images/a.png){ width=40% }\n")
        self.assertEqual(out, '<img src="images/a.png" alt="図1" width="40%">\n')
        self.assertEqual(n, 1)

    def test_width_px_and_height(self):
        out, _ = convert('![](a.png){width="300px" height=200}\n')
        self.assertEqual(out, '<img src="a.png" alt="" width="300" height="200">\n')

    def test_linked_image_keeps_link(self):
        out, _ = convert("[![](x/a.png){ width=40% }](https://example.com)\n")
        self.assertEqual(out, '[<img src="x/a.png" alt="" width="40%">](https://example.com)\n')

    def test_unsupported_attrs_dropped_with_warning(self):
        with self.assertLogs(level="WARNING") as cm:
            out, n = convert("![](a.png){ width=8cm #fig:a .wide }\n")
        self.assertEqual(out, "![](a.png)\n")
        self.assertEqual(n, 0)
        self.assertIn("8cm", cm.output[0])

    def test_mixed_supported_and_unsupported(self):
        with self.assertLogs(level="WARNING"):
            out, _ = convert("![](a.png){#fig:a width=50%}\n")
        self.assertEqual(out, '<img src="a.png" alt="" width="50%">\n')

    def test_space_before_attrs(self):
        out, _ = convert("![](a.png) {width=50%}\n")
        self.assertEqual(out, '<img src="a.png" alt="" width="50%">\n')

    def test_alt_is_escaped(self):
        out, _ = convert('![a "b" & <c>](a.png){width=10%}\n')
        self.assertEqual(out, '<img src="a.png" alt="a &quot;b&quot; &amp; &lt;c&gt;" width="10%">\n')

    def test_image_without_attrs_untouched(self):
        src = "![](a.png)\n\ntext\n"
        out, n = convert(src)
        self.assertEqual(out, src)
        self.assertEqual(n, 0)

    def test_code_fence_and_inline_code_untouched(self):
        src = "```md\n![](a.png){ width=40% }\n```\n\n`![](b.png){width=1%}` x\n"
        out, n = convert(src)
        self.assertEqual(out, src)
        self.assertEqual(n, 0)

    def test_frontmatter_untouched(self):
        src = "---\ntitle: '![](a.png){width=1%}'\n---\n\n![](b.png){width=2%}\n"
        out, _ = convert(src)
        self.assertIn("title: '![](a.png){width=1%}'", out)
        self.assertIn('<img src="b.png" alt="" width="2%">', out)


class TestGithubmdRun(unittest.TestCase):
    def _args(self, recipe: Path, **kw):
        ns = argparse.Namespace(input=str(recipe), workdir=None, log_level="error",
                                dry_run=False, json=False, force=False)
        for k, v in kw.items():
            setattr(ns, k, v)
        return ns

    def test_run_writes_githubmd_from_puremd(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "doc_puremd.md").write_text("![](a.png){ width=40% }\n", encoding="utf-8")
            recipe = d / "r.yaml"
            recipe.write_text("output:\n  targetbasefilename: doc\n", encoding="utf-8")
            self.assertEqual(run(self._args(recipe)), 0)
            out = (d / "doc_github.md").read_text(encoding="utf-8")
            self.assertEqual(out, '<img src="a.png" alt="" width="40%">\n')
            # puremd の出力は変えない
            self.assertEqual((d / "doc_puremd.md").read_text(encoding="utf-8"),
                             "![](a.png){ width=40% }\n")
            # 既存出力は --force なしでは上書きしない
            self.assertNotEqual(run(self._args(recipe)), 0)
            self.assertEqual(run(self._args(recipe, force=True)), 0)


if __name__ == "__main__":
    unittest.main()
