# Pyramid Validation Pilot v0.1 Findings

Evidence root:

```text
benchmarks/ai-doc-benchmark/runs/pyramid-pilot-20260923
```

This pilot used the existing production interfaces and Benchmark Execution v0.1.
No new benchmark framework, analysis subsystem, provider adapter hierarchy, or
grader framework was added.

## A0 Diagnostic Pilot

Production interface:

```text
python -m ai_doc check <fixture> --format json --non-interactive
```

Fixtures:

```text
a0-fixtures/
```

Summary file:

```text
a0-a1-check-summary.json
```

Result:

- `exact-dup-positive` produced `FINOPS_DUPLICATE_PARAGRAPH`.
- `literal-contradiction-positive` produced `RISK_LITERAL_CONTRADICTION` and
  exited `2`, matching a blocking deterministic finding.
- `structure-positive` produced `STRUCTURE_HEADING_JUMP`.
- `exact-dup-negative`, `literal-contradiction-negative`, and
  `already-good-negative` produced no findings.

Approximate runtime:

- about 1.2-1.4 seconds per fixture on this machine.

Interpretation:

- A0 behaved like a reliable narrow static/lint tier on the tiny diagnostic set.
- The positive findings were mechanically precise.
- No broad A0 fixture expansion was needed for this pilot.

## A1 Incremental Pilot

Production interface:

```text
python -m ai_doc check <fixture> --format json --non-interactive
```

Configuration:

```yaml
local_ml:
  enabled: true
  semantic_duplication: true
  semantic_contradiction: true
```

Default production model ids were used:

```text
sentence-transformers/all-MiniLM-L6-v2
cross-encoder/nli-deberta-v3-small
similarity_threshold: 0.90
nli_confidence_threshold: 0.90
```

Result:

- Every A1 fixture produced `RISK_LOCAL_ML_UNAVAILABLE` from the semantic
  analyzer paths.
- No semantic duplicate or semantic contradiction judgment actually executed.

Approximate runtime:

- about 1.2-1.3 seconds per fixture, because model loading failed quickly.

Interpretation:

- A1 production behavior is reachable, but this environment is not provisioned
  with the pinned local model dependencies.
- The pilot cannot claim incremental A1 semantic value from this run.
- Further A1 validation is blocked on explicit local-model provisioning, not on
  benchmark runner architecture.

## B Predictive Pilot

Status:

```text
BLOCKED_BY_PRODUCT_INTERFACE
```

Record:

```text
b-c1-blockers.json
```

Reason:

- Production B currently exists through `check --deep` and optimizer semantic /
  pairwise paths.
- The pilot needed a blinded baseline-vs-candidate prediction over benchmark
  treatment artifacts before C2 outcomes.
- No standalone production B interface currently accepts those treatment pairs
  directly without converting benchmark cases into product evaluation suites or
  driving optimizer-specific semantics.

Interpretation:

- This is a real interface gap.
- Building a generic B judge during the pilot would be substantial new
  infrastructure, so the B experiment was deferred.

## C1 Planning Pilot

Status:

```text
DEFER_C1
```

Record:

```text
b-c1-blockers.json
```

Reason:

- Product C1 uses `ai-doc probe` with the `AI_DOC_TARGET_COMMAND` JSON
  stdin/stdout contract.
- The already qualified Codex/Gemini/Claude target configs are native
  natural-language `task.md` execution commands, not JSON planning adapters.

Interpretation:

- C1 can only be tested once a small target-command adapter exists for at least
  one target, or once benchmark cases are translated into product evaluation
  scenarios.
- That adapter work was judged outside this narrow pilot pass.

## C2 Discriminative Scan

Initial preferred cells:

```text
quality-cohort-shared-low
quality-cohort-shared-medium
quality-cohort-shared-high
```

These were attempted first and deferred. Every attempted cell failed during
treatment preparation before target startup because the current corpus entries
do not define deterministic treatment artifacts. They also do not currently
define executable deterministic graders, so expanding them would require corpus
and grader work.

Replacement case:

```text
duplication-generated-contract-low
```

Reason:

- It is the only current case with deterministic treatment artifacts and an
  executable deterministic grader.

Targets:

```text
codex-gpt-5-approve-smoke
gemini-3.5-flash-yolo-smoke
claude-sonnet-5-bypass-smoke
```

Treatments:

```text
original
degraded-control
simple-compression-control
ai-doc
```

Observation summary:

```text
c2-observation-summary.json
```

Command summary:

```text
c2-scan-command-summary.json
```

Result:

- 12 replacement C2 observations were produced.
- All 12 observations reached `target_started: true`.
- All 12 observations reached `termination_status: completed`.
- All 12 deterministic graders executed.
- Gemini and Claude satisfied all task and instruction criteria for all four
  treatments.
- Codex started but failed all four task-success/source-update criteria with
  exit code `1`; stderr shows `401 Unauthorized` from the Codex API transport.
  The generated evidence is valid execution evidence, but the pilot should treat
  these Codex cells as target-auth/infrastructure-limited rather than behavioral
  evidence about instruction quality.

Interpretation:

- C2 execution evidence collection works with the existing harness for cases
  that have artifacts and graders.
- The current executable corpus is too small for the pilot's intended
  discriminative scan.
- On the one executable case, Gemini and Claude were ceiling-saturated across
  treatments in one repetition; no additional repetitions are justified from
  this pass.
- Codex requires authentication/configuration repair before its C2 results can
  be interpreted behaviorally.

## Cross-Tier Notes

- A0 worked on tiny intrinsic fixtures and can be treated as a reliable narrow
  static signal for exact duplication, literal contradiction, and heading-jump
  structure checks.
- A1 did not run semantic inference in this environment, so no A0 -> A1
  incremental-value claim is supported yet.
- B -> C2 could not be tested without a production-interface decision.
- C1 -> C2 could not be tested without a target-command adapter.
- C2 collected real evidence, but current executable coverage is effectively
  one case.

## Recommended Next Step

Do not build analysis infrastructure yet.

The next concrete blocker to remove is corpus executability for the intended
pilot cases:

1. add deterministic treatment artifacts for the selected
   `quality-cohort-shared-*` cases;
2. add focused deterministic graders for those cases;
3. rerun the same C2 scan shape before adding repetitions or cross-tier
   analysis.

For A1, provision pinned local models before rerunning semantic fixtures. For B
and C1, decide whether to add the smallest product-facing interfaces/adapters or
to defer those tiers from v0.1 empirical validation.
