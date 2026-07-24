"""Audit exact-sequence validity of completed Task035b regionwise-p spaces."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from src.adaptivity.hcurl_regionwise_p import (
    create_reduced_trace_hcurl_element,
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def build_regionwise_space_audit(
    p4_trace_candidate: dict[str, Any],
    p5_trace_p4_low_candidate: dict[str, Any],
    *,
    p4_source: dict[str, str] | None = None,
    p5_source: dict[str, str] | None = None,
    generator_source_commit: str | None = None,
) -> dict[str, Any]:
    """Reclassify candidate evidence using a local de Rham prerequisite."""

    expected_status = "actual_regionwise_p_controlled_negative"
    if p4_trace_candidate.get("status") != expected_status:
        raise ValueError("p4-trace candidate record has an unexpected status")
    if p5_trace_p4_low_candidate.get("status") != expected_status:
        raise ValueError("p5-trace candidate record has an unexpected status")
    p4_audit = create_reduced_trace_hcurl_element(4, 6, 4).audit
    p5_audit = create_reduced_trace_hcurl_element(5, 6, 4).audit
    p4_valid = bool(p4_audit["both_high_and_low_exact_sequence_pass"])
    p5_valid = bool(p5_audit["both_high_and_low_exact_sequence_pass"])
    if not p4_valid or p5_valid:
        raise RuntimeError(
            "regionwise exact-sequence audit did not reproduce the expected "
            "valid-p4 / invalid-p5 structural split"
        )
    return {
        "schema_version": "task035b.regionwise-space-structural-audit.v1",
        "status": "regionwise_space_structural_audit_complete",
        "pass": True,
        "canonical": False,
        "production_qualified": False,
        "ordinary_default_changed": False,
        "generator_source": {
            "commit_sha": generator_source_commit,
            "verified_clean_sha": generator_source_commit,
        },
        "source_records": {
            "p4_trace_p4_p6_interior": p4_source,
            "p5_trace_p4_low_p6_high": p5_source,
        },
        "candidates": {
            "p4_trace_p4_p6_interior": {
                "original_status": p4_trace_candidate["status"],
                "candidate_accuracy_pass": p4_trace_candidate.get(
                    "candidate_accuracy_pass"
                ),
                "local_space_audit": p4_audit,
                "exact_sequence_valid_for_accuracy_interpretation": True,
                "reclassification": (
                    "valid_exact_sequence_controlled_negative_accuracy"
                ),
            },
            "p5_trace_p4_low_p6_high": {
                "original_status": p5_trace_p4_low_candidate["status"],
                "candidate_accuracy_pass": p5_trace_p4_low_candidate.get(
                    "candidate_accuracy_pass"
                ),
                "local_space_audit": p5_audit,
                "exact_sequence_valid_for_accuracy_interpretation": False,
                "reclassification": (
                    "controlled_negative_non_exact_sequence_space"
                ),
                "missing_gradient_mode_count": p5_audit[
                    "low_exact_sequence"
                ]["missing_gradient_mode_count"],
            },
        },
        "independent_exact_sequence_valid_accuracy_negative_count": 1,
        "previous_two_negative_lane_closure_supported": False,
        "lane_decision": (
            "reopen_only_for_an_exact-sequence-conforming physically reduced "
            "trace/local-p construction; do not rerun the invalid "
            "p5-trace/p4-interior space"
        ),
        "interpretation": (
            "a small linear residual certifies the solved algebraic system, "
            "not the missing-gradient de Rham prerequisite of that system"
        ),
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--p4-trace-record", type=Path, required=True)
    parser.add_argument("--p5-trace-record", type=Path, required=True)
    parser.add_argument("--verified-clean-sha", required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    if (
        len(args.verified_clean_sha) != 40
        or any(
            character not in "0123456789abcdef"
            for character in args.verified_clean_sha.lower()
        )
    ):
        raise ValueError("--verified-clean-sha must be a full 40-hex commit")
    p4_path = args.p4_trace_record.resolve()
    p5_path = args.p5_trace_record.resolve()
    record = build_regionwise_space_audit(
        json.loads(p4_path.read_text(encoding="utf-8")),
        json.loads(p5_path.read_text(encoding="utf-8")),
        p4_source={"path": str(p4_path), "sha256": _sha256(p4_path)},
        p5_source={"path": str(p5_path), "sha256": _sha256(p5_path)},
        generator_source_commit=args.verified_clean_sha,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(record, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
