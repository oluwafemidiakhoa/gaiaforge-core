"""Deterministic proposal staging. A copied workspace is NOT a security sandbox.

Proposal files are untrusted data. This module never executes source code or tools.
"""
from __future__ import annotations

import ast
import difflib
import hashlib
import json
import os
import re
import shutil
import stat
from pathlib import Path, PurePosixPath
from typing import Any

from .ledger import append_record

MAX_PROPOSAL_BYTES = 256_000
MAX_OPERATIONS = 30
MAX_FILE_BYTES = 128_000
MAX_SOURCE_FILES = 1000
MAX_TOTAL_BYTES = 10_000_000
ALLOWED_SUFFIXES = {".py", ".md", ".toml", ".json", ".yaml", ".yml", ".sql", ".js", ".ts", ".tsx", ".html", ".css"}
IGNORED_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", "dist", "build", ".gaiaforge"}
HEX_DIGEST = re.compile(r"^[0-9a-f]{64}$")


class ProposalError(ValueError):
    """Proposed change violates staging constraints."""


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _path(value: Any) -> PurePosixPath:
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        raise ProposalError("invalid proposal path")
    p = PurePosixPath(value)
    if p.is_absolute() or any(x in {"", ".", ".."} for x in value.split("/")):
        raise ProposalError("proposal path must be a canonical relative path")
    if ":" in value or any(part.startswith(".") or part in IGNORED_DIRS for part in p.parts):
        raise ProposalError("hidden or excluded paths are prohibited")
    if p.suffix.lower() not in ALLOWED_SUFFIXES:
        raise ProposalError("unsupported source file type")
    return p


def load_proposal(path: Path) -> dict:
    if path.stat().st_size > MAX_PROPOSAL_BYTES:
        raise ProposalError("proposal exceeds size budget")
    try:
        proposal = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ProposalError("proposal must be UTF-8 JSON") from exc
    if not isinstance(proposal, dict) or set(proposal) != {"proposal_id", "operations"}:
        raise ProposalError("proposal requires only proposal_id and operations")
    ident = proposal["proposal_id"]
    if not isinstance(ident, str) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", ident):
        raise ProposalError("invalid proposal identifier")
    ops = proposal["operations"]
    if not isinstance(ops, list) or not 1 <= len(ops) <= MAX_OPERATIONS:
        raise ProposalError("invalid operation count")
    seen = set()
    for op in ops:
        if not isinstance(op, dict) or set(op) != {"path", "previous_sha256", "content"}:
            raise ProposalError("each operation needs path, previous_sha256 and content")
        filename = _path(op["path"]).as_posix()
        if filename in seen:
            raise ProposalError("duplicate modified path")
        seen.add(filename)
        digest = op["previous_sha256"]
        if digest is not None and (not isinstance(digest, str) or not HEX_DIGEST.fullmatch(digest)):
            raise ProposalError("previous_sha256 must be a SHA-256 hex digest or null for new files")
        if not isinstance(op["content"], str) or len(op["content"].encode("utf-8")) > MAX_FILE_BYTES:
            raise ProposalError("proposed content must be bounded UTF-8 text")
    return proposal


def _walk_source(root: Path) -> list[tuple[PurePosixPath, bytes]]:
    if root.is_symlink() or not root.is_dir():
        raise ProposalError("source must be a real directory")
    result: list[tuple[PurePosixPath, bytes]] = []
    total = 0
    for parent, dirs, files in os.walk(root, followlinks=False):
        parent_path = Path(parent)
        safe_dirs = []
        for name in sorted(dirs):
            child = parent_path / name
            if name in IGNORED_DIRS or name.startswith("."):
                continue
            if child.is_symlink():
                raise ProposalError("source contains a disallowed directory symlink")
            safe_dirs.append(name)
        dirs[:] = safe_dirs
        for name in sorted(files):
            path = parent_path / name
            relative = PurePosixPath(*path.relative_to(root).parts)
            if name.startswith(".") or path.suffix.lower() not in ALLOWED_SUFFIXES:
                continue
            if path.is_symlink() or not path.is_file():
                raise ProposalError("source contains a disallowed file symlink or special file")
            mode = path.stat(follow_symlinks=False).st_mode
            if not stat.S_ISREG(mode):
                raise ProposalError("only regular source files are accepted")
            size = path.stat().st_size
            if size > MAX_FILE_BYTES:
                raise ProposalError("source file exceeds staging budget")
            total += size
            if total > MAX_TOTAL_BYTES or len(result) >= MAX_SOURCE_FILES:
                raise ProposalError("source repository exceeds staging budget")
            result.append((relative, path.read_bytes()))
    return result


def stage_proposal(source: Path, proposal_file: Path, destination: Path, *, evidence_ledger: Path | None = None) -> dict:
    """Make a review-only copy. No source mutation and no source execution.

    The destination must not exist; evidence ledger, if requested, stays outside the workspace.
    """
    source = source.absolute()
    destination = destination.absolute()
    proposal_file = proposal_file.absolute()
    if source == destination or source in destination.parents or destination in source.parents:
        raise ProposalError("source and destination cannot overlap")
    if destination.exists() or destination.is_symlink():
        raise ProposalError("destination already exists")
    if evidence_ledger is not None:
        led = evidence_ledger.absolute()
        if led == destination or destination in led.parents:
            raise ProposalError("evidence ledger must be outside staged workspace")
    proposal = load_proposal(proposal_file)
    entries = _walk_source(source)
    originals = {p.as_posix(): data for p, data in entries}
    changes = []
    for op in proposal["operations"]:
        name = op["path"]
        old = originals.get(name)
        expected = op["previous_sha256"]
        if (old is None and expected is not None) or (old is not None and _sha(old) != expected):
            raise ProposalError(f"baseline checksum mismatch: {name}")
        if old is not None:
            try:
                old_text = old.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise ProposalError(f"baseline is not UTF-8: {name}") from exc
        else:
            old_text = ""
        changes.append({"path": name, "before_sha256": _sha(old) if old is not None else None,
                        "after_sha256": _sha(op["content"].encode("utf-8")),
                        "diff": "".join(difflib.unified_diff(old_text.splitlines(keepends=True),
                             op["content"].splitlines(keepends=True), fromfile=f"a/{name}", tofile=f"b/{name}"))[:16000]})
    # Complete validation happens before constructing the output workspace.
    try:
        destination.mkdir(parents=True)
        for relative, data in entries:
            target = destination.joinpath(*relative.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        for op in proposal["operations"]:
            target = destination.joinpath(*_path(op["path"]).parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(op["content"], encoding="utf-8")
        syntax = []
        for entry in changes:
            if entry["path"].endswith(".py"):
                content = (destination / entry["path"]).read_text(encoding="utf-8")
                try:
                    ast.parse(content, filename=entry["path"])
                    syntax.append({"path": entry["path"], "valid": True})
                except SyntaxError as exc:
                    syntax.append({"path": entry["path"], "valid": False,
                                   "error": f"line {exc.lineno}: {exc.msg}"})
        report = {"proposal_id": proposal["proposal_id"], "source": str(source),
                  "workspace": str(destination), "baseline_files": len(entries),
                  "changes": changes, "python_syntax": syntax,
                  "static_checks_passed": all(s["valid"] for s in syntax),
                  "executed_code": False, "sandboxed": False, "release_authorized": False,
                  "status": "review_required"}
        # The report goes outside the workspace so it cannot be confused with repository content.
        if evidence_ledger is not None:
            record = append_record(evidence_ledger, "proposal_staged", {
                "proposal_id": proposal["proposal_id"], "changes": [
                    {k: v for k, v in entry.items() if k != "diff"} for entry in changes],
                "static_checks_passed": report["static_checks_passed"], "executed_code": False})
            report["ledger_hash"] = record["hash"]
        return report
    except Exception:
        shutil.rmtree(destination, ignore_errors=True)
        raise
