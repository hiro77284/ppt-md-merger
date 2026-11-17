"""画像参照と pandoc 属性の間の空白詰め（_imagerefs.join_image_attributes）のテスト。

実行: python -m unittest discover -s tests
"""

import shutil
import subprocess
import unittest

from md_merge._imagerefs import join_image_attributes


class TestJoinImageAttributes(unittest.TestCase):
    def test_joins_space_before_attribute(self):
        out, n = join_image_attributes("![](images/物品紛失事件_standard_slide2.png) {width=80%}\n")
        self.assertEqual(out, "![](images/物品紛失事件_standard_slide2.png){width=80%}\n")
        self.assertEqual(n, 1)

    def test_already_joined_is_unchanged(self):
        src = "![](images/a.png){width=90%}\n"
        self.assertEqual(join_image_attributes(src), (src, 0))

    def test_multiple_spaces_and_tabs_and_alt(self):
        out, n = join_image_attributes("![図 1](a.png) \t { width=50% }\n![](b.png)  {#fig:b}\n")
        self.assertEqual(out, "![図 1](a.png){ width=50% }\n![](b.png){#fig:b}\n")
        self.assertEqual(n, 2)

    def test_newline_between_is_not_joined(self):
        src = "![](a.png)\n{width=80%}\n"
        self.assertEqual(join_image_attributes(src), (src, 0))

    def test_text_brace_without_image_is_unchanged(self):
        src = "[link](a.md) {width=80%}\n変数 {x} です\n"
        self.assertEqual(join_image_attributes(src), (src, 0))

    def test_fenced_code_block_is_unchanged(self):
        src = (
            "```markdown\n![](a.png) {width=80%}\n```\n"
            "~~~~\n```\n![](b.png) {width=1%}\n~~~~\n"
            "![](c.png) {width=80%}\n"
        )
        out, n = join_image_attributes(src)
        self.assertEqual(n, 1)
        self.assertIn("```markdown\n![](a.png) {width=80%}\n```\n", out)
        self.assertIn("![](b.png) {width=1%}\n", out)
        self.assertIn("![](c.png){width=80%}\n", out)

    def test_inline_code_is_unchanged(self):
        out, n = join_image_attributes("`![](a.png) {width=80%}` と ![](b.png) {width=80%}\n")
        self.assertEqual(out, "`![](a.png) {width=80%}` と ![](b.png){width=80%}\n")
        self.assertEqual(n, 1)


@unittest.skipUnless(shutil.which("pandoc"), "pandoc がありません")
class TestPandocReadsJoinedAttribute(unittest.TestCase):
    def test_width_reaches_pandoc(self):
        out, _ = join_image_attributes("![](a.png) {width=80%}\n")
        html = subprocess.run(
            ["pandoc", "-f", "markdown", "-t", "html"],
            input=out, capture_output=True, text=True, encoding="utf-8", check=True,
        ).stdout
        self.assertIn('style="width:80', html)
        self.assertNotIn("{width", html)


if __name__ == "__main__":
    unittest.main()
