"""Build a portable dashboard package (zip) that runs with Python only.

The package contains the backend (stdlib + requirements.txt), the already built
frontend (frontend/dist), the CLI scripts, the static scopeboard viewer and the
root launcher/docs files. Runtime data (.agent, .cache, *.db, *.json datasets)
is never copied.

Usage:
    python scripts/package_portable.py --dry-run
    python scripts/package_portable.py --out dist/windy-dashboard-portable-v0.3.1.zip
"""

import argparse
import fnmatch
import hashlib
import json
import platform
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent

PACKAGE_NAME = "windy-smart-dashboard"
MANIFEST_NAME = "MANIFEST.json"
CHUNK_SIZE = 1 << 20

DEFAULT_INCLUDE_DIRS = ("backend", "scopeboard")
DEFAULT_INCLUDE_FILES = (
    "run_dashboard.bat",
    "run.bat",
    "run.ps1",
    "run_dashboard.sh",
    "README.md",
    "README-viewer.md",
    "README.th.md",
    "LICENSE",
    "docs/PACKAGING.md",
)

EXCLUDE_DIR_NAMES = {
    "__pycache__",
    "node_modules",
    ".venv",
    ".git",
    ".agent",
    "playwright-report",
    "test-results",
}

EXCLUDE_PATH_PARTS = (
    "backend/.cache",
    "frontend/src",
    "frontend/tests",
    "frontend/e2e",
    "frontend/node_modules",
    "frontend/playwright-report",
    "frontend/test-results",
    "dist",
)

EXCLUDE_PATTERNS = (
    "*.pyc",
    "*.db",
    "opencode.json",
    ".mcp.json",
)

BACKEND_CONTENT_GLOBS = ("*.py", "requirements*.txt")

SCOPEBOARD_FILES = ("index.html", "all.html")


class PackagingError(Exception):
    """Raised when the package cannot be built; carries a machine code + message."""

    def __init__(self, code, text):
        super().__init__(f"{code}: {text}")
        self.code = code
        self.text = text


def _relative(path, root):
    try:
        return Path(path).relative_to(root)
    except ValueError:
        return None


def _rel_posix(path, root):
    rel = _relative(path, root)
    return rel.as_posix() if rel is not None else Path(path).as_posix()


def _is_excluded(path, root):
    path = Path(path)
    rel = _relative(path, root)
    parts = rel.parts if rel is not None else path.parts
    if any(part in EXCLUDE_DIR_NAMES for part in parts):
        return True
    if rel is not None:
        rel_posix = rel.as_posix()
        for prefix in EXCLUDE_PATH_PARTS:
            if rel_posix == prefix or rel_posix.startswith(prefix + "/"):
                return True
    return any(fnmatch.fnmatch(path.name, pattern) for pattern in EXCLUDE_PATTERNS)


def _walk_files(base, root):
    for path in sorted(Path(base).rglob("*")):
        if path.is_file() and not _is_excluded(path, root):
            yield path


def collect_files(root, frontend_dist=None, *, verify=True):
    """Return absolute paths of every file that belongs in the portable package."""
    root = Path(root).resolve()
    frontend_dist = (
        Path(frontend_dist).resolve() if frontend_dist is not None
        else root / "frontend" / "dist"
    )
    collected = set()

    backend = root / "backend"
    if backend.is_dir():
        for path in _walk_files(backend, root):
            if any(fnmatch.fnmatch(path.name, pattern) for pattern in BACKEND_CONTENT_GLOBS):
                collected.add(path)

    if (frontend_dist / "index.html").is_file():
        for path in _walk_files(frontend_dist, root):
            collected.add(path)
    elif verify:
        raise PackagingError(
            "FRONTEND_NOT_BUILT",
            f"frontend build not found at {frontend_dist} "
            "(run `cd frontend && npm install && npm run build`, "
            "or pass --skip-verify to build a backend-only package)",
        )

    scripts = root / "scripts"
    if scripts.is_dir():
        for path in sorted(scripts.glob("*.py")):
            if path.is_file() and not _is_excluded(path, root):
                collected.add(path)

    for name in SCOPEBOARD_FILES:
        path = root / "scopeboard" / name
        if path.is_file() and not _is_excluded(path, root):
            collected.add(path)

    for name in DEFAULT_INCLUDE_FILES:
        path = root / name
        if path.is_file() and not _is_excluded(path, root):
            collected.add(path)

    return sorted((path.resolve() for path in collected),
                  key=lambda path: _rel_posix(path, root))


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _utc_now_iso():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def build_manifest(version, files, root):
    """Build the package manifest (counts + per-file sha256) for the given files."""
    root = Path(root).resolve()
    entries = []
    for path in sorted(files, key=lambda item: _rel_posix(item, root)):
        path = Path(path)
        rel = _relative(path.resolve(), root)
        if rel is None:
            raise PackagingError(
                "PATH_OUTSIDE_ROOT",
                f"{path} is outside the package root {root}",
            )
        entries.append({
            "path": rel.as_posix(),
            "size": path.stat().st_size,
            "sha256": sha256_file(path),
        })
    return {
        "name": PACKAGE_NAME,
        "version": version,
        "builtAt": _utc_now_iso(),
        "python": platform.python_version(),
        "counts": {
            "files": len(entries),
            "totalBytes": sum(entry["size"] for entry in entries),
        },
        "files": entries,
    }


def create_zip(root, files, out_path, manifest):
    """Write MANIFEST.json first, then every file; return summary + zip sha256."""
    root = Path(root).resolve()
    out_path = Path(out_path).expanduser().resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(MANIFEST_NAME, json.dumps(manifest, indent=2, ensure_ascii=False))
        for path in sorted(files, key=lambda item: _rel_posix(item, root)):
            path = Path(path).resolve()
            if path == out_path:
                continue
            archive.write(path, arcname=_rel_posix(path, root))
            written += 1
    return {
        "out": str(out_path),
        "files": written,
        "bytes": out_path.stat().st_size,
        "sha256": sha256_file(out_path),
    }


def read_version(root):
    """Read `version` from frontend/package.json; fall back to 0.0.0."""
    package_json = Path(root) / "frontend" / "package.json"
    try:
        data = json.loads(package_json.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return "0.0.0"
    version = data.get("version") if isinstance(data, dict) else None
    return str(version) if version else "0.0.0"


def _human_bytes(size):
    if size < 1024:
        return f"{int(size)} B"
    value = float(size)
    for unit in ("KiB", "MiB", "GiB"):
        value /= 1024.0
        if value < 1024 or unit == "GiB":
            return f"{value:.1f} {unit}"
    return f"{value:.1f} GiB"


def group_counts(rel_paths):
    """Count files per top-level entry; root-level files land in "(root)"."""
    groups = {}
    for rel in rel_paths:
        key = rel.split("/", 1)[0] if "/" in rel else "(root)"
        groups[key] = groups.get(key, 0) + 1
    return dict(sorted(groups.items()))


def render_plan(out_path, manifest):
    groups = group_counts([entry["path"] for entry in manifest["files"]])
    lines = [
        "Portable package plan (dry-run, nothing written)",
        f"  name        : {manifest['name']}",
        f"  version     : {manifest['version']}",
        f"  python      : {manifest['python']}",
        f"  out         : {out_path}",
        f"  files       : {manifest['counts']['files']}",
        f"  total size  : {_human_bytes(manifest['counts']['totalBytes'])}",
        "  groups      :",
    ]
    for name, count in groups.items():
        lines.append(f"    {name:<12} {count}")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Build a portable, Python-only dashboard package (zip).",
    )
    parser.add_argument(
        "--root", default=str(ROOT),
        help="Project root to package (default: repository root)",
    )
    parser.add_argument(
        "--out", default=None,
        help="Output zip path; relative paths resolve against --root "
             "(default: dist/windy-dashboard-portable-v<version>.zip)",
    )
    parser.add_argument(
        "--version", default=None,
        help="Package version (default: version from frontend/package.json)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print the packaging plan without writing the zip",
    )
    parser.add_argument(
        "--skip-verify", action="store_true",
        help="Do not fail when frontend/dist is missing (backend-only package)",
    )
    args = parser.parse_args(argv)

    root = Path(args.root).expanduser().resolve()
    try:
        if not root.is_dir():
            raise PackagingError("ROOT_NOT_FOUND", f"root directory not found: {root}")
        version = args.version or read_version(root)
        out_path = Path(args.out).expanduser() if args.out else Path("dist") / (
            f"windy-dashboard-portable-v{version}.zip"
        )
        if not out_path.is_absolute():
            out_path = root / out_path
        files = collect_files(root, root / "frontend" / "dist",
                              verify=not args.skip_verify)
        manifest = build_manifest(version, files, root)
        if args.dry_run:
            print(render_plan(out_path, manifest))
            return 0
        result = create_zip(root, files, out_path, manifest)
    except PackagingError as err:
        print(f"package failed [{err.code}]: {err.text}", file=sys.stderr)
        return 2

    print(
        f"Created {result['out']}: {result['files']} files, "
        f"{_human_bytes(result['bytes'])}, sha256 {result['sha256']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
