"""Low-impact local source discovery; never follow symlinks."""
from __future__ import annotations

import hashlib
from pathlib import Path

EXCLUDED = {".git", ".venv", "venv", "node_modules", "__pycache__", ".mypy_cache", ".pytest_cache", "dist", "build"}
EXTENSIONS = {".py", ".md", ".toml", ".yaml", ".yml", ".json", ".sql", ".js", ".ts", ".tsx", ".html", ".css"}


def inspect_repo(root: Path, *, max_files: int = 500, max_bytes: int = 1_000_000) -> dict:
    root = root.resolve(strict=True)
    if not root.is_dir():
        raise ValueError("repository path must be a directory")
    entries: list[dict] = []
    skipped = 0
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root)
        if any(p in EXCLUDED or p.startswith(".") and p != ".github" for p in rel.parts):
            continue
        if path.is_symlink() or not path.is_file() or path.suffix.lower() not in EXTENSIONS:
            continue
        if len(entries) >= max_files:
            skipped += 1
            continue
        size = path.stat().st_size
        if size > max_bytes:
            skipped += 1
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        entries.append({"path": rel.as_posix(), "bytes": size, "sha256": digest})
    return {"root": str(root), "files": entries, "skipped": skipped, "file_count": len(entries)}
