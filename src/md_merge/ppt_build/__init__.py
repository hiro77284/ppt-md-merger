"""ppt_build: run the shared front half (pptpdfexport … render) once, then the
selected output tails (--pdf / --puremd / --githubmd / --notecom / --transfer).
With no output option it stops after render and keeps the rendered MD.

Each output corresponds to one existing pipeline command (``ppt_to_pdf`` etc.).
Running them together saves repeating the front half, which every ppt_to_*
pipeline shares unchanged.

``when.command`` / ``when.not_command`` in the recipe procedure are matched
against those equivalent commands, because the single merge run has to serve
every selected output. If the filtered procedure would differ between them,
the outputs cannot share one merge and the command stops with an error.
"""

from __future__ import annotations

import argparse
import logging

from md_merge._conditions import filter_procedure
from md_merge._output import EXIT_BAD_INPUT, EXIT_OK, setup_logging
from md_merge._procedure import ProcedureNotationError
from md_merge._pipeline import ALL_WORK_FILE_KEYS, run_pipeline
from md_merge.githubmd import run as run_githubmd
from md_merge.idcollect import run as run_idcollect
from md_merge.idresolve import run as run_idresolve
from md_merge.merge import run as run_merge
from md_merge.merge._recipe import load_yaml, resolve_input_path
from md_merge.notecomexport import run as run_notecomexport
from md_merge.pandoc import run as run_pandoc
from md_merge.ppt_to_pdf import check_pdf_collision
from md_merge.pptimgexport import run as run_pptimgexport
from md_merge.pptmdexport import run as run_pptmdexport
from md_merge.pptpdfexport import run as run_pptpdfexport
from md_merge.puremd import run as run_puremd
from md_merge.render import run as run_render
from md_merge.transfer import run as run_transfer

COMMAND = "ppt_build"

# Output flags (argparse dest) in the order they are reported.
OUTPUT_FLAGS = ("pdf", "puremd", "githubmd", "notecom", "transfer")

_FRONT_STEPS: list[tuple[str, object]] = [
    ("pptpdfexport", run_pptpdfexport),
    ("pptimgexport", run_pptimgexport),
    ("pptmdexport",  run_pptmdexport),
    ("merge",        run_merge),
    ("idcollect",    run_idcollect),
    ("idresolve",    run_idresolve),
    ("render",       run_render),
]


def selected_outputs(args: argparse.Namespace) -> list[str]:
    return [name for name in OUTPUT_FLAGS if getattr(args, name, False)]


def build_steps(outputs: list[str]) -> list[tuple[str, object]]:
    """Front half + the tails the selected outputs need, in dependency order.

    pandoc runs last: it is the slowest and most failure-prone step, so the MD
    deliverables already exist even when the PDF fails.
    """
    sel = set(outputs)
    steps = list(_FRONT_STEPS)
    if sel & {"puremd", "githubmd", "notecom", "transfer"}:
        steps.append(("puremd", run_puremd))
    if "githubmd" in sel:
        steps.append(("githubmd", run_githubmd))
    if "notecom" in sel:
        steps.append(("notecomexport", run_notecomexport))
    if "transfer" in sel:
        steps.append(("transfer", run_transfer))
    if "pdf" in sel:
        steps.append(("pandoc", run_pandoc))
    return steps


def work_file_keys(outputs: list[str]) -> tuple[str, ...]:
    """Intermediate files to delete: every work key except the deliverables.

    Mirrors the single-output pipelines: ppt_to_pdf keeps the rendered MD,
    ppt_to_puremd / ppt_to_githubmd / ppt_to_notecom keep the puremd MD, and a
    transfer-only run (ppt_to_transfer) keeps neither.
    """
    sel = set(outputs)
    keep: set[str] = set()
    if not sel or "pdf" in sel:  # 出力指定なし = render まで（rendered MD が成果物）
        keep.add("renderedfilename")
    if sel & {"puremd", "githubmd", "notecom"}:
        keep.add("puremdfilename")
    return tuple(k for k in ALL_WORK_FILE_KEYS if k not in keep)


def transfer_source_key(outputs: list[str]) -> str | None:
    """--transfer sends the GitHub MD when --githubmd is selected, else the puremd MD."""
    if "transfer" not in outputs:
        return None
    return "githubmdfilename" if "githubmd" in outputs else "puremdfilename"


def equivalent_commands(outputs: list[str]) -> list[str]:
    """The ppt_to_* commands whose deliverables this run produces (for when.command)."""
    sel = set(outputs)
    cmds: list[str] = []
    # 出力指定なし（render まで）は ppt_to_pdf と同じ rendered MD を作るので ppt_to_pdf で照合する
    if not sel or "pdf" in sel:
        cmds.append("ppt_to_pdf")
    if "puremd" in sel:
        cmds.append("ppt_to_puremd")
    if "githubmd" in sel:
        cmds.append("ppt_to_githubmd")
    if "notecom" in sel:
        cmds.append("ppt_to_notecom")
    # ppt_to_puremd / ppt_to_githubmd --transfer stay those commands; a transfer
    # without either MD output is what ppt_to_transfer does.
    if "transfer" in sel and not sel & {"puremd", "githubmd"}:
        cmds.append("ppt_to_transfer")
    return cmds


def resolve_condition_command(args: argparse.Namespace, commands: list[str]) -> tuple[int, str | None]:
    """Pick the command name to match when.command against, or fail if the
    equivalent commands would select different procedure items.

    Returns (exit code, command name). A missing / unreadable recipe is left to
    the later steps' normal error handling (returns the first command).
    """
    yaml_path = resolve_input_path(args)
    if yaml_path is None or not yaml_path.exists() or len(commands) == 1:
        return EXIT_OK, commands[0]
    try:
        recipe = load_yaml(yaml_path)
    except ProcedureNotationError:
        raise
    except Exception:  # noqa: BLE001  読み込み失敗は後段の通常エラー処理に任せる
        return EXIT_OK, commands[0]
    results = {
        name: filter_procedure(recipe, argparse.Namespace(subcommand=name)).get("procedure")
        for name in commands
    }
    first = results[commands[0]]
    differing = [name for name in commands[1:] if results[name] != first]
    if differing:
        logging.error(
            "procedure の when.command / not_command により、%s で使う procedure が出力ごとに異なります"
            "（%s と %s）。1 回の merge で両方は作れないので、該当する ppt_to_* を別々に実行してください",
            COMMAND, commands[0], ", ".join(differing),
        )
        return EXIT_BAD_INPUT, None
    return EXIT_OK, commands[0]


def run(args: argparse.Namespace) -> int:
    setup_logging(args.log_level)
    outputs = selected_outputs(args)

    code, cond_cmd = resolve_condition_command(args, equivalent_commands(outputs))
    if code != EXIT_OK:
        return code
    args.condition_command = cond_cmd
    logging.info("[%s] outputs: %s", COMMAND, ", ".join(outputs) or "rendered (render まで)")

    if "pdf" in outputs:
        code = check_pdf_collision(args)
        if code != EXIT_OK:
            return code

    return run_pipeline(
        args,
        command=COMMAND,
        steps=build_steps(outputs),
        work_file_keys=work_file_keys(outputs),
        transfer_source_key=transfer_source_key(outputs),
    )
