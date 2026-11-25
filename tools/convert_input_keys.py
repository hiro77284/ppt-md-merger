"""レシピの input セクションを fragment / source に書き換える。

input セクションは廃止し、中身を目的別の 2 つのセクションに分けた（docs/recipe_key_reference.md）。

    input:                      fragment:
      dirs: [...]        →        dirs: [...]
      imagesdir: [...]          source:
      cropsrc: {...}              cropimagedirs: [...]
                                  cropsrc: {...}

YAML を読み書きするとコメントが失われるため、行単位のテキスト置換で変換する（キーの行とその値・
直前のコメント行をまとめて動かし、中身には触らない）。recipe version は変えない。

次の場合は書き換えずに理由を表示する（手で直す）:

- input.mddir / input.pptxdir がある（廃止。fragment.dirs に書く）
- input の中に上の 3 つ以外のキー（``_include`` など）がある、または ``input: {...}`` のフロー書式
- すでに fragment: / source: セクションがある

使い方:
    python tools/convert_input_keys.py [--check] [--no-backup] RECIPE...

--check は書き換えずに変更内容だけを表示する。既定では書き換える前のファイルを
``<名前>.before_input_keys`` として残す（--no-backup で残さない）。
"""

from __future__ import annotations

import argparse
import difflib
import re
import shutil
import sys
from pathlib import Path

_KEY_RE = re.compile(r"^(?P<indent>\s*)(?P<key>[A-Za-z_][\w-]*)\s*:(?P<rest>.*)$")

# 旧キー → (新しいセクション, 新しいキー)
_MOVES = {
    "dirs": ("fragment", "dirs"),
    "imagesdir": ("source", "cropimagedirs"),
    "cropsrc": ("source", "cropsrc"),
}
_REMOVED = {
    "mddir": "input.mddir は廃止しました。fragment.dirs に手で書き換えてください",
    "pptxdir": "input.pptxdir は廃止しました。fragment.dirs に手で書き換えてください",
}


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _is_blank(line: str) -> bool:
    return not line.strip()


def _is_comment(line: str) -> bool:
    return line.lstrip().startswith("#")


def _top_key(line: str) -> str | None:
    if _is_blank(line) or _is_comment(line) or _indent(line) != 0:
        return None
    m = _KEY_RE.match(line)
    return m.group("key") if m else None


def convert_text(text: str) -> tuple[str, list[str]]:
    """変換後の本文と、変換できなかった理由（空なら変換できた／不要）を返す。"""
    lines = text.splitlines(keepends=True)
    starts = [i for i, ln in enumerate(lines) if _top_key(ln) == "input"]
    if not starts:
        return text, []
    if len(starts) > 1:
        return text, ["input: が複数あります"]
    others = {_top_key(ln) for ln in lines}
    clash = [s for s in ("fragment", "source") if s in others]
    if clash:
        return text, [f"すでに {', '.join(clash)}: セクションがあります。手で統合してください"]

    start = starts[0]
    head = _KEY_RE.match(lines[start])
    rest = head.group("rest").split("#", 1)[0].strip()
    if rest:
        return text, ["input: がフロー書式（同じ行に値）です。手で書き換えてください"]

    # input の範囲: 次の 0 桁目の行（コメント含む）まで。末尾の空行は範囲外に残す。
    end = start + 1
    while end < len(lines) and (_is_blank(lines[end]) or _indent(lines[end]) > 0):
        end += 1
    body_end = end
    while body_end > start + 1 and _is_blank(lines[body_end - 1]):
        body_end -= 1
    body = lines[start + 1:body_end]
    if not body:
        return text, []

    child = min(_indent(ln) for ln in body if not _is_blank(ln) and not _is_comment(ln)) if any(
        not _is_blank(ln) and not _is_comment(ln) for ln in body) else None
    if child is None:
        return text, []

    # 子キーごとのブロック。キーの間のコメント・空行は次のキーの側に付ける
    blocks: list[tuple[str, list[str]]] = []
    pending: list[str] = []
    for ln in body:
        if _is_blank(ln) or _is_comment(ln):
            pending.append(ln)
            continue
        if _indent(ln) == child:
            m = _KEY_RE.match(ln)
            if not m:
                return text, [f"input の中を解釈できません: {ln.strip()}"]
            blocks.append((m.group("key"), pending + [ln]))
        elif _indent(ln) > child and blocks:
            blocks[-1][1].extend(pending + [ln])
        else:
            return text, [f"input の中を解釈できません: {ln.strip()}"]
        pending = []
    if blocks:
        blocks[-1][1].extend(pending)

    errors: list[str] = []
    for key, _ in blocks:
        if key in _REMOVED:
            errors.append(_REMOVED[key])
        elif key not in _MOVES:
            errors.append(f"input.{key} は自動で書き換えられません。手で書き換えてください")
    if errors:
        return text, errors

    def renamed(key: str, blk: list[str]) -> list[str]:
        out = list(blk)
        for i, ln in enumerate(out):
            if not _is_blank(ln) and not _is_comment(ln):
                out[i] = re.sub(r"^(\s*)[A-Za-z_][\w-]*(\s*:)", rf"\g<1>{_MOVES[key][1]}\g<2>", ln, count=1)
                break
        return out

    def strip_trailing_blank(blk: list[str]) -> list[str]:
        while blk and _is_blank(blk[-1]):
            blk = blk[:-1]
        return blk

    nl = "\r\n" if lines[start].endswith("\r\n") else "\n"
    out: list[str] = []
    for section in ("fragment", "source"):
        sec_blocks = [(k, b) for k, b in blocks if _MOVES[k][0] == section]
        if not sec_blocks:
            continue
        if out:
            out.append(nl)
        out.append(f"{section}:{nl}")
        for i, (k, b) in enumerate(sec_blocks):
            b = renamed(k, b)
            if i == 0:
                while b and _is_blank(b[0]):
                    b = b[1:]
            if i == len(sec_blocks) - 1:
                b = strip_trailing_blank(b)
            out.extend(b)
    return "".join(lines[:start] + out + lines[body_end:]), []


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("recipes", nargs="+", type=Path, metavar="RECIPE")
    ap.add_argument("--check", action="store_true", help="書き換えずに変更内容だけを表示する")
    ap.add_argument("--no-backup", action="store_true", help="<名前>.before_input_keys を残さない")
    ns = ap.parse_args(argv)

    failed = False
    for path in ns.recipes:
        try:
            raw = path.read_bytes()
        except OSError as exc:
            print(f"読めません: {path}: {exc}", file=sys.stderr)
            failed = True
            continue
        text = raw.decode("utf-8-sig")
        new, errors = convert_text(text)
        if errors:
            failed = True
            print(f"[skip] {path}", file=sys.stderr)
            for e in errors:
                print(f"  {e}", file=sys.stderr)
            continue
        if new == text:
            print(f"[ok]   {path}（変更なし）")
            continue
        if ns.check:
            print(f"[diff] {path}")
            sys.stdout.writelines(difflib.unified_diff(
                text.splitlines(keepends=True), new.splitlines(keepends=True),
                fromfile=str(path), tofile=str(path) + " (converted)",
            ))
            continue
        if not ns.no_backup:
            shutil.copy2(path, path.with_name(path.name + ".before_input_keys"))
        bom = raw.startswith(b"\xef\xbb\xbf")
        path.write_bytes((b"\xef\xbb\xbf" if bom else b"") + new.encode("utf-8"))
        print(f"[done] {path}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
