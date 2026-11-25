"""Explicitly authorized local verification, not a security sandbox."""
from __future__ import annotations

import hashlib
import subprocess
import time
from pathlib import Path


ALLOWED = {
    "unittest": ["python", "-m", "unittest", "discover", "-s", "tests", "-v"],
    "pytest": ["python", "-m", "pytest", "-q"],
    "ruff": ["python", "-m", "ruff", "check", "."],
}


def run_verification(repo: Path, check: str, *, authorized: bool = False, timeout: int = 60) -> dict:
    if not authorized:
        raise PermissionError("execution requires explicit --authorize-execution")
    if check not in ALLOWED:
        raise ValueError("unsupported verification check")
    if type(timeout) is not int or not 1 <= timeout <= 300:
        raise ValueError("timeout must be between 1 and 300 seconds")
    repo = repo.resolve(strict=True)
    if not repo.is_dir():
        raise ValueError("repository must be a directory")
    command = ALLOWED[check]
    start = time.monotonic()
    try:
        result = subprocess.run(command, cwd=repo, capture_output=True, text=True, timeout=timeout, check=False)
        status, output = result.returncode, (result.stdout + "\n" + result.stderr)[-30000:]
        timed_out = False
    except subprocess.TimeoutExpired as exc:
        status = None
        output = str(exc)
        timed_out = True
    return {
        "check": check,
        "command": command,
        "exit_code": status,
        "passed": status == 0 and not timed_out,
        "timed_out": timed_out,
        "duration_seconds": round(time.monotonic() - start, 3),
        "output_sha256": hashlib.sha256(output.encode()).hexdigest(),
        "output_excerpt": output,
    }


def compare_evaluations(baseline: dict, candidate: dict) -> dict:
    """Conservative comparison: never promote on incomplete or incomparable evidence."""
    for obj in (baseline, candidate):
        if not isinstance(obj, dict) or type(obj.get("passed")) is not bool or not isinstance(obj.get("suite_id"), str):
            raise ValueError("evaluation requires passed:boolean and suite_id:string")
    comparable = baseline["suite_id"] == candidate["suite_id"] and bool(baseline["suite_id"])
    promoted = comparable and candidate["passed"] and not baseline["passed"]
    return {
        "comparable": comparable,
        "baseline_passed": baseline["passed"],
        "candidate_passed": candidate["passed"],
        "recommend_promotion": promoted,
        "human_approval_required": True,
        "reason": "newly passing fixed suite" if promoted else "inconclusive, unchanged, or regression",
    }
