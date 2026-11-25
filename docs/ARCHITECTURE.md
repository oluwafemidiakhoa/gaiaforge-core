# GaiaForge Core — Architectural boundaries

## Goal

A reproducible foundation for a future AI engineering platform where every proposed change has independent test evidence, bounded execution, and a reviewable promotion decision.

## Trust boundaries

1. **User input and repositories are untrusted.** Source code and test scripts can execute malicious commands; inspection only hashes allowlisted files, while `verify` requires explicit authorization and is suitable only for trusted checkouts.
2. **Model output is a proposal, not an authorization.** Version 0.2 does not connect an LLM; a future model adapter must not grant its own tools or approvals.
3. **The ledger is evidence, not proof of correctness.** Hash chaining detects mutation relative to an independently pinned head; payload claims need real artifacts and reproducible checks.
4. **Staging and production are different authorities.** Releases require independent human approval; this package contains no release executor.
5. **Scientific testing is separate from software CI.** Successful unit tests never imply research validity or model performance.

## Reference flow

`Objective -> validated task DAG -> repository inventory -> checksum-locked change staging (implemented) -> independent frozen tests -> conservative comparison -> evidence ledger -> human review -> authorized release (future)`

## Threat scenarios to test in future releases

- Prompt injection embedded in source files or retrieved documentation
- Agent attempts to access credentials or external network without permission
- Manipulation of acceptance criteria after observing test results
- Suite-ID spoofing and fabricated evaluation outcomes
- Concurrent ledger writes, malicious evidence payloads and full ledger rewrite
- TOCTOU changes between repository inspection and execution
- Symlink escape, filesystem mounts, and uncontrolled subprocess trees
- Resource exhaustion, timeout evasion, and uncontrolled recursive cost

## Safe rollout

Start with local, trusted repository experiments. Introduce a dedicated sandbox, pin images by digest, mount secrets only for the minimum duration, disable network by default, add per-task limits, separate reviewer identity from agent identity and never execute production changes without a host-enforced grant.

## v0.2 staging contract

The staging operation is deterministic. A proposer supplies a JSON object containing a proposal ID and bounded file replacements with SHA-256 baseline preconditions. GaiaForge checks all operations before copying a source snapshot to a separate directory. The original files are not modified. A unified diff, source and destination digests, AST syntax result and a review-required status are returned. Optionally, a digest summary is written to the evidence ledger.

**Explicit limitation:** the copy is NOT container/VM isolation, a security boundary, or a working LLM agent. The stage command does not run proposed code. It performs no recursive self-improvement, external changes, or production writes. Concurrent edits of source during copying require further TOCTOU controls in a later version.
