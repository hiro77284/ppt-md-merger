import logging
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from md_merge._imagerefs import (
    Ref,
    apply_naming,
    pick_destination,
    rewrite_line,
    rewrite_yaml_links,
    should_skip,
)

# image-dir 未指定時の既定サブディレクトリ名。結合済み MD と画像を同階層の 1 段構成に
# 保つための規約（docs/design_image_refs.md §4.2）。レシピで空文字を明示すると
# outputdir 直下に置く（旧挙動）。
DEFAULT_IMAGE_DIR = "images"


@dataclass
class ImageCopier:
    """Copies local images to the output image directory and rewrites their refs.

    Keeps a registry of already-copied files so the same source image is
    not copied twice even when referenced from multiple places.
    """

    out_md: Path          # destination merged MD (images go next to it)
    dir_name: str         # name of the image subdirectory
    flatten: bool         # True → flat dir; False → preserve relative structure
    in_dir: Path | None   # base for structure-preserving mode (input.mddir)
    naming: str           # "preserve" (keep the source name) | "sanitize" (ASCII slug)
    collision: str        # "rename" (add _1/_2) | "overwrite" (warn and clobber)
    _registry: dict[Path, Path] = field(default_factory=dict, init=False)

    @property
    def img_dir(self) -> Path:
        # 正規化しておく。outputdir が ``../build`` のように ``..`` を含み、image-dir も
        # ``../build/images`` のときに、参照が ``../build/images/x.png`` という遠回りの
        # 相対パスになると typst が --root の外に出るとみなしてエラーにするため。
        return (self.out_md.parent / self.dir_name).resolve()

    def rewrite_line(self, line: str, source_md: Path, *, in_frontmatter: bool) -> str:
        """Rewrite the local image refs in *line*, copying the files.

        Body refs and frontmatter image keys resolve by the same rule; only which
        notation is scanned differs (decided by ``_imagerefs``).
        """
        return rewrite_line(
            line,
            in_frontmatter=in_frontmatter,
            resolve=lambda r: self._resolve(r, source_md),
        )

    # ── internals ────────────────────────────────────────

    # 見つからないときの警告に出す種別名（サブクラスで差し替える）
    _label = "画像"

    def _resolve(self, ref: Ref, source_md: Path) -> str | None:
        """Copy the referenced image and return its ref relative to the merged MD."""
        if should_skip(ref.ref):
            return None
        img_src = (source_md.parent / ref.ref).resolve()
        if not img_src.exists():
            logging.warning("%sファイルが見つかりません: %s (参照元: %s)", self._label, img_src, source_md)
            return None
        img_dst = self._copy(img_src)
        return Path(os.path.relpath(img_dst, self.out_md.parent.resolve())).as_posix()

    def _copy(self, src: Path) -> Path:
        if src in self._registry:
            return self._registry[src]
        if self.img_dir.resolve() in src.parents:
            # 既に image-dir 内にある画像（pptimgexport の書き出し先が image-dir と
            # 同じ構成など）はコピーせずその場で参照する。自分自身へのコピーや
            # image-dir/images/... の入れ子を作らないため。
            self._registry[src] = src
            return src
        dst = self._dst_path(src)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        self._registry[src] = dst
        return dst

    def _dst_path(self, src: Path) -> Path:
        """Pick the copy destination: image-dir ＋ naming 変換、衝突は collision 方針で。"""
        if self.flatten or self.in_dir is None:
            rel = Path(src.name)
        else:
            try:
                rel = src.relative_to(self.in_dir)
            except ValueError:
                rel = Path(src.name)
        candidate = self.img_dir / rel.with_name(apply_naming(rel.name, self.naming))
        return pick_destination(
            candidate, collision=self.collision, taken=set(self._registry.values())
        )


@dataclass
class YamlCopier(ImageCopier):
    """Copies YAML files linked from the body (``[text](x.yaml)``) and rewrites the links.

    コピー先・命名・衝突回避・既に yaml-dir 内にあるファイルの扱いは ImageCopier と同じ。
    設定は merge.yaml-dir / flatten-yamls / overwrite-yamls / no-copy-yamls で画像と独立。
    """

    _label = "YAML "

    def rewrite_line(self, line: str, source_md: Path, *, in_frontmatter: bool) -> str:
        return rewrite_yaml_links(
            line,
            in_frontmatter=in_frontmatter,
            resolve=lambda r: self._resolve(r, source_md),
        )


@dataclass
class ChainedCopier:
    """複数の copier を順に適用する（画像 → YAML リンク）。expand_md には 1 つとして渡す。"""

    copiers: list

    def rewrite_line(self, line: str, source_md: Path, *, in_frontmatter: bool) -> str:
        for c in self.copiers:
            line = c.rewrite_line(line, source_md, in_frontmatter=in_frontmatter)
        return line


@dataclass
class ImageSourceCollector:
    """Records the resolved local image sources referenced by the merge inputs.

    ``expand_md`` に image_copier の代わりに渡すと、行は書き換えずに参照先の
    実パスだけを集める。clear-dir-before-merge が merge 自身のコピー元を
    消さないかの判定に使う。
    """

    sources: set[Path] = field(default_factory=set)

    def rewrite_line(self, line: str, source_md: Path, *, in_frontmatter: bool) -> str:
        def record(ref: Ref) -> None:
            if not should_skip(ref.ref):
                self.sources.add((source_md.parent / ref.ref).resolve())
            return None

        rewrite_line(line, in_frontmatter=in_frontmatter, resolve=record)
        rewrite_yaml_links(line, in_frontmatter=in_frontmatter, resolve=record)
        return line


def make_image_copier(args, out_path: Path, in_dir: Path | None):
    """merge 用の copier を作る（画像と YAML リンク。両方無効なら None）。"""
    naming = getattr(args, "image_naming", None) or "preserve"
    image_dir = getattr(args, "image_dir", None)
    image_dir = DEFAULT_IMAGE_DIR if image_dir is None else image_dir
    copiers: list = []
    if not getattr(args, "no_copy_images", False):
        copiers.append(ImageCopier(
            out_md=out_path,
            dir_name=image_dir,
            flatten=getattr(args, "flatten_images", False),
            in_dir=in_dir,
            naming=naming,
            collision=getattr(args, "image_collision", None) or "rename",
        ))
    if not getattr(args, "no_copy_yamls", False):
        # yaml-dir 省略時は image-dir と同じディレクトリに置く
        yaml_dir = getattr(args, "yaml_dir", None)
        copiers.append(YamlCopier(
            out_md=out_path,
            dir_name=image_dir if yaml_dir is None else yaml_dir,
            flatten=getattr(args, "flatten_yamls", False),
            in_dir=in_dir,
            naming=naming,
            collision="overwrite" if getattr(args, "overwrite_yamls", False) else "rename",
        ))
    if not copiers:
        return None
    return copiers[0] if len(copiers) == 1 else ChainedCopier(copiers)
