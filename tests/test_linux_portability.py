"""Windows 専用依存（win32com）なしで動くことと、OS 依存の区切り文字のテスト。

実行: python -m unittest discover -s tests
"""

import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

from md_merge.pandoc import _resource_path_arg
from md_merge.pptmerge._com import PowerPointUnavailableError, dispatch_powerpoint

_WIN32_MODULES = ("pythoncom", "win32com", "win32com.client")


class TestNoWin32Import(unittest.TestCase):
    def test_cli_modules_import_without_win32(self):
        # 別プロセスで win32com/pythoncom を import 不能にした状態で CLI を読み込む
        code = (
            "import sys\n"
            "for m in ('pythoncom', 'win32com', 'win32com.client'):\n"
            "    sys.modules[m] = None\n"
            "import md_merge.__main__, md_merge.pptmerge._merger, md_merge.pptmerge._slide_titles\n"
        )
        r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_dispatch_powerpoint_without_win32_raises_clear_error(self):
        with mock.patch.dict(sys.modules, {m: None for m in _WIN32_MODULES}):
            with self.assertRaises(PowerPointUnavailableError) as cm:
                dispatch_powerpoint()
        self.assertIn("Windows", str(cm.exception))


class TestResourcePathArg(unittest.TestCase):
    def test_joined_with_os_pathsep(self):
        paths = [Path("a"), Path("b")]
        self.assertEqual(_resource_path_arg(paths), os.pathsep.join([".", "a", "b"]))

    def test_empty_is_current_dir(self):
        self.assertEqual(_resource_path_arg([]), ".")


if __name__ == "__main__":
    unittest.main()
