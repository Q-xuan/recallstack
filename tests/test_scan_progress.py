"""Header scan-progress parser (status + progress_message → phase / N/M / %)."""

from recallstack.learning.scan_progress import parse_scan_progress


def test_write_topic_fraction_near_fifty_five():
    p = parse_scan_progress("generating_wiki", "Wrote topic 7/16")
    assert p.phase == "write"
    assert (p.current, p.total) == (7, 16)
    assert p.determinate
    assert p.percent == 55


def test_zh_analyzed_modules():
    p = parse_scan_progress("scanning", "已分析模块 3/29")
    assert p.phase == "scan"
    assert (p.current, p.total) == (3, 29)
    assert p.determinate


def test_zh_wrote_modules_beats_enriching_status():
    p = parse_scan_progress("llm_enriching", "已撰写模块 4/10")
    assert p.phase == "write"
    assert (p.current, p.total) == (4, 10)


def test_cite_from_zh_message():
    p = parse_scan_progress("generating_wiki", "正在核验引用")
    assert p.phase == "cite"
    assert p.current is None
    assert p.determinate
    assert (p.percent or 0) >= 80


def test_outline_from_message():
    p = parse_scan_progress("generating_wiki", "正在规划 Wiki 大纲")
    assert p.phase == "outline"


def test_queued_is_indeterminate_scan():
    p = parse_scan_progress("queued", None)
    assert p.phase == "scan"
    assert p.determinate is False
    assert p.percent is None


def test_ready_hides_bar():
    p = parse_scan_progress("ready", "完成")
    assert p.phase is None
    assert p.percent is None
    assert p.determinate is False


def test_polish_from_status_when_message_empty():
    p = parse_scan_progress("llm_enriching", None)
    assert p.phase == "polish"
    assert p.determinate
    assert (p.percent or 0) >= 90


def test_zh_write_topic_alias():
    p = parse_scan_progress("generating_wiki", "撰写专题 2/8")
    assert p.phase == "write"
    assert (p.current, p.total) == (2, 8)
