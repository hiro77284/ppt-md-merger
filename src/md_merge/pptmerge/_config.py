from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

import yaml

from md_merge.merge._recipe import _DuplicateKeyLoader, _process_yaml_text


class ConfigError(Exception):
    pass


def load_yaml(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding='utf-8')
    text = _process_yaml_text(text, path.parent)
    data = yaml.load(text, Loader=_DuplicateKeyLoader)
    if not isinstance(data, dict):
        raise ConfigError("YAMLのトップレベルは辞書である必要があります。")
    return data


def resolve_base(config_path: Path, workdir: Path | None = None) -> Path:
    return workdir.resolve() if workdir else config_path.parent.resolve()


def resolve_dir(
    dir_value: str,
    config_path: Path,
    workdir: Path | None = None,
) -> Path:
    p = Path(dir_value)
    if p.is_absolute():
        return p.resolve()
    base = resolve_base(config_path, workdir)
    return (base / p).resolve()


def resolve_file(file_value: str, input_dir: Path) -> Path:
    p = Path(file_value)
    if p.is_absolute():
        return p.resolve()
    return (input_dir / p).resolve()


def resolve_dirs(
    dir_value: "str | list",
    config_path: Path,
    workdir: Path | None = None,
) -> list[Path]:
    """Resolve a single dir string or list of dir strings to a list of Paths."""
    entries = dir_value if isinstance(dir_value, list) else [dir_value]
    return [resolve_dir(str(e), config_path, workdir) for e in entries]


def resolve_file_in_dirs(file_value: str, input_dirs: list[Path]) -> Path:
    """Search *input_dirs* for *file_value*; warn if found in multiple; return first found.

    Falls back to ``input_dirs[0] / file_value`` when not found in any directory
    so the caller's existence check can produce a meaningful error path.
    """
    p = Path(file_value)
    if p.is_absolute():
        return p.resolve()
    found_dirs = [d for d in input_dirs if (d / file_value).exists()]
    found = [(d / file_value).resolve() for d in found_dirs]
    unique = list(dict.fromkeys(found))
    if len(unique) > 1:
        logging.warning(
            "insertpptx: '%s' が複数のディレクトリに存在します。最初に見つかったものを使用します: %s\n  発見: %s",
            file_value, found[0], ", ".join(str(d) for d in found_dirs),
        )
    return found[0] if found else (input_dirs[0] / file_value).resolve()


def parse_log_duplicate(config: dict[str, Any]) -> str | None:
    log_cfg = config.get("log") or {}
    dup = log_cfg.get("duplicate")
    if dup is None:
        return None
    s = str(dup).strip()
    if not s:
        return None
    low = s.lower()
    if low in ("stdout", "stderr"):
        return low
    raise ConfigError(
        f"log.duplicate は stdout または stderr です（未設定または空で無効）: {dup!r}"
    )


_RANGE_RE = re.compile(r"^(\d+)-(\d+)$")


def _parse_slides_entry(entry: Any, original: Any) -> list[int]:
    if isinstance(entry, bool):
        pass
    elif isinstance(entry, int) and entry > 0:
        return [entry]
    elif isinstance(entry, str):
        s = entry.strip()
        if s.isdigit():
            n = int(s)
            if n > 0:
                return [n]
        m = _RANGE_RE.match(s)
        if m:
            start, end = int(m.group(1)), int(m.group(2))
            if start < 1:
                raise ConfigError(f"slides の範囲は1以上で指定してください: {entry!r}")
            if end < start:
                raise ConfigError(f"slides の範囲で終端が始端より小さいです: {entry!r}")
            return list(range(start, end + 1))
    raise ConfigError(
        f"slides の要素は1以上の整数または 'N-M' 形式の範囲で指定してください: {entry!r}"
    )


def parse_slides(slides: Any) -> list[int] | None:
    if slides is None or slides == "all":
        return None
    if isinstance(slides, int) and not isinstance(slides, bool):
        return list(_parse_slides_entry(str(slides), slides))
    if isinstance(slides, str):
        entries = [p.strip() for p in slides.split(",") if p.strip()]
        result = []
        for entry in entries:
            result.extend(_parse_slides_entry(entry, slides))
        return result
    if isinstance(slides, list):
        result = []
        for entry in slides:
            result.extend(_parse_slides_entry(entry, slides))
        return result
    raise ConfigError(
        f"slides は all、カンマ区切り文字列、整数配列、または 'N-M' 範囲で指定してください: {slides}"
    )


def validate_config(config: dict[str, Any]) -> None:
    for key in ("output", "procedure"):
        if key not in config:
            raise ConfigError(f"{key} がありません。")

    output = config["output"]
    input_ = config.get("input") or {}
    procedure = config["procedure"]

    if not isinstance(output, dict):
        raise ConfigError("output は辞書で指定してください。")
    if not isinstance(input_, dict):
        raise ConfigError("input は辞書で指定してください。")
    if not isinstance(procedure, list):
        raise ConfigError("procedure は配列で指定してください。")

    if not output.get("pptxfilename") and not output.get("targetbasefilename"):
        raise ConfigError("output.pptxfilename または output.targetbasefilename が必要です。")

    log_cfg = config.get("log")
    if isinstance(log_cfg, dict):
        parse_log_duplicate(config)

    indexer = config.get("indexer")
    if isinstance(indexer, dict):
        pptxnumbering = indexer.get("pptxnumbering")
        # YAML の裸の 'no' はブール False に変換されるため正規化する
        if pptxnumbering is False:
            indexer["pptxnumbering"] = "no"
            pptxnumbering = "no"
        _VALID_NUMBERING = ("no", "chapt_section", "idresolve")
        if pptxnumbering is not None and pptxnumbering not in _VALID_NUMBERING:
            raise ConfigError(
                f"indexer.pptxnumbering は {' / '.join(_VALID_NUMBERING)} です: {pptxnumbering!r}"
            )

    _VALID_OPS = frozenset(
        ("insertpptx", "insertmd","chapter", "section", "subsection", "beginstay", "endstay")
    )
    for item in procedure:
        if not isinstance(item, dict):
            raise ConfigError("procedure の各要素は辞書で指定してください。")
        operation = item.get("operation", "insertpptx")
        if operation not in _VALID_OPS:
            raise ConfigError(
                f"procedure の operation は {' / '.join(sorted(_VALID_OPS))} です: {operation!r}"
            )
        if operation == "insertpptx" and item.get("pptxfilename") is None:
            raise ConfigError(
                "operation が insertpptx のときは pptxfilename に入力 pptx を指定してください。"
            )
