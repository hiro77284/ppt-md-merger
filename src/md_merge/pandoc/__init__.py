import argparse
import logging
import os
import shutil
import subprocess
from pathlib import Path

from md_merge._output import EXIT_BAD_INPUT, EXIT_FAILURE, EXIT_NOT_FOUND, EXIT_OK, emit, setup_logging
from md_merge.merge._recipe import apply_recipe_force, load_yaml, resolve_condblock_output, resolve_input_path, resolve_out_file, resolve_workdir, setup_recipe_file_logging

# Built-in Lua filters shipped with this package
_BUILTIN_FILTERS_DIR = Path(__file__).parent.parent / "filters"


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

    pandoc_section = recipe.get("pandoc", {})

    if getattr(args, "tex", False):
        out_key = "texfilename"
        pandoc_format = "latex"
        defaults_key = "defaults"
        simple_mode = False
    elif getattr(args, "html", False):
        out_key = "htmlfilename"
        pandoc_format = "html"
        defaults_key = "htmldefaults"
        simple_mode = True
    elif getattr(args, "reveal", False):
        out_key = "revealfilename"
        pandoc_format = "revealjs"
        defaults_key = "revealdefaults"
        simple_mode = True
    else:
        out_key = "pdffilename"
        pandoc_format = pandoc_section.get("format") or "pdf"
        defaults_key = "defaults"
        simple_mode = False

    rendered_path = resolve_out_file(recipe, "renderedfilename", yaml_path, workdir)
    if rendered_path is None:
        logging.error("output.renderedfilename is not specified in %s", yaml_path)
        return EXIT_BAD_INPUT

    pdf_path = resolve_out_file(recipe, out_key, yaml_path, workdir)
    if pdf_path is None:
        logging.error("output.%s is not specified in %s", out_key, yaml_path)
        return EXIT_BAD_INPUT

    # Resolve data-dir first — used as base for defaults / template / include-in-header
    data_dir: Path | None = None
    _data_dir_val = pandoc_section.get("data-dir")
    if _data_dir_val:
        _p = _resolve_path(_data_dir_val, yaml_path, workdir)
        if _p is not None:
            data_dir = _p.resolve()

    # defaults / htmldefaults / revealdefaults: resolved from data-dir
    defaults_path = _resolve_from_datadir(pandoc_section.get(defaults_key), data_dir, yaml_path, workdir)

    filter_paths, missing = _resolve_filters(
        pandoc_section.get("filters") or [], yaml_path, workdir
    )

    # metadata-file: resolved from workdir (not data-dir)
    # template / include-in-header: resolved from data-dir (PDF/LaTeX mode only)
    # data-dir: already resolved above, appended last with canonical path
    path_opts: list[tuple[str, Path]] = []
    _metadata = _resolve_path(pandoc_section.get("metadata-file"), yaml_path, workdir)
    if _metadata is not None:
        path_opts.append(("metadata-file", _metadata.resolve()))
    if not simple_mode:
        for key in ("template", "include-in-header"):
            resolved = _resolve_from_datadir(pandoc_section.get(key), data_dir, yaml_path, workdir)
            if resolved is not None:
                path_opts.append((key, resolved))
    if data_dir is not None:
        path_opts.append(("data-dir", data_dir))

    highlight_style = pandoc_section.get("syntax-highlighting") or None

    # include-before-body: single path or list. Not used in HTML / reveal mode.
    if simple_mode:
        include_before_body = []
    else:
        include_before_body = _resolve_resource_paths(
            pandoc_section.get("include-before-body"), yaml_path, workdir
        )
        cond_out = resolve_condblock_output(pandoc_section, recipe, yaml_path, workdir)
        if cond_out is not None:
            include_before_body = [cond_out] + include_before_body
            logging.debug("conditional-process-output prepended to include-before-body: %s", cond_out)

    # resource-path: semicolon-separated string or YAML list
    # Resolved paths are written to output.resourcepathfilename as \graphicspath{...}
    # and added to pandoc via --include-in-header.
    # Not used in HTML mode.
    if simple_mode:
        resource_paths = []
        graphicspath_tex = None
    else:
        resource_paths = _resolve_resource_paths(pandoc_section.get("resource-path"), yaml_path, None)
        graphicspath_tex = resolve_out_file(recipe, "resourcepathfilename", yaml_path, workdir)

    logging.debug("yaml     : %s", yaml_path)
    logging.debug("rendered : %s", rendered_path)
    logging.debug("output   : %s", pdf_path)
    logging.debug("defaults : %s", defaults_path)
    logging.debug("filters  : %s", filter_paths)
    for key, p in path_opts:
        logging.debug("%-16s: %s", key, p)
    if highlight_style:
        logging.debug("syntax-highlighting : %s", highlight_style)
    if include_before_body:
        logging.debug("include-before-body: %s", include_before_body)
    if resource_paths:
        logging.debug("resource-path   : %s", resource_paths)
    if graphicspath_tex:
        logging.debug("graphicspath-tex: %s", graphicspath_tex)

    if args.dry_run:
        emit(args, "ok", "pandoc", yaml_path, pdf_path, dry_run=True)
        return EXIT_OK

    if not rendered_path.exists():
        logging.error("Rendered MD not found: %s", rendered_path)
        return EXIT_NOT_FOUND

    if defaults_path is not None and not defaults_path.exists():
        logging.error("Pandoc defaults file not found: %s", defaults_path)
        return EXIT_NOT_FOUND

    for key, p in path_opts:
        if not p.exists():
            logging.error("Pandoc option --%s file not found: %s", key, p)
            return EXIT_NOT_FOUND

    for p in include_before_body:
        if not p.exists():
            logging.error("Pandoc option --include-before-body file not found: %s", p)
            return EXIT_NOT_FOUND

    for p in resource_paths:
        if not p.exists():
            logging.error("resource-path directory not found: %s", p)
            return EXIT_NOT_FOUND

    if missing:
        for name in missing:
            logging.error("Filter not found: %s", name)
        return EXIT_NOT_FOUND

    if pdf_path.exists() and not getattr(args, "force", False):
        logging.error("Output file already exists (use --force to overwrite): %s", pdf_path)
        return EXIT_FAILURE

    if shutil.which("pandoc") is None:
        logging.error("pandoc not found on PATH")
        return EXIT_FAILURE

    # Write \graphicspath{...} tex file when resource-path and output file are both set
    if resource_paths and graphicspath_tex:
        _write_graphicspath(resource_paths, graphicspath_tex)

    pdf_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = ["pandoc", str(rendered_path), "-o", str(pdf_path)]
    if defaults_path is not None:
        cmd += ["-d", str(defaults_path)]
    for fp in filter_paths:
        cmd += ["-L", str(fp)]
    cmd += ["-t", pandoc_format]
    for key, p in path_opts:
        cmd += [f"--{key}", str(p)]
    if highlight_style:
        cmd += [f"--syntax-highlighting={highlight_style}" ]
    for p in include_before_body:
        cmd += ["--include-before-body", str(p)]
    if resource_paths and graphicspath_tex:
        cmd += ["--include-in-header", str(graphicspath_tex)]

    resource_path_value = ";".join([".", *[str(p) for p in resource_paths]])
    cmd += ["--resource-path", resource_path_value]

    logging.debug("cmd:\n%s", "\n".join(cmd))
    _orig_cwd = Path.cwd()
    os.chdir(pdf_path.parent)
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
    finally:
        os.chdir(_orig_cwd)

    if result.stdout:
        logging.info("%s", result.stdout.rstrip())
    if result.stderr:
        (logging.error if result.returncode != 0 else logging.warning)("%s", result.stderr.rstrip())

    if result.returncode != 0:
        logging.error("pandoc exited with code %d", result.returncode)
        return EXIT_FAILURE

    emit(args, "ok", "pandoc", yaml_path, pdf_path)
    return EXIT_OK


# ── helpers ────────────────────────────────────────────────────────────────


def _write_graphicspath(paths: list[Path], out_path: Path) -> None:
    """Write a LaTeX file containing \\graphicspath{{path1/}{path2/}...}."""
    comment = f"% {out_path.name}"
    entries = "\n".join(f"  {{{p.as_posix()}/}}" for p in paths)
    content = f"{comment}\n\\graphicspath{{\n{entries}\n}}\n"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(content, encoding="utf-8")


def _resolve_resource_paths(
    val: "str | list | None",
    yaml_path: Path,
    workdir: Path | None,
) -> list[Path]:
    """Resolve resource-path (semicolon-separated string or YAML list) to a list of Paths."""
    if not val:
        return []
    entries = val if isinstance(val, list) else str(val).split(";")
    result = []
    for entry in entries:
        entry = str(entry).strip()
        if entry:
            p = _resolve_path(entry, yaml_path, workdir)
            if p is not None:
                result.append(p)
    return result


def _resolve_path(val: str | None, yaml_path: Path, workdir: Path | None) -> Path | None:
    if not val:
        return None
    p = Path(val)
    result = p if p.is_absolute() else (workdir if workdir else yaml_path.parent) / p
    if ".." in result.parts:
        return result.resolve()
    return result


def _resolve_from_datadir(
    val: str | None,
    data_dir: Path | None,
    yaml_path: Path,
    workdir: Path | None,
) -> Path | None:
    """Resolve *val* preferring data_dir as base; return canonical (resolved) path.

    Resolution order:
    1. Absolute path — resolved as-is.
    2. Relative path under data_dir — if the file exists there.
    3. Relative path under workdir / yaml_path.parent — fallback.
    """
    if not val:
        return None
    p = Path(val)
    if p.is_absolute():
        return p.resolve()
    if data_dir is not None:
        candidate = (data_dir / p).resolve()
        if candidate.exists():
            return candidate
    base = workdir if workdir else yaml_path.parent
    return (base / p).resolve()


def _resolve_filters(
    names: list[str],
    yaml_path: Path,
    workdir: Path | None,
) -> tuple[list[Path], list[str]]:
    """Resolve filter names to paths.

    Resolution order per entry:
    1. Absolute path — used as-is.
    2. Relative path resolved against yaml_dir (or workdir) — custom filter.
    3. Name looked up in the built-in filters directory.

    Returns (resolved_paths, missing_names).
    """
    resolved: list[Path] = []
    missing: list[str] = []
    base = workdir if workdir else yaml_path.parent

    for name in names:
        p = Path(name)
        if p.is_absolute():
            if p.exists():
                resolved.append(p)
            else:
                missing.append(name)
            continue

        custom = base / p
        if custom.exists():
            resolved.append(custom)
            continue

        builtin = _BUILTIN_FILTERS_DIR / p.name
        if builtin.exists():
            resolved.append(builtin)
            continue

        missing.append(name)

    return resolved, missing
