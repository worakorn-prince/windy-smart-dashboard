import os
import sys

import pytest

os.environ.setdefault("DASH_TEST_MODE", "1")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture(autouse=True)
def _isolate_maintenance_history(request, tmp_path, monkeypatch):
    mod = getattr(request.node, "module", None) or getattr(request, "module", None)
    if mod is None or not getattr(mod, "__name__", "").startswith("test_maintenance"):
        return
    import config

    monkeypatch.setattr(config, "HISTORY_DB", tmp_path / "history.db", raising=False)
