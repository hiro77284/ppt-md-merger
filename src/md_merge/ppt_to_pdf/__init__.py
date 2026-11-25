from __future__ import annotations

import argparse
import logging
from pathlib import Path

from md_merge._cropsrc import cropsrc_pdf_paths
from md_merge._output import EXIT_BAD_INPUT, EXIT_OK, setup_logging
from md_merge._pipeline import run_pipeline
from md_merge.idcollect import run as run_idcollect
from md_merge.idresolve import run as run_idresolve
from md_merge.merge import run as run_merge
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

# The PDF is the deliverable; the rendered MD is kept as well (pandoc's input,
# handy for inspecting the PDF source).
_WORK_FILE_KEYS = (
    "mdfilename",
    "idcollectfilename",
    "idresolvedfilename",
)

_STEPS: list[tuple[str, object]] = [
    ("pptpdfexport",     run_pptpdfexport),
    ("pptimgexport",     run_pptimgexport),
    ("pptmdexport",      run_pptmdexport),
    ("merge",            run_merge),
    ("idcollect",        run_idcollect),
    ("idresolve",        run_idresolve),
    ("render",           run_render),
    ("pandoc",           run_pandoc),
]


def check_pdf_collision(args: argparse.Namespace) -> int:
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
                "source.cropsrc の PDF と成果物 PDF（output.pdffilename）が同じパスです: %s"
                " — pandoc の出力がスライド PDF を上書きしてしまうため、"
                "source.cropsrc[].pdf か output.pdffilename / targetbasefilename を別名にしてください",
                out_pdf,
            )
            return EXIT_BAD_INPUT
    return EXIT_OK


def run(args: argparse.Namespace) -> int:
    setup_logging(args.log_level)
    code = check_pdf_collision(args)
    if code != EXIT_OK:
        return code
    return run_pipeline(
        args,
        command="ppt_to_pdf",
        steps=_STEPS,
        work_file_keys=_WORK_FILE_KEYS,
    )
