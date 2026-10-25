"""version 1 レシピ（operation 記法）を version 2（操作キー記法）へ書き換える。

YAML を読み書きするとコメントが失われるため、行単位のテキスト置換で変換する。

    - operation: insertpptx          →   - insertpptx: a.pptx
      pptxfilename: a.pptx                 slides: 2-5
      slides: 2-5

対象:
  - ``- operation: X`` で始まる procedure 要素（コメント内の要素は対象外）
  - トップレベルの ``version: 1`` → ``version: 2``（.yaml のみ）
  - .md では ```yaml フェンス内の要素だけを変換する
  - .toml（!constants ファイル）では複数行定数内の要素を変換する。定数を共有する
    レシピはすべて同じ version にそろえること

使い方:
    python tools/convert_procedure_v2.py [--check] FILE...

--check は書き換えずに変換対象のファイル名だけを表示する。
operation 省略（暗黙の insertpptx）要素は変換しないので、警告を見て手で直すこと。
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

_PRIMARY = {
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

_HEAD_RE = re.compile(r"^(?P<ind>[ \t]*)- operation:[ \t]*(?P<op>[A-Za-z_]+)[ \t]*(?P<c>#.*)?$")
_VERSION_RE = re.compile(r"^version:[ \t]*1([ \t]*(?:#.*)?)$")
_IMPLICIT_RE = re.compile(r"^[ \t]*- pptxfilename:")


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" \t"))


def _convert_lines(lines: list[str], warn: list[str], label: str, offset: int = 0) -> list[str]:
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        m = _HEAD_RE.match(line)
        if not m:
            if _IMPLICIT_RE.match(line):
                warn.append(f"{label}:{offset + i + 1}: operation 省略の要素（手で - insertpptx: に直してください）")
            out.append(line)
            i += 1
            continue
        ind, op, comment = m.group("ind"), m.group("op"), m.group("c")
        key_ind = len(ind) + 2
        # 要素の続き行（空行または浅いインデントで終わる）
        j = i + 1
        while j < len(lines) and lines[j].strip() and _indent(lines[j]) >= key_ind:
            j += 1
        body = lines[i + 1:j]
        primary = _PRIMARY.get(op)
        if op not in _PRIMARY:
            warn.append(f"{label}:{offset + i + 1}: 未知の operation {op!r}（変換しません）")
            out.extend(lines[i:j])
            i = j
            continue
        rest = None
        if primary is not None:
            pm = re.compile(rf"^[ \t]{{{key_ind}}}{re.escape(primary)}:(?P<rest>.*)$")
            for k, bl in enumerate(body):
                if _indent(bl) == key_ind:
                    mm = pm.match(bl)
                    if mm:
                        rest = mm.group("rest")
                        del body[k]
                        break
            if rest is None:
                warn.append(f"{label}:{offset + i + 1}: {op} に {primary} がありません（- {op}: のまま出力）")
                rest = ""
            has_comment = "#" in rest and re.search(r"(^|[ \t])#", rest)
            if comment and has_comment:
                out.append(f"{ind}{comment}")
                head = f"{ind}- {op}:{rest}"
            elif comment:
                head = f"{ind}- {op}:{rest.rstrip()}  {comment}"
            else:
                head = f"{ind}- {op}:{rest}"
        else:
            # 兄弟キー（description 等）があればマッピング（- op:）、なければ文字列（- op）
            colon = ":" if any(bl.strip() and not bl.lstrip().startswith("#") for bl in body) else ""
            head = f"{ind}- {op}{colon}" + (f"  {comment}" if comment else "")
        out.append(head.rstrip())
        out.extend(body)
        i = j
    return out


def convert_text(text: str, kind: str, label: str = "", warn: list[str] | None = None) -> str:
    """*kind* は "yaml" / "md" / "toml"。"""
    warn = warn if warn is not None else []
    lines = text.split("\n")
    if kind == "toml":  # !constants の複数行定数に書かれた procedure 要素
        return "\n".join(_convert_lines(lines, warn, label))
    if kind == "yaml":
        lines = [(_VERSION_RE.sub(r"version: 2\1", ln)) for ln in lines]
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
            fence = [(_VERSION_RE.sub(r"version: 2\1", f)) for f in fence]
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
        kind = {".md": "md", ".toml": "toml"}.get(path.suffix.lower(), "yaml")
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
