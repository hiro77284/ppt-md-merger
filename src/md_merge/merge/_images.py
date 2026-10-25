import logging
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from md_merge._imagerefs import Ref, apply_naming, pick_destination, rewrite_line, should_skip

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
        return self.out_md.parent / self.dir_name

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

    def _resolve(self, ref: Ref, source_md: Path) -> str | None:
        """Copy the referenced image and return its ref relative to the merged MD."""
        if should_skip(ref.ref):
            return None
        img_src = (source_md.parent / ref.ref).resolve()
        if not img_src.exists():
            logging.warning("画像ファイルが見つかりません: %s (参照元: %s)", img_src, source_md)
            return None
        img_dst = self._copy(img_src)
        return img_dst.relative_to(self.out_md.parent).as_posix()

    def _copy(self, src: Path) -> Path:
        if src in self._registry:
            return self._registry[src]
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


def make_image_copier(args, out_path: Path, in_dir: Path | None) -> "ImageCopier | None":
    if getattr(args, "no_copy_images", False):
        return None
    dir_name = getattr(args, "image_dir", None)
    return ImageCopier(
        out_md=out_path,
        dir_name=DEFAULT_IMAGE_DIR if dir_name is None else dir_name,
        flatten=getattr(args, "flatten_images", False),
        in_dir=in_dir,
        naming=getattr(args, "image_naming", None) or "preserve",
        collision=getattr(args, "image_collision", None) or "rename",
    )
