from __future__ import annotations

import argparse

from md_merge._pipeline import run_pipeline
from md_merge.idcollect import run as run_idcollect
from md_merge.idresolve import run as run_idresolve
from md_merge.merge import run as run_merge
from md_merge.pptimgexport import run as run_pptimgexport
from md_merge.pptmdexport import run as run_pptmdexport
from md_merge.pptpdfexport import run as run_pptpdfexport
from md_merge.puremd import run as run_puremd
from md_merge.render import run as run_render

# Same pipeline as ppt_to_transfer but stopping at puremd: the puremd-processed
# MD (puremdfilename) is the deliverable, so it is deliberately omitted from the
# work-file cleanup list below while every other intermediate is removed.
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
]


def run(args: argparse.Namespace) -> int:
    return run_pipeline(
        args,
        command="ppt_to_puremd",
        steps=_STEPS,
        work_file_keys=_WORK_FILE_KEYS,
    )
