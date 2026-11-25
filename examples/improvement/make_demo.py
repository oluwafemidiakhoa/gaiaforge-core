"""Generate synthetic evidence to demonstrate gate behavior, NOT real Docker validation."""
import json
from pathlib import Path

root = Path(__file__).resolve().parent / "generated"
root.mkdir(exist_ok=True)
image = "python@sha256:" + "b" * 64
suite = "a" * 64
base = {"suite_sha256": suite, "snapshot_sha256": "c" * 64, "image": image,
        "check": "unittest", "backend": "docker", "passed": False,
        "timed_out": False, "exit_code": 1, "output_sha256": "d" * 64,
        "release_authorized": False}
candidate = dict(base, snapshot_sha256="e" * 64, passed=True, exit_code=0)
proposal = {"proposal_id": "example-improvement", "operations": [
    {"path": "main.py", "previous_sha256": None, "content": "answer = 42\n"}
]}
manifest = {"evaluation_id": "illustrative-only", "baseline": "baseline.json",
            "candidates": [{"proposal": "proposal.json", "report": "candidate.json"}]}
for name, data in (("baseline.json", base), ("candidate.json", candidate),
                   ("proposal.json", proposal), ("manifest.json", manifest)):
    (root / name).write_text(json.dumps(data, indent=2), encoding="utf-8")
print(f"Synthetic example generated in: {root}")
