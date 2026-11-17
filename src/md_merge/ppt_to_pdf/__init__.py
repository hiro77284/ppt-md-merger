from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from md_merge._cropsrc import cropsrc_pdf_paths
from md_merge._output import EXIT_BAD_INPUT, EXIT_OK, print_done, setup_logging
from md_merge._preprocess import apply_preprocess, cleanup_preprocessed
from md_merge.checkverify import gate as checkverify_gate
from md_merge.idcollect import run as run_idcollect
from md_merge.idresolve import run as run_idresolve
from md_merge.merge import preflight_clear_confirm, run as run_merge
from md_merge.merge._recipe import (
    load_yaml,
    resolve_input_path,
    resolve_out_file,
    resolve_workdir,
)
from md_merge.pandoc import run as run_pandoc
from md_merge.pptimgexport import run as run_pptimgexport
from md_merge.pptmdexport import run as run_pptmdexport
from md_merge.pptpdfexport import run as run_pptpdfexport
from md_merge.render import run as run_render

_WORK_FILE_KEYS = (
    "mdfilename",
    "idcollectfilename",
    "idresolvedfilename",
)


def _cleanup_work_files(args: argparse.Namespace) -> None:
    yaml_path = resolve_input_path(args)
    if yaml_path is None or not yaml_path.exists():
        return
    recipe = load_yaml(yaml_path)
    cli_workdir = Path(args.workdir).resolve() if getattr(args, "workdir", None) else None
    workdir = resolve_workdir(recipe, yaml_path, cli_workdir)

    candidates: list[Path] = []
    for key in _WORK_FILE_KEYS:
        p = resolve_out_file(recipe, key, yaml_path, workdir)
        if p is not None:
            candidates.append(p)

    logging.info("[ppt_to_pdf] deleting work-files")
    deleted = 0
    for p in candidates:
        if p.exists():
            try:
                p.unlink()
                logging.info("[ppt_to_pdf] deleted: %s", p.name)
                deleted += 1
            except OSError as e:
                logging.warning("[ppt_to_pdf] work file 削除失敗: %s: %s", p, e)
    if deleted >= 1:
        logging.info("[ppt_to_pdf] use --keep-work option to preserve work-files")


_STEPS: list[tuple[str, ...]] = [
    ("pptpdfexport",     run_pptpdfexport),
    ("pptimgexport",     run_pptimgexport),
    ("pptmdexport",      run_pptmdexport),
    ("merge",            run_merge),
    ("idcollect",        run_idcollect),
    ("idresolve",        run_idresolve),
    ("render",           run_render),
    ("pandoc",           run_pandoc),
]


def _fill_defaults(args: argparse.Namespace) -> None:
    for attr, default in (
        ("no_copy_images", False),
        ("image_dir", None),
        ("flatten_images", False),
        ("strict", False),
        ("ppquit", False),
        ("closepptx", True),   # ppt_to_pdf では必ず Close して COM ファイルロックを解放する
        ("preprocess", False),
        ("delete_csl", None),
        ("delete_csp", None),
    ):
        if not hasattr(args, attr):
            setattr(args, attr, default)


def _check_pdf_collision(args: argparse.Namespace) -> int:
    """cropsrc のスライド PDF と最終成果物 PDF が同じパスなら中止する。

    同じだと pandoc の出力がスライド PDF を上書きし、次回の pptpdfexport が
    「最新」と誤判定してスキップ → pptimgexport が成果物 PDF からスライドを
    切り出そうとしてページ不足で失敗する。
    """
    yaml_path = resolve_input_path(args)
    if yaml_path is None or not yaml_path.exists():
        return EXIT_OK  # 入力不正は後段の通常エラー処理に任せる
    try:
        recipe = load_yaml(yaml_path)
    except Exception:  # noqa: BLE001  読み込み失敗も後段に委ねる
        return EXIT_OK
    cli_workdir = Path(args.workdir).resolve() if getattr(args, "workdir", None) else None
    workdir = resolve_workdir(recipe, yaml_path, cli_workdir)
    out_pdf = resolve_out_file(recipe, "pdffilename", yaml_path, workdir)
    if out_pdf is None:
        return EXIT_OK
    out_pdf = out_pdf.resolve()
    for slide_pdf in cropsrc_pdf_paths(recipe, yaml_path, workdir):
        if slide_pdf.resolve() == out_pdf:
            logging.error(
                "input.cropsrc の PDF と成果物 PDF（output.pdffilename）が同じパスです: %s"
                " — pandoc の出力がスライド PDF を上書きしてしまうため、"
                "input.cropsrc[].pdf か output.pdffilename / targetbasefilename を別名にしてください",
                out_pdf,
            )
            return EXIT_BAD_INPUT
    return EXIT_OK


def _step_print(args: argparse.Namespace, name: str, status: str, exit_code: int | None = None) -> None:
    if getattr(args, "json", False):
        payload: dict = {"command": "ppt_to_pdf", "step": name, "status": status}
        if exit_code is not None:
            payload["exit_code"] = exit_code
        print(json.dumps(payload, ensure_ascii=False))
    else:
        if exit_code is not None:
            msg = f"[ppt_to_pdf] {name} FAILED (exit {exit_code})"
            print(msg)
            logging.error("%s", msg)
        else:
            msg = f"[ppt_to_pdf] {name} {status}"
            print(msg)
            logging.info("%s", msg)


def run(args: argparse.Namespace) -> int:
    setup_logging(args.log_level)
    sys.stdout.reconfigure(line_buffering=True)
    _fill_defaults(args)

    code = _check_pdf_collision(args)
    if code != EXIT_OK:
        return code

    # 全処理を始める前に clear-dir-before-merge の確認を済ませる（承認後は後段 merge が再確認しない）
    code = preflight_clear_confirm(args)
    if code != EXIT_OK:
        return code

    if getattr(args, "preprocess", False) and not getattr(args, "dry_run", False):
        _step_print(args, "preprocess", "...")
        code = apply_preprocess(args)
        if code != EXIT_OK:
            _step_print(args, "preprocess", "FAILED", exit_code=code)
            return code
        _step_print(args, "preprocess", "OK")

    # The pre-merge drift gate owns the insertmd check in pipelines; disable the
    # merge step's own check so it is not run twice.
    run_gate = not getattr(args, "no_check", False)
    args.no_check = True

    for name, step_run in _STEPS:
        if name == "merge" and run_gate:
            _step_print(args, "checkverify", "...")
            gcode = checkverify_gate(args)
            if gcode != EXIT_OK:
                _step_print(args, "checkverify", "FAILED", exit_code=gcode)
                return gcode
            _step_print(args, "checkverify", "OK")
        _step_print(args, name, "...")
        code = step_run(args)
        if code != EXIT_OK:
            _step_print(args, name, "FAILED", exit_code=code)
            return code
        _step_print(args, name, "OK")
    if not getattr(args, "keep_work", False):
        _cleanup_work_files(args)
        cleanup_preprocessed(args)
    if not getattr(args, "json", False):
        print_done("ppt_to_pdf")
    return EXIT_OK
