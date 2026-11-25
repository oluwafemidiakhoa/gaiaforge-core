"""Local report-to-ledger consistency checks; not cryptographic attestation.

A matching local ledger can be rewritten by someone controlling both report and ledger.
Use an independently stored expected head, signed CI attestations, and trusted builders
before treating evidence as authenticated.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path

from .ledger import read_verified

_HEX = re.compile(r"^[0-9a-f]{64}$")
_MAX_REPORT_BYTES = 256_000


class ProvenanceError(ValueError):
    """Missing, unsafe, or inconsistent local verification evidence."""


def source_identity(repo: Path) -> dict:
    """Read Git identity only for a repo rooted at this exact directory.

    Avoid picking up an unrelated parent (e.g. a Git repo in a Windows home folder).
    A clean Git checkout is metadata, NOT proof that a Docker snapshot matches HEAD.
    """
    repo = Path(repo).resolve(strict=True)
    result = {"git_commit": None, "git_worktree_clean": None, "git_root_matches": False}
    if not (repo / ".git").exists():
        return result
    try:
        root = subprocess.run(["git", "-C", str(repo), "rev-parse", "--show-toplevel"],
                              text=True, capture_output=True, timeout=5, check=False)
        if root.returncode != 0 or Path(root.stdout.strip()).resolve(strict=False) != repo:
            return result
        result["git_root_matches"] = True
        head = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                              text=True, capture_output=True, timeout=5, check=False)
        status = subprocess.run(["git", "-C", str(repo), "status", "--porcelain", "--untracked-files=all"],
                                text=True, capture_output=True, timeout=5, check=False)
        if head.returncode != 0 or not re.fullmatch(r"[0-9a-f]{40,64}", head.stdout.strip()):
            return result
        result["git_commit"] = head.stdout.strip()
        if status.returncode == 0:
            result["git_worktree_clean"] = not bool(status.stdout.strip())
    except (OSError, subprocess.TimeoutExpired, ValueError):
        pass
    return result


def verify_receipt(report_file: Path, ledger_file: Path, *, expected_head: str | None = None) -> dict:
    """Check one saved JSON report against its exact chained ledger record.

    An expected head must be obtained from an independent trusted channel to serve
    as an anchor. This function cannot establish the identity of a code executor.
    """
    report_file = Path(report_file)
    ledger_file = Path(ledger_file)
    for path in (report_file, ledger_file):
        if path.is_symlink() or not path.is_file():
            raise ProvenanceError("report and ledger must be regular files, not symlinks")
    if report_file.stat().st_size > _MAX_REPORT_BYTES:
        raise ProvenanceError("report exceeds size budget")
    if expected_head is not None and (not isinstance(expected_head, str) or not _HEX.fullmatch(expected_head)):
        raise ProvenanceError("expected head must be a SHA-256 hex digest")
    try:
        report = json.loads(report_file.read_text(encoding="utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ProvenanceError("invalid report JSON") from exc
    if not isinstance(report, dict) or not isinstance(report.get("ledger_hash"), str) or not _HEX.fullmatch(report["ledger_hash"]):
        raise ProvenanceError("report lacks a valid ledger_hash")
    if report.get("backend") != "docker" or report.get("release_authorized") is not False:
        raise ProvenanceError("not a Docker verification report with release disabled")
    if report.get("passed") is not (report.get("exit_code") == 0 and report.get("timed_out") is False):
        raise ProvenanceError("inconsistent report execution result")
    records = read_verified(ledger_file)
    if not records:
        raise ProvenanceError("ledger contains no records")
    head = records[-1]["hash"]
    if expected_head is not None and head != expected_head:
        raise ProvenanceError("ledger head does not match expected independent anchor")
    matches = [rec for rec in records if rec.get("hash") == report["ledger_hash"]]
    if len(matches) != 1 or matches[0].get("kind") != "container_verification":
        raise ProvenanceError("report receipt is absent or wrong kind")
    recorded_payload = matches[0].get("payload")
    if not isinstance(recorded_payload, dict):
        raise ProvenanceError("invalid ledger payload")
    expected_payload = {k: v for k, v in report.items() if k not in ("output_excerpt", "ledger_hash")}
    if recorded_payload != expected_payload:
        raise ProvenanceError("saved report does not match ledger payload")
    return {
        "valid": True,
        "report_sha256": hashlib.sha256(report_file.read_bytes()).hexdigest(),
        "receipt_hash": matches[0]["hash"],
        "ledger_head": head,
        "record_count": len(records),
        "git_commit": report.get("git_commit"),
        "git_worktree_clean": report.get("git_worktree_clean"),
        "external_anchor_checked": expected_head is not None,
        "execution_authenticated": False,
        "release_authorized": False,
    }
