"""Parity tests: Python maintenance modules vs the original Node updater.

Fixtures under `tests/fixtures/` are generated from `D:/Coding_Project/updater/lib`
by a node script (see the task report) — never hand-copied. No test here runs
PowerShell or touches the filesystem outside of reading fixtures.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from maintenance import actions, cleaner, error_codes, export

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def error_code_fixture() -> dict[str, dict[str, str]]:
    return _load("updater_error_codes.json")


@pytest.fixture(scope="module")
def allowlists() -> dict:
    return _load("updater_allowlists.json")


def test_error_code_fixture_is_complete(error_code_fixture: dict) -> None:
    assert len(error_code_fixture) == 22
    assert error_codes.count() == 22


def test_error_codes_match_js_source(error_code_fixture: dict) -> None:
    mapped = {str(code): entry for code, entry in error_codes.ERROR_CODES.items()}
    assert sorted(mapped, key=int) == sorted(error_code_fixture, key=int)
    for code, expected in error_code_fixture.items():
        actual = mapped[code]
        assert actual["text"] == expected["text"], f"text drift for code {code}"
        assert actual["hint"] == expected["hint"], f"hint drift for code {code}"
        assert error_codes.text(int(code)) == expected["text"]
        assert error_codes.hint(int(code)) == expected["hint"]


def test_allowed_actions_subset_of_js(allowlists: dict) -> None:
    assert isinstance(actions.ALLOWED_ACTIONS, tuple)
    assert actions.ALLOWED_ACTIONS
    assert set(actions.ALLOWED_ACTIONS) <= set(allowlists["actions"])


def test_allowed_targets_match_js(allowlists: dict) -> None:
    assert isinstance(cleaner.ALLOWED_TARGETS, tuple)
    assert list(cleaner.ALLOWED_TARGETS) == allowlists["targets"]


def test_open_devmgmt_is_the_only_documented_deviation(allowlists: dict) -> None:
    assert "open-devmgmt" in allowlists["actions"]
    assert "open-devmgmt" not in actions.ALLOWED_ACTIONS
    assert set(allowlists["actions"]) - set(actions.ALLOWED_ACTIONS) == {"open-devmgmt"}


def test_run_action_rejects_open_devmgmt_without_powershell(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called: list[str] = []

    def fake_powershell(*args, **kwargs):
        called.append("powershell")
        raise AssertionError("run_action must not reach PowerShell for open-devmgmt")

    def fake_record(*args, **kwargs):
        called.append("history")

    monkeypatch.setattr(actions, "run_powershell", fake_powershell)
    monkeypatch.setattr(actions.history, "record", fake_record)

    with pytest.raises(actions.ActionError) as excinfo:
        asyncio.run(actions.run_action("open-devmgmt"))

    err = excinfo.value
    assert err.code == actions.UNSUPPORTED_ACTION
    assert err.status_code == 400
    assert called == ["history"], called


def test_build_csv_matches_js_layout(allowlists: dict) -> None:
    rows = [
        {
            "device": "Intel(R) Wi-Fi 6 AX201",
            "driverName": "Netwtw10.sys",
            "version": "22.10.0.7",
            "date": "2026-10-20",
            "status": "OK",
            "deviceId": r"PCI\VEN_8086&DEV_A0F0",
            "errorCode": 0,
            "errorText": "",
        },
        {
            "device": "USB, \"Hub\"",
            "driverName": None,
            "version": "1.0",
            "date": "2026-10-19",
            "status": "Error",
            "deviceId": "USB\\VID_0001",
            "errorCode": 28,
            "errorText": "ยังไม่ได้ติดตั้งไดรเวอร์",
        },
    ]
    body = export.build_csv(rows)

    assert body.startswith("\ufeff")
    lines = body[1:].split("\r\n")
    assert lines[0] == ",".join(allowlists["csvHeader"])
    assert len(lines) == 1 + len(rows)
    assert list(export.DEVICE_HEADER) == allowlists["csvHeader"]

    first = lines[1].split(",")
    assert first[0] == "Intel(R) Wi-Fi 6 AX201"
    assert first[6] == "0"
    assert lines[2].startswith('"USB, ""Hub""",')


def test_clean_scripts_keep_critical_tokens() -> None:
    assert set(cleaner.CLEAN_SCRIPTS) == set(cleaner.ALLOWED_TARGETS)
    scripts = " ".join(cleaner.CLEAN_SCRIPTS.values())
    for token in (
        "$env:TEMP",
        "SystemRoot",
        "$Recycle.Bin",
        "Clear-RecycleBin",
        "Remove-Item -LiteralPath",
    ):
        assert token in scripts, f"missing token in CLEAN_SCRIPTS: {token}"

    assert "Remove-Item -LiteralPath" in cleaner.CLEAN_SCRIPTS["user-temp"]
    assert "Remove-Item -LiteralPath" in cleaner.CLEAN_SCRIPTS["windows-temp"]
    assert "Clear-RecycleBin" in cleaner.CLEAN_SCRIPTS["recycle-bin"]
