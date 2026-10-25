from __future__ import annotations

import argparse
import logging
import re
import shutil
from pathlib import Path

from md_merge._imagerefs import (
    COLLISION_MODES,
    NAMING_MODES,
    apply_naming,
    pick_destination,
    rewrite,
    should_skip,
)
from md_merge._output import EXIT_BAD_INPUT, EXIT_FAILURE, EXIT_NOT_FOUND, EXIT_OK, emit, setup_logging
from md_merge.merge._recipe import load_yaml, resolve_input_path, resolve_out_file, resolve_workdir, setup_recipe_file_logging

_SLUG_RE = re.compile(r'^[a-z0-9][a-z0-9-]*[a-z0-9]$')

# --source choices -> output.<key> mapping.
_SOURCE_KEYS = {
    "puremd":   "puremdfilename",
    "rendered": "renderedfilename",
    "merged":   "mdfilename",
}


def _rewrite_and_collect(
    content: str, src_md: Path, img_dst_dir: Path, slug: str,
    image_naming: str = "preserve", image_collision: str = "rename",
) -> tuple[str, dict[Path, Path]]:
    """Rewrite local image refs to {slug}/{filename} and return src→dst mapping.

    Which notations count as an image ref (body ``![alt](ref)`` and the frontmatter
    image keys) is defined once in :mod:`md_merge._imagerefs`; this function only
    decides where each ref resolves to.

    ``image_naming`` selects the copied basename (``preserve`` / ``sanitize``) and
    ``image_collision`` how two different sources landing on the same name are
    resolved (``rename`` / ``overwrite``). Both are defined in :mod:`md_merge._imagerefs`.
    """
    registry: dict[Path, Path] = {}

    def register(ref: str) -> str | None:
        """Queue *ref* for copying and return its new ``{slug}/{name}`` ref (None → keep as-is)."""
        if should_skip(ref):
            return None
        img_src = (src_md.parent / ref).resolve()
        if not img_src.exists():
            logging.warning("画像ファイルが見つかりません: %s (参照元: %s)", img_src, src_md)
            return None
        if img_src not in registry:
            target = apply_naming(img_src.name, image_naming)
            if target != img_src.name:
                logging.debug("transfer: 画像名を ASCII 化: %s → %s", img_src.name, target)
            registry[img_src] = pick_destination(
                img_dst_dir / target,
                collision=image_collision,
                taken=set(registry.values()),
            )
        return f"{slug}/{registry[img_src].name}"

    return rewrite(content, lambda r: register(r.ref)), registry


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

    transfer_cfg = recipe.get("transfer") or {}
    output_section = recipe.get("output") or {}
    force = getattr(args, "force", False) or bool(output_section.get("force"))
    dry_run = getattr(args, "dry_run", False)

    # ── slug ──────────────────────────────────────────────────────────────
    slug = str(transfer_cfg.get("slug") or "").strip()
    if not slug:
        logging.error("transfer.slug が指定されていません: %s", yaml_path)
        return EXIT_BAD_INPUT
    if not _SLUG_RE.match(slug):
        logging.error("transfer.slug が不正です (^[a-z0-9][a-z0-9-]*[a-z0-9]$): %s", slug)
        return EXIT_BAD_INPUT

    # ── input MD ──────────────────────────────────────────────────────────
    # Precedence:
    #   1. --source {puremd|rendered|merged}  (CLI override, wins over recipe)
    #   2. transfer.inputmd                   (explicit recipe file name)
    #   3. transfer_source_key                (pipeline default, e.g. ppt_to_transfer)
    #   4. renderedfilename                   (standalone default)
    source_opt = getattr(args, "source", None)
    inputmd_val = str(transfer_cfg.get("inputmd") or "").strip()
    if source_opt:
        src_key = _SOURCE_KEYS[source_opt]
        src_md = resolve_out_file(recipe, src_key, yaml_path, workdir)
        if src_md is None:
            logging.error("--source %s に対応する output.%s が指定されていません: %s", source_opt, src_key, yaml_path)
            return EXIT_BAD_INPUT
    elif inputmd_val:
        base = workdir if workdir else yaml_path.parent
        outdir_val = output_section.get("outputdir")
        if outdir_val:
            p = Path(str(outdir_val))
            out_dir = p if p.is_absolute() else (base / p).resolve()
        else:
            out_dir = base
        try:
            src_md = (out_dir / inputmd_val).resolve()
        except Exception:
            logging.error("transfer.inputmd が不正なファイル名です: %s", inputmd_val)
            return EXIT_BAD_INPUT
    else:
        # Pipelines may redirect the source to another output key (e.g. ppt_to_transfer
        # feeds the puremd-processed MD). Standalone transfer defaults to renderedfilename.
        src_key = getattr(args, "transfer_source_key", None) or "renderedfilename"
        src_md = resolve_out_file(recipe, src_key, yaml_path, workdir)
        if src_md is None:
            logging.error("transfer.inputmd と output.%s のどちらも指定されていません: %s", src_key, yaml_path)
            return EXIT_BAD_INPUT

    if not src_md.exists():
        logging.error("入力 MD ファイルが見つかりません: %s", src_md)
        return EXIT_NOT_FOUND

    # ── dataentry_input ───────────────────────────────────────────────────
    dataentry_val = str(transfer_cfg.get("dataentry_input") or "").strip()
    if not dataentry_val:
        logging.error("transfer.dataentry_input が指定されていません: %s", yaml_path)
        return EXIT_BAD_INPUT
    try:
        p = Path(dataentry_val)
        base = workdir if workdir else yaml_path.parent
        dataentry_dir = p if p.is_absolute() else (base / p).resolve()
    except Exception:
        logging.error("transfer.dataentry_input が不正なパスです: %s", dataentry_val)
        return EXIT_BAD_INPUT

    img_dst_dir = dataentry_dir / slug

    # ── image naming mode ─────────────────────────────────────────────────
    image_naming = str(transfer_cfg.get("image_naming") or "preserve").strip().lower()
    if image_naming not in NAMING_MODES:
        logging.error("transfer.image_naming は %s のいずれかです: %s",
                      " / ".join(NAMING_MODES), image_naming)
        return EXIT_BAD_INPUT
    image_collision = str(transfer_cfg.get("image_collision") or "rename").strip().lower()
    if image_collision not in COLLISION_MODES:
        logging.error("transfer.image_collision は %s のいずれかです: %s",
                      " / ".join(COLLISION_MODES), image_collision)
        return EXIT_BAD_INPUT

    # ── output MD name ────────────────────────────────────────────────────
    # transfer.outputmd で転送先のファイル名を上書きできる（省略時は {slug}.md）。
    # 主な用途は README.md へのリネーム。パス脱出は防ぐ。
    outputmd_val = str(transfer_cfg.get("outputmd") or "").strip()
    out_name = outputmd_val or f"{slug}.md"
    if Path(out_name).is_absolute() or ".." in Path(out_name).parts:
        logging.error("transfer.outputmd はファイル名で指定してください（絶対パス/.. は不可）: %s", out_name)
        return EXIT_BAD_INPUT
    out_md = dataentry_dir / out_name

    logging.debug("src_md        : %s", src_md)
    logging.debug("dataentry_dir : %s", dataentry_dir)
    logging.debug("img_dst_dir   : %s", img_dst_dir)
    logging.debug("out_md        : %s", out_md)
    logging.debug("image_naming  : %s", image_naming)
    logging.debug("image_collision: %s", image_collision)

    # ── read input ────────────────────────────────────────────────────────
    try:
        content = src_md.read_text(encoding="utf-8")
    except Exception as e:
        logging.error("入力 MD ファイルを読み込めません: %s: %s", src_md, e)
        return EXIT_FAILURE

    rewritten, registry = _rewrite_and_collect(
        content, src_md, img_dst_dir, slug, image_naming, image_collision
    )

    if dry_run:
        emit(args, "ok", "transfer", src_md, out_md, dry_run=True)
        return EXIT_OK

    # ── create dirs ───────────────────────────────────────────────────────
    try:
        dataentry_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        logging.error("dataentry_input ディレクトリを作成できません: %s: %s", dataentry_dir, e)
        return EXIT_FAILURE

    if registry:
        try:
            img_dst_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            logging.error("画像出力ディレクトリを作成できません: %s: %s", img_dst_dir, e)
            return EXIT_FAILURE

    # ── write MD ──────────────────────────────────────────────────────────
    if out_md.exists() and not force:
        logging.error("出力 MD が既に存在します (--force で上書き): %s", out_md)
        return EXIT_FAILURE

    try:
        out_md.write_text(rewritten, encoding="utf-8")
    except Exception as e:
        logging.error("MD ファイルを書き込めません: %s: %s", out_md, e)
        return EXIT_FAILURE

    # ── copy images ───────────────────────────────────────────────────────
    errors = 0
    for img_src, img_dst in registry.items():
        try:
            shutil.copy2(img_src, img_dst)
        except Exception as e:
            logging.error("画像ファイルのコピーに失敗しました: %s → %s: %s", img_src, img_dst, e)
            errors += 1

    emit(args, "ok", "transfer", src_md, out_md)
    return EXIT_OK if errors == 0 else EXIT_FAILURE
