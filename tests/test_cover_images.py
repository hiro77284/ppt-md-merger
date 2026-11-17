"""表紙 MD（pandoc.cover-md）の画像をレシピ基準で解決して merge.image-dir にコピーする。"""
import shutil
import tempfile
import unittest
from pathlib import Path

from md_merge._cover_images import body_image_targets, copy_cover_images, cover_image_settings
from md_merge.pandoc import _build_cover_from_md, _cover_image_opts


def _png(path: Path, data: bytes = b"\x89PNG-a") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


class CoverImageSettingsTest(unittest.TestCase):
    def test_defaults_follow_merge(self):
        self.assertEqual(cover_image_settings(None), (True, "images", "preserve", "rename"))

    def test_copy_images_false(self):
        self.assertFalse(cover_image_settings({"copy-images": False})[0])
        self.assertFalse(cover_image_settings({"no-copy-images": True})[0])

    def test_contradiction_means_no_copy(self):
        self.assertFalse(cover_image_settings({"copy-images": True, "no-copy-images": True})[0])


class CopyCoverImagesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.src = self.tmp / "src"
        self.build = self.tmp / "build"
        self.img_dir = self.build / "images"
        self.src.mkdir()
        self.build.mkdir()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def _copy(self, content, **kw):
        return copy_cover_images(
            content, bases=[self.src], img_dir=self.img_dir, ref_base=self.build, **kw
        )

    def test_recipe_relative_image_is_copied(self):
        _png(self.tmp / "images" / "cover_image.png")
        out = self._copy("![](../images/cover_image.png){width=80%}\n")
        self.assertEqual(out, "![](images/cover_image.png){width=80%}\n")
        self.assertTrue((self.img_dir / "cover_image.png").is_file())

    def test_not_found_is_left_for_resource_path(self):
        out = self._copy("![](cover_image.png)\n")
        self.assertEqual(out, "![](cover_image.png)\n")
        self.assertFalse(self.img_dir.exists())

    def test_url_is_untouched(self):
        out = self._copy("![](https://example.com/a.png)\n")
        self.assertEqual(out, "![](https://example.com/a.png)\n")

    def test_image_already_in_image_dir_is_referenced_in_place(self):
        _png(self.img_dir / "kv.png")
        out = copy_cover_images(
            "![](../build/images/kv.png)\n",
            bases=[self.src], img_dir=self.img_dir, ref_base=self.build,
        )
        self.assertEqual(out, "![](images/kv.png)\n")

    def test_collision_with_body_image_is_renamed(self):
        body = _png(self.img_dir / "cover_image.png", b"body")
        _png(self.tmp / "images" / "cover_image.png", b"cover")
        out = self._copy("![](../images/cover_image.png)\n", taken={body.resolve()})
        self.assertEqual(out, "![](images/cover_image_1.png)\n")
        self.assertEqual(body.read_bytes(), b"body")
        self.assertEqual((self.img_dir / "cover_image_1.png").read_bytes(), b"cover")

    def test_stale_file_from_previous_run_is_overwritten(self):
        _png(self.img_dir / "cover_image.png", b"old")
        _png(self.tmp / "images" / "cover_image.png", b"new")
        out = self._copy("![](../images/cover_image.png)\n")
        self.assertEqual(out, "![](images/cover_image.png)\n")
        self.assertEqual((self.img_dir / "cover_image.png").read_bytes(), b"new")

    def test_same_content_as_body_image_is_shared(self):
        body = _png(self.img_dir / "cover_image.png", b"same")
        _png(self.tmp / "images" / "cover_image.png", b"same")
        out = self._copy("![](../images/cover_image.png)\n", taken={body.resolve()})
        self.assertEqual(out, "![](images/cover_image.png)\n")

    def test_sanitize_naming(self):
        _png(self.tmp / "images" / "Cover.PNG")
        out = self._copy("![](../images/Cover.PNG)\n", naming="sanitize")
        self.assertEqual(out, "![](images/cover.png)\n")

    def test_body_image_targets(self):
        rendered = self.build / "x_rendered.md"
        rendered.write_text("![](images/a.png)\n![](../elsewhere/b.png)\n", encoding="utf-8")
        self.assertEqual(body_image_targets(rendered, self.img_dir), {(self.img_dir / "a.png").resolve()})


@unittest.skipUnless(shutil.which("pandoc"), "pandoc が必要")
class BuildCoverTest(unittest.TestCase):
    """pdf1_minimum と同じ構成: src/recipe.yaml, images/cover_image.png, build/images。"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        (self.tmp / "src").mkdir()
        self.yaml_path = self.tmp / "src" / "recipe.yaml"
        self.yaml_path.write_text("version: 4\n", encoding="utf-8")
        _png(self.tmp / "images" / "cover_image.png")
        self.cover = self.tmp / "src" / "cover.md"
        self.cover.write_text(
            "{{#if:COVER_IMAGE}}\n![]({{v:COVER_IMAGE}}){width=80%}\n{{#endif:COVER_IMAGE}}\n",
            encoding="utf-8",
        )
        self.build = self.tmp / "build"
        self.build.mkdir()
        self.rendered = self.build / "out_rendered.md"
        self.rendered.write_text("本文\n", encoding="utf-8")
        self.recipe = {
            "version": 4,
            "output": {"outputdir": "../build", "targetbasefilename": "out"},
            "merge": {"copy-images": True, "image-dir": "../build/images", "flatten-images": True},
        }

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def _build(self, vars_section):
        return _build_cover_from_md(
            str(self.cover), vars_section, self.yaml_path, None, self.build, "typst", False,
            [self.build, self.build / "images"],
            cover_image_opts=_cover_image_opts(self.recipe, self.yaml_path, None, self.rendered),
        )

    def test_cover_image_relative_to_recipe_is_copied(self):
        frag = self._build({"COVER_IMAGE": "../images/cover_image.png"})
        self.assertIsNotNone(frag)
        self.assertTrue((self.build / "images" / "cover_image.png").is_file())
        self.assertIn('image("images/cover_image.png"', frag.read_text(encoding="utf-8"))

    def test_copy_images_false_keeps_old_behaviour(self):
        self.recipe["merge"]["copy-images"] = False
        frag = _build_cover_from_md(
            str(self.cover), {"COVER_IMAGE": "../images/cover_image.png"}, self.yaml_path, None,
            self.build, "typst", False, [self.build, self.build / "images"],
            cover_image_opts=_cover_image_opts(self.recipe, self.yaml_path, None, self.rendered),
        )
        self.assertIsNotNone(frag)
        self.assertFalse((self.build / "images" / "cover_image.png").exists())


if __name__ == "__main__":
    unittest.main()
