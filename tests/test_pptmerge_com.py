"""pptmerge の PowerPoint COM 入口（dispatch_powerpoint）のテスト。

ppt_build では先に動いた段が CoUninitialize するので、dispatch_powerpoint は
Dispatch の前に必ず CoInitialize する。win32com が無い環境でも動くよう偽モジュールで確認する。
"""

import sys
import types
import unittest
from unittest import mock

from md_merge.pptmerge import _com


class TestDispatchPowerPoint(unittest.TestCase):
    def test_coinitialize_before_dispatch(self):
        calls = []
        pythoncom = types.ModuleType("pythoncom")
        pythoncom.CoInitialize = lambda: calls.append("CoInitialize")
        client = types.ModuleType("win32com.client")
        client.Dispatch = lambda name: calls.append(("Dispatch", name)) or "app"
        win32com = types.ModuleType("win32com")
        win32com.client = client
        with mock.patch.dict(sys.modules, {"pythoncom": pythoncom, "win32com": win32com,
                                           "win32com.client": client}):
            self.assertEqual(_com.dispatch_powerpoint(), "app")
        self.assertEqual(calls, ["CoInitialize", ("Dispatch", "PowerPoint.Application")])

    def test_unavailable_without_win32com(self):
        with mock.patch.dict(sys.modules, {"pythoncom": None, "win32com": None, "win32com.client": None}):
            with self.assertRaises(_com.PowerPointUnavailableError):
                _com.dispatch_powerpoint()


if __name__ == "__main__":
    unittest.main()
