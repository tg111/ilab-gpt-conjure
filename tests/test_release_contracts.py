from __future__ import annotations

import json
import re
import subprocess
import tempfile
import tomllib
import unittest
from pathlib import Path

from codex_image.version import APP_VERSION


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_LICENSE = "AGPL-3.0-only"
PINNED_ACTIONS = {
    "actions/checkout": ("3d3c42e5aac5ba805825da76410c181273ba90b1", "v7.0.1"),
    "actions/setup-python": ("ece7cb06caefa5fff74198d8649806c4678c61a1", "v6.3.0"),
    "actions/setup-node": ("249970729cb0ef3589644e2896645e5dc5ba9c38", "v6.5.0"),
}


class ReleaseContractTests(unittest.TestCase):
    def test_public_repository_tracks_design_and_rejects_local_agent_rules(self) -> None:
        tracked = subprocess.run(
            ["git", "ls-files", "-z"], cwd=ROOT, check=True, capture_output=True, text=True,
        ).stdout.split("\0")
        self.assertIn("DESIGN.md", tracked)
        self.assertTrue((ROOT / "DESIGN.md").is_file())
        self.assertFalse([
            path for path in tracked
            if path in {"AGENT.md", "AGENTS.md"} or path.startswith("docs/superpowers/")
        ], "Private agent rules must not enter the public index")

        workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("test ! -e AGENT.md", workflow)
        self.assertIn("test ! -e AGENTS.md", workflow)
        self.assertIn("test -f DESIGN.md", workflow)

    def test_runtime_version_is_the_single_release_version_source(self) -> None:
        version_source = (ROOT / "codex_image" / "version.py").read_text(encoding="utf-8")
        self.assertEqual(
            re.findall(r'^APP_VERSION = "([^"]+)"$', version_source, re.MULTILINE),
            [APP_VERSION],
        )

        pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        project = pyproject["project"]
        self.assertNotIn("version", project)
        self.assertIn("version", project["dynamic"])
        self.assertEqual(
            pyproject["tool"]["setuptools"]["dynamic"]["version"]["attr"],
            "codex_image.version.APP_VERSION",
        )

    def test_python_package_discovery_excludes_workspace_and_includes_webui_assets(self) -> None:
        pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        setuptools = pyproject["tool"]["setuptools"]

        self.assertRegex(pyproject["build-system"]["requires"][0], r"^setuptools==[^=]+$")
        self.assertEqual(setuptools["packages"]["find"]["include"], ["codex_image*"])
        self.assertFalse(setuptools["packages"]["find"]["namespaces"])
        webui_data = setuptools["package-data"]["codex_image.webui"]
        self.assertIn("static/*", webui_data)
        self.assertIn("static/**/*", webui_data)

    def test_python_package_publishes_the_license_identifier(self) -> None:
        pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

        self.assertEqual(pyproject["project"]["license"], EXPECTED_LICENSE)

    def test_runtime_dependencies_are_exactly_pinned_and_hash_checked(self) -> None:
        pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        dependencies = pyproject["project"]["dependencies"]
        self.assertIn("certifi==2026.10.23", dependencies)
        for dependency in dependencies:
            self.assertRegex(dependency, r"^[A-Za-z0-9_.-]+(?:\[[A-Za-z0-9_.-]+\])?==[^=]+$")

        requirements = (ROOT / "requirements-webui.txt").read_text(encoding="utf-8")
        self.assertIn("--require-hashes", requirements)
        self.assertNotIn(">=", requirements)
        self.assertNotIn("~=", requirements)
        package_lines = [
            line.strip()
            for line in requirements.splitlines()
            if line
            and not line.startswith((" ", "#", "--"))
        ]
        self.assertGreaterEqual(len(package_lines), 15)
        for line in package_lines:
            self.assertRegex(line, r"^[A-Za-z0-9_.-]+(?:\[[A-Za-z0-9_.-]+\])?==")

        self.assertRegex(
            requirements,
            r"(?m)^colorama==[^=]+ \\$",
            "Windows-only runtime dependencies must be present in the cross-platform lock",
        )

        for relative in (
            "Start WebUI.command",
            "Start WebUI Debug.command",
            "Start WebUI.bat",
        ):
            text = (ROOT / relative).read_text(encoding="utf-8")
            self.assertIn("--require-hashes", text, relative)

    def test_build_backend_is_in_the_hash_checked_audit_lock(self) -> None:
        pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        build_input = (ROOT / "requirements-build.in").read_text(encoding="utf-8")
        build_lock = (ROOT / "requirements-build.txt").read_text(encoding="utf-8")
        self.assertIn("--require-hashes", build_lock)
        for requirement in pyproject["build-system"]["requires"]:
            self.assertIn(requirement, build_input)
            self.assertIn(requirement + " \\", build_lock)
        workflow = (ROOT / ".github/workflows/dependency-audit.yml").read_text(encoding="utf-8")
        for lock in ("requirements-webui.txt", "requirements-build.txt"):
            self.assertIn(lock, workflow)
        self.assertIn("npm audit --package-lock-only", workflow)
        self.assertIn("schedule:", workflow)

    def test_dependency_check_detects_outdated_direct_runtime_package(self) -> None:
        from codex_image.dependency_check import dependency_mismatches

        with tempfile.TemporaryDirectory() as directory:
            requirements_path = Path(directory) / "requirements.txt"
            requirements_path.write_text(
                "--require-hashes\n"
                "fastapi==1.2.3 \\\n"
                "    --hash=sha256:" + ("0" * 64) + "\n"
                "httpx==4.5.6 \\\n"
                "    --hash=sha256:" + ("1" * 64) + "\n",
                encoding="utf-8",
            )

            installed = {"fastapi": "1.2.2", "httpx": "4.5.6"}
            mismatches = dependency_mismatches(
                requirements_path,
                distribution_version=installed.__getitem__,
                package_names=("fastapi", "httpx"),
            )

        self.assertEqual(mismatches, ["fastapi: installed 1.2.2, required 1.2.3"])

    def test_dependency_check_detects_outdated_transitive_runtime_package(self) -> None:
        from codex_image.dependency_check import dependency_mismatches

        with tempfile.TemporaryDirectory() as directory:
            requirements_path = Path(directory) / "requirements.txt"
            requirements_path.write_text(
                "fastapi==1.2.3\n"
                "uvicorn==2.3.4\n"
                "python-multipart==3.4.5\n"
                "httpx==4.5.6\n"
                "pillow==5.6.7\n"
                "idna==8.9.0\n",
                encoding="utf-8",
            )
            installed = {
                "fastapi": "1.2.3",
                "uvicorn": "2.3.4",
                "python-multipart": "3.4.5",
                "httpx": "4.5.6",
                "pillow": "5.6.7",
                "idna": "8.8.0",
            }
            mismatches = dependency_mismatches(
                requirements_path,
                distribution_version=installed.__getitem__,
            )

        self.assertEqual(mismatches, ["idna: installed 8.8.0, required 8.9.0"])

    def test_ci_has_python_quality_and_security_gates(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

        for expected in (
            "ruff check",
            "bandit",
            "pip-audit",
            "coverage report --fail-under=",
        ):
            self.assertIn(expected, workflow)

    def test_workflows_pin_every_action_to_a_full_commit_sha(self) -> None:
        workflows = "\n".join(
            path.read_text(encoding="utf-8")
            for path in sorted((ROOT / ".github" / "workflows").glob("*.yml"))
        )
        uses = re.findall(r"^\s*uses:\s*([^@\s]+)@([^\s#]+)(?:\s+#\s*(\S+))?", workflows, re.MULTILINE)
        self.assertTrue(set(PINNED_ACTIONS).issubset({action for action, _, _ in uses}))

        for action, revision, comment in uses:
            self.assertRegex(revision, r"^[0-9a-f]{40}$", action)
            if action in PINNED_ACTIONS:
                expected_revision, expected_comment = PINNED_ACTIONS[action]
                self.assertEqual(revision, expected_revision)
                self.assertEqual(comment, expected_comment)


if __name__ == "__main__":
    unittest.main()
