"""Direct unittest privacy journeys for the selected installed cppulse package.

The failing native executable and optional distribution metadata are authored
fixtures. They exercise real collection paths, not native-analysis correctness
or authenticity of an optional producer. Root supplies the installed-prefix
assertion and network denial when qualifying installed artifacts.
"""

from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import cppulse
from cppulse import cli


@contextmanager
def working_directory(path: Path):
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


@unittest.skipUnless(os.name == "posix", "Authored executable-probe fixture uses POSIX")
class DiagnosticPrivacy112(unittest.TestCase):
    def setUp(self) -> None:
        expected = os.environ.get("CPPULSE_DIAGNOSTIC_EXPECT_PREFIX112")
        if expected:
            self.assertTrue(
                Path(cli.__file__).resolve().is_relative_to(Path(expected).resolve()),
                f"cppulse.cli is outside the required installed prefix: {cli.__file__}",
            )
        parent = os.environ.get("CPPULSE_PRIVACY_FIXTURES112")
        self.base = Path(
            tempfile.mkdtemp(prefix="PATH_SENTINEL112 private-", dir=parent)
        )
        self.project = self.base / "private project"
        self.home = self.base / "private home"
        self.project.mkdir()
        self.home.mkdir()
        self.secrets = {
            "source": "SOURCE_EXCERPT_SENTINEL112",
            "config": "CONFIG_SECRET_SENTINEL112",
            "credential": "CREDENTIAL_SECRET_SENTINEL112",
            "token": "TOKEN_SECRET_SENTINEL112",
            "environment": "ENVIRONMENT_SECRET_SENTINEL112",
            "remote": "REMOTE_PASSWORD_SENTINEL112",
            "stdout": "PROBE_STDOUT_SECRET_SENTINEL112",
            "stderr": "PROBE_STDERR_SECRET_SENTINEL112",
            "path": str(self.base),
        }
        (self.project / "main.cpp").write_text(
            "// " + self.secrets["source"] + "\nint private_function() { return 1; }\n"
        )
        (self.project / ".cppulserc.json").write_text(
            json.dumps({"private_configuration": self.secrets["config"]})
        )
        (self.project / ".env").write_text("API_TOKEN=" + self.secrets["token"] + "\n")
        git = self.project / ".git"
        git.mkdir()
        (git / "config").write_text(
            '[remote "origin"]\n  url = https://private-user:'
            + self.secrets["remote"]
            + "@example.invalid/private/repository.git\n"
        )
        (self.home / ".netrc").write_text(
            "machine example.invalid login private-user password "
            + self.secrets["credential"]
            + "\n"
        )
        aws = self.home / ".aws"
        aws.mkdir()
        (aws / "credentials").write_text(
            "[default]\naws_secret_access_key=" + self.secrets["credential"] + "\n"
        )
        self.receipt = self.base / "actual-probe-invocations.jsonl"
        self.probe = self.base / "private-native-probe"
        self.probe.write_text(
            f"#!{sys.executable}\n"
            "import json,sys\nfrom pathlib import Path\n"
            f"with Path({str(self.receipt)!r}).open('a') as stream:\n"
            "    stream.write(json.dumps({'argv':sys.argv[1:],'exit_status':7})+'\\n')\n"
            f"print({self.secrets['stdout']!r})\n"
            f"print({self.secrets['stderr']!r},file=sys.stderr)\n"
            "raise SystemExit(7)\n"
        )
        self.probe.chmod(0o700)
        self.originals = self._file_pins()

    def _file_pins(self) -> dict[str, tuple[object, ...]]:
        result = {}
        for path in sorted(self.base.rglob("*")):
            if path.is_file():
                info = path.lstat()
                result[str(path)] = (
                    hashlib.sha256(path.read_bytes()).hexdigest(),
                    info.st_mode,
                    info.st_uid,
                    info.st_gid,
                    info.st_mtime_ns,
                )
        return result

    def _unchanged(self) -> None:
        current = self._file_pins()
        for path, expected in self.originals.items():
            self.assertIn(path, current)
            self.assertEqual(current[path], expected, path)

    def _environment(self, *, missing_native: bool = False) -> dict[str, str]:
        environment = os.environ.copy()
        for name in (
            "CPPULSE_ANALYZER",
            "CPPULSE_NATIVE_PREFIX",
            "CPPULSE_CLANG_RESOURCE_DIR",
        ):
            environment.pop(name, None)
        environment.update(
            HOME=str(self.home),
            USERPROFILE=str(self.home),
            CPPULSE_ANALYZER=(
                str(self.base / "missing-private-analyzer")
                if missing_native
                else str(self.probe)
            ),
            API_TOKEN=self.secrets["token"],
            AWS_SECRET_ACCESS_KEY=self.secrets["credential"],
            GITHUB_TOKEN=self.secrets["token"],
            CPPULSE_PRIVATE_ENV112=self.secrets["environment"],
            PYTHONDONTWRITEBYTECODE="1",
        )
        # Select the actual package imported by this direct unittest invocation;
        # the fixture cwd never supplies cppulse or pytest conftest injection.
        environment["PYTHONPATH"] = str(Path(cppulse.__file__).resolve().parent.parent)
        return environment

    def _read_bundle(self, path: Path) -> dict[str, object]:
        with zipfile.ZipFile(path) as archive:
            self.assertIsNone(archive.testzip())
            self.assertEqual(archive.namelist(), ["diagnostics.json"])
            collected = [archive.comment]
            for member in archive.infolist():
                self.assertFalse(member.is_dir())
                collected.extend(
                    [
                        member.filename.encode(),
                        member.extra,
                        member.comment,
                        archive.read(member),
                    ]
                )
            all_members = b"\n".join(collected)
            for name, secret in self.secrets.items():
                self.assertNotIn(secret.encode(), all_members, name)
            for excluded in (b"main.cpp", b".cppulserc", b".git/config", b".netrc"):
                self.assertNotIn(excluded, all_members)
            report = json.loads(archive.read("diagnostics.json"))
        self.assertEqual(report["cppulse"], cppulse.__version__)
        self.assertEqual(report["platform"], sys.platform)
        self.assertRegex(report["python"], r"^\d+\.\d+\.\d+")
        self.assertIsInstance(report["optional"], dict)
        self.assertIn("created_at", report)
        self.assertIn("redaction", report)
        self.assertTrue(
            set(report)
            <= {
                "cppulse",
                "python",
                "platform",
                "machine",
                "optional",
                "native",
                "created_at",
                "redaction",
            }
        )
        self.assertTrue(
            set(report["native"])
            <= {
                "available",
                "startup_exit",
                "error_code",
            }
        )
        return report

    def _public_cli(self, environment: dict[str, str], name: str):
        output = self.base / name
        command = [
            sys.executable,
            "-m",
            "cppulse",
            "diagnostics",
            "--output",
            str(output),
        ]
        result = subprocess.run(
            command,
            cwd=self.project,
            env=environment,
            capture_output=True,
            text=True,
            timeout=40,
            check=False,
        )
        (self.base / (name + ".stdout")).write_text(result.stdout)
        (self.base / (name + ".stderr")).write_text(result.stderr)
        (self.base / (name + ".command.json")).write_text(
            json.dumps(
                {
                    "argv": command,
                    "exit_status": result.returncode,
                    "selected_cppulse_module": str(Path(cli.__file__).resolve()),
                },
                indent=2,
            )
            + "\n"
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        response = json.loads(result.stdout)
        self.assertEqual(
            response, {"diagnostics": str(output.resolve()), "uploaded": False}
        )
        self.assertEqual(result.stderr, "")
        return self._read_bundle(output)

    def test_function_redacts_real_failed_probe_and_private_user_inputs(self) -> None:
        environment = self._environment()
        with (
            patch.dict(os.environ, environment, clear=True),
            working_directory(self.project),
        ):
            raw = cli.doctor()
            # The real collector reached the authored executable. No doctor or
            # subprocess outcomes are mocked to manufacture this redaction case.
            self.assertEqual(raw["native"]["path"], str(self.probe))
            self.assertIn(self.secrets["stderr"], raw["native"]["error"])
            output = cli.diagnostic_bundle(self.base / "function-default.zip")
        report = self._read_bundle(output)
        self.assertEqual(report["native"], {"available": False, "startup_exit": 7})
        calls = [json.loads(line) for line in self.receipt.read_text().splitlines()]
        self.assertEqual(len(calls), 2)
        self.assertTrue(
            all(row == {"argv": ["--help"], "exit_status": 7} for row in calls)
        )
        self._unchanged()

    def test_public_cli_redacts_real_discovery_error_path_and_keeps_safe_code(
        self,
    ) -> None:
        report = self._public_cli(
            self._environment(missing_native=True), "discovery-default.zip"
        )
        self.assertEqual(
            report["native"],
            {
                "available": False,
                "error_code": "INVALID_NATIVE_INSTALL",
            },
        )
        self.assertFalse(self.receipt.exists())
        self._unchanged()

    def test_public_cli_excludes_token_from_actual_optional_metadata_producer(
        self,
    ) -> None:
        metadata_root = self.base / "private distribution metadata"
        distribution = metadata_root / "xgboost-1.0.dist-info"
        distribution.mkdir(parents=True)
        token = "privatetokenmetadata112abcdef"
        self.secrets["optional_metadata_token"] = token
        declared_version = "1.0+" + token
        (distribution / "METADATA").write_text(
            "Metadata-Version: 2.1\nName: xgboost\nVersion: " + declared_version + "\n"
        )
        (metadata_root / "xgboost.py").write_text(
            "# Authored optional-module presence fixture.\n"
        )
        self.originals = self._file_pins()
        environment = self._environment()
        environment["PYTHONPATH"] = (
            str(metadata_root) + os.pathsep + environment["PYTHONPATH"]
        )
        # Show the real importlib.metadata reader in the exact child environment
        # observes a valid local-version token; no malformed version mock or
        # invented doctor field is used as evidence of collection.
        producer = subprocess.run(
            [
                sys.executable,
                "-c",
                "from importlib import metadata; print(metadata.version('xgboost'))",
            ],
            cwd=self.project,
            env=environment,
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        (self.base / "metadata-producer.json").write_text(
            json.dumps(
                {
                    "exit_status": producer.returncode,
                    "stdout": producer.stdout,
                    "stderr": producer.stderr,
                    "metadata_file": str(distribution / "METADATA"),
                },
                indent=2,
            )
            + "\n"
        )
        self.assertEqual(producer.returncode, 0)
        self.assertEqual(producer.stdout.strip(), declared_version)
        report = self._public_cli(environment, "optional-metadata-default.zip")
        self.assertEqual(report["native"], {"available": False, "startup_exit": 7})
        self.assertTrue(report["optional"]["ml"]["installed"])
        self._unchanged()


if __name__ == "__main__":
    unittest.main(verbosity=2)
