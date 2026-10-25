"""レシピ YAML の ``_include`` / ``_constants``（と旧書式 ``!include`` / ``!constants``）のテスト。

実行: python -m unittest discover -s tests
"""

import importlib.util
import tempfile
import textwrap
import unittest
from pathlib import Path

from md_merge.merge._recipe import load_yaml, load_yaml_text

_TOOL = Path(__file__).resolve().parents[1] / "tools" / "convert_include_keys.py"
_spec = importlib.util.spec_from_file_location("convert_include_keys", _TOOL)
convert_include_keys = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(convert_include_keys)


class _TmpDir(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def write(self, name: str, text: str) -> Path:
        p = self.dir / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(textwrap.dedent(text), encoding="utf-8")
        return p

    def load(self, name: str, text: str):
        return load_yaml(self.write(name, text), normalize=False)


class TestInclude(_TmpDir):
    def test_merge_with_sibling_keys_wins(self):
        self.write("settings.yaml", """\
            engine: tex
            defaults: a.yaml
        """)
        r = self.load("recipe.yaml", """\
            pandoc:
              typst-cover-md: cover.md
              engine: typst
              _include: settings.yaml
        """)
        self.assertEqual(r["pandoc"], {"engine": "typst", "defaults": "a.yaml", "typst-cover-md": "cover.md"})

    def test_list_later_file_wins(self):
        self.write("a.yaml", "x: 1\ny: 1\n")
        self.write("b.yaml", "y: 2\n")
        r = self.load("recipe.yaml", "vars:\n  _include: [a.yaml, b.yaml]\n")
        self.assertEqual(r["vars"], {"x": 1, "y": 2})

    def test_non_mapping_replaces_value(self):
        self.write("slots.yaml", "- a\n- b\n")
        self.write("one.yaml", "hello\n")
        r = self.load("recipe.yaml", """\
            slots:
              _include: slots.yaml
            title: {_include: one.yaml}
        """)
        self.assertEqual(r["slots"], ["a", "b"])
        self.assertEqual(r["title"], "hello")

    def test_non_mapping_with_siblings_is_error(self):
        self.write("slots.yaml", "- a\n")
        with self.assertRaises(ValueError):
            self.load("recipe.yaml", "slots:\n  _include: slots.yaml\n  extra: 1\n")

    def test_nested_path_is_relative_to_including_file(self):
        self.write("sub/inner.yaml", "k: v\n")
        self.write("sub/outer.yaml", "_include: inner.yaml\nouter: 1\n")
        r = self.load("recipe.yaml", "top:\n  _include: sub/outer.yaml\n")
        self.assertEqual(r["top"], {"k": "v", "outer": 1})

    def test_top_level_include(self):
        self.write("base.yaml", "version: 2\nlog:\n  level: info\n")
        r = self.load("recipe.yaml", "_include: base.yaml\nlog:\n  level: debug\n")
        self.assertEqual(r, {"version": 2, "log": {"level": "debug"}})

    def test_circular_is_error(self):
        self.write("a.yaml", "_include: b.yaml\n")
        self.write("b.yaml", "_include: a.yaml\n")
        with self.assertRaises(ValueError):
            self.load("recipe.yaml", "x:\n  _include: a.yaml\n")

    def test_missing_file(self):
        with self.assertRaises(FileNotFoundError):
            self.load("recipe.yaml", "x:\n  _include: nothing.yaml\n")


class TestConstants(_TmpDir):
    def test_constants_key_applies_to_file_and_includes(self):
        self.write("c.toml", "__AUTHOR__ = 'Yamada'\n__BLOCK__ = '''\n- one\n- two\n'''\n")
        self.write("inc.yaml", "who: __AUTHOR__\n")
        r = self.load("recipe.yaml", """\
            _constants: c.toml
            author: __AUTHOR__
            items:
              __BLOCK__
            sub:
              _include: inc.yaml
        """)
        self.assertEqual(r, {"author": "Yamada", "items": ["one", "two"], "sub": {"who": "Yamada"}})

    def test_constants_list_and_child_overrides(self):
        self.write("a.toml", "__X__ = 'a'\n__Y__ = 'a'\n")
        self.write("b.toml", "__Y__ = 'b'\n")
        self.write("inc.yaml", "_constants: b.toml\nx: __X__\ny: __Y__\n")
        r = self.load("recipe.yaml", "_constants:\n  - a.toml\nsub:\n  _include: inc.yaml\ny: __Y__\n")
        self.assertEqual(r, {"sub": {"x": "a", "y": "b"}, "y": "a"})

    def test_note_yaml_text(self):
        self.write("head.yaml", "id: sample\n")
        r = load_yaml_text("_include: head.yaml\ntitle: t\n", self.dir)
        self.assertEqual(r, {"id": "sample", "title": "t"})


class TestLegacy(_TmpDir):
    def test_legacy_still_works_with_warning(self):
        self.write("c.toml", "__A__ = 'x'\n")
        self.write("settings.yaml", "engine: typst\n")
        with self.assertLogs(level="WARNING") as cm:
            r = self.load("recipe.yaml", """\
                !constants c.toml
                pandoc:
                  !include settings.yaml

                  typst-cover-md: __A__.md
            """)
        self.assertEqual(r["pandoc"], {"engine": "typst", "typst-cover-md": "x.md"})
        self.assertTrue(any("非推奨" in m for m in cm.output))


class TestConverter(_TmpDir):
    def test_convert_matches_legacy_result(self):
        self.write("c.toml", "__A__ = 'x'\n")
        self.write("settings.yaml", "engine: typst\n")
        self.write("one.yaml", "hello\n")
        legacy = textwrap.dedent("""\
            !constants c.toml   # 定数
            pandoc:
              !include settings.yaml

              typst-cover-md: __A__.md
            title: !include one.yaml  # inline
            # !include commented.yaml
        """)
        warn: list[str] = []
        converted = convert_include_keys.convert_text(legacy, "yaml", "t", warn)
        self.assertEqual(converted, textwrap.dedent("""\
            _constants: c.toml  # 定数
            pandoc:
              _include: settings.yaml

              typst-cover-md: __A__.md
            title: {_include: one.yaml}  # inline
            # !include commented.yaml
        """))
        self.assertEqual(warn, [])
        self.assertEqual(
            self.load("new.yaml", converted),
            self.load("old.yaml", legacy),
        )

    def test_warns_on_order_change_and_groups_multiple(self):
        warn: list[str] = []
        out = convert_include_keys.convert_text(
            "vars:\n  a: 1\n  !include x.yaml\n  !include y.yaml\n", "yaml", "t", warn)
        self.assertEqual(out, "vars:\n  a: 1\n  _include:\n    - x.yaml\n    - y.yaml\n")
        self.assertEqual(len(warn), 2)


if __name__ == "__main__":
    unittest.main()
