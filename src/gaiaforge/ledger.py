"""Tamper-evident JSONL ledger using a chained record hash.

Hash chaining detects accidental or adversarial modifications if the chain root
is anchored externally; it does not itself prevent rewriting the entire ledger.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def canonical(data: Any) -> bytes:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def record_hash(record: dict) -> str:
    return hashlib.sha256(canonical({k: v for k, v in record.items() if k != "hash"})).hexdigest()


def read_verified(path: Path) -> list[dict]:
    if not path.exists():
        return []
    chain: list[dict] = []
    with path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            try:
                entry = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid ledger JSON on line {line_number}") from exc
            previous = chain[-1]["hash"] if chain else "0" * 64
            if entry.get("previous_hash") != previous or entry.get("hash") != record_hash(entry):
                raise ValueError(f"ledger integrity check failed on line {line_number}")
            chain.append(entry)
    return chain


def append_record(path: Path, kind: str, payload: dict) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("payload must be an object")
    path.parent.mkdir(parents=True, exist_ok=True)
    # Cross-process serialization on POSIX; Windows callers should use a single writer.
    with path.open("a+", encoding="utf-8") as handle:
        try:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        except ImportError:
            pass
        handle.seek(0)
        chain = read_verified(path)
        record = {
            "sequence": len(chain) + 1,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "kind": kind,
            "payload": payload,
            "previous_hash": chain[-1]["hash"] if chain else "0" * 64,
        }
        record["hash"] = record_hash(record)
        handle.seek(0, os.SEEK_END)
        handle.write(canonical(record).decode("utf-8") + "\n")
        handle.flush()
        os.fsync(handle.fileno())
        return record
