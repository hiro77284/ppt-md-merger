import argparse
import logging
from pathlib import Path

from md_merge._output import EXIT_BAD_INPUT, EXIT_FAILURE, EXIT_NOT_FOUND, EXIT_OK, emit, setup_logging
from md_merge.merge._images import make_image_copier
from md_merge.merge._recipe import (
    CircularIncludeError,
    IncludeNotFoundError,
    apply_recipe_force,
    collect_procedure_items,
    expand_md,
    load_yaml,
    resolve_input_mddir,
    resolve_input_path,
    resolve_output_path,
    resolve_workdir,
)


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
    _apply_recipe_merge_opts(args, recipe.get("merge", {}))

    in_dirs = resolve_input_mddir(recipe, yaml_path, workdir)
    procedure_items = collect_procedure_items(recipe, in_dirs, yaml_path)

    if not any(isinstance(i, Path) for i in procedure_items):
        logging.warning("No insertmd entries found in procedure")

    out_path = resolve_output_path(recipe, yaml_path, workdir)

    logging.debug("yaml    : %s", yaml_path)
    logging.debug("in_dirs : %s", [str(d) for d in in_dirs])
    logging.debug("files   : %s", [str(i) for i in procedure_items if isinstance(i, Path)])
    logging.debug("output  : %s", out_path)

    if args.dry_run:
        emit(args, "ok", "merge", yaml_path, out_path, dry_run=True)
        return EXIT_OK

    if out_path.exists() and not getattr(args, "force", False):
        logging.error("Output file already exists (use --force to overwrite): %s", out_path)
        return EXIT_FAILURE

    strict = getattr(args, "strict", False)
    image_copier = make_image_copier(args, out_path, in_dirs[0] if in_dirs else None)

    parts: list[str] = []
    for item in procedure_items:
        if isinstance(item, str):
            parts.append(item)
            continue
        p = item
        if not p.exists():
            if strict:
                logging.error("MD file not found: %s", p)
                return EXIT_NOT_FOUND
            logging.warning("MD file not found: %s — skipping", p)
            continue
        try:
            parts.append(expand_md(
                p, strict=strict, yaml_dir=yaml_path.parent,
                image_copier=image_copier,
            ))
        except CircularIncludeError as e:
            logging.error("Circular include detected: %s", e.path)
            return EXIT_FAILURE
        except IncludeNotFoundError as e:
            logging.error("Include target not found: %s", e.path)
            return EXIT_NOT_FOUND

    merged = "\n\n".join(parts)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(merged, encoding="utf-8")

    emit(args, "ok", "merge", yaml_path, out_path)
    return EXIT_OK


# ── helpers ────────────────────────────────────────────────────────────────


def _apply_recipe_merge_opts(args: argparse.Namespace, mc: dict) -> None:
    """Fill unset CLI boolean/string options from the recipe's merge section.

    CLI flags (store_true) default to False; a True value means the flag was
    explicitly passed, so recipe values only fill in when the flag is False.
    """
    if not args.no_copy_images:
        args.no_copy_images = bool(mc.get("no-copy-images", False))
    if not args.image_dir:
        args.image_dir = mc.get("image-dir") or None
    if not args.flatten_images:
        args.flatten_images = bool(mc.get("flatten-images", False))
    if not getattr(args, "strict", False):
        args.strict = bool(mc.get("strict", False))


