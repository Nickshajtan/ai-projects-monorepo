# Pyramid Pilot Hardening: Discriminative C2 Findings

Evidence root:

```text
benchmarks/ai-doc-benchmark/runs/pyramid-pilot-discriminative-20260923
```

This run hardened only the concrete blockers named by the pilot specification.
Benchmark Execution v0.1 was not changed.

## Changes Made

The three controlled quality-cohort cases are now executable:

```text
quality-cohort-shared-low
quality-cohort-shared-medium
quality-cohort-shared-high
```

Each case now has:

- deterministic `original`, `degraded-control`, and `simple-compression-control`
  artifacts;
- a case-owned deterministic grader for the shared payment-fee task;
- unchanged underlying task/workspace/ground-truth criteria.

The high-quality case now supports `simple-compression-control` with a concise
semantics-preserving compression instead of being marked non-applicable.

## Preflight

Preflight evidence:

```text
preflight-quality-cohort.json
```

All 12 combinations prepared successfully:

```text
3 quality-cohort cases x 4 treatments
```

For each cell:

- treatment preparation succeeded;
- `task.md` was produced;
- a baseline workspace was created;
- the deterministic grader executed.

The real `ai-doc` treatment prepared successfully for all three cases through
the existing production optimizer path. In all three cases, `ai-doc` reported no
material objective improvement, selected `C001` through deterministic fallback,
and produced an artifact byte-identical to the source treatment.

## A1

Evidence:

```text
a1-provisioning.json
```

Status:

```text
A1_PROVISIONING_BLOCKED
```

Attempted provisioning:

```text
projects/ai-doc/.venv/Scripts/python.exe -m pip install -e "projects/ai-doc[ml]"
```

The install downloaded the expected local-ML stack but stalled during package
installation and was interrupted. After interruption:

- `torch` was installed;
- `sentence-transformers` was not installed;
- `transformers` was not installed.

Therefore semantic inference did not execute in this hardening run. The blocker
is environment provisioning, not benchmark architecture.

## Codex

Evidence:

```text
codex-qualification.json
codex-qualification-2.stderr.txt
```

Status:

```text
TARGET_UNQUALIFIED
```

Codex CLI was reachable:

```text
codex-cli 0.155.1
```

The documented non-interactive `gpt-5` command still failed from the disposable
qualification workspace with exit code `1`; no output file was produced. Stderr
shows `401 Unauthorized` from the OpenAI Responses transport. Codex was excluded
from the C2 scan as required by the spec.

## C2 Scan

Evidence:

```text
c2-scan/
c2-scan-command-summary.json
c2-observation-summary.json
```

Executed matrix:

```text
3 cases x 4 treatments x 2 qualified targets x 1 repetition
```

Targets:

```text
Gemini CLI / gemini-3.5-flash
Claude Code / claude-sonnet-5
```

Codex was not included because requalification failed.

All 24 observations:

- were valid;
- started the target;
- completed without timeout;
- ran the deterministic grader;
- satisfied the payment test;
- updated `src/payments.py`;
- preserved `tests/snapshots/fee.txt`;
- satisfied the critical snapshot criterion.

## C2 Discrimination

Observed classification:

```text
no visible discrimination / ceiling saturation
```

No one-repetition behavioral difference was observed across:

- quality level: low, medium, high;
- treatment: original, degraded-control, simple-compression-control, ai-doc;
- target: Gemini, Claude;
- criterion: task success, required source update, forbidden snapshot
  preservation, critical snapshot preservation.

The degraded controls were plausible weaker instructions, but on this task both
qualified targets still performed the desired source-only fix and preserved the
snapshot.

## ai-doc Treatment

For all three quality-cohort cases:

- `ai-doc` ran through the real optimizer path;
- no material objective improvement was found;
- no recommended candidate was produced;
- deterministic fallback selected `C001`;
- the selected artifact was byte-identical to the original source artifact.

This is a valid no-op treatment result, not an execution failure.

Behaviorally, because `ai-doc` was identical to original in these cases, the C2
observations cannot support a claim that `ai-doc` changed target behavior.

## Repetition Gate

No additional repetitions were run.

Reason:

- every qualified target/case/treatment cell succeeded on all criteria;
- there was no visible instability or target disagreement;
- the scan is ceiling-saturated.

Repeating every cell for symmetry would not satisfy the pilot gate.

## Validation

Commands run:

```text
python -m ai_doc_benchmarks validate corpus/benchmark-corpus-v0.1.json
python -m ai_doc_benchmarks validate --starter-profile corpus/benchmark-corpus-v0.1.json
D:\AI\projects\projects\ai-doc\.venv\Scripts\python.exe -m unittest tests.test_execution tests.test_corpus tests.test_observation_schema
```

Results:

- corpus validation passed;
- starter-profile validation passed;
- focused benchmark tests passed: 29 tests.

An earlier attempt to run unittest with the system `C:\Python313` failed because
that local Python environment could not import the stdlib `difflib` module. The
project venv run passed.

## Next Investment

The next investment should be case redesign or additional C2 cases, not
repetitions of this matrix.

Current evidence supports:

- keeping A0 as a narrow deterministic static tier;
- treating A1 as blocked until local model provisioning is completed cleanly;
- deferring B and C1 until C2 has discriminative behavioral signal;
- improving or adding C2 cases whose degraded/low-quality instructions can
  plausibly change behavior for already-qualified targets.

Do not expand this exact quality-cohort matrix to five repetitions unless a
future target or revised case produces a non-ceiling first scan.
