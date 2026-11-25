import tempfile
import unittest
from pathlib import Path

from gaiaforge.inspect import inspect_repo
from gaiaforge.ledger import append_record, read_verified
from gaiaforge.models import PlanError, eligible_tasks, validate_plan
from gaiaforge.verification import compare_evaluations, run_verification


def task(id, phase="inspect", depends_on=None, side_effect="read", environment="sandbox", approval_required=False):
    return {"id": id, "phase": phase, "side_effect": side_effect, "environment": environment, "depends_on": depends_on or [], "acceptance": "verified evidence", "budget_seconds": 30, "approval_required": approval_required}


class PlanTests(unittest.TestCase):
    def test_valid_plan_and_eligibility(self):
        tasks = validate_plan({"tasks": [task("inspect"), task("test", "test", ["inspect"]), task("review", "review", ["test"]), task("release", "release", ["review"], "external_write", "staging", True)]})
        self.assertEqual(eligible_tasks(tasks, set()), ["inspect"])
        self.assertEqual(eligible_tasks(tasks, {"inspect"}), ["test"])

    def test_cycle_blocked(self):
        with self.assertRaises(PlanError):
            validate_plan({"tasks": [task("a", depends_on=["b"]), task("b", depends_on=["a"])]})

    def test_unknown_dependency_blocked(self):
        with self.assertRaises(PlanError):
            validate_plan({"tasks": [task("a", depends_on=["missing"])]})

    def test_duplicate_ids_blocked(self):
        with self.assertRaises(PlanError):
            validate_plan({"tasks": [task("a"), task("a")]})

    def test_unapproved_prod_blocked(self):
        with self.assertRaises(PlanError):
            validate_plan({"tasks": [task("prod", environment="production")]})

    def test_self_approved_release_blocked(self):
        with self.assertRaises(PlanError):
            validate_plan({"tasks": [task("release", phase="release")]})

    def test_release_without_tests_blocked(self):
        with self.assertRaises(PlanError):
            validate_plan({"tasks": [task("review", phase="review"), task("release", "release", ["review"], approval_required=True)]})

    def test_bad_budget_type_blocked(self):
        item = task("a")
        item["budget_seconds"] = True
        with self.assertRaises(PlanError):
            validate_plan({"tasks": [item]})


class LedgerTests(unittest.TestCase):
    def test_append_and_verify(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ledger.jsonl"
            first = append_record(path, "baseline", {"score": 0})
            second = append_record(path, "candidate", {"score": 1})
            self.assertEqual(second["previous_hash"], first["hash"])
            self.assertEqual(len(read_verified(path)), 2)

    def test_tampering_detected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ledger.jsonl"
            append_record(path, "test", {"score": 0})
            path.write_text(path.read_text().replace('"score":0', '"score":9'))
            with self.assertRaises(ValueError):
                read_verified(path)


class InspectionTests(unittest.TestCase):
    def test_ignores_secrets_and_symlinks(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "main.py").write_text("print('hello')")
            (root / ".env").write_text("SECRET=not-for-inspection")
            (root / "link.py").symlink_to(root / "main.py")
            output = inspect_repo(root)
            self.assertEqual([x["path"] for x in output["files"]], ["main.py"])


class VerificationTests(unittest.TestCase):
    def test_execution_opt_in_required(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(PermissionError):
                run_verification(Path(directory), "unittest")

    def test_unknown_check_not_allowed(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                run_verification(Path(directory), "rm -rf", authorized=True)

    def test_comparison_promotes_only_verified_fix(self):
        result = compare_evaluations({"suite_id": "fixed-v1", "passed": False}, {"suite_id": "fixed-v1", "passed": True})
        self.assertTrue(result["recommend_promotion"])
        self.assertTrue(result["human_approval_required"])

    def test_mismatched_suite_cannot_promote(self):
        result = compare_evaluations({"suite_id": "a", "passed": False}, {"suite_id": "b", "passed": True})
        self.assertFalse(result["recommend_promotion"])

    def test_regression_cannot_promote(self):
        result = compare_evaluations({"suite_id": "a", "passed": True}, {"suite_id": "a", "passed": False})
        self.assertFalse(result["recommend_promotion"])


if __name__ == "__main__":
    unittest.main()
