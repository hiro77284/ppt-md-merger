"""procedure の insertvar（変数の値をそのまま挿入）のテスト。

実行: python -m pytest tests/test_insertvar.py
"""

import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

from md_merge._filters import strip_frontmatter
from md_merge._procedure import ProcedureNotationError, normalize_recipe, to_notation
from md_merge.merge._recipe import VarInsert, collect_procedure_items, expand_var
from md_merge.validate._lint import lint

_SRC = Path(__file__).resolve().parents[1] / "src"

_FM = "---\ntitle: Foo\ntags: [a, b]\n---\n"


def _run(*args: str, cwd: Path) -> subprocess.CompletedProcess:
    env = dict(os.environ, PYTHONPATH=str(_SRC))
    return subprocess.run(
        [sys.executable, "-m", "md_merge", *args],
        cwd=cwd, env=env, capture_output=True, text=True,
        encoding="utf-8", stdin=subprocess.DEVNULL,
    )


class TestNotation(unittest.TestCase):
    def test_v2_short_notation(self):
        r = normalize_recipe({"version": 2, "procedure": [{"insertvar": "FM"}]})
        self.assertEqual(r["procedure"], [{"operation": "insertvar", "varname": "FM"}])
        self.assertEqual(to_notation(r["procedure"][0], 2), {"insertvar": "FM"})

    def test_v1_operation_notation(self):
        r = normalize_recipe(
            {"version": 1, "procedure": [{"operation": "insertvar", "varname": "FM"}]},
            warn_deprecated=False,
        )
        self.assertEqual(r["procedure"][0]["varname"], "FM")

    def test_non_string_value_is_error(self):
        with self.assertRaises(ProcedureNotationError):
            normalize_recipe({"version": 2, "procedure": [{"insertvar": ["FM"]}]})

    def test_varname_key_not_allowed_in_v2(self):
        with self.assertRaises(ProcedureNotationError):
            normalize_recipe({"version": 2, "procedure": [{"insertvar": "FM", "varname": "X"}]})


class TestCollect(unittest.TestCase):
    def _collect(self, vars_, *items):
        r = normalize_recipe({"version": 2, "vars": vars_, "procedure": list(items)})
        return collect_procedure_items(r, [], Path("r.yaml"))

    def test_value_is_looked_up(self):
        self.assertEqual(self._collect({"FM": _FM}, {"insertvar": "FM"}), [VarInsert("FM", _FM)])

    def test_undefined_is_skipped_with_warning(self):
        with self.assertLogs(level="WARNING") as cm:
            self.assertEqual(self._collect({}, {"insertvar": "NOPE"}), [])
        self.assertIn("NOPE", cm.output[0])

    def test_mapping_value_is_skipped(self):
        with self.assertLogs(level="WARNING"):
            self.assertEqual(self._collect({"FM": {"title": "x"}}, {"insertvar": "FM"}), [])

    def test_scalar_value_is_stringified(self):
        self.assertEqual(self._collect({"N": 3}, {"insertvar": "N"}), [VarInsert("N", "3")])


class TestExpandVar(unittest.TestCase):
    def test_source_marker_and_newline(self):
        out = expand_var(VarInsert("FM", "---\ntitle: X\n---"), Path("."))
        self.assertEqual(out, "<!-- source: var:FM -->\n---\ntitle: X\n---\n")

    def test_conditionals_are_evaluated(self):
        text = "a\n{{#if:WEB}}\nweb only\n{{#endif:WEB}}\nb\n"
        out = expand_var(VarInsert("X", text), Path("."), cond_vars={})
        self.assertNotIn("web only", out)
        out = expand_var(VarInsert("X", text), Path("."), cond_vars={"WEB": "1"})
        self.assertIn("web only", out)

    def test_frontmatter_is_stripped_for_pdf(self):
        merged = expand_var(VarInsert("FM", _FM), Path(".")) + "\n\n<!-- source: a.md -->\n# A\n"
        out, n = strip_frontmatter(merged)
        self.assertEqual(n, 1)
        self.assertNotIn("title: Foo", out)


class TestLint(unittest.TestCase):
    def _lint(self, recipe):
        normalized = normalize_recipe(dict(recipe), warn_deprecated=False)
        return lint(recipe, normalized, Path("r.yaml"), None)

    def test_undefined_var_warns(self):
        res = self._lint({"version": 2, "procedure": [{"insertvar": "FM"}]})
        self.assertTrue(any("insertvar FM" in w for w in res.warnings), res.warnings)

    def test_value_is_scanned_for_refs(self):
        res = self._lint({
            "version": 2, "vars": {"FM": "---\ntitle: {{v:TITLE}}\n---\n"},
            "procedure": [{"insertvar": "FM"}],
        })
        self.assertTrue(any("TITLE" in w and "vars.FM" in w for w in res.warnings), res.warnings)

    def test_param_used_only_by_insertvar_is_not_unused(self):
        res = self._lint({
            "version": 2, "params": {"FM": {"type": "string", "default": "x"}},
            "procedure": [{"insertvar": "FM"}],
        })
        self.assertFalse(any("params.FM" in w for w in res.warnings), res.warnings)


class TestMergeEndToEnd(unittest.TestCase):
    def test_merge_inserts_frontmatter_first(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "a_md.md").write_text("# A\n\nbody\n", encoding="utf-8")
            recipe = root / "r_recipe.yaml"
            recipe.write_text(textwrap.dedent("""\
                version: 2
                vars:
                  TITLE: Hello
                  FM: |
                    ---
                    title: "{{v:TITLE}}"
                    author: hiro
                    ---
                output:
                  targetbasefilename: r
                procedure:
                  - insertvar: FM
                  - insertmd: a_md.md
                  - insertvar: FM
                    when:
                      var: EXTRA
                """), encoding="utf-8")
            res = _run("merge", str(recipe), "--force", cwd=root)
            self.assertEqual(res.returncode, 0, res.stderr)
            merged = (root / "work_r_merged.md").read_text(encoding="utf-8")
            self.assertTrue(merged.startswith(
                '<!-- source: var:FM -->\n---\ntitle: "{{v:TITLE}}"\nauthor: hiro\n---\n'), merged)
            self.assertEqual(merged.count("source: var:FM"), 1)
            self.assertIn("# A", merged)

            res = _run("merge", str(recipe), "--force", "--var", "EXTRA=1", "--var", "TITLE=Bye", cwd=root)
            self.assertEqual(res.returncode, 0, res.stderr)
            merged = (root / "work_r_merged.md").read_text(encoding="utf-8")
            self.assertEqual(merged.count("source: var:FM"), 2)

    def test_merge_var_from_cli(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            recipe = root / "r_recipe.yaml"
            recipe.write_text(textwrap.dedent("""\
                version: 2
                output:
                  targetbasefilename: r
                procedure:
                  - insertvar: NOTE
                """), encoding="utf-8")
            res = _run("merge", str(recipe), "--force", "--var", "NOTE=from cli", cwd=root)
            self.assertEqual(res.returncode, 0, res.stderr)
            merged = (root / "work_r_merged.md").read_text(encoding="utf-8")
            self.assertEqual(merged, "<!-- source: var:NOTE -->\nfrom cli\n")


if __name__ == "__main__":
    unittest.main()
