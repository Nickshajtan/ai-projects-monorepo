from __future__ import annotations

import json
import unittest
from pathlib import Path

from ai_doc_benchmarks.schema import BenchmarkValidationError, validate_corpus

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "corpus" / "benchmark-corpus-v0.1.json"


def load_corpus() -> dict:
    return json.loads(CORPUS.read_text(encoding="utf-8"))


class CorpusTests(unittest.TestCase):
    def test_starter_corpus_is_valid(self) -> None:
        validate_corpus(load_corpus())

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
            validate_corpus(corpus)
