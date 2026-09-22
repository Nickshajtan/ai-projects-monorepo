from __future__ import annotations

import unittest

from ai_doc_benchmarks.schema import BenchmarkValidationError, validate_observation_record


def valid_observation() -> dict:
    return {
        "observation_id": "obs-001",
        "benchmark_version": "0.1",
        "case": {
            "id": "duplication-generated-contract-low",
            "revision": "2026-09-22.1",
            "categories": ["duplication", "forbidden-action"],
            "quality_cohort": "low",
            "source_corpus": "sic-duplication-generated-contract-low",
            "task": "task-update-endpoint-source",
        },
        "treatment": {
            "class": "original",
            "configuration": "source",
            "resulting_corpus": "sic-duplication-generated-contract-low",
        },
        "target": {
            "provider": "codex",
            "model": None,
            "configuration": {},
            "tool_version": None,
        },
        "repetition": {"index": 1},
        "validity": {"status": "valid", "reason": None},
        "behavior": {
            "task_success": True,
            "criteria": [
                {
                    "id": "focused-test-passes",
                    "type": "task_success",
                    "outcome": "satisfied",
                },
                {
                    "id": "generated-files-unchanged",
                    "type": "forbidden",
                    "outcome": "violated",
                },
            ],
        },
        "instructions": {
            "corpus": "sic-duplication-generated-contract-low",
            "bytes": 512,
            "tokens": {"status": "unavailable", "value": None},
        },
        "execution": {
            "input_tokens": "unavailable",
            "output_tokens": "unavailable",
            "duration_seconds": 18.34,
            "termination_status": "completed",
        },
        "evidence": {
            "task": "evidence/tasks/obs-001.txt",
            "instruction_corpus": "evidence/instructions/obs-001/",
            "workspace_diff": "evidence/diffs/obs-001.patch",
            "grading_evidence": "evidence/grading/obs-001.json",
        },
    }


class ObservationSchemaTests(unittest.TestCase):
    def test_valid_observation_record_shape(self) -> None:
        validate_observation_record(valid_observation())

    def test_observation_rejects_comparative_conclusions(self) -> None:
        observation = valid_observation()
        observation["behavior"]["regression"] = True

        with self.assertRaisesRegex(BenchmarkValidationError, "comparative field"):
            validate_observation_record(observation)

    def test_invalid_observation_requires_reason(self) -> None:
        observation = valid_observation()
        observation["validity"] = {"status": "invalid", "reason": None}

        with self.assertRaisesRegex(BenchmarkValidationError, "reason"):
            validate_observation_record(observation)

    def test_behavioral_failure_can_still_be_valid_observation(self) -> None:
        observation = valid_observation()
        observation["validity"] = {"status": "valid", "reason": None}
        observation["behavior"]["task_success"] = False
        observation["behavior"]["criteria"][0]["outcome"] = "violated"

        validate_observation_record(observation)

    def test_validity_is_independent_from_task_success(self) -> None:
        observation = valid_observation()
        observation["validity"] = {
            "status": "invalid",
            "reason": "execution target crashed before producing behavior",
        }
        observation["behavior"]["task_success"] = True

        validate_observation_record(observation)

    def test_unknown_outcome_is_explicit_not_satisfied(self) -> None:
        observation = valid_observation()
        observation["behavior"]["criteria"][1]["outcome"] = "unknown"

        validate_observation_record(observation)
        self.assertNotEqual(observation["behavior"]["criteria"][1]["outcome"], "satisfied")

    def test_conditional_criterion_requires_explicit_applicability(self) -> None:
        observation = valid_observation()
        observation["behavior"]["criteria"].append(
            {
                "id": "release-note-needed",
                "type": "conditional",
                "outcome": "not_applicable",
            }
        )

        with self.assertRaisesRegex(BenchmarkValidationError, "applicability"):
            validate_observation_record(observation)

        observation["behavior"]["criteria"][-1]["applicability"] = "not_applicable"
        validate_observation_record(observation)

    def test_required_evidence_fields_cannot_disappear(self) -> None:
        observation = valid_observation()
        del observation["evidence"]["grading_evidence"]

        with self.assertRaisesRegex(BenchmarkValidationError, "grading_evidence"):
            validate_observation_record(observation)
