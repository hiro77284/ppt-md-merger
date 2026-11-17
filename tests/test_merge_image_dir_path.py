"""merge の画像参照が ``..`` を含む outputdir / image-dir でも素直な相対パスになる。"""
import shutil
import tempfile
import unittest
from pathlib import Path

from md_merge.merge._images import ImageCopier


class ImageDirPathTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        (self.tmp / "src").mkdir()
        (self.tmp / "mds").mkdir()
        (self.tmp / "mds" / "a.png").write_bytes(b"png")
        self.source_md = self.tmp / "mds" / "a.md"

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_dotdot_outputdir_and_image_dir(self):
        # pdf1_minimum: outputdir: ../build, image-dir: ../build/images（レシピは src/）
        out_md = self.tmp / "src" / ".." / "build" / "out_merged.md"
        copier = ImageCopier(out_md=out_md, dir_name="../build/images", flatten=True,
                             in_dir=None, naming="preserve", collision="rename")
        line = copier.rewrite_line("![](a.png)\n", self.source_md, in_frontmatter=False)
        self.assertEqual(line, "![](images/a.png)\n")
        self.assertTrue((self.tmp / "build" / "images" / "a.png").is_file())

    def test_plain_image_dir(self):
        out_md = self.tmp / "build" / "out_merged.md"
        copier = ImageCopier(out_md=out_md, dir_name="images", flatten=True,
                             in_dir=None, naming="preserve", collision="rename")
        line = copier.rewrite_line("![](a.png)\n", self.source_md, in_frontmatter=False)
        self.assertEqual(line, "![](images/a.png)\n")

    def test_image_dir_outside_output_dir(self):
        out_md = self.tmp / "build" / "out_merged.md"
        copier = ImageCopier(out_md=out_md, dir_name="../shared_images", flatten=True,
                             in_dir=None, naming="preserve", collision="rename")
        line = copier.rewrite_line("![](a.png)\n", self.source_md, in_frontmatter=False)
        self.assertEqual(line, "![](../shared_images/a.png)\n")


if __name__ == "__main__":
    unittest.main()
