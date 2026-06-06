import argparse
import logging
import sys
from pathlib import Path

from md_merge._output import EXIT_BAD_INPUT, EXIT_FAILURE, EXIT_NOT_FOUND, EXIT_OK, emit, setup_logging
from md_merge.merge._recipe import apply_recipe_force, load_yaml, resolve_input_path, resolve_out_file, resolve_workdir, setup_recipe_file_logging
from md_merge.pptmerge._config import ConfigError
from md_merge.pptmerge._merger import _apply_cli_indexer_opts, merge_pptx, resolve_merge_log_path
from md_merge.pptmerge._slide_titles import postprocess_after_merge, postprocess_idresolve


def run(args: argparse.Namespace) -> int:
    setup_logging(args.log_level)

    yaml_path = resolve_input_path(args)
    if yaml_path is None:
        logging.error("No input file specified")
        return EXIT_BAD_INPUT
    if not yaml_path.exists():
        logging.error("Input file not found: %s", yaml_path)
        return EXIT_NOT_FOUND

    recipe = load_yaml(yaml_path)
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

    if args.dry_run:
        emit(args, "ok", "pptmerge", yaml_path, out_path, dry_run=True)
        return EXIT_OK

    if out_path.exists() and not force:
        logging.error("Output file already exists (use --force to overwrite): %s", out_path)
        return EXIT_FAILURE

    try:
        output_path, operations = merge_pptx(
            yaml_path, workdir=workdir, force=force, config=recipe,
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

    emit(args, "ok", "pptmerge", yaml_path, output_path)
    return EXIT_OK
