from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from md_merge._output import EXIT_OK, setup_logging
from md_merge.condblockprocess import run as run_condblockprocess
from md_merge.idcollect import run as run_idcollect
from md_merge.idresolve import run as run_idresolve
from md_merge.merge import run as run_merge
from md_merge.merge._recipe import (
    load_yaml,
    resolve_condblock_output,
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
    "resourcepathfilename",
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
    cond_out = resolve_condblock_output(recipe.get("pandoc") or {}, recipe, yaml_path, workdir)
    if cond_out is not None:
        candidates.append(cond_out)

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


def _run_condblockprocess_if_configured(args: argparse.Namespace) -> int:
    yaml_path = resolve_input_path(args)
    if yaml_path is None or not yaml_path.exists():
        return run_condblockprocess(args)
    recipe = load_yaml(yaml_path)
    if not (recipe.get("pandoc") or {}).get("conditional-process-input"):
        logging.info("[ppt_to_pdf] condblockprocess: conditional-process-input 未設定 — スキップ")
        return EXIT_OK
    return run_condblockprocess(args)


_STEPS: list[tuple[str, ...]] = [
    ("pptpdfexport",     run_pptpdfexport),
    ("pptimgexport",     run_pptimgexport),
    ("pptmdexport",      run_pptmdexport),
    ("merge",            run_merge),
    ("idcollect",        run_idcollect),
    ("idresolve",        run_idresolve),
    ("render",           run_render),
    ("condblockprocess", _run_condblockprocess_if_configured),
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
    ):
        if not hasattr(args, attr):
            setattr(args, attr, default)


def _step_print(args: argparse.Namespace, name: str, status: str, exit_code: int | None = None) -> None:
    if getattr(args, "json", False):
        payload: dict = {"command": "ppt_to_pdf", "step": name, "status": status}
        if exit_code is not None:
            payload["exit_code"] = exit_code
        print(json.dumps(payload, ensure_ascii=False))
    else:
        if exit_code is not None:
            print(f"[ppt_to_pdf] {name} FAILED (exit {exit_code})")
        else:
            print(f"[ppt_to_pdf] {name} {status}")


def run(args: argparse.Namespace) -> int:
    setup_logging(args.log_level)
    sys.stdout.reconfigure(line_buffering=True)
    _fill_defaults(args)
    for name, step_run in _STEPS:
        _step_print(args, name, "...")
        code = step_run(args)
        if code != EXIT_OK:
            _step_print(args, name, "FAILED", exit_code=code)
            return code
        _step_print(args, name, "OK")
    if not getattr(args, "keep_work", False):
        _cleanup_work_files(args)
    if not getattr(args, "json", False):
        print("\n========================================")
        print("  ppt_to_pdf 完了")
        print("========================================\n")
    return EXIT_OK
