import argparse
import datetime
import logging
import re
from pathlib import Path

import yaml

_INCLUDE_RE = re.compile(r'^!include\s+(.+?)\s*$')
_RANGE_RE = re.compile(r'\[([^\]]*)\]')

_AUTO_FILENAMES: dict[str, str] = {
    "mdfilename":           "work_{base}_merged.md",
    "idcollectfilename":    "work_{base}_idcollect.yaml",
    "idresolvedfilename":   "work_{base}_idresolve.yaml",
    "renderedfilename":     "{base}_rendered.md",
    "resourcepathfilename": "work_{base}_resourcepath.tex",
    "pdffilename":          "{base}.pdf",
    "texfilename":          "{base}.tex",
    "htmlfilename":         "{base}.html",
    "revealfilename":       "{base}_reveal.html",
    "puremdfilename":       "{base}_puremd.md",
    "pptxfilename":         "{base}.pptx",
}


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


def resolve_condblock_output(
    pandoc_section: dict,
    recipe: dict,
    yaml_path: Path,
    workdir: Path | None,
) -> Path | None:
    """Resolve conditional-process-output path.

    When conditional-process-output is absent/empty, auto-generates
    outputdir/work_<basename(conditional-process-input)>.
    Returns None when conditional-process-input is not set.
    """
    input_val = pandoc_section.get("conditional-process-input")
    if not input_val:
        return None
    output_val = pandoc_section.get("conditional-process-output")
    base = _base_dir(yaml_path, workdir)
    if output_val:
        p = Path(str(output_val))
        return p if p.is_absolute() else base / p
    out_section = recipe.get("output", {})
    outdir_val = out_section.get("outputdir")
    if outdir_val:
        p = Path(str(outdir_val))
        out_dir = p if p.is_absolute() else base / p
    else:
        out_dir = base
    return out_dir / ("work_" + Path(str(input_val)).name)


def get_targetbasefilename(out_section: dict) -> str | None:
    """Return output.targetbasefilename with extension stripped (warns if extension present)."""
    val = out_section.get("targetbasefilename")
    if not val:
        return None
    val = str(val)
    p = Path(val)
    if p.suffix:
        logging.warning(
            "output.targetbasefilename に拡張子が含まれています。拡張子を除去します: '%s' → '%s'",
            val, p.stem,
        )
        val = p.stem
    return val


# ── YAML special constants ─────────────────────────────────────────────────

_SESSION_CONSTANTS: dict[str, str] | None = None


def _get_yaml_constants() -> dict[str, str]:
    """Return __NAME__ → value mapping for recipe YAML substitution.

    Evaluated once per session (cached). Add new constants here.
    """
    global _SESSION_CONSTANTS
    if _SESSION_CONSTANTS is None:
        now = datetime.datetime.now()
        _SESSION_CONSTANTS = {
            "__DATE__":     now.strftime("%Y-%m-%d"),
            "__TIME__":     now.strftime("%H:%M:%S"),
            "__DATETIME__": now.strftime("%Y-%m-%dT%H:%M:%S"),
        }
    return _SESSION_CONSTANTS


def _apply_yaml_constants(text: str) -> str:
    """Replace __CONSTANT__ placeholders in preprocessed YAML text."""
    for placeholder, value in _get_yaml_constants().items():
        text = text.replace(placeholder, value)
    return text


# ── !include preprocessing ─────────────────────────────────────────────────

_STANDALONE_INCLUDE_RE = re.compile(r'^(\s*)!include[ \t]+(\S+?)[ \t]*(?:#.*)?$')
_INLINE_INCLUDE_RE = re.compile(r'!include[ \t]+(\S+?)(?=[ \t]*(?:#.*)?$)')


def _comment_start(s: str) -> int:
    """Return the index of the first YAML comment '#' (preceded by whitespace), or len(s)."""
    for i, c in enumerate(s):
        if c == '#' and (i == 0 or s[i - 1] in (' ', '\t')):
            return i
    return len(s)


def _preprocess_yaml(text: str, base_dir: Path, _seen: frozenset[Path] = frozenset()) -> str:
    """Expand !include directives in YAML text before parsing.

    Standalone lines (``indent!include path``) have their content replaced with
    the included file's lines, each prefixed with the same indentation.
    Inline occurrences (``key: !include path``) replace just the tag+path with
    the included content; multi-line content is placed on the next line with
    increased indentation.
    Paths resolve relative to base_dir. Circular includes raise ValueError.
    """
    result: list[str] = []
    for line in text.splitlines(keepends=True):
        raw = line.rstrip('\r\n')

        # Skip comment-only lines
        if raw.lstrip().startswith('#'):
            result.append(line)
            continue

        m = _STANDALONE_INCLUDE_RE.match(raw)
        if m:
            indent, filename = m.group(1), m.group(2)
            filepath = (base_dir / filename).resolve()
            if filepath in _seen:
                raise ValueError(f"Circular !include: {filepath}")
            inc = _preprocess_yaml(
                filepath.read_text(encoding='utf-8'),
                filepath.parent, _seen | {filepath},
            )
            for inc_line in inc.splitlines(keepends=True):
                result.append(indent + inc_line)
            if inc and not inc.endswith('\n'):
                result.append('\n')
            continue

        # Inline: search only in the non-comment portion of the line
        m = _INLINE_INCLUDE_RE.search(raw[:_comment_start(raw)])
        if m:
            filename = m.group(1)
            filepath = (base_dir / filename).resolve()
            if filepath in _seen:
                raise ValueError(f"Circular !include: {filepath}")
            inc = _preprocess_yaml(
                filepath.read_text(encoding='utf-8'),
                filepath.parent, _seen | {filepath},
            ).rstrip('\n')
            before = raw[:m.start()]
            line_indent = ' ' * (len(raw) - len(raw.lstrip()))
            if '\n' in inc:
                inner = line_indent + '  '
                indented = '\n'.join(inner + l for l in inc.splitlines())
                result.append(before.rstrip() + '\n' + indented + '\n')
            else:
                result.append(before + inc + '\n')
            continue

        result.append(line)
    return ''.join(result)


class _DuplicateKeyLoader(yaml.SafeLoader):
    """SafeLoader that emits a warning on duplicate mapping keys."""
    def construct_mapping(self, node, deep=False):
        seen: set = set()
        for key_node, _ in node.value:
            key = self.construct_object(key_node, deep=False)
            if key in seen:
                logging.warning(
                    "YAML 重複キー: %r (行 %d) — 後の定義で上書きされます",
                    key, key_node.start_mark.line + 1,
                )
            seen.add(key)
        return super().construct_mapping(node, deep=deep)


def load_yaml(yaml_path: Path) -> dict:
    text = yaml_path.read_text(encoding='utf-8')
    text = _preprocess_yaml(text, yaml_path.parent)
    text = _apply_yaml_constants(text)
    return yaml.load(text, Loader=_DuplicateKeyLoader)


def resolve_input_path(args: argparse.Namespace) -> Path | None:
    raw = getattr(args, "input", None)
    return Path(raw).resolve() if raw else None


def _find_in_dirs(fname: str, in_dirs: list[Path]) -> Path | None:
    """Search *in_dirs* for *fname*; warn and return first if found in multiple."""
    found_dirs = [d for d in in_dirs if (d / fname).exists()]
    if not found_dirs:
        return None
    found = [(d / fname).resolve() for d in found_dirs]
    unique = list(dict.fromkeys(found))
    if len(unique) > 1:
        logging.warning(
            "insertmd: '%s' が複数のディレクトリに存在します。最初に見つかったものを使用します: %s\n  発見: %s",
            fname, found[0], ", ".join(str(d) for d in found_dirs),
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

    When the key is absent/empty and output.targetbasefilename is set,
    the filename is auto-generated from targetbasefilename.
    Returns None when neither the key nor targetbasefilename is set.
    """
    out_section = recipe.get("output", {})
    filename = out_section.get(filename_key)
    if not filename:
        base_name = get_targetbasefilename(out_section)
        if base_name and filename_key in _AUTO_FILENAMES:
            filename = _AUTO_FILENAMES[filename_key].format(base=base_name)
        else:
            return None
    base = _base_dir(yaml_path, workdir)
    outdir_val = out_section.get("outputdir")
    out_dir = (Path(outdir_val) if Path(outdir_val).is_absolute() else base / outdir_val) if outdir_val else base
    return out_dir / filename


def setup_recipe_file_logging(recipe: dict, yaml_path: Path, workdir: Path | None) -> None:
    """Add a FileHandler to the root logger when log.filename is set in recipe.

    Directory resolution: log.dir > output.outputdir > base.
    Level: log.level from recipe, else the root logger's current level.
    Already-attached handlers for the same file are not duplicated (safe for pipelines).
    """
    log_cfg = recipe.get("log") or {}
    filename = log_cfg.get("filename")
    if not filename:
        return

    base = _base_dir(yaml_path, workdir)
    log_dir_val = log_cfg.get("dir")
    if log_dir_val:
        p = Path(str(log_dir_val))
        log_dir = p if p.is_absolute() else (base / p).resolve()
    else:
        out_section = recipe.get("output") or {}
        outdir_val = out_section.get("outputdir")
        if outdir_val:
            p = Path(str(outdir_val))
            log_dir = p if p.is_absolute() else (base / p).resolve()
        else:
            log_dir = base

    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = (log_dir / str(filename)).resolve()

    root = logging.getLogger()
    for h in root.handlers:
        if isinstance(h, logging.FileHandler) and Path(h.baseFilename).resolve() == log_path:
            return  # already attached (pipeline re-entry guard)

    level_val = log_cfg.get("level")
    file_level = getattr(logging, str(level_val).upper(), logging.INFO) if level_val else (root.level or logging.INFO)

    # If file level is more verbose than root logger, lower root logger's level
    # and pin existing StreamHandlers to the current level so console output
    # is not affected.
    if file_level < root.level:
        for h in root.handlers:
            if isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler):
                if h.level == logging.NOTSET:
                    h.setLevel(root.level)
        root.setLevel(file_level)

    handler = logging.FileHandler(log_path, encoding="utf-8")
    handler.setLevel(file_level)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-8s %(message)s"))
    root.addHandler(handler)
    logging.debug("log file: %s", log_path)


def apply_recipe_force(args: argparse.Namespace, recipe: dict) -> None:
    """Apply output.force from recipe when --force was not passed on the CLI."""
    if not getattr(args, "force", False):
        args.force = bool((recipe.get("output") or {}).get("force", False))


def resolve_input_dirs(recipe: dict, yaml_path: Path, workdir: Path | None) -> list[Path]:
    """Return the unified input file search path list from input.dirs.

    Relative paths (including '.') are resolved relative to the YAML file's directory.
    input.mddir / input.pptxdir are accepted but deprecated: a recommendation
    is logged and their entries are appended after input.dirs entries.
    Falls back to [workdir or yaml_path.parent] when nothing is specified.
    """
    section = recipe.get("input", {})
    yaml_dir = yaml_path.parent
    base = _base_dir(yaml_path, workdir)
    result: list[Path] = []

    dirs_val = section.get("dirs")
    if dirs_val is None:
        logging.warning(
            "input.dirs が指定されていません。input.dirs の指定を推奨します。"
        )
    else:
        entries = dirs_val if isinstance(dirs_val, list) else [dirs_val]
        for entry in entries:
            p = Path(str(entry))
            result.append((yaml_dir / p).resolve() if not p.is_absolute() else p.resolve())
        if not entries or str(entries[0]).strip() != ".":
            logging.warning(
                "input.dirs の先頭に '.' がありません。"
                "通常は先頭に '.' (recipe YAML のあるディレクトリ) を指定します。"
            )

    mddir_val = section.get("mddir")
    if mddir_val:
        logging.warning(
            "input.mddir は非推奨です。input.dirs の使用を推奨します。"
            "mddir の内容を dirs の末尾に追加します。"
        )
        for entry in (mddir_val if isinstance(mddir_val, list) else [mddir_val]):
            p = Path(str(entry))
            result.append(p if p.is_absolute() else (base / p).resolve())

    pptxdir_val = section.get("pptxdir")
    if pptxdir_val:
        logging.warning(
            "input.pptxdir は非推奨です。input.dirs の使用を推奨します。"
            "pptxdir の内容を dirs の末尾に追加します。"
        )
        for entry in (pptxdir_val if isinstance(pptxdir_val, list) else [pptxdir_val]):
            p = Path(str(entry))
            result.append(p if p.is_absolute() else (base / p).resolve())

    if not result:
        result = [base]
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

    filename = out_section.get("mdfilename")
    if not filename:
        base_name = get_targetbasefilename(out_section)
        filename = _AUTO_FILENAMES["mdfilename"].format(base=base_name) if base_name else (yaml_path.stem + "_merge.md")
    return out_dir / filename


# ── internal helpers ───────────────────────────────────────────────────────


def _resolve_include_ref(current_file: Path, ref: str) -> Path:
    p = Path(ref)
    return p.resolve() if p.is_absolute() else (current_file.parent / p).resolve()


def _base_dir(yaml_path: Path, workdir: Path | None) -> Path:
    return workdir if workdir else yaml_path.parent
