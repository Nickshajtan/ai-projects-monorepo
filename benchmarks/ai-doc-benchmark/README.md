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

- a versioned starter corpus with 16 benchmark cases;
- case metadata for categories, quality cohorts, and relevant `ai-doc` capabilities;
- source instruction corpora, initial workspace state, tasks, and observable ground
  truth criteria;
- treatment-control metadata for original, simple-compression, and degraded controls;
- validation helpers for benchmark cases and normalized observation records.

It does not invoke coding agents, run `ai-doc`, schedule repetitions, or aggregate
results. Those execution mechanics belong to a separate benchmark execution layer.

## Validate

```powershell
$env:PYTHONPATH = "src"
python -m ai_doc_benchmarks validate corpus/benchmark-corpus-v0.1.json
python -m unittest discover -s tests
```

The validator checks that corpus data preserves the experimental semantics required by
the benchmark definition without encoding comparative conclusions such as "winner",
"improvement", or "regression".
