from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

from ai_doc_benchmarks.execution import (
    ExecutionTarget,
    _resolve_executable,
    _select_ai_doc_result,
    prepare_treatment,
    run_execution,
)
from ai_doc_benchmarks.schema import validate_observation_record

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "corpus" / "benchmark-corpus-v0.1.json"


def load_corpus() -> dict:
    return json.loads(CORPUS.read_text(encoding="utf-8"))


class ExecutionTests(unittest.TestCase):
    def test_control_treatments_have_distinct_blinded_task_artifacts(self) -> None:
        case = load_corpus()["cases"][0]
        original = prepare_treatment(case, "original")
        compressed = prepare_treatment(case, "simple-compression-control")
        degraded = prepare_treatment(case, "degraded-control")

        self.assertNotEqual(original.artifact, compressed.artifact)
        self.assertNotEqual(compressed.artifact, degraded.artifact)
        for artifact in (original.artifact, compressed.artifact, degraded.artifact):
            self.assertIn("implement", artifact.lower())
            self.assertNotIn("simple-compression-control", artifact)
            self.assertNotIn("degraded-control", artifact)
            self.assertNotIn("Treatment:", artifact)
            self.assertNotIn("Configuration:", artifact)

    def test_single_execution_produces_observation_and_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            fake_cli = temp_path / "fake_cli.py"
            fake_cli.write_text(
                "\n".join(
                    [
                        "from pathlib import Path",
                        "import sys",
                        "",
                        "assert sys.argv[-1] == 'Implement task.md'",
                        "assert Path('task.md').exists()",
                        "Path('src/api_contract.py').write_text(",
                        "    \"def endpoint_name():\\n    return 'accounts'\\n\",",
                        "    encoding='utf-8',",
                        ")",
                        "Path('notes.txt').write_text('agent note\\n', encoding='utf-8')",
                    ]
                ),
                encoding="utf-8",
            )

            result = run_execution(
                corpus=load_corpus(),
                case_id="duplication-generated-contract-low",
                treatment="original",
                target=ExecutionTarget(
                    id="fake-cli",
                    command=sys.executable,
                    args=(str(fake_cli),),
                    timeout_seconds=10,
                ),
                output_dir=temp_path / "evidence",
                repetition=1,
                observation_id="obs-test",
            )

            self.assertIsNone(result.preparation_failure)
            self.assertIsNotNone(result.observation)
            observation = dict(result.observation or {})
            validate_observation_record(observation)
            self.assertEqual(observation["validity"]["status"], "valid")
            self.assertIs(observation["behavior"]["task_success"], True)
            self.assertEqual(observation["treatment"]["class"], "original")
            self.assertTrue((result.evidence_dir / "task.md").exists())
            self.assertTrue((result.evidence_dir / "workspace.diff").exists())
            self.assertTrue((result.evidence_dir / "grading.json").exists())
            self.assertEqual(list((temp_path / "evidence" / "workspaces").iterdir()), [])

            untracked = json.loads(
                (result.evidence_dir / "untracked-files.json").read_text(encoding="utf-8")
            )
            self.assertEqual(untracked["files"][0]["path"], "notes.txt")
            self.assertEqual(untracked["files"][0]["text"].replace("\r\n", "\n"), "agent note\n")

            task_text = (result.evidence_dir / "task.md").read_text(encoding="utf-8")
            self.assertIn("Make the endpoint contract return accounts", task_text)
            self.assertIn("### AGENTS.md", task_text)
            self.assertNotIn("Treatment:", task_text)

    def test_non_applicable_treatment_is_preparation_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            result = run_execution(
                corpus=load_corpus(),
                case_id="already-good-small-api-high",
                treatment="simple-compression-control",
                target=ExecutionTarget(id="fake-cli", command=sys.executable),
                output_dir=Path(temp),
                observation_id="obs-prep-failure",
            )

            self.assertIsNone(result.observation)
            self.assertIsNotNone(result.preparation_failure)
            failure = json.loads(
                (result.evidence_dir / "preparation-failure.json").read_text(encoding="utf-8")
            )
            self.assertEqual(failure["failure_class"], "treatment-preparation")
            self.assertIn("not applicable", failure["reason"])

    def test_ai_doc_treatment_uses_real_sut_and_records_provenance(self) -> None:
        prepared = prepare_treatment(load_corpus()["cases"][0], "ai-doc")

        self.assertEqual(prepared.treatment_class, "ai-doc")
        self.assertEqual(prepared.provenance["artifact_source"], "ai-doc-cli")
        self.assertEqual(prepared.provenance["invocation_path"], "python -m ai_doc optimize")
        self.assertRegex(prepared.provenance["ai_doc_commit"], r"^[0-9a-f]{40}$")
        self.assertIn("candidate_id", prepared.provenance)
        self.assertIn("selection_rule", prepared.provenance)
        self.assertIn("Make the endpoint contract return accounts", prepared.artifact)

    def test_ai_doc_result_selection_uses_recommended_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            run_dir = Path(temp)
            for candidate_id in ("C001", "C002"):
                candidate = run_dir / "candidates" / candidate_id / "candidate"
                candidate.mkdir(parents=True)
                (candidate / "AGENTS.md").write_text(candidate_id, encoding="utf-8")
            (run_dir / "run.json").write_text(
                json.dumps(
                    {
                        "run_id": "run-test",
                        "baseline_candidate_id": "baseline",
                        "recommended_candidate_id": "C002",
                        "recommendation_reason": "selected by ai-doc",
                        "candidates": [{"id": "C001"}, {"id": "C002"}],
                    }
                ),
                encoding="utf-8",
            )

            selected, provenance = _select_ai_doc_result(run_dir)

            self.assertEqual(selected, run_dir / "candidates" / "C002" / "candidate")
            self.assertEqual(provenance["candidate_id"], "C002")
            self.assertEqual(provenance["selection_source"], "recommended_candidate_id")

    def test_timeout_after_meaningful_execution_still_allows_grading(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            fake_cli = _write_fake_cli(
                temp_path,
                [
                    "from pathlib import Path",
                    "import time",
                    "Path('src/api_contract.py').write_text("
                    "\"def endpoint_name():\\n    return 'accounts'\\n\", encoding='utf-8')",
                    "time.sleep(5)",
                ],
            )
            result = run_execution(
                corpus=load_corpus(),
                case_id="duplication-generated-contract-low",
                treatment="original",
                target=ExecutionTarget(
                    id="fake-cli",
                    command=sys.executable,
                    args=(str(fake_cli),),
                    timeout_seconds=0.5,
                ),
                output_dir=temp_path / "evidence",
                observation_id="obs-timeout",
            )

            observation = dict(result.observation or {})
            self.assertEqual(observation["validity"]["status"], "valid")
            self.assertEqual(observation["execution"]["termination_status"], "timeout")
            self.assertIs(observation["behavior"]["task_success"], True)

    def test_missing_executable_is_invalid_execution_not_behavioral_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            result = run_execution(
                corpus=load_corpus(),
                case_id="duplication-generated-contract-low",
                treatment="original",
                target=ExecutionTarget(id="missing-cli", command="definitely-not-a-real-cli"),
                output_dir=Path(temp),
                observation_id="obs-missing",
            )

            observation = dict(result.observation or {})
            self.assertEqual(observation["validity"]["status"], "invalid")
            self.assertIn("target executable could not start", observation["validity"]["reason"])
            self.assertIn("definitely-not-a-real-cli", observation["validity"]["reason"])

    def test_target_command_is_resolved_before_subprocess_start(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            command = temp_path / "sample-target.cmd"
            command.write_text("@echo off\r\necho ok\r\n", encoding="utf-8")
            old_path = os.environ["PATH"]
            try:
                os.environ["PATH"] = f"{temp_path}{os.pathsep}{old_path}"
                self.assertEqual(Path(_resolve_executable("sample-target")).resolve(), command)
            finally:
                os.environ["PATH"] = old_path

    def test_nonzero_exit_after_workspace_mutation_still_allows_grading(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            fake_cli = _write_fake_cli(
                temp_path,
                [
                    "from pathlib import Path",
                    "import sys",
                    "Path('src/api_contract.py').write_text("
                    "\"def endpoint_name():\\n    return 'accounts'\\n\", encoding='utf-8')",
                    "sys.exit(5)",
                ],
            )
            result = run_execution(
                corpus=load_corpus(),
                case_id="duplication-generated-contract-low",
                treatment="original",
                target=ExecutionTarget(
                    id="fake-cli", command=sys.executable, args=(str(fake_cli),)
                ),
                output_dir=temp_path / "evidence",
                observation_id="obs-nonzero",
            )

            observation = dict(result.observation or {})
            self.assertEqual(observation["validity"]["status"], "valid")
            self.assertEqual(observation["execution"]["exit_code"], 5)
            self.assertIs(observation["behavior"]["task_success"], True)

    def test_malformed_subprocess_output_is_captured_with_replacement(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            fake_cli = _write_fake_cli(
                temp_path,
                [
                    "from pathlib import Path",
                    "import sys",
                    "sys.stdout.buffer.write(b'valid stdout before invalid: \\xff\\n')",
                    "sys.stderr.buffer.write(b'valid stderr before invalid: \\xfe\\n')",
                    "Path('src/api_contract.py').write_text("
                    "\"def endpoint_name():\\n    return 'accounts'\\n\", encoding='utf-8')",
                ],
            )

            result = run_execution(
                corpus=load_corpus(),
                case_id="duplication-generated-contract-low",
                treatment="original",
                target=ExecutionTarget(
                    id="fake-cli", command=sys.executable, args=(str(fake_cli),)
                ),
                output_dir=temp_path / "evidence",
                observation_id="obs-malformed-output",
            )

            observation = dict(result.observation or {})
            self.assertEqual(observation["validity"]["status"], "valid")
            self.assertIs(observation["behavior"]["task_success"], True)
            self.assertIn(
                "valid stdout before invalid: �",
                (result.evidence_dir / "stdout.txt").read_text(encoding="utf-8"),
            )
            self.assertIn(
                "valid stderr before invalid: �",
                (result.evidence_dir / "stderr.txt").read_text(encoding="utf-8"),
            )

    def test_grader_failure_invalidates_observation_without_false_behavior(self) -> None:
        corpus = load_corpus()
        corpus["cases"][0]["grader"]["python"] = "raise RuntimeError('grader exploded')"
        with tempfile.TemporaryDirectory() as temp:
            result = run_execution(
                corpus=corpus,
                case_id="duplication-generated-contract-low",
                treatment="original",
                target=ExecutionTarget(id="noop", command=sys.executable, args=("-c", "pass")),
                output_dir=Path(temp),
                observation_id="obs-grader-failure",
            )

            observation = dict(result.observation or {})
            self.assertEqual(observation["validity"]["status"], "invalid")
            self.assertEqual(observation["behavior"]["task_success"], "unknown")
            self.assertTrue(
                all(item["outcome"] == "unknown" for item in observation["behavior"]["criteria"])
            )

    def test_keep_workspace_retains_workspace_when_requested(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            result = run_execution(
                corpus=load_corpus(),
                case_id="duplication-generated-contract-low",
                treatment="original",
                target=ExecutionTarget(id="noop", command=sys.executable, args=("-c", "pass")),
                output_dir=temp_path / "evidence",
                observation_id="obs-retained",
                keep_workspace=True,
            )

            workspace = Path((result.evidence_dir / "workspace.txt").read_text(encoding="utf-8"))
            self.assertTrue(workspace.exists())
            self.assertTrue((workspace / "task.md").exists())


def _write_fake_cli(root: Path, lines: list[str]) -> Path:
    script = root / f"fake_cli_{len(list(root.glob('fake_cli_*.py')))}.py"
    script.write_text("\n".join(lines), encoding="utf-8")
    return script


if __name__ == "__main__":
    unittest.main()
