import argparse
import sys
from importlib.metadata import version, PackageNotFoundError

from md_merge.condblockprocess import run as run_condblockprocess
from md_merge.validate import run as run_validate
from md_merge.crop import run as run_crop
from md_merge.crop_to_pdf import run as run_crop_to_pdf
from md_merge.pptimgexport import run as run_pptimgexport
from md_merge.pptmdexport import run as run_pptmdexport
from md_merge.ppt_to_pdf import run as run_ppt_to_pdf
from md_merge.merge import run as run_merge
from md_merge.idcollect import run as run_idcollect
from md_merge.idresolve import run as run_idresolve
from md_merge.pandoc import run as run_pandoc
from md_merge.pptmerge import run as run_pptmerge
from md_merge.pptpdfexport import run as run_pptpdfexport
from md_merge.puremd import run as run_puremd
from md_merge.render import run as run_render


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
    return p


def _get_version() -> str:
    try:
        return version("pptmdmerge")
    except PackageNotFoundError:
        return "unknown"


def _make_parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(
        prog="md-merge",
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
    pptmerge.add_argument("--deletecsl", action="store_true", dest="delete_csl", help="Delete slides containing #CSL# marker (overrides recipe indexer.deletecsl)")
    pptmerge.add_argument("--deletecsp", action="store_true", dest="delete_csp", help="Delete shapes containing #CSP# marker (overrides recipe indexer.deletecsp)")
    pptmerge.add_argument("--pptxnumbering", choices=["no", "chapt_section", "idresolve"], dest="pptxnumbering", help="Numbering algorithm (overrides recipe indexer.pptxnumbering)")

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

    # ── puremd ─────────────────────────────────────────────────────────────────
    puremd = sub.add_parser(
        "puremd",
        parents=[common],
        help="Strip LaTeX (and other) raw blocks from a rendered MD file",
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
    p2p.add_argument("--keep-work", action="store_true", dest="keep_work", help="Retain work_ intermediate files after completion")

    # ── condblockprocess ──────────────────────────────────────────────────────
    cbp = sub.add_parser(
        "condblockprocess",
        parents=[common],
        help="Process conditional blocks and variable substitution in a template file",
    )
    cbp.add_argument("input", nargs="?", metavar="INPUT", help="Input YAML file")
    cbp.add_argument("--workdir", "-w", metavar="DIR", help="Base directory for relative paths")
    cbp.add_argument("--force", action="store_true", help="Overwrite existing output file")

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
    pptpdfexport.add_argument("--closepptx", action="store_true", help="Close PowerPoint presentation after export")
    pptpdfexport.add_argument("--ppquit", action="store_true", help="Quit PowerPoint after export")

    return root


def main() -> None:
    parser = _make_parser()
    args = parser.parse_args()

    if args.constants:
        from md_merge.merge._recipe import init_cli_constants
        init_cli_constants(args.constants)

    match args.subcommand:
        case "merge":
            code = run_merge(args)
        case "idcollect":
            code = run_idcollect(args)
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
        case "puremd":
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
        case "ppt_to_pdf":
            code = run_ppt_to_pdf(args)
        case "pptpdfexport":
            code = run_pptpdfexport(args)
        case "condblockprocess":
            code = run_condblockprocess(args)
        case "validate":
            code = run_validate(args)
        case _:
            parser.print_help()
            code = 2

    sys.exit(code)


if __name__ == "__main__":
    main()
