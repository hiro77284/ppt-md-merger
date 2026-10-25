"""PowerPoint COM (win32com) への入口。

win32com / pywin32 は Windows 専用のため、モジュール読み込み時には import せず、
PowerPoint が実際に必要になった時点で ``dispatch_powerpoint()`` から読み込む。
これにより Linux / macOS でも PowerPoint を使わないサブコマンド（md→pdf など）が動く。
"""

from __future__ import annotations

from typing import Any


class PowerPointUnavailableError(RuntimeError):
    """PowerPoint (win32com) が使えない環境で PowerPoint 操作を要求された。"""


def dispatch_powerpoint() -> Any:
    """``PowerPoint.Application`` の COM オブジェクトを返す。

    win32com が import できない場合は ``PowerPointUnavailableError`` を送出する。
    """
    try:
        import win32com.client
    except ImportError as e:
        raise PowerPointUnavailableError(
            "この処理は PowerPoint を使うため Windows + pywin32 が必要です"
            f"（win32com を読み込めません: {e}）"
        ) from e
    return win32com.client.Dispatch("PowerPoint.Application")
