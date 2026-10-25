from __future__ import annotations

import argparse

from md_merge._pipeline import run_pipeline
from md_merge.idcollect import run as run_idcollect
from md_merge.idresolve import run as run_idresolve
from md_merge.merge import run as run_merge
from md_merge.notecomexport import run as run_notecomexport
from md_merge.pptimgexport import run as run_pptimgexport
from md_merge.pptmdexport import run as run_pptmdexport
from md_merge.pptpdfexport import run as run_pptpdfexport
from md_merge.puremd import run as run_puremd
from md_merge.render import run as run_render

# Same front half as ppt_to_transfer, ending in notecomexport instead of transfer.
# The note.com posting YAML (notecomyamlfilename) is the deliverable. The puremd
# MD is deliberately kept as well so that a standalone `transfer` can still run
# afterwards from the same build (one pptx → note.com + Astro).
_WORK_FILE_KEYS = (
    "mdfilename",
    "idcollectfilename",
    "idresolvedfilename",
    "renderedfilename",
    "resourcepathfilename",
)

_STEPS: list[tuple[str, object]] = [
    ("pptpdfexport", run_pptpdfexport),
    ("pptimgexport", run_pptimgexport),
    ("pptmdexport",  run_pptmdexport),
    ("merge",        run_merge),
    ("idcollect",    run_idcollect),
    ("idresolve",    run_idresolve),
    ("render",       run_render),
    ("puremd",       run_puremd),
    ("notecomexport",   run_notecomexport),
]


def run(args: argparse.Namespace) -> int:
    return run_pipeline(
        args,
        command="ppt_to_notecom",
        steps=_STEPS,
        work_file_keys=_WORK_FILE_KEYS,
    )
