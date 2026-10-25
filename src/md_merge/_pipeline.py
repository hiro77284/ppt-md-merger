"""Shared runner for the ppt_to_* pipeline subcommands.

`ppt_to_transfer` and `ppt_to_puremd` share the same step machinery: a fixed
sequence of sub-runs, a pre-merge insertmd drift gate, optional preprocessing,
work-file cleanup, and an end-of-run warning summary. The only differences are
the step list, which output files count as deliverables (and so must survive
cleanup), and whether a transfer source key is seeded. Those are passed in by
the thin command wrappers.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from md_merge._output import EXIT_OK, setup_logging
from md_merge._preprocess import apply_preprocess, cleanup_preprocessed
from md_merge.checkverify import gate as checkverify_gate
from md_merge.merge import preflight_clear_confirm
from md_merge.merge._recipe import (
    load_yaml,
    resolve_input_path,
    resolve_out_file,
    resolve_workdir,
)

# Output-file recipe keys produced by the pipeline steps. A given pipeline keeps
# the subset that are its deliverables and deletes the rest as work files.
_ALL_WORK_FILE_KEYS = (
    "mdfilename",
    "idcollectfilename",
    "idresolvedfilename",
    "renderedfilename",
    "puremdfilename",
    "resourcepathfilename",
)


class _WarningCollector(logging.Handler):
    """Logging handler that collects WARNING+ records for end-of-run summary."""

    def __init__(self) -> None:
        super().__init__(logging.WARNING)
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.append(self.format(record))


def _cleanup_work_files(args: argparse.Namespace, command: str, work_file_keys: tuple[str, ...]) -> None:
    yaml_path = resolve_input_path(args)
    if yaml_path is None or not yaml_path.exists():
        return
    recipe = load_yaml(yaml_path)
    cli_workdir = Path(args.workdir).resolve() if getattr(args, "workdir", None) else None
    workdir = resolve_workdir(recipe, yaml_path, cli_workdir)

    candidates: list[Path] = []
    for key in work_file_keys:
        p = resolve_out_file(recipe, key, yaml_path, workdir)
        if p is not None:
            candidates.append(p)

    logging.info("[%s] deleting work-files", command)
    deleted = 0
    for p in candidates:
        if p.exists():
            try:
                p.unlink()
                logging.info("[%s] deleted: %s", command, p.name)
                deleted += 1
            except OSError as e:
                logging.warning("[%s] work file 削除失敗: %s: %s", command, p, e)
    if deleted >= 1:
        logging.info("[%s] use --keep-work option to preserve work-files", command)


def _fill_defaults(args: argparse.Namespace, transfer_source_key: str | None) -> None:
    for attr, default in (
        ("no_copy_images",  False),
        ("image_dir",       None),
        ("flatten_images",  False),
        ("overwrite_images", False),
        ("strict",          False),
        ("ppquit",          False),
        ("closepptx",       True),
        ("preprocess",      False),
        ("delete_csl",      None),
        ("delete_csp",      None),
    ):
        if not hasattr(args, attr):
            setattr(args, attr, default)
    # The transfer step consumes the puremd-processed MD (rather than the rendered
    # MD) unless transfer.inputmd is set explicitly. Pipelines without a transfer
    # step leave this unset.
    if transfer_source_key is not None:
        args.transfer_source_key = transfer_source_key


def _step_print(args: argparse.Namespace, command: str, name: str, status: str, exit_code: int | None = None) -> None:
    if getattr(args, "json", False):
        payload: dict = {"command": command, "step": name, "status": status}
        if exit_code is not None:
            payload["exit_code"] = exit_code
        print(json.dumps(payload, ensure_ascii=False))
    else:
        if exit_code is not None:
            msg = f"[{command}] {name} FAILED (exit {exit_code})"
            print(msg)
            logging.error("%s", msg)
        else:
            msg = f"[{command}] {name} {status}"
            print(msg)
            logging.info("%s", msg)


def run_pipeline(
    args: argparse.Namespace,
    *,
    command: str,
    steps: list[tuple[str, object]],
    work_file_keys: tuple[str, ...],
    transfer_source_key: str | None = None,
) -> int:
    """Drive a ppt_to_* pipeline.

    command            display name used in log prefixes and --json output
    steps              ordered (name, run_fn) sequence to execute
    work_file_keys     output-file recipe keys to delete during cleanup
                       (a pipeline's deliverables are simply omitted here)
    transfer_source_key seeds args.transfer_source_key for a trailing transfer
                       step; None for pipelines that do not transfer
    """
    setup_logging(args.log_level)
    sys.stdout.reconfigure(line_buffering=True)
    _fill_defaults(args, transfer_source_key)

    # 全処理を始める前に clear-dir-before-merge の確認を済ませる（merge を含む場合のみ）
    if any(name == "merge" for name, _ in steps):
        code = preflight_clear_confirm(args)
        if code != EXIT_OK:
            return code

    collector = _WarningCollector()
    collector.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
    logging.getLogger().addHandler(collector)

    # The pre-merge drift gate owns the insertmd check in pipelines; disable the
    # merge step's own check so it is not run twice.
    run_gate = not getattr(args, "no_check", False)
    args.no_check = True

    try:
        if getattr(args, "preprocess", False) and not getattr(args, "dry_run", False):
            _step_print(args, command, "preprocess", "...")
            code = apply_preprocess(args)
            if code != EXIT_OK:
                _step_print(args, command, "preprocess", "FAILED", exit_code=code)
                return code
            _step_print(args, command, "preprocess", "OK")

        for name, step_run in steps:
            if name == "merge" and run_gate:
                _step_print(args, command, "checkverify", "...")
                gcode = checkverify_gate(args)
                if gcode != EXIT_OK:
                    _step_print(args, command, "checkverify", "FAILED", exit_code=gcode)
                    return gcode
                _step_print(args, command, "checkverify", "OK")
            _step_print(args, command, name, "...")
            code = step_run(args)
            if code != EXIT_OK:
                _step_print(args, command, name, "FAILED", exit_code=code)
                return code
            _step_print(args, command, name, "OK")
    finally:
        logging.getLogger().removeHandler(collector)

    if not getattr(args, "keep_work", False):
        _cleanup_work_files(args, command, work_file_keys)
        cleanup_preprocessed(args)

    if collector.messages:
        if getattr(args, "json", False):
            print(json.dumps({
                "command": command,
                "status": "warnings",
                "warnings": collector.messages,
            }, ensure_ascii=False))
        else:
            print("\n======== 警告まとめ ========")
            for msg in collector.messages:
                print(msg)
            print("============================\n")

    if not getattr(args, "json", False):
        print("\n========================================")
        print(f"  {command} 完了")
        print("========================================\n")

    return EXIT_OK
