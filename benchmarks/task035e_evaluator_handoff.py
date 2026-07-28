#!/usr/bin/env python3
"""Cross the Task035e blind/evaluator boundary after campaign termination.

The blind campaign may create a frozen receipt and candidate bundle, but it
must not import or call the evaluator while either adaptive path is still
running.  This independent entrypoint is invoked only after both paths have
terminated and the candidate-freeze stage has closed.  It verifies every
content binding before any sealed reference package can be opened.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile
from typing import Any, Mapping, Sequence

from src.adaptivity.hidden_auditor import preflight_frozen_candidate
from src.adaptivity.hidden_auditor.contracts import canonical_json_sha256


EVALUATOR_HANDOFF_SCHEMA = "task035e.evaluator-handoff.v1"


class EvaluatorHandoffError(ValueError):
    """Raised when a frozen artifact cannot cross the evaluator boundary."""


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _load_private_mapping(path: Path, *, label: str) -> tuple[Path, dict[str, Any], str]:
    if path.is_symlink():
        raise EvaluatorHandoffError(f"{label} must not be a symlink")
    resolved = path.resolve(strict=True)
    if not resolved.is_file() or stat.S_IMODE(resolved.stat().st_mode) != 0o600:
        raise EvaluatorHandoffError(
            f"{label} must be one immutable mode-0600 JSON file"
        )
    try:
        value = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise EvaluatorHandoffError(f"cannot read {label}") from exc
    if not isinstance(value, Mapping):
        raise EvaluatorHandoffError(f"{label} must contain one JSON object")
    return resolved, dict(value), _file_sha256(resolved)


def _write_private_mapping(path: Path, payload: Mapping[str, Any]) -> Path:
    if path.is_symlink() or path.exists():
        raise FileExistsError(f"refusing to overwrite evaluator handoff: {path}")
    destination = path.resolve(strict=False)
    destination.parent.mkdir(parents=True, exist_ok=True)
    encoded = (
        json.dumps(
            payload,
            sort_keys=True,
            indent=2,
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
        + b"\n"
    )
    descriptor, temporary_name = tempfile.mkstemp(
        dir=destination.parent,
        prefix=f".{destination.name}.",
        suffix=".tmp",
    )
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, destination)
        temporary.unlink()
        directory_descriptor = os.open(destination.parent, os.O_RDONLY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    except BaseException:
        try:
            os.close(descriptor)
        except OSError:
            pass
        temporary.unlink(missing_ok=True)
        raise
    return destination


def run_evaluator_handoff(
    *,
    freeze_receipt_path: Path,
    candidate_bundle_path: Path,
    output_path: Path,
) -> Mapping[str, Any]:
    """Preflight one frozen candidate without opening the sealed reference."""

    (
        resolved_receipt,
        freeze_receipt,
        freeze_receipt_file_sha256,
    ) = _load_private_mapping(
        freeze_receipt_path,
        label="freeze receipt",
    )
    (
        resolved_bundle,
        candidate_bundle,
        candidate_bundle_file_sha256,
    ) = _load_private_mapping(
        candidate_bundle_path,
        label="candidate bundle",
    )
    preflight = preflight_frozen_candidate(
        freeze_receipt,
        candidate_bundle,
    )
    unsigned: dict[str, Any] = {
        "schema_version": EVALUATOR_HANDOFF_SCHEMA,
        "status": "preflight_pass",
        "pass": True,
        "trial_id": preflight.receipt.trial_id,
        "algorithm_id": preflight.receipt.algorithm_id,
        "source_sha": preflight.receipt.source_sha,
        "cycle_index": preflight.receipt.cycle_index,
        "freeze_receipt_path": resolved_receipt.as_posix(),
        "freeze_receipt_file_sha256": freeze_receipt_file_sha256,
        "freeze_receipt_payload_sha256": (
            preflight.receipt.frozen_payload_sha256
        ),
        "candidate_bundle_path": resolved_bundle.as_posix(),
        "candidate_bundle_file_sha256": candidate_bundle_file_sha256,
        "candidate_bundle_payload_sha256": canonical_json_sha256(
            candidate_bundle
        ),
        "candidate_output_sha256": preflight.receipt.output_sha256,
        "resource_inventory_sha256": (
            preflight.receipt.resource_inventory_sha256
        ),
        "two_path_gate_sha256": preflight.receipt.two_path_gate_sha256,
        "sealed_reference_opened": False,
        "ordinary_default_changed": False,
    }
    payload = {
        **unsigned,
        "handoff_sha256": canonical_json_sha256(unsigned),
    }
    _write_private_mapping(output_path, payload)
    return payload


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze-receipt", type=Path, required=True)
    parser.add_argument("--candidate-bundle", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    payload = run_evaluator_handoff(
        freeze_receipt_path=args.freeze_receipt,
        candidate_bundle_path=args.candidate_bundle,
        output_path=args.output,
    )
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "EVALUATOR_HANDOFF_SCHEMA",
    "EvaluatorHandoffError",
    "main",
    "run_evaluator_handoff",
]
