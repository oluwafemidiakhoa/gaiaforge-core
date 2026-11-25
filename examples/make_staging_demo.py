"""Generate a small repeatable demo proposal without fetching dependencies."""
import hashlib
import json
from pathlib import Path

root = Path("demo")
source = root / "source"
source.mkdir(parents=True, exist_ok=True)
original = b"value = 1\n"
(source / "main.py").write_bytes(original)
proposal = {"proposal_id": "demo-fix", "operations": [
    {"path": "main.py", "previous_sha256": hashlib.sha256(original).hexdigest(),
     "content": "value = 2\n"}]}
(root / "proposal.json").write_text(json.dumps(proposal, indent=2), encoding="utf-8")
print("Generated demo/source/main.py and demo/proposal.json")
