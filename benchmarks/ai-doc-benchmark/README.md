# ai-doc experimental benchmarks

This directory contains the benchmark definition artifacts for
`ai-doc`. It is intentionally separate from the system under test at
`../../projects/ai-doc`.

The intended scalable workspace shape is:

```text
projects/
  ai-doc/                 # SUT
benchmarks/
  ai-doc-benchmark/       # benchmark project for ai-doc
```

The current implementation covers the definition layer from
`../../ai-doc-benchmark-definition-v0.1.md`:

- a versioned starter corpus with 19 benchmark cases;
- case metadata for categories, quality cohorts, and relevant `ai-doc` capabilities;
- source instruction corpora, initial workspace state, tasks, and observable ground
  truth criteria;
- treatment-control metadata for original, simple-compression, and degraded controls;
- validation helpers for benchmark cases, the starter-corpus profile, and normalized
  observation records.
- a small local execution harness for one explicitly selected benchmark condition.

It does not schedule benchmark sweeps, run comparative analysis, aggregate results,
rank treatments, or draw product conclusions.

The frozen Benchmark Execution v0.1 contract is documented in
`../../docs/benchmark-execution-v0.1-contract.md`.

## Validate

```powershell
$env:PYTHONPATH = "src"
python -m ai_doc_benchmarks validate corpus/benchmark-corpus-v0.1.json
python -m ai_doc_benchmarks validate --starter-profile corpus/benchmark-corpus-v0.1.json
python -m unittest discover -s tests
```

The validator checks that corpus data preserves the experimental semantics required by
the benchmark definition. The starter-profile check additionally verifies the intended
initial category and quality-cohort coverage. Observation records reject comparative
conclusions such as "winner", "improvement", or "regression".

## Execute One Condition

Execution v0.1 is a local developer harness. A configured target command runs with the
permissions and credentials available to the benchmark process; this is not a security
sandbox.

Create a target config:

```json
{
  "id": "codex-default",
  "command": "codex",
  "args": ["exec"],
  "timeout_seconds": 600,
  "model": null
}
```

Then run one selected condition:

```powershell
$env:PYTHONPATH = "src"
python -m ai_doc_benchmarks execute `
  --corpus corpus/benchmark-corpus-v0.1.json `
  --case-id duplication-generated-contract-low `
  --treatment original `
  --target target.json `
  --output-dir runs
```

The runner creates an isolated temporary Git workspace, writes the selected treatment as neutral
`task.md`, invokes the command with the prompt `Implement task.md`, grades the resulting
workspace through the case-owned deterministic grader, writes an Observation Record and
supporting evidence, then removes the temporary workspace after evidence is preserved.
