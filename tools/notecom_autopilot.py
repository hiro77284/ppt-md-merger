#!/usr/bin/env python
"""note.com 半自動投稿ツール（Playwright）。

`pptmdmerge notecomexport` / `ppt_to_notecom` が生成した note 用 YAML（`{base}_notecom.yaml`）を
読み、note.com の新規記事エディタへカバー画像・タイトル・本文ブロックを順に入力する。
入力完了後は Playwright Inspector で一時停止するので、目視確認のうえ再開すると
「公開に進む」を押してハッシュタグを埋め、公開直前の画面で待機する。
**最終的な公開ボタンは押さない**（人間が押す）。

依存（pptmdmerge 本体には含めない。`pip install "pptmdmerge[notecom]"` または個別に）:
    playwright  pyperclip  Pillow
    python -m playwright install chromium

使い方:
    python tools/notecom_autopilot.py build/article_notecom.yaml --auth-state auth.json
    python tools/notecom_autopilot.py build/article_notecom.yaml --imagedir build --hashtags "#図解,#読解力"

auth.json は Playwright の storage_state（note.com にログイン済みの Cookie 等）。
一度だけ `python -m playwright codegen --save-storage=auth.json https://note.com/login`
でログインして作る。`--auth-state` 省略時は環境変数 NOTE_AUTH_STATE を使う。

YAML の形式（notecomexport の出力）:
    meta:
      title: 記事タイトル
      cover: images/cover.png        # 任意。1280×670 にリサイズしてアップロード
      hashtags: ['#タグ1', '#タグ2']  # 任意
    blocks:
      - {type: paragraph, text: ...}
      - {type: paragraph, text: ..., runs: [{text: ..}, {text: .., url: ..}]}  # リンク入り
      - {type: heading1|heading2, text: ...}   # 大見出し
      - {type: heading3, text: ...}            # 小見出し
      - {type: unordered_list|ordered_list, items: [...]}   # 項目は str か {text, runs}
      - {type: quote, lines: [...]}                          # 行も同様
      - {type: code, code: ..., lang: ...}
      - {type: image, path: ..., caption: ..., link: ...}   # link は任意（画像にリンク設定）
      - {type: horizontal_rule}
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

import yaml

try:
    from PIL import Image
    import pyperclip
    from playwright.sync_api import sync_playwright
except ImportError as e:  # pragma: no cover
    sys.stderr.write(
        f"依存パッケージが不足しています: {e}\n"
        "  pip install playwright pyperclip Pillow && python -m playwright install chromium\n"
    )
    raise SystemExit(2)

# note カバー画像の推奨サイズ（リサイズとアップロードボタン名の両方に使う）
NOTE_COVER_IMAGE_WIDTH = 1280
NOTE_COVER_IMAGE_HEIGHT = 670

NOTE_NEW_URL = "https://note.com/notes/new"

# リンク設定の URL 入力欄（テキストの Ctrl+K と画像ツールバーの「リンク」で共通）。
# note の実装では <textarea name="alt" placeholder="https://"> なので input だけを探すと見つからない。
# 非表示の同種要素を掴まないよう :visible を付ける（.last で DOM 末尾の隠れた要素を取ると待ちがタイムアウトする）
URL_BOX_SELECTOR = 'textarea[placeholder="https://"]:visible, input[type="url"]:visible, input[placeholder*="http"]:visible'


def close_popovers(page) -> None:
    """起動直後に出る案内ポップオーバー（AI アシスタントの紹介など）を閉じる。放置すると操作を妨げることがある。"""
    for b in page.locator('[role="dialog"] button[aria-label="閉じる"]').all():
        try:
            b.click(timeout=1000)
        except Exception:  # noqa: BLE001
            pass


def _fill_url_and_apply(page, url: str) -> None:
    """表示中の URL 入力欄に url を入れて「適用」で確定する（無ければ Enter）。"""
    box = page.locator(URL_BOX_SELECTOR).first
    try:
        box.wait_for(state="visible", timeout=3000)
    except Exception:
        n_all = page.locator('textarea[placeholder="https://"], input[type="url"], input[placeholder*="http"]').count()
        print(f"DEBUG: URL 入力欄が見つかりません（候補 {n_all} 件、可視 0 件）", file=sys.stderr)
        raise
    box.fill(url)
    apply_btn = page.get_by_role("button", name="適用")
    try:
        apply_btn.wait_for(state="visible", timeout=1500)
        apply_btn.click()
    except Exception:  # noqa: BLE001
        page.keyboard.press("Enter")
    page.wait_for_timeout(300)
    page.keyboard.press("Escape")   # リンク設定モードを抜ける
    page.wait_for_timeout(200)


# ── ユーティリティ ───────────────────────────────────────────────────────────

def load_note_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8-sig"))


def resize_for_note_cover(input_path: Path, output_path: Path) -> None:
    """カバー画像を 1280×670 を覆う最小倍率で拡縮し、中央でクロップして保存する。"""
    target_w, target_h = NOTE_COVER_IMAGE_WIDTH, NOTE_COVER_IMAGE_HEIGHT
    with Image.open(input_path) as img:
        orig_w, orig_h = img.size
        ratio = max(target_w / orig_w, target_h / orig_h)
        img = img.resize((int(orig_w * ratio), int(orig_h * ratio)), Image.Resampling.LANCZOS)
        left = (img.width - target_w) / 2
        top = (img.height - target_h) / 2
        img = img.crop((left, top, left + target_w, top + target_h))
        img.save(output_path, quality=95)
        print(f"Cover image resized: {output_path}")


def paragraph_to_body_paragraphs(text: str) -> list[str]:
    if not text:
        return [""]
    chunks = [c.strip() for c in text.split("\n\n")]
    chunks = [c for c in chunks if c]
    return chunks if chunks else [text]


def resolve_image_path(rel_path: str, asset_root: Path, image_dir: Path | None) -> Path:
    """--imagedir 配下を優先し、無ければ YAML のディレクトリ基準で解決する。"""
    rel = Path(rel_path)
    if rel.is_absolute():
        return rel
    if image_dir is not None:
        candidate = (image_dir / rel).resolve()
        if candidate.is_file():
            return candidate
    return (asset_root / rel).resolve()


# ── エディタ操作 ─────────────────────────────────────────────────────────────

def input_cover_image(page, image_path: str | Path, asset_root: Path, image_dir: Path | None = None) -> None:
    abs_path = resolve_image_path(str(image_path), asset_root, image_dir)
    if not abs_path.is_file():
        print(f"WARN: カバー画像が見つかりません。スキップします: {abs_path}", file=sys.stderr)
        return
    resized_path = abs_path.parent / f"{abs_path.stem}_resized{abs_path.suffix}"
    resize_for_note_cover(abs_path, resized_path)
    print(f"カバー画像をアップロード中: {abs_path}")

    page.get_by_role("button", name="画像を追加").click()
    with page.expect_file_chooser() as fc_info:
        page.get_by_role(
            "button",
            name=f"画像をアップロード 推奨サイズ：{NOTE_COVER_IMAGE_WIDTH}×{NOTE_COVER_IMAGE_HEIGHT}px",
        ).click()
    fc_info.value.set_files(str(resized_path))

    save_button = page.get_by_role("button", name="保存")
    save_button.wait_for(state="visible", timeout=30000)
    page.wait_for_timeout(500)
    save_button.click(force=True)
    page.wait_for_timeout(1000)

    # 「eyecatch」画像が現れればアップロード完了
    page.get_by_role("img", name="eyecatch").wait_for(state="visible", timeout=30000)
    page.wait_for_timeout(500)
    print("カバー画像の設定が完了しました。")


def input_title(page, title: str) -> None:
    page.fill('textarea[placeholder="記事タイトル"]', title)
    page.keyboard.press("Enter")


def _runs_of(item) -> list[dict]:
    """str / {text, runs} のどちらでも run 列にそろえる。"""
    if isinstance(item, dict):
        return list(item.get("runs") or [{"text": item.get("text") or ""}])
    return [{"text": str(item)}]


def _type_link(page, text: str, url: str) -> None:
    """text を打ってから選択し、Ctrl+K でリンクを設定する（note の標準ショートカット）。

    失敗したときはリンクを諦め、選択を解除して ``（url）`` を後ろに補う。
    """
    page.keyboard.type(text)
    n = len(text)
    if n == 0:
        page.keyboard.type(url)
        return
    for _ in range(n):
        page.keyboard.press("Shift+ArrowLeft")
    page.wait_for_timeout(600)   # 選択直後は Ctrl+K が効かない（バブルメニューが出るまで待つ）
    page.keyboard.press("Control+k")
    try:
        _fill_url_and_apply(page, url)
        page.keyboard.press("End")   # 行末に戻って続きを打つ
        page.wait_for_timeout(200)
    except Exception as e:  # noqa: BLE001
        print(f"WARN: リンク設定に失敗しました（{e.__class__.__name__}）。テキストに URL を補います: {url}", file=sys.stderr)
        page.keyboard.press("Escape")
        page.keyboard.press("End")
        page.keyboard.type(f"（{url}）")


def type_runs(page, runs: list[dict]) -> None:
    for run in runs:
        text = str(run.get("text") or "")
        if run.get("url"):
            _type_link(page, text, str(run["url"]))
        else:
            page.keyboard.type(text)


def input_body(page, paragraphs: list[str]) -> None:
    page.keyboard.press("Control+End")
    page.wait_for_timeout(200)
    for i, paragraph in enumerate(paragraphs):
        page.keyboard.type(paragraph)
        if i < len(paragraphs) - 1:
            page.keyboard.press("Enter")


def input_body_runs(page, runs: list[dict]) -> None:
    page.keyboard.press("Control+End")
    page.wait_for_timeout(200)
    type_runs(page, runs)


def _set_image_link(page, url: str) -> bool:
    """直前にアップロードした画像にリンクを設定する（画像クリック → Ctrl+K → URL → 適用 → Esc）。

    Ctrl+K で URL 欄が開かなければ画像ツールバーの「リンク」ボタンを試す。
    成功したら True。入力欄が見つからなければ False を返す（呼び出し側がリンク段落で代替する）。
    """
    stage = "click"
    try:
        page.wait_for_timeout(1500)   # アップロード直後は選択してもツールバーが出ないことがある
        fig = page.locator(".ProseMirror figure").last
        fig.locator("img").click()
        page.wait_for_timeout(600)
        stage = "ctrl+k"
        page.keyboard.press("Control+k")
        page.wait_for_timeout(500)
        if page.locator(URL_BOX_SELECTOR).count() == 0:
            stage = "toolbar"
            btn = page.locator('button[aria-label="リンク"]:visible').last   # 画像ツールバー（リンク / 代替テキスト / 縮小 / 画像の配置 / 削除）
            btn.wait_for(state="visible", timeout=3000)
            btn.click()
        stage = "fill"
        _fill_url_and_apply(page, url)
        return True
    except Exception as e:  # noqa: BLE001
        print(f"WARN: 画像へのリンク設定に失敗しました（{stage}: {e.__class__.__name__}）。リンク段落で代替します: {url}", file=sys.stderr)
        page.keyboard.press("Escape")
        return False


def input_image(page, image_path: str, caption: str, link: str | None = None) -> bool:
    """画像を挿入する。link があれば画像にリンクを設定し、その成否を返す（link 無しは True）。"""
    page.get_by_role("button", name="メニューを開く").click()
    current_count = page.locator("figure.image").count()
    with page.expect_file_chooser() as fc_info:
        page.get_by_role("button", name="画像", exact=True).click()
    fc_info.value.set_files(image_path)
    page.wait_for_function(
        "current_count => document.querySelectorAll('figure.image').length > current_count",
        arg=current_count,
    )
    linked = _set_image_link(page, link) if link else True
    page.locator(".ProseMirror figure").last.locator("figcaption").click()
    page.keyboard.type(caption)
    page.wait_for_timeout(500)
    # キャプション欄で Enter を押しても外に出られないことがあるため Enter×2＋↓で脱出
    page.keyboard.press("Enter")
    page.keyboard.press("Enter")
    page.keyboard.press("ArrowDown")
    page.wait_for_timeout(500)
    return linked


def input_heading_large(page, text: str) -> None:
    page.keyboard.press("Control+Alt+2")
    page.keyboard.type(text)


def input_heading_small(page, text: str) -> None:
    page.keyboard.press("Control+Alt+3")
    page.keyboard.type(text)


def input_quote(page, quote_lines: list) -> None:
    page.keyboard.press("Control+Shift+>")
    for line in quote_lines:
        type_runs(page, _runs_of(line))
        page.keyboard.press("Enter")
    page.keyboard.press("Enter")


def input_code_block_by_paste(page, code_text: str) -> None:
    pyperclip.copy(code_text)
    page.keyboard.press("Control+Alt+\\")
    page.wait_for_timeout(500)
    page.keyboard.press("Control+v")
    page.wait_for_timeout(500)
    page.keyboard.press("Enter")


def input_horizontal_rule(page) -> None:
    page.get_by_role("button", name="メニューを開く").click()
    page.wait_for_timeout(500)
    page.get_by_role("button", name="区切り線").click()
    page.wait_for_timeout(500)


def input_list(page, items: list, ordered: bool) -> None:
    page.keyboard.press("Control+Shift+7" if ordered else "Control+Shift+8")
    for i, item in enumerate(items):
        type_runs(page, _runs_of(item))
        if i < len(items) - 1:
            page.keyboard.press("Enter")


def input_toc(page) -> None:
    first_p = page.locator(".ProseMirror p").first
    first_p.click()
    page.keyboard.press("Control+Home")
    page.wait_for_timeout(300)
    page.keyboard.press("Enter")
    page.keyboard.press("ArrowUp")
    page.get_by_role("button", name="メニューを開く").click()
    page.locator("#toc-setting").click()


# ── ブロック列の投入 ─────────────────────────────────────────────────────────

def apply_meta(page, meta: dict, asset_root: Path, image_dir: Path | None = None) -> None:
    if meta.get("cover"):
        input_cover_image(page, meta["cover"], asset_root, image_dir)
    input_title(page, meta.get("title") or "無題")


def apply_note_blocks(page, blocks: list[dict], asset_root: Path, image_dir: Path | None = None) -> None:
    """blocks を順にエディタへ入力する。

    ブロック間の Enter 押下は note エディタの挙動（直前ブロックの種類でカーソル位置が
    変わる）に合わせて経験的に調整したもの。変更する場合は実機で確認すること。
    """
    time.sleep(1)
    last = ""
    for idx, block in enumerate(blocks):
        btype = block.get("type")
        print(f"[{idx + 1}/{len(blocks)}] {btype}: {str(block.get('text') or block.get('path') or block.get('items') or block.get('lines') or '')[:60]}")

        if btype == "paragraph":
            if last != "" and last != "image":
                page.keyboard.press("Enter")
            if last in ("unordered_list", "ordered_list"):
                page.keyboard.press("Enter")
            if block.get("runs"):
                input_body_runs(page, block["runs"])
            else:
                input_body(page, paragraph_to_body_paragraphs(block["text"]))
        elif btype in ("heading1", "heading2", "heading3"):
            if last != "" and last != "image":
                page.keyboard.press("Enter")
            if last in ("paragraph", "unordered_list", "ordered_list"):
                page.keyboard.press("Enter")
            page.wait_for_timeout(1000)
            (input_heading_small if btype == "heading3" else input_heading_large)(page, block["text"])
        elif btype in ("unordered_list", "ordered_list"):
            if last != "":
                page.keyboard.press("Enter")
            if last in ("paragraph", "unordered_list", "ordered_list") or (btype == "unordered_list" and last == "horizontal_rule"):
                page.keyboard.press("Enter")
            page.wait_for_timeout(1000)
            input_list(page, block["items"], ordered=(btype == "ordered_list"))
        elif btype == "quote":
            if last != "":
                page.keyboard.press("Enter")
            if last in ("paragraph", "unordered_list", "ordered_list"):
                page.keyboard.press("Enter")
            page.wait_for_timeout(1000)
            input_quote(page, block["lines"])
        elif btype == "code":
            if last != "":
                page.keyboard.press("Enter")
            if last in ("paragraph", "unordered_list", "ordered_list"):
                page.keyboard.press("Enter")
            page.wait_for_timeout(1000)
            input_code_block_by_paste(page, block["code"])
        elif btype == "horizontal_rule":
            input_horizontal_rule(page)
        elif btype == "image":
            abs_path = resolve_image_path(block["path"], asset_root, image_dir)
            if not abs_path.is_file():
                print(f"WARN: 画像が見つかりません。スキップします: {abs_path}", file=sys.stderr)
                continue
            link = block.get("link")
            ok = input_image(page, str(abs_path), block.get("caption") or "", link)
            if link and not ok:
                # 画像へのリンク設定に失敗 → 直後にリンク段落を置いて URL を落とさない
                label = block.get("caption") or link
                input_body_runs(page, [{"text": label, "url": link}])
                last = "paragraph"
                time.sleep(1)
                continue
        else:
            print(f"WARN: 未対応のブロック型をスキップしました: {btype}", file=sys.stderr)
            continue

        last = btype
        time.sleep(1)


def run_note_automation(
    note_yaml: Path,
    auth_state: Path,
    image_dir: Path | None = None,
    hashtags: list[str] | None = None,
    no_pause: bool = False,
) -> None:
    if not note_yaml.is_file():
        raise FileNotFoundError(f"YAML が見つかりません: {note_yaml}")
    if not auth_state.is_file():
        raise FileNotFoundError(f"storage_state (auth.json) が見つかりません: {auth_state}")

    data = load_note_yaml(note_yaml)
    blocks = data.get("blocks") or []
    meta = data.get("meta") or {}
    tags = hashtags if hashtags is not None else list(meta.get("hashtags") or [])

    asset_root = note_yaml.parent.resolve()
    resolved_image_dir = image_dir.resolve() if image_dir is not None else None
    print(f"note_yaml : {note_yaml}\nblocks    : {len(blocks)}\nimage_dir : {resolved_image_dir}\nhashtags  : {tags}")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(storage_state=str(auth_state), viewport={"width": 1280, "height": 1400})
        page = context.new_page()
        page.goto(NOTE_NEW_URL)
        page.wait_for_timeout(2000)
        close_popovers(page)

        print("apply_meta 開始")
        apply_meta(page, meta, asset_root, resolved_image_dir)
        print("apply_note_blocks 開始")
        apply_note_blocks(page, blocks, asset_root, resolved_image_dir)
        input_toc(page)
        print("本文入力完了")

        if not no_pause:
            print("Playwright Inspector で一時停止します。内容を確認して Resume してください。")
            page.pause()

        page.wait_for_timeout(500)
        page.get_by_role("button", name="公開に進む").click()
        if tags:
            page.get_by_role("combobox", name="ハッシュタグを追加する").fill(",".join(tags))

        print("投稿準備が完了しました。公開ボタンは手動で押してください（60 秒後にブラウザを閉じます）。")
        page.wait_for_timeout(60000)
        browser.close()


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="note 用 YAML を読み、note.com エディタに順に入力する（Playwright）")
    p.add_argument("note_yaml", type=Path, help="notecomexport が生成した note 用 YAML")
    p.add_argument("--imagedir", type=Path, default=None,
                   help="画像探索の基点ディレクトリ（優先）。見つからない場合は YAML のディレクトリ基準で解決する")
    p.add_argument("--auth-state", type=Path, default=None,
                   help="Playwright の storage_state (JSON)。省略時は環境変数 NOTE_AUTH_STATE")
    p.add_argument("--hashtags", type=str, default=None,
                   help="カンマ区切りのハッシュタグ。指定時は YAML の meta.hashtags を上書きする")
    p.add_argument("--no-pause", action="store_true", help="本文入力後の Inspector 一時停止を行わない")
    return p


def main() -> int:
    args = build_arg_parser().parse_args()
    auth = args.auth_state or (Path(os.environ["NOTE_AUTH_STATE"]) if os.environ.get("NOTE_AUTH_STATE") else None)
    if auth is None:
        print("--auth-state か環境変数 NOTE_AUTH_STATE で storage_state を指定してください", file=sys.stderr)
        return 2
    tags = None
    if args.hashtags is not None:
        tags = [t.strip() for t in args.hashtags.split(",") if t.strip()]
        tags = [t if t.startswith("#") else f"#{t}" for t in tags]
    try:
        run_note_automation(args.note_yaml.resolve(), auth.resolve(), args.imagedir, tags, args.no_pause)
    except FileNotFoundError as e:
        print(e, file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
