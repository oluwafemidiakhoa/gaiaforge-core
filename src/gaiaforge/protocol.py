"""Frozen, locally checkable evaluation protocol and paired report receipts.

All inputs are caller-controlled. Local consistency is not runner authentication.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from .sandbox import _suite_digest, _validate_repository
from .improvement import _report
from .provenance import verify_receipt

_HEX = re.compile(r"^[a-f0-9]{64}$")
_IMAGE = re.compile(r"^[a-z0-9][a-z0-9._:/-]*@sha256:[0-9a-f]{64}$")


class ProtocolError(ValueError):
    pass


def _canonical(data: dict) -> bytes:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def freeze_protocol(repo: Path, destination: Path, *, image: str, protocol_id: str) -> dict:
    """Freeze suite identity without executing any code. Never overwrite an existing freeze."""
    if not isinstance(protocol_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", protocol_id):
        raise ProtocolError("invalid protocol identifier")
    if not isinstance(image, str) or not _IMAGE.fullmatch(image):
        raise ProtocolError("image must be digest-pinned")
    repo = _validate_repository(Path(repo))
    destination = Path(destination).resolve(strict=False)
    if destination == repo or repo in destination.parents:
        raise ProtocolError("freeze must be stored outside evaluation repository")
    protocol = {
        "schema": "gaiaforge.frozen-protocol.v1",
        "protocol_id": protocol_id,
        "suite_sha256": _suite_digest(repo),
        "image": image,
        "check": "unittest",
        "backend": "docker",
        "release_authorized": False,
    }
    protocol["protocol_sha256"] = hashlib.sha256(_canonical(protocol)).hexdigest()
    # Exclusive create prevents silent changes to a frozen evaluation plan.
    with destination.open("x", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(protocol, indent=2) + "\n")
    return protocol


def _load_protocol(path: Path) -> dict:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 8192:
        raise ProtocolError("protocol must be a bounded regular file")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ProtocolError("invalid frozen protocol") from exc
    required = {"schema", "protocol_id", "suite_sha256", "image", "check", "backend", "release_authorized", "protocol_sha256"}
    if not isinstance(data, dict) or set(data) != required:
        raise ProtocolError("invalid frozen protocol fields")
    if (data["schema"] != "gaiaforge.frozen-protocol.v1" or
        not isinstance(data["protocol_id"], str) or
        not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", data["protocol_id"]) or
        not isinstance(data["suite_sha256"], str) or not _HEX.fullmatch(data["suite_sha256"]) or
        not isinstance(data["image"], str) or not _IMAGE.fullmatch(data["image"]) or
        data["check"] != "unittest" or data["backend"] != "docker" or
        data["release_authorized"] is not False):
        raise ProtocolError("invalid protocol contents")
    checksum = hashlib.sha256(_canonical({k: v for k, v in data.items() if k != "protocol_sha256"})).hexdigest()
    if checksum != data["protocol_sha256"]:
        raise ProtocolError("frozen protocol checksum mismatch")
    return data


def verify_experiment(protocol_file: Path, baseline_file: Path, baseline_ledger: Path,
                      candidate_file: Path, candidate_ledger: Path,
                      *, expected_baseline_head: str | None = None,
                      expected_candidate_head: str | None = None) -> dict:
    """Validate paired receipts against same frozen protocol; never grant promotion."""
    protocol = _load_protocol(Path(protocol_file))
    baseline_receipt = verify_receipt(Path(baseline_file), Path(baseline_ledger), expected_head=expected_baseline_head)
    candidate_receipt = verify_receipt(Path(candidate_file), Path(candidate_ledger), expected_head=expected_candidate_head)
    baseline, baseline_sha = _report(Path(baseline_file))
    candidate, candidate_sha = _report(Path(candidate_file))
    for name, report in (("baseline", baseline), ("candidate", candidate)):
        if any(report.get(key) != protocol[key] for key in ("suite_sha256", "image", "check", "backend")):
            raise ProtocolError(f"{name} report deviates from frozen protocol")
        if report.get("release_authorized") is not False:
            raise ProtocolError(f"{name} report has invalid release authority")
    if baseline_sha != baseline_receipt["report_sha256"] or candidate_sha != candidate_receipt["report_sha256"]:
        raise ProtocolError("report changed during evaluation")
    if baseline["snapshot_sha256"] == candidate["snapshot_sha256"]:
        raise ProtocolError("baseline and candidate snapshots are identical")
    changed_and_passing = (not baseline["passed"] and candidate["passed"] and
                           not baseline["timed_out"] and not candidate["timed_out"])
    return {
        "protocol_id": protocol["protocol_id"],
        "protocol_sha256": protocol["protocol_sha256"],
        "frozen_suite_sha256": protocol["suite_sha256"],
        "baseline_report_sha256": baseline_sha,
        "candidate_report_sha256": candidate_sha,
        "baseline_receipt_hash": baseline_receipt["receipt_hash"],
        "candidate_receipt_hash": candidate_receipt["receipt_hash"],
        "newly_passing": changed_and_passing,
        "decision": "human_review_required" if changed_and_passing else "not_eligible",
        "external_anchors_checked": bool(expected_baseline_head and expected_candidate_head),
        "execution_authenticated": False,
        "automatic_promotion": False,
        "release_authorized": False,
        "human_approval_required": True,
    }
