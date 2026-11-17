"""pptyamlexport: トップレベル id 未指定は警告のみ、export-note 未指定はエラー、slot の id 未指定はエラーにするテスト。

実行: python -m unittest discover -s tests
"""

import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

from pptx import Presentation

_SRC = Path(__file__).resolve().parents[1] / "src"


def _note(yaml_body: str) -> str:
    return "NOTE_CONTENT_FORMAT: 1.0\n\n===BLOCK===\n{{BLOCK:YAML}}\n" + textwrap.dedent(yaml_body)


def _make_pptx(path: Path, notes: list[str]) -> None:
    prs = Presentation()
    for text in notes:
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        slide.notes_slide.notes_text_frame.text = text
    prs.save(str(path))


def _run(root: Path, notes: list[str]) -> subprocess.CompletedProcess:
    _make_pptx(root / "deck.pptx", notes)
    recipe = root / "r.yaml"
    recipe.write_text(textwrap.dedent("""\
        version: 2
        input:
          cropsrc:
            pptx: deck.pptx
        """), encoding="utf-8")
    env = dict(os.environ, PYTHONPATH=str(_SRC))
    return subprocess.run(
        [sys.executable, "-m", "md_merge", "pptyamlexport", str(recipe), "--force"],
        cwd=root, env=env, capture_output=True, text=True,
        encoding="utf-8", stdin=subprocess.DEVNULL,
    )


_SLOT = """\
    slots:
      - id: slot1
        x: 0.1
        y: 0.1
        width: 0.2
        height: 0.2
    """


class TestTopLevelId(unittest.TestCase):
    def test_missing_id_warns_and_uses_export_note(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            r = _run(root, [_note("export-note: out.yaml\n" + textwrap.dedent(_SLOT))])
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("id が指定されていません", r.stderr)
            self.assertIn("WARNING", r.stderr.upper())
            self.assertTrue((root / "out.yaml").exists())

    def test_missing_export_note_is_error(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            r = _run(root, [_note("id: fig\n" + textwrap.dedent(_SLOT))])
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("export-note が指定されていません", r.stderr)
            self.assertFalse((root / "fig.yaml").exists())
            self.assertEqual(list(root.glob("*.yaml")), [root / "r.yaml"])

    def test_with_id_unchanged(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            r = _run(root, [_note("export-note: fig.yaml\nid: fig\n" + textwrap.dedent(_SLOT))])
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertNotIn("id が指定されていません", r.stderr)
            self.assertTrue((root / "fig.yaml").exists())

    def test_missing_slot_id_is_still_error(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            body = "export-note: fig.yaml\nid: fig\nslots:\n  - x: 0.1\n    y: 0.1\n    width: 0.2\n    height: 0.2\n"
            r = _run(root, [_note(body)])
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("に id がありません", r.stderr)
            self.assertFalse((root / "fig.yaml").exists())


if __name__ == "__main__":
    unittest.main()
