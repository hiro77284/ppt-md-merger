import argparse
import logging
from pathlib import Path

from md_merge._inventory import extract_entries, write_inventory
from md_merge._output import EXIT_BAD_INPUT, EXIT_FAILURE, EXIT_NOT_FOUND, EXIT_OK, emit, setup_logging
from md_merge.merge._recipe import apply_recipe_force, load_yaml, resolve_input_path, resolve_out_file, resolve_workdir, setup_recipe_file_logging


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
    setup_recipe_file_logging(recipe, yaml_path, workdir)
    apply_recipe_force(args, recipe)
    yaml_dir = yaml_path.parent

    merged_path = resolve_out_file(recipe, "mdfilename", yaml_path, workdir)
    if merged_path is None:
        logging.error("output.mdfilename is not specified in %s", yaml_path)
        return EXIT_BAD_INPUT

    inventory_path = resolve_out_file(recipe, "idcollectfilename", yaml_path, workdir)
    if inventory_path is None:
        logging.error("output.idcollectfilename is not specified in %s", yaml_path)
        return EXIT_BAD_INPUT

    logging.debug("yaml      : %s", yaml_path)
    logging.debug("merged md : %s", merged_path)
    logging.debug("inventory : %s", inventory_path)

    if args.dry_run:
        emit(args, "ok", "idcollect", yaml_path, inventory_path, dry_run=True)
        return EXIT_OK

    if not merged_path.exists():
        logging.error("Merged MD not found: %s", merged_path)
        return EXIT_NOT_FOUND

    if inventory_path.exists() and not getattr(args, "force", False):
        logging.error("Inventory file already exists (use --force to overwrite): %s", inventory_path)
        return EXIT_FAILURE

    merged_content = merged_path.read_text(encoding="utf-8")
    entries = extract_entries(merged_content, merged_path, yaml_dir)
    write_inventory(inventory_path, entries, yaml_path, yaml_dir)

    emit(args, "ok", "idcollect", yaml_path, inventory_path)
    return EXIT_OK
