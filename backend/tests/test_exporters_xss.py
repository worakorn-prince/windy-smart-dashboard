"""XSS hardening tests for the HTML report exporter (HARDEN-102).

Ensures every value interpolated into the exported HTML report is escaped,
so payloads coming from logs / client-supplied reports cannot execute.
"""
from __future__ import annotations

from pathlib import Path

import exporters

SCRIPT_PAYLOAD = "<script>alert('xss')</script>"
IMG_PAYLOAD = '<img src=x onerror="alert(1)">'
QUOTE_PAYLOAD = '"><script>alert(1)</script>'


def _payload_report() -> dict:
    return {
        "generated_at": "2026-01-01T00:00:00" + SCRIPT_PAYLOAD,
        "duration_ms": IMG_PAYLOAD,
        "riskscore": QUOTE_PAYLOAD,
        "risk_label": "Low" + IMG_PAYLOAD,
        "findings": [
            {
                "category": "cat" + SCRIPT_PAYLOAD,
                "title": SCRIPT_PAYLOAD,
                "description": IMG_PAYLOAD,
                "weight": "1" + IMG_PAYLOAD,
                "severity": "high" + QUOTE_PAYLOAD,
            }
        ],
        "data": {"suspicious_countries": [SCRIPT_PAYLOAD, "KP"]},
    }


def _benign_report() -> dict:
    return {
        "generated_at": "2026-01-01T00:00:00",
        "duration_ms": 123,
        "riskscore": 42,
        "risk_label": "Low",
        "findings": [
            {
                "category": "R&D",
                "title": "Plain title",
                "description": "Ampersand & angle <test>",
                "weight": 3,
                "severity": "high",
            }
        ],
        "data": {"suspicious_countries": ["KP"]},
    }


def test_to_html_escapes_script_payload() -> None:
    text = exporters.to_html(_payload_report()).decode("utf-8")
    assert SCRIPT_PAYLOAD not in text
    assert "&lt;script&gt;" in text


def test_to_html_escapes_img_onerror_payload() -> None:
    text = exporters.to_html(_payload_report()).decode("utf-8")
    assert "<img" not in text
    assert IMG_PAYLOAD not in text


def test_to_html_escapes_quote_breakout_in_class_attr() -> None:
    text = exporters.to_html(_payload_report()).decode("utf-8")
    assert QUOTE_PAYLOAD not in text
    assert '"><script' not in text


def test_to_html_escapes_generated_at_riskscore_and_countries() -> None:
    text = exporters.to_html(_payload_report()).decode("utf-8")
    assert SCRIPT_PAYLOAD not in text
    assert "&lt;script&gt;alert(&#x27;xss&#x27;)&lt;/script&gt;" in text
    assert "&quot;&gt;&lt;script&gt;" in text


def test_to_html_keeps_table_structure_with_payloads() -> None:
    text = exporters.to_html(_payload_report()).decode("utf-8")
    assert "<table>" in text
    assert "<tbody>" in text
    assert "Findings (1)" in text


def test_to_html_benign_report_roundtrip() -> None:
    text = exporters.to_html(_benign_report()).decode("utf-8")
    assert 'class="sev-high"' in text
    assert "R&amp;D" in text
    assert "R&D" not in text
    assert "Ampersand &amp; angle &lt;test&gt;" in text
    assert "Risk Score: 42 (Low)" in text


def test_to_html_empty_findings_row() -> None:
    report = _benign_report()
    report["findings"] = []
    text = exporters.to_html(report).decode("utf-8")
    assert "No findings" in text


def test_save_html_writes_escaped_file(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(exporters, "AUDIT_DIR", tmp_path)
    report = _payload_report()
    report["generated_at"] = "2026-01-01T00:00:00"
    path = Path(exporters.save(report, "html"))
    assert path.parent == tmp_path
    text = path.read_text(encoding="utf-8")
    assert SCRIPT_PAYLOAD not in text
    assert "<img" not in text
    assert "&lt;script&gt;" in text
