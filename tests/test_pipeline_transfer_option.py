"""ppt_to_puremd / ppt_to_githubmd の --transfer オプションのテスト。

実行: python -m unittest discover -s tests
"""

import argparse
import unittest
from unittest import mock

import md_merge.ppt_to_githubmd as p2gh
import md_merge.ppt_to_puremd as p2pm


class TestTransferOption(unittest.TestCase):
    def _call(self, mod, **kw):
        with mock.patch.object(mod, "run_pipeline", return_value=0) as rp:
            mod.run(argparse.Namespace(**kw))
        return rp.call_args.kwargs

    def test_without_transfer(self):
        for mod in (p2pm, p2gh):
            kw = self._call(mod, transfer=False)
            self.assertNotIn("transfer", [n for n, _ in kw["steps"]])
            self.assertIsNone(kw["transfer_source_key"])

    def test_with_transfer(self):
        for mod, key in ((p2pm, "puremdfilename"), (p2gh, "githubmdfilename")):
            kw = self._call(mod, transfer=True)
            names = [n for n, _ in kw["steps"]]
            self.assertEqual(names[-1], "transfer")
            self.assertEqual(kw["transfer_source_key"], key)
            # 成果物は削除しない
            self.assertNotIn(key, kw["work_file_keys"])


if __name__ == "__main__":
    unittest.main()
