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
