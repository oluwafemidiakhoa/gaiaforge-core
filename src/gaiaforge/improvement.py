"""Evidence-gated, bounded candidate assessment. Never executes code or approves release.

Input reports are untrusted until tied to a trusted evaluator and external evidence.
The gate produces a REVIEW decision, not deployment authorization.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from .ledger import append_record
from .staging import load_proposal

_HEX = re.compile(r"^[0-9a-f]{64}$")
_MAX_REPORT = 256_000
_MAX_CANDIDATES = 5
_REQUIRED = {
    "suite_sha256", "snapshot_sha256", "image", "check", "backend", "passed",
    "timed_out", "exit_code", "output_sha256", "release_authorized"
}


class ImprovementError(ValueError):
    """Invalid or insufficient evidence for a bounded improvement decision."""


def _report(path: Path) -> tuple[dict, str]:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > _MAX_REPORT:
        raise ImprovementError("report must be a bounded regular file")
    raw = path.read_bytes()
    try:
        data = json.loads(raw)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ImprovementError("report must contain valid UTF-8 JSON") from exc
    if not isinstance(data, dict) or not _REQUIRED <= data.keys():
        raise ImprovementError("verification report missing required evidence")
    for key in ("suite_sha256", "snapshot_sha256", "output_sha256"):
        if not isinstance(data[key], str) or not _HEX.fullmatch(data[key]):
            raise ImprovementError(f"invalid {key}")
    if data["backend"] != "docker" or data["check"] != "unittest":
        raise ImprovementError("unsupported verification backend or check")
    if (type(data["passed"]) is not bool or type(data["timed_out"]) is not bool or
            data["release_authorized"] is not False):
        raise ImprovementError("invalid execution or authorization flags")
    if data["exit_code"] is not None and type(data["exit_code"]) is not int:
        raise ImprovementError("invalid exit code")
    if data["passed"] != (data["exit_code"] == 0 and not data["timed_out"]):
        raise ImprovementError("inconsistent execution result")
    if not isinstance(data["image"], str) or not re.fullmatch(r"[a-z0-9][a-z0-9._:/-]*@sha256:[0-9a-f]{64}", data["image"]):
        raise ImprovementError("verification image is not pinned")
    return data, hashlib.sha256(raw).hexdigest()


def assess_candidates(manifest_file: Path, *, evidence_ledger: Path | None = None) -> dict:
    """Compare frozen-suite reports without running code or granting promotion.

    Manifest format:
      {"evaluation_id":"...", "baseline":"baseline.json",
       "candidates":[{"proposal":"proposal.json", "report":"candidate.json"}]}
    Paths are relative to the manifest directory and cannot escape it.
    """
    manifest_file = Path(manifest_file).resolve(strict=True)
    if manifest_file.stat().st_size > 64_000:
        raise ImprovementError("manifest exceeds size budget")
    try:
        manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ImprovementError("manifest must be UTF-8 JSON") from exc
    if not isinstance(manifest, dict) or set(manifest) != {"evaluation_id", "baseline", "candidates"}:
        raise ImprovementError("invalid evaluation manifest")
    ident = manifest["evaluation_id"]
    if not isinstance(ident, str) or re.fullmatch(r"[A-Za-z0-9_-]{1,64}", ident) is None:
        raise ImprovementError("invalid evaluation identifier")
    candidates = manifest["candidates"]
    if not isinstance(candidates, list) or not 1 <= len(candidates) <= _MAX_CANDIDATES:
        raise ImprovementError("candidate budget exceeded")
    root = manifest_file.parent

    def local_file(name: str) -> Path:
        if (not isinstance(name, str) or not name or "\\" in name or ":" in name or
                name.startswith("/") or any(part in ("", ".", "..") for part in name.split("/"))):
            raise ImprovementError("manifest paths must be canonical relative paths")
        path = root.joinpath(*name.split("/"))
        if path.is_symlink() or not path.resolve(strict=False).is_relative_to(root):
            raise ImprovementError("manifest file escapes evaluation directory")
        return path

    baseline, baseline_hash = _report(local_file(manifest["baseline"]))
    findings = []
    seen = set()
    for item in candidates:
        if not isinstance(item, dict) or set(item) != {"proposal", "report"}:
            raise ImprovementError("candidate requires proposal and report paths")
        proposal_path = local_file(item["proposal"])
        proposal = load_proposal(proposal_path)
        proposal_id = proposal["proposal_id"]
        if proposal_id in seen:
            raise ImprovementError("duplicate proposal identifier")
        seen.add(proposal_id)
        candidate, report_hash = _report(local_file(item["report"]))
        comparable = all(baseline[k] == candidate[k] for k in ("suite_sha256", "image", "check", "backend"))
        # A passing candidate must not have changed the frozen suite.
        # The source snapshot may differ because the candidate modifies source code.
        newly_passing = bool(comparable and not baseline["passed"] and candidate["passed"] and
                            not baseline["timed_out"] and not candidate["timed_out"])
        findings.append({
            "proposal_id": proposal_id,
            "proposal_sha256": hashlib.sha256(proposal_path.read_bytes()).hexdigest(),
            "report_sha256": report_hash,
            "comparable": comparable,
            "newly_passing": newly_passing,
            "decision": "human_review_required" if newly_passing else "not_eligible",
            "reason": ("candidate passed same frozen suite" if newly_passing else
                       "suite/image mismatch, no improvement, or failed verification"),
        })

    review = {
        "evaluation_id": ident,
        "baseline_report_sha256": baseline_hash,
        "frozen_suite_sha256": baseline["suite_sha256"],
        "candidate_count": len(findings),
        "candidates": findings,
        "executed_code": False,
        "automatic_promotion": False,
        "release_authorized": False,
        "human_approval_required": True,
        "evidence_trust": "caller_supplied_unattested",
    }
    if evidence_ledger is not None:
        evidence_ledger = Path(evidence_ledger).resolve(strict=False)
        if evidence_ledger.is_relative_to(root):
            raise ImprovementError("evidence ledger must be outside evaluation directory")
        entry = append_record(evidence_ledger, "improvement_assessment", review)
        review["ledger_hash"] = entry["hash"]
    return review
