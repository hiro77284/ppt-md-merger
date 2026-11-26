"""PowerPoint COM (win32com) への入口。

win32com / pywin32 は Windows 専用のため、モジュール読み込み時には import せず、
PowerPoint が実際に必要になった時点で ``dispatch_powerpoint()`` から読み込む。
これにより Linux / macOS でも PowerPoint を使わないサブコマンド（md→pdf など）が動く。
"""

from __future__ import annotations

from typing import Any


class PowerPointUnavailableError(RuntimeError):
    """PowerPoint (win32com) が使えない環境で PowerPoint 操作を要求された。"""


def powerpoint_unavailable_reason() -> str | None:
    """win32com が読み込めなければその理由を、読み込めれば ``None`` を返す（COM は起動しない）。"""
    try:
        import win32com.client  # noqa: F401
    except ImportError as e:
        return f"win32com を読み込めません: {e}"
    return None


def dispatch_powerpoint() -> Any:
    """``PowerPoint.Application`` の COM オブジェクトを返す。

    win32com が import できない場合は ``PowerPointUnavailableError`` を送出する。
    """
    try:
        import pythoncom
        import win32com.client
    except ImportError as e:
        raise PowerPointUnavailableError(
            "この処理は PowerPoint を使うため Windows + pywin32 が必要です"
            f"（win32com を読み込めません: {e}）"
        ) from e
    # 同じプロセスで先に動いた段（ppt_build の pptpdfexport / pptimgexport 等）が
    # CoUninitialize を呼ぶと、このスレッドの COM は未初期化に戻っている。
    # import 時の暗黙の初期化に頼らず、ここで必ず初期化する（初期化済みなら S_FALSE で無害）。
    # 対応する CoUninitialize は呼ばない: 返した COM オブジェクトは呼び出し側が使い続け、
    # プロセス終了時に後始末される。
    pythoncom.CoInitialize()
    return win32com.client.Dispatch("PowerPoint.Application")
