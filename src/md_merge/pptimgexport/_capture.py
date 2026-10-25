"""スライドショーを COM で駆動し、アニメーションの各ステップをキャプチャする（Windows 専用）。

``export-image-step:`` 付きの IMAGE ブロックの画像ソース。PDF は全オブジェクトが
出揃った最終状態しか持たないため、途中のステップはスライドショーを実際に
再生して撮るしかない。設計と試作の実測は docs/design_pptx_animation_capture.md。

使い方::

    with SlideShowSession(pptx_path, target_size=(2000, 1125)) as show:
        n = show.click_count(3)
        img = show.capture(3, 2)   # スライド 3 を 2 回クリックした状態（target_size に揃え済み）

取得した画像はスライド全体を *target_size* へリサンプルしたもの。PDF 経路と同じ
% 座標でそのまま切り出せる。
"""

from __future__ import annotations

import ctypes
import hashlib
import logging
import time
from pathlib import Path

from PIL import Image

# ── PowerPoint COM 定数 ────────────────────────────────────────────────────
_PP_SHOW_TYPE_WINDOW = 2         # ppShowTypeWindow: 全画面ではなくウィンドウで再生
_PP_MANUAL_ADVANCE = 1           # ppSlideShowManualAdvance: 自動時間送りを止める
_PP_SHOW_ALL = 1                 # ppShowAll: 範囲指定・目的別スライドショーを無視
_PP_SLIDE_SHOW_RUNNING = 1       # ppSlideShowRunning
_PW_RENDERFULLCONTENT = 2        # PrintWindow のフラグ（DWM 合成内容を取る）

_STARTUP_WAIT = 1.5              # スライドショー起動後の待ち秒数
_SETTLE_INTERVAL = 0.12          # 差分収束判定の撮影間隔（秒）
_SETTLE_TIMEOUT = 3.0            # 差分収束の打ち切り秒数
_UPSCALE_WARN = 1.05             # これを超える拡大率で画質低下を警告
_RESIZE_MARGIN = 1.02            # ウィンドウを目標より少し大きめに取る


class StepCaptureError(RuntimeError):
    """キャプチャ経路の失敗（PowerPoint の起動・ウィンドウ特定・移動など）。"""


def _set_dpi_aware() -> None:
    """GetWindowRect が物理ピクセルを返すようにする（表示スケール 100% 以外で必要）。"""
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PROCESS_PER_MONITOR_DPI_AWARE
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def _capture_window(hwnd: int) -> Image.Image:
    """*hwnd* の内容を PrintWindow(PW_RENDERFULLCONTENT) で取得する。

    ウィンドウ表示のスライドショーでは黒画像にならず、前面である必要もない（試作で確認）。
    """
    import win32gui
    import win32ui

    left, top, right, bottom = win32gui.GetWindowRect(hwnd)
    width, height = right - left, bottom - top
    if width <= 0 or height <= 0:
        raise StepCaptureError(f"ウィンドウサイズが不正です: {width}x{height}（最小化されていませんか）")

    hwnd_dc = win32gui.GetWindowDC(hwnd)
    mfc_dc = win32ui.CreateDCFromHandle(hwnd_dc)
    save_dc = mfc_dc.CreateCompatibleDC()
    bitmap = win32ui.CreateBitmap()
    bitmap.CreateCompatibleBitmap(mfc_dc, width, height)
    save_dc.SelectObject(bitmap)
    try:
        if not ctypes.windll.user32.PrintWindow(hwnd, save_dc.GetSafeHdc(), _PW_RENDERFULLCONTENT):
            raise StepCaptureError("PrintWindow が失敗しました")
        info = bitmap.GetInfo()
        bits = bitmap.GetBitmapBits(True)
        img = Image.frombuffer("RGB", (info["bmWidth"], info["bmHeight"]), bits, "raw", "BGRX", 0, 1)
    finally:
        save_dc.DeleteDC()
        mfc_dc.DeleteDC()
        win32gui.ReleaseDC(hwnd, hwnd_dc)
        win32gui.DeleteObject(bitmap.GetHandle())
    return img


def _client_box(hwnd: int) -> tuple[int, int, int, int]:
    """ウィンドウ画像内でのクライアント領域（タイトルバー・枠を除いた部分）の箱。"""
    import win32gui

    _cl, _ct, cr, cb = win32gui.GetClientRect(hwnd)
    sx, sy = win32gui.ClientToScreen(hwnd, (0, 0))
    wl, wt, _wr, _wb = win32gui.GetWindowRect(hwnd)
    ox, oy = sx - wl, sy - wt
    return (ox, oy, ox + cr, oy + cb)


def _band_trim(img: Image.Image, thresh: int = 12) -> tuple[int, int, int, int]:
    """四辺の暗い帯（レターボックス）を除いた箱を返す。"""
    gray = img.convert("L")
    w, h = gray.size
    rows = list(gray.resize((1, h), Image.BOX).getdata())
    cols = list(gray.resize((w, 1), Image.BOX).getdata())
    top, bottom, left, right = 0, h, 0, w
    while top < bottom and rows[top] < thresh:
        top += 1
    while bottom > top and rows[bottom - 1] < thresh:
        bottom -= 1
    while left < right and cols[left] < thresh:
        left += 1
    while right > left and cols[right - 1] < thresh:
        right -= 1
    return (left, top, right, bottom)


def _fit_box(w: int, h: int, aspect: float) -> tuple[int, int, int, int]:
    """幅 *w*・高さ *h* の領域の中央に縦横比 *aspect* の箱を最大で収める。"""
    if w / h > aspect:
        bw = round(h * aspect)
        x0 = (w - bw) // 2
        return (x0, 0, x0 + bw, h)
    bh = round(w / aspect)
    y0 = (h - bh) // 2
    return (0, y0, w, y0 + bh)


def _slide_box(client_img: Image.Image, aspect: float) -> tuple[int, int, int, int]:
    """クライアント領域画像の中のスライド領域を求める。

    スライドは黒帯で囲まれて表示されるので、まず暗い帯を実測で落とす。ブラウズ表示には
    右端に縦スクロールバー（黒ではない）が付くため、最後に縦横比へスナップして余剰幅を
    右から削る。スライドの縁自体が暗いと帯の検出が食い込むので、結果が小さすぎる場合は
    クライアント領域への幾何的な当てはめに切り替える。
    """
    cw, ch = client_img.size
    left, top, right, bottom = _band_trim(client_img)
    height = bottom - top
    if height <= 0 or right <= left:
        return _fit_box(cw, ch, aspect)
    want_w = round(height * aspect)
    if right - left > want_w:
        right = left + want_w
    elif right - left < want_w:
        want_h = round((right - left) / aspect)
        top += (height - want_h) // 2
        bottom = top + want_h
    fx0, fy0, fx1, fy1 = _fit_box(cw, ch, aspect)
    if (right - left) * (bottom - top) < 0.8 * (fx1 - fx0) * (fy1 - fy0):
        logging.debug("スライド領域の帯検出が小さすぎるため幾何的な当てはめを使います")
        return (fx0, fy0, fx1, fy1)
    return (left, top, right, bottom)


def _list_ppt_windows() -> dict[int, tuple[int, int]]:
    """可視の PowerPoint フレームウィンドウ（class=PPTFrameClass）の {hwnd: (w, h)}。

    ウィンドウ表示のスライドショーは PowerPoint 本体と同じ ``PPTFrameClass`` の別ウィンドウ
    として出る（タイトルはローカライズされるため当てにしない）。
    """
    import win32gui

    found: dict[int, tuple[int, int]] = {}

    def cb(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd):
            return
        if win32gui.GetClassName(hwnd) != "PPTFrameClass":
            return
        left, top, right, bottom = win32gui.GetWindowRect(hwnd)
        found[hwnd] = (right - left, bottom - top)

    win32gui.EnumWindows(cb, None)
    return found


class SlideShowSession:
    """pptx 1 つぶんのウィンドウ表示スライドショー。``with`` で使う。

    *target_size* はスライド全体の出力ピクセル寸法（PDF 経路を同じ DPI で
    ラスタライズしたときと同じ値を渡す）。
    """

    def __init__(self, pptx_path: Path, target_size: tuple[int, int]):
        self.pptx_path = pptx_path
        self.target_size = target_size
        self.aspect = target_size[0] / target_size[1]
        self._app = None
        self._pres = None
        self._show_window = None
        self._view = None
        self._hwnd = 0
        self._box: tuple[int, int, int, int] | None = None   # ウィンドウ画像内のスライド領域
        self._upscale_warned = False
        self._quit_app = False

    # ── ライフサイクル ──────────────────────────────────────────────────
    def __enter__(self) -> SlideShowSession:
        import pythoncom
        import win32com.client as win32

        _set_dpi_aware()
        pythoncom.CoInitialize()
        try:
            try:
                running = win32.GetActiveObject("PowerPoint.Application")
            except Exception:
                running = None
            self._app = running or win32.Dispatch("PowerPoint.Application")
            self._quit_app = running is None
            self._app.Visible = True   # PowerPoint は不可視モードが使えない
            self._pres = self._app.Presentations.Open(str(self.pptx_path), ReadOnly=True, WithWindow=True)

            settings = self._pres.SlideShowSettings
            settings.AdvanceMode = _PP_MANUAL_ADVANCE
            settings.ShowType = _PP_SHOW_TYPE_WINDOW
            for prop, value in (("RangeType", _PP_SHOW_ALL), ("ShowPresenterView", False),
                                ("ShowWithAnimation", True)):
                try:
                    setattr(settings, prop, value)
                except Exception as e:  # バージョンによって無い／設定できない
                    logging.debug("SlideShowSettings.%s を設定できませんでした: %s", prop, e)

            before = _list_ppt_windows()
            self._show_window = settings.Run()
            self._view = self._show_window.View
            time.sleep(_STARTUP_WAIT)
            self._hwnd = self._find_hwnd(before)
            logging.debug("スライドショーウィンドウ hwnd=%d", self._hwnd)
            self._fit_window()
        except BaseException:
            self.__exit__(None, None, None)
            raise
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        import pythoncom

        try:
            if self._view is not None and self._view.State == _PP_SLIDE_SHOW_RUNNING:
                self._view.Exit()
        except Exception:
            pass
        try:
            if self._pres is not None:
                self._pres.Close()
        except Exception:
            pass
        if self._quit_app and self._app is not None:
            try:
                if self._app.Presentations.Count == 0:
                    self._app.Quit()
            except Exception:
                pass
        self._view = self._show_window = self._pres = self._app = None
        pythoncom.CoUninitialize()

    # ── 公開 API ────────────────────────────────────────────────────────
    def click_count(self, slide_no: int) -> int:
        """スライド *slide_no* のクリックステップ数（``GetClickCount()``）。"""
        self._goto(slide_no, 0)
        return int(self._view.GetClickCount())

    def capture(self, slide_no: int, step: int) -> Image.Image:
        """スライド *slide_no* を *step* 回クリックした状態を、*target_size* に揃えて返す。"""
        self._goto(slide_no, step)
        img = self._capture_settled(f"slide {slide_no} step {step}")
        if img.convert("L").getextrema()[1] < 8:
            raise StepCaptureError(
                f"slide {slide_no} step {step}: 真っ黒な画像しか取れませんでした"
                "（ウィンドウが最小化されているか、画面がロックされていませんか）"
            )
        if self._box is None:
            self._box = self._measure_box(img)
        slide_img = img.crop(self._box)
        sw, sh = slide_img.size
        ratio = self.target_size[0] / sw
        if ratio > _UPSCALE_WARN and not self._upscale_warned:
            logging.warning(
                "キャプチャしたスライド領域 %dx%dpx が目標 %dx%dpx より小さく、%.2f 倍に拡大します"
                "（画質が落ちます。より大きな画面で実行すると改善します）: %s",
                sw, sh, *self.target_size, ratio, self.pptx_path.name,
            )
            self._upscale_warned = True
        if slide_img.size != self.target_size:
            slide_img = slide_img.resize(self.target_size, Image.LANCZOS)
        return slide_img

    # ── 内部 ────────────────────────────────────────────────────────────
    def _find_hwnd(self, before: dict[int, tuple[int, int]]) -> int:
        """スライドショーウィンドウの HWND を特定する。

        ``SlideShowWindow.HWND`` は遅延バインディングではメソッドとして見え、HWND を
        返さないことがある（試作で確認）。その場合はスライドショー起動の前後で増えた
        ``PPTFrameClass`` ウィンドウを差分で特定する。
        """
        raw = getattr(self._show_window, "HWND", None)
        if callable(raw):
            try:
                raw = raw()
            except Exception:
                raw = None
        try:
            if raw:
                return int(raw)
        except (TypeError, ValueError):
            pass
        after = _list_ppt_windows()
        new = [h for h in after if h not in before]
        if new:
            return max(new, key=lambda h: after[h][0] * after[h][1])
        raise StepCaptureError("スライドショーウィンドウの HWND を特定できませんでした")

    def _fit_window(self) -> None:
        """スライド領域が *target_size* 以上になるようにウィンドウを広げる。

        pt と物理 px の比は表示スケールで変わるので、実測して比率で合わせる（2 回まで）。
        画面より大きくできない環境では取れる大きさのまま進み、capture() が拡大＋警告する。
        """
        for _ in range(2):
            img = self._capture_settled("ウィンドウ寸法の測定")
            box = self._measure_box(img)
            cur_w = box[2] - box[0]
            if cur_w >= self.target_size[0]:
                break
            scale = self.target_size[0] / cur_w * _RESIZE_MARGIN
            try:
                w, h = float(self._show_window.Width), float(self._show_window.Height)
                self._show_window.Left = 0
                self._show_window.Top = 0
                self._show_window.Width = w * scale
                self._show_window.Height = h * scale
            except Exception as e:
                logging.debug("スライドショーウィンドウの寸法を変更できませんでした: %s", e)
                break
            time.sleep(0.5)
        self._box = None   # 寸法が変わり得るので、最初の capture() で測り直す

    def _measure_box(self, img: Image.Image) -> tuple[int, int, int, int]:
        cl, ct, cr, cb = _client_box(self._hwnd)
        l, t, r, b = _slide_box(img.crop((cl, ct, cr, cb)), self.aspect)
        box = (cl + l, ct + t, cl + r, ct + b)
        logging.debug("スライド領域: %s（%dx%dpx、目標 %dx%dpx）",
                      box, box[2] - box[0], box[3] - box[1], *self.target_size)
        return box

    def _goto(self, slide_no: int, step: int) -> None:
        self._view.GotoSlide(slide_no)
        try:
            shown = int(self._view.Slide.SlideIndex)
        except Exception:
            shown = slide_no
        if shown != slide_no:
            raise StepCaptureError(
                f"スライドショーでスライド {slide_no} に移動できません（表示中: {shown}）。"
                "非表示スライドではありませんか"
            )
        if step:
            self._view.GotoClick(step)

    def _capture_settled(self, label: str) -> Image.Image:
        """アニメーションが落ち着くまで撮り続け、2 枚連続で同一になったフレームを返す。

        ``GotoClick`` は即座に戻り、アニメーションはその後再生される。完了イベントが無い
        ため、フレーム差分の収束で代替する。収束しない（繰り返し再生など）場合は最後の
        フレームを返して警告する。
        """
        t0 = time.perf_counter()
        prev_digest = None
        prev_img = None
        while time.perf_counter() - t0 < _SETTLE_TIMEOUT:
            img = _capture_window(self._hwnd)
            digest = hashlib.blake2b(img.tobytes(), digest_size=16).digest()
            if digest == prev_digest:
                return img
            prev_digest, prev_img = digest, img
            time.sleep(_SETTLE_INTERVAL)
        logging.warning("%s: %.1f 秒以内に描画が収束しませんでした（最後のフレームを使います）",
                        label, _SETTLE_TIMEOUT)
        return prev_img
