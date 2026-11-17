"""merge が本文の YAML ファイルへのリンク ``[text](x.yaml)`` を画像と同様にコピー・書き換えするテスト。

キー: merge.no-copy-yamls / yaml-dir / flatten-yamls / overwrite-yamls（CLI 同名フラグが優先）。

実行: python -m unittest discover -s tests
"""

import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

_SRC = Path(__file__).resolve().parents[1] / "src"

_MD = textwrap.dedent("""\
    ## A

    <!-- #inputs -->
    ![背景](../images/s2.png)
    [入力欄定義](../mds/s2.yaml)
    <!-- /inputs -->

    [外部](https://example.com/x.yaml) [md](other.md)
    """)


def _run_merge(recipe: Path, *extra: str) -> subprocess.CompletedProcess:
    env = dict(os.environ, PYTHONPATH=str(_SRC))
    return subprocess.run(
        [sys.executable, "-m", "md_merge", "merge", str(recipe), "--force", *extra],
        cwd=recipe.parent, env=env, capture_output=True, text=True,
        encoding="utf-8", stdin=subprocess.DEVNULL,
    )


class TestMergeYamlLinks(unittest.TestCase):
    def _project(self, root: Path, merge_section: str = "") -> Path:
        (root / "mds").mkdir()
        (root / "images").mkdir()
        (root / "images" / "s2.png").write_bytes(b"png")
        (root / "mds" / "s2.yaml").write_text("a: 1\n", encoding="utf-8")
        (root / "mds" / "a_md.md").write_text(_MD, encoding="utf-8")
        recipe = root / "r.yaml"
        recipe.write_text(textwrap.dedent("""\
            version: 2
            output:
              outputdir: build
              mdfilename: out.md
            """) + merge_section + textwrap.dedent("""\
            procedure:
              - insertmd: mds/a_md.md
            """), encoding="utf-8")
        return recipe

    def _out(self, root: Path) -> str:
        return (root / "build" / "out.md").read_text(encoding="utf-8")

    def test_default_follows_image_dir(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            recipe = self._project(root, "merge:\n  image-dir: assets\n  flatten-images: true\n")
            r = _run_merge(recipe)
            self.assertEqual(r.returncode, 0, r.stderr)
            out = self._out(root)
            self.assertIn("![背景](assets/s2.png)", out)
            self.assertIn("[入力欄定義](assets/mds/s2.yaml)", out)
            self.assertTrue((root / "build" / "assets" / "mds" / "s2.yaml").exists())
            # URL・非 YAML リンクは触らない
            self.assertIn("[外部](https://example.com/x.yaml)", out)
            self.assertIn("[md](other.md)", out)

    def test_yaml_keys(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            recipe = self._project(root, "merge:\n  yaml-dir: defs\n  flatten-yamls: true\n")
            r = _run_merge(recipe)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("[入力欄定義](defs/s2.yaml)", self._out(root))
            self.assertTrue((root / "build" / "defs" / "s2.yaml").exists())
            self.assertIn("![背景](images/images/s2.png)", self._out(root))

    def test_no_copy_yamls_key(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            recipe = self._project(root, "merge:\n  no-copy-yamls: true\n")
            r = _run_merge(recipe)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("[入力欄定義](../mds/s2.yaml)", self._out(root))
            self.assertIn("![背景](images/images/s2.png)", self._out(root))
            self.assertFalse(list((root / "build").rglob("*.yaml")))

    def test_cli_overrides_recipe(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            recipe = self._project(root, "merge:\n  yaml-dir: defs\n")
            r = _run_merge(recipe, "--yaml-dir", "cli", "--flatten-yamls")
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("[入力欄定義](cli/s2.yaml)", self._out(root))

    def test_collision_rename_and_overwrite(self):
        for section, expect_second in (
            ("merge:\n  flatten-yamls: true\n", "x/s2_1.yaml"),
            ("merge:\n  flatten-yamls: true\n  overwrite-yamls: true\n", "x/s2.yaml"),
        ):
            with self.subTest(section=section), tempfile.TemporaryDirectory() as d:
                root = Path(d)
                recipe = self._project(root, section + "  yaml-dir: x\n")
                (root / "mds" / "sub").mkdir()
                (root / "mds" / "sub" / "s2.yaml").write_text("b: 2\n", encoding="utf-8")
                (root / "mds" / "a_md.md").write_text(
                    "[1](s2.yaml)\n[2](sub/s2.yaml)\n", encoding="utf-8")
                r = _run_merge(recipe)
                self.assertEqual(r.returncode, 0, r.stderr)
                out = self._out(root)
                self.assertIn("[1](x/s2.yaml)", out)
                self.assertIn(f"[2]({expect_second})", out)

    def test_validate_accepts_keys(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            recipe = self._project(root, textwrap.dedent("""\
                merge:
                  no-copy-yamls: false
                  yaml-dir: defs
                  flatten-yamls: true
                  overwrite-yamls: false
                """))
            env = dict(os.environ, PYTHONPATH=str(_SRC))
            r = subprocess.run(
                [sys.executable, "-m", "md_merge", "validate", str(recipe)],
                cwd=root, env=env, capture_output=True, text=True, encoding="utf-8",
            )
            self.assertNotIn("yaml", (r.stdout + r.stderr).replace("r.yaml", ""), r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
