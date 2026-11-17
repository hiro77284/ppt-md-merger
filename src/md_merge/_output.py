import argparse
import json
import logging
import time
from pathlib import Path

EXIT_OK = 0
EXIT_FAILURE = 1
EXIT_BAD_INPUT = 2
EXIT_NOT_FOUND = 3

_LOG_LEVELS = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "warn": logging.WARNING,
    "error": logging.ERROR,
}


# コマンド開始時刻 (perf_counter)。main() が start_timer() で設定する。
# 未設定のまま print_done() が呼ばれた場合 (テスト等で run() を直接呼ぶ) は
# モジュール読み込み時刻を起点にする。
_start_time: float = time.perf_counter()


def start_timer() -> None:
    """コマンド全体の所要時間計測を開始する。"""
    global _start_time
    _start_time = time.perf_counter()


def elapsed_seconds() -> float:
    """start_timer() からの経過秒数。"""
    return time.perf_counter() - _start_time


def format_elapsed(seconds: float) -> str:
    """所要時間を人が読める形にする (例: 12.3秒 / 2分05.4秒 / 1時間02分03秒)。"""
    if seconds < 60:
        return f"{seconds:.1f}秒"
    if seconds < 3600:
        m, s = divmod(seconds, 60)
        return f"{int(m)}分{s:04.1f}秒"
    h, rem = divmod(int(round(seconds)), 3600)
    m, s = divmod(rem, 60)
    return f"{h}時間{m:02d}分{s:02d}秒"


def print_done(label: str) -> None:
    """「<label> 完了」バナーと、その直後に所要時間を表示する。"""
    print("\n========================================")
    print(f"  {label} 完了")
    print(f"  所要時間: {format_elapsed(elapsed_seconds())}")
    print("========================================\n")


def setup_logging(level: str) -> None:
    logging.basicConfig(
        level=_LOG_LEVELS.get(level, logging.INFO),
        format="%(levelname)s: %(message)s",
    )


def emit(
    args: argparse.Namespace,
    status: str,
    command: str,
    input_path: Path,
    output_path: Path,
    dry_run: bool = False,
) -> None:
    if args.json:
        payload: dict = {
            "status": status,
            "command": command,
            "input": str(input_path),
            "output": str(output_path),
        }
        if dry_run:
            payload["dry_run"] = True
        print(json.dumps(payload, ensure_ascii=False))
    elif dry_run:
        msg = f"DRY-RUN: {input_path}\n-> {output_path}"
        print(msg)
        logging.info("%s", msg)
    else:
        msg = f"OK: {input_path}\n-> {output_path}"
        print(msg)
        logging.info("%s", msg)
