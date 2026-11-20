"""transfer が githubmd 出力の <img src> も画像として転送することのテスト。

実行: python -m unittest discover -s tests
"""

import argparse
import tempfile
import unittest
from pathlib import Path

from md_merge._imagerefs import rewrite
from md_merge.transfer import run as run_transfer


class TestHtmlImgRewrite(unittest.TestCase):
    def test_off_by_default(self):
        src = '<img src="a.png" alt="" width="40%">\n'
        self.assertEqual(rewrite(src, lambda r: "x/" + r.ref), src)

    def test_html_img_rewritten(self):
        out = rewrite('[<img src="img/a.png" alt="" width="40%">](u) ![](b.png){width=1%}\n',
                      lambda r: "s/" + r.ref.split("/")[-1], html_img=True)
        self.assertEqual(out, '[<img src="s/a.png" alt="" width="40%">](u) ![](s/b.png){width=1%}\n')

    def test_escaped_src_roundtrip(self):
        seen = []
        out = rewrite('<img src="a&amp;b.png" alt="">\n',
                      lambda r: seen.append(r.ref) or "s/a&b.png", html_img=True)
        self.assertEqual(seen, ["a&b.png"])
        self.assertEqual(out, '<img src="s/a&amp;b.png" alt="">\n')

    def test_url_skipped_by_resolver_returning_none(self):
        src = '<img src="https://x/a.png" alt="">\n'
        self.assertEqual(rewrite(src, lambda r: None, html_img=True), src)


class TestTransferGithubmd(unittest.TestCase):
    def test_transfer_copies_img_tag_images(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "images").mkdir()
            (d / "images" / "a.png").write_bytes(b"png")
            (d / "doc_github.md").write_text(
                '<img src="images/a.png" alt="" width="40%">\n', encoding="utf-8")
            recipe = d / "r.yaml"
            recipe.write_text(
                "output:\n  targetbasefilename: doc\n"
                "transfer:\n  slug: my-doc\n  dataentry_input: out\n", encoding="utf-8")
            args = argparse.Namespace(input=str(recipe), workdir=None, log_level="error",
                                      dry_run=False, json=False, force=False, source="githubmd")
            self.assertEqual(run_transfer(args), 0)
            self.assertEqual((d / "out" / "my-doc.md").read_text(encoding="utf-8"),
                             '<img src="my-doc/a.png" alt="" width="40%">\n')
            self.assertTrue((d / "out" / "my-doc" / "a.png").exists())


if __name__ == "__main__":
    unittest.main()
