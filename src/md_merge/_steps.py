"""アニメーションのステップ（``export-image-step``）まわりの共通処理。

* ``export-image-step`` の書式解析（pptimgexport と pptmdexport で共用）
* pptx の ``p:timing`` からクリック数（＝最終ステップ番号）をオフラインで数える
* ``{{BLOCK:MD}}`` 内の ``<!-- #steps -->`` … ``<!-- /steps -->`` セクションで、
  画像パスの ``[all]`` 等を実際に書き出されるステップ番号へ行ごと展開する
"""
from __future__ import annotations

import logging
import re
from pathlib import PurePosixPath

STEP_PLACEHOLDER = "<__STEP__>"
STEP_ALL = "all"
STEP_LAST = "last"
_STEP_ITEM_RE = re.compile(r"^(\d+)(?:\s*-\s*(\d+))?$")

_P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"

# <!-- #steps --> / <!-- /steps --> は単独行で書く
_STEPS_OPEN_RE = re.compile(r"^\s*<!--\s*#steps\s*-->\s*$")
_STEPS_CLOSE_RE = re.compile(r"^\s*<!--\s*/steps\s*-->\s*$")
# 画像・リンクの行き先 ](...) の中身
_LINK_DEST_RE = re.compile(r"\]\(([^)]*)\)")
# 行き先の中のステップ指定 [all] / [last] / [0-3, 5]
_STEP_TOKEN_RE = re.compile(r"\[(all|last|\d+(?:\s*-\s*\d+)?(?:\s*,\s*\d+(?:\s*-\s*\d+)?)*)\]")


def parse_step_spec(raw: str) -> list[int] | str | None:
    """``export-image-step`` の値を解釈する。

    戻り値: 空なら None（PDF 経路）、``all`` / ``last`` はその文字列、それ以外は昇順・重複なしの
    ステップ番号リスト（``0-3, 5`` 形式）。書式が不正なら ValueError。
    """
    raw = raw.strip()
    if not raw:
        return None
    if raw.lower() in (STEP_ALL, STEP_LAST):
        return raw.lower()
    steps: set[int] = set()
    for item in raw.split(","):
        m = _STEP_ITEM_RE.match(item.strip())
        if not m:
            raise ValueError(f"ステップ指定を解釈できません: {item.strip()!r}")
        lo = int(m.group(1))
        hi = int(m.group(2)) if m.group(2) is not None else lo
        if hi < lo:
            raise ValueError(f"範囲の向きが逆です: {item.strip()!r}")
        steps.update(range(lo, hi + 1))
    return sorted(steps)


def resolve_steps(spec: list[int] | str, clicks: int) -> list[int]:
    """ステップ指定を、クリック数 *clicks* のスライドで実際に存在するステップ番号へ解決する。"""
    if spec == STEP_ALL:
        return list(range(clicks + 1))
    if spec == STEP_LAST:
        return [clicks]
    return [s for s in spec if s <= clicks]


def count_click_steps(slide) -> int:
    """スライドのクリック数（最終ステップ番号）を ``p:timing`` から数える。

    メインシーケンス（``nodeType="mainSeq"``）内の ``nodeType="clickEffect"`` の数。
    トリガー付きの対話型シーケンスは数えない。PowerPoint の ``GetClickCount()`` と
    同じ値になる（design_pptx_animation_capture.md §5 の実測）。
    """
    el = slide._element
    main_seqs = el.findall(f".//{{{_P_NS}}}timing//{{{_P_NS}}}cTn[@nodeType='mainSeq']")
    return sum(
        len(seq.findall(f".//{{{_P_NS}}}cTn[@nodeType='clickEffect']"))
        for seq in main_seqs
    )


def _norm_path(p: str) -> str:
    return p.strip().replace("\\", "/")


def _find_block(template: str, blocks: list[dict]) -> tuple[dict | None, str]:
    """*template*（``<__STEP__>`` 入りのパス）に対応する IMAGE ブロックを探す。

    パス全体の一致を優先し、無ければファイル名部分の一致で探す。戻り値は
    (ブロック, 見つからない／曖昧なときの理由)。
    """
    t = _norm_path(template)
    exact = [b for b in blocks if b["template"] == t]
    if len(exact) == 1:
        return exact[0], ""
    if len(exact) > 1:
        return None, "同じ export-image の IMAGE ブロックが複数あります"
    name = PurePosixPath(t).name
    by_name = [b for b in blocks if PurePosixPath(b["template"]).name == name]
    if len(by_name) == 1:
        return by_name[0], ""
    if len(by_name) > 1:
        return None, f"ファイル名 {name} に一致する IMAGE ブロックが複数あります（パス全体を export-image と揃えてください）"
    return None, "export-image-step 付きで export-image が一致する IMAGE ブロックがありません"


def _select(spec: list[int] | str, exported: list[int]) -> tuple[list[int], list[int]]:
    """MD 側の指定 *spec* を、書き出されるステップ *exported* に当てはめる。

    戻り値は (展開するステップ, 書き出されないため捨てたステップ)。
    """
    if spec == STEP_ALL:
        return list(exported), []
    if spec == STEP_LAST:
        return exported[-1:], []
    have = set(exported)
    return [s for s in spec if s in have], [s for s in spec if s not in have]


def expand_steps_sections(
    md_text: str,
    image_directives: list[dict[str, str]],
    clicks_fn,
    slide_n: int,
) -> str:
    """``<!-- #steps -->`` … ``<!-- /steps -->`` 内の ``[all]`` 等を行ごと展開する。

    *image_directives* は同じスライドの IMAGE ブロック（プレースホルダー置換済み）、
    *clicks_fn* はそのスライドのクリック数を返す関数（``all`` / ``last`` のときだけ呼ぶ）。
    対応する IMAGE ブロックが見つからない行は警告してそのまま残す。
    """
    lines = md_text.split("\n")
    if not any(_STEPS_OPEN_RE.match(ln) for ln in lines):
        return md_text

    blocks: list[dict] = []
    for meta in image_directives:
        out = (meta.get("export-image") or "").strip()
        try:
            spec = parse_step_spec(meta.get("export-image-step") or "")
        except ValueError:
            continue  # pptimgexport 側で失敗として報告される
        if spec is None or STEP_PLACEHOLDER not in out:
            continue
        blocks.append({"template": _norm_path(out), "spec": spec})

    clicks_cache: list[int] = []

    def exported_steps(spec: list[int] | str) -> list[int]:
        # 数値指定もクリック数を超えた分は pptimgexport で書き出されないので、ここでも除く
        if not clicks_cache:
            clicks_cache.append(clicks_fn())
        return resolve_steps(spec, clicks_cache[0])

    # 閉じていない #steps は展開しない（どこまでが対象か分からないため）
    open_idx: int | None = None
    sections: list[tuple[int, int]] = []
    in_code = False
    for i, ln in enumerate(lines):
        if ln.strip().startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            continue
        if _STEPS_OPEN_RE.match(ln):
            if open_idx is not None:
                logging.warning("スライド %d: <!-- #steps --> が閉じる前に再び現れました（%d 行目）", slide_n, i + 1)
            open_idx = i
        elif _STEPS_CLOSE_RE.match(ln):
            if open_idx is None:
                logging.warning("スライド %d: 対応する <!-- #steps --> の無い <!-- /steps --> です（%d 行目）", slide_n, i + 1)
            else:
                sections.append((open_idx, i))
                open_idx = None
    if open_idx is not None:
        logging.warning("スライド %d: <!-- #steps --> が閉じられていません（%d 行目）。展開しません", slide_n, open_idx + 1)

    in_section = set()
    for a, b in sections:
        in_section.update(range(a + 1, b))

    out: list[str] = []
    for i, ln in enumerate(lines):
        if i not in in_section:
            out.append(ln)
            continue
        hits = [
            (m, t)
            for m in _LINK_DEST_RE.finditer(ln)
            for t in [_STEP_TOKEN_RE.search(m.group(1))]
            if t is not None
        ]
        if not hits:
            out.append(ln)
            continue
        if len(hits) > 1:
            logging.warning("スライド %d: 1 行に展開指定が複数あります。展開しません: %s", slide_n, ln.strip())
            out.append(ln)
            continue
        dest_m, tok_m = hits[0]
        dest = dest_m.group(1)
        template = dest[:tok_m.start()] + STEP_PLACEHOLDER + dest[tok_m.end():]
        block, reason = _find_block(template, blocks)
        if block is None:
            logging.warning("スライド %d: %s: %s", slide_n, reason, dest.strip())
            out.append(ln)
            continue
        md_spec = parse_step_spec(tok_m.group(1))
        exported = exported_steps(block["spec"])
        steps, dropped = _select(md_spec, exported)
        if dropped:
            logging.warning(
                "スライド %d: ステップ %s は書き出されないため展開しません: %s",
                slide_n, ",".join(map(str, dropped)), dest.strip(),
            )
        if not steps:
            logging.warning("スライド %d: 展開するステップがありません: %s", slide_n, dest.strip())
            continue
        dest_start = dest_m.start(1)
        tok_s, tok_e = dest_start + tok_m.start(), dest_start + tok_m.end()
        for s in steps:
            new = ln[:tok_s] + str(s) + ln[tok_e:]
            out.append(new.replace(STEP_PLACEHOLDER, str(s)))
    return "\n".join(out)
