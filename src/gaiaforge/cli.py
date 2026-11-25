"""CLI for evidence-first engineering. No model API or deployment side effects."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .inspect import inspect_repo
from .ledger import append_record, read_verified
from .models import eligible_tasks, validate_plan
from .staging import stage_proposal, ProposalError
from .verification import compare_evaluations, run_verification
from .sandbox import sandbox_verify, compare_sandbox_runs
from .improvement import assess_candidates
from .provenance import verify_receipt
from .protocol import freeze_protocol, verify_experiment


def load_json(path: str) -> dict:
    with open(path, encoding="utf-8") as stream:
        data = json.load(stream)
    if not isinstance(data, dict):
        raise ValueError("expected a JSON object")
    return data


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="gaiaforge", description="GaiaForge Core v0.6.0")
    commands = parser.add_subparsers(dest="command", required=True)
    inspect = commands.add_parser("inspect", help="hash a bounded, allowlisted file inventory")
    inspect.add_argument("path")
    plan = commands.add_parser("plan", help="validate a task DAG; no tasks are executed")
    plan.add_argument("file")
    verify = commands.add_parser("verify", help="run a predefined check, with explicit authorization")
    verify.add_argument("path")
    verify.add_argument("--check", choices=["unittest", "pytest", "ruff"], default="unittest")
    verify.add_argument("--authorize-execution", action="store_true")
    verify.add_argument("--timeout", type=int, default=60)
    compare = commands.add_parser("compare", help="compare fixed-suite evaluation records")
    compare.add_argument("baseline")
    compare.add_argument("candidate")
    append = commands.add_parser("record", help="add a chained evidence record")
    append.add_argument("ledger")
    append.add_argument("kind")
    append.add_argument("payload", help="JSON file containing a payload object")
    stage = commands.add_parser("stage", help="stage checksum-locked text edits in a separate review workspace")
    stage.add_argument("source")
    stage.add_argument("proposal")
    stage.add_argument("destination")
    stage.add_argument("--ledger", help="optional append-only evidence ledger, outside workspace")
    sandbox = commands.add_parser("sandbox-verify", help="opt-in Docker-only verification; never host fallback")
    sandbox.add_argument("path")
    sandbox.add_argument("--image", required=True, help="locally available image@sha256 digest")
    sandbox.add_argument("--authorize-execution", action="store_true")
    sandbox.add_argument("--timeout", type=int, default=60)
    sandbox.add_argument("--ledger")
    sandbox_compare = commands.add_parser("sandbox-compare", help="compare saved Docker verification reports")
    sandbox_compare.add_argument("baseline")
    sandbox_compare.add_argument("candidate")
    improve = commands.add_parser("assess-improvements", help="review bounded proposal candidates using frozen Docker reports")
    improve.add_argument("manifest")
    improve.add_argument("--ledger")
    receipt = commands.add_parser("verify-receipt", help="check saved Docker report against ledger receipt")
    receipt.add_argument("report")
    receipt.add_argument("ledger")
    receipt.add_argument("--expected-head", help="head hash obtained from a separately trusted source")
    freeze = commands.add_parser("freeze-protocol", help="freeze a suite and pinned image without execution")
    freeze.add_argument("path")
    freeze.add_argument("destination", help="new JSON file outside evaluated repository")
    freeze.add_argument("--image", required=True)
    freeze.add_argument("--id", required=True, dest="protocol_id")
    experiment = commands.add_parser("verify-experiment", help="review paired Docker receipts against frozen protocol")
    experiment.add_argument("protocol")
    experiment.add_argument("baseline_report")
    experiment.add_argument("baseline_ledger")
    experiment.add_argument("candidate_report")
    experiment.add_argument("candidate_ledger")
    experiment.add_argument("--baseline-head")
    experiment.add_argument("--candidate-head")
    audit = commands.add_parser("audit", help="verify ledger hash chain")
    audit.add_argument("ledger")
    args = parser.parse_args(argv)
    try:
        if args.command == "inspect":
            output = inspect_repo(Path(args.path))
        elif args.command == "plan":
            tasks = validate_plan(load_json(args.file))
            output = {"valid": True, "task_count": len(tasks), "eligible_without_approval": eligible_tasks(tasks, set())}
        elif args.command == "verify":
            output = run_verification(Path(args.path), args.check, authorized=args.authorize_execution, timeout=args.timeout)
        elif args.command == "compare":
            output = compare_evaluations(load_json(args.baseline), load_json(args.candidate))
        elif args.command == "stage":
            output = stage_proposal(Path(args.source), Path(args.proposal), Path(args.destination),
                                    evidence_ledger=Path(args.ledger) if args.ledger else None)
        elif args.command == "sandbox-verify":
            output = sandbox_verify(Path(args.path), image=args.image, authorized=args.authorize_execution,
                                    timeout=args.timeout, evidence_ledger=Path(args.ledger) if args.ledger else None)
        elif args.command == "sandbox-compare":
            output = compare_sandbox_runs(load_json(args.baseline), load_json(args.candidate))
        elif args.command == "assess-improvements":
            output = assess_candidates(Path(args.manifest), evidence_ledger=Path(args.ledger) if args.ledger else None)
        elif args.command == "verify-receipt":
            output = verify_receipt(Path(args.report), Path(args.ledger), expected_head=args.expected_head)
        elif args.command == "freeze-protocol":
            output = freeze_protocol(Path(args.path), Path(args.destination), image=args.image,
                                     protocol_id=args.protocol_id)
        elif args.command == "verify-experiment":
            output = verify_experiment(Path(args.protocol), Path(args.baseline_report), Path(args.baseline_ledger),
                                       Path(args.candidate_report), Path(args.candidate_ledger),
                                       expected_baseline_head=args.baseline_head,
                                       expected_candidate_head=args.candidate_head)
        elif args.command == "record":
            output = append_record(Path(args.ledger), args.kind, load_json(args.payload))
        else:
            records = read_verified(Path(args.ledger))
            output = {"valid": True, "record_count": len(records), "head_hash": records[-1]["hash"] if records else None}
        print(json.dumps(output, indent=2))
        return 0
    except (ValueError, PermissionError, OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
