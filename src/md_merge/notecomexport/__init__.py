"""notecomexport サブコマンド: puremd 処理済み MD を note.com 投稿用 YAML に変換する。

入力は ``output.puremdfilename``（既定）または ``--source`` / ``notecomexport.inputmd`` で
選んだ MD、出力は ``output.notecomyamlfilename``（既定 ``{base}_notecom.yaml``）。生成した
YAML は tools/notecom_autopilot.py が読み、Playwright で note.com エディタへ入力する。

画像パスは出力 YAML のあるディレクトリからの相対パスに書き換える（入力 MD と出力
YAML が同じ ``output.outputdir`` にある通常構成では元のパスがそのまま残る）。
"""

from __future__ import annotations

import argparse
import logging
import os
import re
from pathlib import Path

from md_merge._imagerefs import should_skip
from md_merge._output import EXIT_BAD_INPUT, EXIT_FAILURE, EXIT_NOT_FOUND, EXIT_OK, emit, setup_logging
from md_merge.merge._recipe import load_yaml, resolve_input_path, resolve_out_file, resolve_workdir, setup_recipe_file_logging
from md_merge.notecomexport._convert import (
    INLINE_MODES,
    QUOTE_LABEL_MODES,
    ParseError,
    convert_markdown,
    dump_note_yaml,
    write_text_lf,
)

# --source choices -> output.<key> mapping（transfer と同じ）
_SOURCE_KEYS = {
    "puremd":   "puremdfilename",
    "rendered": "renderedfilename",
    "merged":   "mdfilename",
}


def _make_image_path_fn(src_md: Path, out_yaml: Path):
    """MD 内の画像参照を、出力 YAML のディレクトリからの相対パスに変換する関数を返す。"""
    md_dir = src_md.parent.resolve()
    yaml_dir = out_yaml.parent.resolve()

    def fn(ref: str, line_no: int) -> str:
        if should_skip(ref) or Path(ref).is_absolute():
            return ref
        abs_path = (md_dir / ref).resolve()
        if not abs_path.exists():
            logging.warning("画像ファイルが見つかりません: %s (参照元: %s:%d)", abs_path, src_md, line_no)
        if md_dir == yaml_dir:
            return ref
        try:
            return os.path.relpath(abs_path, yaml_dir).replace(os.sep, "/")
        except ValueError:  # 別ドライブ
            return str(abs_path)

    return fn


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

    cfg = recipe.get("notecomexport") or {}
    output_section = recipe.get("output") or {}
    force = getattr(args, "force", False) or bool(output_section.get("force"))
    dry_run = getattr(args, "dry_run", False)

    # ── options ──────────────────────────────────────────────────────────
    inline = str(cfg.get("inline") or "plain").strip().lower()
    if inline not in INLINE_MODES:
        logging.error("notecomexport.inline は %s のいずれかです: %s", " / ".join(INLINE_MODES), inline)
        return EXIT_BAD_INPUT
    quote_labels = str(cfg.get("quote_labels") or "drop").strip().lower()
    if quote_labels not in QUOTE_LABEL_MODES:
        logging.error("notecomexport.quote_labels は %s のいずれかです: %s", " / ".join(QUOTE_LABEL_MODES), quote_labels)
        return EXIT_BAD_INPUT
    hashtags = cfg.get("hashtags")
    if hashtags is not None and not isinstance(hashtags, list):
        logging.error("notecomexport.hashtags はリストで指定してください: %r", hashtags)
        return EXIT_BAD_INPUT
    cover = cfg.get("cover")
    link_base = str(cfg.get("link_base") or "").strip() or None
    if link_base and not re.match(r"^https?://", link_base):
        logging.error("notecomexport.link_base は http(s):// で始まる URL で指定してください: %s", link_base)
        return EXIT_BAD_INPUT

    # ── input MD ─────────────────────────────────────────────────────────
    # 優先順位: --source > notecomexport.inputmd > output.puremdfilename
    source_opt = getattr(args, "source", None)
    inputmd_val = str(cfg.get("inputmd") or "").strip()
    if source_opt:
        src_key = _SOURCE_KEYS[source_opt]
        src_md = resolve_out_file(recipe, src_key, yaml_path, workdir)
        if src_md is None:
            logging.error("--source %s に対応する output.%s が指定されていません: %s", source_opt, src_key, yaml_path)
            return EXIT_BAD_INPUT
    elif inputmd_val:
        base = workdir if workdir else yaml_path.parent
        outdir_val = output_section.get("outputdir")
        out_dir = (Path(outdir_val) if Path(outdir_val).is_absolute() else (base / outdir_val).resolve()) if outdir_val else base
        src_md = (out_dir / inputmd_val).resolve()
    else:
        src_md = resolve_out_file(recipe, "puremdfilename", yaml_path, workdir)
        if src_md is None:
            logging.error("notecomexport.inputmd と output.puremdfilename のどちらも指定されていません: %s", yaml_path)
            return EXIT_BAD_INPUT
    if not src_md.exists():
        logging.error("入力 MD ファイルが見つかりません: %s", src_md)
        return EXIT_NOT_FOUND

    # ── output YAML ──────────────────────────────────────────────────────
    out_yaml = resolve_out_file(recipe, "notecomyamlfilename", yaml_path, workdir)
    if out_yaml is None:
        logging.error("output.notecomyamlfilename も output.targetbasefilename も指定されていません: %s", yaml_path)
        return EXIT_BAD_INPUT

    logging.debug("src_md   : %s", src_md)
    logging.debug("out_yaml : %s", out_yaml)
    logging.debug("inline=%s quote_labels=%s hashtags=%s cover=%s link_base=%s",
                  inline, quote_labels, hashtags, cover, link_base)

    try:
        text = src_md.read_text(encoding="utf-8-sig")
    except Exception as e:
        logging.error("入力 MD ファイルを読み込めません: %s: %s", src_md, e)
        return EXIT_FAILURE

    try:
        note = convert_markdown(
            text,
            source_name=str(src_md),
            inline=inline,
            quote_labels=quote_labels,
            hashtags=hashtags,
            cover=cover,
            image_path_fn=_make_image_path_fn(src_md, out_yaml),
            link_base=link_base,
        )
    except ParseError as e:
        logging.error("MD の解析に失敗しました: %s", e)
        return EXIT_BAD_INPUT

    n_img = sum(1 for b in note["blocks"] if b["type"] == "image")
    n_link = sum(len([r for r in b.get("runs", []) if "url" in r]) + (1 if b.get("link") else 0) for b in note["blocks"])
    n_link += sum(len([r for it in b.get("items", []) + b.get("lines", []) if isinstance(it, dict)
                       for r in it.get("runs", []) if "url" in r]) for b in note["blocks"])
    logging.info("notecomexport: title=%r blocks=%d images=%d links=%d hashtags=%s",
                 note["meta"].get("title"), len(note["blocks"]), n_img, n_link, note["meta"].get("hashtags"))

    if dry_run:
        emit(args, "ok", "notecomexport", src_md, out_yaml, dry_run=True)
        return EXIT_OK

    if out_yaml.exists() and not force:
        logging.error("出力 YAML が既に存在します (--force で上書き): %s", out_yaml)
        return EXIT_FAILURE
    try:
        out_yaml.parent.mkdir(parents=True, exist_ok=True)
        write_text_lf(out_yaml, dump_note_yaml(note))
    except Exception as e:
        logging.error("YAML ファイルを書き込めません: %s: %s", out_yaml, e)
        return EXIT_FAILURE

    emit(args, "ok", "notecomexport", src_md, out_yaml)
    return EXIT_OK
