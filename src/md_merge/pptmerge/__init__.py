import argparse
import logging
import sys
from pathlib import Path

from md_merge._fingerprint import load_pptx_check_map, verify_pptx_against_check
from md_merge._output import EXIT_BAD_INPUT, EXIT_FAILURE, EXIT_NOT_FOUND, EXIT_OK, emit, setup_logging
from md_merge.merge._recipe import (
    apply_recipe_force,
    iter_insertpptx_entries,
    load_recipe,
    resolve_input_dirs,
    resolve_input_path,
    resolve_out_file,
    resolve_workdir,
    setup_recipe_file_logging,
)
from md_merge.pptmerge._config import ConfigError, resolve_base, resolve_file_in_dirs
from md_merge.pptmerge._merger import _apply_cli_indexer_opts, merge_pptx, resolve_merge_log_path
from md_merge.pptmerge._slide_titles import postprocess_after_merge, postprocess_idresolve


def _output_is_fresh(
    recipe: dict, yaml_path: Path, workdir, out_path: Path,
) -> bool:
    """Return True when *out_path* exists and is at least as new as every merge input.

    Inputs considered: the recipe YAML, each ``procedure`` ``insertpptx`` source pptx,
    the ``pptmerge.stylebase`` (if any), and the resolved-id YAML consumed for
    ``{{num/title/label}}`` substitution (if present). A missing declared input means
    the output is not considered fresh (let the merge surface the error).
    """
    try:
        out_mtime = out_path.stat().st_mtime
    except OSError:
        return False

    inputs: list[Path] = [yaml_path]
    input_dirs = resolve_input_dirs(recipe, yaml_path, workdir)
    for item in recipe.get("procedure") or []:
        if item.get("operation", "") == "insertpptx":
            fname = item.get("pptxfilename")
            if fname:
                inputs.append(resolve_file_in_dirs(str(fname), input_dirs))

    stylebase = (recipe.get("pptmerge") or {}).get("stylebase")
    if stylebase:
        sp = Path(str(stylebase))
        inputs.append(sp if sp.is_absolute() else (resolve_base(yaml_path, workdir) / sp))

    resolved_path = resolve_out_file(recipe, "idresolvedfilename", yaml_path, workdir)
    if resolved_path is not None and resolved_path.exists():
        inputs.append(resolved_path)

    for p in inputs:
        try:
            if p.stat().st_mtime > out_mtime:
                return False
        except OSError:
            return False  # declared input missing -> not fresh
    return True


def _verify_insertpptx_check(
    args: argparse.Namespace, recipe: dict, yaml_path, workdir,
) -> None:
    """Verify insertpptx slide-count/titles against the check file (if present). Warn on drift.

    Skipped with --no-check or when the check file is absent.
    """
    if getattr(args, "no_check", False):
        return
    check_path = resolve_out_file(recipe, "checkfilename", yaml_path, workdir)
    if check_path is None or not check_path.exists():
        return
    check_map = load_pptx_check_map(check_path)
    if not check_map:
        return
    input_dirs = resolve_input_dirs(recipe, yaml_path, workdir)
    io_entries = iter_insertpptx_entries(recipe, input_dirs)
    problems = verify_pptx_against_check(check_map, io_entries)
    for fname, reasons in problems:
        logging.warning("insertpptx 整合性チェック: %s: %s", fname, "; ".join(reasons))
    if not problems:
        logging.debug("insertpptx 整合性チェック: 差異なし (%s)", check_path.name)


def run(args: argparse.Namespace) -> int:
    setup_logging(args.log_level)

    yaml_path = resolve_input_path(args)
    if yaml_path is None:
        logging.error("No input file specified")
        return EXIT_BAD_INPUT
    if not yaml_path.exists():
        logging.error("Input file not found: %s", yaml_path)
        return EXIT_NOT_FOUND

    recipe = load_recipe(yaml_path, args)
    _apply_cli_indexer_opts(args, recipe)
    cli_workdir = Path(args.workdir).resolve() if getattr(args, "workdir", None) else None
    workdir = resolve_workdir(recipe, yaml_path, cli_workdir)
    setup_recipe_file_logging(recipe, yaml_path, workdir)
    apply_recipe_force(args, recipe)
    force = getattr(args, "force", False)

    # Resolve output path for dry-run and guard
    out_path = resolve_out_file(recipe, "pptxfilename", yaml_path, workdir)
    if out_path is None:
        logging.error("output.pptxfilename または output.targetbasefilename が指定されていません: %s", yaml_path)
        return EXIT_BAD_INPUT

    logging.debug("yaml   : %s", yaml_path)
    logging.debug("output : %s", out_path)

    _verify_insertpptx_check(args, recipe, yaml_path, workdir)

    if args.dry_run:
        emit(args, "ok", "pptmerge", yaml_path, out_path, dry_run=True)
        return EXIT_OK

    # Incremental build: skip the merge when the output pptx is already newer than
    # every input, unless --rebuild forces it. --preprocess always regenerates (the
    # preprocessed sources are rebuilt each run), matching the ppt_to_* pipelines.
    rebuild = getattr(args, "rebuild", False) or getattr(args, "preprocess", False)
    if not rebuild and out_path.exists() and _output_is_fresh(recipe, yaml_path, workdir, out_path):
        if getattr(args, "json", False):
            emit(args, "skip", "pptmerge", yaml_path, out_path)
        else:
            msg = f"最新のためスキップ (--rebuild で再生成): {out_path}"
            print(msg)
            logging.info("%s", msg)
        return EXIT_OK

    if out_path.exists() and not force:
        logging.error("Output file already exists (use --force to overwrite): %s", out_path)
        return EXIT_FAILURE

    # --preprocess: run each insertpptx source through a single-file pptmerge first,
    # then have the merge read the preprocessed copies (see md_merge._preprocess).
    # Imported lazily to avoid a circular import (_preprocess imports pptmerge._config).
    if getattr(args, "preprocess", False):
        from md_merge._preprocess import apply_preprocess_procedure
        code = apply_preprocess_procedure(args)
        if code != EXIT_OK:
            return code

    try:
        output_path, operations = merge_pptx(
            yaml_path, workdir=workdir, force=force, args=args, config=recipe,
        )
    except ConfigError as e:
        logging.error("Config error: %s", e)
        return EXIT_BAD_INPUT
    except FileNotFoundError as e:
        logging.error("File not found: %s", e)
        return EXIT_NOT_FOUND
    except Exception as e:
        logging.error("pptmerge failed: %s", e)
        return EXIT_FAILURE

    try:
        from md_merge.pptmerge._config import parse_log_duplicate
        log_path = resolve_merge_log_path(yaml_path, recipe, output_path.parent, output_path.name, workdir)
        dup = parse_log_duplicate(recipe)
        dup_stream = (
            sys.stdout if dup == "stdout"
            else (sys.stderr if dup == "stderr" else None)
        )
        # CSL マーカー処理はここ（結合済み pptx に対する postprocess）でのみ行う。
        # csl_mode は指定せず indexer.deletecsl から導出する:
        #   true  -> CSL スライド削除処理 / false -> CSL マーカー消去処理
        pptxnumbering = recipe.get("indexer", {}).get("pptxnumbering", "no")
        if pptxnumbering is False:
            pptxnumbering = "no"
        if pptxnumbering == "idresolve":
            logging.debug("postprocess_after_merge: idresolve: output_path=%s", output_path)
            resolved_path = resolve_out_file(recipe, "idresolvedfilename", yaml_path, workdir)
            if resolved_path is None:
                logging.error("output.idresolvedfilename が指定されていません: %s", yaml_path)
                return EXIT_BAD_INPUT
            postprocess_idresolve(
                output_path, resolved_path, log_path,
                duplicate_to=dup_stream,
                config=recipe,
            )
        elif pptxnumbering == "no":
            postprocess_after_merge(
                output_path, log_path,
                duplicate_to=dup_stream,
                config=recipe,
                operations=[],
            )
        else:
            postprocess_after_merge(
                output_path, log_path,
                duplicate_to=dup_stream,
                config=recipe,
                operations=operations,
            )
    except Exception as e:
        logging.error("Postprocess failed: %s", e)
        return EXIT_FAILURE

    if getattr(args, "preprocess", False) and not getattr(args, "keep_work", False):
        from md_merge._preprocess import cleanup_preprocessed
        cleanup_preprocessed(args)

    emit(args, "ok", "pptmerge", yaml_path, output_path)
    return EXIT_OK
