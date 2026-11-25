# GaiaForge Core — Architectural boundaries

## Goal

A reproducible foundation for a future AI engineering platform where every proposed change has independent test evidence, bounded execution, and a reviewable promotion decision.

## Trust boundaries

1. **User input and repositories are untrusted.** Source code and test scripts can execute malicious commands; inspection only hashes allowlisted files, while `verify` requires explicit authorization and is suitable only for trusted checkouts.
2. **Model output is a proposal, not an authorization.** Version 0.1 does not connect an LLM; a future model adapter must not grant its own tools or approvals.
3. **The ledger is evidence, not proof of correctness.** Hash chaining detects mutation relative to an independently pinned head; payload claims need real artifacts and reproducible checks.
4. **Staging and production are different authorities.** Releases require independent human approval; this package contains no release executor.
5. **Scientific testing is separate from software CI.** Successful unit tests never imply research validity or model performance.

## Reference flow

`Objective -> validated task DAG -> repository inventory -> proposed changes (future) -> independent frozen tests -> conservative comparison -> evidence ledger -> human review -> authorized release (future)`

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
