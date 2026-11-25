"""pptmerge の insertpptx ``slides`` の ``N-END``（N から最後まで）のテスト。

実行: python -m unittest tests.test_slides_end
"""

import unittest

from md_merge.pptmerge._config import ConfigError, parse_slides, slides_need_count


class TestSlidesEnd(unittest.TestCase):
    def test_n_end(self):
        self.assertEqual(parse_slides("3-END", 5), [3, 4, 5])
        self.assertEqual(parse_slides("3-end", 5), [3, 4, 5])
        self.assertEqual(parse_slides("5-END", 5), [5])

    def test_mixed(self):
        self.assertEqual(parse_slides("1, 4-END", 6), [1, 4, 5, 6])
        self.assertEqual(parse_slides([1, "4-END"], 6), [1, 4, 5, 6])

    def test_need_count(self):
        self.assertTrue(slides_need_count("1, 4-END"))
        self.assertTrue(slides_need_count(["4-end"]))
        self.assertFalse(slides_need_count("1, 3-5"))
        self.assertFalse(slides_need_count("all"))
        self.assertFalse(slides_need_count(3))

    def test_errors(self):
        with self.assertRaises(ConfigError):
            parse_slides("6-END", 5)  # 始端が枚数超え
        with self.assertRaises(ConfigError):
            parse_slides("0-END", 5)
        with self.assertRaises(ConfigError):
            parse_slides("3-END")  # 枚数不明

    def test_existing_unchanged(self):
        self.assertIsNone(parse_slides("all"))
        self.assertEqual(parse_slides("1, 3-5, 7"), [1, 3, 4, 5, 7])
        self.assertEqual(parse_slides(5), [5])


if __name__ == "__main__":
    unittest.main()
