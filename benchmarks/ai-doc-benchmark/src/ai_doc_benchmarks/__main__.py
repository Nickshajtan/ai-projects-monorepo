from __future__ import annotations

import argparse
import json
from pathlib import Path

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
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
