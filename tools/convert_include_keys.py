"""旧書式の ``!include`` / ``!constants`` を YAML キー ``_include:`` / ``_constants:`` へ書き換える。

YAML を読み書きするとコメントが失われるため、行単位のテキスト置換で変換する。

    !constants ../constants.toml        →   _constants: ../constants.toml
    pandoc:                                 pandoc:
      !include ../pandoc.yaml           →     _include: ../pandoc.yaml
      engine: typst                           engine: typst
    cover: !include cover.yaml          →   cover: {_include: cover.yaml}

対象:
  - .yaml / .yml はファイル全体、.md では ```yaml フェンス内だけを変換する
  - コメント行・行末コメント内の ``!include`` は対象外

意味が変わりうる箇所は変換したうえで警告する（手で確認すること）:
  - 同じマッピングに ``!include`` が複数ある → ``_include: [a, b]`` にまとめる
  - ``!include`` より前に兄弟キーがある → 旧書式では読み込み先が後勝ちで上書き
    していたが、``_include`` では兄弟キーが常に優先される
  - トップレベルの ``!constants`` が複数ある → ``_constants: [a, b]`` にまとめる

使い方:
    python tools/convert_include_keys.py [--check] FILE...

--check は書き換えずに変換対象のファイル名だけを表示する。
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

_CONSTANTS_RE = re.compile(r"^!constants[ \t]+(?P<p>\S+?)[ \t]*(?P<c>#.*)?$")
_STANDALONE_RE = re.compile(r"^(?P<ind>[ \t]*)!include[ \t]+(?P<p>\S+?)[ \t]*(?P<c>#.*)?$")
_INLINE_RE = re.compile(r"!include[ \t]+(?P<p>\S+?)(?=[ \t]*(?:#.*)?$)")


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" \t"))


def _is_content(line: str) -> bool:
    s = line.strip()
    return bool(s) and not s.startswith("#")


def _comment_start(s: str) -> int:
    for i, c in enumerate(s):
        if c == "#" and (i == 0 or s[i - 1] in (" ", "\t")):
            return i
    return len(s)


def _with_comment(body: str, comment: str | None) -> str:
    return f"{body}  {comment}" if comment else body


def _convert_lines(lines: list[str], warn: list[str], label: str, offset: int = 0) -> list[str]:
    out = list(lines)
    # 同じマッピング（同じ親・同じインデント）に属する standalone !include を束ねる
    groups: dict[tuple[int, int], list[int]] = {}
    for i, line in enumerate(lines):
        m = _STANDALONE_RE.match(line)
        if not m:
            continue
        ind = _indent(line)
        parent = -1
        for j in range(i - 1, -1, -1):
            if _is_content(lines[j]) and _indent(lines[j]) < ind:
                parent = j
                break
        groups.setdefault((parent, ind), []).append(i)

    for (parent, ind), idxs in groups.items():
        last = idxs[-1]
        if any(_is_content(lines[j]) and _indent(lines[j]) == ind and not _STANDALONE_RE.match(lines[j])
               for j in range(parent + 1, last)):
            warn.append(
                f"{label}:{offset + last + 1}: !include より前に兄弟キーがあります"
                "（旧書式は読み込み先で上書き、_include では兄弟キーが優先）"
            )
        ms = [_STANDALONE_RE.match(lines[i]) for i in idxs]
        ind = ms[0].group("ind")
        if len(idxs) == 1:
            out[idxs[0]] = _with_comment(f"{ind}_include: {ms[0].group('p')}", ms[0].group("c"))
            continue
        warn.append(f"{label}:{offset + idxs[0] + 1}: 同じマッピングの !include {len(idxs)} 件を _include のリストにまとめました")
        out[idxs[0]] = "\n".join(
            [f"{ind}_include:"] + [_with_comment(f"{ind}  - {m.group('p')}", m.group("c")) for m in ms]
        )
        # 後続の !include 行は先頭行の下へ移したので、元の位置からは消す
        for i in idxs[1:]:
            out[i] = None  # type: ignore[call-overload]

    consts = [i for i, line in enumerate(lines) if _CONSTANTS_RE.match(line)]
    if consts:
        ms = [_CONSTANTS_RE.match(lines[i]) for i in consts]
        if len(consts) == 1:
            out[consts[0]] = _with_comment(f"_constants: {ms[0].group('p')}", ms[0].group("c"))
        else:
            warn.append(f"{label}:{offset + consts[0] + 1}: !constants {len(consts)} 件を _constants のリストにまとめました")
            out[consts[0]] = "\n".join(["_constants:"] + [_with_comment(f"  - {m.group('p')}", m.group("c")) for m in ms])
            for i in consts[1:]:
                out[i] = None  # type: ignore[call-overload]

    for i, line in enumerate(lines):
        if out[i] is not line or not _is_content(line):
            continue
        cut = _comment_start(line)
        body = line[:cut]
        m = _INLINE_RE.search(body)
        if m:
            out[i] = body[: m.start()] + "{_include: " + m.group("p") + "}" + body[m.end():] + line[cut:]
    return [ln for ln in out if ln is not None]


def convert_text(text: str, kind: str, label: str = "", warn: list[str] | None = None) -> str:
    """*kind* は "yaml" / "md"。"""
    warn = warn if warn is not None else []
    lines = text.split("\n")
    if kind == "yaml":
        return "\n".join(_convert_lines(lines, warn, label))
    out: list[str] = []
    fence: list[str] | None = None
    start = 0
    for n, ln in enumerate(lines):
        s = ln.strip()
        if fence is None:
            out.append(ln)
            if s.startswith("```yaml") or s.startswith("```yml"):
                fence, start = [], n + 1
        elif s.startswith("```"):
            out.extend(_convert_lines(fence, warn, label, start))
            out.append(ln)
            fence = None
        else:
            fence.append(ln)
    if fence is not None:
        out.extend(fence)
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="+", type=Path)
    ap.add_argument("--check", action="store_true", help="書き換えずに対象ファイルを表示する")
    ns = ap.parse_args(argv)
    warn: list[str] = []
    changed = 0
    for path in ns.files:
        raw = path.read_bytes().decode("utf-8")
        crlf = "\r\n" in raw
        text = raw.replace("\r\n", "\n")
        kind = "md" if path.suffix.lower() == ".md" else "yaml"
        new = convert_text(text, kind, str(path), warn)
        if crlf:  # 改行コードは元のファイルに合わせる
            new, text = new.replace("\n", "\r\n"), raw
        if new != text:
            changed += 1
            print(f"{'変換対象' if ns.check else '変換'}: {path}")
            if not ns.check:
                path.write_bytes(new.encode("utf-8"))
    for w in warn:
        print(f"警告: {w}", file=sys.stderr)
    print(f"{changed} ファイル{'が対象です' if ns.check else 'を変換しました'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
