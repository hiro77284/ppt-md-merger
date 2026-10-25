"""`input.cropsrc` セクションの共有ヘルパ。

pptimgexport / pptmdexport / pptyamlexport / pptpdfexport と `--preprocess` は
いずれも同じ `input.cropsrc` を読む。各サブコマンドが同一の正規化・パス解決を
私有コピーで持っていたため、ここに集約する。
"""

from __future__ import annotations

from pathlib import Path

from md_merge.pptmerge._config import resolve_base


def normalize_cropsrc(cropsrc: dict | list) -> list[dict]:
    """cropsrc を常にリストとして返す（辞書は単一要素リストに変換）。"""
    if isinstance(cropsrc, list):
        return cropsrc
    if isinstance(cropsrc, dict):
        return [cropsrc]
    return []


def cropsrc_entries(recipe: dict) -> list[dict]:
    """レシピの `input.cropsrc` を正規化済みリストとして返す。"""
    return normalize_cropsrc((recipe.get("input") or {}).get("cropsrc") or {})


def resolve_cropsrc_path(val: str, yaml_path: Path, workdir: Path | None) -> Path:
    """cropsrc のパス値を解決する（絶対パスはそのまま、相対はレシピ基準）。"""
    base = resolve_base(yaml_path, workdir)
    p = Path(val)
    return p if p.is_absolute() else (base / p).resolve()
