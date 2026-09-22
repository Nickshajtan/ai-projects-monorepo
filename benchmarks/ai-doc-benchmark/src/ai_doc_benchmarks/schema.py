from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Any

BENCHMARK_VERSION = "0.1"

ALLOWED_CATEGORIES = {
    "duplication",
    "contradiction",
    "hidden-critical-rule",
    "excessive-context",
    "routing-scope",
    "normative-ambiguity",
    "important-example",
    "over-compression",
    "forbidden-action",
    "conditional-instruction",
    "multi-document",
    "already-good",
}

ALLOWED_CAPABILITIES = {
    "structural-analysis",
    "cross-document-analysis",
    "instruction-routing",
    "semantic-invariant-preservation",
    "skill-specialized-instruction-discoverability",
    "recommendation-candidate-selection",
}

QUALITY_COHORTS = {"low", "medium", "high"}
CRITERION_TYPES = {"task_success", "required", "forbidden", "conditional", "critical"}
CLASSIFICATION_METHODS = {"deterministic", "manual", "non_deterministic"}
TREATMENT_CLASSES = {"original", "ai-doc", "simple-compression-control", "degraded-control"}
OBSERVATION_VALIDITY = {"valid", "invalid"}
OUTCOMES = {"satisfied", "violated", "not_applicable", "unknown"}
APPLICABILITY = {"applicable", "not_applicable", "unknown"}

COMPARATIVE_FIELD_NAMES = {
    "better",
    "worse",
    "winner",
    "loser",
    "improvement",
    "regression",
    "quality_score",
    "optimization_benefit",
    "treatment_winner",
}


class BenchmarkValidationError(ValueError):
    """Raised when benchmark definition data violates required semantics."""


def validate_corpus(corpus: Mapping[str, Any]) -> None:
    _require_equal(corpus, "benchmark_version", BENCHMARK_VERSION)
    cases = _require_list(corpus, "cases")

    case_ids: set[str] = set()

    for case in cases:
        if not isinstance(case, Mapping):
            raise BenchmarkValidationError("each case must be an object")
        case_id = _require_str(case, "id")
        if case_id in case_ids:
            raise BenchmarkValidationError(f"duplicate case id: {case_id}")
        case_ids.add(case_id)
        validate_case(case)


def validate_starter_corpus_profile(corpus: Mapping[str, Any]) -> None:
    validate_corpus(corpus)

    category_coverage: set[str] = set()
    cohort_coverage: set[str] = set()
    for case in _require_list(corpus, "cases"):
        category_coverage.update(_require_string_set(case, "categories", ALLOWED_CATEGORIES))
        cohort_coverage.add(_require_str(case, "quality_cohort"))

    missing_categories = ALLOWED_CATEGORIES - category_coverage
    if missing_categories:
        missing = ", ".join(sorted(missing_categories))
        raise BenchmarkValidationError(f"corpus is missing category coverage: {missing}")

    missing_cohorts = QUALITY_COHORTS - cohort_coverage
    if missing_cohorts:
        missing = ", ".join(sorted(missing_cohorts))
        raise BenchmarkValidationError(f"corpus is missing quality cohorts: {missing}")


def validate_case(case: Mapping[str, Any]) -> None:
    _require_str(case, "id")
    _require_str(case, "revision")
    _require_str(case, "title")
    _require_member(case, "quality_cohort", QUALITY_COHORTS)
    _require_string_set(case, "categories", ALLOWED_CATEGORIES)
    _require_string_set(case, "ai_doc_capabilities", ALLOWED_CAPABILITIES)

    source = _require_mapping(case, "source_instruction_corpus")
    _require_str(source, "id")
    _require_file_map(source, "files")

    workspace = _require_mapping(case, "initial_workspace")
    _require_file_map(workspace, "files")

    task = _require_mapping(case, "task")
    _require_str(task, "id")
    _require_str(task, "prompt")

    ground_truth = _require_mapping(case, "ground_truth")
    has_task_success = False
    has_instruction_criterion = False
    criterion_ids: set[str] = set()
    for group_name in (
        "task_success_criteria",
        "required_instruction_criteria",
        "forbidden_criteria",
        "conditional_criteria",
        "critical_constraints",
    ):
        criteria = _require_list(ground_truth, group_name)
        for criterion in criteria:
            if not isinstance(criterion, Mapping):
                raise BenchmarkValidationError(f"{case['id']} {group_name} entries must be objects")
            criterion_id = _require_str(criterion, "id")
            if criterion_id in criterion_ids:
                raise BenchmarkValidationError(
                    f"{case['id']} duplicate criterion id: {criterion_id}"
                )
            criterion_ids.add(criterion_id)
            criterion_type = _require_member(criterion, "type", CRITERION_TYPES)
            _require_member(criterion, "classification_method", CLASSIFICATION_METHODS)
            _require_str(criterion, "observable_evidence")
            if criterion_type == "task_success":
                has_task_success = True
            else:
                has_instruction_criterion = True
            if criterion_type == "conditional":
                _require_str(criterion, "condition")

    if not has_task_success:
        raise BenchmarkValidationError(f"{case['id']} must define task-success criteria")
    if not has_instruction_criterion:
        raise BenchmarkValidationError(f"{case['id']} must define instruction criteria")

    treatments = _require_mapping(case, "control_treatments")
    _require_mapping(treatments, "original")
    compression = _require_mapping(treatments, "simple_compression_control")
    compression_applicable = _require_bool(compression, "applicable")
    if compression_applicable:
        _require_str(compression, "method")
    else:
        _require_str(compression, "reason")
        if "method" in compression:
            raise BenchmarkValidationError(
                "non-applicable simple_compression_control must not define method"
            )
    degraded = _require_mapping(treatments, "degraded_control")
    _require_str(degraded, "degradation")
    _require_str(degraded, "targeted_criterion")


def validate_observation_record(record: Mapping[str, Any]) -> None:
    _reject_comparative_fields(record)
    _require_str(record, "observation_id")
    _require_equal(record, "benchmark_version", BENCHMARK_VERSION)

    case = _require_mapping(record, "case")
    _require_str(case, "id")
    _require_str(case, "revision")
    _require_string_set(case, "categories", ALLOWED_CATEGORIES)
    _require_member(case, "quality_cohort", QUALITY_COHORTS)
    _require_str(case, "source_corpus")
    _require_str(case, "task")

    treatment = _require_mapping(record, "treatment")
    _require_member(treatment, "class", TREATMENT_CLASSES)
    _require_str(treatment, "configuration")
    _require_str(treatment, "resulting_corpus")

    target = _require_mapping(record, "target")
    _require_str(target, "provider")
    _require_nullable_str(target, "model")

    repetition = _require_mapping(record, "repetition")
    if not isinstance(repetition.get("index"), int):
        raise BenchmarkValidationError("repetition.index must be an integer")

    validity = _require_mapping(record, "validity")
    status = _require_member(validity, "status", OBSERVATION_VALIDITY)
    if status == "invalid":
        _require_str(validity, "reason")

    behavior = _require_mapping(record, "behavior")
    task_success = behavior.get("task_success")
    if task_success not in {True, False, "unknown"}:
        raise BenchmarkValidationError("behavior.task_success must be true, false, or unknown")
    criteria = _require_list(behavior, "criteria")
    for criterion in criteria:
        if not isinstance(criterion, Mapping):
            raise BenchmarkValidationError("behavior.criteria entries must be objects")
        _require_str(criterion, "id")
        criterion_type = _require_member(criterion, "type", CRITERION_TYPES)
        if criterion_type == "conditional":
            _require_member(criterion, "applicability", APPLICABILITY)
        _require_member(criterion, "outcome", OUTCOMES)

    instructions = _require_mapping(record, "instructions")
    _require_str(instructions, "corpus")
    _require_int_or_unavailable(instructions, "bytes")
    _require_measurement(instructions, "tokens")

    _require_mapping(record, "execution")
    evidence = _require_mapping(record, "evidence")
    for field in ("task", "instruction_corpus", "workspace_diff", "grading_evidence"):
        _require_nullable_str(evidence, field)


def _reject_comparative_fields(value: Any, path: str = "") -> None:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            current_path = f"{path}.{key}" if path else str(key)
            if str(key) in COMPARATIVE_FIELD_NAMES:
                raise BenchmarkValidationError(
                    f"observation records must not contain comparative field {current_path}"
                )
            _reject_comparative_fields(nested, current_path)
    elif isinstance(value, Sequence) and not isinstance(value, str):
        for index, nested in enumerate(value):
            _reject_comparative_fields(nested, f"{path}[{index}]")


def _require_mapping(parent: Mapping[str, Any], field: str) -> Mapping[str, Any]:
    value = parent.get(field)
    if not isinstance(value, Mapping):
        raise BenchmarkValidationError(f"{field} must be an object")
    return value


def _require_list(parent: Mapping[str, Any], field: str) -> list[Any]:
    value = parent.get(field)
    if not isinstance(value, list):
        raise BenchmarkValidationError(f"{field} must be a list")
    return value


def _require_str(parent: Mapping[str, Any], field: str) -> str:
    value = parent.get(field)
    if not isinstance(value, str) or not value:
        raise BenchmarkValidationError(f"{field} must be a non-empty string")
    return value


def _require_nullable_str(parent: Mapping[str, Any], field: str) -> str | None:
    if field not in parent:
        raise BenchmarkValidationError(f"{field} must be present")
    value = parent.get(field)
    if value is not None and not isinstance(value, str):
        raise BenchmarkValidationError(f"{field} must be a string or null")
    return value


def _require_bool(parent: Mapping[str, Any], field: str) -> bool:
    value = parent.get(field)
    if not isinstance(value, bool):
        raise BenchmarkValidationError(f"{field} must be true or false")
    return value


def _require_equal(parent: Mapping[str, Any], field: str, expected: str) -> None:
    value = _require_str(parent, field)
    if value != expected:
        raise BenchmarkValidationError(f"{field} must be {expected!r}")


def _require_member(parent: Mapping[str, Any], field: str, allowed: Iterable[str]) -> str:
    value = _require_str(parent, field)
    allowed_values = set(allowed)
    if value not in allowed_values:
        allowed_text = ", ".join(sorted(allowed_values))
        raise BenchmarkValidationError(f"{field} must be one of: {allowed_text}")
    return value


def _require_string_set(
    parent: Mapping[str, Any], field: str, allowed: set[str]
) -> set[str]:
    values = _require_list(parent, field)
    if not values:
        raise BenchmarkValidationError(f"{field} must not be empty")
    result: set[str] = set()
    for value in values:
        if not isinstance(value, str) or not value:
            raise BenchmarkValidationError(f"{field} entries must be non-empty strings")
        if value not in allowed:
            allowed_text = ", ".join(sorted(allowed))
            raise BenchmarkValidationError(
                f"{field} entry {value!r} must be one of: {allowed_text}"
            )
        result.add(value)
    return result


def _require_file_map(parent: Mapping[str, Any], field: str) -> Mapping[str, str]:
    files = _require_mapping(parent, field)
    if not files:
        raise BenchmarkValidationError(f"{field} must not be empty")
    for path, content in files.items():
        if not isinstance(path, str) or not path:
            raise BenchmarkValidationError(f"{field} paths must be non-empty strings")
        if path.startswith("/") or "\\" in path or ".." in path.split("/"):
            raise BenchmarkValidationError(f"{field} path must be relative and POSIX-style: {path}")
        if not isinstance(content, str):
            raise BenchmarkValidationError(f"{field}.{path} content must be a string")
    return files  # type: ignore[return-value]


def _require_int_or_unavailable(parent: Mapping[str, Any], field: str) -> None:
    value = parent.get(field)
    if value == "unavailable":
        return
    if not isinstance(value, int) or value < 0:
        raise BenchmarkValidationError(f"{field} must be a non-negative integer or unavailable")


def _require_measurement(parent: Mapping[str, Any], field: str) -> None:
    value = parent.get(field)
    if not isinstance(value, Mapping):
        raise BenchmarkValidationError(f"{field} must be a measurement object")
    status = _require_str(value, "status")
    if status == "available":
        if not isinstance(value.get("value"), int) or value["value"] < 0:
            raise BenchmarkValidationError(f"{field}.value must be a non-negative integer")
        _require_member(value, "method", {"exact", "estimated"})
    elif status == "unavailable":
        if value.get("value") is not None:
            raise BenchmarkValidationError(f"{field}.value must be null when unavailable")
    else:
        raise BenchmarkValidationError(f"{field}.status must be available or unavailable")
