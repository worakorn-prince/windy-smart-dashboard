import asyncio
import hashlib
import json
import sys

import pytest
from fastapi.testclient import TestClient

import config
import main
from maintenance import history as action_log
from maintenance import startup

ONE_DRIVE_COMMAND = (
    '"C:\\Users\\prince\\AppData\\Local\\Microsoft\\OneDrive\\OneDrive.exe" /background'
)

LISTING = "\n".join(
    [
        f"HKCU\\Run\tOneDrive\t{ONE_DRIVE_COMMAND}",
        'HKCU\\Run\tSteam\t"C:\\Program Files (x86)\\Steam\\steam.exe" -silent',
        "HKLM\\Run\tSecurityHealth\tC:\\Windows\\System32\\SecurityHealthSystray.exe",
        "HKCU\\RunOnce\tSetupOnce\tC:\\Temp\\setup.exe",
        "startup-folder\tDiscord.lnk\tC:\\Users\\prince\\AppData\\Roaming\\Microsoft\\Windows\\Start Menu\\Programs\\Startup\\Discord.lnk",
        "startup-folder\tVPN.lnk\tC:\\ProgramData\\Microsoft\\Windows\\Start Menu\\Programs\\Startup\\VPN.lnk",
    ]
)

LISTING_WITHOUT_ONEDRIVE = "\n".join(
    line for line in LISTING.splitlines() if not line.startswith("HKCU\\Run\tOneDrive")
)

GOLDEN_QUERY_OUTPUT = (
    "\r\n"
    "HKEY_CURRENT_USER\\Software\\Microsoft\\Windows\\CurrentVersion\\Run\r\n"
    '    My App    REG_SZ    "C:\\Program Files\\My App\\app.exe" --flag "x y"\r\n'
    "\r\n"
)

GOLDEN_EXPAND_OUTPUT = (
    "\r\n"
    "HKEY_CURRENT_USER\\Software\\Microsoft\\Windows\\CurrentVersion\\Run\r\n"
    "    Tool Box    REG_EXPAND_SZ    %ProgramFiles%\\Tool Box\\tool.exe /start\r\n"
    "\r\n"
)


def _present(command: str = ONE_DRIVE_COMMAND, value_type: str = "REG_SZ") -> str:
    output = (
        "\r\nHKEY_CURRENT_USER\\Software\\Microsoft\\Windows\\CurrentVersion\\Run\r\n"
        f"    OneDrive    {value_type}    {command}\r\n\r\n"
    )
    return json.dumps({"exitCode": 0, "output": output})


def _absent() -> str:
    return json.dumps(
        {
            "exitCode": 1,
            "output": "ERROR: The system was unable to find the specified registry key or value.",
        }
    )


class FakeRunner:
    """Records every script and answers with canned PowerShell output.

    `probe_plan` is a queue of per-query answers (payload strings or exceptions)
    so a test can model "value present when reading, gone when verifying".
    """

    def __init__(
        self,
        listing: str = LISTING,
        *,
        value_present: bool = False,
        value: str = ONE_DRIVE_COMMAND,
        query_raises: bool = False,
        probe_plan: list[object] | None = None,
        remove_ok: bool = True,
        remove_raises: bool = False,
        set_ok: bool = True,
        set_raises: bool = False,
    ) -> None:
        self.listing = listing
        self.value_present = value_present
        self.value = value
        self.query_raises = query_raises
        self.probe_plan = list(probe_plan or [])
        self.remove_ok = remove_ok
        self.remove_raises = remove_raises
        self.set_ok = set_ok
        self.set_raises = set_raises
        self.list_calls = 0
        self.query_calls: list[str] = []
        self.remove_calls: list[str] = []
        self.set_calls: list[str] = []

    def _query_payload(self) -> str:
        if not self.value_present:
            return _absent()
        return _present(self.value)

    async def __call__(self, script: str, *, timeout: float = 30.0) -> str:
        if script == startup.LIST_SCRIPT:
            self.list_calls += 1
            return self.listing
        if "reg.exe query" in script:
            self.query_calls.append(script)
            if self.probe_plan:
                answer = self.probe_plan.pop(0)
                if isinstance(answer, Exception):
                    raise answer
                return str(answer)
            if self.query_raises:
                raise RuntimeError("reg query exploded")
            return self._query_payload()
        if "Remove-ItemProperty" in script:
            self.remove_calls.append(script)
            if self.remove_raises:
                raise RuntimeError("Remove-ItemProperty exploded")
            return json.dumps(
                {"ok": self.remove_ok, "error": "" if self.remove_ok else "access denied"}
            )
        if "Set-ItemProperty" in script:
            self.set_calls.append(script)
            if self.set_raises:
                raise RuntimeError("Set-ItemProperty exploded")
            return json.dumps(
                {"ok": self.set_ok, "error": "" if self.set_ok else "access denied"}
            )
        raise AssertionError(f"unexpected PowerShell script: {script}")


@pytest.fixture(autouse=True)
def _isolated_backup(tmp_path, monkeypatch):
    monkeypatch.setattr(startup, "BACKUP_PATH", tmp_path / "startup_backup.json")
    yield


def _item_id(location: str, name: str) -> str:
    return hashlib.sha1(f"{location}|{name}".encode()).hexdigest()[:12]


def _client():
    try:
        return TestClient(main.app, base_url="http://testserver", client=("127.0.0.1", 51000))
    except TypeError:
        return TestClient(main.app)


def _headers() -> dict[str, str]:
    headers = {"X-Requested-With": "windy-dashboard"}
    if config.ADMIN_TOKEN:
        headers["X-Admin-Token"] = config.ADMIN_TOKEN
    return headers


def _seed_backup(item_id: str, command: str, *, name: str = "OneDrive") -> None:
    startup.BACKUP_PATH.parent.mkdir(parents=True, exist_ok=True)
    startup.BACKUP_PATH.write_text(
        json.dumps(
            {
                "items": {
                    item_id: {
                        "location": "HKCU\\Run",
                        "name": name,
                        "command": command,
                        "disabled_at": "2026-01-01T00:00:00Z",
                    }
                }
            }
        ),
        encoding="utf-8",
    )


def _backup_items() -> dict:
    return json.loads(startup.BACKUP_PATH.read_text(encoding="utf-8"))["items"]


# ---- registry query parsing (golden output) ---- #


def test_query_value_keeps_value_names_with_spaces_and_quotes():
    raw = json.dumps({"exitCode": 0, "output": GOLDEN_QUERY_OUTPUT})

    assert startup._query_value(raw) == '"C:\\Program Files\\My App\\app.exe" --flag "x y"'


def test_query_value_supports_reg_expand_sz():
    raw = json.dumps({"exitCode": 0, "output": GOLDEN_EXPAND_OUTPUT})

    assert startup._query_value(raw) == "%ProgramFiles%\\Tool Box\\tool.exe /start"


def test_query_value_returns_none_when_value_is_missing():
    assert startup._query_value(_absent()) is None


def test_query_value_falls_back_to_empty_string_without_data():
    raw = json.dumps(
        {
            "exitCode": 0,
            "output": (
                "\r\nHKEY_CURRENT_USER\\Software\\Microsoft\\Windows\\CurrentVersion\\Run\r\n"
                "    OneDrive    REG_SZ    \r\n"
            ),
        }
    )

    assert startup._query_value(raw) == ""


# ---- listing ---- #


def test_list_parses_registry_and_startup_folder():
    runner = FakeRunner()

    result = asyncio.run(startup.list_startup(runner=runner))

    assert runner.list_calls == 1
    assert result["count"] == 6
    assert len(result["items"]) == 6
    assert result["scannedAt"].endswith("Z")

    by_name = {item["name"]: item for item in result["items"]}
    assert by_name["OneDrive"]["location"] == "HKCU\\Run"
    assert by_name["OneDrive"]["command"] == ONE_DRIVE_COMMAND
    assert by_name["OneDrive"]["enabled"] is True
    assert by_name["OneDrive"]["writable"] is True
    assert by_name["OneDrive"]["backup_stale"] is False
    assert by_name["SetupOnce"]["location"] == "HKCU\\RunOnce"
    assert by_name["SecurityHealth"]["location"] == "HKLM\\Run"
    assert by_name["SecurityHealth"]["writable"] is True
    assert by_name["Discord.lnk"]["location"] == "startup-folder"
    assert by_name["Discord.lnk"]["enabled"] is True
    assert by_name["Discord.lnk"]["writable"] is False

    assert by_name["OneDrive"]["id"] == _item_id("HKCU\\Run", "OneDrive")
    assert len(by_name["OneDrive"]["id"]) == 12


def test_list_ids_are_stable_across_calls():
    first = asyncio.run(startup.list_startup(runner=FakeRunner()))
    second = asyncio.run(startup.list_startup(runner=FakeRunner()))

    assert [item["id"] for item in first["items"]] == [
        item["id"] for item in second["items"]
    ]
    assert [item["name"] for item in first["items"]] == [
        item["name"] for item in second["items"]
    ]


def test_list_skips_malformed_lines():
    listing = "\n".join(
        [
            "",
            "   ",
            "# comment",
            "garbage line",
            "HKCU\\Run\tOnlyTwoFields",
            "\t\t",
            "BOGUS\\Run\tBad\tC:\\bad.exe",
            "HKCU\\Run\t\tC:\\noname.exe",
            "HKLM\\Run\tEmpty\t",
            "\x00\x01\x02",
            "HKCU\\Run\tGood\tC:\\good.exe",
        ]
    )

    result = asyncio.run(startup.list_startup(runner=FakeRunner(listing)))

    assert result["count"] == 1
    assert result["items"][0]["name"] == "Good"
    assert result["items"][0]["location"] == "HKCU\\Run"


def test_list_merges_disabled_items_from_backup():
    item_id = _item_id("HKCU\\Run", "OneDrive")
    _seed_backup(item_id, ONE_DRIVE_COMMAND)

    result = asyncio.run(startup.list_startup(runner=FakeRunner(LISTING_WITHOUT_ONEDRIVE)))

    disabled = [item for item in result["items"] if item["id"] == item_id]
    assert len(disabled) == 1
    assert disabled[0]["enabled"] is False
    assert disabled[0]["backup_stale"] is False
    assert disabled[0]["command"] == ONE_DRIVE_COMMAND
    assert disabled[0]["writable"] is True
    assert result["count"] == 6


def test_list_keeps_stale_backup_item_enabled():
    item_id = _item_id("HKCU\\Run", "OneDrive")
    _seed_backup(item_id, ONE_DRIVE_COMMAND)

    result = asyncio.run(startup.list_startup(runner=FakeRunner()))

    entry = next(item for item in result["items"] if item["id"] == item_id)
    assert entry["enabled"] is True
    assert entry["backup_stale"] is True
    assert entry["command"] == ONE_DRIVE_COMMAND


# ---- toggling ---- #


@pytest.mark.parametrize("confirm", ["", "Startup", "yes", "relaunch", None])
def test_toggle_requires_confirm(confirm):
    runner = FakeRunner()

    with pytest.raises(startup.StartupError) as excinfo:
        asyncio.run(startup.set_enabled("abcdef123456", False, confirm, runner=runner))

    assert excinfo.value.code == startup.CONFIRM_REQUIRED
    assert excinfo.value.status_code == 400
    assert runner.list_calls == 0
    assert not startup.BACKUP_PATH.exists()


def test_toggle_rejects_non_bool_enabled():
    runner = FakeRunner()

    with pytest.raises(startup.StartupError) as excinfo:
        asyncio.run(startup.set_enabled("abcdef123456", "false", "startup", runner=runner))

    assert excinfo.value.code == startup.INVALID_REQUEST
    assert runner.list_calls == 0


def test_toggle_unknown_item_is_not_found():
    runner = FakeRunner()

    with pytest.raises(startup.StartupError) as excinfo:
        asyncio.run(startup.set_enabled("deadbeef0000", False, "startup", runner=runner))

    assert excinfo.value.code == startup.NOT_FOUND
    assert excinfo.value.status_code == 404
    assert runner.query_calls == []
    assert runner.remove_calls == []


def test_toggle_startup_folder_is_unsupported():
    item_id = _item_id("startup-folder", "Discord.lnk")
    runner = FakeRunner()

    with pytest.raises(startup.StartupError) as excinfo:
        asyncio.run(startup.set_enabled(item_id, False, "startup", runner=runner))

    assert excinfo.value.code == startup.UNSUPPORTED_LOCATION
    assert excinfo.value.status_code == 400
    assert runner.query_calls == []
    assert runner.remove_calls == []
    assert not startup.BACKUP_PATH.exists()


@pytest.mark.parametrize("name", ["/evil", "bad\x01name", "line\x1ffeed"])
def test_toggle_rejects_dangerous_names(name):
    listing = f"HKCU\\Run\t{name}\tC:\\evil.exe"
    runner = FakeRunner(listing)

    with pytest.raises(startup.StartupError) as excinfo:
        asyncio.run(
            startup.set_enabled(_item_id("HKCU\\Run", name), False, "startup", runner=runner)
        )

    assert excinfo.value.code == startup.INVALID_NAME
    assert excinfo.value.status_code == 400
    assert runner.query_calls == []
    assert runner.remove_calls == []
    assert runner.set_calls == []


def test_disable_backs_up_then_removes():
    item_id = _item_id("HKCU\\Run", "OneDrive")
    runner = FakeRunner(value_present=True)

    result = asyncio.run(startup.set_enabled(item_id, False, "startup", runner=runner))

    assert result["ok"] is True
    assert result["changed"] is True
    assert result["item"]["id"] == item_id
    assert result["item"]["enabled"] is False
    assert result["item"]["writable"] is True

    entry = _backup_items()[item_id]
    assert entry["location"] == "HKCU\\Run"
    assert entry["name"] == "OneDrive"
    assert entry["command"] == ONE_DRIVE_COMMAND
    assert entry["disabled_at"].endswith("Z")

    assert len(runner.query_calls) == 1
    assert "reg.exe query" in runner.query_calls[0]
    assert len(runner.remove_calls) == 1
    script = runner.remove_calls[0]
    assert "Remove-ItemProperty" in script
    assert "-Name 'OneDrive'" in script
    assert "-LiteralPath 'HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Run'" in script

    after = asyncio.run(startup.list_startup(runner=FakeRunner(LISTING_WITHOUT_ONEDRIVE)))
    disabled = [item for item in after["items"] if item["id"] == item_id]
    assert len(disabled) == 1
    assert disabled[0]["enabled"] is False

    row = action_log.query(limit=1)[0]
    assert row["action"] == "startup"
    assert row["target"] == item_id
    assert row["ok"] is True
    assert json.loads(row["detail"])["command"] == ONE_DRIVE_COMMAND


def test_disable_rolls_back_backup_when_value_still_present():
    item_id = _item_id("HKCU\\Run", "OneDrive")
    runner = FakeRunner(value_present=True, remove_ok=False)

    with pytest.raises(startup.StartupError) as excinfo:
        asyncio.run(startup.set_enabled(item_id, False, "startup", runner=runner))

    assert excinfo.value.code == startup.WRITE_FAILED
    assert excinfo.value.status_code == 502

    assert _backup_items() == {}
    assert startup.load_backup()["items"] == {}

    after = asyncio.run(startup.list_startup(runner=FakeRunner()))
    entry = next(item for item in after["items"] if item["id"] == item_id)
    assert entry["enabled"] is True
    assert entry["backup_stale"] is False

    row = action_log.query(limit=1)[0]
    assert row["action"] == "startup"
    assert row["ok"] is False
    assert row["error"] == startup.WRITE_FAILED
    assert json.loads(row["detail"])["command"] == ONE_DRIVE_COMMAND


def test_disable_keeps_backup_when_runner_raises_but_value_is_gone():
    item_id = _item_id("HKCU\\Run", "OneDrive")
    runner = FakeRunner(
        value_present=True,
        remove_raises=True,
        probe_plan=[_present(), _absent()],
    )

    result = asyncio.run(startup.set_enabled(item_id, False, "startup", runner=runner))

    assert result["ok"] is True
    assert result["changed"] is True
    assert result["verified"] is True
    assert result["item"]["enabled"] is False

    entry = _backup_items()[item_id]
    assert entry["command"] == ONE_DRIVE_COMMAND

    after = asyncio.run(startup.list_startup(runner=FakeRunner(LISTING_WITHOUT_ONEDRIVE)))
    disabled = [item for item in after["items"] if item["id"] == item_id]
    assert len(disabled) == 1
    assert disabled[0]["enabled"] is False

    row = action_log.query(limit=1)[0]
    assert row["ok"] is True
    assert json.loads(row["detail"])["verifiedAfterError"] is True
    assert json.loads(row["detail"])["command"] == ONE_DRIVE_COMMAND


def test_disable_keeps_backup_when_state_cannot_be_verified():
    item_id = _item_id("HKCU\\Run", "OneDrive")
    runner = FakeRunner(
        value_present=True,
        remove_raises=True,
        probe_plan=[_present(), RuntimeError("probe exploded")],
    )

    with pytest.raises(startup.StartupError) as excinfo:
        asyncio.run(startup.set_enabled(item_id, False, "startup", runner=runner))

    assert excinfo.value.code == startup.WRITE_FAILED
    assert item_id in _backup_items()

    row = action_log.query(limit=1)[0]
    assert row["ok"] is False
    assert "stateUnknown" in (row["detail"] or "")
    assert json.loads(row["detail"])["command"] == ONE_DRIVE_COMMAND


def test_disable_fails_when_registry_query_fails():
    item_id = _item_id("HKCU\\Run", "OneDrive")
    runner = FakeRunner(query_raises=True)

    with pytest.raises(startup.StartupError) as excinfo:
        asyncio.run(startup.set_enabled(item_id, False, "startup", runner=runner))

    assert excinfo.value.code == startup.WRITE_FAILED
    assert runner.remove_calls == []
    assert not startup.BACKUP_PATH.exists()
    assert json.loads(action_log.query(limit=1)[0]["detail"])["command"] == ONE_DRIVE_COMMAND


def test_disable_falls_back_to_listed_command_when_query_has_no_value():
    item_id = _item_id("HKCU\\Run", "OneDrive")
    runner = FakeRunner(value_present=True, value="")

    asyncio.run(startup.set_enabled(item_id, False, "startup", runner=runner))

    assert _backup_items()[item_id]["command"] == ONE_DRIVE_COMMAND


def test_disable_preserves_previous_backup_entries():
    first_id = _item_id("HKCU\\Run", "OneDrive")
    second_id = _item_id("HKCU\\Run", "Steam")
    runner = FakeRunner(value_present=True)

    asyncio.run(startup.set_enabled(first_id, False, "startup", runner=runner))
    asyncio.run(startup.set_enabled(second_id, False, "startup", runner=runner))

    items = _backup_items()
    assert set(items) == {first_id, second_id}
    assert items[second_id]["name"] == "Steam"


def test_enable_restores_command_and_clears_backup():
    item_id = _item_id("HKCU\\Run", "OneDrive")
    stored_command = '"C:\\OneDrive.exe" /background'
    _seed_backup(item_id, stored_command)
    runner = FakeRunner(LISTING_WITHOUT_ONEDRIVE)

    result = asyncio.run(startup.set_enabled(item_id, True, "startup", runner=runner))

    assert result["ok"] is True
    assert result["changed"] is True
    assert result["item"]["enabled"] is True
    assert result["item"]["command"] == stored_command

    assert len(runner.set_calls) == 1
    script = runner.set_calls[0]
    assert "Set-ItemProperty" in script
    assert "-Name 'OneDrive'" in script
    assert f"-Value '{stored_command}'" in script
    assert "-LiteralPath 'HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Run'" in script

    assert _backup_items() == {}

    row = action_log.query(limit=1)[0]
    assert row["action"] == "startup"
    assert row["ok"] is True
    assert json.loads(row["detail"])["command"] == stored_command


def test_enable_aborts_when_value_is_already_in_registry():
    item_id = _item_id("HKCU\\Run", "OneDrive")
    _seed_backup(item_id, ONE_DRIVE_COMMAND)
    runner = FakeRunner(LISTING_WITHOUT_ONEDRIVE, value_present=True)

    with pytest.raises(startup.StartupError) as excinfo:
        asyncio.run(startup.set_enabled(item_id, True, "startup", runner=runner))

    assert excinfo.value.code == startup.ALREADY_ENABLED
    assert excinfo.value.status_code == 409
    assert runner.set_calls == []
    assert item_id in _backup_items()


def test_enable_is_noop_when_already_enabled():
    item_id = _item_id("HKCU\\Run", "OneDrive")
    runner = FakeRunner()

    result = asyncio.run(startup.set_enabled(item_id, True, "startup", runner=runner))

    assert result["changed"] is False
    assert result["item"]["enabled"] is True
    assert runner.set_calls == []
    assert runner.remove_calls == []
    assert runner.query_calls == []


def test_enable_rolls_back_registry_when_backup_update_fails(monkeypatch):
    item_id = _item_id("HKCU\\Run", "OneDrive")
    _seed_backup(item_id, ONE_DRIVE_COMMAND)
    runner = FakeRunner(LISTING_WITHOUT_ONEDRIVE)

    def _boom(_data):
        raise OSError("disk full")

    monkeypatch.setattr(startup, "_write_backup", _boom)

    with pytest.raises(startup.StartupError) as excinfo:
        asyncio.run(startup.set_enabled(item_id, True, "startup", runner=runner))

    assert excinfo.value.code == startup.WRITE_FAILED
    assert len(runner.set_calls) == 1
    assert len(runner.remove_calls) == 1


def test_enable_fails_when_set_fails():
    item_id = _item_id("HKCU\\Run", "OneDrive")
    _seed_backup(item_id, ONE_DRIVE_COMMAND)
    runner = FakeRunner(LISTING_WITHOUT_ONEDRIVE, set_ok=False)

    with pytest.raises(startup.StartupError) as excinfo:
        asyncio.run(startup.set_enabled(item_id, True, "startup", runner=runner))

    assert excinfo.value.code == startup.WRITE_FAILED
    assert item_id in startup.load_backup()["items"]


def test_enable_fails_when_probe_raises():
    item_id = _item_id("HKCU\\Run", "OneDrive")
    _seed_backup(item_id, ONE_DRIVE_COMMAND)
    runner = FakeRunner(LISTING_WITHOUT_ONEDRIVE, query_raises=True)

    with pytest.raises(startup.StartupError) as excinfo:
        asyncio.run(startup.set_enabled(item_id, True, "startup", runner=runner))

    assert excinfo.value.code == startup.WRITE_FAILED
    assert runner.set_calls == []
    assert item_id in startup.load_backup()["items"]


def test_list_failure_is_wrapped():
    class Boom:
        async def __call__(self, script: str, *, timeout: float = 30.0) -> str:
            raise RuntimeError("powershell exploded")

    with pytest.raises(startup.StartupError) as excinfo:
        asyncio.run(startup.list_startup(runner=Boom()))

    assert excinfo.value.code == startup.LIST_FAILED
    assert excinfo.value.status_code == 502


# ---- backup file handling ---- #


def test_corrupt_backup_is_quarantined_and_ignored():
    startup.BACKUP_PATH.parent.mkdir(parents=True, exist_ok=True)
    startup.BACKUP_PATH.write_text("{not json at all", encoding="utf-8")

    assert startup.load_backup()["items"] == {}

    corrupt = startup.BACKUP_PATH.with_name(startup.BACKUP_PATH.name + ".corrupt")
    assert corrupt.exists()
    assert corrupt.read_text(encoding="utf-8") == "{not json at all"

    result = asyncio.run(startup.list_startup(runner=FakeRunner()))
    assert result["count"] == 6


# ---- API ---- #


def test_startup_endpoint_lists_items(monkeypatch):
    async def _fake_list():
        return {
            "items": [
                {
                    "id": "abc123456789",
                    "name": "OneDrive",
                    "command": "x",
                    "location": "HKCU\\Run",
                    "enabled": True,
                    "writable": True,
                    "backup_stale": False,
                }
            ],
            "count": 1,
            "scannedAt": "2026-01-01T00:00:00Z",
        }

    monkeypatch.setattr(startup, "list_startup", _fake_list)

    response = _client().get("/api/maintenance/startup")

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["module"] == "maintenance"
    assert body["stage"] == "write"
    assert body["count"] == 1
    assert body["items"][0]["id"] == "abc123456789"
    assert body["servedAt"].endswith("Z")


def test_startup_toggle_requires_csrf_header():
    response = _client().post(
        "/api/maintenance/startup/toggle",
        json={"id": "abc123456789", "enabled": False, "confirm": "startup"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "forbidden: csrf"


def test_startup_toggle_rejects_bad_confirm(monkeypatch):
    async def _boom(*_args, **_kwargs):
        raise AssertionError("PowerShell runner must not run without a valid confirm")

    monkeypatch.setattr(startup, "list_startup", _boom)

    response = _client().post(
        "/api/maintenance/startup/toggle",
        json={"id": "abc123456789", "enabled": False, "confirm": "nope"},
        headers=_headers(),
    )

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail["code"] == startup.CONFIRM_REQUIRED
    assert detail["action"] == "startup"
    assert detail["text"]
    assert detail["hint"]


def test_startup_toggle_returns_item(monkeypatch):
    calls: list[tuple[str, bool, str]] = []

    async def _fake_set(item_id, enabled, confirm, *, runner=None):
        calls.append((item_id, enabled, confirm))
        return {
            "ok": True,
            "changed": True,
            "item": {"id": item_id, "enabled": enabled},
        }

    monkeypatch.setattr(startup, "set_enabled", _fake_set)

    response = _client().post(
        "/api/maintenance/startup/toggle",
        json={"id": "abc123456789", "enabled": False, "confirm": "startup"},
        headers=_headers(),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["item"]["enabled"] is False
    assert calls == [("abc123456789", False, "startup")]


def test_startup_toggle_unknown_id_is_404(monkeypatch):
    async def _fake_list(*_args, **_kwargs):
        return {"items": [], "count": 0, "scannedAt": "2026-01-01T00:00:00Z"}

    monkeypatch.setattr(startup, "list_startup", _fake_list)

    response = _client().post(
        "/api/maintenance/startup/toggle",
        json={"id": "deadbeef0000", "enabled": False, "confirm": "startup"},
        headers=_headers(),
    )

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == startup.NOT_FOUND


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
