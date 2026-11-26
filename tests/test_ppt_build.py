"""ppt_build（render まで 1 回 + 選んだ出力だけ実行）のテスト。

実行: python -m unittest discover -s tests
"""

import argparse
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest import mock

import md_merge.ppt_build as pb
from md_merge._conditions import build_context
from md_merge._output import EXIT_BAD_INPUT, EXIT_OK

_FRONT = ["pptpdfexport", "pptimgexport", "pptmdexport", "merge", "idcollect", "idresolve", "render"]


def _names(outputs):
    return [n for n, _ in pb.build_steps(outputs)]


def _args(**kw):
    base = {name: False for name in pb.OUTPUT_FLAGS}
    base.update(input=None, log_level="warning")
    base.update(kw)
    return argparse.Namespace(**base)


class TestSteps(unittest.TestCase):
    def test_single_outputs_match_legacy_pipelines(self):
        self.assertEqual(_names(["pdf"]), _FRONT + ["pandoc"])
        self.assertEqual(_names(["puremd"]), _FRONT + ["puremd"])
        self.assertEqual(_names(["githubmd"]), _FRONT + ["puremd", "githubmd"])
        self.assertEqual(_names(["notecom"]), _FRONT + ["puremd", "notecomexport"])
        self.assertEqual(_names(["transfer"]), _FRONT + ["puremd", "transfer"])

    def test_combined_runs_front_once_and_pandoc_last(self):
        names = _names(["pdf", "githubmd", "notecom", "transfer"])
        self.assertEqual(names, _FRONT + ["puremd", "githubmd", "notecomexport", "transfer", "pandoc"])
        self.assertEqual(names.count("render"), 1)
        self.assertEqual(names.count("puremd"), 1)


class TestWorkFiles(unittest.TestCase):
    def test_deliverables_kept(self):
        self.assertIn("puremdfilename", pb.work_file_keys(["pdf"]))
        self.assertNotIn("renderedfilename", pb.work_file_keys(["pdf"]))
        for out in ("puremd", "githubmd", "notecom"):
            keys = pb.work_file_keys([out])
            self.assertNotIn("puremdfilename", keys)
            self.assertIn("renderedfilename", keys)
        # transfer だけなら ppt_to_transfer と同じく puremd MD も作業ファイル
        self.assertIn("puremdfilename", pb.work_file_keys(["transfer"]))
        both = pb.work_file_keys(["pdf", "githubmd"])
        self.assertNotIn("puremdfilename", both)
        self.assertNotIn("renderedfilename", both)


class TestTransferSource(unittest.TestCase):
    def test_source(self):
        self.assertIsNone(pb.transfer_source_key(["pdf", "puremd"]))
        self.assertEqual(pb.transfer_source_key(["transfer"]), "puremdfilename")
        self.assertEqual(pb.transfer_source_key(["puremd", "transfer"]), "puremdfilename")
        self.assertEqual(pb.transfer_source_key(["githubmd", "transfer"]), "githubmdfilename")
        self.assertEqual(pb.transfer_source_key(["puremd", "githubmd", "transfer"]), "githubmdfilename")


class TestEquivalentCommands(unittest.TestCase):
    def test_mapping(self):
        self.assertEqual(pb.equivalent_commands(["pdf", "githubmd"]), ["ppt_to_pdf", "ppt_to_githubmd"])
        self.assertEqual(pb.equivalent_commands(["transfer"]), ["ppt_to_transfer"])
        self.assertEqual(pb.equivalent_commands(["githubmd", "transfer"]), ["ppt_to_githubmd"])
        self.assertEqual(pb.equivalent_commands(["notecom", "transfer"]), ["ppt_to_notecom", "ppt_to_transfer"])

    def test_condition_command_used_for_context(self):
        ctx = build_context(argparse.Namespace(subcommand="ppt_build", condition_command="ppt_to_pdf"))
        self.assertEqual(ctx.command, "ppt_to_pdf")
        self.assertEqual(build_context(argparse.Namespace(subcommand="merge")).command, "merge")


class TestConditionConsistency(unittest.TestCase):
    def _recipe(self, d: Path, when_yaml: str) -> Path:
        p = d / "r.yaml"
        p.write_text(textwrap.dedent(f"""\
            version: 4
            procedure:
              - insertmd: a.md
              - insertmd: b.md
                when: {when_yaml}
            """), encoding="utf-8")
        return p

    def test_same_procedure_ok(self):
        with tempfile.TemporaryDirectory() as td:
            # どちらの出力でも b.md は残る
            r = self._recipe(Path(td), "{not_command: ppt_to_notecom}")
            code, cmd = pb.resolve_condition_command(
                _args(input=str(r)), ["ppt_to_pdf", "ppt_to_githubmd"])
            self.assertEqual((code, cmd), (EXIT_OK, "ppt_to_pdf"))

    def test_different_procedure_error(self):
        with tempfile.TemporaryDirectory() as td:
            r = self._recipe(Path(td), "{not_command: ppt_to_pdf}")
            with self.assertLogs(level="ERROR"):
                code, cmd = pb.resolve_condition_command(
                    _args(input=str(r)), ["ppt_to_pdf", "ppt_to_githubmd"])
            self.assertEqual((code, cmd), (EXIT_BAD_INPUT, None))

    def test_single_command_skips_check(self):
        code, cmd = pb.resolve_condition_command(_args(input="missing.yaml"), ["ppt_to_pdf"])
        self.assertEqual((code, cmd), (EXIT_OK, "ppt_to_pdf"))


class TestRun(unittest.TestCase):
    def test_no_outputs_runs_until_render(self):
        with mock.patch.object(pb, "run_pipeline", return_value=0) as rp, \
             mock.patch.object(pb, "check_pdf_collision") as cc:
            args = _args()
            self.assertEqual(pb.run(args), 0)
        kw = rp.call_args.kwargs
        self.assertEqual([n for n, _ in kw["steps"]], _FRONT)
        self.assertNotIn("renderedfilename", kw["work_file_keys"])
        self.assertIsNone(kw["transfer_source_key"])
        self.assertEqual(args.condition_command, "ppt_to_pdf")
        cc.assert_not_called()

    def test_run_pipeline_args(self):
        with mock.patch.object(pb, "run_pipeline", return_value=0) as rp:
            args = _args(githubmd=True, transfer=True)
            self.assertEqual(pb.run(args), 0)
        kw = rp.call_args.kwargs
        self.assertEqual(kw["command"], "ppt_build")
        self.assertEqual(kw["transfer_source_key"], "githubmdfilename")
        self.assertEqual([n for n, _ in kw["steps"]][-1], "transfer")
        self.assertEqual(args.condition_command, "ppt_to_githubmd")

    def test_pdf_runs_collision_check(self):
        with mock.patch.object(pb, "run_pipeline", return_value=0), \
             mock.patch.object(pb, "check_pdf_collision", return_value=EXIT_BAD_INPUT) as cc:
            self.assertEqual(pb.run(_args(pdf=True)), EXIT_BAD_INPUT)
        cc.assert_called_once()


class TestPptx(unittest.TestCase):
    def test_steps_pptmerge_before_pandoc(self):
        self.assertEqual(_names(["pptx"]), _FRONT + ["pptmerge"])
        self.assertEqual(
            _names(["pdf", "githubmd", "pptx"]),
            _FRONT + ["puremd", "githubmd", "pptmerge", "pandoc"],
        )

    def test_pptx_is_not_an_md_output(self):
        # --pptx だけなら MD 側は「render まで」と同じ扱い
        self.assertEqual(pb.work_file_keys(["pptx"]), pb.work_file_keys([]))
        self.assertEqual(pb.equivalent_commands(["pptx"]), ["ppt_to_pdf"])
        self.assertEqual(pb.equivalent_commands(["githubmd", "pptx"]), ["ppt_to_githubmd"])
        self.assertIsNone(pb.transfer_source_key(["pptx"]))

    def test_pptx_step_matches_pptmerge_and_restores_args(self):
        seen = {}

        def fake_pptmerge(a):
            seen["cmd"] = a.condition_command
            seen["no_check"] = a.no_check
            a.cropsrc_pptx_override = {"x.pptx": "x_preprocessed.pptx"}
            return EXIT_OK

        args = _args(pptx=True, condition_command="ppt_to_pdf", no_check=True, pptx_no_check=False,
                     cropsrc_pptx_override={"g.pptx": "g_preprocessed.pptx"})
        with mock.patch.object(pb, "run_pptmerge", side_effect=fake_pptmerge):
            self.assertEqual(pb.run_pptx_step(args), EXIT_OK)
        self.assertEqual(seen, {"cmd": "pptmerge", "no_check": False})
        self.assertEqual(args.condition_command, "ppt_to_pdf")
        self.assertTrue(args.no_check)
        self.assertEqual(args.cropsrc_pptx_override,
                         {"x.pptx": "x_preprocessed.pptx", "g.pptx": "g_preprocessed.pptx"})

    def test_pptx_procedure_filtered_as_pptmerge(self):
        from md_merge._conditions import filter_procedure
        recipe = {"version": 4, "procedure": [
            {"operation": "insertpptx", "pptxfilename": "a.pptx"},
            {"operation": "insertpptx", "pptxfilename": "b.pptx", "when": {"command": "pptmerge"}},
        ]}
        ns = argparse.Namespace(subcommand="ppt_build", condition_command=pb.PPTX_COMMAND)
        names = [i["pptxfilename"] for i in filter_procedure(recipe, ns)["procedure"]]
        self.assertEqual(names, ["a.pptx", "b.pptx"])

    def test_no_powerpoint_stops_before_pipeline(self):
        with mock.patch.object(pb, "run_pipeline", return_value=0) as rp, \
             mock.patch.object(pb, "powerpoint_unavailable_reason", return_value="no win32com"):
            with self.assertLogs(level="ERROR"):
                self.assertEqual(pb.run(_args(pdf=True, pptx=True)), EXIT_BAD_INPUT)
        rp.assert_not_called()

    def test_dry_run_skips_powerpoint_check(self):
        with mock.patch.object(pb, "run_pipeline", return_value=0) as rp, \
             mock.patch.object(pb, "powerpoint_unavailable_reason", return_value="no win32com"):
            self.assertEqual(pb.run(_args(pptx=True, dry_run=True)), EXIT_OK)
        self.assertEqual([n for n, _ in rp.call_args.kwargs["steps"]], _FRONT + ["pptmerge"])

    def test_pptx_only_options_warn_without_pptx(self):
        with mock.patch.object(pb, "run_pipeline", return_value=0):
            with self.assertLogs(level="WARNING") as cm:
                pb.run(_args(pptxnumbering="idresolve", delete_csl="on"))
        text = "\n".join(cm.output)
        self.assertIn("--pptxnumbering", text)
        self.assertIn("--deletecsl", text)

    def test_cli_parses_pptx(self):
        from md_merge.__main__ import _make_parser
        a = _make_parser().parse_args(["ppt_build", "r.yaml", "--pdf", "--pptx", "--pptxnumbering", "idresolve"])
        self.assertTrue(a.pptx)
        self.assertEqual(a.pptxnumbering, "idresolve")


if __name__ == "__main__":
    unittest.main()
