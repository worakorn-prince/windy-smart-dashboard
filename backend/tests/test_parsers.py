from metrics import _infer_ddr_type_from_speed, humanize_bytes
from security.winapi import _parse_json_list


def test_humanize_bytes_zero():
    assert humanize_bytes(0) == "0.0 B"


def test_humanize_bytes_kb():
    assert humanize_bytes(1024) == "1.0 KB"
    assert humanize_bytes(1536) == "1.5 KB"


def test_humanize_bytes_gb():
    gb = 1024 ** 3
    assert humanize_bytes(gb * 2.5) == "2.5 GB"


def test_humanize_bytes_none():
    assert humanize_bytes(None) == "?"


def test_ddr5_threshold():
    assert _infer_ddr_type_from_speed(6400) == "DDR5"
    assert _infer_ddr_type_from_speed(4800) == "DDR5"


def test_ddr4_threshold():
    assert _infer_ddr_type_from_speed(3200) == "DDR4"
    assert _infer_ddr_type_from_speed(2133) == "DDR4"


def test_ddr3_and_legacy():
    assert _infer_ddr_type_from_speed(1600) == "DDR3"
    assert _infer_ddr_type_from_speed(800) == "DDR2"
    assert _infer_ddr_type_from_speed(400) == "DDR"


def test_parse_json_list_array():
    out = _parse_json_list('[{"a":1},{"a":2}]')
    assert isinstance(out, list)
    assert len(out) == 2


def test_parse_json_list_single_object_wraps():
    assert _parse_json_list('{"a":1}') == [{"a": 1}]


def test_parse_json_list_garbage_returns_empty():
    assert _parse_json_list("not json at all") == []


def test_parse_json_list_empty_string():
    assert _parse_json_list("") == []
