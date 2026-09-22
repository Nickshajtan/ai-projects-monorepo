from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import textwrap
import time
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ai_doc_benchmarks.schema import BENCHMARK_VERSION, validate_case, validate_observation_record

PROMPT = "Implement task.md"

AGENT_INSTRUCTION_FILES = {
    "AGENTS.md",
    "CLAUDE.md",
    "GEMINI.md",
    "copilot-instructions.md",
    ".github/copilot-instructions.md",
}

TREATMENT_KEYS = {
    "original": "original",
    "simple-compression-control": "simple_compression_control",
    "degraded-control": "degraded_control",
}


class ExecutionError(RuntimeError):
    """Raised when an execution condition cannot be constructed."""


class TreatmentPreparationError(ExecutionError):
    """Raised when treatment preparation fails before target execution."""


@dataclass(frozen=True)
class ExecutionTarget:
    id: str
    command: str
    args: tuple[str, ...] = ()
    timeout_seconds: float = 600.0
    model: str | None = None
    env: Mapping[str, str] = field(default_factory=dict)
    tool_version: str | None = None

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> ExecutionTarget:
        target_id = payload.get("id")
        command = payload.get("command")
        if not isinstance(target_id, str) or not target_id:
            raise ExecutionError("target.id must be a non-empty string")
        if not isinstance(command, str) or not command:
            raise ExecutionError("target.command must be a non-empty string")

        args = payload.get("args", [])
        if not isinstance(args, list) or not all(isinstance(arg, str) for arg in args):
            raise ExecutionError("target.args must be a list of strings")

        timeout = payload.get("timeout_seconds", payload.get("timeout", 600))
        if not isinstance(timeout, int | float) or timeout <= 0:
            raise ExecutionError("target.timeout_seconds must be a positive number")

        env = payload.get("env", {})
        if not isinstance(env, Mapping) or not all(
            isinstance(key, str) and isinstance(value, str) for key, value in env.items()
        ):
            raise ExecutionError("target.env must be an object of string values")

        model = payload.get("model")
        tool_version = payload.get("tool_version")
        return cls(
            id=target_id,
            command=command,
            args=tuple(args),
            timeout_seconds=float(timeout),
            model=model if isinstance(model, str) and model else None,
            env=dict(env),
            tool_version=tool_version if isinstance(tool_version, str) and tool_version else None,
        )


@dataclass(frozen=True)
class PreparedTreatment:
    treatment_class: str
    configuration: str
    resulting_corpus: str
    artifact: str
    artifact_sha256: str


@dataclass(frozen=True)
class ExecutionResult:
    observation_id: str
    observation: Mapping[str, Any] | None
    evidence_dir: Path
    preparation_failure: Mapping[str, Any] | None = None


def run_execution(
    *,
    corpus: Mapping[str, Any],
    case_id: str,
    treatment: str,
    target: ExecutionTarget,
    output_dir: Path,
    repetition: int = 1,
    observation_id: str | None = None,
    keep_worktree: bool = False,
) -> ExecutionResult:
    benchmark_case = _find_case(corpus, case_id)
    validate_case(benchmark_case)

    observation_id = observation_id or f"obs-{uuid.uuid4().hex}"
    evidence_dir = output_dir / observation_id
    evidence_dir.mkdir(parents=True, exist_ok=False)

    try:
        prepared = prepare_treatment(benchmark_case, treatment)
    except TreatmentPreparationError as exc:
        failure = {
            "observation_id": observation_id,
            "benchmark_version": BENCHMARK_VERSION,
            "case_id": case_id,
            "case_revision": benchmark_case.get("revision"),
            "treatment": treatment,
            "failure_class": "treatment-preparation",
            "reason": str(exc),
        }
        _write_json(evidence_dir / "preparation-failure.json", failure)
        return ExecutionResult(observation_id, None, evidence_dir, failure)

    _write_text(evidence_dir / "task.md", prepared.artifact)
    _write_json(
        evidence_dir / "treatment.json",
        {
            "class": prepared.treatment_class,
            "configuration": prepared.configuration,
            "resulting_corpus": prepared.resulting_corpus,
            "artifact_sha256": prepared.artifact_sha256,
        },
    )

    worktree_parent = output_dir / "worktrees"
    worktree_parent.mkdir(parents=True, exist_ok=True)
    worktree = Path(tempfile.mkdtemp(prefix=f"{observation_id}-", dir=worktree_parent))
    target_started = False
    execution_started_at = time.monotonic()
    process_result: subprocess.CompletedProcess[str] | None = None
    timed_out = False
    validity_status = "valid"
    validity_reason: str | None = None

    try:
        _populate_worktree(worktree, benchmark_case)
        _write_text(worktree / "task.md", prepared.artifact)
        _git(["add", "."], worktree)
        _git(["commit", "-m", "case baseline"], worktree)

        command = [target.command, *target.args, PROMPT]
        env = os.environ.copy()
        env.update(target.env)

        try:
            target_started = True
            process_result = subprocess.run(
                command,
                cwd=worktree,
                env=env,
                text=True,
                capture_output=True,
                timeout=target.timeout_seconds,
                check=False,
            )
            termination_status = "completed"
        except subprocess.TimeoutExpired as exc:
            timed_out = True
            process_result = subprocess.CompletedProcess(
                command,
                returncode=-1,
                stdout=exc.stdout if isinstance(exc.stdout, str) else "",
                stderr=exc.stderr if isinstance(exc.stderr, str) else "",
            )
            termination_status = "timeout"
        except FileNotFoundError as exc:
            target_started = False
            validity_status = "invalid"
            validity_reason = f"target executable could not start: {exc.filename}"
            process_result = subprocess.CompletedProcess(
                command, returncode=127, stdout="", stderr=str(exc)
            )
            termination_status = "startup-failure"

        duration = time.monotonic() - execution_started_at
        grading = grade_case(worktree, benchmark_case)
        diff_text = _git(["diff", "--no-ext-diff", "HEAD"], worktree, capture=True)
        untracked = _collect_untracked(worktree)

        _write_text(evidence_dir / "stdout.txt", process_result.stdout or "")
        _write_text(evidence_dir / "stderr.txt", process_result.stderr or "")
        _write_text(evidence_dir / "workspace.diff", diff_text)
        _write_json(evidence_dir / "untracked-files.json", untracked)
        _write_json(evidence_dir / "grading.json", grading)
        _write_json(
            evidence_dir / "execution.json",
            {
                "command": command,
                "cwd": str(worktree),
                "exit_code": process_result.returncode,
                "termination_status": termination_status,
                "timeout": timed_out,
                "duration_seconds": duration,
                "target_started": target_started,
            },
        )

        if grading["grader_status"] == "failed" and validity_status == "valid":
            validity_status = "invalid"
            validity_reason = "required grader failed and prevented classification"

        observation = _build_observation(
            benchmark_case=benchmark_case,
            prepared=prepared,
            target=target,
            repetition=repetition,
            observation_id=observation_id,
            validity_status=validity_status,
            validity_reason=validity_reason,
            behavior=grading,
            execution={
                "exit_code": process_result.returncode,
                "duration_seconds": duration,
                "termination_status": termination_status,
                "timeout": timed_out,
                "target_started": target_started,
                "monorepo_commit": _monorepo_commit(),
            },
            evidence_dir=evidence_dir,
        )
        validate_observation_record(observation)
        _write_json(evidence_dir / "observation.json", observation)
        return ExecutionResult(observation_id, observation, evidence_dir)
    finally:
        if keep_worktree:
            _write_text(evidence_dir / "worktree.txt", str(worktree))
        else:
            _remove_tree(worktree)


def prepare_treatment(benchmark_case: Mapping[str, Any], treatment: str) -> PreparedTreatment:
    if treatment == "ai-doc":
        raise TreatmentPreparationError(
            "ai-doc treatment generation is not implemented in execution v0.1 without "
            "a real ai-doc API binding"
        )
    if treatment not in TREATMENT_KEYS:
        choices = ", ".join([*TREATMENT_KEYS, "ai-doc"])
        raise TreatmentPreparationError(
            f"unknown treatment {treatment!r}; expected one of: {choices}"
        )

    treatment_key = TREATMENT_KEYS[treatment]
    controls = benchmark_case["control_treatments"]
    control = controls[treatment_key]

    if treatment == "simple-compression-control" and not control["applicable"]:
        raise TreatmentPreparationError(
            f"simple-compression-control is not applicable: {control['reason']}"
        )

    configuration = "source"
    if treatment == "simple-compression-control":
        configuration = control["method"]
    elif treatment == "degraded-control":
        configuration = control["degradation"]

    artifact = _render_task_artifact(benchmark_case, treatment, configuration)
    return PreparedTreatment(
        treatment_class=treatment,
        configuration=configuration,
        resulting_corpus=f"{benchmark_case['source_instruction_corpus']['id']}:{treatment}",
        artifact=artifact,
        artifact_sha256=hashlib.sha256(artifact.encode("utf-8")).hexdigest(),
    )


def grade_case(worktree: Path, benchmark_case: Mapping[str, Any]) -> dict[str, Any]:
    baseline_files = benchmark_case["initial_workspace"]["files"]
    diff_names = _git(["diff", "--name-only", "HEAD"], worktree, capture=True).splitlines()
    changed_paths = set(diff_names)
    test_cache: dict[str, tuple[bool, str]] = {}
    criteria: list[dict[str, Any]] = []

    grader_status = "completed"
    for group_name in (
        "task_success_criteria",
        "required_instruction_criteria",
        "forbidden_criteria",
        "conditional_criteria",
        "critical_constraints",
    ):
        for criterion in benchmark_case["ground_truth"][group_name]:
            result = _classify_criterion(
                worktree=worktree,
                baseline_files=baseline_files,
                changed_paths=changed_paths,
                criterion=criterion,
                test_cache=test_cache,
            )
            criteria.append(result)
            if result.get("grader_error"):
                grader_status = "failed"

    task_outcomes = [
        criterion["outcome"] for criterion in criteria if criterion["type"] == "task_success"
    ]
    if task_outcomes and all(outcome == "satisfied" for outcome in task_outcomes):
        task_success: bool | str = True
    elif any(outcome == "violated" for outcome in task_outcomes):
        task_success = False
    else:
        task_success = "unknown"

    return {
        "task_success": task_success,
        "criteria": criteria,
        "grader_status": grader_status,
    }


def _find_case(corpus: Mapping[str, Any], case_id: str) -> Mapping[str, Any]:
    for benchmark_case in corpus.get("cases", []):
        if isinstance(benchmark_case, Mapping) and benchmark_case.get("id") == case_id:
            return benchmark_case
    raise ExecutionError(f"case not found: {case_id}")


def _populate_worktree(worktree: Path, benchmark_case: Mapping[str, Any]) -> None:
    _git(["init"], worktree)
    _git(["config", "user.name", "AI Doc Benchmark"], worktree)
    _git(["config", "user.email", "benchmark@example.invalid"], worktree)

    for path, content in benchmark_case["initial_workspace"]["files"].items():
        if path in AGENT_INSTRUCTION_FILES:
            raise ExecutionError(
                f"case workspace must not deliver benchmark instructions via {path}"
            )
        _write_text(worktree / path, content)


def _render_task_artifact(
    benchmark_case: Mapping[str, Any], treatment: str, configuration: str
) -> str:
    sections = [
        f"# {benchmark_case['task']['id']}",
        "",
        benchmark_case["task"]["prompt"],
        "",
        "## Instruction Corpus",
        "",
    ]

    for path, content in benchmark_case["source_instruction_corpus"]["files"].items():
        sections.extend(
            [
                f"### {path}",
                "",
                "```text",
                content.rstrip(),
                "```",
                "",
            ]
        )

    if treatment != "original":
        sections.extend(
            [
                "## Treatment Control",
                "",
                f"Treatment: {treatment}",
                f"Configuration: {configuration}",
                "",
            ]
        )

    return "\n".join(sections).rstrip() + "\n"


def _classify_criterion(
    *,
    worktree: Path,
    baseline_files: Mapping[str, str],
    changed_paths: set[str],
    criterion: Mapping[str, Any],
    test_cache: dict[str, tuple[bool, str]],
) -> dict[str, Any]:
    criterion_type = criterion["type"]
    evidence = criterion["observable_evidence"]
    supported, ok, details = _evaluate_evidence(
        worktree=worktree,
        baseline_files=baseline_files,
        changed_paths=changed_paths,
        evidence=evidence,
        test_cache=test_cache,
    )

    if not supported:
        outcome = "unknown"
    elif ok:
        outcome = "satisfied"
    else:
        outcome = "violated"

    result: dict[str, Any] = {
        "id": criterion["id"],
        "type": criterion_type,
        "outcome": outcome,
        "evidence": details,
    }
    if criterion_type == "conditional":
        result["applicability"] = "unknown" if not supported else "applicable"
    return result


def _evaluate_evidence(
    *,
    worktree: Path,
    baseline_files: Mapping[str, str],
    changed_paths: set[str],
    evidence: str,
    test_cache: dict[str, tuple[bool, str]],
) -> tuple[bool, bool, str]:
    if evidence.endswith(" passes") and evidence.startswith("tests/"):
        test_path = evidence.removesuffix(" passes")
        return _run_python_test_file(worktree, test_path, test_cache)

    marker = " contains "
    if marker in evidence:
        path_text, expected = evidence.split(marker, 1)
        path = path_text.strip()
        file_path = worktree / path
        if file_path.exists() and file_path.is_file():
            return True, expected.strip() in file_path.read_text(encoding="utf-8"), evidence

    if evidence.startswith("git diff contains no changes under "):
        prefix = evidence.removeprefix("git diff contains no changes under ").strip()
        return True, all(not path.startswith(prefix) for path in changed_paths), evidence

    if evidence.endswith(" is unchanged"):
        path = evidence.removesuffix(" is unchanged").strip()
        return _file_matches_baseline(worktree, baseline_files, path, evidence)

    if evidence.endswith(" is byte-identical to baseline"):
        path = evidence.removesuffix(" is byte-identical to baseline").strip()
        return _file_matches_baseline(worktree, baseline_files, path, evidence)

    if evidence.startswith("no files under ") and evidence.endswith(" changed"):
        prefix = evidence.removeprefix("no files under ").removesuffix(" changed").strip()
        return True, all(not path.startswith(prefix) for path in changed_paths), evidence

    return False, False, f"unsupported deterministic evidence: {evidence}"


def _file_matches_baseline(
    worktree: Path, baseline_files: Mapping[str, str], path: str, evidence: str
) -> tuple[bool, bool, str]:
    if path not in baseline_files:
        return True, False, f"{evidence}; no baseline entry"
    file_path = worktree / path
    if not file_path.exists():
        return True, False, f"{evidence}; file missing"
    return True, file_path.read_text(encoding="utf-8") == baseline_files[path], evidence


def _run_python_test_file(
    worktree: Path, test_path: str, test_cache: dict[str, tuple[bool, str]]
) -> tuple[bool, bool, str]:
    if test_path in test_cache:
        ok, details = test_cache[test_path]
        return True, ok, details

    if not (worktree / test_path).exists():
        details = f"{test_path} is missing"
        test_cache[test_path] = (False, details)
        return True, False, details

    runner = textwrap.dedent(
        """
        import importlib.util
        import pathlib
        import sys
        import traceback

        root = pathlib.Path.cwd()
        path = root / sys.argv[1]
        sys.path.insert(0, str(root))
        spec = importlib.util.spec_from_file_location("benchmark_case_tests", path)
        module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(module)
            tests = [
                value for name, value in vars(module).items()
                if name.startswith("test_") and callable(value)
            ]
            if not tests:
                raise AssertionError("no test_ functions found")
            for test in tests:
                test()
        except BaseException:
            traceback.print_exc()
            raise
        """
    )
    result = subprocess.run(
        [sys.executable, "-c", runner, test_path],
        cwd=worktree,
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )
    details = (result.stdout + result.stderr).strip() or f"{test_path} passed"
    ok = result.returncode == 0
    test_cache[test_path] = (ok, details)
    return True, ok, details


def _build_observation(
    *,
    benchmark_case: Mapping[str, Any],
    prepared: PreparedTreatment,
    target: ExecutionTarget,
    repetition: int,
    observation_id: str,
    validity_status: str,
    validity_reason: str | None,
    behavior: Mapping[str, Any],
    execution: Mapping[str, Any],
    evidence_dir: Path,
) -> dict[str, Any]:
    return {
        "observation_id": observation_id,
        "benchmark_version": BENCHMARK_VERSION,
        "case": {
            "id": benchmark_case["id"],
            "revision": benchmark_case["revision"],
            "categories": benchmark_case["categories"],
            "quality_cohort": benchmark_case["quality_cohort"],
            "source_corpus": benchmark_case["source_instruction_corpus"]["id"],
            "task": benchmark_case["task"]["id"],
        },
        "treatment": {
            "class": prepared.treatment_class,
            "configuration": prepared.configuration,
            "resulting_corpus": prepared.resulting_corpus,
            "artifact_sha256": prepared.artifact_sha256,
        },
        "target": {
            "provider": target.id,
            "model": target.model,
            "configuration": {"args": list(target.args), "timeout_seconds": target.timeout_seconds},
            "tool_version": target.tool_version,
        },
        "repetition": {"index": repetition},
        "validity": {"status": validity_status, "reason": validity_reason},
        "behavior": {
            "task_success": behavior["task_success"],
            "criteria": behavior["criteria"],
        },
        "instructions": {
            "corpus": prepared.resulting_corpus,
            "bytes": len(prepared.artifact.encode("utf-8")),
            "tokens": {"status": "unavailable", "value": None},
        },
        "execution": dict(execution),
        "evidence": {
            "task": str(evidence_dir / "task.md"),
            "instruction_corpus": str(evidence_dir / "treatment.json"),
            "workspace_diff": str(evidence_dir / "workspace.diff"),
            "grading_evidence": str(evidence_dir / "grading.json"),
        },
    }


def _collect_untracked(worktree: Path) -> dict[str, Any]:
    output = _git(["ls-files", "--others", "--exclude-standard", "-z"], worktree, capture=True)
    paths = [path for path in output.split("\0") if path]
    files = []
    for path in paths:
        file_path = worktree / path
        entry: dict[str, Any] = {"path": path}
        if file_path.is_file():
            content = file_path.read_bytes()
            entry["sha256"] = hashlib.sha256(content).hexdigest()
            if len(content) <= 16_384:
                try:
                    entry["text"] = content.decode("utf-8")
                except UnicodeDecodeError:
                    entry["text"] = None
        files.append(entry)
    return {"files": files}


def _monorepo_commit() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=Path(__file__).resolve().parents[4],
            text=True,
            capture_output=True,
            check=False,
        ).stdout.strip()
    except OSError:
        return "unavailable"


def _git(args: Sequence[str], cwd: Path, *, capture: bool = False) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        details = result.stderr.strip()
        raise ExecutionError(f"git {' '.join(args)} failed: {details}")
    return result.stdout if capture else ""


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{json.dumps(payload, indent=2)}\n", encoding="utf-8")


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _remove_tree(path: Path) -> None:
    def retry_with_write_permission(function: Any, value: str, _exc_info: Any) -> None:
        os.chmod(value, stat.S_IWRITE)
        function(value)

    if path.exists():
        shutil.rmtree(path, onerror=retry_with_write_permission)
