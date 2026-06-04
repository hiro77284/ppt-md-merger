import argparse
import copy
import logging
from pathlib import Path

import yaml

from md_merge._output import EXIT_BAD_INPUT, EXIT_FAILURE, EXIT_NOT_FOUND, EXIT_OK, emit, setup_logging
from md_merge._resolve import expand_title_label_refs, get_indexer, resolve_entries, write_resolved
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
    yaml_dir = yaml_path.parent

    inventory_path = resolve_out_file(recipe, "idcollectfilename", yaml_path, workdir)
    if inventory_path is None:
        logging.error("output.idcollectfilename is not specified in %s", yaml_path)
        return EXIT_BAD_INPUT

    resolved_path = resolve_out_file(recipe, "idresolvedfilename", yaml_path, workdir)
    if resolved_path is None:
        logging.error("output.idresolvedfilename is not specified in %s", yaml_path)
        return EXIT_BAD_INPUT

    logging.debug("yaml      : %s", yaml_path)
    logging.debug("inventory : %s", inventory_path)
    logging.debug("resolved  : %s", resolved_path)

    if args.dry_run:
        emit(args, "ok", "idresolve", yaml_path, resolved_path, dry_run=True)
        return EXIT_OK

    if not inventory_path.exists():
        logging.error("Inventory file not found: %s", inventory_path)
        return EXIT_NOT_FOUND

    if resolved_path.exists() and not getattr(args, "force", False):
        logging.error("Resolved file already exists (use --force to overwrite): %s", resolved_path)
        return EXIT_FAILURE

    with inventory_path.open(encoding="utf-8") as f:
        inventory = yaml.safe_load(f)

    entries = copy.deepcopy(inventory.get("entries") or [])
    delimiter, separator = get_indexer(recipe)
    resolve_entries(entries, delimiter, separator)
    expand_title_label_refs(entries, separator)
    write_resolved(resolved_path, entries, yaml_path, yaml_dir, inventory_path, delimiter, separator)

    emit(args, "ok", "idresolve", yaml_path, resolved_path)
    return EXIT_OK
