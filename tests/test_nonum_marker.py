"""{{nonum}} マーカー（ID は登録するが採番しない）のテスト。

実行: python -m unittest discover -s tests
"""

import unittest
from pathlib import Path

from md_merge._inventory import extract_entries
from md_merge._render import build_resolved_map, render_content
from md_merge._resolve import expand_title_label_refs, resolve_entries
from md_merge.pptmerge._slide_titles import _parse_title_markers

_MD = """\
{{#id:chapter:p:c}}
# 章

{{#id:section:p:s}}
## 節

{{#id:subsection:p:a}}
### 手順A

{{#id:subsection:p:note}} {{nonum}}
### 補足 {{num:subsection:p:b}}

{{#id:subsection:p:b}}
### 手順B

参照: [{{num:subsection:p:note}}] {{title:subsection:p:note}} / {{label:subsection:p:note}}
"""


def _pipeline(md: str) -> tuple[list[dict], str]:
    base = Path("/tmp")
    entries = extract_entries(md, base / "merged.md", base)
    resolve_entries(entries, ".", ") ")
    expand_title_label_refs(entries, ") ")
    return entries, render_content(md, build_resolved_map({"entries": entries}))


class NonumMarkerTest(unittest.TestCase):
    def test_inventory_flag(self):
        entries, _ = _pipeline(_MD)
        flags = {e["full_id"]: e.get("nonum", False) for e in entries}
        self.assertTrue(flags["subsection:p:note"])
        self.assertFalse(flags["subsection:p:a"])

    def test_counter_not_consumed(self):
        entries, _ = _pipeline(_MD)
        nums = {e["full_id"]: e["number"] for e in entries}
        self.assertEqual(nums["subsection:p:a"], "1.1.1")
        self.assertEqual(nums["subsection:p:note"], "")
        self.assertEqual(nums["subsection:p:b"], "1.1.2")

    def test_label_is_title_with_refs_expanded(self):
        entries, _ = _pipeline(_MD)
        note = next(e for e in entries if e["full_id"] == "subsection:p:note")
        self.assertEqual(note["title"], "補足 1.1.2")
        self.assertEqual(note["label"], "補足 1.1.2")

    def test_render(self):
        _, out = _pipeline(_MD)
        self.assertIn("### 1.1.1) 手順A\n", out)
        self.assertIn("<!-- #id:subsection:p:note -->\n### 補足 1.1.2\n", out)
        self.assertIn("### 1.1.2) 手順B\n", out)
        self.assertIn("参照: [] 補足 1.1.2 / 補足 1.1.2", out)
        self.assertNotIn("{{nonum}}", out)

    def test_nonum_does_not_reset_lower_counters(self):
        md = (
            "{{#id:chapter:p:c1}}\n# 一\n\n"
            "{{#id:section:p:s1}}\n## 節1\n\n"
            "{{#id:chapter:p:x}} {{nonum}}\n# 付録的な章\n\n"
            "{{#id:section:p:s2}}\n## 節2\n"
        )
        entries, out = _pipeline(md)
        nums = {e["full_id"]: e["number"] for e in entries}
        self.assertEqual(nums["section:p:s2"], "1.2")
        self.assertIn("# 付録的な章\n", out)

    def test_pptx_note_marker_skips_title_replacement(self):
        markers = _parse_title_markers("{{#id:section:p:n}} {{nonum}}\n{{#id:section:p:m}}")
        self.assertEqual(markers, [("iddef", "section:p:n", True), ("iddef", "section:p:m", False)])


if __name__ == "__main__":
    unittest.main()
