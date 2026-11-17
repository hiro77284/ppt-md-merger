"""完了バナー後の所要時間表示。"""
from md_merge import _output
from md_merge._output import format_elapsed, print_done


def test_format_elapsed_seconds():
    assert format_elapsed(0.04) == "0.0秒"
    assert format_elapsed(12.34) == "12.3秒"


def test_format_elapsed_minutes():
    assert format_elapsed(125.4) == "2分05.4秒"


def test_format_elapsed_hours():
    assert format_elapsed(3723) == "1時間02分03秒"


def test_print_done_prints_elapsed_after_done(capsys, monkeypatch):
    monkeypatch.setattr(_output, "_start_time", 100.0)
    monkeypatch.setattr(_output.time, "perf_counter", lambda: 107.5)
    print_done("ppt_to_puremd")
    out = capsys.readouterr().out.splitlines()
    i = out.index("  ppt_to_puremd 完了")
    assert out[i + 1] == "  所要時間: 7.5秒"
