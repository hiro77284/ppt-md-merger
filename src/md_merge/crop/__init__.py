from __future__ import annotations

import argparse
import logging
import re
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from md_merge._output import EXIT_BAD_INPUT, EXIT_FAILURE, EXIT_NOT_FOUND, EXIT_OK, emit, setup_logging
from md_merge.merge._recipe import apply_recipe_force, load_yaml, resolve_input_path, resolve_workdir

# ファイル名末尾の RANGE コード: __{LEFT}_{TOP}_{RIGHT}_{BOTTOM} (各0〜100)
_RANGE_PATTERN = re.compile(
    r"__(?P<left>\d{1,3})_(?P<top>\d{1,3})_(?P<right>\d{1,3})_(?P<bottom>\d{1,3})$"
)

_IMAGE_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif", ".gif", ".webp"})


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
    force = getattr(args, "force", False)

    images_dirs = _resolve_imagesdirs(recipe, yaml_path, workdir)

    errors = 0
    all_targets: list[tuple[Path, Path, dict]] = []
    for images_dir in images_dirs:
        if not images_dir.exists():
            logging.error("images directory not found: %s", images_dir)
            errors += 1
            continue
        all_targets.extend(_collect_targets(images_dir))

    if errors:
        return EXIT_FAILURE

    if not all_targets:
        logging.warning("RANGE コード付きの画像ファイルが見つかりません")
        return EXIT_OK

    if args.dry_run:
        for src, dst, _rect in all_targets:
            emit(args, "ok", "crop", src, dst, dry_run=True)
        return EXIT_OK

    for src, dst, rect_pct in all_targets:
        if dst.exists() and not force:
            logging.error("出力ファイルが既に存在します (--force で上書き): %s", dst)
            errors += 1
            continue
        try:
            _crop_image(src, dst, rect_pct)
            emit(args, "ok", "crop", src, dst)
        except (OSError, UnidentifiedImageError) as e:
            logging.error("crop failed: %s: %s", src.name, e)
            errors += 1

    return EXIT_OK if errors == 0 else EXIT_FAILURE


# ── helpers ────────────────────────────────────────────────────────────────


def _resolve_imagesdirs(recipe: dict, yaml_path: Path, workdir: Path | None) -> list[Path]:
    section = recipe.get("input", {})
    base = workdir if workdir else yaml_path.parent
    val = section.get("imagesdir")
    if not val:
        return [base.resolve()]
    entries = val if isinstance(val, list) else [val]
    result = []
    for entry in entries:
        p = Path(entry)
        result.append(p.resolve() if p.is_absolute() else (base / p).resolve())
    return result


def _collect_targets(images_dir: Path) -> list[tuple[Path, Path, dict]]:
    """Return list of (src, dst, rect_pct) for files matching RANGE pattern."""
    targets = []
    for p in sorted(images_dir.iterdir()):
        if not p.is_file() or p.suffix.lower() not in _IMAGE_SUFFIXES:
            continue
        m = _RANGE_PATTERN.search(p.stem)
        if not m:
            continue
        rect_pct = {k: int(v) for k, v in m.groupdict().items()}
        if not _validate_range(rect_pct):
            logging.warning("無効な RANGE 値 (left<right, top<bottom, 0-100) — スキップ: %s", p.name)
            continue
        basename = p.stem[: m.start()]
        dst = p.parent / (basename + p.suffix)
        targets.append((p, dst, rect_pct))
    return targets


def _validate_range(rect_pct: dict) -> bool:
    left, top, right, bottom = rect_pct["left"], rect_pct["top"], rect_pct["right"], rect_pct["bottom"]
    return all(0 <= v <= 100 for v in (left, top, right, bottom)) and left < right and top < bottom


def _crop_image(src: Path, dst: Path, rect_pct: dict) -> None:
    img = Image.open(src)
    with img:
        w, h = img.size
        pixel_rect = (
            round(w * rect_pct["left"]   / 100),
            round(h * rect_pct["top"]    / 100),
            round(w * rect_pct["right"]  / 100),
            round(h * rect_pct["bottom"] / 100),
        )
        cropped = img.crop(pixel_rect)
    dst.parent.mkdir(parents=True, exist_ok=True)
    cropped.save(dst)
