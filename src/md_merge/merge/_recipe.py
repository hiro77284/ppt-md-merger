import argparse
import logging
import re
from pathlib import Path

import yaml

_INCLUDE_RE = re.compile(r'^!include\s+(.+?)\s*$')
_RANGE_RE = re.compile(r'\[([^\]]*)\]')


# ── exceptions ─────────────────────────────────────────────────────────────


class CircularIncludeError(Exception):
    def __init__(self, path: Path, chain: frozenset[Path]) -> None:
        self.path = path
        self.chain = chain
        super().__init__(f"Circular include: {path}")


class IncludeNotFoundError(Exception):
    def __init__(self, path: Path) -> None:
        self.path = path
        super().__init__(f"Include target not found: {path}")


# ── range expansion ────────────────────────────────────────────────────────


def _expand_mdfilename(val: str) -> list[str]:
    """Expand a single ``[from-to]`` range in *val* and return the filename list.

    Raises ValueError for invalid range specifications.
    """
    m = _RANGE_RE.search(val)
    if m is None:
        return [val]

    spec = m.group(1)
    prefix = val[: m.start()]
    suffix = val[m.end() :]

    if not spec.isascii():
        raise ValueError(f"全角文字は使用できません: [{spec}]")

    parts = spec.split("-")
    if len(parts) != 2 or not parts[0] or not parts[1]:
        raise ValueError(f"[from-to] 形式で指定してください: [{spec}]")

    frm, to = parts

    if frm.isdigit() and to.isdigit():
        frm_i, to_i = int(frm), int(to)
        if frm.startswith("0") or to.startswith("0"):
            width = max(len(frm), len(to))
            fmt = lambda n: str(n).zfill(width)  # noqa: E731
        else:
            fmt = str
        step = 1 if frm_i <= to_i else -1
        return [prefix + fmt(n) + suffix for n in range(frm_i, to_i + step, step)]

    if len(frm) == 1 and len(to) == 1 and frm.isalpha() and to.isalpha():
        if frm.isupper() != to.isupper():
            raise ValueError(f"from と to の大文字小文字が一致しません: [{spec}]")
        step = 1 if frm <= to else -1
        return [prefix + chr(c) + suffix for c in range(ord(frm), ord(to) + step, step)]

    raise ValueError(
        f"from/to は数値または単一アルファベット文字で指定してください: [{spec}]"
    )


# ── public API ─────────────────────────────────────────────────────────────


def load_yaml(yaml_path: Path) -> dict:
    with yaml_path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def resolve_input_path(args: argparse.Namespace) -> Path | None:
    raw = getattr(args, "input", None)
    return Path(raw).resolve() if raw else None


def _find_in_dirs(fname: str, in_dirs: list[Path]) -> Path | None:
    """Search *in_dirs* for *fname*; warn and return first if found in multiple."""
    found = [(d / fname).resolve() for d in in_dirs if (d / fname).exists()]
    if not found:
        return None
    if len(found) > 1:
        logging.warning(
            "insertmd: '%s' が複数のディレクトリに存在します。最初に見つかったものを使用します: %s",
            fname, found[0],
        )
    return found[0]


def collect_procedure_items(recipe: dict, in_dirs: list[Path], yaml_path: Path) -> list[Path | str]:
    items: list[Path | str] = []
    auto_id_counter = 0
    for item in recipe.get("procedure", []):
        op = item.get("operation")
        if op == "insertmd":
            val = item.get("mdfilename")
            if not val:
                logging.warning("insertmd entry missing 'mdfilename' field — skipping")
                continue
            try:
                filenames = _expand_mdfilename(val)
            except ValueError as e:
                logging.warning("insertmd mdfilename range error: %s — skipping", e)
                continue
            for fname in filenames:
                p = Path(fname)
                logging.debug("collect_procedure_items: %s", p)
                if p.is_absolute():
                    items.append(p)
                elif in_dirs:
                    found = _find_in_dirs(fname, in_dirs)
                    items.append(found if found is not None else (in_dirs[0] / fname).resolve())
                else:
                    items.append(yaml_path.parent / p)
        elif op in ("chapter", "section", "subsection"):
            value = str(item.get(op, "")).strip("\"'")
            title = item.get("title") or ""
            hashes = {"chapter": "#", "section": "##", "subsection": "###"}[op]
            auto_id_counter += 1
            items.append(
                f"<!-- md_merge {{{{{op}:{value}}}}} {{{{title:{title}}}}} -->\n"
                f"{{{{#id:{op}:AUTOCHAPTER:AUTOID_{auto_id_counter}}}}}\n"
                f"{hashes} {title}"
            )
    return items


def expand_md(
    path: Path,
    chain: frozenset[Path] = frozenset(),
    strict: bool = False,
    yaml_dir: Path | None = None,
    image_copier=None,
    file_log: "list[Path] | None" = None,
) -> str:
    """Read *path* and recursively expand any ``!include`` directives.

    *chain* holds the resolved paths of all ancestors in the current call
    stack.  The same file may appear in sibling branches (parallel includes),
    but appearing in *chain* means a circular dependency.

    Each expanded file is preceded by an HTML comment recording its path
    relative to *yaml_dir* (falls back to absolute when outside *yaml_dir*).

    If *image_copier* is provided, local image references on each line are
    copied to the output directory and their paths rewritten.

    If *file_log* is provided, the resolved path of every expanded file
    (including recursively included ones) is appended to it in processing order.
    The same file is recorded each time it appears (duplicates allowed).
    """
    path = path.resolve()
    new_chain = chain | {path}

    if file_log is not None:
        file_log.append(path)

    try:
        display = path.relative_to(yaml_dir).as_posix() if yaml_dir else path.as_posix()
    except ValueError:
        display = path.as_posix()

    lines = path.read_text(encoding="utf-8-sig").splitlines(keepends=True)
    parts: list[str] = [f"<!-- source: {display} -->\n"]
    for line in lines:
        m = _INCLUDE_RE.match(line)
        if not m:
            if image_copier is not None:
                line = image_copier.process(line, path)
            parts.append(line)
            continue
        ref_path = _resolve_include_ref(path, m.group(1))
        if ref_path in new_chain:
            raise CircularIncludeError(ref_path, new_chain)
        if not ref_path.exists():
            if strict:
                raise IncludeNotFoundError(ref_path)
            logging.warning("Include target not found: %s — skipping", ref_path)
            continue
        parts.append(expand_md(
            ref_path, new_chain,
            strict=strict, yaml_dir=yaml_dir,
            image_copier=image_copier, file_log=file_log,
        ))
    return "".join(parts)


def resolve_workdir(recipe: dict, yaml_path: Path, cli_workdir: Path | None) -> Path | None:
    """Return effective workdir: CLI arg > recipe 'workdir' key > None (yaml parent is default)."""
    if cli_workdir is not None:
        return cli_workdir
    val = recipe.get("workdir")
    if val:
        p = Path(str(val))
        return p.resolve() if p.is_absolute() else (yaml_path.parent / p).resolve()
    return None


def resolve_out_file(
    recipe: dict,
    filename_key: str,
    yaml_path: Path,
    workdir: Path | None,
) -> Path | None:
    """Resolve output.<filename_key> under output.outputdir from *recipe*.

    Returns None when the key is absent from the output section.
    """
    out_section = recipe.get("output", {})
    filename = out_section.get(filename_key)
    if not filename:
        return None
    base = _base_dir(yaml_path, workdir)
    outdir_val = out_section.get("outputdir")
    out_dir = (Path(outdir_val) if Path(outdir_val).is_absolute() else base / outdir_val) if outdir_val else base
    return out_dir / filename


def apply_recipe_force(args: argparse.Namespace, recipe: dict) -> None:
    """Apply output.force from recipe when --force was not passed on the CLI."""
    if not getattr(args, "force", False):
        args.force = bool((recipe.get("output") or {}).get("force", False))


def resolve_input_mddir(recipe: dict, yaml_path: Path, workdir: Path | None) -> list[Path]:
    """Return the list of resolved input mddirs.

    When mddir is unset, returns [base] (recipe YAML directory by default).
    """
    section = recipe.get("input", {})
    base = _base_dir(yaml_path, workdir)
    val = section.get("mddir")
    if not val:
        return [base]
    entries = val if isinstance(val, list) else [val]
    result = []
    for entry in entries:
        p = Path(entry)
        result.append(p if p.is_absolute() else base / p)
    return result


def resolve_output_path(
    recipe: dict,
    yaml_path: Path,
    workdir: Path | None,
) -> Path:
    out_section = recipe.get("output", {})
    base = _base_dir(yaml_path, workdir)

    outdir_val = out_section.get("outputdir")
    out_dir = (Path(outdir_val) if Path(outdir_val).is_absolute() else base / outdir_val) if outdir_val else base

    filename = out_section.get("mdfilename") or (yaml_path.stem + "_merge.md")
    return out_dir / filename


# ── internal helpers ───────────────────────────────────────────────────────


def _resolve_include_ref(current_file: Path, ref: str) -> Path:
    p = Path(ref)
    return p.resolve() if p.is_absolute() else (current_file.parent / p).resolve()


def _base_dir(yaml_path: Path, workdir: Path | None) -> Path:
    return workdir if workdir else yaml_path.parent
