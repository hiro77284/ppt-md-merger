"""engine: typst で LaTeX 用 pandoc.defaults だけが書かれているときの警告。"""
import logging
import unittest

from md_merge.pandoc import _warn_latex_defaults_ignored


class TestTypstDefaultsWarning(unittest.TestCase):
    def test_warns_when_only_latex_defaults(self):
        with self.assertLogs(level="WARNING") as cm:
            self.assertTrue(_warn_latex_defaults_ignored({"defaults": ["defaults/a.yaml"]}))
        self.assertTrue(any("typstdefaults" in m for m in cm.output))

    def test_silent_when_typstdefaults_given(self):
        logger = logging.getLogger()
        with self.assertNoLogs(logger, level="WARNING"):
            self.assertFalse(_warn_latex_defaults_ignored(
                {"defaults": "a.yaml", "typstdefaults": "t.yaml"}))

    def test_silent_when_no_defaults(self):
        with self.assertNoLogs(logging.getLogger(), level="WARNING"):
            self.assertFalse(_warn_latex_defaults_ignored({}))


if __name__ == "__main__":
    unittest.main()
