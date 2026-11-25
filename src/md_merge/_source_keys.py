"""入力ファイルの探し方を書くキー（``fragment`` / ``source`` セクション）。

``input`` セクションは廃止し、中身を目的別の 2 つのセクションに分けた。

- ``fragment.dirs``: 結合する部品（insertmd の MD・insertpptx の pptx・``_include`` 先など）を探す
  ディレクトリ。merge / pptmerge ほか、procedure を読む段が使う。
- ``source.cropimagedirs``: crop が RANGE 付き画像を探すディレクトリ。
- ``source.cropsrc``: 画像・MD・図版 YAML を取り出す元の pptx（と PDF）。
  pptimgexport / pptmdexport / pptyamlexport / pptpdfexport が使う。

旧キーの扱い（recipe version によらない）:

- ``input.dirs`` / ``input.imagesdir`` / ``input.cropsrc``: 非推奨。新しいキーに読み替え、
  ファイルごとに 1 回 warning を出す。新旧の両方を書くとエラー。
- ``input.mddir`` / ``input.pptxdir``: エラー（以前から非推奨だった）。``fragment.dirs`` に書く。

読み替えは :func:`md_merge._procedure.normalize_recipe` が行うので、各サブコマンドは新しいキーだけを
読めばよい。``tools/convert_input_keys.py`` でレシピを書き換えられる。
"""

from __future__ import annotations

import logging
from pathlib import Path

from md_merge._procedure import ProcedureNotationError

FRAGMENT = "fragment"
SOURCE = "source"
LEGACY_INPUT = "input"

FRAGMENT_KEYS = frozenset({"dirs"})
SOURCE_KEYS = frozenset({"cropimagedirs", "cropsrc"})

# 非推奨の旧キー → (新しいセクション, 新しいキー)
DEPRECATED_INPUT_KEYS: dict[str, tuple[str, str]] = {
    "dirs": (FRAGMENT, "dirs"),
    "imagesdir": (SOURCE, "cropimagedirs"),
    "cropsrc": (SOURCE, "cropsrc"),
}

# 廃止した旧キー（エラー）→ 案内
REMOVED_INPUT_KEYS: dict[str, str] = {
    "mddir": "input.mddir は廃止しました。fragment.dirs に書いてください（相対パスはレシピ YAML のあるディレクトリ基準）",
    "pptxdir": "input.pptxdir は廃止しました。fragment.dirs に書いてください（相対パスはレシピ YAML のあるディレクトリ基準）",
}

CONVERT_HINT = "tools/convert_input_keys.py で書き換えられます"

_warned: set[tuple[str, str]] = set()


class SourceKeyError(ProcedureNotationError):
    """``input`` / ``fragment`` / ``source`` セクションの書き方の誤り。"""


def source_key_errors(recipe: object) -> list[str]:
    """廃止キー・新旧の重複・セクションの型の誤りを列挙する。"""
    if not isinstance(recipe, dict):
        return []
    errors: list[str] = []
    for name in (FRAGMENT, SOURCE):
        sec = recipe.get(name)
        if sec is not None and not isinstance(sec, dict):
            errors.append(f"{name} はマッピングで指定してください")
    legacy = recipe.get(LEGACY_INPUT)
    if legacy is None:
        return errors
    if not isinstance(legacy, dict):
        errors.append(
            "input セクションは廃止しました。fragment.dirs / source.cropimagedirs / source.cropsrc に書いてください"
        )
        return errors
    for key, msg in REMOVED_INPUT_KEYS.items():
        if key in legacy:
            errors.append(msg)
    for old, (section, new) in DEPRECATED_INPUT_KEYS.items():
        if old not in legacy:
            continue
        sec = recipe.get(section)
        if isinstance(sec, dict) and new in sec:
            errors.append(
                f"input.{old} と {section}.{new} が両方あります。input.{old} を消してください"
            )
    return errors


def deprecated_input_keys(recipe: object) -> list[str]:
    """レシピに書かれている非推奨の旧キー（``input.dirs`` など）の名前。"""
    legacy = recipe.get(LEGACY_INPUT) if isinstance(recipe, dict) else None
    if not isinstance(legacy, dict):
        return []
    return [k for k in DEPRECATED_INPUT_KEYS if k in legacy]


def deprecation_message(old: str) -> str:
    section, new = DEPRECATED_INPUT_KEYS[old]
    return f"input.{old} は非推奨です。{section}.{new} に書き換えてください（{CONVERT_HINT}）"


def normalize_source_keys(recipe: dict, source: Path | None = None, warn: bool = True) -> dict:
    """旧 ``input`` セクションを ``fragment`` / ``source`` に読み替えたレシピを返す。

    誤りがあれば :class:`SourceKeyError`。*warn* が真なら旧キーごと・ファイルごとに 1 回 warning。
    未知の旧キーは ``input`` に残す（validate が未知のキーとして報告する）。
    """
    errors = source_key_errors(recipe)
    where = f": {source}" if source is not None else ""
    if errors:
        raise SourceKeyError("レシピのキーが不正です" + where + "\n  " + "\n  ".join(errors))
    legacy = recipe.get(LEGACY_INPUT)
    if not isinstance(legacy, dict):
        return recipe
    result = dict(recipe)
    rest = dict(legacy)
    for old, (section, new) in DEPRECATED_INPUT_KEYS.items():
        if old not in rest:
            continue
        sec = dict(result.get(section) or {})
        sec[new] = rest.pop(old)
        result[section] = sec
        if warn:
            key = (str(source) if source is not None else "", old)
            if key not in _warned:
                _warned.add(key)
                logging.warning("%s%s", deprecation_message(old), where)
    if rest:
        result[LEGACY_INPUT] = rest
    else:
        result.pop(LEGACY_INPUT, None)
    return result


def fragment_section(recipe: dict) -> dict:
    sec = recipe.get(FRAGMENT)
    return sec if isinstance(sec, dict) else {}


def source_section(recipe: dict) -> dict:
    sec = recipe.get(SOURCE)
    return sec if isinstance(sec, dict) else {}
