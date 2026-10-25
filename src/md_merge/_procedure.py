"""procedure 記法の定義と、レシピ version ごとの記法検査・内部形式への正規化。

- version 1（既定）: ``- operation: insertpptx`` + ``pptxfilename: ...`` の operation 記法。
  ``operation`` 省略時は insertpptx とみなす。
- version 2: ``- insertpptx: somefile.pptx`` の操作キー記法。操作キーの値が主引数。
  引数のない操作は ``- beginstay`` / ``- beginstay:`` と書ける。

記法の混在（v1 に操作キー記法、v2 に operation 記法）はエラー。読み込み後の内部表現は
常に operation 記法（v1 形式）なので、下流のコードは version を意識しない。
"""

from __future__ import annotations

import logging
from pathlib import Path

LATEST_VERSION = 2
SUPPORTED_VERSIONS = frozenset({1, 2})

# procedure.operation の有効値と、各 operation で使えるキー（内部表現 = v1 記法）
PROCEDURE_OPS = frozenset({
    "insertmd", "insertpptx",
    "chapter", "section", "subsection",
    "beginstay", "endstay",
    "insertvspace", "insertpagebreak", "insertvfill",
})

PROCEDURE_ITEM_KEYS: dict[str, frozenset] = {
    "insertmd":    frozenset({"operation", "mdfilename"}),
    "insertpptx":  frozenset({"operation", "pptxfilename", "slides", "separator_before", "vars"}),
    "chapter":     frozenset({"operation", "chapter", "section", "title", "note", "id"}),
    "section":     frozenset({"operation", "section", "chapter", "title", "note", "id"}),
    "subsection":  frozenset({"operation", "subsection", "title", "id"}),
    "beginstay":   frozenset({"operation"}),
    "endstay":     frozenset({"operation"}),
    "insertvspace":    frozenset({"operation", "lines"}),
    "insertpagebreak": frozenset({"operation"}),
    "insertvfill":     frozenset({"operation"}),
}

# v1 で operation キーがない場合の既定値 (pptmerge レシピの慣習)
DEFAULT_OP_V1 = "insertpptx"

# v2: 操作キーの値を内部表現のどのキーへ移すか（None は引数なし操作）
PRIMARY_ARG: dict[str, str | None] = {
    "insertmd": "mdfilename",
    "insertpptx": "pptxfilename",
    "chapter": "chapter",
    "section": "section",
    "subsection": "subsection",
    "insertvspace": "lines",
    "beginstay": None,
    "endstay": None,
    "insertpagebreak": None,
    "insertvfill": None,
}


class ProcedureNotationError(ValueError):
    """レシピ version と procedure 記法が合わない、または記法として解釈できない。"""


def recipe_version(recipe: dict) -> int:
    """レシピの version を返す（省略時は 1）。未対応の値は ProcedureNotationError。"""
    version = recipe.get("version")
    if version is None:
        return 1
    if isinstance(version, bool) or version not in SUPPORTED_VERSIONS:
        raise ProcedureNotationError(
            f"未対応の version です: {version!r}"
            f" (有効値: {', '.join(str(v) for v in sorted(SUPPORTED_VERSIONS))})"
        )
    return version


def _check_v1_item(i: int, item: object) -> list[str]:
    if not isinstance(item, dict):
        if isinstance(item, str) and item in PROCEDURE_OPS:
            return [f"procedure[{i}]: {item!r} は version 2 の記法です（version 1 では operation: {item} と書きます）"]
        return []  # 非辞書の一般エラーは validate / 各サブコマンドに任せる
    op = item.get("operation")
    if op is None:
        allowed: frozenset = frozenset()
    else:
        allowed = PROCEDURE_ITEM_KEYS.get(op, frozenset())
    stray = sorted(k for k in item if k in PROCEDURE_OPS and k not in allowed)
    if stray:
        return [
            f"procedure[{i}]: 操作キー {', '.join(repr(k) for k in stray)} は version 2 の記法です"
            "（version 1 では operation: で操作を指定します。新記法を使うには version: 2 にしてください）"
        ]
    return []


def _normalize_v2_item(i: int, item: object) -> tuple[dict | None, list[str]]:
    """v2 の 1 要素を内部表現へ変換する。戻り値は (変換結果, エラー一覧)。"""
    if isinstance(item, str):
        if item not in PROCEDURE_OPS:
            return None, [f"procedure[{i}]: 未知の操作です: {item!r} (有効値: {', '.join(sorted(PROCEDURE_OPS))})"]
        if PRIMARY_ARG[item] is not None:
            return None, [f"procedure[{i}]: {item} には値が必要です（例: - {item}: ...）"]
        return {"operation": item}, []
    if not isinstance(item, dict):
        return None, []  # 非辞書の一般エラーは validate / 各サブコマンドに任せる
    if "operation" in item:
        return None, [
            f"procedure[{i}]: operation 記法は version 2 では使えません"
            f"（例: - {item.get('operation') or 'insertpptx'}: ...）"
        ]
    ops = [k for k in item if k in PROCEDURE_OPS]
    if not ops:
        return None, [
            f"procedure[{i}]: 操作キーがありません（有効な操作: {', '.join(sorted(PROCEDURE_OPS))}）"
        ]
    if len(ops) > 1:
        return None, [
            f"procedure[{i}]: 1 要素に操作キーが複数あります: {', '.join(repr(k) for k in ops)}"
            "（version 2 では 1 要素に 1 操作です）"
        ]
    op = ops[0]
    primary = PRIMARY_ARG[op]
    value = item[op]
    if primary is None:
        if value is not None:
            return None, [f"procedure[{i}]: {op} は値を取りません（- {op} と書きます）: {value!r}"]
    elif primary != op and primary in item:
        return None, [
            f"procedure[{i}]: version 2 では {primary} キーは使えません（- {op}: <値> に書きます）"
        ]
    if op in ("insertpptx", "insertmd") and value is not None and not isinstance(value, str):
        return None, [f"procedure[{i}]: {op} の値が文字列ではありません（引用符で囲んでください）: {value!r}"]
    result: dict = {"operation": op}
    for k, v in item.items():
        if k == op:
            # 値の省略（- chapter:）は v1 で主引数キーを書かなかった場合と同じ扱いにする
            if primary is not None and v is not None:
                result[primary] = v
        else:
            result[k] = v
    return result, []


def check_procedure_notation(recipe: dict) -> list[str]:
    """version と procedure 記法の不整合を列挙する（validate 用。例外は投げない）。"""
    try:
        version = recipe_version(recipe)
    except ProcedureNotationError as e:
        return [str(e)]
    procedure = recipe.get("procedure")
    if not isinstance(procedure, list):
        return []
    errors: list[str] = []
    for i, item in enumerate(procedure):
        if version == 1:
            errors.extend(_check_v1_item(i, item))
        else:
            errors.extend(_normalize_v2_item(i, item)[1])
    return errors


_warned_v1: set[str] = set()


def normalize_recipe(
    recipe: object, source: Path | None = None, warn_deprecated: bool = True
) -> object:
    """procedure を内部表現（operation 記法）へ正規化したレシピを返す。

    記法に不整合があれば ProcedureNotationError。version 1 のレシピは
    ファイルごとに 1 回だけ非推奨の warning を出す。
    """
    if not isinstance(recipe, dict):
        return recipe
    errors = check_procedure_notation(recipe)
    where = f": {source}" if source is not None else ""
    if errors:
        raise ProcedureNotationError(
            f"procedure の記法が version と合いません{where}\n  " + "\n  ".join(errors)
        )
    version = recipe_version(recipe)
    procedure = recipe.get("procedure")
    if version == 1:
        if warn_deprecated and isinstance(procedure, list) and procedure:
            key = str(source) if source is not None else ""
            if key not in _warned_v1:
                _warned_v1.add(key)
                logging.warning(
                    "version 1 の operation 記法は非推奨です。version: 2 の記法"
                    "（例: - insertpptx: a.pptx）へ移行してください%s", where,
                )
        if not isinstance(procedure, list):
            return recipe
        # operation 省略要素は insertpptx（v1 の慣習）。下流で既定値を揃えるため明示する
        filled = [
            {**item, "operation": DEFAULT_OP_V1}
            if isinstance(item, dict) and item.get("operation") is None else item
            for item in procedure
        ]
        return {**recipe, "procedure": filled}
    if not isinstance(procedure, list):
        return recipe
    normalized = [
        _normalize_v2_item(i, item)[0] if isinstance(item, (dict, str)) else item
        for i, item in enumerate(procedure)
    ]
    return {**recipe, "procedure": normalized}


def to_notation(item: dict, version: int) -> dict:
    """内部表現の 1 要素を、指定 version の記法の dict に変換する（レシピ生成用）。"""
    if version == 1:
        return dict(item)
    op = item.get("operation", DEFAULT_OP_V1)
    primary = PRIMARY_ARG.get(op)
    result: dict = {op: item.get(primary) if primary else None}
    for k, v in item.items():
        if k in ("operation", primary):
            continue
        result[k] = v
    return result
