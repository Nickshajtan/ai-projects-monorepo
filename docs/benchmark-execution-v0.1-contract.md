# Benchmark Execution v0.1 Contract

Date: 2026-09-23

Benchmark Execution v0.1 is a local, generic execution harness for producing
Observation Records from one explicitly selected benchmark condition. The runner
is intentionally narrow:

- it prepares one treatment artifact;
- creates one disposable Git workspace;
- writes the artifact as neutral `task.md`;
- invokes one configured target command with the stable prompt `Implement task.md`;
- captures stdout, stderr, diff, untracked files, grader output, execution metadata,
  and the Observation Record;
- removes the disposable workspace unless explicitly asked to keep it.

It does not implement experiment orchestration, matrix scheduling, retries,
provider adapters, comparative analysis, aggregation, or treatment ranking.

## Target Contract

Execution targets are capability-qualified concrete CLIs. The generic runner only
knows:

```text
command + args + cwd + env + timeout
```

A target configuration is suitable for Benchmark Execution v0.1 when it can:

- run non-interactively;
- identify the exact target and model in the target config;
- receive the stable prompt `Implement task.md`;
- run with the disposable benchmark workspace as `cwd`;
- read `task.md` from that workspace;
- modify files inside that workspace;
- require no human intervention during an observation;
- terminate in a way the generic runner can record.

Provider-specific authentication, permission, sandbox, approval, TLS, and wrapper
details belong in target configuration and factual spawn notes. They are not
normalized into a runner abstraction in v0.1.

Current provider qualification notes:

- `docs/codex-cli-spawn-findings.md`
- `docs/gemini-cli-spawn-findings.md`
- `docs/claude-cli-spawn-findings.md`

## Output Capture

Target stdout and stderr are evidence, not control channels. The runner captures
them with deterministic UTF-8 decoding and replacement for malformed byte
sequences. Valid UTF-8 output is preserved normally; undecodable bytes are
represented with the Unicode replacement character so evidence collection is not
disrupted by provider, terminal, or Windows code-page differences.

The evidence package should always include `stdout.txt` and `stderr.txt`, even
when the target exits nonzero, times out, emits malformed bytes, or fails to
start.

## Revision Discipline

Each Observation Record includes `execution.monorepo_commit`; this is the source
of truth for the repository revision used by that observation.

Smoke and target-qualification runs may occur across multiple commits while the
execution layer itself is being stabilized. Real comparative experiment batches
should not do that silently. All observations belonging to one comparative
experiment batch should be executed against one pinned monorepo revision unless
the experiment explicitly defines otherwise.

Benchmark Execution v0.1 does not add an orchestration layer to enforce this
across runs. Batch-level tooling or manual experiment procedure must compare the
per-observation `monorepo_commit` values before analysis.

## ai-doc No-Op Treatment Semantics

The `ai-doc` treatment may legitimately produce an artifact byte-identical to the
original source instruction corpus. This is not an execution failure and must not
be fixed by forcing `ai-doc` to modify the corpus.

Observed smoke example:

```text
original artifact_sha256 = 3fa56e31f6d5f1c9241a14b73cd4ecac251b3d1cc93247be4b5026998eca6616
ai-doc artifact_sha256   = 3fa56e31f6d5f1c9241a14b73cd4ecac251b3d1cc93247be4b5026998eca6616
```

In that case `ai-doc` reported no material objective improvement and no
recommended candidate; the deterministic fallback selected `C001`, which was
identical to the source.

Semantic rules:

- an `ai-doc` treatment may validly be a no-op;
- the resulting observation remains valid if execution and grading are otherwise valid;
- provenance must preserve the `ai-doc` run and selection information;
- later analysis must distinguish "ai-doc applied and produced no material
  treatment change" from "ai-doc applied and produced a changed treatment";
- equality with original must not by itself be interpreted as evidence that an
  actual textual transformation had no behavioral effect.

For v0.1, derive this from artifact identity and treatment provenance during
analysis rather than expanding the Observation schema.

## Frozen Scope

Benchmark Execution v0.1 is frozen at the generic execution layer once focused
tests pass. Further work should proceed as experimental data collection or
separate analysis tooling, not as additional execution architecture.
