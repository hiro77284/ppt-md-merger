"""merge.copy-images / copy-yamls（肯定形、既定 true）と旧来の no-copy-* の併用テスト。

- copy-* が標準キー。no-copy-* も引き続き受け付ける。
- 両方を指定して意味が食い違うとエラー（merge は EXIT_BAD_INPUT、validate もエラー）。
- 意味が一致する併用は許容。CLI --no-copy-images / --no-copy-yamls は従来どおり優先。

実行: python -m unittest discover -s tests
"""

import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

from md_merge.merge._copy_keys import CopyKeyConflictError, copy_key_errors, resolve_no_copy

_SRC = Path(__file__).resolve().parents[1] / "src"

_MD = "## A\n\n![背景](../images/s2.png)\n[入力欄定義](../mds/s2.yaml)\n"


def _run(cmd: str, recipe: Path, *extra: str) -> subprocess.CompletedProcess:
    env = dict(os.environ, PYTHONPATH=str(_SRC))
    args = [sys.executable, "-m", "md_merge", cmd, str(recipe)]
    if cmd == "merge":
        args.append("--force")
    return subprocess.run(
        [*args, *extra], cwd=recipe.parent, env=env, capture_output=True, text=True,
        encoding="utf-8", stdin=subprocess.DEVNULL,
    )


class TestResolveNoCopy(unittest.TestCase):
    def test_default_copies(self):
        self.assertFalse(resolve_no_copy({}, "copy-images", "no-copy-images"))

    def test_positive_key(self):
        self.assertTrue(resolve_no_copy({"copy-images": False}, "copy-images", "no-copy-images"))
        self.assertFalse(resolve_no_copy({"copy-images": True}, "copy-images", "no-copy-images"))

    def test_negative_key_still_accepted(self):
        self.assertTrue(resolve_no_copy({"no-copy-images": True}, "copy-images", "no-copy-images"))
        self.assertFalse(resolve_no_copy({"no-copy-images": False}, "copy-images", "no-copy-images"))

    def test_consistent_both_ok(self):
        mc = {"copy-images": False, "no-copy-images": True}
        self.assertTrue(resolve_no_copy(mc, "copy-images", "no-copy-images"))
        mc = {"copy-images": True, "no-copy-images": False}
        self.assertFalse(resolve_no_copy(mc, "copy-images", "no-copy-images"))

    def test_conflict_raises(self):
        for mc in ({"copy-images": True, "no-copy-images": True},
                   {"copy-images": False, "no-copy-images": False}):
            with self.subTest(mc=mc), self.assertRaises(CopyKeyConflictError):
                resolve_no_copy(mc, "copy-images", "no-copy-images")

    def test_copy_key_errors(self):
        self.assertEqual(copy_key_errors({"copy-images": False, "copy-yamls": True}), [])
        errs = copy_key_errors({"copy-yamls": False, "no-copy-yamls": False})
        self.assertEqual(len(errs), 1)
        self.assertIn("copy-yamls", errs[0])


class TestMergeCopyKeys(unittest.TestCase):
    def _project(self, root: Path, merge_section: str = "") -> Path:
        (root / "mds").mkdir()
        (root / "images").mkdir()
        (root / "images" / "s2.png").write_bytes(b"png")
        (root / "mds" / "s2.yaml").write_text("a: 1\n", encoding="utf-8")
        (root / "mds" / "a_md.md").write_text(_MD, encoding="utf-8")
        recipe = root / "r.yaml"
        recipe.write_text(textwrap.dedent("""\
            version: 4
            output:
              outputdir: build
              mdfilename: out.md
            """) + merge_section + "procedure:\n  - insertmd: mds/a_md.md\n", encoding="utf-8")
        return recipe

    def _out(self, root: Path) -> str:
        return (root / "build" / "out.md").read_text(encoding="utf-8")

    def test_copy_images_false(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            r = _run("merge", self._project(root, "merge:\n  copy-images: false\n"))
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("![背景](../images/s2.png)", self._out(root))
            self.assertFalse(list((root / "build").rglob("*.png")))
            # YAML 側は独立（既定でコピー）
            self.assertIn("[入力欄定義](images/mds/s2.yaml)", self._out(root))

    def test_copy_images_true_explicit(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            r = _run("merge", self._project(root, "merge:\n  copy-images: true\n"))
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("![背景](images/images/s2.png)", self._out(root))

    def test_copy_yamls_false(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            r = _run("merge", self._project(root, "merge:\n  copy-yamls: false\n"))
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("[入力欄定義](../mds/s2.yaml)", self._out(root))
            self.assertIn("![背景](images/images/s2.png)", self._out(root))

    def test_cli_no_copy_images_overrides_copy_images_true(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            r = _run("merge", self._project(root, "merge:\n  copy-images: true\n"), "--no-copy-images")
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("![背景](../images/s2.png)", self._out(root))

    def test_conflict_is_error(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            recipe = self._project(root, "merge:\n  copy-images: true\n  no-copy-images: true\n")
            r = _run("merge", recipe)
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("矛盾", r.stderr)
            self.assertFalse((root / "build" / "out.md").exists())

    def test_validate(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            ok = self._project(root, "merge:\n  copy-images: false\n  copy-yamls: true\n")
            r = _run("validate", ok)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertNotIn("未知のキー", r.stdout + r.stderr)
            ng = root / "ng.yaml"
            ng.write_text(ok.read_text(encoding="utf-8").replace(
                "  copy-yamls: true\n", "  copy-yamls: true\n  no-copy-yamls: true\n"), encoding="utf-8")
            r = _run("validate", ng)
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("矛盾", r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
