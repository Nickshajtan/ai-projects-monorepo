# Pyramid Validation Phase 0: Production Interface Map

This document maps the AI-Doc Benchmark Pyramid Validation Specification v0.1
to the production `ai-doc` implementation that exists now. It is intentionally
limited to Phase 0: interface mapping, corpus gap analysis, and implementation
planning. Benchmark Definition v0.1 and Benchmark Execution v0.1 remain frozen.

## 1. Tier -> Production-Interface Map

### A0: Deterministic Static Analysis

Production status: implemented.

- Production entry points:
  - CLI: `python -m ai_doc check [path]`
  - Module API: `ai_doc.app.run_static_check(root, config, profile, extensions, token_counter)`
  - Optimizer preflight: `ai_doc.optimizer.source_discovery.run_optimization_static_check`
- Implementation paths:
  - `projects/ai-doc/src/ai_doc/cli/check.py`
  - `projects/ai-doc/src/ai_doc/app.py`
  - `projects/ai-doc/src/ai_doc/analyzers/suite.py`
- Built-in analyzers:
  - `StructureAnalyzer`
  - `FinOpsAnalyzer`
  - `DuplicationAnalyzer`
  - `SemanticDuplicationAnalyzer`
  - `ClarityAnalyzer`
  - `ContradictionAnalyzer`
  - `SemanticContradictionAnalyzer`
- A0-relevant deterministic analyzers:
  - structure checks
  - token/context cost checks
  - exact paragraph/list-item duplication
  - deterministic clarity checks
  - literal normative contradiction checks
- Required configuration:
  - `AiDocConfig.include`
  - `AiDocConfig.exclude`
  - `AiDocConfig.profiles`
  - token counter selection, defaulting to approximate token counting
- Optional configuration dimensions:
  - `--profile`
  - `budgets`
  - extension analyzers/adapters, only with `--allow-extensions`
  - token counter extensions
  - observability enablement/path
- Required dependencies/models/providers:
  - no external model dependency for deterministic A0 behavior
  - optional extension processes only when configured
- Inputs:
  - repository/documentation root
  - `.ai-doc.yaml` or default config
  - markdown instruction/reference documents discovered from configured include/exclude rules
- Outputs/artifacts:
  - `CheckReport`
  - console or JSON output from `check`
  - exit code `2` when blocking static errors exist
  - optional JSONL observation when observability is enabled
- Existing observability/provenance:
  - `ai-doc.observation/v1` records command `check`, tier `a0`, tool version,
    config/project fingerprints, finding fingerprints, finding counts, duration,
    and exit code.
- Current benchmark corpus suitability:
  - the corpus can provide instruction documents to A0, but it does not yet carry
    property-level A0 ground truth.
  - behavioral cases with categories such as `duplication`, `contradiction`,
    `routing-scope`, `excessive-context`, and `already-good` are useful starting
    points for behavioral relevance, not intrinsic A0 accuracy.
- Suitable existing cases:
  - `duplication-generated-contract-low`
  - `contradiction-docs-precedence-medium`
  - `quality-cohort-shared-low`
  - `quality-cohort-shared-medium`
  - `quality-cohort-shared-high`
  - `negative-routing-readme-high`
- Additional fixtures required:
  - exact duplicate paragraph positives/negatives, including length boundaries
  - exact duplicate list item positives/negatives, including local unnamed-scope
    exception coverage
  - literal contradiction positives/negatives based on the deterministic
    instruction extractor
  - structural/routing fixtures with expected finding codes
  - token/context budget fixtures with expected thresholds
- Missing benchmark-only infrastructure:
  - A0 runner that invokes the real CLI/API and records finding-code expectations
  - A0 fixture schema for expected present/absent properties
  - result normalizer that maps `CheckReport.findings` to benchmark evidence
- Spec functionality not yet exposed in production:
  - production exposes deterministic findings, but not benchmark-specific
    intrinsic truth labels or benchmark metrics.

### A1: Local Semantic Static Analysis

Production status: partially implemented as optional local-ML analyzers inside
the same static check path.

- Production entry points:
  - CLI: `python -m ai_doc check [path]`
  - Module API: `ai_doc.app.run_static_check(...)`
- Implementation paths:
  - `projects/ai-doc/src/ai_doc/analyzers/semantic_duplication.py`
  - `projects/ai-doc/src/ai_doc/analyzers/semantic_contradiction.py`
  - `projects/ai-doc/src/ai_doc/config/models.py`
- Required configuration:
  - `local_ml.enabled: true`
  - at least one of `local_ml.semantic_duplication` or
    `local_ml.semantic_contradiction` enabled
- Optional configuration dimensions:
  - `local_ml.similarity_model`
  - `local_ml.nli_model`
  - `local_ml.similarity_threshold`
  - `local_ml.nli_confidence_threshold`
- Required dependencies/models/providers:
  - sentence-transformers style local similarity model for semantic duplication
  - local NLI model for strong duplicate evidence and semantic contradiction
  - no external hosted LLM provider is used by A1
- Inputs:
  - same discovered markdown snapshot used by A0
  - configured local model names and thresholds
- Outputs/artifacts:
  - `CheckReport.findings`
  - A1 finding codes such as `FINOPS_SEMANTIC_DUPLICATE`,
    `FINOPS_STRONG_SEMANTIC_DUPLICATE`, `RISK_SEMANTIC_CONTRADICTION`
  - `RISK_LOCAL_ML_UNAVAILABLE` info findings when configured models cannot load
- Existing observability/provenance:
  - current `check_observation` records all static findings as tier `a0`.
    It does not distinguish A1 findings as a separate observed tier.
- Current benchmark corpus suitability:
  - current cases contain semantic-risk categories, but do not define expected
    paraphrase pairs, contradiction pairs, hard negatives, or threshold-sensitive
    labels.
- Suitable existing cases:
  - `normative-ambiguity-migration-low`
  - `manual-criterion-ui-copy-medium`
  - `conditional-null-cache-medium`
  - `quality-cohort-shared-low`
  - `quality-cohort-shared-medium`
- Additional fixtures required:
  - semantic duplicate positives with human-authored paraphrases
  - semantic duplicate hard negatives with lexical overlap but different meaning
  - semantic contradiction positives and negatives
  - entailment-asymmetry fixtures
  - model-unavailable fixtures if availability behavior is benchmarked
- Missing benchmark-only infrastructure:
  - A1 runner that invokes real `ai-doc check` with local ML enabled
  - evidence schema that preserves model ids, thresholds, and A1 applicability
  - fixture labels independent from A1 output
- Spec functionality not yet exposed in production:
  - no separate A1 CLI command or tier-labeled observability record exists.
    A1 is implemented as optional static analyzers within `check`.

### B: Predictive LLM Judgment

Production status: implemented through deep evaluation and optimizer semantic
judging, but not as a standalone benchmark judge.

- Production entry points:
  - CLI: `python -m ai_doc check [path] --deep`
  - CLI: `python -m ai_doc optimize [path] --deep`
  - CLI: `python -m ai_doc optimize [path] --pairwise-semantic`
  - CLI: `python -m ai_doc optimize [path] --require-pairwise-semantic`
  - CLI: `python -m ai_doc optimize [path] --gated-pairwise`
- Implementation paths:
  - `projects/ai-doc/src/ai_doc/cli/check.py`
  - `projects/ai-doc/src/ai_doc/cli/optimize.py`
  - `projects/ai-doc/src/ai_doc/evaluators/context.py`
  - `projects/ai-doc/src/ai_doc/evaluators/deepeval.py`
  - `projects/ai-doc/src/ai_doc/optimizer/semantic.py`
  - `projects/ai-doc/src/ai_doc/providers/semantic.py`
- Required configuration:
  - evaluation scenarios loaded from the project evaluation suite
  - for DeepEval: explicit evaluator model where required by the evaluator
  - for command provider: configured provider component or
    `AI_DOC_SEMANTIC_COMMAND`
- Optional configuration dimensions:
  - evaluation engine: `promptfoo` or `deepeval`
  - evaluator/model under `evaluation.deep`
  - optimizer `deepeval_model`
  - provider-backed semantic operations
  - pairwise semantic judging
  - required pairwise postcondition
  - gated pairwise behavior
  - semantic-provider budget limits
- Required dependencies/models/providers:
  - Promptfoo or DeepEval optional dependency when those engines are selected
  - external evaluator/model credentials as required by the selected engine
  - optional command semantic provider implementing JSON stdin/stdout
- Inputs:
  - baseline documentation snapshot
  - optional candidate documentation snapshot
  - evaluation scenarios
  - pairwise baseline/candidate text and rubric dimensions
- Outputs/artifacts:
  - `EvaluationResult` from deep checks
  - optimizer `run.json`, `frontier.json`, `lineage.json`,
    `search-memory.json`, `report.json`, and candidate artifacts
  - pairwise comparison counts/outcomes in optimizer reports
  - exit code `3` when required pairwise did not run
  - exit code `4` when optimize has no recommended candidate
- Existing observability/provenance:
  - `check_observation` records B only when `report.evaluation` exists.
  - `optimize_observation` records B when candidate evaluations exist and records
    provider usage/cost and pairwise counts.
- Current benchmark corpus suitability:
  - current treatments can feed B pairwise comparisons, especially when paired
    with C2 smoke/execution outcomes.
  - current corpus lacks B-specific expected labels and blinded prediction
    persistence.
- Suitable existing cases:
  - `quality-cohort-shared-low`
  - `quality-cohort-shared-medium`
  - `quality-cohort-shared-high`
  - `duplication-generated-contract-low`
  - `contradiction-docs-precedence-medium`
  - `conditional-null-cache-medium`
  - `forbidden-dependency-medium`
- Additional fixtures required:
  - stable baseline/candidate instruction pairs with human-authored expected
    predictive direction or expected uncertainty
  - cases where B should disagree with A0/A1
  - cases where B predicts no material difference
- Missing benchmark-only infrastructure:
  - B runner that invokes real `ai-doc` B interfaces and stores pre-C2
    predictions without looking at execution outcomes
  - pairwise evidence schema for rubric dimension outcomes and model/provider ids
  - comparison linkage between B prediction ids and later C2 observations
- Spec functionality not yet exposed in production:
  - no standalone pure B pairwise CLI exists outside `optimize`.
    Benchmarking can use `check --deep` and optimizer pairwise paths, or document
    a minimal product interface request later.

### C1: Target-Agent Planning / Behavioral Probe

Production status: implemented as a provider-neutral JSON command contract, not
as native natural-language CLI execution.

- Production entry points:
  - CLI: `python -m ai_doc probe [path]`
  - Optional candidate comparison: `python -m ai_doc probe [path] --candidate <path>`
- Implementation paths:
  - `projects/ai-doc/src/ai_doc/cli/probe.py`
  - `projects/ai-doc/src/ai_doc/probes/command.py`
  - `projects/ai-doc/src/ai_doc/probes/runner.py`
  - `projects/ai-doc/src/ai_doc/probes/verification.py`
- Required configuration:
  - `AI_DOC_TARGET_COMMAND` must name a command that accepts the target probe JSON
    contract on stdin and returns valid JSON on stdout.
  - evaluation scenarios must exist for the project.
- Optional configuration dimensions:
  - candidate documentation tree for baseline-vs-candidate planning comparison
  - local NLI verification via `local_ml.enabled` and
    `local_ml.nli_confidence_threshold`
  - include/exclude/profile rules that affect selected instruction context
- Required dependencies/models/providers:
  - target-command adapter
  - optional local NLI model for semantic verification
- Inputs:
  - deterministic task-selected instruction context
  - evaluation scenario
  - JSON request with `mode: "plan"`, scenario, and instruction texts
- Outputs/artifacts:
  - `PlanningProbeReport`
  - optional `PlanningProbeComparison`
  - target response fields: target, model/model_version, applicable rules,
    planned actions, avoided forbidden actions, uncertainties, usage, raw summary
- Existing observability/provenance:
  - `probe_observation` records command `probe`, tier `c1`, scenario count, tool
    version, config/project fingerprints, duration, and exit code.
- Current benchmark corpus suitability:
  - current C2 cases can be adapted into C1 scenarios, but the current benchmark
    corpus does not expose them as product `EvaluationScenario` suites.
  - native Codex/Gemini/Claude benchmark smoke configs do not satisfy the product
    JSON `AI_DOC_TARGET_COMMAND` contract by themselves.
- Suitable existing cases:
  - `quality-cohort-shared-low`
  - `quality-cohort-shared-medium`
  - `quality-cohort-shared-high`
  - `forbidden-dependency-medium`
  - `hidden-security-rule-low`
  - `conditional-null-cache-medium`
  - `negative-routing-readme-high`
- Additional fixtures required:
  - explicit expected planned actions and forbidden planned actions
  - task-selected context fixtures that match product evaluation-suite loading
  - hard cases where planning claims should diverge from execution behavior
- Missing benchmark-only infrastructure:
  - adapter from benchmark cases to product evaluation scenarios
  - optional provider wrappers that translate native CLI behavior into the
    `AI_DOC_TARGET_COMMAND` JSON plan contract
  - C1 evidence schema linked to later C2 observations
- Spec functionality not yet exposed in production:
  - product C1 is not the Benchmark Execution v0.1 `task.md` harness and does
    not directly invoke native CLIs with `Implement task.md`.

### C2: Target-Agent Execution

Production status: implemented in two different forms that must not be confused.

- Production entry points:
  - Product probe CLI: `python -m ai_doc execute [path]`
  - Benchmark execution harness: `python -m ai_doc_benchmarks execute ...`
- Implementation paths:
  - Product: `projects/ai-doc/src/ai_doc/cli/execute.py`
  - Product command adapter:
    `projects/ai-doc/src/ai_doc/probes/execution.py`
  - Product execution runner:
    `projects/ai-doc/src/ai_doc/probes/execution_runner.py`
  - Benchmark harness:
    `benchmarks/ai-doc-benchmark/src/ai_doc_benchmarks/execution.py`
- Required configuration:
  - product `execute`: `AI_DOC_TARGET_COMMAND` implementing JSON stdin/stdout,
    plus evaluation scenarios
  - benchmark harness: target config with `id`, `command`, optional `args`,
    `timeout_seconds`, `model`, `tool_version`, and `env`
- Optional configuration dimensions:
  - product local NLI verification
  - benchmark target CLI/model/sandbox/approval settings
  - benchmark treatment class and repetition number
  - benchmark `--keep-workspace` for inspection
- Required dependencies/models/providers:
  - product: target-command adapter
  - benchmark: qualified real target CLI such as Codex, Gemini, or Claude with
    provider-specific non-interactive permissions already documented separately
- Inputs:
  - product: isolated workspace copy, selected instruction context, scenario JSON
  - benchmark: disposable Git workspace, neutral `task.md`, prompt
    `Implement task.md`, selected target command/config
- Outputs/artifacts:
  - product: `ExecutionProbeReport`, target self-report, workspace delta
  - benchmark: `observation.json`, `execution.json`, `grading.json`,
    `treatment.json`, `task.md`, `stdout.txt`, `stderr.txt`, `workspace.diff`,
    `untracked-files.json`
- Existing observability/provenance:
  - product `execute` records command `execute`, tier `c2`, scenario count, and
    execution status through `probe_observation`.
  - benchmark observations record target id/model/tool version, monorepo commit,
    termination status, validity, grader status, treatment provenance, and
    evidence file locations.
- Current benchmark corpus suitability:
  - current corpus is primarily suitable for C2. Each case has a workspace,
    task, treatment artifacts, and deterministic behavioral criteria.
- Suitable existing cases:
  - all 19 cases are C2 candidates subject to provider qualification.
  - the `quality-cohort-shared-*` trio is especially useful for controlled
    cross-tier validation because it holds task/workspace constant while varying
    instruction quality.
- Additional fixtures required:
  - none required to continue C2 smoke/execution, but repeated observations and
    analysis metadata are needed for real comparative experiments.
- Missing benchmark-only infrastructure:
  - repeated-run scheduling is intentionally not in Execution v0.1
  - analysis layer for C2 distributions and cross-tier prediction checks
  - C1-to-C2 linkage records
- Spec functionality not yet exposed in production:
  - product `ai-doc execute` uses a JSON target command and target self-report
    plus workspace delta. The benchmark's highest empirical reference in v0.1 is
    the existing external C2 execution harness with deterministic graders.

## 2. Configuration Inventory

Evidence-tier configuration:

- A0:
  - include/exclude globs
  - document profiles
  - budgets
  - token counter component
  - extension trust/runtime if extensions are deliberately in scope
- A1:
  - `local_ml.enabled`
  - `local_ml.semantic_duplication`
  - `local_ml.semantic_contradiction`
  - `local_ml.similarity_model`
  - `local_ml.nli_model`
  - `local_ml.similarity_threshold`
  - `local_ml.nli_confidence_threshold`
- B:
  - `evaluation.deep.engine`
  - `evaluation.deep.evaluator`
  - `evaluation.deep.model`
  - `optimization.deepeval_model`
  - configured semantic provider or `AI_DOC_SEMANTIC_COMMAND`
  - pairwise semantic requested/required/gated behavior
  - provider request/token/cost budgets
- C1:
  - `AI_DOC_TARGET_COMMAND`
  - product evaluation suite
  - optional local NLI verification settings
  - target/model/version returned by the target command
- C2:
  - for product `execute`: same `AI_DOC_TARGET_COMMAND` JSON contract plus
    evaluation suite and optional local NLI verification
  - for Benchmark Execution v0.1: target `id`, `command`, `args`,
    `timeout_seconds`, `model`, `tool_version`, `env`, treatment, case id,
    repetition, and monorepo revision provenance

Optimizer/search configuration:

- `optimization.strategy`: `conservative`, `balanced`, `search`
- `population.initial_candidates`
- `search.generations`
- `search.initial_candidates`
- `search.children_per_generation`
- `search.max_candidates`
- `search.max_llm_requests`
- `search.max_input_tokens`
- `search.max_output_tokens`
- `search.max_cost_usd`
- `search.patience`
- `optimization.exploration_rate`
- `optimization.restart_after_stagnation`
- `optimization.concurrency`
- `gepa.enabled`
- `gepa.iterations`
- `gepa.pareto_size`
- `gepa.minibatch_size`
- `gepa.patience`
- `gepa.random_seed`
- `gepa.reflection_model`
- `gepa.mutation_model`
- Pareto tolerances and recommendation policy thresholds

Target execution configuration:

- Benchmark runner targets are generic `command + args + cwd + env + timeout`.
- Provider-specific permission/authentication behavior is documented in:
  - `docs/codex-cli-spawn-findings.md`
  - `docs/gemini-cli-spawn-findings.md`
  - `docs/claude-cli-spawn-findings.md`
- Do not normalize provider sandbox/approval mechanisms into a benchmark
  abstraction for Pyramid Validation v0.1.

## 3. Existing Corpus Coverage Matrix

| Case or case family | A0 intrinsic | A1 intrinsic | B -> C2 | C1 -> C2 | C2 behavioral | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| `duplication-generated-contract-low` | partial | no | yes | possible | yes | Good duplication and behavior-relevance seed, but lacks A0 labels. |
| `contradiction-docs-precedence-medium` | partial | possible | yes | yes | yes | Useful for contradiction/routing behavior; needs intrinsic labels. |
| `hidden-security-rule-low` | no | no | possible | yes | yes | Primarily behavioral hidden-rule/forbidden-action case. |
| `excessive-context-focused-tests-medium` | partial | no | possible | possible | yes | Useful for cost/context relevance, not intrinsic static accuracy yet. |
| `routing-frontend-vs-backend-medium` | partial | no | possible | possible | yes | Good context-selection behavior case. |
| `normative-ambiguity-migration-low` | no | partial | yes | possible | yes | Useful A1/B behavioral-relevance seed. |
| `important-example-error-format-medium` | no | possible | yes | possible | yes | Behavioral and B-prediction candidate. |
| `over-compression-null-vs-empty-high` | no | possible | yes | possible | yes | Good high-quality/control contrast candidate. |
| `forbidden-dependency-medium` | partial | no | yes | yes | yes | Strong C-tier forbidden-action case. |
| `conditional-public-docs-medium` | no | possible | possible | possible | yes | Conditional instruction behavior case. |
| `multi-document-skill-discovery-low` | partial | no | possible | yes | yes | Good routing/context-selection behavior case. |
| `already-good-small-api-high` | partial | possible | possible | possible | yes | Useful negative/control case for no-change expectations. |
| `quality-cohort-shared-low/medium/high` | partial | possible | yes | yes | yes | Best existing controlled family for B/C1/C2 relationship tests. |
| `cross-document-critical-release-medium` | partial | possible | possible | yes | yes | Good multi-document scenario seed. |
| `negative-routing-readme-high` | partial | no | possible | yes | yes | Useful hard negative for routing behavior. |
| `manual-criterion-ui-copy-medium` | no | partial | yes | possible | yes | Good ambiguity/important-example behavioral seed. |
| `conditional-null-cache-medium` | no | partial | yes | yes | yes | Good conditional/criterion preservation case. |

Overall corpus findings:

- All 19 current cases are usable for C2, subject to target qualification.
- The current corpus is not yet an intrinsic A0/A1 benchmark because it lacks
  human-authored analyzer property labels.
- Existing treatments make the corpus useful for B -> C2 validation once B
  predictions are captured before C2 outcomes are observed.
- C1 -> C2 validation needs a bridge from benchmark cases to product evaluation
  scenarios and target-command adapters.
- A0/A1 behavioral relevance can be tested later by linking static findings to
  C2 outcomes, but this requires explicit applicability metadata.

## 4. Missing Fixture Inventory

A0 fixtures:

- exact duplicate paragraph positive and negative fixtures
- exact duplicate list item positive and negative fixtures
- boundary fixtures for duplicate length thresholds
- local unnamed-scope duplicate exception fixture
- literal contradiction positive and negative fixtures
- structure/routing fixtures with expected finding codes
- token/context-budget threshold fixtures
- already-good static negative fixtures

A1 fixtures:

- semantic duplicate positives with paraphrased equivalent rules
- semantic duplicate hard negatives with high lexical overlap
- semantic contradiction positives
- semantic contradiction hard negatives
- entailment-asymmetry cases
- threshold-boundary fixtures for similarity and NLI confidence
- model-unavailable behavior fixtures if local dependency availability is in
  scope for benchmark reporting

B fixtures:

- baseline/candidate pairs with expected predictive preference or uncertainty
- pairs where A0/A1 signal is present but B should predict no behavioral effect
- pairs where B should detect behavior-relevant risks missed by A0/A1
- stable evaluator/provider/model configuration examples

C1 fixtures:

- evaluation scenarios derived from existing benchmark cases
- expected planned actions
- expected forbidden actions avoided
- cases expected to produce uncertainty
- native target wrappers for Codex/Gemini/Claude only if the benchmark chooses
  to exercise product `ai-doc probe`

C2 fixtures:

- no new fixtures required for narrow continuation of Execution v0.1
- later comparative experiments need pinned batch metadata and repetition plans,
  but not changes to case semantics.

## 5. Infrastructure Gap Analysis

Implemented and usable now:

- real `ai-doc check` production entry point for A0 and optional A1
- real `ai-doc optimize` entry point for optimizer and B-adjacent semantic
  evaluation/pairwise judging
- real `ai-doc probe` and `ai-doc execute` JSON target-command probes
- frozen Benchmark Execution v0.1 for external C2 execution with deterministic
  graders
- provider qualification notes for Codex, Gemini, and Claude

Still missing for Pyramid Validation v0.1:

- A0 benchmark runner invoking production `ai-doc check`
- A0 expected-property fixture schema
- A1 benchmark runner invoking production `ai-doc check` with local ML enabled
- A1 evidence schema preserving model ids and thresholds
- B runner that captures production B predictions before C2
- B evidence schema for model/provider/rubric/pairwise outcome provenance
- bridge from benchmark cases to product evaluation scenarios
- C1 runner/adapters for real target planning probes
- linkage schema from A0/A1/B/C1 observations to C2 observations
- minimal analysis inputs for correlation/prediction checks

Important boundary:

- Do not reimplement analyzers, semantic evaluators, optimizer search, or target
  probes inside the benchmark.
- If a production interface is insufficient, add the smallest product-facing
  interface later and keep the benchmark pinned to that interface.

## 6. Proposed Implementation Sequence

1. Add benchmark fixture metadata for A0/A1 expected properties without changing
   the frozen C2 corpus semantics.
2. Implement an A0 runner that invokes real `ai-doc check --format json` and maps
   finding codes to expected properties.
3. Implement an A1 runner that invokes real `ai-doc check --format json` with
   pinned local ML config, model ids, thresholds, and applicability handling.
4. Add B prediction capture using the smallest existing production path:
   `check --deep` for absolute scenario evaluation and `optimize
   --pairwise-semantic` only where pairwise candidate comparison is required.
5. Convert selected benchmark cases into product evaluation scenarios for C1,
   then qualify target-command adapters if product `ai-doc probe` is the chosen
   C1 interface.
6. Link B and C1 prediction records to later C2 observations without adding a
   full analysis subsystem.
7. Run a small repeated C2 pilot on the `quality-cohort-shared-*` family and a
   few category-diverse cases to validate the evidence join before expanding.

## 7. Open Questions

- Should C1 validation use product `ai-doc probe` with JSON target-command
  adapters, or should the benchmark define a separate natural-language planning
  harness aligned with Benchmark Execution v0.1?
- Which B interface is normative for v0.1 pairwise prediction: DeepEval
  pairwise, command semantic provider pairwise, or both as separate configured
  benchmark targets?
- Which local A1 model artifacts can be pinned and made reproducibly available
  on benchmark machines?
- Should product observability label A1 findings separately from A0, or should
  the benchmark infer tier from finding codes and configuration?
- How should benchmark case revisions and product evaluation scenario revisions
  be linked once C1 scenarios are derived from existing C2 cases?
