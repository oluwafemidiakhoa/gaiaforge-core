# GaiaForge v0.3 — controlled container verification

**Experimental.** The `sandbox-verify` CLI is Docker-only and opt-in. It is not a verified
security boundary for adversarial code. Use a dedicated hardened Docker VM or host,
never a privileged production workstation. Docker daemon access is itself privileged.

## What is implemented

- Rejects missing execution authorization and unknown test commands.
- Accepts locally present container images pinned by `@sha256:` only; does not pull.
- Copies supported non-hidden repository files to an ephemeral filtered snapshot,
  excluding `.env`, `.git`, virtual environments and cache directories. This prevents
  straightforward accidental exposure; it is **not a comprehensive secret scanner**.
- Mounts the snapshot read-only and requests no network, all Linux capabilities dropped,
  a non-root UID, no new privileges, limits for CPU, memory and processes, and a read-only
  root filesystem with a bounded tmpfs.
- Requests forced removal of a specifically named container after Docker CLI timeout.
  A failed cleanup is treated as an error requiring human investigation.
- Records the test suite digest, snapshot digest, pinned image, result, output hash,
  resource settings and an optional ledger entry. Evidence-chain heads must be anchored
  elsewhere to be tamper-evident against a full rewrite.
- Only recommends **review** for a newly passing candidate with equal test-suite hash,
  image and check. Never authorizes release or a merge.

## Prerequisites

1. An isolated Docker Engine / Docker Desktop environment that the operator explicitly authorizes.
2. A **previously obtained and inspected** image with a known digest and Python/unittest available.
3. An approved source checkout. Run only with evaluation suites you trust and have frozen.
4. Run separately on baseline and candidate under the exact same test suite and pinned image.

## Commands

```powershell
# Docker must exist and have access to the local pinned image.
docker version
docker image inspect "python@sha256:REPLACE_WITH_REAL_64_HEX_DIGEST"

# Use actual locally available digest, never the example placeholder.
gaiaforge sandbox-verify . --image "python@sha256:ACTUAL_DIGEST" --authorize-execution --timeout 60 --ledger ..\gaiaforge-verification.jsonl

gaiaforge audit ..\gaiaforge-verification.jsonl

# Compare independently saved JSON reports (not the ledger payload).
gaiaforge sandbox-compare baseline-report.json candidate-report.json
```

The current CLI prints a JSON report to standard output. Redirect each run to separate
files if you want to compare them later. Do not use a ledger file inside the evaluated
repository. On Windows, keep the ephemeral snapshot on a Docker-shareable drive.

## Limitations and release gates

- A container shares the host kernel. Docker daemon compromise, kernel vulnerabilities,
  unsafe daemon configuration, volume sharing, and host-dependent limits are not eliminated.
- Docker Desktop, WSL2 and native Linux have different mount semantics and security boundaries.
- The command-line result is not independently attested; no container integration execution
  has been performed in this release environment because Docker was unavailable.
- The content snapshot is filtered by file names and extensions and can still include
  sensitive material in legitimate source files. Review before execution or use a
  separately isolated runner and an enforceable secrets policy.
- Baseline/candidate comparison relies on caller-supplied report files; add signed
  provenance, trusted evaluation fixtures, Git commit identity and independent scoring
  before claiming reliable autonomous self-improvement.
- There is no model adapter, MCP runtime, automated code editing, or recursive loop yet.
- **Never merge, deploy or enable autonomous execution solely because tests pass.**
