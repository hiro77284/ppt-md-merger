#!/usr/bin/env python3
"""2 つの PDF をページ単位で比較し、差の程度を解析する（手動起動ツール）。

まず全ページの知覚ハッシュ(dHash)でページを対応付け（順序を保った DP アライメント）、
ページの挿入/削除/差し替えがあっても正しく突き合わせる。対応したページ対について:
  - pixdiff : ページを DPI 指定でラスタライズし、グレースケール明度差が閾値を超えた
              ピクセルの割合（レイアウト・見た目の変化。AA ノイズは閾値で無視）
  - textsim : 抽出テキストの difflib 類似度 0.0〜1.0（内容=文字の変化）
  - phash   : dHash の Hamming 距離 0〜64（シフト/スケールに強い大局類似度）
片側にしか無いページは removed（A のみ）/ added（B のみ）として報告する。
差のある対応ページは変化箇所を赤でハイライトした差分画像を保存する。

わずかな平行移動・微小なサイズ違い（レンダリングのジッタ）は実質差が無いので、
--tolerance / --blur（または --fuzzy）で pixdiff の検出を抑制できる。

使い方:
    python tools/pdfdiff.py A.pdf B.pdf [options]

主なオプション:
    --out DIR            差分画像・JSON の出力先（既定: ./pdfdiff_out）
    --dpi N              ラスタライズ DPI（既定 120）
    --pixel-threshold N  ピクセル差とみなす明度差 0-255（既定 24。小さいほど厳しい）
    --tolerance N        平行移動の許容 px。±N のズレは差とみなさない（既定 0）
    --blur R             比較前の Gaussian ぼかし半径。微小なサイズ違い/AA を吸収（既定 0）
    --fuzzy              小さなズレを無視するプリセット（tolerance=2, blur=1.0 相当）
    --no-align           ページ整合をせず index 順（i対i）で比較する
    --align-gap F        整合の gap ペナルティ 0-1。小さいほど挿入/削除に敏感（既定 0.22）
    --save-all           変化の無いページも差分画像を保存する
    --no-images          差分画像を作らない（レポートのみ）
    --json               <out>/report.json に機械可読レポートも書く
    --max-pages N        各 PDF 先頭 N ページのみ対象（デバッグ用）

終了コード: 変化ページ・removed・added のいずれかがあれば 1、完全一致なら 0。
依存: pymupdf(fitz), numpy, Pillow。
"""
from __future__ import annotations

import argparse
import difflib
import json
import sys
from pathlib import Path

try:
    import pymupdf as fitz  # 新しめの PyMuPDF は正式名 pymupdf
except ModuleNotFoundError:
    try:
        import fitz  # 後方互換の別名
    except ModuleNotFoundError:
        sys.stderr.write(
            "エラー: pymupdf(fitz) が見つかりません。\n"
            "pptmdmerge をインストールした Python 環境で実行してください"
            "（pymupdf/numpy/Pillow はその依存に含まれます）。\n"
            f"  実行中の Python : {sys.executable}\n"
            "  対処例          : pip install pymupdf numpy Pillow\n"
            "                    もしくは該当の venv を有効化してから実行\n"
        )
        sys.exit(3)

import numpy as np
from PIL import Image, ImageFilter


# ── ラスタライズ / ピクセル差 ────────────────────────────────────────────────

def render_rgb(page: "fitz.Page", dpi: int) -> np.ndarray:
    """ページを RGB の (H, W, 3) uint8 配列にラスタライズする。"""
    pix = page.get_pixmap(dpi=dpi, colorspace=fitz.csRGB, alpha=False)
    return np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, 3)


def to_gray(arr: np.ndarray) -> np.ndarray:
    return arr[..., 0] * 0.299 + arr[..., 1] * 0.587 + arr[..., 2] * 0.114


def resize_to(arr: np.ndarray, hw: tuple[int, int]) -> np.ndarray:
    h, w = hw
    if arr.shape[:2] == (h, w):
        return arr
    return np.asarray(Image.fromarray(arr).resize((w, h), Image.BILINEAR))


def _shift(a: np.ndarray, dx: int, dy: int) -> np.ndarray:
    """配列を (dx, dy) だけずらす（露出した縁は端ピクセルを複製＝偽の差を作らない）。"""
    h, w = a.shape
    ys = np.clip(np.arange(h) - dy, 0, h - 1)
    xs = np.clip(np.arange(w) - dx, 0, w - 1)
    return a[ys][:, xs]


def _gray_blur(rgb: np.ndarray, blur: float) -> np.ndarray:
    if blur > 0:
        img = Image.fromarray(rgb).convert("L").filter(ImageFilter.GaussianBlur(blur))
        return np.asarray(img, dtype=np.float32)
    return to_gray(rgb).astype(np.float32)


def diff_mask(a_rgb: np.ndarray, b_rgb: np.ndarray, threshold: int,
              tolerance: int = 0, blur: float = 0.0) -> tuple[np.ndarray, float]:
    """A サイズに合わせた明度差マスクと差ピクセル率を返す。

    ``tolerance`` px までの平行移動は差とみなさない（各画素を相手の近傍 ±tolerance と
    照合し、最小差が閾値以下なら一致扱い）。``blur`` で事前ぼかしし微小なサイズ違い・
    アンチエイリアスのゆらぎを吸収する。
    """
    b_fit = resize_to(b_rgb, a_rgb.shape[:2])
    ga = _gray_blur(a_rgb, blur)
    gb = _gray_blur(b_fit, blur)
    best = np.abs(ga - gb)
    for dy in range(-tolerance, tolerance + 1):
        for dx in range(-tolerance, tolerance + 1):
            if dx == 0 and dy == 0:
                continue
            best = np.minimum(best, np.abs(ga - _shift(gb, dx, dy)))
    mask = best > threshold
    return mask, float(mask.mean())


def make_diff_image(a_rgb: np.ndarray, mask: np.ndarray, path: Path) -> None:
    """A を淡色化した背景に、変化ピクセルを赤で乗せた画像を保存する。"""
    bg = (a_rgb.astype(np.float32) * 0.30 + 255.0 * 0.70).astype(np.uint8)
    bg[mask] = (230, 0, 0)
    Image.fromarray(bg).save(str(path))


# ── 知覚ハッシュ(dHash)とページ整合 ──────────────────────────────────────────

def dhash(page: "fitz.Page", size: int = 8) -> np.ndarray:
    """ページの dHash（size*size ビットの bool 配列）。低解像度グレースケールで算出。"""
    pix = page.get_pixmap(dpi=32, colorspace=fitz.csGRAY, alpha=False)
    img = Image.frombytes("L", (pix.width, pix.height), pix.samples)
    a = np.asarray(img.resize((size + 1, size), Image.LANCZOS), dtype=np.int16)
    return (a[:, 1:] > a[:, :-1]).ravel()


def hamming(h1: np.ndarray, h2: np.ndarray) -> int:
    return int(np.count_nonzero(h1 != h2))


def align_pages(ha: list[np.ndarray], hb: list[np.ndarray], gap: float) -> list[tuple]:
    """dHash 列を順序保存でアライメントし、(ai|None, bj|None) のペア列を返す。

    ``gap`` は挿入/削除ペナルティ（0-1 正規化）。小さいほど gap を入れやすく、
    非類似ページ対を match せず removed/added に分ける。
    """
    na, nb = len(ha), len(hb)
    nbits = ha[0].size if na else (hb[0].size if nb else 64)

    def cost(i: int, j: int) -> float:
        return hamming(ha[i], hb[j]) / nbits

    dp = np.zeros((na + 1, nb + 1), dtype=np.float64)
    for i in range(1, na + 1):
        dp[i][0] = i * gap
    for j in range(1, nb + 1):
        dp[0][j] = j * gap
    for i in range(1, na + 1):
        for j in range(1, nb + 1):
            dp[i][j] = min(dp[i - 1][j - 1] + cost(i - 1, j - 1),
                           dp[i - 1][j] + gap, dp[i][j - 1] + gap)

    pairs: list[tuple] = []
    i, j = na, nb
    while i > 0 or j > 0:
        if i > 0 and j > 0:
            diag = dp[i - 1][j - 1] + cost(i - 1, j - 1)
            up = dp[i - 1][j] + gap
            left = dp[i][j - 1] + gap
            m = min(diag, up, left)
            if m == diag:
                pairs.append((i - 1, j - 1)); i -= 1; j -= 1
            elif m == up:
                pairs.append((i - 1, None)); i -= 1
            else:
                pairs.append((None, j - 1)); j -= 1
        elif i > 0:
            pairs.append((i - 1, None)); i -= 1
        else:
            pairs.append((None, j - 1)); j -= 1
    pairs.reverse()
    return pairs


def verdict_for(ratio: float, sim: float, size_mismatch: bool,
                flag_ratio: float, text_flag: float) -> str:
    if size_mismatch:
        return "changed"
    if ratio == 0.0 and sim >= 0.99995:
        return "identical"
    if ratio > flag_ratio or sim < text_flag:
        return "changed"
    return "minor"


# ── 比較本体 ─────────────────────────────────────────────────────────────────

def compare(a_path: Path, b_path: Path, args) -> int:
    da = fitz.open(str(a_path))
    db = fitz.open(str(b_path))
    na, nb = da.page_count, db.page_count
    if args.max_pages:
        na = min(na, args.max_pages)
        nb = min(nb, args.max_pages)

    # 全ページの dHash（低解像度・軽量）
    ha = [dhash(da[i]) for i in range(na)]
    hb = [dhash(db[j]) for j in range(nb)]

    if args.no_align:
        pairs = [(k if k < na else None, k if k < nb else None) for k in range(max(na, nb))]
    else:
        pairs = align_pages(ha, hb, args.align_gap)

    out_dir = Path(args.out)
    if not args.no_images:
        out_dir.mkdir(parents=True, exist_ok=True)
        for old in out_dir.glob("pair-*.png"):
            old.unlink()

    lenient = []
    if args.tolerance:
        lenient.append(f"tol={args.tolerance}px")
    if args.blur:
        lenient.append(f"blur={args.blur}")
    mode = "index" if args.no_align else "aligned"
    tags = f"  [{mode}" + (", " + ", ".join(lenient) if lenient else "") + "]"
    print(f"PDF diff: {a_path.name} ({na}p) vs {b_path.name} ({nb}p) @ {args.dpi}dpi{tags}")
    print(f"{'A':>4} {'B':>4}  {'pixdiff':>8}  {'textsim':>7}  {'phash':>5}  verdict")

    rows = []
    changed = removed = added = 0
    sum_ratio = sum_sim = 0.0
    matched = 0
    for (i, j) in pairs:
        if i is not None and j is not None:
            a_rgb = render_rgb(da[i], args.dpi)
            b_rgb = render_rgb(db[j], args.dpi)
            size_mismatch = a_rgb.shape[:2] != b_rgb.shape[:2]
            mask, ratio = diff_mask(a_rgb, b_rgb, args.pixel_threshold, args.tolerance, args.blur)
            sim = difflib.SequenceMatcher(None, da[i].get_text("text"), db[j].get_text("text")).ratio()
            ph = hamming(ha[i], hb[j])
            v = verdict_for(ratio, sim, size_mismatch, args.flag_ratio, args.text_flag)
            matched += 1
            sum_ratio += ratio
            sum_sim += sim
            img_rel = None
            if not args.no_images and (v == "changed" or args.save_all):
                img_path = out_dir / f"pair-A{i + 1:03d}-B{j + 1:03d}.png"
                make_diff_image(a_rgb, mask, img_path)
                img_rel = str(img_path)
            if v == "changed":
                changed += 1
            note = ""
            if size_mismatch:
                note = f"  [size {a_rgb.shape[1]}x{a_rgb.shape[0]} vs {b_rgb.shape[1]}x{b_rgb.shape[0]}]"
            arrow = f"  -> {img_rel}" if img_rel else ""
            print(f"{i + 1:>4} {j + 1:>4}  {ratio * 100:>7.2f}%  {sim:>7.3f}  {ph:>5}  {v}{note}{arrow}")
            rows.append({"a_page": i + 1, "b_page": j + 1, "pixdiff": ratio, "textsim": sim,
                         "phash": ph, "verdict": v, "size_mismatch": size_mismatch, "image": img_rel})
        elif i is not None:
            removed += 1
            print(f"{i + 1:>4} {'-':>4}  {'-':>8}  {'-':>7}  {'-':>5}  removed (A のみ)")
            rows.append({"a_page": i + 1, "b_page": None, "verdict": "removed"})
        else:
            added += 1
            print(f"{'-':>4} {j + 1:>4}  {'-':>8}  {'-':>7}  {'-':>5}  added (B のみ)")
            rows.append({"a_page": None, "b_page": j + 1, "verdict": "added"})

    avg_ratio = sum_ratio / matched if matched else 0.0
    avg_sim = sum_sim / matched if matched else 1.0
    print(f"\nSummary: 対応 {matched} / 変化 {changed} / removed {removed} / added {added} / "
          f"平均 pixdiff {avg_ratio * 100:.2f}% / 平均 textsim {avg_sim:.3f}")
    if not args.no_images and (changed or args.save_all):
        print(f"差分画像: {out_dir}（赤=変化箇所）")

    if args.json:
        out_dir.mkdir(parents=True, exist_ok=True)
        report = {
            "a": str(a_path), "b": str(b_path), "dpi": args.dpi, "mode": mode,
            "pages_a": na, "pages_b": nb, "matched": matched,
            "changed": changed, "removed": removed, "added": added,
            "avg_pixdiff": avg_ratio, "avg_textsim": avg_sim, "pages": rows,
        }
        rp = out_dir / "report.json"
        rp.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"JSON: {rp}")

    return 1 if (changed or removed or added) else 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description="2 つの PDF をページ単位で比較し差の程度を解析する（pHash でページ整合）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("pdf_a", help="比較元 PDF")
    ap.add_argument("pdf_b", help="比較先 PDF")
    ap.add_argument("--out", default="pdfdiff_out", help="差分画像・JSON の出力先（既定 ./pdfdiff_out）")
    ap.add_argument("--dpi", type=int, default=120, help="ラスタライズ DPI（既定 120）")
    ap.add_argument("--pixel-threshold", type=int, default=24, help="明度差の閾値 0-255（既定 24）")
    ap.add_argument("--tolerance", type=int, default=0,
                    help="平行移動の許容 px。この範囲のズレは差とみなさない（既定 0）")
    ap.add_argument("--blur", type=float, default=0.0,
                    help="比較前の Gaussian ぼかし半径。微小なサイズ違い/AA を吸収（既定 0）")
    ap.add_argument("--fuzzy", action="store_true",
                    help="小さなズレを無視するプリセット（未指定なら tolerance=2, blur=1.0 相当）")
    ap.add_argument("--no-align", action="store_true", help="ページ整合せず index 順(i対i)で比較")
    ap.add_argument("--align-gap", type=float, default=0.22,
                    help="整合の gap ペナルティ 0-1。小さいほど挿入/削除に敏感（既定 0.22）")
    ap.add_argument("--flag-ratio", type=float, default=0.005, help="変化とみなす pixdiff 率（既定 0.005）")
    ap.add_argument("--text-flag", type=float, default=0.995, help="変化とみなす textsim 下限（既定 0.995）")
    ap.add_argument("--save-all", action="store_true", help="変化の無いページも差分画像を保存")
    ap.add_argument("--no-images", action="store_true", help="差分画像を作らない")
    ap.add_argument("--json", action="store_true", help="report.json も書く")
    ap.add_argument("--max-pages", type=int, default=0, help="各 PDF 先頭 N ページのみ対象")
    args = ap.parse_args()
    if args.fuzzy:
        if args.tolerance == 0:
            args.tolerance = 2
        if args.blur == 0.0:
            args.blur = 1.0

    a_path, b_path = Path(args.pdf_a), Path(args.pdf_b)
    for p in (a_path, b_path):
        if not p.exists():
            print(f"PDF が見つかりません: {p}", file=sys.stderr)
            return 2
    return compare(a_path, b_path, args)


if __name__ == "__main__":
    sys.exit(main())
