# GaiaForge v0.6 — frozen paired evaluation

Experimental research support. No autonomous execution, promotion, signed attestation, or trusted-builder identity is provided.

A frozen protocol binds the *expected* Python unittest suite hash and a locally available immutable Docker image. The protocol checksum detects accidental changes **if the expected checksum is retained independently**; anyone who can replace both protocol and checksum can forge it. Preserve the protocol and external ledger heads in a separately trusted location **before** candidate evaluation.

## Read-only preparation (no code execution)

```cmd
cd /d "%USERPROFILE%\Downloads\gaiaforge-workspace"
gaiaforge freeze-protocol . "..\gaiaforge-v06-protocol.json" --image "python@sha256:191083cdf6c7bda8c76158983163ead5d5cf7b77cf3033e805bb0f5296f51b4b" --id baseline-2026-11
```

Freeze *before* changing tests or looking at candidate outcomes. Never overwrite an existing freeze. This protects against unnoticed local drift, not adversarial tampering by an operator with unrestricted file access.

## Paired evaluation

On a dedicated isolated Docker host, run the same pinned image and unchanged tests against two authorized source checkouts, using separate ledger files **outside** each checkout. Save the JSON stdout of `gaiaforge sandbox-verify` as separate reports. Do not reuse ledger paths from previous runs for this experiment if you want an unambiguous, one-record ledger head.

```cmd
gaiaforge verify-experiment "..\gaiaforge-v06-protocol.json" baseline-report.json baseline-ledger.jsonl candidate-report.json candidate-ledger.jsonl
```

For externally preserved heads, add `--baseline-head <64 hex>` and `--candidate-head <64 hex>`. These flags check heads against the supplied values but **cannot verify that those values came from a trusted source**.

A qualifying newly passing candidate returns `human_review_required`, `automatic_promotion=false`, and `release_authorized=false`. Caller-controlled reports can still be manufactured in concert with ledgers, so the result is **not execution authentication**.

## Additional adversarial checks remaining

- Real timeout and forced-removal behavior using a trusted nonterminating test fixture on an isolated runner.
- Direct observation of network and filesystem restrictions, not only Docker flags.
- Signed CI identity and tamper-evident external protocol/ledger anchor.
- Independent holdout tests to reduce selection bias and test-suite gaming.

Never execute unknown AI-produced code on an ordinary personal or production workstation.
