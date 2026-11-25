"""procedure 記法の定義と、レシピ version ごとの記法検査・内部形式への正規化。

- version 1（既定）: ``- operation: insertpptx`` + ``pptxfilename: ...`` の operation 記法。
  ``operation`` 省略時は insertpptx とみなす。
- version 2: ``- insertpptx: somefile.pptx`` の操作キー記法。操作キーの値が主引数。
  引数のない操作は ``- beginstay`` / ``- beginstay:`` と書ける。
- version 3: procedure 記法は version 2 と同じ。PDF（typst）の表紙を ``typst-cover-md`` を
  明示したときだけ付ける（暗黙の標準表紙をやめた。_typst_cover.py）。
- version 4: procedure 記法は version 2 と同じ。LaTeX 撤去に合わせて pandoc のキーを整理した
  （PDF の表紙 ``cover-md``・defaults ``defaults``。_pandoc_keys.py）。

v2 以降では ``- group: [...]`` で複数の項目を束ね、``when:`` をまとめて付けられる。
また ``- insertmdpages: a[1-3].md`` は、レンジ展開した各 MD の間に insertvfill と
insertpagebreak を挟んだ insertmd の並びの略記（正規化時に展開する。内部表現には残らない）。
グループは正規化時に平らに展開し、グループの ``when:`` は子の内部キー
``_group_when`` に (位置, when) の組として引き継ぐ（判定は _conditions.py）。

記法の混在（v1 に操作キー記法、v2 に operation 記法）はエラー。読み込み後の内部表現は
常に operation 記法（v1 形式）なので、下流のコードは version を意識しない。
"""

from __future__ import annotations

import logging
from pathlib import Path

from md_merge._mdrange import expand_mdfilename, is_open_range

LATEST_VERSION = 4
SUPPORTED_VERSIONS = frozenset({1, 2, 3, 4})

# procedure.operation の有効値と、各 operation で使えるキー（内部表現 = v1 記法）
PROCEDURE_OPS = frozenset({
    "insertmd", "insertpptx", "insertvar",
    "chapter", "section", "subsection",
    "beginstay", "endstay",
    "insertvspace", "insertpagebreak", "insertvfill",
})

PROCEDURE_ITEM_KEYS: dict[str, frozenset] = {
    "insertmd":    frozenset({"operation", "mdfilename", "range-max"}),
    "insertpptx":  frozenset({"operation", "pptxfilename", "slides", "separator_before", "vars"}),
    "insertvar":   frozenset({"operation", "varname"}),
    "chapter":     frozenset({"operation", "chapter", "section", "title", "note", "id"}),
    "section":     frozenset({"operation", "section", "chapter", "title", "note", "id"}),
    "subsection":  frozenset({"operation", "subsection", "title", "id"}),
    "beginstay":   frozenset({"operation"}),
    "endstay":     frozenset({"operation"}),
    "insertvspace":    frozenset({"operation", "lines"}),
    "insertpagebreak": frozenset({"operation"}),
    "insertvfill":     frozenset({"operation"}),
}

# v2: 複数項目を束ねる要素（内部表現には残らない）。値は子の procedure リスト。
GROUP_KEY = "group"
GROUP_ITEM_KEYS = frozenset({GROUP_KEY, "when", "description"})
# グループから引き継いだ when: の一覧（[(位置ラベル, when), ...]、外側が先）
INHERITED_WHEN_KEY = "_group_when"

# v2 の略記操作（内部表現には残らない）。値は insertmd と同じファイル名（[from-to] レンジ可）で、
# 正規化時に insertmd / insertvfill / insertpagebreak の並びへ展開する。
MDPAGES_OP = "insertmdpages"
MDPAGES_SEPARATOR = ("insertvfill", "insertpagebreak")
# insertmdpages の [from-END] は存在するファイルが merge 時まで決まらないため、正規化では
# insertmd 1 つに残してこの内部キーを付け、merge のファイル収集で区切りを挟む。
MDPAGES_INTERNAL_KEY = "_mdpages"
# v2 の要素に書ける操作キー（内部の操作 + 略記）
V2_OPS = PROCEDURE_OPS | {MDPAGES_OP}

# v1 で operation キーがない場合の既定値 (pptmerge レシピの慣習)
DEFAULT_OP_V1 = "insertpptx"

# v2: 操作キーの値を内部表現のどのキーへ移すか（None は引数なし操作）
PRIMARY_ARG: dict[str, str | None] = {
    "insertmd": "mdfilename",
    "insertpptx": "pptxfilename",
    "insertvar": "varname",
    "chapter": "chapter",
    "section": "section",
    "subsection": "subsection",
    "insertvspace": "lines",
    "beginstay": None,
    "endstay": None,
    "insertpagebreak": None,
    "insertvfill": None,
    MDPAGES_OP: "mdfilename",
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
        if isinstance(item, str) and item in V2_OPS:
            return [f"procedure[{i}]: {item!r} は version 2 以降の記法です（version 1 では operation: {item} と書きます）"]
        return []  # 非辞書の一般エラーは validate / 各サブコマンドに任せる
    if GROUP_KEY in item:
        return [f"procedure[{i}]: group は version 2 以降でのみ使えます（version: {LATEST_VERSION} にしてください）"]
    op = item.get("operation")
    if op == MDPAGES_OP or (op is None and MDPAGES_OP in item):
        return [f"procedure[{i}]: {MDPAGES_OP} は version 2 以降でのみ使えます（version: {LATEST_VERSION} にしてください）"]
    if op is None:
        allowed: frozenset = frozenset()
    else:
        allowed = PROCEDURE_ITEM_KEYS.get(op, frozenset())
    stray = sorted(k for k in item if k in V2_OPS and k not in allowed)
    if stray:
        return [
            f"procedure[{i}]: 操作キー {', '.join(repr(k) for k in stray)} は version 2 以降の記法です"
            f"（version 1 では operation: で操作を指定します。新記法を使うには version: {LATEST_VERSION} にしてください）"
        ]
    return []


def _normalize_v2_item(label: str, item: object) -> tuple[dict | None, list[str]]:
    """v2 の 1 要素（group 以外）を内部表現へ変換する。戻り値は (変換結果, エラー一覧)。

    *label* はエラー表示用の位置（例: ``procedure[3]`` / ``procedure[3].group[0]``）。
    """
    if isinstance(item, str):
        if item not in V2_OPS:
            return None, [f"{label}: 未知の操作です: {item!r} (有効値: {', '.join(sorted(V2_OPS))})"]
        if PRIMARY_ARG[item] is not None:
            return None, [f"{label}: {item} には値が必要です（例: - {item}: ...）"]
        return {"operation": item}, []
    if not isinstance(item, dict):
        return None, []  # 非辞書の一般エラーは validate / 各サブコマンドに任せる
    if "operation" in item:
        return None, [
            f"{label}: operation 記法は version 2 以降では使えません"
            f"（例: - {item.get('operation') or 'insertpptx'}: ...）"
        ]
    ops = [k for k in item if k in V2_OPS]
    if not ops:
        return None, [
            f"{label}: 操作キーがありません（有効な操作: {', '.join(sorted(V2_OPS))}）"
        ]
    if len(ops) > 1:
        return None, [
            f"{label}: 1 要素に操作キーが複数あります: {', '.join(repr(k) for k in ops)}"
            "（version 2 以降では 1 要素に 1 操作です）"
        ]
    op = ops[0]
    primary = PRIMARY_ARG[op]
    value = item[op]
    if primary is None:
        if value is not None:
            return None, [f"{label}: {op} は値を取りません（- {op} と書きます）: {value!r}"]
    elif primary != op and primary in item:
        return None, [
            f"{label}: version 2 以降では {primary} キーは使えません（- {op}: <値> に書きます）"
        ]
    if op in ("insertpptx", "insertmd", "insertvar", MDPAGES_OP) and value is not None and not isinstance(value, str):
        return None, [f"{label}: {op} の値が文字列ではありません（引用符で囲んでください）: {value!r}"]
    result: dict = {"operation": op}
    for k, v in item.items():
        if k == op:
            # 値の省略（- chapter:）は v1 で主引数キーを書かなかった場合と同じ扱いにする
            if primary is not None and v is not None:
                result[primary] = v
        else:
            result[k] = v
    return result, []


def _check_group(label: str, item: dict) -> list[str]:
    """group 要素そのもの（子は除く）の書式エラーを列挙する。"""
    errors: list[str] = []
    ops = [k for k in item if k in V2_OPS]
    if ops:
        errors.append(
            f"{label}: group と操作キー {', '.join(repr(k) for k in ops)} は同じ要素に書けません"
            "（操作は group: の下のリストに書きます）"
        )
    stray = sorted(str(k) for k in item if k not in GROUP_ITEM_KEYS and k not in V2_OPS)
    if stray:
        errors.append(
            f"{label}: group に書けないキー: {', '.join(repr(k) for k in stray)}"
            f"（有効: {', '.join(sorted(GROUP_ITEM_KEYS))}）"
        )
    children = item[GROUP_KEY]
    if not isinstance(children, list) or not children:
        errors.append(f"{label}: group の値は項目のリストで指定してください（子の項目を group: の下にリストで書きます）")
    return errors


def _check_v2_list(items: list, prefix: str) -> list[str]:
    errors: list[str] = []
    for j, item in enumerate(items):
        label = f"{prefix}[{j}]"
        if isinstance(item, dict) and GROUP_KEY in item:
            errors.extend(_check_group(label, item))
            if isinstance(item[GROUP_KEY], list):
                errors.extend(_check_v2_list(item[GROUP_KEY], f"{label}.{GROUP_KEY}"))
        else:
            errors.extend(_normalize_v2_item(label, item)[1])
    return errors


def _flatten_v2_list(items: list, prefix: str, inherited: tuple) -> list:
    """v2 の項目リストを内部表現へ変換し、group を展開して平らなリストにする。"""
    result: list = []
    for j, item in enumerate(items):
        label = f"{prefix}[{j}]"
        if isinstance(item, dict) and GROUP_KEY in item:
            inner = inherited
            if "when" in item:
                inner = inherited + ((label, item["when"]),)
            result.extend(_flatten_v2_list(item[GROUP_KEY], f"{label}.{GROUP_KEY}", inner))
            continue
        normalized = _normalize_v2_item(label, item)[0] if isinstance(item, (dict, str)) else item
        expanded = _expand_mdpages(normalized) if isinstance(normalized, dict) else [normalized]
        for one in expanded:
            if inherited and isinstance(one, dict):
                one[INHERITED_WHEN_KEY] = list(inherited)
            result.append(one)
    return result


def _expand_mdpages(item: dict) -> list[dict]:
    """insertmdpages を insertmd / insertvfill / insertpagebreak の並びへ展開する。

    ファイルが 1 つ（レンジなし）なら insertmd 1 つと同じ。``when:`` は展開した全項目に
    付ける（区切りだけが残らないように）。その他の兄弟キー（``description`` 等）は
    先頭の insertmd にだけ残す。レンジが不正なら値をそのまま insertmd 1 つにして、
    insertmd と同じ警告・validate エラーに任せる。
    """
    if item.get("operation") != MDPAGES_OP:
        return [item]
    extras = {k: v for k, v in item.items() if k not in ("operation", "mdfilename")}
    shared = {k: v for k, v in extras.items() if k == "when"}
    val = item.get("mdfilename")
    if is_open_range(val):
        # [from-END]: 実在ファイルは merge 時に決まる → 区切りは collect_procedure_items が挟む
        return [{"operation": "insertmd", "mdfilename": val, **extras, MDPAGES_INTERNAL_KEY: True}]
    try:
        names = expand_mdfilename(val) if isinstance(val, str) else [val]
    except ValueError:
        names = [val]
    result: list[dict] = []
    for n, name in enumerate(names):
        if n:
            result.extend({"operation": op, **shared} for op in MDPAGES_SEPARATOR)
        md: dict = {"operation": "insertmd"}
        if name is not None:
            md["mdfilename"] = name
        md.update(extras if n == 0 else shared)
        result.append(md)
    return result


def check_procedure_notation(recipe: dict) -> list[str]:
    """version と procedure 記法の不整合を列挙する（validate 用。例外は投げない）。"""
    try:
        version = recipe_version(recipe)
    except ProcedureNotationError as e:
        return [str(e)]
    procedure = recipe.get("procedure")
    if not isinstance(procedure, list):
        return []
    if version != 1:
        return _check_v2_list(procedure, "procedure")
    errors: list[str] = []
    for i, item in enumerate(procedure):
        errors.extend(_check_v1_item(i, item))
    return errors


_warned_v1: set[str] = set()


def normalize_recipe(
    recipe: object, source: Path | None = None, warn_deprecated: bool = True
) -> object:
    """procedure を内部表現（operation 記法）へ正規化したレシピを返す。

    記法に不整合があれば ProcedureNotationError。version 1 のレシピは
    ファイルごとに 1 回だけ非推奨の warning を出す。旧 ``input`` セクションは
    ``fragment`` / ``source`` に読み替える（_source_keys.py）。
    """
    if not isinstance(recipe, dict):
        return recipe
    from md_merge._source_keys import normalize_source_keys  # 循環 import を避ける
    recipe = normalize_source_keys(recipe, source, warn=warn_deprecated)
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
                    "version 1 の operation 記法は非推奨です。version: %d の記法"
                    "（例: - insertpptx: a.pptx）へ移行してください%s", LATEST_VERSION, where,
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
    return {**recipe, "procedure": _flatten_v2_list(procedure, "procedure", ())}


def to_notation(item: dict, version: int) -> dict:
    """内部表現の 1 要素を、指定 version の記法の dict に変換する（レシピ生成用）。"""
    if version == 1:
        return dict(item)
    op = item.get("operation", DEFAULT_OP_V1)
    primary = PRIMARY_ARG.get(op)
    result: dict = {op: item.get(primary) if primary else None}
    for k, v in item.items():
        if k in ("operation", primary, INHERITED_WHEN_KEY):
            continue
        result[k] = v
    return result
