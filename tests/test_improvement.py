import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from gaiaforge.improvement import ImprovementError, assess_candidates
from gaiaforge.ledger import read_verified

SHA = "a" * 64
IMAGE = "python@sha256:" + "b" * 64


class ImprovementTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "evaluation"
        self.root.mkdir()
        self.baseline = self.report(False)
        self.candidate = self.report(True, snapshot_sha256="c" * 64)
        self.write("baseline.json", self.baseline)
        self.write("candidate.json", self.candidate)
        self.write("proposal.json", {"proposal_id": "fix-1", "operations": [
            {"path": "main.py", "previous_sha256": None, "content": "answer = 42\n"}
        ]})
        self.manifest = {"evaluation_id": "eval-1", "baseline": "baseline.json",
                         "candidates": [{"proposal": "proposal.json", "report": "candidate.json"}]}
        self.write("manifest.json", self.manifest)

    def report(self, passed, **overrides):
        result = {"suite_sha256": SHA, "snapshot_sha256": SHA, "image": IMAGE,
                  "check": "unittest", "backend": "docker", "passed": passed,
                  "timed_out": False, "exit_code": 0 if passed else 1,
                  "output_sha256": SHA, "release_authorized": False}
        result.update(overrides)
        return result

    def write(self, name, data):
        (self.root / name).write_text(json.dumps(data), encoding="utf-8")

    def assess(self, ledger=None):
        return assess_candidates(self.root / "manifest.json", evidence_ledger=ledger)

    def test_newly_passing_candidate_requires_review(self):
        result = self.assess()
        self.assertEqual(result["candidate_count"], 1)
        self.assertEqual(result["candidates"][0]["decision"], "human_review_required")
        self.assertFalse(result["automatic_promotion"])
        self.assertFalse(result["release_authorized"])
        self.assertFalse(result["executed_code"])
        self.assertEqual(result["evidence_trust"], "caller_supplied_unattested")

    def test_mismatched_suite_cannot_qualify(self):
        self.write("candidate.json", self.report(True, suite_sha256="e" * 64))
        self.assertEqual(self.assess()["candidates"][0]["decision"], "not_eligible")

    def test_regression_cannot_qualify(self):
        self.write("baseline.json", self.report(True))
        self.write("candidate.json", self.report(False))
        self.assertEqual(self.assess()["candidates"][0]["decision"], "not_eligible")

    def test_inconsistent_pass_flag_rejected(self):
        self.write("candidate.json", self.report(True, exit_code=1))
        with self.assertRaisesRegex(ImprovementError, "inconsistent"):
            self.assess()

    def test_missing_digest_rejected(self):
        self.write("candidate.json", self.report(True, snapshot_sha256="fake"))
        with self.assertRaisesRegex(ImprovementError, "snapshot_sha256"):
            self.assess()

    def test_unpinned_image_rejected(self):
        self.write("candidate.json", self.report(True, image="python:latest"))
        with self.assertRaisesRegex(ImprovementError, "pinned"):
            self.assess()

    def test_duplicate_proposals_rejected(self):
        self.manifest["candidates"].append(self.manifest["candidates"][0].copy())
        self.write("manifest.json", self.manifest)
        with self.assertRaisesRegex(ImprovementError, "duplicate"):
            self.assess()

    def test_budget_exceeded(self):
        self.manifest["candidates"] = self.manifest["candidates"] * 6
        self.write("manifest.json", self.manifest)
        with self.assertRaisesRegex(ImprovementError, "budget"):
            self.assess()

    def test_path_traversal_rejected(self):
        self.manifest["baseline"] = "../outside.json"
        self.write("manifest.json", self.manifest)
        with self.assertRaisesRegex(ImprovementError, "relative paths"):
            self.assess()

    def test_ledger_outside_evaluation(self):
        ledger = Path(self.tmp.name) / "audit.jsonl"
        result = self.assess(ledger)
        self.assertEqual(result["ledger_hash"], read_verified(ledger)[-1]["hash"])

    def test_ledger_inside_evaluation_rejected(self):
        with self.assertRaisesRegex(ImprovementError, "outside evaluation"):
            self.assess(self.root / "audit.jsonl")

    def test_malicious_proposal_path_rejected(self):
        self.write("proposal.json", {"proposal_id": "fix-1", "operations": [
            {"path": "../secrets.py", "previous_sha256": None, "content": "secret"}]})
        with self.assertRaises(ValueError):
            self.assess()


if __name__ == "__main__":
    unittest.main()
