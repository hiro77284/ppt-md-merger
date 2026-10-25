from __future__ import annotations

import argparse
import logging
from pathlib import Path

from md_merge._cropsrc import cropsrc_entries, resolve_cropsrc_path
from md_merge._output import EXIT_BAD_INPUT, EXIT_FAILURE, EXIT_NOT_FOUND, EXIT_OK, emit, setup_logging
from md_merge._preprocess import cropsrc_read_path
from md_merge.merge._recipe import load_yaml, resolve_input_path, resolve_workdir, setup_recipe_file_logging
from md_merge.pptmerge._config import resolve_base

# PowerPoint SaveAs format constant for PDF
_PP_SAVE_AS_PDF = 32


def _find_open_presentation(ppt_app: object, pptx_path: Path) -> object | None:
    """Return the already-open presentation matching pptx_path, or None.

    When a presentation is already open *with a window* (e.g. the user opened it
    manually), reopening it with ReadOnly/WithWindow=False returns that same
    windowed instance, and SaveAs(ppSaveAsPDF) on it silently ignores the target
    directory. Detecting it lets us close and reopen a clean window-less copy.
    """
    target = str(pptx_path).lower()
    try:
        for i in range(1, ppt_app.Presentations.Count + 1):
            try:
                prs = ppt_app.Presentations(i)
                if prs.FullName.lower() == target:
                    return prs
            except Exception:
                pass
    except Exception:
        pass
    return None


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
    entries = cropsrc_entries(recipe)
    output_section = recipe.get("output") or {}
    cli_workdir = Path(args.workdir).resolve() if getattr(args, "workdir", None) else None
    workdir = resolve_workdir(recipe, yaml_path, cli_workdir)
    setup_recipe_file_logging(recipe, yaml_path, workdir)
    # --force / output.force is kept for cross-subcommand consistency but does
    # NOT trigger a rebuild here: the default is incremental (skip when the PDF
    # is newer than the PPTX). Use --rebuild to force regeneration.
    rebuild = getattr(args, "rebuild", False)
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
        pptx_path = resolve_cropsrc_path(str(pptx_val), yaml_path, workdir)
        if logging.getLogger().isEnabledFor(logging.DEBUG):
            base = resolve_base(yaml_path, workdir)
            absolute = Path(str(pptx_val)).is_absolute()
            logging.debug(
                "%s.pptx 探索: 入力値=%r 基準ディレクトリ=%s",
                label, str(pptx_val), "(絶対パスのため基準なし)" if absolute else base,
            )
            logging.debug(
                "%s.pptx 探索パス: %s (%s)",
                label, pptx_path, "存在" if pptx_path.exists() else "未発見",
            )
        if pdf_val:
            pdf_path = resolve_cropsrc_path(str(pdf_val), yaml_path, workdir)
        else:
            pdf_path = _auto_pdf_path(str(pptx_val), output_section, yaml_path, workdir)
            logging.debug("%s.pdf: 自動生成 %s", label, pdf_path)

        # --preprocess: convert the preprocessed copy instead of the original.
        pptx_path = cropsrc_read_path(args, pptx_path)

        if not pptx_path.exists():
            logging.error("PPTX ファイルが見つかりません: %s", pptx_path)
            return EXIT_NOT_FOUND

        # Incremental: skip when the PDF exists and is newer than the PPTX,
        # unless --rebuild forces regeneration.
        if not rebuild and pdf_path.exists() and pdf_path.stat().st_mtime >= pptx_path.stat().st_mtime:
            logging.info("最新のためスキップ (--rebuild で再生成): %s", pdf_path)
            continue

        resolved.append((pptx_path, pdf_path))

    if not resolved:
        logging.info("すべての PDF が最新です。生成対象はありません")
        return EXIT_OK

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
                # A presentation already open with a window makes SaveAs(PDF)
                # ignore the target directory. Close a clean copy and reopen it
                # window-less; warn (without closing) if it has unsaved changes.
                existing = _find_open_presentation(ppt_app, pptx_path)
                if existing is not None:
                    if existing.Saved:
                        logging.warning(
                            "対象 PPTX が PowerPoint で開かれていたため、正しくエクスポートするために一旦閉じます: %s",
                            pptx_path,
                        )
                        try:
                            existing.Close()
                            existing = None
                        except Exception as e:
                            logging.warning("既存プレゼンを閉じられませんでした: %s: %s", pptx_path, e)
                    else:
                        logging.warning(
                            "対象 PPTX が未保存の変更を含む状態で PowerPoint で開かれています。"
                            "PDF が正しい場所に出力されない可能性があります。"
                            "PowerPoint で閉じてから再実行してください: %s",
                            pptx_path,
                        )
                logging.debug("Opening PPTX: %s", pptx_path)
                prs = ppt_app.Presentations.Open(str(pptx_path), ReadOnly=True, WithWindow=False)
                opened_by_us = existing is None
                logging.debug("Exporting PDF: %s", pdf_path)
                prs.SaveAs(str(pdf_path), _PP_SAVE_AS_PDF)
                if not pdf_path.exists():
                    raise RuntimeError(
                        f"エクスポートは完了しましたが出力 PDF が指定先に見つかりません"
                        f"（PowerPoint が別ディレクトリへ書き出した可能性があります）: {pdf_path}"
                    )
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


def _auto_pdf_path(pptx_val: str, output_section: dict, yaml_path: Path, workdir: Path | None) -> Path:
    """Auto-generate PDF path as output.outputdir/<pptx_stem>.pdf."""
    base = resolve_base(yaml_path, workdir)
    outdir_val = output_section.get("outputdir")
    if outdir_val:
        p = Path(str(outdir_val))
        out_dir = p if p.is_absolute() else (base / p).resolve()
    else:
        out_dir = base
    return out_dir / (Path(pptx_val).stem + ".pdf")
