from __future__ import annotations

from pathlib import Path


def replace_slide_placeholders(text: str, pptx_path: Path, slide_title: str, slide_idx: int) -> str:
    """Replace <__TITLE__>, <__FILENAME__>, <__BASEFILENAME__>, <__SLIDENUM__> in *text*."""
    text = text.replace("<__TITLE__>", slide_title)
    text = text.replace("<__FILENAME__>", pptx_path.name)
    text = text.replace("<__BASEFILENAME__>", pptx_path.stem)
    text = text.replace("<__SLIDENUM__>", str(slide_idx))
    return text


def _frontmatter_end(lines: list[str]) -> int:
    """先頭の YAML frontmatter（``---`` … ``---``）の閉じ行のインデックスを返す。無ければ -1。

    開始 ``---`` の前には空行と ``<!-- ... -->`` コメント行だけを許容する。
    """
    i = 0
    while i < len(lines) and (lines[i].strip() == "" or (lines[i].strip().startswith("<!--") and lines[i].strip().endswith("-->"))):
        i += 1
    if i >= len(lines) or lines[i].strip() != "---":
        return -1
    for j in range(i + 1, len(lines)):
        if lines[j].strip() == "---":
            return j
    return -1


_SOURCE_MARKER_PREFIX = "<!-- source:"


def _is_leadin(stripped: str) -> bool:
    """frontmatter の開始 ``---`` の前に来てよい行（空行・1 行の HTML コメント）か。"""
    return stripped == "" or (stripped.startswith("<!--") and stripped.endswith("-->"))


def strip_frontmatter(text: str) -> tuple[str, int]:
    """MD から YAML frontmatter ブロックを取り除き、(本文, 取り除いた数) を返す。

    対象は「文書の先頭」と「``<!-- source: ... -->`` 行（merge が各ファイル・include の
    先頭に挿入する）の直後」に現れる ``---`` … ``---`` ブロック。開始 ``---`` の前には
    空行と 1 行の HTML コメント（``<!-- md_merge_rawtitle: ... -->`` 等）を許容する。
    中身が YAML のマッピングとして読めるものだけを frontmatter とみなす（本文の水平線
    ``---`` を誤って消さないため）。コメント行・空行はそのまま残し、ブロックは空行 1 行に置き換える。

    pandoc は frontmatter の直前に空行が無いとメタデータとして読まず本文に出してしまう
    （merge 後は ``<!-- source: -->`` などのコメントが直前に来る）うえ、2 ファイル目以降の
    frontmatter は文書の途中に来るため、PDF 等の出力前にここで落とす。
    """
    import yaml  # 遅延 import（_filters は軽量に保つ）

    lines = text.splitlines(keepends=True)
    out: list[str] = []
    removed = 0
    seeking = True  # 文書先頭 or source マーカー直後で、まだ開始 --- を探している
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        stripped = line.strip()
        if stripped.startswith(_SOURCE_MARKER_PREFIX) and stripped.endswith("-->"):
            out.append(line)
            seeking = True
            i += 1
            continue
        if seeking:
            if stripped == "---":
                end = next((j for j in range(i + 1, n) if lines[j].strip() == "---"), -1)
                if end >= 0:
                    try:
                        data = yaml.safe_load("".join(lines[i + 1 : end]))
                    except yaml.YAMLError:
                        data = None
                    if isinstance(data, dict) and data:
                        removed += 1
                        out.append("\n")  # 前後の行がくっついて段落化しないよう空行で置き換える
                        i = end + 1
                        seeking = False
                        continue
                seeking = False
            elif not _is_leadin(stripped):
                seeking = False
        out.append(line)
        i += 1
    return "".join(out), removed


def escape_backslash_smart(text: str) -> str:
    """LaTeX 向けに ``\\`` と ``&`` をエスケープする。

    コードブロック・インラインコードの中は触らない。先頭の YAML frontmatter も触らない
    （frontmatter は pandoc がメタデータとして読み、transfer / notecomexport が title 等を
    そのまま使うため、``\\&`` にすると Web 側にバックスラッシュが漏れる）。
    """
    lines = text.splitlines()
    processed_lines = []

    fm_end = _frontmatter_end(lines)
    if fm_end >= 0:
        processed_lines.extend(lines[: fm_end + 1])
        lines = lines[fm_end + 1 :]

    # 状態を管理するフラグ（あらゆるコードブロックを対象にする）
    in_code_block = False

    for line in lines:
        # --- 1. コードブロックの開始・終了の判定 ---
        # 行頭が ``` で始まっている場合（```{=latex} も ``` もすべてキャッチ）
        if line.strip().startswith("```"):
            # スイッチを反転させる（FalseならTrueに、TrueならFalseに）
            in_code_block = not in_code_block
            processed_lines.append(line)
            continue
            
        # --- 2. 保護エリア（何らかのコードブロック内）の処理 ---
        if in_code_block:
            # コードブロックの中（無名、latex問わず）は一切触らず、そのままスルー
            processed_lines.append(line)
        else:
            # --- 3. 通常エリアの処理（インラインコードを保護しつつ \ や & を置換） ---
            parts = line.split("`")
            for i in range(len(parts)):
                if i % 2 == 0:
                    # インラインコードの「外側」だけ、特殊文字を安全に置換
                    parts[i] = parts[i].replace("\\", "\\\\")
                    parts[i] = parts[i].replace("&", "\\&")
            
            processed_line = "`".join(parts)
            processed_lines.append(processed_line)
            
    return "\n".join(processed_lines)
