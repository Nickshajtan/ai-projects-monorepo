from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

from ai_doc_benchmarks.execution import ExecutionTarget, run_execution
from ai_doc_benchmarks.schema import validate_observation_record

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "corpus" / "benchmark-corpus-v0.1.json"


def load_corpus() -> dict:
    return json.loads(CORPUS.read_text(encoding="utf-8"))


class ExecutionTests(unittest.TestCase):
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
            self.assertEqual(list((temp_path / "evidence" / "worktrees").iterdir()), [])

            untracked = json.loads(
                (result.evidence_dir / "untracked-files.json").read_text(encoding="utf-8")
            )
            self.assertEqual(untracked["files"][0]["path"], "notes.txt")
            self.assertEqual(untracked["files"][0]["text"].replace("\r\n", "\n"), "agent note\n")

            task_text = (result.evidence_dir / "task.md").read_text(encoding="utf-8")
            self.assertIn("Make the endpoint contract return accounts", task_text)
            self.assertIn("### AGENTS.md", task_text)

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


if __name__ == "__main__":
    unittest.main()
