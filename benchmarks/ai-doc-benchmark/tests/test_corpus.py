from __future__ import annotations

import json
import unittest
from pathlib import Path

from ai_doc_benchmarks.schema import (
    BenchmarkValidationError,
    validate_case,
    validate_corpus,
    validate_starter_corpus_profile,
)

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "corpus" / "benchmark-corpus-v0.1.json"


def load_corpus() -> dict:
    return json.loads(CORPUS.read_text(encoding="utf-8"))


class CorpusTests(unittest.TestCase):
    def test_starter_corpus_is_valid(self) -> None:
        validate_corpus(load_corpus())
        validate_starter_corpus_profile(load_corpus())

    def test_case_revisions_are_explicit(self) -> None:
        corpus = load_corpus()
        self.assertTrue(all(case["revision"] for case in corpus["cases"]))

    def test_validation_rejects_missing_category_coverage(self) -> None:
        corpus = load_corpus()
        for case in corpus["cases"]:
            case["categories"] = [
                category for category in case["categories"] if category != "duplication"
            ]

        with self.assertRaisesRegex(BenchmarkValidationError, "missing category coverage"):
            validate_starter_corpus_profile(corpus)

    def test_generic_corpus_validity_does_not_require_starter_coverage(self) -> None:
        corpus = load_corpus()
        corpus["cases"] = corpus["cases"][:1]

        validate_corpus(corpus)
        with self.assertRaisesRegex(BenchmarkValidationError, "missing category coverage"):
            validate_starter_corpus_profile(corpus)

    def test_generic_corpus_validity_has_no_starter_size_limit(self) -> None:
        corpus = load_corpus()
        corpus["cases"] = corpus["cases"][:14]
        validate_corpus(corpus)

        corpus = load_corpus()
        template = corpus["cases"][0]
        while len(corpus["cases"]) < 21:
            clone = json.loads(json.dumps(template))
            clone["id"] = f"{template['id']}-extra-{len(corpus['cases'])}"
            clone["revision"] = "2026-09-22.1"
            corpus["cases"].append(clone)
        validate_corpus(corpus)

    def test_case_revision_is_required(self) -> None:
        case = load_corpus()["cases"][0]
        del case["revision"]

        with self.assertRaisesRegex(BenchmarkValidationError, "revision"):
            validate_case(case)

    def test_non_applicable_simple_compression_control_validates(self) -> None:
        case = next(
            case
            for case in load_corpus()["cases"]
            if not case["control_treatments"]["simple_compression_control"]["applicable"]
        )

        validate_case(case)

    def test_applicable_simple_compression_control_requires_method(self) -> None:
        case = load_corpus()["cases"][0]
        del case["control_treatments"]["simple_compression_control"]["method"]

        with self.assertRaisesRegex(BenchmarkValidationError, "method"):
            validate_case(case)

    def test_non_applicable_simple_compression_control_rejects_fake_method(self) -> None:
        case = next(
            case
            for case in load_corpus()["cases"]
            if not case["control_treatments"]["simple_compression_control"]["applicable"]
        )
        case["control_treatments"]["simple_compression_control"]["method"] = "pretend transform"

        with self.assertRaisesRegex(BenchmarkValidationError, "must not define method"):
            validate_case(case)
