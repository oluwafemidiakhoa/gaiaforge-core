# GaiaForge Core v0.3

**Evidence-first engineering workflows with bounded plans, explicit verification, and a chained Improvement Ledger.**

GaiaForge is an experimental GaiaLab project. Version 0.3 adds a **Docker-backed, explicitly authorized verification runner** with a filtered source snapshot. It remains an experimental foundation, not an autonomous software engineer. It does not include a live LLM coding agent, MCP runtime, production deployment, or scientific validation claims.

## Install

Requires Python 3.10+.

```bash
python -m venv .venv
# Windows PowerShell: .venv\\Scripts\\Activate.ps1
# Linux/macOS: source .venv/bin/activate
python -m pip install -e .
python -m unittest discover -s tests -v
```

## Start using it

```bash
gaiaforge inspect .
gaiaforge plan examples/plan.json
gaiaforge compare examples/baseline.json examples/candidate.json
gaiaforge record .gaiaforge/evidence.jsonl candidate examples/evidence.json
gaiaforge audit .gaiaforge/evidence.jsonl
```

Run tests on a **trusted local checkout only**; test execution is *not* sandboxed:

```bash
gaiaforge verify . --check unittest --authorize-execution --timeout 60
```

The `verify` command is opt-in because even a predefined `unittest` or `pytest` invocation may execute arbitrary repository code. Never run verification against an untrusted repository on your host machine. Use a separately provisioned sandbox before integrating an autonomous coding agent.

### Optional API

```bash
python -m pip install -e '.[api]'
uvicorn gaiaforge.api:app --host 127.0.0.1 --port 8000
```

Endpoints: `GET /health`, `POST /plans/validate`, `POST /evaluations/compare`. The optional API is read-only and intentionally has no network-accessible execution endpoint.

## Checksum-locked change proposals (new in v0.2)

`stage` reads a JSON proposal, verifies original file hashes, copies allowlisted text files
into a **separate review workspace**, applies bounded replacements and performs Python AST
syntax checks. It does not execute the proposed code, access a model, or deploy changes.

```bash
# Create a small trusted test repository and generate a proposal for it:
python examples/make_staging_demo.py
# Stage a copy; the original demo/source directory remains unchanged:
gaiaforge stage demo/source demo/proposal.json demo/review --ledger demo/evidence.jsonl
# Independently audit the evidence chain:
gaiaforge audit demo/evidence.jsonl
```

**Security note:** copying files to a directory does not constitute security isolation.
Do not execute untrusted source in a staged workspace on your host. The staging command
rejects path traversal, symlinks, unknown file types, oversized proposals and stale SHA-256
baselines. Syntax validation is not a safety or correctness guarantee. A future code agent
will need a separately enforced operating-system or VM isolation boundary.

The format of a proposal is:

```json
{
  "proposal_id": "fix-001",
  "operations": [
    {"path": "main.py", "previous_sha256": "<64 lowercase hex characters>", "content": "value = 2\n"}
  ]
}
```

Use `null` for `previous_sha256` when adding a new file.

## Docker-only controlled verification (experimental, new in v0.3)

The `sandbox-verify` command creates a temporary filtered source snapshot and executes
allowlisted `unittest` checks in a locally available, digest-pinned Docker image. It
requires `--authorize-execution` and **never falls back to the host**. Example:

```bash
gaiaforge sandbox-verify . --image "python@sha256:YOUR_REAL_IMAGE_DIGEST" --authorize-execution --timeout 60 --ledger ../verification.jsonl
gaiaforge audit ../verification.jsonl
gaiaforge sandbox-compare baseline-report.json candidate-report.json
```

The image value above is a placeholder: identify and inspect an actual installed digest
first. Docker must be installed and authorized. A dedicated isolated Docker host/VM is
recommended for untrusted input. **Container execution was not integration-tested in
this build environment because Docker was unavailable.** The container is not a
certified sandbox. See [the verification guide](docs/CONTAINER_VERIFICATION.md) for
security limitations and Windows prerequisites.

## Architecture

- `models.py`: bounded task DAGs, dependencies, approval requirements, no self-approved release
- `inspect.py`: allowlisted repository file inventory and SHA-256 digests
- `verification.py`: opt-in bounded test runner and fixed-suite comparison
- `ledger.py`: append-only *convention* with hash chaining and integrity audit
- `staging.py`: checksum-locked, bounded source-copy staging and static syntax checks
- `sandbox.py`: opt-in Docker-only verification, filtered snapshot and conservative comparison
- `cli.py`: command-line workflows
- `api.py`: optional read-only FastAPI service
- `tests/`: regression and negative safety tests

### Non-goals / security limitations

- Plan validation does **not** grant permissions, execute tasks, or satisfy change-management approval.
- A hash chain is tamper-*evident only if its head is anchored externally*. Anyone who can rewrite the entire local ledger can forge a new chain.
- The inventory does not parse source code into dependency graphs and must not be considered a secret scanner.
- CLI test execution is **not** a sandbox. Use DevVM, container isolation, or an equivalent separately evaluated execution boundary before running untrusted agent-generated code.
- Improvement comparisons are conservative but simplistic: a matching suite ID and passing result are not sufficient scientific evidence that a change generalizes. Baselines, test provenance, budgets and human approvals must be independently enforced before release.
- Treat output excerpts and evidence payloads as potentially sensitive; use authorized repositories and an appropriate data retention policy.

## Roadmap

1. Integration-test and harden container-based workers on a dedicated Docker host/VM; ensure host-enforced grants and pinned images.
2. Add code dependency graph and actual model adapters in *proposal-only* mode.
3. Freeze and sign evaluation manifests and benchmark suites; add regression and adversarial tests.
4. Introduce independent promotion policy, reviewer sign-off, and external ledger anchoring.
5. Add provenance queries, OpenTelemetry traces, and a research-grade evidence graph.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for boundaries and threat model.

## License

Apache-2.0. See `LICENSE`.

## Publishing to GitHub

Follow [docs/PUBLISH.md](docs/PUBLISH.md) to create a new remote without altering an existing repository.

## v0.4 — Evidence-gated candidate assessment

Version 0.4 adds `gaiaforge assess-improvements` for **read-only** comparison of up to
five independently supplied baseline/candidate Docker reports and JSON code proposals.
It rejects incompatible suites, forged-looking inconsistent flags, invalid digests,
unsafe manifest paths and over-budget candidate lists. A newly passing candidate is
marked `human_review_required` only; releases and automatic promotion stay disabled.

```cmd
python examples\improvement\make_demo.py
gaiaforge assess-improvements examples\improvement\generated\manifest.json
```

The example reports are **synthetic**. See `docs/IMPROVEMENT_GATE.md` for format,
security limitations and evidence provenance requirements. No live LLM agent,
automated patch generation or self-modifying recursion is implemented in v0.4.

## v0.5: receipt cross-checking (experimental)

The `verify-receipt` command compares a saved `sandbox-verify` JSON report with
its chained ledger entry, optionally comparing the ledger head to an independently
saved hash. Container reports also include best-effort Git HEAD/clean-worktree
metadata only when the path is the root of its own checkout, protecting against
accidentally picking up a Git repository in a parent Windows user directory.
This is **not authenticated provenance**, and release authorization remains false.
See [the receipt verification guide](docs/RECEIPT_VERIFICATION.md).
