"""input セクションの廃止と fragment / source への改名のテスト。

- fragment.dirs / source.cropimagedirs / source.cropsrc が新しいキー。
- 旧 input.dirs / input.imagesdir / input.cropsrc は非推奨（読み替えて warning）。
- input.mddir / input.pptxdir はエラー。新旧の両方を書くとエラー。

実行: python -m unittest discover -s tests
"""

import logging
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

from md_merge._cropsrc import cropsrc_entries
from md_merge._source_keys import (
    SourceKeyError,
    deprecated_input_keys,
    normalize_source_keys,
    source_key_errors,
)
from md_merge.crop import _resolve_imagesdirs
from md_merge.merge._recipe import load_yaml, resolve_input_dirs

_SRC = Path(__file__).resolve().parents[1] / "src"


def _run(cmd: str, recipe: Path, *extra: str) -> subprocess.CompletedProcess:
    env = dict(os.environ, PYTHONPATH=str(_SRC))
    args = [sys.executable, "-m", "md_merge", cmd, str(recipe)]
    if cmd == "merge":
        args.append("--force")
    return subprocess.run(
        [*args, *extra], cwd=recipe.parent, env=env, capture_output=True, text=True,
        encoding="utf-8", stdin=subprocess.DEVNULL,
    )


class TestNormalize(unittest.TestCase):
    def test_new_keys_untouched(self):
        r = {"fragment": {"dirs": ["."]}, "source": {"cropsrc": {"pptx": "a.pptx"}}}
        self.assertEqual(normalize_source_keys(r), r)

    def test_legacy_keys_moved(self):
        r = {"input": {"dirs": [".", "mds"], "imagesdir": ["../images"], "cropsrc": {"pptx": "a.pptx"}}}
        with self.assertLogs(level="WARNING") as cm:
            out = normalize_source_keys(r, Path("legacy_moved.yaml"))
        self.assertEqual(out, {
            "fragment": {"dirs": [".", "mds"]},
            "source": {"cropimagedirs": ["../images"], "cropsrc": {"pptx": "a.pptx"}},
        })
        text = "\n".join(cm.output)
        for msg in ("input.dirs は非推奨です。fragment.dirs",
                    "input.imagesdir は非推奨です。source.cropimagedirs",
                    "input.cropsrc は非推奨です。source.cropsrc"):
            self.assertIn(msg, text)

    def test_legacy_merges_with_other_new_key(self):
        r = {"input": {"cropsrc": {"pptx": "a.pptx"}}, "source": {"cropimagedirs": ["img"]}}
        out = normalize_source_keys(r, warn=False)
        self.assertEqual(out, {"source": {"cropimagedirs": ["img"], "cropsrc": {"pptx": "a.pptx"}}})

    def test_warn_once_per_file(self):
        r = {"input": {"dirs": ["."]}}
        with self.assertLogs(level="WARNING") as cm:
            normalize_source_keys(r, Path("warn_once.yaml"))
            normalize_source_keys(r, Path("warn_once.yaml"))
            logging.warning("sentinel")
        self.assertEqual(sum("input.dirs" in m for m in cm.output), 1)

    def test_unknown_legacy_key_kept(self):
        out = normalize_source_keys({"input": {"dirs": ["."], "foo": 1}}, warn=False)
        self.assertEqual(out["input"], {"foo": 1})

    def test_removed_keys_error(self):
        for key in ("mddir", "pptxdir"):
            with self.subTest(key=key):
                errs = source_key_errors({"input": {key: "md"}})
                self.assertEqual(len(errs), 1)
                self.assertIn(f"input.{key} は廃止しました", errs[0])
                with self.assertRaises(SourceKeyError):
                    normalize_source_keys({"input": {key: "md"}})

    def test_both_old_and_new_error(self):
        cases = [
            ({"input": {"dirs": ["."]}, "fragment": {"dirs": ["."]}}, "input.dirs と fragment.dirs"),
            ({"input": {"imagesdir": "i"}, "source": {"cropimagedirs": "i"}}, "input.imagesdir と source.cropimagedirs"),
            ({"input": {"cropsrc": {}}, "source": {"cropsrc": {}}}, "input.cropsrc と source.cropsrc"),
        ]
        for recipe, msg in cases:
            with self.subTest(msg=msg):
                errs = source_key_errors(recipe)
                self.assertEqual(len(errs), 1)
                self.assertIn(msg, errs[0])

    def test_section_type_errors(self):
        self.assertTrue(source_key_errors({"fragment": ["."]}))
        self.assertTrue(source_key_errors({"source": "a.pptx"}))
        self.assertTrue(source_key_errors({"input": ["."]}))

    def test_deprecated_input_keys(self):
        self.assertEqual(deprecated_input_keys({"input": {"cropsrc": {}, "dirs": []}}), ["dirs", "cropsrc"])
        self.assertEqual(deprecated_input_keys({"fragment": {"dirs": []}}), [])


class TestReaders(unittest.TestCase):
    def _recipe(self, d: Path, body: str) -> Path:
        p = d / "r.yaml"
        p.write_text(textwrap.dedent(body), encoding="utf-8")
        return p

    def test_new_and_legacy_read_the_same(self):
        new = """\
            version: 4
            fragment:
              dirs: [., mds]
            source:
              cropimagedirs: [images]
              cropsrc:
                pptx: a.pptx
            procedure:
              - insertmd: a.md
            """
        legacy = """\
            version: 4
            input:
              dirs: [., mds]
              imagesdir: [images]
              cropsrc:
                pptx: a.pptx
            procedure:
              - insertmd: a.md
            """
        results = []
        for body in (new, legacy):
            with tempfile.TemporaryDirectory() as td:
                d = Path(td)
                p = self._recipe(d, body)
                r = load_yaml(p)
                results.append((
                    [x.relative_to(d.resolve()) for x in resolve_input_dirs(r, p, None)],
                    [x.relative_to(d.resolve()) for x in _resolve_imagesdirs(r, p, None)],
                    cropsrc_entries(r),
                ))
        self.assertEqual(results[0], results[1])
        self.assertEqual(results[0][0], [Path("."), Path("mds")])
        self.assertEqual(results[0][1], [Path("images")])
        self.assertEqual(results[0][2], [{"pptx": "a.pptx"}])

    def test_legacy_in_include(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            (d / "shared.yaml").write_text("dirs: [., mds]\n", encoding="utf-8")
            p = self._recipe(d, """\
                version: 4
                input:
                  _include: shared.yaml
                procedure:
                  - insertmd: a.md
                """)
            r = load_yaml(p)
            self.assertEqual(r["fragment"], {"dirs": [".", "mds"]})
            self.assertNotIn("input", r)


class TestCli(unittest.TestCase):
    def _write(self, d: Path, inp: str) -> Path:
        (d / "a.md").write_text("# A\n", encoding="utf-8")
        p = d / "r.yaml"
        p.write_text("version: 4\noutput:\n  mdfilename: m.md\n" + inp + "procedure:\n  - insertmd: a.md\n",
                     encoding="utf-8")
        return p

    def test_merge_legacy_dirs_warns(self):
        with tempfile.TemporaryDirectory() as td:
            p = self._write(Path(td), "input:\n  dirs: [.]\n")
            res = _run("merge", p)
            self.assertEqual(res.returncode, 0, res.stderr)
            self.assertIn("input.dirs は非推奨です", res.stderr)
            self.assertTrue((Path(td) / "m.md").exists())

    def test_merge_new_dirs_quiet(self):
        with tempfile.TemporaryDirectory() as td:
            p = self._write(Path(td), "fragment:\n  dirs: [.]\n")
            res = _run("merge", p)
            self.assertEqual(res.returncode, 0, res.stderr)
            self.assertNotIn("非推奨", res.stderr)

    def test_merge_mddir_error(self):
        with tempfile.TemporaryDirectory() as td:
            p = self._write(Path(td), "input:\n  mddir: .\n")
            res = _run("merge", p)
            self.assertNotEqual(res.returncode, 0)
            self.assertIn("input.mddir は廃止しました", res.stderr)

    def test_validate(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            p = self._write(d, "input:\n  dirs: [.]\n")
            res = _run("validate", p)
            self.assertEqual(res.returncode, 0, res.stderr)
            self.assertIn("input.dirs は非推奨です", res.stderr)

            p = self._write(d, "fragment:\n  dirs: [.]\nsource:\n  cropimagedirs: [.]\n")
            res = _run("validate", p)
            self.assertEqual(res.returncode, 0, res.stderr)
            self.assertNotIn("未知のキー", res.stderr + res.stdout)
            self.assertNotIn("非推奨", res.stderr)

            p = self._write(d, "input:\n  pptxdir: .\n")
            res = _run("validate", p)
            self.assertNotEqual(res.returncode, 0)
            self.assertIn("input.pptxdir は廃止しました", res.stderr)

            p = self._write(d, "input:\n  dirs: [.]\nfragment:\n  dirs: [.]\n")
            res = _run("validate", p)
            self.assertNotEqual(res.returncode, 0)
            self.assertIn("両方あります", res.stderr)

            p = self._write(d, "fragment:\n  dirs: [.]\n  mddir: x\n")
            res = _run("validate", p)
            self.assertIn("未知のキー: fragment.'mddir'", res.stderr)


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from convert_input_keys import convert_text  # noqa: E402


class TestConverter(unittest.TestCase):
    def test_full(self):
        src = textwrap.dedent("""\
            version: 4
            input:
              dirs:
                - .
                - ../mds

              imagesdir:
                - ../images

              # pptx から画像を取得する設定
              cropsrc:
                pptx: a.pptx   # 元の pptx
                pdf:

            # 結合手順
            procedure:
              - insertmd: a.md
            """)
        out, errors = convert_text(src)
        self.assertEqual(errors, [])
        self.assertEqual(out, textwrap.dedent("""\
            version: 4
            fragment:
              dirs:
                - .
                - ../mds

            source:
              cropimagedirs:
                - ../images

              # pptx から画像を取得する設定
              cropsrc:
                pptx: a.pptx   # 元の pptx
                pdf:

            # 結合手順
            procedure:
              - insertmd: a.md
            """))
        import yaml
        self.assertEqual(normalize_source_keys(yaml.safe_load(src), warn=False), yaml.safe_load(out))

    def test_dirs_only_at_end(self):
        out, errors = convert_text("version: 4\ninput:\n  dirs: [.]\n")
        self.assertEqual((out, errors), ("version: 4\nfragment:\n  dirs: [.]\n", []))

    def test_no_input(self):
        self.assertEqual(convert_text("version: 4\n"), ("version: 4\n", []))

    def test_skips(self):
        for src, msg in [
            ("input:\n  mddir: md\n", "input.mddir は廃止"),
            ("input:\n  _include: s.yaml\n", "input._include"),
            ("input: {dirs: [.]}\n", "フロー書式"),
            ("input:\n  dirs: [.]\nfragment:\n  dirs: [.]\n", "fragment"),
        ]:
            with self.subTest(src=src):
                out, errors = convert_text(src)
                self.assertEqual(out, src)
                self.assertTrue(any(msg in e for e in errors), errors)


if __name__ == "__main__":
    unittest.main()
