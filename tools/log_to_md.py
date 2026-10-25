#!/usr/bin/env python3
"""Claude Code のセッションログ(JSONL)を読みやすい Markdown に変換する（手動ツール）。

含めるもの: ユーザー発言 ＋ アシスタントの表示テキスト（＋ thinking があれば）。
含めないもの: tool_use（ツール呼び出し）と tool_result（ツール結果）。

【注意】thinking（内部思考）ブロックは transcript には署名(signature)のみが残り、
本文テキストは保存されない（`thinking: ""`）。そのため実際の出力は
「ユーザー発言＋アシスタント表示テキスト」になる。--fold-thinking 等の thinking 系
オプションは、本文入りのログが得られた場合のための備え。

「ターン」= 1 回のユーザー発言（＝その発言と、次の発言までのアシスタント応答群）。
まず ``--list`` でターン一覧を見て、``--from`` / ``--to`` 等で範囲を絞る。

使い方:
    python tools/log_to_md.py [SESSION.jsonl] [options]

    SESSION.jsonl  対象ログ。省略時は cwd に対応する
                   ~/.claude/projects/<slug>/ の最新 *.jsonl を自動選択
    --list         ターン一覧（番号・時刻・冒頭）を表示して終了（範囲決め用）
    --from N       開始ターン番号（1 始まり・含む）
    --to N         終了ターン番号（含む）
    --last N       末尾 N ターンのみ
    --grep REGEX   ユーザー発言が正規表現にマッチするターンのみ（大文字小文字無視）
    --no-thinking  thinking を除外する
    --fold-thinking  thinking を <details>（折りたたみ）で出す（既定は引用ブロックで常時表示）
    -o FILE        出力先 .md（省略時は標準出力）

依存: 標準ライブラリのみ。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


def default_session() -> "Path | None":
    """cwd に対応する Claude projects ログdir の最新 *.jsonl を返す。"""
    slug = re.sub(r"[^A-Za-z0-9]", "-", str(Path.cwd()))
    d = Path.home() / ".claude" / "projects" / slug
    cands = sorted(d.glob("*.jsonl"), key=lambda p: p.stat().st_mtime) if d.exists() else []
    if not cands:  # フォールバック: どのプロジェクトでもよいので最新
        root = Path.home() / ".claude" / "projects"
        cands = sorted(root.rglob("*.jsonl"), key=lambda p: p.stat().st_mtime) if root.exists() else []
    return cands[-1] if cands else None


def load_events(path: Path) -> list[dict]:
    evs = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                evs.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return evs


def _content_blocks(o: dict) -> list:
    c = (o.get("message") or {}).get("content")
    return c if isinstance(c, list) else []


def is_real_user(o: dict) -> bool:
    """ユーザーが実際に打った発言イベントか（tool_result・メタ・サイドチェーンを除く）。"""
    if o.get("type") != "user" or o.get("isMeta") or o.get("isSidechain"):
        return False
    c = (o.get("message") or {}).get("content")
    if isinstance(c, str):
        return bool(c.strip())
    if isinstance(c, list):
        if any(b.get("type") == "tool_result" for b in c):
            return False
        return any(b.get("type") == "text" for b in c)
    return False


def user_text(o: dict) -> str:
    c = (o.get("message") or {}).get("content")
    if isinstance(c, str):
        return c.strip()
    return "\n".join(b.get("text", "") for b in c if isinstance(b, dict) and b.get("type") == "text").strip()


def short_ts(o: dict) -> str:
    ts = o.get("timestamp") or ""
    # 2026-06-30T00:31:15.108Z -> 2026-06-30 00:31
    m = re.match(r"(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2})", ts)
    return f"{m.group(1)} {m.group(2)}" if m else ts


def blockquote(s: str) -> str:
    return "\n".join(("> " + ln) if ln.strip() else ">" for ln in s.rstrip().split("\n"))


def assign_turns(events: list[dict]) -> list[tuple[int, dict]]:
    """各イベントに所属ターン番号を付ける（サイドチェーン/メタは除外して None にしない=飛ばす）。"""
    tagged = []
    turn = 0
    for o in events:
        if o.get("isSidechain"):
            continue
        if is_real_user(o):
            turn += 1
        if turn == 0:
            continue  # 最初のユーザー発言より前（システム初期化等）は捨てる
        tagged.append((turn, o))
    return tagged


def render(tagged: list[tuple[int, dict]], selected: set[int], args) -> str:
    out: list[str] = []
    cur = None
    for turn, o in tagged:
        if turn not in selected:
            continue
        t = o.get("type")
        if is_real_user(o):
            cur = turn
            out.append(f"\n## Turn {turn} · {short_ts(o)}\n")
            out.append("**👤 ユーザー**\n")
            out.append(user_text(o) + "\n")
            asst_open = False
            continue
        if t == "assistant":
            blocks = _content_blocks(o)
            for b in blocks:
                bt = b.get("type")
                if bt == "text":
                    txt = (b.get("text") or "").strip()
                    if not txt:
                        continue
                    out.append("\n**🤖 アシスタント**\n")
                    out.append(txt + "\n")
                elif bt == "thinking" and not args.no_thinking:
                    th = (b.get("thinking") or "").strip()
                    if not th:
                        continue
                    if args.fold_thinking:
                        out.append("\n<details><summary>💭 思考</summary>\n")
                        out.append("\n" + th + "\n\n</details>\n")
                    else:
                        out.append("\n> 💭 **思考**\n>\n" + blockquote(th) + "\n")
                # tool_use は除外
        # tool_result（type=user のリスト）は selected 判定前に is_real_user=False で素通り→ここでは無視
    return "\n".join(out).strip() + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Claude Code セッションログ(JSONL)を Markdown 化する",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("session", nargs="?", help="対象 .jsonl（省略時は cwd 対応の最新ログを自動選択）")
    ap.add_argument("--list", action="store_true", help="ターン一覧を表示して終了")
    ap.add_argument("--from", dest="from_", type=int, default=None, help="開始ターン番号（含む）")
    ap.add_argument("--to", type=int, default=None, help="終了ターン番号（含む）")
    ap.add_argument("--last", type=int, default=None, help="末尾 N ターンのみ")
    ap.add_argument("--grep", default=None, help="ユーザー発言が正規表現にマッチするターンのみ")
    ap.add_argument("--no-thinking", action="store_true", help="thinking を除外")
    ap.add_argument("--fold-thinking", action="store_true", help="thinking を <details> 折りたたみで出す")
    ap.add_argument("-o", "--out", default=None, help="出力先 .md（省略時は標準出力）")
    args = ap.parse_args()

    session = Path(args.session) if args.session else default_session()
    if session is None or not session.exists():
        print("セッションログが見つかりません。パスを引数で指定してください。", file=sys.stderr)
        return 2

    events = load_events(session)
    tagged = assign_turns(events)
    total = max((t for t, _ in tagged), default=0)

    # ターン -> ユーザー発言（一覧・grep 用）
    user_of: dict[int, dict] = {}
    for t, o in tagged:
        if is_real_user(o) and t not in user_of:
            user_of[t] = o

    if args.list:
        print(f"# {session.name} — 全 {total} ターン\n")
        for t in range(1, total + 1):
            o = user_of.get(t)
            head = user_text(o).split("\n", 1)[0][:78] if o else "(?)"
            print(f"{t:>4} · {short_ts(o) if o else '':<16} {head}")
        return 0

    # 選択ターン集合
    sel = set(range(1, total + 1))
    if args.from_ is not None:
        sel &= set(range(args.from_, total + 1))
    if args.to is not None:
        sel &= set(range(1, args.to + 1))
    if args.last is not None:
        sel &= set(range(max(1, total - args.last + 1), total + 1))
    if args.grep:
        rx = re.compile(args.grep, re.IGNORECASE)
        sel &= {t for t, o in user_of.items() if rx.search(user_text(o))}

    if not sel:
        print("該当ターンがありません（範囲/grep を確認してください）。", file=sys.stderr)
        return 1

    lo, hi = min(sel), max(sel)
    header = (f"# 会話ログ: {session.name}\n\n"
              f"- 対象ターン: {lo}–{hi}（{len(sel)} ターン / 全 {total}）"
              f"{'  grep=' + args.grep if args.grep else ''}\n")
    body = render(tagged, sel, args)
    md = header + "\n" + body

    if args.out:
        Path(args.out).write_text(md, encoding="utf-8")
        print(f"書き出し: {args.out}（{len(sel)} ターン）", file=sys.stderr)
    else:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stdout.write(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
