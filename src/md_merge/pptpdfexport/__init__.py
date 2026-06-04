from __future__ import annotations

import argparse
import logging
from pathlib import Path

from md_merge._output import EXIT_BAD_INPUT, EXIT_FAILURE, EXIT_NOT_FOUND, EXIT_OK, emit, setup_logging
from md_merge.merge._recipe import load_yaml, resolve_input_path, resolve_workdir
from md_merge.pptmerge._config import resolve_base

# PowerPoint SaveAs format constant for PDF
_PP_SAVE_AS_PDF = 32


def _is_already_open(ppt_app: object, pptx_path: Path) -> bool:
    """Return True if pptx_path is already open in this PowerPoint instance."""
    target = str(pptx_path).lower()
    try:
        for i in range(1, ppt_app.Presentations.Count + 1):
            try:
                if ppt_app.Presentations(i).FullName.lower() == target:
                    return True
            except Exception:
                pass
    except Exception:
        pass
    return False


def _normalize_cropsrc(cropsrc: dict | list) -> list[dict]:
    """cropsrc を常にリストとして返す（辞書は単一要素リストに変換）。"""
    if isinstance(cropsrc, list):
        return cropsrc
    if isinstance(cropsrc, dict):
        return [cropsrc]
    return []


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
    raw_cropsrc = (recipe.get("input") or {}).get("cropsrc") or {}
    entries = _normalize_cropsrc(raw_cropsrc)
    output_section = recipe.get("output") or {}
    cli_workdir = Path(args.workdir).resolve() if getattr(args, "workdir", None) else None
    workdir = resolve_workdir(recipe, yaml_path, cli_workdir)
    recipe_force = bool(output_section.get("force"))
    force = getattr(args, "force", False) or recipe_force
    dry_run = getattr(args, "dry_run", False)

    if not entries:
        logging.error("input.cropsrc が指定されていません: %s", yaml_path)
        return EXIT_BAD_INPUT

    # ── 全エントリのパス解決と事前検証（fail fast）────────────────────────
    resolved: list[tuple[Path, Path]] = []
    for i, entry in enumerate(entries):
        label = f"input.cropsrc[{i}]" if len(entries) > 1 else "input.cropsrc"
        pptx_val = entry.get("pptx")
        pdf_val = entry.get("pdf")

        if not pptx_val:
            logging.error("%s.pptx が指定されていません: %s", label, yaml_path)
            return EXIT_BAD_INPUT
        if not pdf_val:
            logging.error("%s.pdf が指定されていません: %s", label, yaml_path)
            return EXIT_BAD_INPUT

        pptx_path = _resolve_cropsrc_path(str(pptx_val), yaml_path, workdir)
        pdf_path = _resolve_cropsrc_path(str(pdf_val), yaml_path, workdir)

        if not pptx_path.exists():
            logging.error("PPTX ファイルが見つかりません: %s", pptx_path)
            return EXIT_NOT_FOUND

        if pdf_path.exists() and not force:
            logging.error("出力 PDF が既に存在します (--force で上書き): %s", pdf_path)
            return EXIT_FAILURE

        resolved.append((pptx_path, pdf_path))

    if dry_run:
        for pptx_path, pdf_path in resolved:
            emit(args, "ok", "pptpdfexport", pptx_path, pdf_path, dry_run=True)
        return EXIT_OK

    try:
        import win32com.client as win32
        import pythoncom
    except ImportError:
        logging.error("win32com が利用できません。Windows + pywin32 が必要です")
        return EXIT_FAILURE

    pythoncom.CoInitialize()
    ppt_app = None
    errors = 0
    try:
        ppt_app = win32.Dispatch("PowerPoint.Application")
        ppt_app.Visible = True

        for pptx_path, pdf_path in resolved:
            prs = None
            opened_by_us = False
            try:
                pdf_path.parent.mkdir(parents=True, exist_ok=True)
                logging.debug("Opening PPTX: %s", pptx_path)
                already_open = _is_already_open(ppt_app, pptx_path)
                prs = ppt_app.Presentations.Open(str(pptx_path), ReadOnly=True, WithWindow=False)
                opened_by_us = not already_open
                logging.debug("Exporting PDF: %s", pdf_path)
                prs.SaveAs(str(pdf_path), _PP_SAVE_AS_PDF)
                logging.debug("PDF export complete")
                emit(args, "ok", "pptpdfexport", pptx_path, pdf_path)
            except Exception as e:
                logging.error("PDF エクスポートに失敗しました: %s: %s", pptx_path, e)
                errors += 1
            finally:
                if prs is not None and opened_by_us and getattr(args, "closepptx", False):
                    try:
                        prs.Close()
                    except Exception:
                        pass

    finally:
        if ppt_app is not None and getattr(args, "ppquit", False):
            try:
                ppt_app.Quit()
            except Exception:
                pass
        pythoncom.CoUninitialize()

    return EXIT_OK if errors == 0 else EXIT_FAILURE


def _resolve_cropsrc_path(val: str, yaml_path: Path, workdir: Path | None) -> Path:
    base = resolve_base(yaml_path, workdir)
    p = Path(val)
    return p if p.is_absolute() else (base / p).resolve()
