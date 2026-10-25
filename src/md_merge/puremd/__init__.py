from __future__ import annotations

import argparse
import logging
import re
from pathlib import Path
from typing import Any

import yaml

from md_merge._output import EXIT_BAD_INPUT, EXIT_FAILURE, EXIT_NOT_FOUND, EXIT_OK, emit, setup_logging
from md_merge._semantics import Semantics, SemanticsError, load_semantics
from md_merge.merge._recipe import apply_recipe_force, load_yaml, resolve_input_path, resolve_out_file, resolve_workdir, setup_recipe_file_logging

# ── registry-driven raw escape-hatch drop ────────────────────────────────────
# Dropping raw passthrough blocks (```` ```{=latex} ````) when lowering to GFM is
# the escape-hatch contract from the semantic registry (semantics.yaml raw.gfm.drop),
# NOT a user config concern. puremd applies it unconditionally, independent of
# puremd.strip_config (which is for project-custom removals only).

def _raw_drop_langs(sem: Semantics) -> frozenset[str]:
    """Fence language identifiers ({=latex} etc.) dropped for GFM per the registry."""
    return frozenset(f"{{={fmt}}}" for fmt in sem.gfm_raw_drop_formats())


def _build_raw_drop_patterns(sem: Semantics) -> list[tuple[re.Pattern, str]]:
    """Compile the registry-driven raw escape-hatch strip patterns for GFM."""
    return [
        _compile_pattern({"name": f"raw_{fmt}_block", "type": "fenced_code", "lang": f"{{={fmt}}}"})
        for fmt in sem.gfm_raw_drop_formats()
    ]


# ── pattern compilation ───────────────────────────────────────────────────────

def _compile_pattern(entry: dict[str, Any]) -> tuple[re.Pattern, str]:
    """Compile a strip config entry into a (pattern, name) tuple.

    Supported types:
      fenced_code   — removes ```{lang}\\n...\\n``` blocks（fenced *code* block）
      regex         — removes substrings matching an arbitrary regex

    'fenced_block' は 'fenced_code' の非推奨エイリアス（pandoc の fenced *div* と
    紛らわしいため改名）。当面は警告付きで受理する。
    """
    name = entry.get("name", "<unnamed>")
    ptype = entry.get("type", "").strip()

    if ptype == "fenced_block":
        logging.warning(
            "strip entry '%s': type 'fenced_block' は非推奨です。'fenced_code' を使用してください",
            name,
        )
        ptype = "fenced_code"

    if ptype == "fenced_code":
        lang = entry.get("lang", "")
        if not lang:
            raise ValueError(f"strip entry '{name}': 'lang' is required for type 'fenced_code'")
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

    raise ValueError(f"strip entry '{name}': unknown type '{ptype}' (expected 'fenced_code' or 'regex')")


def _load_strip_patterns(
    strip_config_path: Path,
) -> list[dict]:
    """Load strip patterns from a YAML config file.

    Expected format::

        strip:
          - name: latex_raw_block
            type: fenced_code
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


# ── semantic lowering to plain Markdown (GFM) ─────────────────────────────────
# Block fenced divs, inline bracketed spans, and leaf markers are lowered to plain
# Markdown so the content survives while still standing out from body text. The
# class/marker -> GFM rules come from the semantic registry (semantics.yaml);
# recipe puremd.fenced_div.* layers on top for alerts / plain_blockquote.
#
# Fenced div (block):
#   - registry gfm.alert       -> GitHub-style alert (``> [!NOTE]`` ...)
#   - registry gfm.blockquote=plain -> label-less blockquote
#   - registry gfm.unwrap      -> unwrapped (content kept, fences dropped)
#   - any other named class    -> labelled blockquote (``> **CLASS**`` ...)
#   - no class (attrs only)    -> unwrapped
# Inline span ``[text]{.class}``  -> registry gfm.wrap (``**``/``*``/`` ` ``) or
#                                    gfm.html element (e.g. ``<kbd>``)
# Leaf ``{{name}}`` / ``{{name:arg}}`` -> registry gfm.drop / gfm.text

# Inline bracketed spans: ``[text]{.class}``. The ``]{`` sequence distinguishes a
# span from a markdown link (``](``), so the match is safe against normal links.
_SPAN_RE = re.compile(r"\[([^\]]*)\]\{([^}]*)\}")

_FENCE_CLOSE_RE = re.compile(r'^:{3,}[ \t]*$')
_FENCE_OPEN_RE = re.compile(r'^(:{3,})[ \t]*(.*?)[ \t]*$')


def _fence_open_classes(line: str) -> list[str] | None:
    """Return the class list of an opening fenced-div line, or None if not one.

    A closing fence (colons only) and non-fence lines return None. An opening
    fence with attributes but no class returns an empty list.
    """
    if _FENCE_CLOSE_RE.match(line):
        return None
    m = _FENCE_OPEN_RE.match(line)
    if not m:
        return None
    rest = m.group(2)
    if not rest:
        return None
    classes: list[str] = []
    if rest.startswith("{") and rest.endswith("}"):
        for tok in rest[1:-1].split():
            if tok.startswith("."):
                classes.append(tok[1:])
    else:
        first = rest.split()[0]
        classes.append(first[1:] if first.startswith(".") else first)
    return classes


def _quote(line: str) -> str:
    return ">" if line.strip() == "" else "> " + line


def _render_div(
    cls: str | None,
    inner: list[str],
    alerts: dict[str, str],
    plain_quotes: set[str],
    unwrap_classes: set[str],
) -> list[str]:
    # Trim blank lines at the inner edges so the blockquote starts/ends cleanly.
    while inner and inner[0].strip() == "":
        inner.pop(0)
    while inner and inner[-1].strip() == "":
        inner.pop()

    if cls is None:
        # No class to distinguish on: unwrap (drop fences, keep content).
        return inner

    alert = alerts.get(cls)
    if alert:
        logging.debug("puremd: fenced div '.%s' -> alert [!%s]", cls, alert)
        return [f"> [!{alert}]"] + [_quote(line) for line in inner]

    if cls in plain_quotes:
        logging.debug("puremd: fenced div '.%s' -> plain blockquote", cls)
        return [_quote(line) for line in inner]

    if cls in unwrap_classes:
        logging.debug("puremd: fenced div '.%s' -> unwrap", cls)
        return inner

    logging.debug("puremd: fenced div '.%s' -> labelled blockquote", cls)
    label = cls.upper()
    return [f"> **{label}**", ">"] + [_quote(line) for line in inner]


def _collect_div(lines: list[str], i: int) -> tuple[list[str], int]:
    """Collect raw inner lines until the matching close fence (nesting-aware)."""
    depth = 1
    inner: list[str] = []
    n = len(lines)
    while i < n:
        line = lines[i]
        if _fence_open_classes(line) is not None:
            depth += 1
            inner.append(line)
        elif _FENCE_CLOSE_RE.match(line):
            depth -= 1
            if depth == 0:
                return inner, i + 1
            inner.append(line)
        else:
            inner.append(line)
        i += 1
    logging.warning("puremd: 閉じられていない fenced div を検出しました。残りを内容として扱います。")
    return inner, i


def _transform_lines(
    lines: list[str], alerts: dict[str, str], plain_quotes: set[str], unwrap_classes: set[str]
) -> list[str]:
    out: list[str] = []
    i = 0
    n = len(lines)
    while i < n:
        classes = _fence_open_classes(lines[i])
        if classes is not None:
            inner_raw, j = _collect_div(lines, i + 1)
            inner = _transform_lines(inner_raw, alerts, plain_quotes, unwrap_classes)  # recurse for nested divs
            cls = classes[0] if classes else None
            out.extend(_render_div(cls, inner, alerts, plain_quotes, unwrap_classes))
            i = j
        else:
            out.append(lines[i])
            i += 1
    return out


def _transform_fenced_divs(
    content: str, alerts: dict[str, str], plain_quotes: set[str], unwrap_classes: set[str]
) -> str:
    return "\n".join(_transform_lines(content.split("\n"), alerts, plain_quotes, unwrap_classes))


def _span_class(attr: str) -> str | None:
    """First ``.class`` token from a bracketed-span attribute string, or None."""
    for tok in attr.split():
        if tok.startswith("."):
            return tok[1:]
    return None


def _transform_inline_spans(content: str, sem: Semantics) -> str:
    """Lower pandoc bracketed spans ``[text]{.class}`` to GFM per the registry.

    Known inline classes use their ``gfm`` rule — wrap chars (``**``/``*``/`` ` ``)
    or an HTML element such as ``<kbd>``. Unknown or class-less spans unwrap to
    their text (attributes dropped) so no literal ``{...}`` leaks into the output.
    """
    def repl(m: "re.Match[str]") -> str:
        text, attr = m.group(1), m.group(2)
        cls = _span_class(attr)
        rule = sem.inline(cls) if cls else None
        if rule:
            g = rule.get("gfm") or {}
            wrap = g.get("wrap")
            if wrap:
                return f"{wrap}{text}{wrap}"
            html = g.get("html")
            if html:
                return f"<{html}>{text}</{html}>"
        return text

    return _SPAN_RE.sub(repl, content)


def _transform_leaves(content: str, sem: Semantics) -> str:
    """Lower leaf markers (``{{vspace:N}}`` / ``{{pagebreak}}`` / ``{{vfill}}``) per registry.

    GFM rules: ``drop`` removes the marker entirely; ``text`` replaces it with a
    literal (e.g. ``---`` for a page break).
    """
    for name, rule in sem.leaves.items():
        if rule.get("arg"):
            rx = re.compile(r"\{\{" + re.escape(name) + r":[^}]*\}\}")
        else:
            rx = re.compile(r"\{\{" + re.escape(name) + r"\}\}")
        g = rule.get("gfm") or {}
        if g.get("drop"):
            content = rx.sub("", content)
        elif "text" in g:
            replacement = str(g["text"])
            content = rx.sub(lambda _m: replacement, content)  # lambda: avoid backref interpretation
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
    setup_recipe_file_logging(recipe, yaml_path, workdir)
    apply_recipe_force(args, recipe)

    rendered_path = resolve_out_file(recipe, "renderedfilename", yaml_path, workdir)
    if rendered_path is None:
        logging.error("output.renderedfilename is not specified in %s", yaml_path)
        return EXIT_BAD_INPUT

    puremd_path = resolve_out_file(recipe, "puremdfilename", yaml_path, workdir)
    if puremd_path is None:
        logging.error("output.puremdfilename is not specified in %s", yaml_path)
        return EXIT_BAD_INPUT

    puremd_section = recipe.get("puremd") or {}

    # Semantic registry: base lowering rules + the raw escape-hatch drop contract.
    try:
        sem = load_semantics()
    except SemanticsError as exc:
        logging.error("puremd: セマンティックレジストリの読み込みに失敗: %s", exc)
        return EXIT_FAILURE

    # Strip patterns = registry-driven raw escape-hatch drop (always applied) +
    # optional user strip_config (project-custom removals only). Dropping raw
    # ```{=latex} blocks is a built-in contract (semantics.yaml raw.gfm.drop), no
    # longer something a recipe must declare.
    try:
        raw_patterns = _build_raw_drop_patterns(sem)
    except ValueError as exc:
        logging.error("puremd: raw-drop pattern compile error: %s", exc)
        return EXIT_FAILURE
    logging.debug("puremd: %d built-in raw-drop pattern(s) from registry (drop=%s)",
                  len(raw_patterns), list(sem.gfm_raw_drop_formats()))

    user_patterns: list[tuple[re.Pattern, str]] = []
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
        builtin_langs = _raw_drop_langs(sem)
        try:
            for i, e in enumerate(raw_entries):
                is_fenced = e.get("type") in ("fenced_code", "fenced_block")
                logging.debug("  [%d] name=%s type=%s %s", i, e.get("name"), e.get("type"),
                              f"lang={e.get('lang')!r}" if is_fenced else f"pattern={e.get('pattern')!r}")
                if is_fenced and e.get("lang") in builtin_langs:
                    logging.warning(
                        "strip entry '%s': raw %s ブロックの除去は組み込み化されました"
                        "（semantics.yaml raw.gfm.drop）。strip_config から削除してください",
                        e.get("name", "<unnamed>"), e.get("lang"),
                    )
                    continue
                user_patterns.append(_compile_pattern(e))
        except ValueError as exc:
            logging.error("puremd: pattern compile error: %s", exc)
            return EXIT_BAD_INPUT

    patterns = raw_patterns + user_patterns
    for rx, name in patterns:
        logging.debug("puremd: compiled pattern '%s' = %r", name, rx.pattern)

    # ── fenced div transform config ────────────────────────────────────────
    fenced_cfg = puremd_section.get("fenced_div")
    if fenced_cfg is None:
        fenced_cfg = {}
    if not isinstance(fenced_cfg, dict):
        logging.error("puremd.fenced_div はマッピングである必要があります")
        return EXIT_BAD_INPUT
    fenced_enabled = fenced_cfg.get("enabled", True)

    # Recipe overrides layer on top of the semantic registry's fenced-div rules.
    alerts = dict(sem.gfm_alerts())
    user_alerts = fenced_cfg.get("alerts")
    if user_alerts is not None:
        if not isinstance(user_alerts, dict):
            logging.error("puremd.fenced_div.alerts はマッピングである必要があります")
            return EXIT_BAD_INPUT
        for k, v in user_alerts.items():
            alerts[str(k)] = str(v).strip().lstrip("!").strip().upper()
    plain_quotes = set(sem.gfm_plain_blockquotes())
    user_plain = fenced_cfg.get("plain_blockquote")
    if user_plain is not None:
        if not isinstance(user_plain, list):
            logging.error("puremd.fenced_div.plain_blockquote はリストである必要があります")
            return EXIT_BAD_INPUT
        plain_quotes.update(str(x) for x in user_plain)
    unwrap_classes = set(sem.gfm_unwrap_blocks())
    logging.debug(
        "puremd: fenced_div enabled=%s alerts=%s plain_quotes=%s unwrap=%s",
        fenced_enabled, alerts, sorted(plain_quotes), sorted(unwrap_classes),
    )

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
    if fenced_enabled:
        content = _transform_fenced_divs(content, alerts, plain_quotes, unwrap_classes)
    # Inline spans and leaf markers are new semantic constructs (no existing content
    # uses them), so lowering them is always-on and cannot affect legacy documents.
    content = _transform_inline_spans(content, sem)
    content = _transform_leaves(content, sem)

    try:
        puremd_path.parent.mkdir(parents=True, exist_ok=True)
        puremd_path.write_text(content, encoding="utf-8")
    except Exception as exc:
        logging.error("Failed to write %s: %s", puremd_path, exc)
        return EXIT_FAILURE

    emit(args, "ok", "puremd", rendered_path, puremd_path)
    return EXIT_OK
