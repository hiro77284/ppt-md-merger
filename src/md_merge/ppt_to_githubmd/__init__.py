from __future__ import annotations

import argparse

from md_merge._pipeline import run_pipeline
from md_merge.githubmd import run as run_githubmd
from md_merge.idcollect import run as run_idcollect
from md_merge.idresolve import run as run_idresolve
from md_merge.merge import run as run_merge
from md_merge.pptimgexport import run as run_pptimgexport
from md_merge.pptmdexport import run as run_pptmdexport
from md_merge.pptpdfexport import run as run_pptpdfexport
from md_merge.puremd import run as run_puremd
from md_merge.render import run as run_render
from md_merge.transfer import run as run_transfer

# ppt_to_puremd + a trailing githubmd step. The GitHub-ready MD (githubmdfilename)
# is the deliverable; the puremd MD is kept as well (like ppt_to_notecom) so that
# transfer / notecomexport can follow from the same run.
_WORK_FILE_KEYS = (
    "mdfilename",
    "idcollectfilename",
    "idresolvedfilename",
    "renderedfilename",
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
    ("githubmd",     run_githubmd),
]


def run(args: argparse.Namespace) -> int:
    # --transfer appends a transfer step that copies this pipeline's deliverable
    # (githubmdfilename) and its images to transfer.dataentry_input, like ppt_to_transfer.
    # The deliverable itself is kept (not treated as a work file).
    with_transfer = bool(getattr(args, "transfer", False))
    steps = _STEPS + [("transfer", run_transfer)] if with_transfer else _STEPS
    return run_pipeline(
        args,
        command="ppt_to_githubmd",
        steps=steps,
        work_file_keys=_WORK_FILE_KEYS,
        transfer_source_key="githubmdfilename" if with_transfer else None,
    )
