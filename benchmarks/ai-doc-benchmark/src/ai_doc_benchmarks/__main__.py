from __future__ import annotations

import argparse
import json
from pathlib import Path

from ai_doc_benchmarks.execution import ExecutionTarget, run_execution
from ai_doc_benchmarks.schema import (
    BenchmarkValidationError,
    validate_corpus,
    validate_starter_corpus_profile,
)


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m ai_doc_benchmarks")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_parser = subparsers.add_parser("validate")
    validate_parser.add_argument("--starter-profile", action="store_true")
    validate_parser.add_argument("corpus", type=Path)

    execute_parser = subparsers.add_parser("execute")
    execute_parser.add_argument("--corpus", type=Path, required=True)
    execute_parser.add_argument("--case-id", required=True)
    execute_parser.add_argument("--treatment", required=True)
    execute_parser.add_argument("--target", type=Path, required=True)
    execute_parser.add_argument("--output-dir", type=Path, required=True)
    execute_parser.add_argument("--repetition", type=int, default=1)
    execute_parser.add_argument("--observation-id")
    execute_parser.add_argument("--keep-worktree", action="store_true")

    args = parser.parse_args()
    if args.command == "validate":
        payload = json.loads(args.corpus.read_text(encoding="utf-8"))
        try:
            if args.starter_profile:
                validate_starter_corpus_profile(payload)
            else:
                validate_corpus(payload)
        except BenchmarkValidationError as exc:
            print(str(exc))
            return 1
        print(f"valid: {args.corpus}")
        return 0
    if args.command == "execute":
        corpus = json.loads(args.corpus.read_text(encoding="utf-8"))
        target = ExecutionTarget.from_mapping(json.loads(args.target.read_text(encoding="utf-8")))
        result = run_execution(
            corpus=corpus,
            case_id=args.case_id,
            treatment=args.treatment,
            target=target,
            output_dir=args.output_dir,
            repetition=args.repetition,
            observation_id=args.observation_id,
            keep_worktree=args.keep_worktree,
        )
        if result.preparation_failure is not None:
            print(f"preparation failed: {result.evidence_dir}")
            return 1
        print(f"observation: {result.evidence_dir / 'observation.json'}")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
