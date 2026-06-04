from __future__ import annotations

import re

_FORMAT_VERSION_RE = re.compile(r'^NOTE_CONTENT_FORMAT:\s*\S+')
_CONTENT_TYPE_RE = re.compile(r'^\{\{BLOCK:([A-Z]+)(?::([A-Z]+))?\}\}$')


def _parse_blocks(note_text: str) -> list[tuple[str, str | None, str]] | None:
    """NOTE_CONTENT_FORMAT ノートを解析して (maintype, subtype, body) のリストを返す。

    フォーマットヘッダーがなければ None を返す。
    """
    text = note_text.replace("\r\n", "\n").replace("\r", "\n")
    lines = text.splitlines()

    if not lines or not _FORMAT_VERSION_RE.match(lines[0].strip()):
        return None

    segments = re.split(r'(?m)^===BLOCK===[ \t]*$', text)
    # segments[0] はバージョンヘッダー、segments[1:] が各ブロック

    parsed: list[tuple[str, str | None, str]] = []
    for seg in segments[1:]:
        seg_lines = seg.splitlines()

        # 先頭の空行をスキップして CONTENT_TYPE_LINE を探す
        type_idx: int | None = None
        for j, sline in enumerate(seg_lines):
            if sline.strip():
                type_idx = j
                break
        if type_idx is None:
            continue

        m = _CONTENT_TYPE_RE.match(seg_lines[type_idx].strip())
        if not m:
            continue

        maintype = m.group(1)
        subtype = m.group(2)
        # {{BLOCK:MD}} (サブタイプなし) = {{BLOCK:MD:LONG}}
        if maintype == "MD" and subtype is None:
            subtype = "LONG"

        # CONTENT_BODY: タイプ行より後
        body_lines = seg_lines[type_idx + 1:]
        # タイプ行直後の空行（文法上の NEWLINE）を 1 行だけスキップ
        if body_lines and not body_lines[0].strip():
            body_lines = body_lines[1:]
        # 末尾の空行を除去
        while body_lines and not body_lines[-1].strip():
            body_lines.pop()

        parsed.append((maintype, subtype, "\n".join(body_lines)))

    return parsed


def _body_to_directives(body: str) -> dict[str, str]:
    """CONTENT_BODY の key: value 行を辞書に変換する。"""
    result: dict[str, str] = {}
    for line in body.splitlines():
        if ":" in line:
            key, _, val = line.partition(":")
            result[key.strip()] = val.strip()
    return result


def parse_note_content(note_text: str) -> tuple[dict[str, str], str]:
    """NOTE_CONTENT_FORMAT ノートを解析して (directives, md_text) を返す。

    directives: 最初の EXPORT_BLOCK の key: value ペア。
    md_text:    MD_LONGBLOCK > MD_BLOCK > PLAIN_BLOCK の優先度で選択した本文。

    フォーマットヘッダーがなければ ({}, "") を返す。
    """
    blocks = _parse_blocks(note_text)
    if blocks is None:
        return {}, ""

    # 最初の EXPORT_BLOCK からディレクティブを取得
    directives: dict[str, str] = {}
    for maintype, subtype, body in blocks:
        if maintype == "EXPORT":
            directives = _body_to_directives(body)
            break

    # MD テキストを優先度順に選択
    md_text = ""
    for maintype, subtype, body in blocks:
        if maintype == "MD" and subtype == "LONG":
            md_text = body
            break
    if not md_text:
        for maintype, subtype, body in blocks:
            if maintype == "MD":
                md_text = body
                break
    if not md_text:
        for maintype, subtype, body in blocks:
            if maintype == "PLAIN":
                md_text = body
                break

    return directives, md_text


def parse_note_md_blocks(note_text: str) -> list[str]:
    """すべての MD_BLOCK の CONTENT_BODY をリストで返す（出現順）。

    フォーマットヘッダーがなければ空リストを返す。
    """
    blocks = _parse_blocks(note_text)
    if not blocks:
        return []
    return [body for maintype, subtype, body in blocks if maintype == "MD"]


def parse_note_md_body(note_text: str) -> str | None:
    """MD_LONGBLOCK > MD_BLOCK > PLAIN_BLOCK の優先度で最初に見つかったブロックの CONTENT_BODY を返す。

    フォーマットヘッダーがなければ None を返す。
    マッチするブロックがなければ None を返す。
    """
    blocks = _parse_blocks(note_text)
    if blocks is None:
        return None
    for maintype, subtype, body in blocks:
        if maintype == "MD" and subtype == "LONG":
            return body
    for maintype, subtype, body in blocks:
        if maintype == "MD":
            return body
    for maintype, subtype, body in blocks:
        if maintype == "PLAIN":
            return body
    return None


def parse_note_image_directives(note_text: str) -> list[dict[str, str]]:
    """すべての IMAGE_BLOCK の CONTENT_BODY を key:value 辞書のリストとして返す。

    IMAGE_BLOCK が存在しない、またはフォーマットヘッダーがなければ空リストを返す。
    """
    blocks = _parse_blocks(note_text)
    if not blocks:
        return []
    return [
        _body_to_directives(body)
        for maintype, subtype, body in blocks
        if maintype == "IMAGE"
    ]
