import hashlib
import json
import os
import platform
import sys
import tempfile
import unittest
import zipfile
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import package_portable as packaging


def _write(root, rel, content="x"):
    path = os.path.join(root, *rel.split("/"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(content)
    return path


class TestCollectFiles(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        _write(self.root, "backend/main.py", "print('hi')\n")
        _write(self.root, "backend/requirements.txt", "fastapi\n")
        _write(self.root, "backend/.cache/geoip.json", "{}")
        _write(self.root, "backend/__pycache__/main.cpython-312.pyc", "bin")
        _write(self.root, "backend/maintenance/runner.py", "pass\n")
        _write(self.root, "frontend/dist/index.html", "<html></html>")
        _write(self.root, "frontend/dist/assets/app.js", "console.log(1)")
        _write(self.root, "frontend/src/App.vue", "<template></template>")
        _write(self.root, "scripts/a.py", "print('a')\n")
        _write(self.root, "scopeboard/index.html", "<html>sb</html>")
        _write(self.root, "scopeboard/data.json", "{}")
        _write(self.root, "README.md", "# readme\n")

    def tearDown(self):
        self.tmp.cleanup()

    def _rel_paths(self):
        files = packaging.collect_files(self.root, os.path.join(self.root, "frontend", "dist"))
        return [os.path.relpath(path, self.root).replace(os.sep, "/") for path in files]

    def test_collect_includes_expected_and_drops_runtime(self):
        rels = self._rel_paths()
        for expected in (
            "backend/main.py",
            "backend/maintenance/runner.py",
            "backend/requirements.txt",
            "frontend/dist/index.html",
            "frontend/dist/assets/app.js",
            "scripts/a.py",
            "scopeboard/index.html",
            "README.md",
        ):
            self.assertIn(expected, rels)
        for excluded in (
            "backend/.cache/geoip.json",
            "backend/__pycache__/main.cpython-312.pyc",
            "frontend/src/App.vue",
            "scopeboard/data.json",
        ):
            self.assertNotIn(excluded, rels)
        self.assertEqual(rels, sorted(rels))
        for path in packaging.collect_files(self.root, os.path.join(self.root, "frontend", "dist")):
            self.assertTrue(os.path.isabs(path))
            self.assertTrue(os.path.isfile(path))

    def test_missing_frontend_dist_raises(self):
        empty = os.path.join(self.root, "empty-root")
        os.makedirs(os.path.join(empty, "backend"))
        with self.assertRaises(packaging.PackagingError) as ctx:
            packaging.collect_files(empty, os.path.join(empty, "frontend", "dist"))
        self.assertEqual(ctx.exception.code, "FRONTEND_NOT_BUILT")

    def test_skip_verify_allows_no_dist(self):
        empty = os.path.join(self.root, "empty-root")
        os.makedirs(os.path.join(empty, "backend"))
        files = packaging.collect_files(empty, os.path.join(empty, "frontend", "dist"),
                                        verify=False)
        self.assertEqual(files, [])


class TestManifestAndZip(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        _write(self.root, "backend/main.py", "print('hi')\n")
        _write(self.root, "backend/requirements.txt", "fastapi\n")
        _write(self.root, "backend/.cache/geoip.json", "{}")
        _write(self.root, "backend/__pycache__/main.cpython-312.pyc", "bin")
        _write(self.root, "frontend/dist/index.html", "<html></html>")
        _write(self.root, "frontend/dist/assets/app.js", "console.log(1)")
        _write(self.root, "frontend/src/App.vue", "<template></template>")
        _write(self.root, "scripts/a.py", "print('a')\n")
        _write(self.root, "scopeboard/index.html", "<html>sb</html>")
        _write(self.root, "scopeboard/data.json", "{}")
        _write(self.root, "README.md", "# readme\n")
        _write(self.root, "frontend/package.json", json.dumps({"version": "9.9.9"}))
        self.files = packaging.collect_files(
            self.root, os.path.join(self.root, "frontend", "dist"))

    def tearDown(self):
        self.tmp.cleanup()

    def test_build_manifest_version_counts_and_hashes(self):
        manifest = packaging.build_manifest("1.2.3", self.files, self.root)
        self.assertEqual(manifest["name"], "windy-smart-dashboard")
        self.assertEqual(manifest["version"], "1.2.3")
        self.assertEqual(manifest["python"], platform.python_version())
        self.assertTrue(manifest["builtAt"].endswith("Z"))
        self.assertEqual(manifest["counts"]["files"], len(self.files))
        self.assertEqual(
            manifest["counts"]["totalBytes"],
            sum(os.path.getsize(path) for path in self.files),
        )
        by_path = {entry["path"]: entry for entry in manifest["files"]}
        self.assertIn("backend/main.py", by_path)
        self.assertNotIn("scopeboard/data.json", by_path)
        self.assertNotIn("frontend/src/App.vue", by_path)
        with open(os.path.join(self.root, "backend", "main.py"), "rb") as handle:
            expected = hashlib.sha256(handle.read()).hexdigest()
        self.assertEqual(by_path["backend/main.py"]["sha256"], expected)
        self.assertEqual(
            by_path["backend/main.py"]["size"],
            os.path.getsize(os.path.join(self.root, "backend", "main.py")),
        )
        self.assertEqual(
            [entry["path"] for entry in manifest["files"]],
            sorted(entry["path"] for entry in manifest["files"]),
        )

    def test_read_version_from_package_json(self):
        self.assertEqual(packaging.read_version(self.root), "9.9.9")
        bare = os.path.join(self.root, "bare")
        os.makedirs(bare)
        self.assertEqual(packaging.read_version(bare), "0.0.0")

    def test_create_zip_manifest_first_and_no_runtime_data(self):
        manifest = packaging.build_manifest("1.2.3", self.files, self.root)
        out_path = os.path.join(self.root, "out", "pkg.zip")
        result = packaging.create_zip(self.root, self.files, out_path, manifest)
        self.assertEqual(result["out"], os.path.abspath(out_path))
        self.assertTrue(os.path.isfile(out_path))
        self.assertEqual(result["bytes"], os.path.getsize(out_path))
        with open(out_path, "rb") as handle:
            self.assertEqual(result["sha256"], hashlib.sha256(handle.read()).hexdigest())
        with zipfile.ZipFile(out_path) as archive:
            names = archive.namelist()
            self.assertEqual(names[0], "MANIFEST.json")
            self.assertIn("backend/main.py", names)
            self.assertIn("frontend/dist/assets/app.js", names)
            self.assertIn("scripts/a.py", names)
            self.assertIn("scopeboard/index.html", names)
            self.assertFalse([n for n in names if "/.cache/" in n or n.endswith("data.json")])
            self.assertFalse([n for n in names if "__pycache__" in n or n.endswith(".pyc")])
            on_disk = json.loads(archive.read("MANIFEST.json").decode("utf-8"))
            self.assertEqual(on_disk["version"], "1.2.3")
            self.assertEqual(on_disk["counts"]["files"], len(names) - 1)
            self.assertEqual(result["files"], len(names) - 1)


class TestCli(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        _write(self.root, "backend/main.py", "print('hi')\n")
        _write(self.root, "backend/requirements.txt", "fastapi\n")
        _write(self.root, "frontend/dist/index.html", "<html></html>")
        _write(self.root, "frontend/src/App.vue", "<template></template>")
        _write(self.root, "scopeboard/data.json", "{}")
        _write(self.root, "frontend/package.json", json.dumps({"version": "4.5.6"}))

    def tearDown(self):
        self.tmp.cleanup()

    def _run(self, args):
        out, err = StringIO(), StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = packaging.main(args)
        return code, out.getvalue(), err.getvalue()

    def test_dry_run_writes_nothing(self):
        code, out, _ = self._run(["--dry-run", "--root", self.root])
        self.assertEqual(code, 0)
        self.assertIn("dry-run", out)
        self.assertIn("4.5.6", out)
        self.assertIn("files", out)
        self.assertIn("frontend", out)
        self.assertFalse(os.path.exists(os.path.join(self.root, "dist")))

    def test_build_writes_zip_with_default_name(self):
        code, out, _ = self._run(["--root", self.root])
        self.assertEqual(code, 0)
        expected = os.path.join(self.root, "dist",
                                "windy-dashboard-portable-v4.5.6.zip")
        self.assertTrue(os.path.isfile(expected))
        self.assertIn("sha256", out)
        with zipfile.ZipFile(expected) as archive:
            self.assertEqual(archive.namelist()[0], "MANIFEST.json")

    def test_missing_dist_exits_2_and_reports_code(self):
        os.remove(os.path.join(self.root, "frontend", "dist", "index.html"))
        code, _, err = self._run(["--root", self.root])
        self.assertEqual(code, 2)
        self.assertIn("FRONTEND_NOT_BUILT", err)
        self.assertFalse(os.path.exists(os.path.join(self.root, "dist")))

    def test_skip_verify_builds_backend_only(self):
        os.remove(os.path.join(self.root, "frontend", "dist", "index.html"))
        code, out, _ = self._run(["--root", self.root, "--skip-verify",
                                  "--out", "dist/backend-only.zip"])
        self.assertEqual(code, 0)
        self.assertIn("backend-only.zip", out)
        with zipfile.ZipFile(os.path.join(self.root, "dist", "backend-only.zip")) as archive:
            names = archive.namelist()
            self.assertIn("backend/main.py", names)
            self.assertFalse([n for n in names if n.startswith("frontend/dist/")])


if __name__ == "__main__":
    unittest.main()
