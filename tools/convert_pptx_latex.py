#!/usr/bin/env python3
r"""原稿 pptx のノート内 ```{=latex}...``` を semantic コードへ変換する（手動起動ツール）。

対応パターン（これらだけを含むブロックのみ変換。未対応を含むブロックは温存）:
    \begin{center} / \end{center}              -> ::: {.center} / :::
    \begin{widequote}[..,left=6mm] / \end{...} -> ::: {.widequote left=6mm} / :::
                                                  （key=value の属性のみ残し、内部 style 名は破棄）
    \vfill                                      -> {{vfill}}
    \newpage / \clearpage                       -> {{pagebreak}}
    \par\vspace{N\baselineskip}                 -> {{vspace:N}}

コードフェンス外の「素の生 latex 行」も変換する（```{=latex}``` ブロック外に直接
書かれた \par\vspace{N\baselineskip} / \vfill / \newpage 等。前後を空行で分離して
リーフ段落にする。div フェンスや mm 単位 vspace 等の bespoke は温存）。
行末の \hfill (ラベル) は [ラベル]{.rightlabel} に変換する。

また {{v:TEX_*}} 変数も semantic リーフ記法へ変換する:
    {{v:TEX_VFILL}}          -> {{vfill}}
    {{v:TEX_NEWPAGE}}        -> {{pagebreak}}
    {{v:TEX_VFILL_NEWPAGE}}  -> {{vfill}} + {{pagebreak}}
    {{v:TEX_NLINE_SKIP}}     -> {{vspace:N}}  （TEX_1LINE_SKIP, TEX_2LINE_SKIP, ...）

使い方:
    python tools/convert_pptx_latex.py <pptx-file-or-folder> [--dry-run] [--no-backup]
      --dry-run   : 書き換えず、変換予定と残 unknown を表示するだけ
      --no-backup : バックアップを作らない（既定はファイルごとに _pptx_latex_bak/ へ退避）

出力の最後に「未対応の {=latex} が残ったファイル一覧」を表示する。
依存: python-pptx
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

from pptx import Presentation

BLOCK_RE = re.compile(r'^```\{=latex\}[ \t]*\r?\n([\s\S]*?)^```[ \t]*$', re.MULTILINE)
VSPACE_RE = re.compile(r'^\\par\\vspace\{([\d.]+)\\baselineskip\}$')
WQ_BEGIN_RE = re.compile(r'^\\begin\{widequote\}(?:\[([^\]]*)\])?$')

# {{v:TEX_*}} 変数 -> semantic リーフ記法（原稿では全て行独立・空行分離で使われる）
NLINE_RE = re.compile(r'\{\{v:TEX_(\d+)LINE_SKIP\}\}')
LEFTOVER_TEX_RE = re.compile(r'\{\{v:TEX_[A-Za-z0-9_]+\}\}')

# 行末の \hfill (ラベル) -> [ラベル]{.rightlabel}（右寄せラベル span）
HFILL_RE = re.compile(r'[ \t]*\\hfill[ \t]*(\S.*?)[ \t]*$', re.MULTILINE)


def conv_line(l: str):
    """1 行の raw latex を semantic へ。未対応は None。"""
    if l == '\\begin{center}':
        return '::: {.center}'
    if l == '\\end{center}':
        return ':::'
    if l == '\\vfill':
        return '{{vfill}}'
    if l in ('\\newpage', '\\clearpage'):
        return '{{pagebreak}}'
    m = VSPACE_RE.match(l)
    if m:
        return '{{vspace:%s}}' % m.group(1)
    mb = WQ_BEGIN_RE.match(l)
    if mb:
        opts = mb.group(1) or ''
        attrs = [t.strip() for t in opts.split(',') if '=' in t]  # key=value のみ残す
        return '::: {.widequote ' + ' '.join(attrs) + '}' if attrs else '::: {.widequote}'
    if l == '\\end{widequote}':
        return ':::'
    return None


def conv_block(body: str):
    """{=latex} ブロック本体を変換。未対応行が 1 つでもあれば None（＝温存）。"""
    out = []
    for raw in body.splitlines():
        l = raw.strip()
        if not l:
            continue
        c = conv_line(l)
        if c is None:
            return None
        out.append(c)
    # 1 行ずつ独立段落にする（リーフ記法は段落全体がマーカー 1 個のときだけ lower され、
    # div フェンスも直前が段落だと段落の続きとして読まれる）
    return '\n\n'.join(out) if out else None


# PowerPoint ノートの段落内改行（Shift+Enter）は \v。直後のフェンスは行頭にないので
# BLOCK_RE に当たらず、pandoc もフェンスとして読まない。段落区切りに直してから変換する。
SOFTBREAK_FENCE_RE = re.compile(r'\v(?=```)')


def transform(text: str) -> str:
    text = SOFTBREAK_FENCE_RE.sub('\n', text)

    def repl(m):
        c = conv_block(m.group(1))
        if c is None:
            return m.group(0)
        # 前後の段落とくっつかないよう空行で分離する
        before = text[:m.start()]
        after = text[m.end():]
        if before and not before.endswith('\n\n'):
            c = '\n' + c
        if after.startswith('\n') and not after.startswith('\n\n'):
            c = c + '\n'
        return c
    return BLOCK_RE.sub(repl, text)


def transform_vars(text: str) -> str:
    """{{v:TEX_*}} 変数を semantic リーフ記法へ。

    TEX_VFILL -> {{vfill}} / TEX_NEWPAGE -> {{pagebreak}} /
    TEX_VFILL_NEWPAGE -> {{vfill}} + 空行 + {{pagebreak}} /
    TEX_NLINE_SKIP -> {{vspace:N}}（N は任意の整数）。
    原稿では各変数が空行で段落分離されているため、単純置換で標準の leaf 段落になる。
    """
    text = text.replace('{{v:TEX_VFILL_NEWPAGE}}', '{{vfill}}\n\n{{pagebreak}}')
    text = text.replace('{{v:TEX_VFILL}}', '{{vfill}}')
    text = text.replace('{{v:TEX_NEWPAGE}}', '{{pagebreak}}')
    text = NLINE_RE.sub(lambda m: '{{vspace:%s}}' % m.group(1), text)
    return text


def transform_hfill(text: str) -> str:
    """行末の ``…\\hfill (ラベル)`` を ``… [(ラベル)]{.rightlabel}`` に変換する。"""
    return HFILL_RE.sub(lambda m: ' [' + m.group(1) + ']{.rightlabel}', text)


def transform_bare(text: str) -> str:
    """コードフェンス外の「素の生 latex 行」を semantic リーフ記法へ変換する。

    ``\\par\\vspace{N\\baselineskip}`` / ``\\vfill`` / ``\\newpage`` 等（conv_line が
    認識し、かつ結果がリーフマーカー ``{{...}}`` になるもののみ）を変換する。div フェンス
    （center/widequote）は対ペアが必要なため素の行では扱わない。```...``` フェンス内
    （温存された {=latex} ブロック等）は触らない。リーフマーカーが独立段落になるよう、
    前後を空行で分離する。
    """
    lines = text.split('\n')
    out: list[str] = []
    in_fence = False
    n = len(lines)
    for i, line in enumerate(lines):
        s = line.strip()
        if s.startswith('```'):
            in_fence = not in_fence
            out.append(line)
            continue
        if not in_fence and s.startswith('\\'):
            c = conv_line(s)
            if c is not None and c.startswith('{{'):
                if out and out[-1].strip() != '':   # 前が非空 → 空行を挿入
                    out.append('')
                out.append(c)
                nxt = lines[i + 1].strip() if i + 1 < n else ''
                if nxt != '':                        # 次が非空 → 空行を挿入
                    out.append('')
                continue
        out.append(line)
    return '\n'.join(out)


def remaining_unknowns(text: str) -> set[str]:
    """変換後テキストに残る {=latex} ブロック内の非空行（未対応パターン）を集める。"""
    u = set()
    for m in BLOCK_RE.finditer(text):
        for raw in m.group(1).splitlines():
            l = raw.strip()
            if l:
                u.add(l)
    return u


def set_note(tf, text: str) -> None:
    """1 行 = 1 段落で書き戻す（tf.text が \n 連結で往復するため構造保持）。"""
    tf.clear()
    lines = text.split('\n')
    tf.paragraphs[0].text = lines[0]
    for ln in lines[1:]:
        tf.add_paragraph().text = ln


def process_file(path: Path, dry_run: bool, backup: bool):
    """1 ファイルを処理。(converted_blocks, remaining:set, changed, leftover_vars:set) を返す。"""
    prs = Presentation(str(path))
    changed = False
    converted = 0
    remaining: set[str] = set()
    leftover_vars: set[str] = set()
    updates = []  # (tf, new_text)
    for slide in prs.slides:
        if not slide.has_notes_slide:
            continue
        tf = slide.notes_slide.notes_text_frame
        old = tf.text or ""
        new = transform_bare(transform_hfill(transform_vars(transform(old))))
        converted += (old.count("{=latex}") - new.count("{=latex}")) // 2  # 2 フェンス=1 ブロック
        remaining |= remaining_unknowns(new)          # 残る未対応 {=latex}（変換有無に関わらず集計）
        leftover_vars |= set(LEFTOVER_TEX_RE.findall(new))  # 変換されず残った TEX 変数
        if new != old:
            changed = True
            updates.append((tf, new))
    if changed and not dry_run:
        if backup:
            bak_dir = path.parent / "_pptx_latex_bak"
            bak_dir.mkdir(exist_ok=True)
            bak = bak_dir / path.name
            if not bak.exists():  # 最初の原本のみ保存
                shutil.copy(str(path), str(bak))
        for tf, new in updates:
            set_note(tf, new)
        prs.save(str(path))
    return converted, remaining, changed, leftover_vars


def main() -> int:
    ap = argparse.ArgumentParser(description="pptx ノートの {=latex} を semantic へ変換")
    ap.add_argument("path", help="pptx ファイル、またはフォルダ（*.pptx を走査）")
    ap.add_argument("--dry-run", action="store_true", help="書き換えず表示のみ")
    ap.add_argument("--no-backup", action="store_true", help="バックアップを作らない")
    args = ap.parse_args()

    root = Path(args.path)
    if root.is_dir():
        targets = sorted(p for p in root.glob("*.pptx") if not p.name.startswith("~$"))
    elif root.is_file():
        targets = [root]
    else:
        print(f"パスが見つかりません: {root}", file=sys.stderr)
        return 2

    total_conv = 0
    files_with_remaining: dict[str, set[str]] = {}
    files_with_leftover_vars: dict[str, set[str]] = {}
    changed_files = []
    for p in targets:
        try:
            conv, remaining, changed, leftover_vars = process_file(p, args.dry_run, not args.no_backup)
        except Exception as e:
            print(f"[skip] {p.name}: {e}")
            continue
        total_conv += conv
        if changed:
            changed_files.append(p.name)
        if remaining:
            files_with_remaining[p.name] = remaining
        if leftover_vars:
            files_with_leftover_vars[p.name] = leftover_vars

    mode = "（DRY-RUN 変更なし）" if args.dry_run else ""
    print(f"対象 {len(targets)} ファイル / 変換したブロック概算 {total_conv} / "
          f"{'変換予定' if args.dry_run else '変換した'}ファイル {len(changed_files)} {mode}")

    if files_with_remaining:
        print(f"\n=== 未対応 {{=latex}} が残るファイル（{len(files_with_remaining)} 件）===")
        for name in sorted(files_with_remaining):
            print(f"  {name}")
    else:
        print("\n未対応の {=latex} は残っていません。")

    if files_with_leftover_vars:
        print(f"\n=== 未対応の {{{{v:TEX_*}}}} 変数が残るファイル ===")
        for name in sorted(files_with_leftover_vars):
            print(f"  {name}: {', '.join(sorted(files_with_leftover_vars[name]))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
