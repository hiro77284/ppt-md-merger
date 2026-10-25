import logging
import re

_ID_RE = re.compile(r'\{\{#id:([^:}]+):([^:}]+):([^}]+)\}\}')
_REF_RE = re.compile(r'\{\{(num|title|label|rawtitle):([^:}]+:[^:}]+:[^}]+)\}\}')
_VAR_RE = re.compile(r'\{\{v:([A-Za-z0-9_]+)\}\}')
_HEADING_RE = re.compile(r'^(#{1,3})\s+(.*)')
_NOLABEL_RE = re.compile(r'\s*\{\{nolabel\}\}')
_NOREF_RE = re.compile(r'\s*\{\{noref\}\}')
# {{sectionlist}} = 現在の chapter のセクション一覧。
# {{sectionlist:chapter:PART:LOCAL}} = 指定 chapter のセクション一覧（明示形）。
_SECTIONLIST_RE = re.compile(r'\{\{sectionlist(?::([^:}]+):([^:}]+):([^}]+))?\}\}')

_EXPECTED_HEADING_LEVEL = {"chapter": 1, "section": 2, "subsection": 3}


def build_resolved_map(resolved_data: dict) -> dict[str, dict]:
    return {e["full_id"]: e for e in (resolved_data.get("entries") or [])}


def render_content(
    content: str,
    resolved_map: dict[str, dict],
    vars_map: dict[str, str] | None = None,
    apply_title_labels: bool = True,
) -> str:
    """Apply title substitution, reference substitution, and variable substitution."""
    lines = content.splitlines(keepends=True)
    output: list[str] = []
    i = 0

    # 文書順のエントリ列（dict は挿入順＝文書順を保持）。{{sectionlist}} 展開で使う。
    entries_in_order = list(resolved_map.values())
    # 走査中に直近で見た chapter の full_id。{{sectionlist}}（引数なし）の基準。
    current_chapter_full_id: str | None = None

    while i < len(lines):
        line = lines[i]
        raw = line.rstrip("\n\r")
        id_matches = list(_ID_RE.finditer(raw))

        if id_matches:
            # 直近 chapter を記録（{{sectionlist}} の「現在の chapter」判定に使う）
            for m in id_matches:
                if m.group(1) == "chapter":
                    current_chapter_full_id = f"{m.group(1)}:{m.group(2)}:{m.group(3)}"
                    break
            nolabel = bool(_NOLABEL_RE.search(raw))
            noref = bool(_NOREF_RE.search(raw))
            # Convert all {{#id:...}} markers on this line to HTML comments
            comment_line = _ID_RE.sub(
                lambda m: f"<!-- #id:{m.group(1)}:{m.group(2)}:{m.group(3)} -->",
                raw,
            )
            comment_line = _NOLABEL_RE.sub("", comment_line)
            comment_line = _NOREF_RE.sub("", comment_line)
            if not noref:
                comment_line = _resolve_refs(comment_line, resolved_map)
                comment_line = _resolve_vars(comment_line, vars_map)
            output.append(comment_line + _ending(line))
            i += 1

            # Lookahead: find heading within 0–2 blank lines
            pending: list[str] = []
            blanks = 0
            heading_found = False

            while i < len(lines) and blanks < 3:
                peek = lines[i]
                peek_raw = peek.rstrip("\n\r").rstrip()

                if peek_raw == "":
                    pending.append(peek)
                    blanks += 1
                    i += 1
                elif _HEADING_RE.match(peek_raw):
                    m0 = id_matches[0]
                    full_id = f"{m0.group(1)}:{m0.group(2)}:{m0.group(3)}"
                    output.extend(pending)
                    if apply_title_labels and not nolabel:
                        labeled = _apply_label(peek, full_id, m0.group(1), resolved_map)
                        if noref:
                            output.append(labeled)
                        else:
                            resolved = _resolve_refs(labeled, resolved_map)
                            output.append(_resolve_vars(resolved, vars_map))
                    else:
                        if noref:
                            output.append(peek)
                        else:
                            resolved = _resolve_refs(peek, resolved_map)
                            output.append(_resolve_vars(resolved, vars_map))
                    heading_found = True
                    i += 1
                    break
                else:
                    break  # non-blank, non-heading line → stop lookahead

            if not heading_found:
                output.extend(pending)

        elif _SECTIONLIST_RE.search(raw):
            # セクション一覧マーカーを展開する（生成物は resolved の label 済みなので
            # 追加のref/var解決は不要）。
            output.append(
                _expand_sectionlist(line, current_chapter_full_id, entries_in_order)
            )
            i += 1

        else:
            resolved = _resolve_refs(line, resolved_map)
            output.append(_resolve_vars(resolved, vars_map))
            i += 1

    return "".join(output)


# ── helpers ────────────────────────────────────────────────────────────────


def _sections_for_chapter(
    entries_in_order: list[dict], chapter_full_id: str
) -> list[dict]:
    """*chapter_full_id* 直後から次の chapter 手前までの section エントリを文書順で返す。

    番号の前置ではなく文書順のグルーピングで判定するため、番号方式に依存しない。
    """
    result: list[dict] = []
    started = False
    for e in entries_in_order:
        if not started:
            if e.get("full_id") == chapter_full_id:
                started = True
            continue
        id_type = e.get("identifier_type")
        if id_type == "chapter":
            break  # 次の chapter に到達したら終了
        if id_type == "section":
            result.append(e)
    return result


def _render_sectionlist(chapter_full_id: str, entries_in_order: list[dict]) -> str:
    """chapter のセクション一覧を Markdown 箇条書き（``- label``）で返す。

    label（例 ``2.1) 概要``）を用い、番号無効時は title にフォールバックする。
    """
    lines: list[str] = []
    for e in _sections_for_chapter(entries_in_order, chapter_full_id):
        text = e.get("label") or e.get("title") or ""
        lines.append(f"- {text}")
    return "\n".join(lines)


def _expand_sectionlist(
    line: str, current_chapter_full_id: str | None, entries_in_order: list[dict]
) -> str:
    """行中の {{sectionlist}} / {{sectionlist:chapter:PART:LOCAL}} を一覧に置換する。"""
    end = _ending(line)

    def replace(m: re.Match) -> str:
        if m.group(1):  # 明示形: chapter を full_id で指定
            chapter_full_id = f"{m.group(1)}:{m.group(2)}:{m.group(3)}"
        else:  # 引数なし: 現在の chapter
            chapter_full_id = current_chapter_full_id
        if not chapter_full_id:
            logging.warning(
                "{{sectionlist}}: 直前に chapter が無く現在の章を特定できません — 空に置換します"
            )
            return ""
        return _render_sectionlist(chapter_full_id, entries_in_order)

    return _SECTIONLIST_RE.sub(replace, line.rstrip("\n\r")) + end


def _ending(line: str) -> str:
    if line.endswith("\r\n"):
        return "\r\n"
    if line.endswith("\n"):
        return "\n"
    return ""


def _apply_label(
    heading_line: str,
    full_id: str,
    id_type: str,
    resolved_map: dict[str, dict],
) -> str:
    """Replace the title part of *heading_line* with the label from *resolved_map*."""
    raw = heading_line.rstrip("\n\r")
    m = _HEADING_RE.match(raw)
    if not m:
        return heading_line

    hashes = m.group(1)
    level = len(hashes)
    end = _ending(heading_line)

    expected = _EXPECTED_HEADING_LEVEL.get(id_type)
    if expected is not None and level != expected:
        logging.warning(
            "Heading level mismatch for %s (full_id=%s): expected %s, got %s",
            id_type, full_id, "#" * expected, hashes,
        )

    entry = resolved_map.get(full_id)
    if entry is None:
        logging.warning("No resolved entry for full_id=%s — heading unchanged", full_id)
        return heading_line

    return f"{hashes} {entry.get('label', '')}{end}"


def _resolve_vars(line: str, vars_map: dict[str, str] | None) -> str:
    """Replace {{v:NAME}} with the value from *vars_map*."""
    if not vars_map:
        return line

    def replace(m: re.Match) -> str:
        name = m.group(1)
        if name not in vars_map:
            logging.warning("Undefined variable {{v:%s}} — left as-is", name)
            return m.group(0)
        return str(vars_map[name])

    return _VAR_RE.sub(replace, line)


def _resolve_refs(line: str, resolved_map: dict[str, dict]) -> str:
    """Replace {{num:}}, {{title:}}, {{label:}}, {{rawtitle:}} references by FULL_ID."""
    def replace(m: re.Match) -> str:
        ref_type, full_id = m.group(1), m.group(2)
        entry = resolved_map.get(full_id)
        if entry is None:
            logging.warning(
                "No resolved entry for reference {{%s:%s}} — left as-is",
                ref_type, full_id,
            )
            return m.group(0)
        if ref_type == "num":
            return entry.get("number", "")
        if ref_type == "title":
            return entry.get("title", "")
        if ref_type == "rawtitle":
            return entry.get("rawtitle", "")
        if ref_type == "label":
            return entry.get("label", "")
        return m.group(0)

    return _REF_RE.sub(replace, line)
