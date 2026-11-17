"""PDF（typst）の文書プロパティ（タイトル・作成者・サブジェクト・キーワード・言語）を決める。

表紙用のレシピ変数 COVER_* を主な設定項目とし、PDF のプロパティにも流用する。
pandoc の defaults ファイルの ``metadata:``（version 3 以前は ``pandoc.metadata-file`` も）に同じ項目があれば、
そちらで上書きする。

| プロパティ | COVER_* 変数     | metadata のキー |
|------------|------------------|-----------------|
| タイトル   | COVER_TITLE      | title           |
| 作成者     | COVER_AUTHOR     | author          |
| サブジェクト | COVER_SUBTITLE | subject         |
| キーワード | （なし）         | keywords        |
| 言語       | （なし）         | lang            |

作成日は COVER_DATE ではなくビルドした日時（typst の ``date: auto`` の既定）にする。
結果は typst のコード（``#set document(...)`` と ``#set text(lang: ...)``）として
report_template.typst の ``$sem-document$`` に渡す。
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

import yaml

# (プロパティ名, COVER_* 変数名 or None)
_PROPS = (
    ("title", "COVER_TITLE"),
    ("author", "COVER_AUTHOR"),
    ("subject", "COVER_SUBTITLE"),
    ("keywords", None),
    ("lang", None),
)

_LANG_RE = re.compile(r"^([A-Za-z]{2,3})(?:[-_]([A-Za-z]{2}))?$")


def _load_metadata(path: Path, key: str | None) -> dict:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8-sig")) or {}
    except (OSError, yaml.YAMLError) as e:
        logging.debug("metadata を読めません: %s (%s)", path, e)
        return {}
    if not isinstance(data, dict):
        return {}
    if key is not None:
        data = data.get(key) or {}
    return data if isinstance(data, dict) else {}


def collect_metadata(defaults_paths: "list[Path]", metadata_file: "Path | None" = None) -> dict:
    """pandoc に渡す metadata を pandoc と同じ優先順でまとめる。

    metadata-file は defaults の ``metadata:`` に負ける（pandoc の仕様）。defaults は後勝ち。
    """
    merged: dict = {}
    if metadata_file is not None:
        merged.update(_load_metadata(metadata_file, None))
    for p in defaults_paths:
        merged.update(_load_metadata(p, "metadata"))
    return merged


def _plain(v) -> str:
    """YAML の値を 1 行の文字列にする（空なら ""）。"""
    if v is None or v is False:
        return ""
    return re.sub(r"\s+", " ", str(v)).strip()


def _plain_list(v) -> list[str]:
    items = v if isinstance(v, list) else [v]
    return [s for s in (_plain(x) for x in items) if s]


def document_properties(vars_section: dict, metadata: dict) -> dict:
    """COVER_* と metadata から PDF のプロパティを決める（metadata が優先）。"""
    vars_section = vars_section or {}
    props: dict = {}
    for name, var in _PROPS:
        if name in metadata:
            val = metadata[name]
        elif var is not None:
            val = vars_section.get(var)
        else:
            continue
        if name in ("author", "keywords"):
            lst = _plain_list(val)
            if lst:
                props[name] = lst
        else:
            s = _plain(val)
            if s:
                props[name] = s
    return props


def _typst_str(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _typst_array(items: list[str]) -> str:
    return "(" + ", ".join(_typst_str(x) for x in items) + ("," if len(items) == 1 else "") + ")"


def typst_document_code(props: dict) -> str:
    """プロパティを typst のコードにする。何も無ければ ""。"""
    args = []
    if "title" in props:
        args.append("title: " + _typst_str(props["title"]))
    if "author" in props:
        args.append("author: " + _typst_array(props["author"]))
    if "subject" in props:
        args.append("description: " + _typst_str(props["subject"]))
    if "keywords" in props:
        args.append("keywords: " + _typst_array(props["keywords"]))
    lines = []
    if args:
        lines.append("#set document(" + ", ".join(args) + ")")
    lang = props.get("lang")
    if lang:
        m = _LANG_RE.match(lang)
        if m:
            text_args = ["lang: " + _typst_str(m.group(1).lower())]
            if m.group(2):
                text_args.append("region: " + _typst_str(m.group(2).lower()))
            lines.append("#set text(" + ", ".join(text_args) + ")")
        else:
            logging.warning("metadata の lang=%s は言語コード（ja / en / en-US など）でないので使いません", lang)
    return "\n".join(lines)
