from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from io import BytesIO
from pathlib import Path

import fitz  # pymupdf
from PIL import Image
from pptx import Presentation

from md_merge._filters import replace_slide_placeholders
from md_merge._note_parser import parse_note_image_directives
from md_merge._cropsrc import cropsrc_entries, resolve_cropsrc_path
from md_merge._output import EXIT_BAD_INPUT, EXIT_FAILURE, EXIT_NOT_FOUND, EXIT_OK, emit, setup_logging
from md_merge._preprocess import cropsrc_read_path
from md_merge._shapes import find_shape, not_found_reason
from md_merge.merge._recipe import load_yaml, resolve_input_path, resolve_workdir, setup_recipe_file_logging
from md_merge.pptmerge._config import resolve_base

_DEFAULT_DPI = 150
_MODE_SLIDE = "slide"
_MODE_NAMED_SHAPE = "named_shape"
_MODE_SLIDE_WITH_RECTPCT = "slide_with_rectpct"
_KNOWN_MODES = {_MODE_SLIDE, _MODE_NAMED_SHAPE, _MODE_SLIDE_WITH_RECTPCT}
_STEP_PLACEHOLDER = "<__STEP__>"
_STEP_ALL = "all"
_STEP_LAST = "last"
_STEP_ITEM_RE = re.compile(r"^(\d+)(?:\s*-\s*(\d+))?$")


def _to_ltrb_float(
    shape_left: int, shape_top: int, shape_width: int, shape_height: int,
    slide_width: int, slide_height: int,
) -> tuple[float, float, float, float]:
    l = shape_left / slide_width * 100
    t = shape_top / slide_height * 100
    r = (shape_left + shape_width) / slide_width * 100
    b = (shape_top + shape_height) / slide_height * 100
    return l, t, r, b



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


def _crop_pdf_page(
    pdf_doc: fitz.Document,
    page_idx: int,
    l: float, t: float, r: float, b: float,
    dpi: int,
    inset_px: int = 0,
) -> Image.Image:
    page = pdf_doc[page_idx]
    scale = dpi / 72
    pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale))
    img = Image.open(BytesIO(pix.tobytes("png")))
    return _crop_image(img, l, t, r, b, inset_px)


def _crop_image(img: Image.Image, l: float, t: float, r: float, b: float, inset_px: int = 0) -> Image.Image:
    """スライド全体の画像 *img* を % 座標 (l, t, r, b) で切り出す。"""
    w, h = img.size
    # 出力ピクセル基準の box。inset_px>0 で外側へ拡大、<0 で内側へ縮小。画像範囲にクランプ。
    x0 = round(w * l / 100) - inset_px
    y0 = round(h * t / 100) - inset_px
    x1 = round(w * r / 100) + inset_px
    y1 = round(h * b / 100) + inset_px
    x0 = max(0, min(x0, w))
    y0 = max(0, min(y0, h))
    x1 = max(0, min(x1, w))
    y1 = max(0, min(y1, h))
    if x1 <= x0:
        x1 = min(w, x0 + 1)
    if y1 <= y0:
        y1 = min(h, y0 + 1)
    return img.crop((x0, y0, x1, y1))


def _slide_pixel_size(slide_width: int, slide_height: int, dpi: int) -> tuple[int, int]:
    """スライド全体を *dpi* でラスタライズしたときのピクセル寸法（PDF 経路と同じ丸め）。

    キャプチャ経路はスライド領域をこの寸法へリサンプルするので、同じ切り出し指定から
    PDF 経路と同じピクセル寸法の画像ができる。
    """
    scale = dpi / 72
    rect = fitz.Rect(0, 0, slide_width / 12700, slide_height / 12700) * fitz.Matrix(scale, scale)
    irect = rect.irect
    return irect.width, irect.height


def _parse_step_spec(raw: str) -> list[int] | str | None:
    """``export-image-step`` の値を解釈する。

    戻り値: 空なら None（PDF 経路）、``all`` / ``last`` はその文字列、それ以外は昇順・重複なしの
    ステップ番号リスト（``0-3, 5`` 形式）。書式が不正なら ValueError。
    """
    raw = raw.strip()
    if not raw:
        return None
    if raw.lower() in (_STEP_ALL, _STEP_LAST):
        return raw.lower()
    steps: set[int] = set()
    for item in raw.split(","):
        m = _STEP_ITEM_RE.match(item.strip())
        if not m:
            raise ValueError(f"ステップ指定を解釈できません: {item.strip()!r}")
        lo = int(m.group(1))
        hi = int(m.group(2)) if m.group(2) is not None else lo
        if hi < lo:
            raise ValueError(f"範囲の向きが逆です: {item.strip()!r}")
        steps.update(range(lo, hi + 1))
    return sorted(steps)


def _is_multi_step(spec: list[int] | str) -> bool:
    return spec == _STEP_ALL or (isinstance(spec, list) and len(spec) > 1)


def _step_output(out_template: Path, step: int) -> Path:
    return Path(str(out_template).replace(_STEP_PLACEHOLDER, str(step)))


def _fmt_step(spec) -> str:
    if spec is None:
        return "-"
    if isinstance(spec, list):
        return ",".join(str(s) for s in spec)
    return spec


def _fmt_pct(v: float) -> str:
    return f"{v:.2f}" if v != int(v) else str(int(v))


def _is_hidden_slide(slide) -> bool:
    """スライドが非表示（hidden）設定かを判定する。

    p:sld 要素の ``show`` 属性が明示的に偽（``0`` / ``false``）のとき非表示。
    属性が無ければ表示（既定 True）扱い。
    """
    show = slide._element.get("show")
    return show is not None and str(show).lower() in ("0", "false")


def _detect_hidden_slides(prs) -> list[int]:
    """1始まりの非表示スライド番号を返す。"""
    return [i for i, slide in enumerate(prs.slides, start=1) if _is_hidden_slide(slide)]


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
    recipe_force = bool(output_section.get("force"))
    force = getattr(args, "force", False) or recipe_force
    dry_run = getattr(args, "dry_run", False)
    json_mode = getattr(args, "json", False)

    if not entries:
        logging.error("input.cropsrc が指定されていません: %s", yaml_path)
        return EXIT_BAD_INPUT

    # ── 全エントリのパス解決と存在確認（fail fast）────────────────────────
    resolved: list[tuple[Path, Path, int]] = []
    for i, entry in enumerate(entries):
        label = f"input.cropsrc[{i}]" if len(entries) > 1 else "input.cropsrc"
        pptx_val = entry.get("pptx")
        pdf_val = entry.get("pdf")
        dpi = int(entry.get("dpi", _DEFAULT_DPI))

        if not pptx_val:
            logging.error("%s.pptx が指定されていません: %s", label, yaml_path)
            return EXIT_BAD_INPUT
        pptx_path = resolve_cropsrc_path(str(pptx_val), yaml_path, workdir)
        if pdf_val:
            pdf_path = resolve_cropsrc_path(str(pdf_val), yaml_path, workdir)
        else:
            pdf_path = _auto_pdf_path(str(pptx_val), output_section, yaml_path, workdir)
            logging.debug("%s.pdf: 自動生成 %s", label, pdf_path)

        if not pptx_path.exists():
            logging.error("PPTX ファイルが見つかりません: %s", pptx_path)
            return EXIT_NOT_FOUND
        if not pdf_path.exists():
            logging.error("PDF ファイルが見つかりません: %s", pdf_path)
            return EXIT_NOT_FOUND

        resolved.append((pptx_path, pdf_path, dpi))

    # ── エントリごとに処理 ────────────────────────────────────────────────
    errors = 0
    failures: list[str] = []  # 失敗タスクの理由（末尾サマリ用）
    json_entries: list[dict] = []

    for pptx_path, pdf_path, dpi in resolved:
        # PPTX 読み込み・タスク収集。--preprocess 時は前処理済み pptx から読む
        # （出力パス・PDF 名・プレースホルダーは元の pptx_path のまま）。
        read_pptx_path = cropsrc_read_path(args, pptx_path)
        try:
            prs = Presentation(str(read_pptx_path))
        except Exception as e:
            logging.error("PPTX ファイルを開けません: %s: %s", read_pptx_path, e)
            errors += 1
            failures.append(f"PPTX を開けない: {read_pptx_path}: {e}")
            continue

        sw = prs.slide_width
        sh = prs.slide_height

        # 非表示スライドは pptpdfexport（PowerPoint）の PDF に出力されず、PDF の
        # ページ数が pptx のスライド数とズレる。pptimgexport は「pptx スライド番号
        # ＝PDF ページ番号」を前提にクロップするため、途中に非表示スライドがあると
        # それ以降が誤ったページを参照する。検出して警告する（番号の自動補正はしない）。
        hidden_slides = _detect_hidden_slides(prs)
        if hidden_slides:
            logging.warning(
                "非表示スライドを検出しました: %s（%s）。"
                "非表示スライドは PDF に出力されず PDF のページ数がズレるため、"
                "以降のスライドの画像切り出しが誤ったページを参照する可能性があります。",
                ", ".join(str(i) for i in hidden_slides), pptx_path.name,
            )

        tasks: list[dict] = []
        for slide_idx, slide in enumerate(prs.slides, start=1):
            note_text = ""
            if slide.has_notes_slide:
                tf = slide.notes_slide.notes_text_frame
                note_text = (tf.text or "") if tf else ""

            title_shape = slide.shapes.title
            slide_title = title_shape.text if title_shape is not None else ""
            note_text = replace_slide_placeholders(note_text, pptx_path, slide_title, slide_idx)

            image_directives = parse_note_image_directives(note_text)
            for meta in image_directives:
                mode = meta.get("export-image-mode", "").strip()
                if mode not in _KNOWN_MODES:
                    if mode:
                        # 値はあるが不正（typo 等）
                        logging.warning(
                            "スライド %d: export-image-mode の値が不正です: %r（有効値: %s）",
                            slide_idx, mode, ", ".join(sorted(_KNOWN_MODES)),
                        )
                    elif (meta.get("export-image") or "").strip() or (meta.get("export-image-target") or "").strip():
                        # mode 未指定だが他の export-image-* に値がある＝書きかけの不備
                        logging.warning(
                            "スライド %d: export-image-mode が未指定です（他の export-image-* は指定あり。有効値: %s）",
                            slide_idx, ", ".join(sorted(_KNOWN_MODES)),
                        )
                    # 全項目が空の IMAGE ブロックはプレースホルダとみなし黙ってスキップ
                    continue

                target = meta.get("export-image-target", "").strip()
                export_val = meta.get("export-image", "").strip()

                # 出力 px 単位のインセット。正でクロップ枠を外側へ拡大（枠線を確実に
                # 含めたいとき）、負で内側へ縮小。既定 0。
                inset_raw = (meta.get("export-image-inset") or "").strip()
                try:
                    inset_px = int(inset_raw) if inset_raw else 0
                except ValueError:
                    logging.warning(
                        "スライド %d: export-image-inset が整数ではありません: %r — 0 を使用",
                        slide_idx, inset_raw,
                    )
                    inset_px = 0

                if not export_val:
                    logging.warning("スライド %d: export-image が未指定です", slide_idx)
                    continue

                # export-image-step があればキャプチャ経路（アニメーションの途中状態）。
                # 書き間違いは画像が黙って欠けるので警告ではなく失敗にする。
                try:
                    step_spec = _parse_step_spec(meta.get("export-image-step") or "")
                except ValueError as e:
                    logging.error("スライド %d: export-image-step が不正です: %s", slide_idx, e)
                    errors += 1
                    failures.append(f"slide {slide_idx}: export-image-step が不正: {e}")
                    continue
                if step_spec is not None and _is_multi_step(step_spec) and _STEP_PLACEHOLDER not in export_val:
                    logging.error(
                        "スライド %d: 複数ステップ（%s）を指定していますが export-image に %s がありません"
                        "（全ステップが同じファイルに上書きされます）: %s",
                        slide_idx, _fmt_step(step_spec), _STEP_PLACEHOLDER, export_val,
                    )
                    errors += 1
                    failures.append(f"slide {slide_idx}: 複数ステップ指定で export-image に {_STEP_PLACEHOLDER} が無い")
                    continue

                if mode == _MODE_SLIDE:
                    l: float = 0.0
                    t: float = 0.0
                    r: float = 100.0
                    b: float = 100.0
                    shape_label = _MODE_SLIDE
                elif mode == _MODE_NAMED_SHAPE:
                    if not target:
                        logging.warning("スライド %d: export-image-target が未指定です（mode: named_shape）", slide_idx)
                        continue
                    found, in_group = find_shape(slide, target)
                    if found is None:
                        logging.warning("スライド %d: %s", slide_idx, not_found_reason(target, in_group))
                        continue
                    l, t, r, b = _to_ltrb_float(found.left, found.top, found.width, found.height, sw, sh)
                    shape_label = target
                else:  # slide_with_rectpct
                    if not target:
                        logging.warning("スライド %d: export-image-target が未指定です（mode: slide_with_rectpct）", slide_idx)
                        continue
                    found, in_group = find_shape(slide, target)
                    if found is None:
                        logging.warning("スライド %d: %s", slide_idx, not_found_reason(target, in_group))
                        continue
                    # 整数%への丸めはせず、実エッジに正確に追従する（枠線のちらつき回避）。
                    l, t, r, b = _to_ltrb_float(found.left, found.top, found.width, found.height, sw, sh)
                    shape_label = target

                export_path = Path(export_val)
                out_path = export_path if export_path.is_absolute() else (pptx_path.parent / export_path).resolve()

                tasks.append({
                    "slide": slide_idx,
                    "mode": mode,
                    "shape_label": shape_label,
                    "L": l, "T": t, "R": r, "B": b,
                    "inset": inset_px,
                    "step": step_spec,
                    "output": out_path,
                })

        if not tasks:
            if not json_mode:
                print(f"対象スライドが見つかりません: {pptx_path}")
            json_entries.append({"pptx": str(pptx_path), "pdf": str(pdf_path), "tasks": [], "crops": []})
            continue

        # 座標一覧表示
        if not json_mode:
            print(f"対象スライド ({len(tasks)} 件): {pptx_path}")
            print(f"{'スライド':>6}  {'モード':<20}  {'シェイプ':<18}  {'L':>7}  {'T':>7}  {'R':>7}  {'B':>7}  {'ステップ':<8}  出力先")
            print("-" * 120)
            for task in tasks:
                print(
                    f"{task['slide']:>6}  {task['mode']:<20}  {task['shape_label']:<18}  "
                    f"{_fmt_pct(task['L']):>7}  {_fmt_pct(task['T']):>7}  "
                    f"{_fmt_pct(task['R']):>7}  {_fmt_pct(task['B']):>7}  "
                    f"{_fmt_step(task['step']):<8}  {task['output']}"
                )

        # export-image-step 付きはスライドショーのキャプチャ、それ以外は PDF から切り出す
        pdf_tasks = [t for t in tasks if t["step"] is None]
        step_tasks = [t for t in tasks if t["step"] is not None]
        crop_results: list[dict] = []

        if step_tasks:
            step_errors, step_failures = _run_step_tasks(
                args, pptx_path, read_pptx_path, step_tasks,
                _slide_pixel_size(sw, sh, dpi), force, dry_run, crop_results,
            )
            errors += step_errors
            failures.extend(step_failures)

        if not pdf_tasks:
            json_entries.append({
                "pptx": str(pptx_path),
                "pdf": str(pdf_path),
                "tasks": [_task_to_json(t) for t in tasks],
                "crops": crop_results,
            })
            continue

        # PDF クロップ
        try:
            pdf_doc = fitz.open(str(pdf_path))
        except Exception as e:
            logging.error("PDF ファイルを開けません: %s: %s", pdf_path, e)
            errors += 1
            failures.append(f"PDF を開けない: {pdf_path}: {e}")
            continue

        pdf_page_count = len(pdf_doc)

        for task in pdf_tasks:
            slide_n = task["slide"]
            page_idx = slide_n - 1
            out_path: Path = task["output"]

            if page_idx >= pdf_page_count:
                logging.warning(
                    "PDF にページ %d が存在しません（PDF は %d ページ）: %s",
                    slide_n, pdf_page_count, pdf_path,
                )
                errors += 1
                failures.append(
                    f"slide {slide_n}: PDF にページ {slide_n} が無い（PDF は {pdf_page_count} ページ）: {pdf_path}"
                )
                continue

            if out_path.exists() and not force:
                logging.error("出力ファイルが既に存在します (--force で上書き): %s", out_path)
                errors += 1
                failures.append(f"slide {slide_n}: 出力が既存で --force なし: {out_path}")
                continue

            if dry_run:
                emit(args, "ok", "pptimgexport", pdf_path, out_path, dry_run=True)
                crop_results.append({"slide": slide_n, "output": str(out_path)})
                continue

            try:
                out_path.parent.mkdir(parents=True, exist_ok=True)
                cropped = _crop_pdf_page(
                    pdf_doc, page_idx, task["L"], task["T"], task["R"], task["B"], dpi,
                    task.get("inset", 0),
                )
                cropped.save(str(out_path))
                emit(args, "ok", "pptimgexport", pdf_path, out_path)
                crop_results.append({"slide": slide_n, "output": str(out_path)})
            except Exception as e:
                logging.error("crop 失敗: slide %d: %s", slide_n, e)
                errors += 1
                failures.append(f"slide {slide_n}: crop 失敗: {out_path}: {e}")

        if getattr(args, "closepptx", False):
            pdf_doc.close()

        json_entries.append({
            "pptx": str(pptx_path),
            "pdf": str(pdf_path),
            "tasks": [_task_to_json(t) for t in tasks],
            "crops": crop_results,
        })

    if json_mode:
        print(json.dumps({
            "status": "ok" if errors == 0 else "error",
            "command": "pptimgexport",
            "entries": json_entries,
            "failures": failures,
        }, ensure_ascii=False, indent=2))
    elif failures:
        # どのタスクが何で失敗したかを末尾に必ず明示する。個々の失敗は上に出て
        # いても、成功した OK 行に埋もれて見落とされやすいため（パイプラインでは
        # 特に）、終了直前にまとめて再掲する。
        logging.error("pptimgexport: %d 件のタスクが失敗しました:", len(failures))
        for reason in failures:
            logging.error("  - %s", reason)

    return EXIT_OK if errors == 0 else EXIT_FAILURE


def _run_step_tasks(
    args: argparse.Namespace,
    pptx_path: Path,
    read_pptx_path: Path,
    tasks: list[dict],
    target_size: tuple[int, int],
    force: bool,
    dry_run: bool,
    crop_results: list[dict],
) -> tuple[int, list[str]]:
    """``export-image-step`` 付きタスクをスライドショーのキャプチャで処理する。

    pptx 1 つにつきスライドショーを 1 回だけ起動する。戻り値は (失敗数, 失敗理由)。
    出力パスとプレースホルダーは元の *pptx_path* 基準、開くのは *read_pptx_path*
    （--preprocess 時は前処理済み pptx）。
    """
    errors = 0
    failures: list[str] = []

    def fail(slide_n: int, msg: str) -> None:
        nonlocal errors
        logging.error("slide %d: %s", slide_n, msg)
        errors += 1
        failures.append(f"slide {slide_n}: {msg}")

    if dry_run:
        # PowerPoint を起動しないのでステップ数は分からない。all / last は展開しない
        for task in tasks:
            spec = task["step"]
            outs = [_step_output(task["output"], s) for s in spec] if isinstance(spec, list) else [task["output"]]
            for out in outs:
                emit(args, "ok", "pptimgexport", pptx_path, out, dry_run=True)
                crop_results.append({"slide": task["slide"], "step": spec, "output": str(out)})
        return errors, failures

    if sys.platform != "win32":
        for task in tasks:
            fail(task["slide"], "export-image-step（アニメーションのステップ切り出し）は Windows 専用です")
        return errors, failures

    try:
        from md_merge.pptimgexport._capture import SlideShowSession, StepCaptureError
    except ImportError as e:
        for task in tasks:
            fail(task["slide"], f"キャプチャに必要なモジュールがありません（pywin32）: {e}")
        return errors, failures

    try:
        with SlideShowSession(read_pptx_path, target_size) as show:
            click_counts: dict[int, int] = {}
            for task in tasks:
                slide_n = task["slide"]
                try:
                    if slide_n not in click_counts:
                        click_counts[slide_n] = show.click_count(slide_n)
                        logging.debug("slide %d: GetClickCount() = %d", slide_n, click_counts[slide_n])
                    clicks = click_counts[slide_n]
                except StepCaptureError as e:
                    fail(slide_n, str(e))
                    continue

                spec = task["step"]
                if spec == _STEP_ALL:
                    steps = list(range(clicks + 1))
                elif spec == _STEP_LAST:
                    steps = [clicks]
                else:
                    over = [s for s in spec if s > clicks]
                    if over:
                        fail(slide_n, f"ステップ {','.join(map(str, over))} はありません（このスライドは {clicks} ステップ）")
                    steps = [s for s in spec if s <= clicks]

                for step in steps:
                    out_path = _step_output(task["output"], step)
                    if out_path.exists() and not force:
                        fail(slide_n, f"出力ファイルが既に存在します (--force で上書き): {out_path}")
                        continue
                    try:
                        slide_img = show.capture(slide_n, step)
                        cropped = _crop_image(
                            slide_img, task["L"], task["T"], task["R"], task["B"], task.get("inset", 0),
                        )
                        out_path.parent.mkdir(parents=True, exist_ok=True)
                        cropped.save(str(out_path))
                        emit(args, "ok", "pptimgexport", pptx_path, out_path)
                        crop_results.append({"slide": slide_n, "step": step, "output": str(out_path)})
                    except Exception as e:
                        fail(slide_n, f"step {step} のキャプチャに失敗: {out_path}: {e}")
    except Exception as e:
        logging.error("スライドショーのキャプチャを開始できません: %s: %s", read_pptx_path, e)
        for task in tasks:
            errors += 1
            failures.append(f"slide {task['slide']}: スライドショーのキャプチャを開始できない: {e}")

    return errors, failures


def _task_to_json(task: dict) -> dict:
    return {**{k: v for k, v in task.items() if k != "output"}, "output": str(task["output"])}
