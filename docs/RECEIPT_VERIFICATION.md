# GaiaForge v0.5: local receipt consistency (experimental)

v0.5 adds `gaiaforge verify-receipt` and best-effort Git identity metadata to the
existing `sandbox-verify` report. This is **local evidence consistency**, not a
signed software supply-chain attestation or a secure remote execution claim.

## Windows CMD walkthrough

Run these commands from a trusted, dedicated GaiaForge workspace on a test-only
Docker host. The command executes trusted source tests; do not run hostile code
on an ordinary personal workstation. The ledger and report must be outside the
source tree. Do not put `.env` or secrets in allowlisted source files.

```cmd
cd /d "%USERPROFILE%\Downloads\gaiaforge-workspace"
python -m pip install -e .

docker image ls --digests python
```

Replace `DIGEST_FROM_DOCKER` with a **full real 64-hex digest** reported by your
local Docker installation. For example, after examining and approving the image:

```cmd
gaiaforge sandbox-verify . --image "python@sha256:DIGEST_FROM_DOCKER" --authorize-execution --timeout 60 --ledger "..\gaiaforge-v05-ledger.jsonl" > "..\gaiaforge-v05-report.json"
gaiaforge verify-receipt "..\gaiaforge-v05-report.json" "..\gaiaforge-v05-ledger.jsonl"
gaiaforge audit "..\gaiaforge-v05-ledger.jsonl"
docker ps -a --filter "name=gaiaforge"
```

Do **not** run a follow-up verifier if `sandbox-verify` failed. A CLI exit status
of zero indicates a completed report, not necessarily that the tests passed;
inspect `passed`, `exit_code`, and `timed_out` in the report.

`verify-receipt` checks the ledger hash chain, the claimed record kind, and
exact field equality between the saved report and the stored ledger payload
(excluding `output_excerpt`, which the ledger deliberately does not retain).
The command rejects missing receipts, mismatched fields and damaged chains.
It does not independently re-run Docker, prove the builder's identity, or
verify the displayed output excerpt against the output hash.

The optional `--expected-head <64-hex-value>` checks a ledger head hash that
**must be retained separately from the report and ledger** to provide useful
rewrite detection. A hash copied from the same untrusted files is not an anchor.
A mutable local JSONL ledger is not tamper-proof.

`git_commit` is reported only when `path` is the root of its *own* Git checkout.
If the checkout has uncommitted changes, `git_worktree_clean` is false. Even
when clean, the Git identity is observational metadata; it is not a
cryptographic assertion that the copied Docker snapshot exactly matches HEAD.

## Known limitations

- No real Docker timeout/forced-cleanup integration exercise in this release.
- Docker Desktop's Linux VM is not a proven containment environment for hostile agents.
- No external signing, transparency log or trusted CI provenance authority.
- No independently authenticated candidate improvements or model adapter.
- No automatic merges, deployments or release grants.
