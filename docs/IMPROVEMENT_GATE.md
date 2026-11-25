# GaiaForge v0.4 — candidate assessment gate

The `assess-improvements` command is a **read-only, bounded evidence comparator**. It does
not generate code, execute proposals, approve releases, merge branches, or validate the
provenance of externally supplied reports. It accepts at most five candidate proposals.

## Manifest schema

```json
{
  "evaluation_id": "evaluation-001",
  "baseline": "baseline-report.json",
  "candidates": [
    {"proposal": "candidate-1-proposal.json", "report": "candidate-1-report.json"}
  ]
}
```

Paths are relative to the manifest file and must remain within its directory. Each
proposal must use GaiaForge's checksum-locked staging schema. The baseline and candidate
reports must come from independently controlled `gaiaforge sandbox-verify` runs, using
exactly the same frozen tests, pinned image, and check.

```cmd
python examples\improvement\make_demo.py
gaiaforge assess-improvements examples\improvement\generated\manifest.json --ledger ..\gaiaforge-improvement-ledger.jsonl
gaiaforge audit ..\gaiaforge-improvement-ledger.jsonl
```

**Warning:** The example generator creates *synthetic* reports to demonstrate the
input contract. A `human_review_required` finding on these reports is not evidence
of any actual improvement, nor permission to merge or deploy.

## Security and scientific limitations

- All report content is caller-supplied and can be forged. Hashes confirm file
  content identity, not trusted origin. An independently run verification service
  and signed provenance are needed before treating a result as genuine.
- A passing change may overfit a fixed suite. Use held-out regression and
  adversarial checks before scientific or production claims.
- Reports with differing suite digest, image, backend or check are not comparable.
- The graph of code dependencies and full recursive agent loop are not implemented.
- The evidence ledger is an unsigned local hash chain; anchor its head externally
  for tamper evidence against total rewrite.
- A review recommendation **never** grants authorization for deployment, merges,
  privileged tool calls or container access.
