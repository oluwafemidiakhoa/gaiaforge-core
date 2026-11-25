import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from gaiaforge.sandbox import SandboxError, sandbox_verify, compare_sandbox_runs

IMAGE = "python@sha256:" + "a" * 64


class SandboxTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name) / "repo"
        (self.repo / "tests").mkdir(parents=True)
        (self.repo / "tests" / "test_example.py").write_text(
            "import unittest\nclass Example(unittest.TestCase):\n    def test_ok(self): self.assertTrue(True)\n",
            encoding="utf-8")

    def test_explicit_permission_required(self):
        with self.assertRaises(PermissionError):
            sandbox_verify(self.repo, image=IMAGE)

    def test_unpinned_image_rejected(self):
        with self.assertRaises(SandboxError):
            sandbox_verify(self.repo, image="python:3.12", authorized=True)

    def test_missing_docker_fails_closed(self):
        with patch("gaiaforge.sandbox.shutil.which", return_value=None):
            with self.assertRaisesRegex(SandboxError, "Docker is unavailable"):
                sandbox_verify(self.repo, image=IMAGE, authorized=True)

    def test_missing_image_never_triggers_pull(self):
        from subprocess import CompletedProcess
        with patch("gaiaforge.sandbox.shutil.which", return_value="docker"), \
             patch("gaiaforge.sandbox.subprocess.run", return_value=CompletedProcess([], 1)) as run:
            with self.assertRaisesRegex(SandboxError, "not present locally"):
                sandbox_verify(self.repo, image=IMAGE, authorized=True)
            self.assertEqual(run.call_args.args[0][:3], ["docker", "image", "inspect"])

    def test_builds_hardened_docker_command(self):
        from subprocess import CompletedProcess
        def runner(cmd, **kwargs):
            if cmd[1:3] == ["image", "inspect"]:
                return CompletedProcess(cmd, 0, "{}", "")
            self.assertIn("--network=none", cmd)
            self.assertIn("--read-only", cmd)
            self.assertIn("--cap-drop=ALL", cmd)
            self.assertIn("--pull=never", cmd)
            self.assertIn("--user=65534:65534", cmd)
            self.assertIn("--memory=512m", cmd)
            self.assertTrue(any("readonly" in arg and "type=bind" in arg for arg in cmd))
            return CompletedProcess(cmd, 0, "ok", "")
        with patch("gaiaforge.sandbox.shutil.which", return_value="docker"), \
             patch("gaiaforge.sandbox.subprocess.run", side_effect=runner):
            report = sandbox_verify(self.repo, image=IMAGE, authorized=True)
        self.assertTrue(report["passed"])
        self.assertFalse(report["release_authorized"])
        self.assertEqual(report["backend"], "docker")

    def test_snapshot_excludes_sensitive_and_git_files(self):
        from subprocess import CompletedProcess
        (self.repo / ".env").write_text("SECRET=never-mount", encoding="utf-8")
        (self.repo / ".git").mkdir()
        (self.repo / ".git" / "config").write_text("private", encoding="utf-8")
        (self.repo / "src").mkdir()
        (self.repo / "src" / "main.py").write_text("VALUE = 1\n", encoding="utf-8")

        def runner(command, **kwargs):
            if command[1:3] == ["image", "inspect"]:
                return CompletedProcess(command, 0, "{}", "")
            mount = command[command.index("--mount") + 1]
            source = Path(mount.split("src=", 1)[1].split(",dst=", 1)[0])
            self.assertFalse((source / ".env").exists())
            self.assertFalse((source / ".git").exists())
            self.assertEqual((source / "src" / "main.py").read_text(), "VALUE = 1\n")
            self.assertTrue((source / "tests" / "test_example.py").exists())
            return CompletedProcess(command, 0, "ok", "")

        with patch("gaiaforge.sandbox.shutil.which", return_value="docker"), \
             patch("gaiaforge.sandbox.subprocess.run", side_effect=runner):
            result = sandbox_verify(self.repo, image=IMAGE, authorized=True)
        self.assertTrue(result["source_snapshot_filtered"])
        self.assertIn("snapshot_sha256", result)
        self.assertEqual((self.repo / ".env").read_text(), "SECRET=never-mount")

    def test_snapshot_excessive_file_size_is_blocked(self):
        (self.repo / "large.py").write_bytes(b"x" * 2_000_001)
        from subprocess import CompletedProcess
        with patch("gaiaforge.sandbox.shutil.which", return_value="docker"), \
             patch("gaiaforge.sandbox.subprocess.run", return_value=CompletedProcess([], 0, "", "")):
            with self.assertRaisesRegex(SandboxError, "size limit"):
                sandbox_verify(self.repo, image=IMAGE, authorized=True)

    def test_timeout_removes_named_container(self):
        import subprocess
        commands = []
        def runner(cmd, **kwargs):
            commands.append(cmd)
            if cmd[1] == "image":
                return subprocess.CompletedProcess(cmd, 0, "{}", "")
            if cmd[1] == "run":
                raise subprocess.TimeoutExpired(cmd, 1)
            if cmd[1:3] == ["rm", "-f"]:
                return subprocess.CompletedProcess(cmd, 0, "", "")
            raise AssertionError(cmd)
        with patch("gaiaforge.sandbox.shutil.which", return_value="docker"), \
             patch("gaiaforge.sandbox.subprocess.run", side_effect=runner):
            report = sandbox_verify(self.repo, image=IMAGE, authorized=True)
        self.assertTrue(report["timed_out"])
        self.assertEqual(commands[2][1:3], ["rm", "-f"])
        self.assertEqual(commands[2][3], commands[1][4])

    def test_cleanup_failure_fails_closed(self):
        import subprocess
        def runner(cmd, **kwargs):
            if cmd[1] == "image":
                return subprocess.CompletedProcess(cmd, 0, "{}", "")
            if cmd[1] == "run":
                raise subprocess.TimeoutExpired(cmd, 1)
            return subprocess.CompletedProcess(cmd, 1, "", "error")
        with patch("gaiaforge.sandbox.shutil.which", return_value="docker"), \
             patch("gaiaforge.sandbox.subprocess.run", side_effect=runner):
            with self.assertRaisesRegex(SandboxError, "cleanup not verified"):
                sandbox_verify(self.repo, image=IMAGE, authorized=True)

    def test_test_tree_symlink_rejected(self):
        p = self.repo / "tests" / "link.py"
        try:
            p.symlink_to(self.repo / "tests" / "test_example.py")
        except OSError as exc:
            if getattr(exc, "winerror", None) == 1314:
                self.skipTest("Windows symlink creation privilege unavailable")
            raise
        with self.assertRaises(SandboxError):
            sandbox_verify(self.repo, image=IMAGE, authorized=True)

    def test_without_tests_rejected(self):
        (self.repo / "tests" / "test_example.py").unlink()
        with self.assertRaises(SandboxError):
            sandbox_verify(self.repo, image=IMAGE, authorized=True)

    def test_comparison_requires_matching_suite(self):
        a = {"suite_sha256": "a", "image": IMAGE, "check": "unittest", "passed": False,
             "backend": "docker", "timed_out": False}
        b = dict(a, suite_sha256="b", passed=True)
        self.assertFalse(compare_sandbox_runs(a, b)["comparable"])
        b["suite_sha256"] = "a"
        result = compare_sandbox_runs(a, b)
        self.assertTrue(result["newly_passing"])
        self.assertFalse(result["recommend_promotion"])

    def test_refuses_ledger_in_repo(self):
        from subprocess import CompletedProcess
        with patch("gaiaforge.sandbox.shutil.which", return_value="docker"), \
             patch("gaiaforge.sandbox.subprocess.run", return_value=CompletedProcess([], 0, "", "")):
            with self.assertRaisesRegex(SandboxError, "ledger must be outside"):
                sandbox_verify(self.repo, image=IMAGE, authorized=True,
                               evidence_ledger=self.repo / "ledger.jsonl")


if __name__ == "__main__":
    unittest.main()
