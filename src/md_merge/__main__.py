import argparse
import sys
from importlib.metadata import version, PackageNotFoundError

from md_merge._output import EXIT_FAILURE
from md_merge._procedure import ProcedureNotationError
from md_merge.checkgen import run as run_checkgen
from md_merge.checkverify import run as run_checkverify
from md_merge.condblockprocess import run as run_condblockprocess
from md_merge.validate import run as run_validate
from md_merge.crop import run as run_crop
from md_merge.crop_to_pdf import run as run_crop_to_pdf
from md_merge.pptdeletecsl import run as run_pptdeletecsl
from md_merge.pptimgexport import run as run_pptimgexport
from md_merge.pptmdexport import run as run_pptmdexport
from md_merge.pptyamlexport import run as run_pptyamlexport
from md_merge.ppt_to_pdf import run as run_ppt_to_pdf
from md_merge.ppt_to_puremd import run as run_ppt_to_puremd
from md_merge.merge import run as run_merge
from md_merge.idcollect import run as run_idcollect
from md_merge.idresolve import run as run_idresolve
from md_merge.pandoc import run as run_pandoc
from md_merge.pptmerge import run as run_pptmerge
from md_merge.pptpdfexport import run as run_pptpdfexport
from md_merge.puremd import run as run_puremd
from md_merge.render import run as run_render
from md_merge.transfer import run as run_transfer
from md_merge.ppt_to_transfer import run as run_ppt_to_transfer
from md_merge.notecomexport import run as run_notecomexport
from md_merge.ppt_to_notecom import run as run_ppt_to_notecom


def _make_common_parser() -> argparse.ArgumentParser:
    """Parent parser carrying options shared across all subcommands."""
    p = argparse.ArgumentParser(add_help=False)
    p.add_argument(
        "--log-level", "-l",
        choices=["debug", "info", "warn", "error"],
        default="info",
        metavar="LEVEL",
        dest="log_level",
        help="Log level (debug|info|warn|error)",
    )
    p.add_argument("--dry-run", action="store_true", help="Show actions without writing files")
    p.add_argument("--json", action="store_true", help="Output results as JSON to stdout")
    p.add_argument("--constants", metavar="FILE", action="append", default=None,
                   help="TOML constants file for __NAME__ substitution (repeatable)")
    p.add_argument(
        "--tag", metavar="NAME", action="append", default=None,
        help="Tag for conditional procedure items (when: tag / not_tag). Repeatable",
    )
    p.add_argument(
        "--keep-work", action="store_true", dest="keep_work",
        help="Retain work_ intermediate files after completion (only effective for ppt_to_pdf / ppt_to_transfer / ppt_to_puremd / ppt_to_notecom; ignored with a warning elsewhere)",
    )
    return p


def _get_version() -> str:
    try:
        return version("pptmdmerge")
    except PackageNotFoundError:
        return "unknown"


def _make_parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(
        prog="pptmdmerge",
        description="Merge multiple Markdown files from a YAML recipe.",
    )
    root.add_argument("--version", action="version", version=f"%(prog)s {_get_version()}")
    common = _make_common_parser()
    sub = root.add_subparsers(dest="subcommand", required=True)

    # ── merge ──────────────────────────────────────────────────────────────
    merge = sub.add_parser(
        "merge",
        parents=[common],
        help="Merge md files according to a YAML recipe",
    )
    merge.add_argument("input", nargs="?", metavar="INPUT", help="Input YAML file")
    merge.add_argument("--workdir", "-w", metavar="DIR", help="Base directory for relative paths")
    merge.add_argument("--strict", action="store_true", help="Treat warnings as errors")
    merge.add_argument("--no-copy-images", action="store_true", dest="no_copy_images", help="Skip image copying")
    merge.add_argument("--image-dir", metavar="NAME", dest="image_dir", help="Image output directory name")
    merge.add_argument(
        "--flatten-images",
        action="store_true",
        dest="flatten_images",
        help="Copy all images into a single flat directory under the output path",
    )
    merge.add_argument(
        "--image-naming",
        metavar="MODE",
        dest="image_naming",
        choices=("preserve", "sanitize"),
        help="Copied image basename: preserve (default, keep as-is) or sanitize (ASCII slug)",
    )
    merge.add_argument(
        "--image-collision",
        metavar="MODE",
        dest="image_collision",
        choices=("rename", "overwrite"),
        help="When two different source images map to the same copy destination: "
             "rename (default, add _1/_2) or overwrite (warn and clobber)",
    )
    merge.add_argument(
        "--overwrite-images",
        action="store_true",
        dest="overwrite_images",
        help="Deprecated alias for --image-collision overwrite",
    )
    merge.add_argument("--no-check", action="store_true", dest="no_check", help="Skip insertmd content drift check even when a check file exists")
    merge.add_argument(
        "--clear-dir-before-merge",
        action="store_true",
        dest="clear_dir_before_merge",
        help="Delete everything inside the image-dir before merging (default: on; asks for "
             "confirmation showing the full path, --force skips it, recipe clear-dir-before-merge: false disables)",
    )
    merge.add_argument("--force", action="store_true", help="Overwrite existing output files")

    # ── idcollect ──────────────────────────────────────────────────────────
    idcol = sub.add_parser(
        "idcollect",
        parents=[common],
        help="Extract {{#id:...}} markers from a built MD and write an inventory YAML",
    )
    idcol.add_argument("input", nargs="?", metavar="INPUT", help="Input YAML file")
    idcol.add_argument("--workdir", "-w", metavar="DIR", help="Base directory for relative paths")
    idcol.add_argument("--force", action="store_true", help="Overwrite existing inventory file")

    # ── checkgen ───────────────────────────────────────────────────────────
    checkgen = sub.add_parser(
        "checkgen",
        parents=[common],
        help="Generate insertmd content fingerprints (drift-check data) into a separate YAML file",
    )
    checkgen.add_argument("input", nargs="?", metavar="INPUT", help="Input YAML file")
    checkgen.add_argument("--workdir", "-w", metavar="DIR", help="Base directory for relative paths")
    checkgen.add_argument("--force", action="store_true", help="Overwrite existing check file")

    # ── checkverify ────────────────────────────────────────────────────────
    checkverify = sub.add_parser(
        "checkverify",
        parents=[common],
        help="Verify insertmd content against the check file (no merge); exit 1 on significant drift",
    )
    checkverify.add_argument("input", nargs="?", metavar="INPUT", help="Input YAML file")
    checkverify.add_argument("--workdir", "-w", metavar="DIR", help="Base directory for relative paths")

    # ── idresolve ──────────────────────────────────────────────────────────
    idres = sub.add_parser(
        "idresolve",
        parents=[common],
        help="Resolve {{#id:...}} entries from an inventory YAML and write a resolved ID map",
    )
    idres.add_argument("input", nargs="?", metavar="INPUT", help="Input YAML file")
    idres.add_argument("--workdir", "-w", metavar="DIR", help="Base directory for relative paths")
    idres.add_argument("--force", action="store_true", help="Overwrite existing resolved file")

    # ── pandoc ─────────────────────────────────────────────────────────────
    pandoc = sub.add_parser(
        "pandoc",
        parents=[common],
        help="Invoke pandoc on the rendered MD to produce PDF, LaTeX, or other formats",
    )
    pandoc.add_argument("input", nargs="?", metavar="INPUT", help="Input YAML file")
    pandoc.add_argument("--workdir", "-w", metavar="DIR", help="Base directory for relative paths")
    pandoc.add_argument("--force", action="store_true", help="Overwrite existing output file")
    pandoc.add_argument("--tex", action="store_true", help="Output LaTeX (use texfilename, -t latex)")
    pandoc.add_argument("--html", action="store_true", help="Output HTML (use htmlfilename, -t html)")
    pandoc.add_argument("--reveal", action="store_true", help="Output reveal.js (use revealfilename, -t revealjs)")
    pandoc.add_argument(
        "--engine", choices=["latex", "typst"], default=None, metavar="latex|typst",
        help="PDF typesetting engine (overrides recipe pandoc.engine; default typst, which also "
             "keeps <pdfstem>.typ). latex (lualatex) is deprecated",
    )

    # ── render ─────────────────────────────────────────────────────────────
    render = sub.add_parser(
        "render",
        parents=[common],
        help="Render merged MD by substituting ID titles and references using a resolved ID map",
    )
    render.add_argument("input", nargs="?", metavar="INPUT", help="Input YAML file")
    render.add_argument("--workdir", "-w", metavar="DIR", help="Base directory for relative paths")
    render.add_argument("--force", action="store_true", help="Overwrite existing rendered file")

    # ── pptmerge ───────────────────────────────────────────────────────────
    pptmerge = sub.add_parser(
        "pptmerge",
        parents=[common],
        help="Merge multiple PowerPoint files according to a YAML recipe",
    )
    pptmerge.add_argument("input", nargs="?", metavar="INPUT", help="Input YAML file")
    pptmerge.add_argument("--workdir", "-w", metavar="DIR", help="Base directory for relative paths")
    pptmerge.add_argument("--force", action="store_true", help="Overwrite existing output file")
    pptmerge.add_argument("--rebuild", action="store_true", help="Rebuild even when the merged pptx is newer than every input (ignore incremental timestamp skip)")
    pptmerge.add_argument("--deletecsl", choices=["on", "off"], dest="delete_csl", metavar="on|off", help="結合済み pptx の CSL 処理: on=#CSL# を含むスライドを削除 / off=マーカー文字列のみ除去（recipe indexer.deletecsl を上書き）。個別 pptx には影響しない")
    pptmerge.add_argument("--deletecsp", choices=["on", "off"], dest="delete_csp", metavar="on|off", help="Delete shapes containing #CSP# marker (overrides recipe indexer.deletecsp)")
    pptmerge.add_argument("--pptxnumbering", choices=["no", "chapt_section", "idresolve"], dest="pptxnumbering", help="Numbering algorithm (overrides recipe indexer.pptxnumbering)")
    pptmerge.add_argument("--no-check", action="store_true", dest="no_check", help="Skip insertpptx content drift check even when a check file exists")
    pptmerge.add_argument("--preprocess", action="store_true", help="Preprocess each procedure insertpptx source pptx (single-file pptmerge, slides:all) and merge the preprocessed copies. 一般マーカー処理（--deletecsp 等）と recipe vars のみ適用し #CSL# は残す。Deleted after merge unless --keep-work")

    # ── crop ───────────────────────────────────────────────────────────────
    crop = sub.add_parser(
        "crop",
        parents=[common],
        help="Crop images whose filenames contain a RANGE suffix __{L}_{T}_{R}_{B}",
    )
    crop.add_argument("input", nargs="?", metavar="INPUT", help="Input YAML file")
    crop.add_argument("--workdir", "-w", metavar="DIR", help="Base directory for relative paths")
    crop.add_argument("--force", action="store_true", help="Overwrite existing output files")

    # ── crop_to_pdf ────────────────────────────────────────────────────────
    c2p = sub.add_parser(
        "crop_to_pdf",
        parents=[common],
        help="Run crop → merge → idcollect → idresolve → render → pandoc in sequence",
    )
    c2p.add_argument("input", nargs="?", metavar="INPUT", help="Input YAML file")
    c2p.add_argument("--workdir", "-w", metavar="DIR", help="Base directory for relative paths")
    c2p.add_argument("--force", action="store_true", help="Overwrite existing output files")
    c2p.add_argument("--no-check", action="store_true", dest="no_check", help="Skip the pre-merge insertmd drift check (no confirmation prompt)")
    c2p.add_argument(
        "--engine", choices=["latex", "typst"], default=None, metavar="latex|typst",
        help="PDF typesetting engine (overrides recipe pandoc.engine; default typst, which also "
             "keeps <pdfstem>.typ). latex (lualatex) is deprecated",
    )

    # ── pptimgexport ───────────────────────────────────────────────────────
    pptimgexport = sub.add_parser(
        "pptimgexport",
        parents=[common],
        help="Export cropped PDF images from PPTX slides using note-driven export-image-mode",
    )
    pptimgexport.add_argument("input", nargs="?", metavar="INPUT", help="Input YAML file")
    pptimgexport.add_argument("--workdir", "-w", metavar="DIR", help="Base directory for relative paths")
    pptimgexport.add_argument("--force", action="store_true", help="Overwrite existing output files")
    pptimgexport.add_argument("--closepptx", action="store_true", help="Close PDF document after processing")

    # ── pptmdexport ────────────────────────────────────────────────────────
    pptmdexport = sub.add_parser(
        "pptmdexport",
        parents=[common],
        help="Export MD text blocks from PPTX slide notes to files using note-driven export-note",
    )
    pptmdexport.add_argument("input", nargs="?", metavar="INPUT", help="Input YAML file")
    pptmdexport.add_argument("--workdir", "-w", metavar="DIR", help="Base directory for relative paths")
    pptmdexport.add_argument("--force", action="store_true", help="Overwrite existing output files")
    pptmdexport.add_argument("--closepptx", action="store_true", help="Close PPTX after processing")
    pptmdexport.add_argument(
        "--latex-check", choices=["off", "warn", "error"], default=None, dest="latex_check",
        help="Detect raw pandoc passthrough ({=latex}/{=html} etc.) in extracted MD blocks: warn (log only) | error (skip that file, exit non-zero) | off. Overrides recipe pptmdexport.latex_check (default: warn)",
    )

    # ── pptyamlexport ──────────────────────────────────────────────────────
    pptyamlexport = sub.add_parser(
        "pptyamlexport",
        parents=[common],
        help="Export diagram-definition YAML from PPTX slide notes, resolving 'auto' slot "
             "coordinates from named shapes relative to the baseframe shape",
    )
    pptyamlexport.add_argument("input", nargs="?", metavar="INPUT", help="Input YAML file")
    pptyamlexport.add_argument("--workdir", "-w", metavar="DIR", help="Base directory for relative paths")
    pptyamlexport.add_argument("--force", action="store_true", help="Overwrite existing output files")
    pptyamlexport.add_argument("--closepptx", action="store_true", help="Close PPTX after processing")

    # ── puremd (alias: githubmd) ─────────────────────────────────────────────────
    puremd = sub.add_parser(
        "puremd",
        parents=[common],
        aliases=["githubmd"],
        help="Generate GitHub-flavored Markdown: strip LaTeX raw blocks and lower "
             "semantic constructs to GFM (alias: githubmd)",
    )
    puremd.add_argument("input", nargs="?", metavar="INPUT", help="Input YAML file")
    puremd.add_argument("--workdir", "-w", metavar="DIR", help="Base directory for relative paths")
    puremd.add_argument("--force", action="store_true", help="Overwrite existing output file")

    # ── ppt_to_pdf ─────────────────────────────────────────────────────────
    p2p = sub.add_parser(
        "ppt_to_pdf",
        parents=[common],
        help="Run pptimgexport → pptmdexport → merge → idcollect → idresolve → render → pandoc in sequence",
    )
    p2p.add_argument("input", nargs="?", metavar="INPUT", help="Input YAML file")
    p2p.add_argument("--workdir", "-w", metavar="DIR", help="Base directory for relative paths")
    p2p.add_argument("--force", action="store_true", help="Overwrite existing output files")
    p2p.add_argument("--rebuild", action="store_true", help="Force the pptpdfexport step to rebuild PDFs even when newer than the source PPTX")
    p2p.add_argument("--preprocess", action="store_true", help="Preprocess each input.cropsrc.pptx (single-file pptmerge, slides:all) and use the preprocessed pptx for the pptx-consuming steps")
    p2p.add_argument("--deletecsl", nargs="?", const="on", choices=["on", "off"], default=None, dest="delete_csl", metavar="[on|off]", help="[非推奨/無視] パイプラインでは CSL 処理を行わないため効果がない。指定すると警告する")
    p2p.add_argument("--deletecsp", nargs="?", const="on", choices=["on", "off"], default=None, dest="delete_csp", metavar="[on|off]", help="Preprocess: delete shapes containing #CSP#. Bare flag = on; 'off' forces off; omitted = recipe indexer.deletecsp. Effective only with --preprocess")
    p2p.add_argument("--no-check", action="store_true", dest="no_check", help="Skip the pre-merge insertmd drift check (no confirmation prompt)")
    p2p.add_argument(
        "--engine", choices=["latex", "typst"], default=None, metavar="latex|typst",
        help="PDF typesetting engine (overrides recipe pandoc.engine; default typst, which also "
             "keeps <pdfstem>.typ). latex (lualatex) is deprecated",
    )

    # ── condblockprocess ──────────────────────────────────────────────────────
    cbp = sub.add_parser(
        "condblockprocess",
        parents=[common],
        help="Process conditional blocks and variable substitution in a template file",
    )
    cbp.add_argument("input", nargs="?", metavar="INPUT", help="Input YAML file")
    cbp.add_argument("--workdir", "-w", metavar="DIR", help="Base directory for relative paths")
    cbp.add_argument("--force", action="store_true", help="Overwrite existing output file")

    # ── ppt_to_transfer ───────────────────────────────────────────────────
    p2t = sub.add_parser(
        "ppt_to_transfer",
        parents=[common],
        help="Run pptpdfexport → pptimgexport → pptmdexport → merge → idcollect → idresolve → render → puremd → transfer in sequence",
    )
    p2t.add_argument("input", nargs="?", metavar="INPUT", help="Input YAML file")
    p2t.add_argument("--workdir", "-w", metavar="DIR", help="Base directory for relative paths")
    p2t.add_argument("--force", action="store_true", help="Overwrite existing output files")
    p2t.add_argument("--rebuild", action="store_true", help="Force the pptpdfexport step to rebuild PDFs even when newer than the source PPTX")
    p2t.add_argument("--preprocess", action="store_true", help="Preprocess each input.cropsrc.pptx (single-file pptmerge, slides:all) and use the preprocessed pptx for the pptx-consuming steps")
    p2t.add_argument("--deletecsl", nargs="?", const="on", choices=["on", "off"], default=None, dest="delete_csl", metavar="[on|off]", help="[非推奨/無視] パイプラインでは CSL 処理を行わないため効果がない。指定すると警告する")
    p2t.add_argument("--deletecsp", nargs="?", const="on", choices=["on", "off"], default=None, dest="delete_csp", metavar="[on|off]", help="Preprocess: delete shapes containing #CSP#. Bare flag = on; 'off' forces off; omitted = recipe indexer.deletecsp. Effective only with --preprocess")
    p2t.add_argument("--no-check", action="store_true", dest="no_check", help="Skip the pre-merge insertmd drift check (no confirmation prompt)")
    p2t.add_argument(
        "--source", choices=["puremd", "rendered", "merged"], dest="source",
        help="Transfer source MD: puremd (puremdfilename, default) | rendered (renderedfilename) | merged (mdfilename). Overrides transfer.inputmd",
    )

    # ── ppt_to_puremd ─────────────────────────────────────────────────────
    p2pm = sub.add_parser(
        "ppt_to_puremd",
        parents=[common],
        help="Run pptpdfexport → pptimgexport → pptmdexport → merge → idcollect → idresolve → render → puremd in sequence (ppt_to_transfer without the trailing transfer step; puremd MD is the deliverable)",
    )
    p2pm.add_argument("input", nargs="?", metavar="INPUT", help="Input YAML file")
    p2pm.add_argument("--workdir", "-w", metavar="DIR", help="Base directory for relative paths")
    p2pm.add_argument("--force", action="store_true", help="Overwrite existing output files")
    p2pm.add_argument("--rebuild", action="store_true", help="Force the pptpdfexport step to rebuild PDFs even when newer than the source PPTX")
    p2pm.add_argument("--preprocess", action="store_true", help="Preprocess each input.cropsrc.pptx (single-file pptmerge, slides:all) and use the preprocessed pptx for the pptx-consuming steps")
    p2pm.add_argument("--deletecsl", nargs="?", const="on", choices=["on", "off"], default=None, dest="delete_csl", metavar="[on|off]", help="[非推奨/無視] パイプラインでは CSL 処理を行わないため効果がない。指定すると警告する")
    p2pm.add_argument("--deletecsp", nargs="?", const="on", choices=["on", "off"], default=None, dest="delete_csp", metavar="[on|off]", help="Preprocess: delete shapes containing #CSP#. Bare flag = on; 'off' forces off; omitted = recipe indexer.deletecsp. Effective only with --preprocess")
    p2pm.add_argument("--no-check", action="store_true", dest="no_check", help="Skip the pre-merge insertmd drift check (no confirmation prompt)")

    # ── transfer ──────────────────────────────────────────────────────────
    transfer = sub.add_parser(
        "transfer",
        parents=[common],
        help="Copy rendered MD and images to a dataentry input directory for static site generation",
    )
    transfer.add_argument("input", nargs="?", metavar="INPUT", help="Input YAML file")
    transfer.add_argument("--workdir", "-w", metavar="DIR", help="Base directory for relative paths")
    transfer.add_argument("--force", action="store_true", help="Overwrite existing output files")
    transfer.add_argument(
        "--source", choices=["puremd", "rendered", "merged"], dest="source",
        help="Transfer source MD: puremd (puremdfilename) | rendered (renderedfilename) | merged (mdfilename). Overrides transfer.inputmd",
    )

    # ── notecomexport ────────────────────────────────────────────────────────
    notecomexport = sub.add_parser(
        "notecomexport",
        parents=[common],
        help="Convert the puremd-processed MD (frontmatter + GFM) into a note.com posting YAML for tools/notecom_autopilot.py",
    )
    notecomexport.add_argument("input", nargs="?", metavar="INPUT", help="Input YAML file")
    notecomexport.add_argument("--workdir", "-w", metavar="DIR", help="Base directory for relative paths")
    notecomexport.add_argument("--force", action="store_true", help="Overwrite existing output file")
    notecomexport.add_argument(
        "--source", choices=["puremd", "rendered", "merged"], dest="source",
        help="Source MD: puremd (puremdfilename, default) | rendered (renderedfilename) | merged (mdfilename). Overrides notecomexport.inputmd",
    )

    # ── ppt_to_notecom ───────────────────────────────────────────────────────
    p2n = sub.add_parser(
        "ppt_to_notecom",
        parents=[common],
        help="Run pptpdfexport → pptimgexport → pptmdexport → merge → idcollect → idresolve → render → puremd → notecomexport in sequence (note.com posting YAML is the deliverable; puremd MD is kept)",
    )
    p2n.add_argument("input", nargs="?", metavar="INPUT", help="Input YAML file")
    p2n.add_argument("--workdir", "-w", metavar="DIR", help="Base directory for relative paths")
    p2n.add_argument("--force", action="store_true", help="Overwrite existing output files")
    p2n.add_argument("--rebuild", action="store_true", help="Force the pptpdfexport step to rebuild PDFs even when newer than the source PPTX")
    p2n.add_argument("--preprocess", action="store_true", help="Preprocess each input.cropsrc.pptx (single-file pptmerge, slides:all) and use the preprocessed pptx for the pptx-consuming steps")
    p2n.add_argument("--deletecsl", nargs="?", const="on", choices=["on", "off"], default=None, dest="delete_csl", metavar="[on|off]", help="[非推奨/無視] パイプラインでは CSL 処理を行わないため効果がない。指定すると警告する")
    p2n.add_argument("--deletecsp", nargs="?", const="on", choices=["on", "off"], default=None, dest="delete_csp", metavar="[on|off]", help="Preprocess: delete shapes containing #CSP#. Bare flag = on; 'off' forces off; omitted = recipe indexer.deletecsp. Effective only with --preprocess")
    p2n.add_argument("--no-check", action="store_true", dest="no_check", help="Skip the pre-merge insertmd drift check (no confirmation prompt)")
    p2n.add_argument(
        "--source", choices=["puremd", "rendered", "merged"], dest="source",
        help="notecomexport source MD: puremd (puremdfilename, default) | rendered (renderedfilename) | merged (mdfilename). Overrides notecomexport.inputmd",
    )

    # ── validate ──────────────────────────────────────────────────────────
    validate = sub.add_parser(
        "validate",
        parents=[common],
        help="レシピ YAML の整合性を検査し、未知のキーを警告する",
    )
    validate.add_argument("input", nargs="?", metavar="INPUT", help="Input YAML file")
    validate.add_argument("--workdir", "-w", metavar="DIR", help="Base directory for relative paths")
    validate.add_argument("--strict", action="store_true", help="未知のキーがあれば終了コード 1 を返す")

    # ── pptpdfexport ───────────────────────────────────────────────────────
    pptpdfexport = sub.add_parser(
        "pptpdfexport",
        parents=[common],
        help="Export PPTX to PDF using PowerPoint COM automation (Windows only)",
    )
    pptpdfexport.add_argument("input", nargs="?", metavar="INPUT", help="Input YAML file")
    pptpdfexport.add_argument("--workdir", "-w", metavar="DIR", help="Base directory for relative paths")
    pptpdfexport.add_argument("--force", action="store_true", help="Overwrite existing output PDF")
    pptpdfexport.add_argument("--rebuild", action="store_true", help="Rebuild even when the output PDF is newer than the source PPTX (ignore timestamp skip)")
    pptpdfexport.add_argument("--closepptx", action="store_true", help="Close PowerPoint presentation after export")
    pptpdfexport.add_argument("--ppquit", action="store_true", help="Quit PowerPoint after export")

    # ── pptdeletecsl ───────────────────────────────────────────────────────
    pptdeletecsl = sub.add_parser(
        "pptdeletecsl",
        parents=[common],
        help="既存 pptx（マージ後ファイル）の #CSL# を単独で処理する。入力は YAML ではなく pptx",
    )
    pptdeletecsl.add_argument("input", nargs="?", metavar="PPTX", help="処理対象の pptx ファイル")
    pptdeletecsl.add_argument(
        "--output", "-o", metavar="PPTX",
        help="出力先 pptx。省略時は入力ファイルを直接書き換える（in-place）",
    )
    pptdeletecsl.add_argument(
        "--mode", choices=["delete", "strip"], default="delete", metavar="delete|strip",
        help="delete=#CSL# を含むスライドを削除（既定） / strip=スライドは残しマーカー文字列のみ除去",
    )
    pptdeletecsl.add_argument("--force", action="store_true", help="--output の既存ファイルを上書きする")

    return root


# Subcommands that actually honor --keep-work; others accept it but ignore with a warning.
_KEEP_WORK_SUBCOMMANDS = {"ppt_to_pdf", "ppt_to_transfer", "ppt_to_puremd", "ppt_to_notecom"}


def main() -> None:
    parser = _make_parser()
    args = parser.parse_args()

    if getattr(args, "keep_work", False) and args.subcommand not in _KEEP_WORK_SUBCOMMANDS:
        import logging
        from md_merge._output import setup_logging
        setup_logging(getattr(args, "log_level", "info"))
        logging.warning(
            "--keep-work は %s では効果がありません。無視して続行します。", args.subcommand
        )

    if args.constants:
        from md_merge.merge._recipe import init_cli_constants
        init_cli_constants(args.constants)

    # レシピの version と procedure 記法の不整合は、どのサブコマンドでもトレースバックなしで終了する
    try:
        match args.subcommand:
            case "merge":
                code = run_merge(args)
            case "idcollect":
                code = run_idcollect(args)
            case "checkgen":
                code = run_checkgen(args)
            case "checkverify":
                code = run_checkverify(args)
            case "idresolve":
                code = run_idresolve(args)
            case "pandoc":
                code = run_pandoc(args)
                if code == 0 and not getattr(args, "json", False) and not getattr(args, "dry_run", False):
                    print("\n========================================")
                    print("  pandoc 完了")
                    print("========================================\n")
            case "render":
                code = run_render(args)
            case "puremd" | "githubmd":
                code = run_puremd(args)
            case "pptmerge":
                code = run_pptmerge(args)
            case "crop":
                code = run_crop(args)
            case "crop_to_pdf":
                code = run_crop_to_pdf(args)
            case "pptimgexport":
                code = run_pptimgexport(args)
            case "pptmdexport":
                code = run_pptmdexport(args)
            case "pptyamlexport":
                code = run_pptyamlexport(args)
            case "ppt_to_pdf":
                code = run_ppt_to_pdf(args)
            case "pptpdfexport":
                code = run_pptpdfexport(args)
            case "pptdeletecsl":
                code = run_pptdeletecsl(args)
            case "condblockprocess":
                code = run_condblockprocess(args)
            case "ppt_to_transfer":
                code = run_ppt_to_transfer(args)
            case "ppt_to_puremd":
                code = run_ppt_to_puremd(args)
            case "transfer":
                code = run_transfer(args)
            case "notecomexport":
                code = run_notecomexport(args)
            case "ppt_to_notecom":
                code = run_ppt_to_notecom(args)
            case "validate":
                code = run_validate(args)
            case _:
                parser.print_help()
                code = 2
    except ProcedureNotationError as exc:
        import logging
        logging.error("%s", exc)
        code = EXIT_FAILURE

    sys.exit(code)


if __name__ == "__main__":
    main()
