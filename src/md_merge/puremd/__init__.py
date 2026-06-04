from __future__ import annotations

import argparse
import logging
import re
from pathlib import Path
from typing import Any

import yaml

from md_merge._output import EXIT_BAD_INPUT, EXIT_FAILURE, EXIT_NOT_FOUND, EXIT_OK, emit, setup_logging
from md_merge.merge._recipe import apply_recipe_force, load_yaml, resolve_input_path, resolve_out_file, resolve_workdir

# ── built-in default strip patterns ──────────────────────────────────────────
# Applied when puremd.strip_config is not specified in the recipe.
_DEFAULT_STRIP_PATTERNS: list[dict] = [
    {
        "name": "latex_raw_block",
        "description": "Pandoc raw LaTeX fenced blocks",
        "type": "fenced_block",
        "lang": "{=latex}",
    },
]


# ── pattern compilation ───────────────────────────────────────────────────────

def _compile_pattern(entry: dict[str, Any]) -> tuple[re.Pattern, str]:
    """Compile a strip config entry into a (pattern, name) tuple.

    Supported types:
      fenced_block  — removes ```{lang}\\n...\\n``` blocks
      regex         — removes substrings matching an arbitrary regex
    """
    name = entry.get("name", "<unnamed>")
    ptype = entry.get("type", "").strip()

    if ptype == "fenced_block":
        lang = entry.get("lang", "")
        if not lang:
            raise ValueError(f"strip entry '{name}': 'lang' is required for type 'fenced_block'")
        lang_esc = re.escape(lang)
        # Matches the opening fence line, any body, and the closing fence line.
        # Uses MULTILINE so ^ anchors to line boundaries.
        # [\s\S]*? is non-greedy and crosses newlines without DOTALL.
        rx = re.compile(
            rf'^```{lang_esc}[ \t]*\n[\s\S]*?^```[ \t]*\n?',
            re.MULTILINE,
        )
        return rx, name

    if ptype == "regex":
        raw = entry.get("pattern", "")
        if not raw:
            raise ValueError(f"strip entry '{name}': 'pattern' is required for type 'regex'")
        flags = re.MULTILINE
        if entry.get("dotall"):
            flags |= re.DOTALL
        if entry.get("ignorecase"):
            flags |= re.IGNORECASE
        try:
            rx = re.compile(raw, flags)
        except re.error as exc:
            raise ValueError(f"strip entry '{name}': invalid regex: {exc}") from exc
        return rx, name

    raise ValueError(f"strip entry '{name}': unknown type '{ptype}' (expected 'fenced_block' or 'regex')")


def _load_strip_patterns(
    strip_config_path: Path,
) -> list[dict]:
    """Load strip patterns from a YAML config file.

    Expected format::

        strip:
          - name: latex_raw_block
            type: fenced_block
            lang: "{=latex}"
          - name: my_regex
            type: regex
            pattern: '\\\\someCommand\\{[^}]*\\}'
            dotall: false
    """
    with strip_config_path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError(f"strip config must be a YAML mapping: {strip_config_path}")
    entries = data.get("strip")
    if not isinstance(entries, list):
        raise ValueError(f"strip config must have a 'strip' list: {strip_config_path}")
    return entries


def _apply_patterns(content: str, patterns: list[tuple[re.Pattern, str]]) -> str:
    for rx, name in patterns:
        before = len(content)
        content = rx.sub("", content)
        removed = before - len(content)
        if removed:
            logging.debug("puremd: pattern '%s' removed %d char(s)", name, removed)
        else:
            logging.debug("puremd: pattern '%s' matched nothing", name)
    return content


# ── subcommand entry point ────────────────────────────────────────────────────

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

    rendered_path = resolve_out_file(recipe, "renderedfilename", yaml_path, workdir)
    if rendered_path is None:
        logging.error("output.renderedfilename is not specified in %s", yaml_path)
        return EXIT_BAD_INPUT

    puremd_path = resolve_out_file(recipe, "puremdfilename", yaml_path, workdir)
    if puremd_path is None:
        logging.error("output.puremdfilename is not specified in %s", yaml_path)
        return EXIT_BAD_INPUT

    # Load strip patterns from config file or fall back to built-in defaults
    puremd_section = recipe.get("puremd") or {}
    strip_config_val = puremd_section.get("strip_config")

    if strip_config_val:
        cfg_path = Path(strip_config_val)
        if not cfg_path.is_absolute():
            base = workdir if workdir else yaml_path.parent
            cfg_path = (base / cfg_path).resolve()
        logging.debug("puremd: strip_config path = %s", cfg_path)
        if not cfg_path.exists():
            logging.error("puremd.strip_config file not found: %s", cfg_path)
            return EXIT_NOT_FOUND
        try:
            raw_entries = _load_strip_patterns(cfg_path)
        except ValueError as exc:
            logging.error("puremd.strip_config load error: %s", exc)
            return EXIT_BAD_INPUT
        logging.debug("puremd: loaded %d pattern(s) from %s", len(raw_entries), cfg_path)
        for i, e in enumerate(raw_entries):
            logging.debug("  [%d] name=%s type=%s %s", i, e.get("name"), e.get("type"),
                          f"lang={e.get('lang')!r}" if e.get("type") == "fenced_block" else f"pattern={e.get('pattern')!r}")
    else:
        raw_entries = _DEFAULT_STRIP_PATTERNS
        logging.debug("puremd: strip_config not specified — using %d built-in default pattern(s)", len(raw_entries))

    try:
        patterns = [_compile_pattern(e) for e in raw_entries]
    except ValueError as exc:
        logging.error("puremd: pattern compile error: %s", exc)
        return EXIT_BAD_INPUT

    for rx, name in patterns:
        logging.debug("puremd: compiled pattern '%s' = %r", name, rx.pattern)

    logging.debug("rendered : %s", rendered_path)
    logging.debug("puremd   : %s", puremd_path)

    if args.dry_run:
        emit(args, "ok", "puremd", rendered_path, puremd_path, dry_run=True)
        return EXIT_OK

    if not rendered_path.exists():
        logging.error("Rendered MD not found: %s", rendered_path)
        return EXIT_NOT_FOUND

    if puremd_path.exists() and not getattr(args, "force", False):
        logging.error("Output file already exists (use --force to overwrite): %s", puremd_path)
        return EXIT_FAILURE

    content = rendered_path.read_text(encoding="utf-8")
    content = _apply_patterns(content, patterns)

    try:
        puremd_path.parent.mkdir(parents=True, exist_ok=True)
        puremd_path.write_text(content, encoding="utf-8")
    except Exception as exc:
        logging.error("Failed to write %s: %s", puremd_path, exc)
        return EXIT_FAILURE

    emit(args, "ok", "puremd", rendered_path, puremd_path)
    return EXIT_OK
