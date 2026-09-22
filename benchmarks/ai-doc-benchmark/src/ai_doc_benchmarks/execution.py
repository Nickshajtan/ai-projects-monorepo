from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
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
    provenance: Mapping[str, Any] = field(default_factory=dict)


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
    keep_workspace: bool = False,
    ai_doc_root: Path | None = None,
) -> ExecutionResult:
    benchmark_case = _find_case(corpus, case_id)
    validate_case(benchmark_case)

    observation_id = observation_id or f"obs-{uuid.uuid4().hex}"
    evidence_dir = output_dir / observation_id
    evidence_dir.mkdir(parents=True, exist_ok=False)

    try:
        prepared = prepare_treatment(benchmark_case, treatment, ai_doc_root=ai_doc_root)
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
            "provenance": dict(prepared.provenance),
        },
    )

    workspace_parent = output_dir / "workspaces"
    workspace_parent.mkdir(parents=True, exist_ok=True)
    workspace = Path(tempfile.mkdtemp(prefix=f"{observation_id}-", dir=workspace_parent))
    target_started = False
    execution_started_at = time.monotonic()
    process_result: subprocess.CompletedProcess[str] | None = None
    timed_out = False
    validity_status = "valid"
    validity_reason: str | None = None

    try:
        _populate_workspace(workspace, benchmark_case)
        _write_text(workspace / "task.md", prepared.artifact)
        _git(["add", "."], workspace)
        _git(["commit", "-m", "case baseline"], workspace)

        resolved_command = _resolve_executable(target.command)
        command = [resolved_command, *target.args, PROMPT]
        env = os.environ.copy()
        env.update(target.env)

        try:
            target_started = True
            process_result = subprocess.run(
                command,
                cwd=workspace,
                env=env,
                text=True,
                encoding="utf-8",
                errors="replace",
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
                stdout=_decode_subprocess_output(exc.stdout),
                stderr=_decode_subprocess_output(exc.stderr),
            )
            termination_status = "timeout"
        except FileNotFoundError as exc:
            target_started = False
            validity_status = "invalid"
            attempted_executable = exc.filename or command[0]
            validity_reason = f"target executable could not start: {attempted_executable}"
            process_result = subprocess.CompletedProcess(
                command, returncode=127, stdout="", stderr=str(exc)
            )
            termination_status = "startup-failure"

        duration = time.monotonic() - execution_started_at
        grading = grade_case(workspace, benchmark_case)
        diff_text = _git(["diff", "--no-ext-diff", "HEAD"], workspace, capture=True)
        untracked = _collect_untracked(workspace)

        _write_text(evidence_dir / "stdout.txt", process_result.stdout or "")
        _write_text(evidence_dir / "stderr.txt", process_result.stderr or "")
        _write_text(evidence_dir / "workspace.diff", diff_text)
        _write_json(evidence_dir / "untracked-files.json", untracked)
        _write_json(evidence_dir / "grading.json", grading)
        _write_json(
            evidence_dir / "execution.json",
            {
                "command": command,
                "cwd": str(workspace),
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
        if keep_workspace:
            _write_text(evidence_dir / "workspace.txt", str(workspace))
        else:
            _remove_tree(workspace)


def prepare_treatment(
    benchmark_case: Mapping[str, Any], treatment: str, *, ai_doc_root: Path | None = None
) -> PreparedTreatment:
    if treatment == "ai-doc":
        return _prepare_ai_doc_treatment(benchmark_case, ai_doc_root=ai_doc_root)
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

    artifact_files = _artifact_files(control, treatment)
    artifact = _render_task_artifact(benchmark_case, artifact_files)
    return PreparedTreatment(
        treatment_class=treatment,
        configuration=configuration,
        resulting_corpus=f"{benchmark_case['source_instruction_corpus']['id']}:{treatment}",
        artifact=artifact,
        artifact_sha256=hashlib.sha256(artifact.encode("utf-8")).hexdigest(),
        provenance={"artifact_source": "benchmark-data"},
    )


def _artifact_files(control: Mapping[str, Any], treatment: str) -> Mapping[str, str]:
    artifact = control.get("artifact")
    if not isinstance(artifact, Mapping) or not isinstance(artifact.get("files"), Mapping):
        raise TreatmentPreparationError(
            f"{treatment} does not define a deterministic treatment artifact"
        )
    files = artifact["files"]
    if not files or not all(
        isinstance(path, str) and isinstance(text, str) for path, text in files.items()
    ):
        raise TreatmentPreparationError(
            f"{treatment} artifact.files must be a non-empty string map"
        )
    return files


def _prepare_ai_doc_treatment(
    benchmark_case: Mapping[str, Any], *, ai_doc_root: Path | None
) -> PreparedTreatment:
    root = ai_doc_root or Path(__file__).resolve().parents[4] / "projects" / "ai-doc"
    python = root / ".venv" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    if not python.exists():
        raise TreatmentPreparationError(f"ai-doc runtime is missing at {python}")

    with tempfile.TemporaryDirectory() as temp:
        project = Path(temp) / "project"
        project.mkdir()
        source_files = benchmark_case["source_instruction_corpus"]["files"]
        for path, content in source_files.items():
            _write_text(project / path, content)
        include = ", ".join(json.dumps(path) for path in source_files)
        profiles = ", ".join(f"{json.dumps(path)}: instruction" for path in source_files)
        _write_text(
            project / ".ai-doc.yaml",
            f"version: 1\ninclude: [{include}]\nprofiles: {{{profiles}}}\n",
        )
        output = project / ".ai-doc-output"
        env = os.environ.copy()
        env["PYTHONPATH"] = str(root / "src")
        result = subprocess.run(
            [
                str(python),
                "-m",
                "ai_doc",
                "optimize",
                str(project),
                "--output",
                str(output),
                "--max-candidates",
                "2",
            ],
            text=True,
            capture_output=True,
            env=env,
            check=False,
        )
        if result.returncode not in {0, 4}:
            raise TreatmentPreparationError(
                f"ai-doc optimize failed with exit {result.returncode}: {result.stderr.strip()}"
            )
        run_dirs = sorted(output.iterdir()) if output.exists() else []
        if not run_dirs:
            raise TreatmentPreparationError("ai-doc optimize produced no output run directory")
        run_dir = run_dirs[-1]
        candidate, selection_provenance = _select_ai_doc_result(run_dir)
        files: dict[str, str] = {}
        for path in source_files:
            candidate_file = candidate / path
            if candidate_file.exists():
                files[path] = candidate_file.read_text(encoding="utf-8")
        if not files:
            raise TreatmentPreparationError(
                "ai-doc candidate artifact did not contain source files"
            )

    artifact = _render_task_artifact(benchmark_case, files)
    commit = _git(["rev-parse", "HEAD"], root, capture=True).strip()
    return PreparedTreatment(
        treatment_class="ai-doc",
        configuration="cli optimize --max-candidates 2",
        resulting_corpus=f"{benchmark_case['source_instruction_corpus']['id']}:ai-doc",
        artifact=artifact,
        artifact_sha256=hashlib.sha256(artifact.encode("utf-8")).hexdigest(),
        provenance={
            "artifact_source": "ai-doc-cli",
            "ai_doc_root": str(root),
            "ai_doc_commit": commit,
            "invocation_path": "python -m ai_doc optimize",
            **selection_provenance,
        },
    )


def _select_ai_doc_result(run_dir: Path) -> tuple[Path, dict[str, Any]]:
    run_json = run_dir / "run.json"
    if not run_json.exists():
        raise TreatmentPreparationError("ai-doc optimize did not write run.json")
    run = json.loads(run_json.read_text(encoding="utf-8"))
    recommended = run.get("recommended_candidate_id")

    if isinstance(recommended, str) and recommended:
        selected = _candidate_artifact_dir(run_dir, recommended)
        if not selected.exists():
            raise TreatmentPreparationError(
                f"ai-doc recommended candidate {recommended!r} has no artifact"
            )
        return selected, {
            "candidate_id": recommended,
            "selection_source": "recommended_candidate_id",
            "selection_rule": "used ai-doc recommended candidate",
            "recommendation_reason": run.get("recommendation_reason"),
            "run_id": run.get("run_id"),
        }

    candidate_ids = sorted(
        candidate["id"]
        for candidate in run.get("candidates", [])
        if isinstance(candidate, Mapping)
        and isinstance(candidate.get("id"), str)
        and candidate["id"] != run.get("baseline_candidate_id", "baseline")
        and _candidate_artifact_dir(run_dir, candidate["id"]).exists()
    )
    if not candidate_ids:
        raise TreatmentPreparationError("ai-doc optimize produced no candidate artifact")

    selected_id = candidate_ids[0]
    return _candidate_artifact_dir(run_dir, selected_id), {
        "candidate_id": selected_id,
        "selection_source": "deterministic-fallback",
        "selection_rule": (
            "ai-doc reported no recommended_candidate_id; selected lexicographically "
            "first generated candidate id"
        ),
        "recommendation_reason": run.get("recommendation_reason"),
        "run_id": run.get("run_id"),
    }


def _candidate_artifact_dir(run_dir: Path, candidate_id: str) -> Path:
    if candidate_id == "baseline":
        return run_dir / "baseline"
    return run_dir / "candidates" / candidate_id / "candidate"


def _resolve_executable(command: str) -> str:
    return shutil.which(command) or command


def _decode_subprocess_output(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return value.decode("utf-8", errors="replace")


def grade_case(worktree: Path, benchmark_case: Mapping[str, Any]) -> dict[str, Any]:
    grader = benchmark_case.get("grader")
    if not isinstance(grader, Mapping) or not isinstance(grader.get("python"), str):
        return _failed_grading(
            benchmark_case, "case does not define executable deterministic grader"
        )

    with tempfile.TemporaryDirectory() as temp:
        grader_path = Path(temp) / "grader.py"
        baseline_path = Path(temp) / "baseline.json"
        grader_path.write_text(grader["python"], encoding="utf-8")
        baseline_path.write_text(
            json.dumps({"files": benchmark_case["initial_workspace"]["files"]}),
            encoding="utf-8",
        )
        result = subprocess.run(
            [sys.executable, str(grader_path), str(worktree), str(baseline_path)],
            text=True,
            capture_output=True,
            timeout=30,
            check=False,
        )

    if result.returncode != 0:
        return _failed_grading(benchmark_case, (result.stdout + result.stderr).strip())
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        return _failed_grading(benchmark_case, f"grader emitted invalid JSON: {exc}")

    criteria = payload.get("criteria")
    task_success = payload.get("task_success")
    if task_success not in {True, False, "unknown"} or not isinstance(criteria, list):
        return _failed_grading(benchmark_case, "grader result missing task_success or criteria")

    return {
        "task_success": task_success,
        "criteria": criteria,
        "grader_status": "completed",
    }


def _failed_grading(benchmark_case: Mapping[str, Any], reason: str) -> dict[str, Any]:
    criteria: list[dict[str, Any]] = []
    for group_name in (
        "task_success_criteria",
        "required_instruction_criteria",
        "forbidden_criteria",
        "conditional_criteria",
        "critical_constraints",
    ):
        for criterion in benchmark_case["ground_truth"][group_name]:
            result: dict[str, Any] = {
                "id": criterion["id"],
                "type": criterion["type"],
                "outcome": "unknown",
                "evidence": reason,
                "grader_error": True,
            }
            if criterion["type"] == "conditional":
                result["applicability"] = "unknown"
            criteria.append(result)
    return {
        "task_success": "unknown",
        "criteria": criteria,
        "grader_status": "failed",
        "reason": reason,
    }


def _find_case(corpus: Mapping[str, Any], case_id: str) -> Mapping[str, Any]:
    for benchmark_case in corpus.get("cases", []):
        if isinstance(benchmark_case, Mapping) and benchmark_case.get("id") == case_id:
            return benchmark_case
    raise ExecutionError(f"case not found: {case_id}")


def _populate_workspace(worktree: Path, benchmark_case: Mapping[str, Any]) -> None:
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
    benchmark_case: Mapping[str, Any], instruction_files: Mapping[str, str]
) -> str:
    sections = [
        f"# {benchmark_case['task']['id']}",
        "",
        benchmark_case["task"]["prompt"],
        "",
        "## Instruction Corpus",
        "",
    ]

    for path, content in instruction_files.items():
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

    return "\n".join(sections).rstrip() + "\n"


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
