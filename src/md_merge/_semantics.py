"""Loader for the semantic-structure registry (``semantics.yaml``).

The registry is the single source of truth mapping semantic classes (fenced-div
blocks, bracketed-span inlines, leaf markers) to their per-format lowering rules.
``validate`` and ``puremd`` consume it directly in Python; the pandoc (Lua) path
consumes lookup tables that ``tools/gen_lua_semantics.py`` code-generates from
``inlines`` / ``leaves`` into the semantic-spans.lua / semantic-leaf.lua filters
(regenerate after editing this registry).

This module only *loads and validates* the registry and exposes typed accessors.
It does not itself perform any lowering — each backend interprets the rules.

See docs/design_semantic_lowering.md for the schema.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

# Bundled with the package (declared in pyproject package-data), so it loads
# regardless of the current working directory or install location.
_BUILTIN_PATH = Path(__file__).parent / "semantics.yaml"

_SECTIONS = ("blocks", "inlines", "leaves", "raw")


class SemanticsError(ValueError):
    """Raised when semantics.yaml is missing or structurally invalid."""


@dataclass(frozen=True)
class Semantics:
    """Parsed semantic-structure registry.

    blocks / inlines / leaves map a class (or leaf) name to its rule dict, e.g.
    ``blocks["note"] == {"latex": {"env": "notebox"}, "gfm": {"alert": "NOTE"}, ...}``.
    raw holds the escape-hatch policy.
    """

    version: int
    blocks: dict[str, dict[str, Any]]
    inlines: dict[str, dict[str, Any]]
    leaves: dict[str, dict[str, Any]]
    raw: dict[str, Any]

    # ── name sets ──────────────────────────────────────────────────────────
    def block_classes(self) -> frozenset[str]:
        return frozenset(self.blocks)

    def inline_classes(self) -> frozenset[str]:
        return frozenset(self.inlines)

    def leaf_names(self) -> frozenset[str]:
        return frozenset(self.leaves)

    # ── per-entry accessors ────────────────────────────────────────────────
    def block(self, name: str) -> dict[str, Any] | None:
        return self.blocks.get(name)

    def inline(self, name: str) -> dict[str, Any] | None:
        return self.inlines.get(name)

    def leaf(self, name: str) -> dict[str, Any] | None:
        return self.leaves.get(name)

    def allowed_attrs(self, block_name: str) -> frozenset[str]:
        """Attribute names permitted on a block class (empty if none/unknown)."""
        entry = self.blocks.get(block_name) or {}
        return frozenset(entry.get("attrs") or ())

    # ── gfm (puremd) convenience views ─────────────────────────────────────
    def gfm_alerts(self) -> dict[str, str]:
        """class -> GitHub alert type (e.g. {"note": "NOTE"})."""
        out: dict[str, str] = {}
        for name, rule in self.blocks.items():
            alert = (rule.get("gfm") or {}).get("alert")
            if alert:
                out[name] = str(alert)
        return out

    def gfm_plain_blockquotes(self) -> frozenset[str]:
        """Block classes rendered as a label-less blockquote in GFM."""
        return frozenset(
            name for name, rule in self.blocks.items()
            if (rule.get("gfm") or {}).get("blockquote") == "plain"
        )

    def gfm_unwrap_blocks(self) -> frozenset[str]:
        """Block classes that unwrap (drop fences, keep content) in GFM."""
        return frozenset(
            name for name, rule in self.blocks.items()
            if (rule.get("gfm") or {}).get("unwrap") is True
        )

    def gfm_raw_drop_formats(self) -> tuple[str, ...]:
        """Raw escape-hatch formats stripped when lowering to GFM (e.g. ``('latex',)``).

        Driven by ``raw.gfm.drop`` in the registry. puremd builds ```` ```{=FMT} ````
        fenced-code strip patterns from this list and applies them unconditionally;
        formats in ``allowed_formats`` but absent here (e.g. ``html``) pass through
        because GFM renders them natively.
        """
        gfm = self.raw.get("gfm") or {}
        drop = gfm.get("drop") or []
        return tuple(str(x) for x in drop)


def _require_mapping(value: Any, where: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise SemanticsError(f"{where} はマッピングである必要があります（実際: {type(value).__name__}）")
    return value


def _validate(data: dict[str, Any], src: Path) -> Semantics:
    version = data.get("version")
    if not isinstance(version, int):
        raise SemanticsError(f"{src}: 'version'（整数）が必要です")

    for sect in _SECTIONS:
        if sect not in data:
            raise SemanticsError(f"{src}: セクション '{sect}' がありません")

    blocks = _require_mapping(data["blocks"], f"{src}: blocks")
    inlines = _require_mapping(data["inlines"], f"{src}: inlines")
    leaves = _require_mapping(data["leaves"], f"{src}: leaves")
    raw = _require_mapping(data["raw"], f"{src}: raw")

    # Each entry must itself be a mapping; surface bad entries with their name.
    for sect_name, sect in (("blocks", blocks), ("inlines", inlines), ("leaves", leaves)):
        for key, entry in sect.items():
            _require_mapping(entry, f"{src}: {sect_name}.{key}")

    return Semantics(version=version, blocks=blocks, inlines=inlines, leaves=leaves, raw=raw)


@lru_cache(maxsize=None)
def _load_cached(path_str: str) -> Semantics:
    path = Path(path_str)
    if not path.exists():
        raise SemanticsError(f"semantics.yaml が見つかりません: {path}")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise SemanticsError(f"semantics.yaml の YAML 解析に失敗: {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise SemanticsError(f"semantics.yaml はマッピングである必要があります: {path}")
    return _validate(data, path)


def load_semantics(path: Path | None = None) -> Semantics:
    """Load and validate the semantics registry.

    With ``path=None`` the bundled built-in registry is used. Results are cached
    per resolved path. Raises :class:`SemanticsError` on missing/invalid input.
    """
    resolved = (path or _BUILTIN_PATH).resolve()
    return _load_cached(str(resolved))
