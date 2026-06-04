from __future__ import annotations

import argparse
import logging

from md_merge._output import EXIT_OK, setup_logging
from md_merge.crop import run as run_crop
from md_merge.idcollect import run as run_idcollect
from md_merge.idresolve import run as run_idresolve
from md_merge.merge import run as run_merge
from md_merge.pandoc import run as run_pandoc
from md_merge.render import run as run_render

_STEPS: list[tuple[str, ...]] = [
    ("crop",      run_crop),
    ("merge",     run_merge),
    ("idcollect", run_idcollect),
    ("idresolve", run_idresolve),
    ("render",    run_render),
    ("pandoc",    run_pandoc),
]


def _fill_defaults(args: argparse.Namespace) -> None:
    """Set attributes expected by individual subcommand run() functions."""
    # merge/_apply_recipe_merge_opts accesses these without getattr
    for attr, default in (
        ("no_copy_images", False),
        ("image_dir", None),
        ("flatten_images", False),
        ("strict", False),
    ):
        if not hasattr(args, attr):
            setattr(args, attr, default)


def run(args: argparse.Namespace) -> int:
    setup_logging(args.log_level)
    _fill_defaults(args)
    for name, step_run in _STEPS:
        logging.info("[crop_to_pdf] %s ...", name)
        code = step_run(args)
        if code != EXIT_OK:
            logging.error("[crop_to_pdf] %s failed (exit %d) — stopping", name, code)
            return code
    return EXIT_OK
