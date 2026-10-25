"""Shared --preprocess support for the ppt_to_pdf / ppt_to_transfer pipelines.

When --preprocess is given, each ``input.cropsrc.pptx`` is run through a single-file
pptmerge (procedure ignored; one ``insertpptx`` with ``slides: all``) applying
**一般マーカー処理のみ**（``#CSP#`` / ``#TEMP#`` / ``#MEMO#`` / ``#CHAPT#`` 等、
``--deletecsp`` を含む）, producing ``<stem>_preprocessed.pptx`` in
``output.outputdir``. The pptx-consuming steps (pptpdfexport / pptimgexport /
pptmdexport) then *read* the preprocessed copy instead of the original, while output
path resolution (export-note / export-image dirs, PDF names) stays based on the
original pptx location.

CSL マーカー（``#CSL#``）はここでは**一切処理しない**。CSL スライド削除は pptmerge の
最後（結合済み pptx）でのみ行うという全体方針によるもので、``indexer.deletecsl`` や
``--deletecsl`` を指定しても前処理の挙動は変わらない。

Windows only — preprocessing drives PowerPoint via pptmerge (win32com).
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from md_merge._cropsrc import cropsrc_entries, resolve_cropsrc_path
from md_merge._output import EXIT_BAD_INPUT, EXIT_FAILURE, EXIT_NOT_FOUND, EXIT_OK
from md_merge.merge._recipe import load_recipe, resolve_input_path, resolve_workdir
from md_merge.pptmerge._config import resolve_base

_OVERRIDE_ATTR = "cropsrc_pptx_override"


def cropsrc_read_path(args: argparse.Namespace, resolved_pptx: Path) -> Path:
    """Return the preprocessed pptx to *read* in place of *resolved_pptx*, if any.

    Only the content read is redirected. Callers must keep using the original
    *resolved_pptx* for output path resolution and filename placeholders.
    """
    override = getattr(args, _OVERRIDE_ATTR, None)
    if override:
        repl = override.get(str(resolved_pptx))
        if repl:
            return Path(repl)
    return resolved_pptx


def _output_dir(recipe: dict, yaml_path: Path, workdir: Path | None) -> Path:
    base = resolve_base(yaml_path, workdir)
    outdir_val = (recipe.get("output") or {}).get("outputdir")
    if outdir_val:
        p = Path(str(outdir_val))
        return p if p.is_absolute() else (base / p).resolve()
    return base


def _resolve_bool_opt(cli_val: str | None, recipe_val: bool) -> bool:
    """CLI ``on`` / ``off`` overrides the recipe value; otherwise use the recipe (default False)."""
    if cli_val == "on":
        return True
    if cli_val == "off":
        return False
    return bool(recipe_val)


def preprocessed_name(src: Path) -> str:
    """`foo.pptx` -> `foo_preprocessed.pptx`."""
    return f"{src.stem}_preprocessed{src.suffix}"


def build_preprocess_config(
    src: Path, outdir: Path, out_name: str, deletecsp: bool,
    vars_map: dict | None = None,
) -> dict:
    """Synthetic single-file pptmerge config (recipe procedure ignored).

    個別 pptx には**一般マーカー処理のみ**を掛ける。CSL マーカーは残し、CSL スライド
    削除は結合済み pptx に対してのみ行う（``csl_mode="keep"`` で呼び出す）。
    """
    return {
        "output": {"outputdir": str(outdir), "pptxfilename": out_name, "force": True},
        "input": {"dirs": ["."]},
        "indexer": {"pptxnumbering": "no", "deletecsp": deletecsp},
        "vars": dict(vars_map or {}),
        "procedure": [{"operation": "insertpptx", "pptxfilename": str(src), "slides": "all"}],
    }


def _generate_preprocessed(
    yaml_path: Path,
    workdir: Path | None,
    sources: list[Path],
    deletecsp: bool,
    vars_map: dict,
    outdir: Path,
) -> tuple[dict[str, str] | None, int]:
    """Preprocess every path in *sources* (deduped) into ``<stem>_preprocessed.pptx``.

    Each preprocessed copy is written to *outdir*. Returns
    ``({resolved_original: preprocessed}, EXIT_OK)`` on success, or ``(None, EXIT_*)``.
    """
    try:
        from md_merge.pptmerge._config import ConfigError
        from md_merge.pptmerge._merger import merge_pptx, resolve_merge_log_path
        from md_merge.pptmerge._slide_titles import postprocess_after_merge
    except ImportError as e:
        logging.error("前処理に必要なモジュールを読み込めません（Windows + pywin32 が必要）: %s", e)
        return None, EXIT_FAILURE

    override: dict[str, str] = {}
    for src in sources:
        key = str(src)
        if key in override:
            continue  # same pptx referenced more than once -> preprocess once
        if not src.exists():
            logging.error("前処理: PPTX が見つかりません: %s", src)
            return None, EXIT_NOT_FOUND

        syn = build_preprocess_config(src, outdir, preprocessed_name(src), deletecsp, vars_map)
        try:
            out_path, _ops = merge_pptx(yaml_path, workdir=workdir, force=True, config=syn)
            log_path = resolve_merge_log_path(yaml_path, syn, out_path.parent, out_path.name, workdir)
            postprocess_after_merge(
                out_path, log_path, duplicate_to=None, config=syn, operations=[],
                csl_mode="keep",
            )
        except ConfigError as e:
            logging.error("前処理 (pptmerge) 設定エラー: %s: %s", src, e)
            return None, EXIT_BAD_INPUT
        except Exception as e:  # noqa: BLE001 - surface any COM/merge failure as a step failure
            logging.error("前処理 (pptmerge) に失敗しました: %s: %s", src, e)
            return None, EXIT_FAILURE

        override[key] = str(out_path)
        logging.info(
            "前処理（一般マーカーのみ / CSL は未処理）: %s -> %s (deletecsp=%s)",
            src.name, out_path, deletecsp,
        )

    return override, EXIT_OK


def _preprocess_context(args: argparse.Namespace):
    """Load the recipe and resolve the shared preprocess parameters.

    Returns ``(yaml_path, recipe, workdir, deletecsp, vars_map, outdir)`` on
    success, or an ``int`` ``EXIT_*`` code on error.

    ``deletecsl`` は解決しない。前処理は一般マーカーのみを扱い、CSL マーカーは
    設定・オプション指定にかかわらず未処理のまま残す。
    """
    yaml_path = resolve_input_path(args)
    if yaml_path is None:
        logging.error("No input file specified")
        return EXIT_BAD_INPUT
    if not yaml_path.exists():
        logging.error("Input file not found: %s", yaml_path)
        return EXIT_NOT_FOUND

    recipe = load_recipe(yaml_path, args)
    cli_workdir = Path(args.workdir).resolve() if getattr(args, "workdir", None) else None
    workdir = resolve_workdir(recipe, yaml_path, cli_workdir)
    indexer = recipe.get("indexer") or {}
    deletecsp = _resolve_bool_opt(getattr(args, "delete_csp", None), indexer.get("deletecsp", False))
    vars_map = recipe.get("vars") or {}
    outdir = _output_dir(recipe, yaml_path, workdir)
    return yaml_path, recipe, workdir, deletecsp, vars_map, outdir


def apply_preprocess(args: argparse.Namespace) -> int:
    """Generate a preprocessed pptx for every cropsrc.pptx and record the override on *args*.

    Sets ``args.cropsrc_pptx_override`` to ``{resolved_original: preprocessed}``.
    Returns an ``EXIT_*`` code.
    """
    ctx = _preprocess_context(args)
    if isinstance(ctx, int):
        return ctx
    yaml_path, recipe, workdir, deletecsp, vars_map, outdir = ctx

    if getattr(args, "delete_csl", None) is not None:
        logging.warning(
            "--deletecsl はパイプラインでは無視されます"
            "（CSL スライド削除は pptmerge の最後でのみ行います）"
        )
    elif (recipe.get("indexer") or {}).get("deletecsl"):
        logging.info(
            "indexer.deletecsl はパイプラインでは参照されません"
            "（CSL マーカーは未処理のまま成果物に残ります）"
        )

    entries = cropsrc_entries(recipe)
    if not entries:
        logging.error("input.cropsrc が指定されていません: %s", yaml_path)
        return EXIT_BAD_INPUT

    sources: list[Path] = []
    for entry in entries:
        pptx_val = entry.get("pptx")
        if not pptx_val:
            logging.error("input.cropsrc.pptx が指定されていません: %s", yaml_path)
            return EXIT_BAD_INPUT
        sources.append(resolve_cropsrc_path(str(pptx_val), yaml_path, workdir))

    override, code = _generate_preprocessed(yaml_path, workdir, sources, deletecsp, vars_map, outdir)
    if code != EXIT_OK:
        return code

    setattr(args, _OVERRIDE_ATTR, override)
    return EXIT_OK


def apply_preprocess_procedure(args: argparse.Namespace) -> int:
    """Preprocess every ``procedure`` ``insertpptx`` source pptx and record the override on *args*.

    Used by the standalone ``pptmerge`` subcommand's ``--preprocess``: each pptx that
    the merge is about to insert is first run through a single-file pptmerge (applying
    一般マーカー処理と ``--deletecsp``、recipe ``vars``), and the merge then reads the
    preprocessed copy in place of the original. CSL マーカーはここでは処理しない。 Sets ``args.cropsrc_pptx_override`` to
    ``{resolved_original: preprocessed}``. Returns an ``EXIT_*`` code.
    """
    from md_merge.merge._recipe import resolve_input_dirs
    from md_merge.pptmerge._config import resolve_file_in_dirs

    ctx = _preprocess_context(args)
    if isinstance(ctx, int):
        return ctx
    yaml_path, recipe, workdir, deletecsp, vars_map, outdir = ctx

    input_dirs = resolve_input_dirs(recipe, yaml_path, workdir)
    sources: list[Path] = []
    for item in recipe.get("procedure") or []:
        if item.get("operation", "") != "insertpptx":
            continue
        fname = item.get("pptxfilename")
        if not fname:
            continue
        sources.append(resolve_file_in_dirs(str(fname), input_dirs))

    if not sources:
        logging.error("procedure に insertpptx がありません（前処理対象がありません）: %s", yaml_path)
        return EXIT_BAD_INPUT

    override, code = _generate_preprocessed(yaml_path, workdir, sources, deletecsp, vars_map, outdir)
    if code != EXIT_OK:
        return code

    setattr(args, _OVERRIDE_ATTR, override)
    return EXIT_OK


def cleanup_preprocessed(args: argparse.Namespace) -> None:
    """Delete the generated _preprocessed.pptx files (after the full pipeline completes)."""
    override = getattr(args, _OVERRIDE_ATTR, None)
    if not override:
        return
    for path_str in override.values():
        p = Path(path_str)
        if p.exists():
            try:
                p.unlink()
                logging.info("前処理済み pptx を削除: %s", p.name)
            except OSError as e:
                logging.warning("前処理済み pptx の削除に失敗: %s: %s", p, e)
