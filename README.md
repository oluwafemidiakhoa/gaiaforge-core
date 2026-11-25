# GaiaForge Core v0.1

**Evidence-first engineering workflows with bounded plans, explicit verification, and a chained Improvement Ledger.**

GaiaForge is an experimental GaiaLab project. Version 0.1 is a **working orchestration and verification foundation**, not an autonomous software engineer. It does not include a live LLM coding agent, MCP runtime, container sandbox, deployment automation, or scientific validation claims.

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

## Architecture

- `models.py`: bounded task DAGs, dependencies, approval requirements, no self-approved release
- `inspect.py`: allowlisted repository file inventory and SHA-256 digests
- `verification.py`: opt-in bounded test runner and fixed-suite comparison
- `ledger.py`: append-only *convention* with hash chaining and integrity audit
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

1. Implement isolated per-task workers with resource/network constraints and a host authorization boundary.
2. Add code dependency graph and actual model adapters in *proposal-only* mode.
3. Freeze and sign evaluation manifests and benchmark suites; add regression and adversarial tests.
4. Introduce independent promotion policy, reviewer sign-off, and external ledger anchoring.
5. Add provenance queries, OpenTelemetry traces, and a research-grade evidence graph.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for boundaries and threat model.

## License

Apache-2.0. See `LICENSE`.

## Publishing to GitHub

Follow [docs/PUBLISH.md](docs/PUBLISH.md) to create a new remote without altering an existing repository.
