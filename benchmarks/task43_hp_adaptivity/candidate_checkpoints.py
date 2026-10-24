"""Atomic, pre-validation field checkpoints for Task43 candidate runs."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import numpy as np


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _array_identity(values: np.ndarray) -> dict[str, Any]:
    array = np.ascontiguousarray(values)
    if array.dtype.hasobject:
        raise TypeError("pre-validation checkpoint arrays must not use pickle")
    digest = hashlib.sha256()
    digest.update(array.dtype.str.encode("ascii"))
    digest.update(json.dumps(list(array.shape)).encode("ascii"))
    digest.update(array.view(np.uint8))
    return {
        "dtype": array.dtype.str,
        "shape": list(array.shape),
        "sha256": digest.hexdigest(),
    }


def _replace_atomically(path: Path, writer) -> None:
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with temporary.open("xb") as stream:
            writer(stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _json_safe(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, np.ndarray):
        return {
            "array_omitted": True,
            **_array_identity(value),
            "finite": bool(
                np.isfinite(value).all()
                if np.issubdtype(value.dtype, np.number)
                else True
            ),
        }
    if isinstance(value, np.generic):
        return _json_safe(value.item())
    if isinstance(value, complex):
        return [float(value.real), float(value.imag)]
    if isinstance(value, Path):
        return str(value)
    return value


def _json_bytes(value: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(_json_safe(value), indent=2, sort_keys=True, allow_nan=False) + "\n"
    ).encode("utf-8")


def write_atomic_npz(
    path: Path,
    arrays: Mapping[str, np.ndarray],
    *,
    identity: Mapping[str, Any],
    schema: str,
    classification: str,
) -> dict[str, Any]:
    """Atomically persist an immutable, hash-bound NPZ evidence packet."""

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise FileExistsError(f"refusing to overwrite evidence packet {path}")
    arrays_copy = {str(name): np.asarray(value) for name, value in arrays.items()}
    if not arrays_copy or "__task43_record_json__" in arrays_copy:
        raise ValueError("evidence packet requires arrays and a reserved record key")
    if any(value.dtype.hasobject for value in arrays_copy.values()):
        raise TypeError("evidence packet arrays must not use pickle")
    array_identities = {
        name: _array_identity(values) for name, values in arrays_copy.items()
    }
    record = {
        "schema": str(schema),
        "classification": str(classification),
        "official_result": False,
        "passed": False,
        "selection_eligible": False,
        "selection_candidate": False,
        "candidate_selected": False,
        "continuation_all_false": True,
        "continuation": {
            "same_group_R": False,
            "A1_R": False,
            "A2_q": False,
            "A2_R": False,
            "A2_q3": False,
            "B": False,
            "C": False,
            "cost_campaign": False,
            "iteration": False,
        },
        "arrays": array_identities,
        # Return exactly the JSON-safe representation that is embedded in the
        # NPZ record.  In particular, callers may pass nested MappingProxyType
        # diagnostics from the live observer; a shallow dict would still fail
        # when the packet record is sent through MPI.
        "identity": _json_safe(dict(identity)),
    }
    arrays_copy["__task43_record_json__"] = np.frombuffer(
        _json_bytes(record), dtype=np.uint8
    ).copy()

    def write_npz(stream) -> None:
        np.savez_compressed(stream, **arrays_copy)

    _replace_atomically(path, write_npz)
    return {
        **record,
        "npz_path": str(path),
        "npz_sha256": _sha256_file(path),
    }


def write_atomic_json(
    path: Path,
    record: Mapping[str, Any],
    *,
    refuse_overwrite: bool = True,
) -> dict[str, Any]:
    """Atomically save one small terminal or sample-sidecar record."""

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if refuse_overwrite and path.exists():
        raise FileExistsError(f"refusing to overwrite evidence record {path}")
    payload = _json_bytes(record)

    def write_json(stream) -> None:
        stream.write(payload)

    _replace_atomically(path, write_json)
    return {"path": str(path), "sha256": _sha256_file(path)}


def write_atomic_bytes(
    path: Path,
    payload: bytes,
    *,
    refuse_overwrite: bool = True,
) -> dict[str, Any]:
    """Atomically preserve exact bytes when a later record needs demotion."""

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if refuse_overwrite and path.exists():
        raise FileExistsError(f"refusing to overwrite evidence bytes {path}")
    value = bytes(payload)
    _replace_atomically(path, lambda stream: stream.write(value))
    return {
        "path": str(path),
        "sha256": _sha256_file(path),
        "bytes": len(value),
    }


def write_v3_primary_field_sample(
    path: Path,
    order: int,
    sample: Mapping[str, np.ndarray],
    *,
    identity: Mapping[str, Any],
    sample_records: dict[str, Any],
) -> dict[str, Any]:
    """Persist one completed V3 primary sample before starting another order."""

    record = write_atomic_npz(
        path,
        {str(name): np.asarray(value) for name, value in sample.items()},
        schema="task43.v3.a1_primary_field_sample.v1",
        classification="measured_primary_sample_before_extra_correction_not_official",
        identity={**dict(identity), "quadrature_order": int(order)},
    )
    sample_records[f"q{int(order)}"] = record
    return record


def write_v3_primary_before_extra_packet(
    path: Path,
    arrays: Mapping[str, np.ndarray],
    *,
    identity: Mapping[str, Any],
) -> dict[str, Any]:
    """Persist the exact pre-extra state with a fixed V3 fail-closed schema."""

    return write_atomic_npz(
        path,
        arrays,
        schema="task43.v3.a1_primary_before_extra.v1",
        classification="measured_primary_state_before_extra_not_official",
        identity=identity,
    )


def write_v3_extra_before_output_packet(
    path: Path,
    arrays: Mapping[str, np.ndarray],
    *,
    identity: Mapping[str, Any],
) -> dict[str, Any]:
    """Persist extra raw vectors before physical output recovery or sampling."""

    return write_atomic_npz(
        path,
        arrays,
        schema="task43.v3.a2_extra_before_physical_output.v1",
        classification=(
            "measured_extra_state_after_A6_before_physical_output_not_official"
        ),
        identity=identity,
    )


def task43_v3_partial_terminal_record(
    *,
    phase: str | None,
    source_identity: Mapping[str, Any],
    error: str,
    primary_before_extra_packet: Mapping[str, Any] | None,
    primary_q_samples: Mapping[str, Any],
    primary_q8_q10_bundle: Mapping[str, Any] | None,
    pre_validation_checkpoint: Mapping[str, Any] | None,
    native_run_summary: Mapping[str, Any] | None = None,
    extra_q_samples: Mapping[str, Any] | None = None,
    extra_before_output_packet: Mapping[str, Any] | None = None,
    comparison_failure_reference: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build fail-closed status for a V3 endpoint stopped after partial work."""

    return {
        "schema": "task43.v3.partial-terminal.v1",
        "phase": phase,
        "status": "FAILED" if primary_before_extra_packet else "INCOMPLETE",
        "classification": "measured_or_partial_nonofficial_endpoint",
        "error": str(error),
        "source_identity": dict(source_identity),
        "primary_before_extra_packet": primary_before_extra_packet,
        "extra_before_output_packet": extra_before_output_packet,
        "primary_q_samples": dict(primary_q_samples),
        "extra_q_samples": dict(extra_q_samples or {}),
        "primary_q8_q10_bundle": primary_q8_q10_bundle,
        "pre_validation_checkpoint": pre_validation_checkpoint,
        "native_run_summary_authority": native_run_summary,
        "comparison_failure_reference": (
            dict(comparison_failure_reference)
            if comparison_failure_reference is not None
            else None
        ),
        "port_output_scope": (
            "solver-written modal outputs are measurements only; this terminal "
            "record is authoritative and the endpoint is not official"
        ),
        "native_port_payloads_official_without_validated_endpoint": False,
        "official_result": False,
        "passed": False,
        "selection_eligible": False,
        "selection_candidate": False,
        "candidate_selected": False,
        "continuation_all_false": True,
        "continuation": {
            "same_group_R": False,
            "A1_R": False,
            "A2_q": False,
            "A2_R": False,
            "A2_q3": False,
            "B": False,
            "C": False,
            "cost_campaign": False,
            "iteration": False,
        },
    }


def demote_v3_native_summary_after_error(
    summary: dict[str, Any],
    terminal_path: Path,
    *,
    phase: str,
    source_identity: Mapping[str, Any],
    error: BaseException | str,
    primary_before_extra_packet: Mapping[str, Any] | None,
    primary_q_samples: Mapping[str, Any],
    extra_q_samples: Mapping[str, Any] | None = None,
    extra_before_output_packet: Mapping[str, Any] | None = None,
    pre_validation_checkpoint: Mapping[str, Any] | None = None,
    comparison_failure_reference: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Demote native solver outputs if V3 postprocessing or comparison fails."""

    prior_status = summary.get("status")
    prior_passed = summary.get("passed")
    reported_result = summary.pop("official_result", None)
    summary["legacy_solver_reported_result_not_authoritative"] = reported_result
    summary["official_result"] = False
    summary["passed"] = False
    summary["status"] = "FAILED" if primary_before_extra_packet else "INCOMPLETE"
    summary["result_classification"] = "TASK43_V3_MEASURED_OR_PARTIAL_NONOFFICIAL"
    summary["authority"] = "DIAGNOSTIC_ONLY_PARTIAL_NONOFFICIAL"
    summary["selection_eligible"] = False
    summary["selection_candidate"] = False
    summary["candidate_selected"] = False
    summary["continuation_all_false"] = True
    summary["continuation"] = {
        "same_group_R": False,
        "A1_R": False,
        "A2_q": False,
        "A2_R": False,
        "A2_q3": False,
        "B": False,
        "C": False,
        "cost_campaign": False,
        "iteration": False,
    }
    if isinstance(reported_result, Mapping):
        summary["measured_endpoint_output_not_official"] = reported_result
    if comparison_failure_reference is not None:
        summary["task43_v3_comparison_failure_reference"] = dict(
            comparison_failure_reference
        )
    summary["task43_v3_endpoint_authority"] = {
        "official_result": False,
        "passed": False,
        "status": summary["status"],
        "continuation_all_false": True,
    }
    terminal = task43_v3_partial_terminal_record(
        phase=phase,
        source_identity=source_identity,
        error=str(error),
        primary_before_extra_packet=primary_before_extra_packet,
        primary_q_samples=primary_q_samples,
        extra_q_samples=extra_q_samples,
        primary_q8_q10_bundle=None,
        pre_validation_checkpoint=pre_validation_checkpoint,
        native_run_summary={
            "prior_status": prior_status,
            "prior_passed": prior_passed,
            "solver_reported_official_result_was_present": (
                reported_result is not None
            ),
        },
        extra_before_output_packet=extra_before_output_packet,
        comparison_failure_reference=comparison_failure_reference,
    )
    terminal_ref = write_atomic_json(terminal_path, terminal)
    summary["task43_v3_partial_terminal"] = terminal_ref
    return terminal_ref


def write_pre_validation_checkpoint(
    path: Path,
    arrays: Mapping[str, np.ndarray],
    *,
    identity: Mapping[str, Any],
) -> dict[str, Any]:
    """Atomically save serial recovered state before expensive observer work.

    This checkpoint is diagnostic recovery material only. It does not mean the
    solver, independent active residual, or Task43 official-result gates passed.
    The NPZ is renamed into place before its hash-bound JSON sidecar is written.
    """

    path = Path(path)
    sidecar = path.with_suffix(".json")
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() or sidecar.exists():
        raise FileExistsError(f"refusing to overwrite checkpoint {path}")

    arrays_copy = {str(name): np.asarray(value) for name, value in arrays.items()}
    if not arrays_copy:
        raise ValueError("pre-validation checkpoint cannot be empty")
    array_identities = {
        name: _array_identity(values) for name, values in arrays_copy.items()
    }

    def write_npz(stream) -> None:
        np.savez_compressed(stream, **arrays_copy)

    _replace_atomically(path, write_npz)
    record = {
        "schema": "task43.pre-validation-field-checkpoint.v1",
        "status": "written_before_field_capture_and_independent_A6",
        "classification": "pre_validation_diagnostic_not_official",
        "official_result": False,
        "independent_A6": "not_run_at_checkpoint_time",
        "field_capture": "not_run_at_checkpoint_time",
        "mpi_size": 1,
        "npz_path": str(path),
        "npz_sha256": _sha256_file(path),
        "arrays": array_identities,
        "identity": dict(identity),
    }

    def write_json(stream) -> None:
        stream.write(
            (
                json.dumps(record, indent=2, sort_keys=True, allow_nan=False) + "\n"
            ).encode("utf-8")
        )

    _replace_atomically(sidecar, write_json)
    return {
        **record,
        "sidecar_path": str(sidecar),
        "sidecar_sha256": _sha256_file(sidecar),
    }
