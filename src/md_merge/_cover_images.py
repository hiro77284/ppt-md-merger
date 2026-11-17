"""表紙 Markdown（pandoc.cover-md）の画像参照をコピー・書き換える。

表紙 MD は merge を通らず pandoc 段で ``{{v:NAME}}`` を置換するため、``COVER_IMAGE`` などで
指定した画像は merge の画像コピーの対象にならない。そこで pandoc 段で、変数置換後の表紙 MD の
画像参照を insertvar と同じ規則（レシピのディレクトリ基準）で解決し、``merge.copy-images``
が有効なら ``merge.image-dir`` にコピーして参照を書き換える。

- 探す順: レシピのディレクトリ → workdir → 表紙 MD のディレクトリ。
- どこにも無ければ参照は変えない（従来どおり pandoc の resource-path から探す）。
- 表紙画像は常にフラット（image-dir 直下）に置く。命名（image-naming）と同名衝突の方針
  （image-collision）は merge と同じ。衝突は「本文（render 済み MD）が参照する image-dir 内の
  別内容のファイルと同じコピー先になること」を指す。前回実行で置いた同名ファイルは上書きする。
"""

from __future__ import annotations

import filecmp
import logging
import os
import shutil
from pathlib import Path

from md_merge._imagerefs import Ref, apply_naming, pick_destination, rewrite, should_skip
from md_merge.merge._copy_keys import resolve_no_copy
from md_merge.merge._images import DEFAULT_IMAGE_DIR


def cover_image_settings(merge_section: dict | None) -> tuple[bool, str, str, str]:
    """merge セクションから (copy, image-dir, naming, collision) を得る（merge と同じ既定）。"""
    mc = merge_section or {}
    try:
        copy = not resolve_no_copy(mc, "copy-images", "no-copy-images")
    except ValueError:
        copy = False  # 矛盾は merge / validate がエラーにする。ここではコピーしない
    val = mc.get("image-dir", None)
    image_dir = DEFAULT_IMAGE_DIR if val is None else str(val)
    naming = str(mc.get("image-naming") or "preserve").strip().lower()
    legacy = bool(mc.get("overwrite-images", False))
    collision = str(mc.get("image-collision") or ("overwrite" if legacy else "rename")).strip().lower()
    return copy, image_dir, naming, collision


def body_image_targets(rendered_md: Path, img_dir: Path) -> set[Path]:
    """render 済み MD が参照する画像のうち image-dir 内にあるもの（実パス）を返す。"""
    taken: set[Path] = set()
    try:
        text = rendered_md.read_text(encoding="utf-8")
    except OSError:
        return taken
    img_dir = img_dir.resolve()

    def record(ref: Ref) -> None:
        if not should_skip(ref.ref):
            p = (rendered_md.parent / ref.ref).resolve()
            if img_dir in p.parents:
                taken.add(p)
        return None

    rewrite(text, record)
    return taken


def copy_cover_images(
    content: str,
    *,
    bases: list[Path],
    img_dir: Path,
    ref_base: Path,
    naming: str = "preserve",
    collision: str = "rename",
    taken: set[Path] | None = None,
) -> str:
    """表紙 MD *content* の画像参照を解決・コピーし、*ref_base* からの相対参照に書き換える。"""
    img_dir = img_dir.resolve()
    ref_base = ref_base.resolve()
    taken = set() if taken is None else set(taken)
    copied: dict[Path, Path] = {}

    def resolve(ref: Ref) -> str | None:
        if ref.kind != "body" or should_skip(ref.ref):
            return None
        src = None
        for base in bases:
            cand = (base / ref.ref).resolve()
            if cand.is_file():
                src = cand
                break
        if src is None:
            logging.debug("表紙の画像をレシピ基準で見つけられません（resource-path から探します）: %s", ref.ref)
            return None
        if src in copied:
            dst = copied[src]
        elif img_dir in src.parents:
            dst = src  # 既に image-dir 内にある画像はその場で参照する
        else:
            dst = img_dir / apply_naming(src.name, naming)
            if dst in taken and dst.exists() and not filecmp.cmp(src, dst, shallow=False):
                dst = pick_destination(dst, collision=collision, taken=taken)
            dst.parent.mkdir(parents=True, exist_ok=True)
            if not (dst.exists() and filecmp.cmp(src, dst, shallow=False)):
                shutil.copy2(src, dst)
            logging.debug("表紙の画像をコピー: %s -> %s", src, dst)
        copied[src] = dst
        taken.add(dst)
        return Path(os.path.relpath(dst, ref_base)).as_posix()

    return rewrite(content, resolve)
