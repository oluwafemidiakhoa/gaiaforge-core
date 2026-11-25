import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from gaiaforge.ledger import append_record
from gaiaforge.provenance import ProvenanceError, source_identity, verify_receipt


class ProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.report_path = self.root / "report.json"
        self.ledger_path = self.root / "ledger.jsonl"
        self.report = {
            "backend": "docker", "passed": True, "exit_code": 0,
            "timed_out": False, "release_authorized": False,
            "suite_sha256": "a" * 64, "snapshot_sha256": "b" * 64,
            "output_sha256": "c" * 64, "image": "python@sha256:" + "d" * 64,
            "check": "unittest", "output_excerpt": "test output",
        }
        entry = append_record(self.ledger_path, "container_verification",
                              {k: v for k, v in self.report.items() if k != "output_excerpt"})
        self.report["ledger_hash"] = entry["hash"]
        self.save()

    def save(self):
        self.report_path.write_text(json.dumps(self.report), encoding="utf-8")

    def test_valid_receipt(self):
        outcome = verify_receipt(self.report_path, self.ledger_path)
        self.assertTrue(outcome["valid"])
        self.assertFalse(outcome["execution_authenticated"])
        self.assertFalse(outcome["external_anchor_checked"])
        self.assertEqual(outcome["receipt_hash"], self.report["ledger_hash"])

    def test_explicit_anchor_match(self):
        outcome = verify_receipt(self.report_path, self.ledger_path,
                                 expected_head=self.report["ledger_hash"])
        self.assertTrue(outcome["external_anchor_checked"])

    def test_bad_anchor_fails(self):
        with self.assertRaisesRegex(ProvenanceError, "anchor"):
            verify_receipt(self.report_path, self.ledger_path, expected_head="0" * 64)

    def test_modified_report_fails(self):
        self.report["image"] = "python@sha256:" + "e" * 64
        self.save()
        with self.assertRaisesRegex(ProvenanceError, "does not match"):
            verify_receipt(self.report_path, self.ledger_path)

    def test_result_inconsistency_fails(self):
        self.report["passed"] = False
        self.save()
        with self.assertRaisesRegex(ProvenanceError, "inconsistent"):
            verify_receipt(self.report_path, self.ledger_path)

    def test_missing_receipt_fails(self):
        self.report["ledger_hash"] = "0" * 64
        self.save()
        with self.assertRaisesRegex(ProvenanceError, "absent"):
            verify_receipt(self.report_path, self.ledger_path)

    def test_corrupted_ledger_fails(self):
        with self.ledger_path.open("a", encoding="utf-8") as f:
            f.write('{"hash":"bad"}\n')
        with self.assertRaisesRegex(ValueError, "integrity"):
            verify_receipt(self.report_path, self.ledger_path)

    def test_wrong_kind_fails(self):
        other = self.root / "other.jsonl"
        payload = {k: v for k, v in self.report.items() if k not in ("output_excerpt", "ledger_hash")}
        entry = append_record(other, "improvement_assessment", payload)
        self.report["ledger_hash"] = entry["hash"]
        self.save()
        with self.assertRaisesRegex(ProvenanceError, "wrong kind"):
            verify_receipt(self.report_path, other)

    def test_no_parent_git_identity(self):
        child = self.root / "child"
        child.mkdir()
        (child / ".git").mkdir()
        # Simulates Git resolving an unrelated parent user-profile repository.
        with patch("gaiaforge.provenance.subprocess.run",
                   return_value=subprocess.CompletedProcess([], 0, str(self.root) + "\n", "")):
            identity = source_identity(child)
        self.assertIsNone(identity["git_commit"])
        self.assertFalse(identity["git_root_matches"])

    def test_git_identity_from_exact_root(self):
        root = self.root / "project"
        root.mkdir()
        (root / ".git").mkdir()
        def runner(args, **kwargs):
            if "--show-toplevel" in args:
                return subprocess.CompletedProcess(args, 0, str(root) + "\n", "")
            if "HEAD" in args:
                return subprocess.CompletedProcess(args, 0, "c" * 40 + "\n", "")
            return subprocess.CompletedProcess(args, 0, "", "")
        with patch("gaiaforge.provenance.subprocess.run", side_effect=runner):
            result = source_identity(root)
        self.assertEqual(result["git_commit"], "c" * 40)
        self.assertTrue(result["git_worktree_clean"])
        self.assertTrue(result["git_root_matches"])

    def test_symlink_report_rejected(self):
        link = self.root / "link.json"
        try:
            link.symlink_to(self.report_path)
        except OSError as exc:
            if getattr(exc, "winerror", None) == 1314:
                self.skipTest("Windows symlink creation privilege unavailable")
            raise
        with self.assertRaisesRegex(ProvenanceError, "regular files"):
            verify_receipt(link, self.ledger_path)


if __name__ == "__main__":
    unittest.main()
