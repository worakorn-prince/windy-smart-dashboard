"""Viewer API — serve scopeboard data and trigger rebuilds."""
from __future__ import annotations

import asyncio
import json
import sys
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_PATH = REPO_ROOT / "scopeboard" / "data.json"
ALL_PATH = REPO_ROOT / "scopeboard" / "all-projects.json"

router = APIRouter(prefix="/api/viewer", tags=["viewer"])


class RebuildRequest(BaseModel):
    aggregate: bool = False


class DatasetStatus(BaseModel):
    exists: bool
    size: int | None = None
    modified: str | None = None


class StatusResponse(BaseModel):
    ok: bool
    single: DatasetStatus
    all: DatasetStatus


def _no_data() -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={
            "code": "NO_DATA",
            "text": "Dataset not found or unreadable",
            "hint": "รัน scripts/export_json.py หรือกด Rebuild",
        },
    )


def _read_dataset(path: Path) -> dict[str, Any]:
    try:
        content = path.read_text(encoding="utf-8")
        return json.loads(content)
    except (json.JSONDecodeError, OSError) as err:
        raise _no_data() from err


def _dataset_meta(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"exists": False, "size": None, "modified": None}
    stat = path.stat()
    return {
        "exists": True,
        "size": stat.st_size,
        "modified": datetime.fromtimestamp(stat.st_mtime, tz=datetime.now().astimezone().tzinfo).isoformat(),
    }


@router.get("/single")
async def get_single() -> dict[str, Any]:
    data = _read_dataset(DATA_PATH)
    meta = _dataset_meta(DATA_PATH)
    return {"ok": True, "path": str(DATA_PATH), **meta, "data": data}


@router.get("/all")
async def get_all() -> dict[str, Any]:
    data = _read_dataset(ALL_PATH)
    meta = _dataset_meta(ALL_PATH)
    return {"ok": True, "path": str(ALL_PATH), **meta, "data": data}


@router.get("/status", response_model=StatusResponse)
async def get_status() -> dict[str, Any]:
    return {
        "ok": True,
        "single": _dataset_meta(DATA_PATH),
        "all": _dataset_meta(ALL_PATH),
    }


async def require_viewer_admin(request: Request) -> None:
    from main import require_admin

    await require_admin(request)
    if request.headers.get("x-requested-with") != "windy-dashboard":
        raise HTTPException(status_code=403, detail="missing_origin_header")


def _run_script(script: str, timeout: float = 180.0) -> dict[str, Any]:
    script_path = REPO_ROOT / "scripts" / script
    try:
        result = subprocess.run(
            [sys.executable, str(script_path)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return {
            "script": script,
            "code": result.returncode,
            "stdout_tail": result.stdout[-2000:] if result.stdout else "",
            "stderr_tail": result.stderr[-2000:] if result.stderr else "",
        }
    except subprocess.TimeoutExpired:
        return {
            "script": script,
            "code": -1,
            "stdout_tail": "",
            "stderr_tail": "timeout",
            "error": "timeout",
        }


@router.post("/rebuild")
async def rebuild(
    payload: RebuildRequest,
    _admin: None = Depends(require_viewer_admin),
) -> dict[str, Any]:
    import time

    start = time.time()
    outputs = []

    out1 = await asyncio.to_thread(_run_script, "export_json.py")
    outputs.append(out1)

    if payload.aggregate:
        out2 = await asyncio.to_thread(_run_script, "aggregate.py")
        outputs.append(out2)

    failed = any(o.get("code", 0) != 0 for o in outputs)
    if failed:
        detail = {
            "code": "REBUILD_FAILED",
            "text": "One or more rebuild scripts failed",
            "hint": "ตรวจสอบ logs และลองใหม่",
            "outputs": outputs,
        }
        raise HTTPException(status_code=502, detail=detail)

    duration_ms = int((time.time() - start) * 1000)
    return {
        "ok": True,
        "durationMs": duration_ms,
        "outputs": outputs,
        "single": _dataset_meta(DATA_PATH),
        "all": _dataset_meta(ALL_PATH),
    }
