import argparse
import logging
from pathlib import Path

import yaml

from md_merge._output import EXIT_BAD_INPUT, EXIT_FAILURE, EXIT_NOT_FOUND, EXIT_OK, emit, setup_logging
from md_merge._render import build_resolved_map, render_content
from md_merge.merge._recipe import apply_recipe_force, load_yaml, resolve_input_path, resolve_out_file, resolve_workdir


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
    cli_workdir = Path(args.workdir).resolve() if getattr(args, "workdir", None) else None
    workdir = resolve_workdir(recipe, yaml_path, cli_workdir)
    apply_recipe_force(args, recipe)

    merged_path = resolve_out_file(recipe, "mdfilename", yaml_path, workdir)
    if merged_path is None:
        logging.error("output.mdfilename is not specified in %s", yaml_path)
        return EXIT_BAD_INPUT

    resolved_path = resolve_out_file(recipe, "idresolvedfilename", yaml_path, workdir)
    if resolved_path is None:
        logging.error("output.idresolvedfilename is not specified in %s", yaml_path)
        return EXIT_BAD_INPUT

    rendered_path = resolve_out_file(recipe, "renderedfilename", yaml_path, workdir)
    if rendered_path is None:
        logging.error("output.renderedfilename is not specified in %s", yaml_path)
        return EXIT_BAD_INPUT

    logging.debug("yaml     : %s", yaml_path)
    logging.debug("merged   : %s", merged_path)
    logging.debug("resolved : %s", resolved_path)
    logging.debug("rendered : %s", rendered_path)

    if args.dry_run:
        emit(args, "ok", "render", yaml_path, rendered_path, dry_run=True)
        return EXIT_OK

    if not merged_path.exists():
        logging.error("Merged MD not found: %s", merged_path)
        return EXIT_NOT_FOUND

    if not resolved_path.exists():
        logging.error("Resolved ID map not found: %s", resolved_path)
        return EXIT_NOT_FOUND

    if rendered_path.exists() and not getattr(args, "force", False):
        logging.error("Rendered file already exists (use --force to overwrite): %s", rendered_path)
        return EXIT_FAILURE

    merged_content = merged_path.read_text(encoding="utf-8")

    with resolved_path.open(encoding="utf-8") as f:
        resolved_data = yaml.safe_load(f)

    resolved_map = build_resolved_map(resolved_data)
    vars_map = {str(k): str(v) for k, v in (recipe.get("vars") or {}).items()}

    pptxnumbering = (recipe.get("indexer") or {}).get("pptxnumbering", "no")
    if pptxnumbering is False:
        pptxnumbering = "no"
    apply_title_labels = pptxnumbering != "no"

    rendered_content = render_content(merged_content, resolved_map, vars_map, apply_title_labels=apply_title_labels)

    rendered_path.parent.mkdir(parents=True, exist_ok=True)
    rendered_path.write_text(rendered_content, encoding="utf-8")

    emit(args, "ok", "render", yaml_path, rendered_path)
    return EXIT_OK
