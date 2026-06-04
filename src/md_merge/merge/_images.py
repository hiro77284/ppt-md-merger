import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

# Matches ![alt](ref) — captures prefix, ref, suffix for easy substitution
_IMG_RE = re.compile(r'(!\[[^\]]*\]\()([^)\s]+)(\))')

# Refs that should not be processed (URLs, absolute paths, anchors, data URIs)
_SKIP_RE = re.compile(r'^(?:[a-zA-Z][a-zA-Z0-9+\-.]*://|//|/|#|data:)')

_DEFAULT_DIR = ""


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
    _registry: dict[Path, Path] = field(default_factory=dict, init=False)

    @property
    def img_dir(self) -> Path:
        return self.out_md.parent / self.dir_name

    def process(self, line: str, source_md: Path) -> str:
        """Rewrite all local image refs in *line*, copying the files."""
        return _IMG_RE.sub(lambda m: self._handle(m, source_md), line)

    # ── internals ──────────────────────────────────────────────────────────

    def _handle(self, m: re.Match, source_md: Path) -> str:
        prefix, ref, suffix = m.group(1), m.group(2), m.group(3)
        if _SKIP_RE.match(ref):
            return m.group(0)
        img_src = (source_md.parent / ref).resolve()
        if not img_src.exists():
            return m.group(0)  # missing image — leave ref as-is
        img_dst = self._copy(img_src)
        new_ref = img_dst.relative_to(self.out_md.parent).as_posix()
        return f"{prefix}{new_ref}{suffix}"

    def _copy(self, src: Path) -> Path:
        if src in self._registry:
            return self._registry[src]
        dst = self._dst_path(src)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        self._registry[src] = dst
        return dst

    def _dst_path(self, src: Path) -> Path:
        if self.flatten or self.in_dir is None:
            return self._unique(self.img_dir / src.name)
        try:
            rel = src.relative_to(self.in_dir)
            return self.img_dir / rel
        except ValueError:
            return self._unique(self.img_dir / src.name)

    def _unique(self, candidate: Path) -> Path:
        taken = set(self._registry.values())
        if candidate not in taken and not candidate.exists():
            return candidate
        stem, suffix = candidate.stem, candidate.suffix
        i = 1
        while True:
            new = candidate.with_name(f"{stem}_{i}{suffix}")
            if new not in taken and not new.exists():
                return new
            i += 1


def make_image_copier(args, out_path: Path, in_dir: Path | None) -> "ImageCopier | None":
    if getattr(args, "no_copy_images", False):
        return None
    return ImageCopier(
        out_md=out_path,
        dir_name=getattr(args, "image_dir", None) or _DEFAULT_DIR,
        flatten=getattr(args, "flatten_images", False),
        in_dir=in_dir,
    )
