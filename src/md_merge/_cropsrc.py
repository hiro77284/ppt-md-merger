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


# 自動生成するスライド PDF のファイル名サフィックス。
# 以前は ``<pptx_stem>.pdf`` だったが、pptx の stem と ``output.targetbasefilename`` が
# 同じ（よくある命名）だと ppt_to_pdf の最終成果物 PDF と同じパスになり、
# pandoc の出力がスライド PDF を上書きしてしまう。次回実行時、pptpdfexport は
# 「PDF の方が新しい」と判断してスキップし、pptimgexport が成果物 PDF（ページ数が
# スライド数と無関係）から切り出そうとして失敗していた。
AUTO_PDF_SUFFIX = "_slides"


def auto_cropsrc_pdf_path(pptx_val: str, output_section: dict, yaml_path: Path, workdir: Path | None) -> Path:
    """`input.cropsrc[].pdf` 省略時の PDF パス: ``output.outputdir/<pptx_stem>_slides.pdf``。"""
    base = resolve_base(yaml_path, workdir)
    outdir_val = (output_section or {}).get("outputdir")
    if outdir_val:
        p = Path(str(outdir_val))
        out_dir = p if p.is_absolute() else (base / p).resolve()
    else:
        out_dir = base
    return out_dir / (Path(str(pptx_val)).stem + AUTO_PDF_SUFFIX + ".pdf")


def cropsrc_pdf_paths(recipe: dict, yaml_path: Path, workdir: Path | None) -> list[Path]:
    """全 cropsrc エントリのスライド PDF パス（明示指定 or 自動生成）を解決して返す。"""
    output_section = recipe.get("output") or {}
    paths: list[Path] = []
    for entry in cropsrc_entries(recipe):
        if not isinstance(entry, dict):
            continue
        pptx_val = entry.get("pptx")
        pdf_val = entry.get("pdf")
        if pdf_val:
            paths.append(resolve_cropsrc_path(str(pdf_val), yaml_path, workdir))
        elif pptx_val:
            paths.append(auto_cropsrc_pdf_path(str(pptx_val), output_section, yaml_path, workdir))
    return paths
