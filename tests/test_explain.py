"""explain サブコマンドのテスト。

実行: python -m pytest tests/test_explain.py
"""

import argparse
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from md_merge.explain import block_decisions, judge, matrix_axes, run

RECIPE = """\
version: 2
params:
  TARGET:
    values: [PDF, RECIPRO]
    default: PDF
  STEP:
    type: bool
    default: false
fragment:
  dirs: [.]
procedure:
  - insertmd: a.md
  - insertmd: b.md
    when:
      var: TARGET=RECIPRO
  - group:
      - insertmd: c.md
      - insertmd: d.md
        when:
          var: STEP
    when:
      var: TARGET=RECIPRO
  - insertmd: e.md
    when:
      command: ppt_to_pdf
"""


class TestJudge(unittest.TestCase):
    def test_command_unevaluated(self):
        item = {"operation": "insertmd", "when": {"command": "ppt_to_pdf"}}
        self.assertEqual(judge(item, {}, None), (True, ["command=ppt_to_pdf"], True))
        self.assertFalse(judge(item, {}, "merge")[0])

    def test_group_and_own(self):
        item = {"operation": "insertmd", "when": {"var": "STEP"},
                "_group_when": [("procedure[2]", {"var": "TARGET=RECIPRO"})]}
        active, reasons, _ = judge(item, {"TARGET": "RECIPRO", "STEP": "false"}, None)
        self.assertFalse(active)
        self.assertEqual(reasons, ["procedure[2] var TARGET=RECIPRO ○", "var STEP ×"])


class TestBlocks(unittest.TestCase):
    def test_nested_and_else(self):
        text = ("{{#if:A}}\nx\n{{#if:B}}\ny\n{{#endif:B}}\n{{#else:A}}\nz\n{{#endif:A}}\n"
                "```\n{{#if:A}}\n```\n")
        self.assertEqual(block_decisions(text, {"B": "1"}), [
            (1, "{{#if:A}}", False), (3, "{{#if:B}}", False), (6, "{{#else:A}}", True)])


class TestMatrixAxes(unittest.TestCase):
    def test_axes(self):
        r = {"params": {"T": {"values": ["a", "b"]}, "S": {"type": "bool"}}}
        self.assertEqual(matrix_axes(["T", "S", "X=1,2"], r),
                         [("T", ["a", "b"]), ("S", ["true", "false"]), ("X", ["1", "2"])])
        with self.assertRaises(ValueError):
            matrix_axes(["X"], r)


class TestRun(unittest.TestCase):
    def _run(self, **kw):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "r.yaml"
            p.write_text(RECIPE, encoding="utf-8")
            (Path(d) / "c.md").write_text("{{#if:STEP}}\nx\n{{#endif:STEP}}\n", encoding="utf-8")
            opts = dict(log_level="error", json=True, input=str(p), workdir=None,
                        for_command=None, matrix=None, blocks=False, subcommand="explain")
            opts.update(kw)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = run(argparse.Namespace(**opts))
            return code, (json.loads(out.getvalue()) if opts["json"] else out.getvalue())

    def test_single(self):
        code, data = self._run(for_command="merge")
        self.assertEqual(code, 0)
        self.assertEqual([i["active"] for i in data["items"]], [True, False, False, False, False])

    def test_matrix(self):
        code, data = self._run(matrix=["TARGET"])
        self.assertEqual(code, 0)
        self.assertEqual(data["matrix"], ["TARGET=PDF", "TARGET=RECIPRO"])
        self.assertEqual([i["item"] for i in data["items"]], ["insertmd b.md", "insertmd c.md"])

    def test_text_with_blocks(self):
        code, text = self._run(json=False, blocks=True, for_command="merge")
        self.assertEqual(code, 0)
        self.assertNotIn("line 1", text)  # c.md は採用されない（TARGET=PDF）

    def test_matrix_two_axes_text(self):
        code, text = self._run(json=False, matrix=["TARGET", "STEP"])
        self.assertEqual(code, 0)
        self.assertIn("[4] TARGET=RECIPRO,STEP=false", text)
        self.assertIn("insertmd d.md", text)


if __name__ == "__main__":
    unittest.main()
