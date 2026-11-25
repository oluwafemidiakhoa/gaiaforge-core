"""Fail-closed, opt-in container verification. Never falls back to host execution.

Security boundary is the Docker daemon and host kernel; this does not claim a VM or
an adversarially certified sandbox. Use a dedicated, hardened Docker host for any
untrusted code. Docker access itself is privileged and must be separately authorized.
"""
from __future__ import annotations

import hashlib
import os
import uuid
import re
import shutil
import stat
import tempfile
import subprocess
import time
from pathlib import Path

from .ledger import append_record

_IMAGE = re.compile(r"^[a-z0-9][a-z0-9._:/-]*@sha256:[0-9a-f]{64}$")
_MAX_OUTPUT = 16_000
_ALLOWED = {"unittest": ("python", "-B", "-m", "unittest", "discover", "-s", "tests", "-v")}
_EXCLUDED = {".git", ".venv", "venv", "__pycache__", "node_modules", "dist", "build", ".gaiaforge", ".pytest_cache", ".mypy_cache"}
_SNAPSHOT_EXTENSIONS = {".py", ".toml", ".json", ".yaml", ".yml", ".txt", ".md", ".ini", ".cfg"}
_MAX_SNAPSHOT_BYTES = 20_000_000
_MAX_FILE_BYTES = 2_000_000


class SandboxError(ValueError):
    """A run has been blocked before starting or its evidence cannot be trusted."""


def _suite_digest(repo: Path) -> str:
    """Hash a fixed unittest suite (relative paths and contents) before execution."""
    root = repo / "tests"
    if root.is_symlink() or not root.is_dir():
        raise SandboxError("a real tests/ directory is required")
    digest = hashlib.sha256()
    count = 0
    for parent, dirs, files in os.walk(root, followlinks=False):
        for name in list(dirs):
            child = Path(parent) / name
            if child.is_symlink():
                raise SandboxError("symlinks in the test tree are forbidden")
            if name in _EXCLUDED:
                dirs.remove(name)
        for name in sorted(files):
            file = Path(parent) / name
            if file.is_symlink() or not file.is_file():
                raise SandboxError("symlinks or special test files are forbidden")
            if file.suffix != ".py":
                continue
            if file.stat().st_size > 256_000:
                raise SandboxError("test file is too large")
            content = file.read_bytes()
            digest.update(file.relative_to(root).as_posix().encode() + b"\0")
            digest.update(len(content).to_bytes(8, "big") + content)
            count += 1
            if count > 300:
                raise SandboxError("test suite too large")
    if count == 0:
        raise SandboxError("test suite has no Python files")
    return digest.hexdigest()


def _validate_repository(repo: Path) -> Path:
    """Validate source tree before a filtered, read-only snapshot is created."""
    if repo.is_symlink() or not repo.is_dir():
        raise SandboxError("repository must be a real directory")
    repo = repo.resolve(strict=True)
    count = 0
    for parent, dirs, files in os.walk(repo, followlinks=False):
        for name in list(dirs):
            child = Path(parent) / name
            if name in _EXCLUDED or name.startswith("."):
                dirs.remove(name)
            elif child.is_symlink():
                raise SandboxError("repository contains directory symlink")
        for name in files:
            if name.startswith("."):
                continue
            item = Path(parent) / name
            if item.is_symlink() or not stat.S_ISREG(item.stat(follow_symlinks=False).st_mode):
                raise SandboxError("repository contains symlink or special file")
            count += 1
            if count > 5000:
                raise SandboxError("repository exceeds file budget")
    _suite_digest(repo)
    return repo


def _snapshot_repository(repo: Path, destination: Path) -> str:
    """Copy allowlisted source files; never mount the caller's entire checkout.

    This is a privacy boundary against incidental secret exposure, not a guarantee
    against malicious code embedded in included source files.
    """
    digest = hashlib.sha256()
    total = 0
    count = 0
    for parent, dirs, files in os.walk(repo, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d not in _EXCLUDED and not d.startswith("."))
        for name in sorted(files):
            if name.startswith("."):
                continue
            src = Path(parent) / name
            if src.suffix.lower() not in _SNAPSHOT_EXTENSIONS:
                continue
            if src.is_symlink() or not src.is_file():
                raise SandboxError("unsafe source file in snapshot")
            relative = src.relative_to(repo)
            size = src.stat().st_size
            if size > _MAX_FILE_BYTES:
                raise SandboxError("snapshot file exceeds size limit")
            content = src.read_bytes()
            total += len(content)
            count += 1
            if total > _MAX_SNAPSHOT_BYTES or count > 5000:
                raise SandboxError("snapshot resource budget exceeded")
            dst = destination / relative
            dst.parent.mkdir(parents=True, exist_ok=True)
            if os.name != "nt":
                dst.parent.chmod(0o755)
            # Exclusive creation and never traverse a symlink created by source content.
            with dst.open("xb") as stream:
                stream.write(content)
            digest.update(relative.as_posix().encode("utf-8") + b"\0")
            digest.update(len(content).to_bytes(8, "big") + content)
    if not (destination / "tests").is_dir():
        raise SandboxError("snapshot has no test directory")
    return digest.hexdigest()


def _run_once(repo: Path, *, image: str, timeout: int, docker: str, check: str) -> dict:
    container_name = "gaiaforge-" + uuid.uuid4().hex
    command = [
        docker, "run", "--rm", "--name", container_name, "--pull=never", "--network=none", "--read-only",
        "--cap-drop=ALL", "--security-opt=no-new-privileges", "--pids-limit=64",
        "--memory=512m", "--cpus=1", "--user=65534:65534", "--init",
        "--tmpfs=/tmp:rw,noexec,nosuid,size=64m,mode=1777",
        "--env=PYTHONDONTWRITEBYTECODE=1", "--env=PYTHONPATH=/workspace/src",
        "--workdir=/workspace", "--mount", f"type=bind,src={repo},dst=/workspace,readonly",
        image, *_ALLOWED[check]
    ]
    began = time.monotonic()
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)
        exit_code = result.returncode
        timed_out = False
        output = (result.stdout or "") + "\n" + (result.stderr or "")
    except subprocess.TimeoutExpired as exc:
        # The Docker CLI can time out while the container remains alive.
        # Explicitly remove the exact per-run container before returning.
        try:
            cleanup = subprocess.run([docker, "rm", "-f", container_name], capture_output=True,
                                     text=True, timeout=10, check=False)
        except (OSError, subprocess.TimeoutExpired) as cleanup_exc:
            raise SandboxError("timed out; Docker container cleanup not verified") from cleanup_exc
        if cleanup.returncode != 0:
            raise SandboxError("timed out; Docker container cleanup not verified")
        exit_code = None
        timed_out = True
        output = (exc.stdout or b"") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        if isinstance(output, bytes):
            output = output.decode("utf-8", errors="replace")
    return {
        "check": check, "exit_code": exit_code, "passed": exit_code == 0 and not timed_out,
        "timed_out": timed_out, "elapsed_seconds": round(time.monotonic()-began, 3),
        "output_sha256": hashlib.sha256(output.encode("utf-8", errors="replace")).hexdigest(),
        "output_excerpt": output[-_MAX_OUTPUT:], "output_truncated": len(output) > _MAX_OUTPUT,
    }


def sandbox_verify(repo: Path, *, image: str, authorized: bool = False,
                   timeout: int = 60, check: str = "unittest", evidence_ledger: Path | None = None) -> dict:
    """Verify in a pinned, locally available Docker image. Never execute on the host."""
    if not authorized:
        raise PermissionError("container execution requires --authorize-execution")
    if check not in _ALLOWED:
        raise SandboxError("unsupported container check")
    if type(timeout) is not int or not 1 <= timeout <= 180:
        raise SandboxError("timeout must be 1 to 180 seconds")
    if not isinstance(image, str) or not _IMAGE.fullmatch(image):
        raise SandboxError("image must be an explicitly pinned image@sha256 digest")
    repo = _validate_repository(Path(repo))
    docker = shutil.which("docker")
    if docker is None:
        raise SandboxError("Docker is unavailable; host execution is forbidden")
    # Reject missing local images; never fetch or run mutable tags from this command.
    try:
        check_image = subprocess.run([docker, "image", "inspect", image], capture_output=True,
                                     text=True, timeout=10, check=False)
    except (subprocess.TimeoutExpired, OSError) as exc:
        raise SandboxError("could not inspect pinned container image") from exc
    if check_image.returncode != 0:
        raise SandboxError("pinned image not present locally or Docker unavailable")
    if evidence_ledger is not None:
        # Normalize both paths with the same canonicalization. On Windows,
        # TemporaryDirectory paths can contain 8.3 short-name aliases while
        # repo.resolve() expands them, so absolute() alone is insufficient.
        evidence_ledger = Path(evidence_ledger).resolve(strict=False)
        if evidence_ledger == repo or repo in evidence_ledger.parents:
            raise SandboxError("evidence ledger must be outside tested repository")
    suite_id = _suite_digest(repo)
    with tempfile.TemporaryDirectory(prefix="gaiaforge-snapshot-") as folder:
        snapshot = Path(folder)
        # Container runs as an unprivileged UID and must traverse the bind root.
        if os.name != "nt":
            snapshot.chmod(0o755)
        snapshot_id = _snapshot_repository(repo, snapshot)
        if _suite_digest(snapshot) != suite_id:
            raise SandboxError("source test suite changed during snapshot")
        result = _run_once(snapshot, image=image, timeout=timeout, docker=docker, check=check)
        if _suite_digest(snapshot) != suite_id:
            raise SandboxError("snapshot test suite changed during verification")
    report = {"repository": str(repo), "suite_sha256": suite_id,
              "snapshot_sha256": snapshot_id, "image": image,
              "backend": "docker", "network_disabled": True, "read_only_workspace": True,
              "source_snapshot_filtered": True, "sandboxed": True,
              "release_authorized": False, **result}
    if evidence_ledger is not None:
        rec = append_record(evidence_ledger, "container_verification", {
            k: v for k, v in report.items() if k != "output_excerpt"})
        report["ledger_hash"] = rec["hash"]
    return report


def compare_sandbox_runs(baseline: dict, candidate: dict) -> dict:
    """No automatic promotion; compare only equal test suites, images and checks."""
    required = {"suite_sha256", "image", "check", "passed", "backend", "timed_out"}
    if not all(isinstance(x, dict) and required <= x.keys() for x in (baseline, candidate)):
        raise SandboxError("missing verification evidence")
    comparable = (baseline["suite_sha256"] == candidate["suite_sha256"]
                  and baseline["image"] == candidate["image"]
                  and baseline["check"] == candidate["check"]
                  and baseline["backend"] == candidate["backend"] == "docker"
                  and all(type(x["passed"]) is bool and type(x["timed_out"]) is bool
                          for x in (baseline, candidate)))
    improvement = (comparable and not baseline["timed_out"] and not candidate["timed_out"]
                   and not baseline["passed"] and candidate["passed"])
    return {"comparable": comparable, "newly_passing": improvement,
            "recommend_review": improvement, "recommend_promotion": False,
            "human_approval_required": True, "release_authorized": False}
