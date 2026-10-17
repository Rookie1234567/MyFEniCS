"""Continue Task41 P0 post-processing from an immutable saved A2 solution."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
from typing import Any, Mapping

import numpy as np


CONTINUATION_SCHEMA = "task41.p0.saved_output_continuation.v1"
CONTINUATION_RECEIPT = "task41_p0_saved_output_continuation_receipt.json"
CONTINUATION_CHECKER_INPUT = "task41_p0_saved_output_checker_input.json"
CONTINUATION_CHECKER_RECEIPT = "task41_p0_saved_output_checker_result.json"
_A6_LIMIT = 1.0e-6
_A6_ARRAYS = (
    "full_physical_rhs_storage",
    "full_solution_storage",
    "target_backend_applied_storage",
    "target_backend_residual_storage",
    "native_witness_applied_storage",
    "native_witness_residual_storage",
)
_KNOWN_WORKER_ERROR = "Task41 A1 full field representation failed the saved E/H sample witness"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_object(path: Path, label: str) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return value


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _array_from_packet(record: Mapping[str, Any], arrays: Any, name: str) -> np.ndarray:
    descriptor = record.get(name)
    if not isinstance(descriptor, Mapping):
        raise ValueError(f"saved A6 packet omits {name}")
    key = descriptor.get("array_key")
    if not isinstance(key, str) or key not in arrays.files:
        raise ValueError(f"saved A6 packet array {name} is missing")
    value = np.asarray(arrays[key])
    if list(value.shape) != descriptor.get("shape") or str(value.dtype) != descriptor.get("dtype"):
        raise ValueError(f"saved A6 packet array {name} identity changed")
    if value.dtype != np.dtype(np.complex128) or value.ndim != 1 or not np.isfinite(value).all():
        raise ValueError(f"saved A6 packet array {name} is not a finite complex128 vector")
    return value


def validate_saved_a6_packet(
    packet_json: Path,
    *,
    run_root: Path,
    expected_source_sha: str,
    expected_input_sha256: str,
    expected_physical_model_sha256: str,
) -> tuple[np.ndarray, dict[str, Any]]:
    """Recompute both saved A6 residuals and bind the packet to the failed run."""
    run_root = run_root.resolve(strict=True)
    packet_json = packet_json.resolve(strict=True)
    if not packet_json.is_relative_to(run_root):
        raise ValueError("saved A6 packet escaped its original run directory")
    record = _json_object(packet_json, "saved A6 packet")
    arrays_record = record.get("arrays")
    if not isinstance(arrays_record, Mapping):
        raise ValueError("saved A6 packet omits its NPZ manifest")
    npz_path = Path(str(arrays_record.get("path", ""))).resolve(strict=True)
    if (
        not npz_path.is_relative_to(run_root)
        or _sha256(npz_path) != arrays_record.get("sha256")
        or record.get("schema") not in {
            "task40extra.review_v10_b0_candidate_independent_A6_residual.v1",
            "task40extra.review_v10_b0_candidate_post_release_A6_residual.v1",
        }
        or float(record.get("limit", -1.0)) != _A6_LIMIT
    ):
        raise ValueError("saved A6 packet schema, path, hash, or residual limit is invalid")
    identity = record.get("identity")
    if not isinstance(identity, Mapping) or any(
        identity.get(key) != expected
        for key, expected in (
            ("source_sha", expected_source_sha),
            ("input_sha256", expected_input_sha256),
            ("physical_model_sha256", expected_physical_model_sha256),
        )
    ):
        raise ValueError("saved A6 packet identity differs from the original A2 run")

    with np.load(npz_path, allow_pickle=False) as arrays:
        vectors = {name: _array_from_packet(record, arrays, name).copy() for name in _A6_ARRAYS}
    rhs = vectors["full_physical_rhs_storage"]
    solution = vectors["full_solution_storage"]
    if any(value.shape != rhs.shape for value in vectors.values()):
        raise ValueError("saved A6 packet vectors have inconsistent full-space layouts")
    rhs_norm = float(np.linalg.norm(rhs))
    if not np.isfinite(rhs_norm) or rhs_norm <= np.finfo(float).tiny:
        raise ValueError("saved A6 physical RHS has an invalid norm")
    checks = []
    for backend, applied_key, residual_key, relative_key in (
        (
            "sum_factorized_target_backend",
            "target_backend_applied_storage",
            "target_backend_residual_storage",
            "relative_residual",
        ),
        (
            "native_full_A6_witness",
            "native_witness_applied_storage",
            "native_witness_residual_storage",
            "native_witness_relative_residual",
        ),
    ):
        applied = vectors[applied_key]
        saved_residual = vectors[residual_key]
        recomputed = rhs - applied
        relative = float(np.linalg.norm(recomputed) / rhs_norm)
        algebra_defect = float(
            np.linalg.norm(recomputed - saved_residual)
            / max(rhs_norm + float(np.linalg.norm(saved_residual)), np.finfo(float).tiny)
        )
        stored = float(record.get(relative_key, np.inf))
        checks.append(
            {
                "backend": backend,
                "relative_residual": relative,
                "stored_relative_residual": stored,
                "residual_algebra_defect_relative": algebra_defect,
                "passed": bool(
                    np.isfinite(relative)
                    and relative <= _A6_LIMIT
                    and abs(relative - stored) <= 1.0e-12
                    and algebra_defect <= 1.0e-12
                ),
            }
        )
    if not all(row["passed"] for row in checks):
        raise ValueError("saved pre/post-release A6 packet does not independently pass")
    return solution, {
        "packet_json": str(packet_json),
        "packet_json_sha256": _sha256(packet_json),
        "packet_npz": str(npz_path),
        "packet_npz_sha256": str(arrays_record["sha256"]),
        "solution_storage_sha256": hashlib.sha256(
            np.ascontiguousarray(solution).view(np.uint8)
        ).hexdigest(),
        "residual_checks": checks,
    }


def _validate_original_attempt(
    run_root: Path,
    contract: Mapping[str, Any],
    expected_contract_sha256: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any], Path, dict[str, Any]]:
    run_root = run_root.resolve(strict=True)
    worker_path = run_root / "task40_v10_p6_candidate_summary.json"
    run_summary_path = run_root / "run_summary.json"
    manifest_path = run_root / "run_manifest.json"
    worker = _json_object(worker_path, "original A2 worker summary")
    run_summary = _json_object(run_summary_path, "original A2 run summary")
    manifest = _json_object(manifest_path, "original A2 run manifest")
    case = contract["case"]
    if (
        worker.get("status") != "FAILED"
        or worker.get("result_classification") != "WORKER_FAILED"
        or worker.get("official_result") is not False
        or worker.get("error", {}).get("type") != "ValueError"
        or worker.get("error", {}).get("message") != _KNOWN_WORKER_ERROR
        or worker.get("numeric_gates_passed") is not True
        or "output_packet" in worker
        or run_summary.get("status") != "finished"
        or run_summary.get("exit_status") != 4
        or run_summary.get("result_classification") != "WORKER_FAILED"
        or manifest.get("result_classification") != "WORKER_FAILED"
        or worker.get("source_sha") != contract["source"]["sha"]
        or manifest.get("source_sha") != contract["source"]["sha"]
        or worker.get("run_id") != case["run_id"]
        or manifest.get("run_id") != case["run_id"]
        or worker.get("profile") != "task41extra_g13_p6_phi90_a2_y_orbit_reference_v1"
        or worker.get("stage") != "TASK41_A2"
        or worker.get("q_assembly_strategy") != "ROW_TILE_BOUNDED_CSR_V17"
        or run_summary.get("numerical_output_directory")
        != str((run_root / "numerical_output").resolve())
    ):
        raise ValueError("original A2 run is not the preserved postprocessing-only failure")
    authority = worker.get("campaign_authority")
    if (
        not isinstance(authority, Mapping)
        or not isinstance(authority.get("task41_contract_sha256"), str)
        or (
            expected_contract_sha256 is not None
            and authority.get("task41_contract_sha256") != expected_contract_sha256
        )
        or authority.get("campaign_window_sha256") != contract["window"]["sha256"]
        or authority.get("a1_comparison_binding_sha256")
        != contract["comparison"]["a1_binding_sha256"]
    ):
        raise ValueError("original A2 campaign authority differs from the frozen Task41 contract")
    numerical_output = (run_root / "numerical_output").resolve(strict=True)
    if not numerical_output.is_dir():
        raise ValueError("original A2 numerical output directory is missing")
    return worker, run_summary, manifest_path, {
        "worker_summary": {"path": str(worker_path), "sha256": _sha256(worker_path)},
        "run_summary": {"path": str(run_summary_path), "sha256": _sha256(run_summary_path)},
        "run_manifest": {"path": str(manifest_path), "sha256": _sha256(manifest_path)},
        "numerical_output_path": str(numerical_output),
    }


def _link_saved_output(source: Path, destination: Path) -> list[dict[str, Any]]:
    if not source.is_dir() or source.is_symlink():
        raise ValueError("original A2 numerical output is not a regular directory")
    destination.mkdir(parents=True, exist_ok=False)
    manifest = []
    for original in sorted(source.iterdir()):
        if original.is_symlink() or not original.is_file():
            raise ValueError("original A2 numerical output contains a non-regular entry")
        target = destination / original.name
        os.link(original, target)
        manifest.append(
            {
                "name": original.name,
                "source_path": str(original.resolve()),
                "path": str(target.resolve()),
                "size_bytes": int(target.stat().st_size),
                "sha256": _sha256(target),
                "same_inode": original.stat().st_ino == target.stat().st_ino,
            }
        )
        if manifest[-1]["sha256"] != _sha256(original) or not manifest[-1]["same_inode"]:
            raise ValueError("saved output hard-link identity did not preserve the source artifact")
    if not manifest:
        raise ValueError("original A2 numerical output is empty")
    return manifest


def _verify_linked_output_manifest(
    producer: Mapping[str, Any], consumer: Mapping[str, Any]
) -> dict[str, Any]:
    source = Path(str(producer.get("numerical_output_path", ""))).resolve(strict=True)
    destination = Path(str(consumer.get("numerical_output_directory", ""))).resolve(strict=True)
    records = consumer.get("numerical_output_manifest")
    errors: list[str] = []
    if not isinstance(records, list) or not records:
        return {"passed": False, "errors": ["saved output copy manifest is missing"]}
    if source == destination or source.is_relative_to(destination) or destination.is_relative_to(source):
        errors.append("producer and consumer numerical-output directories overlap")
    source_names = sorted(path.name for path in source.iterdir())
    destination_names = sorted(path.name for path in destination.iterdir())
    record_names = sorted(str(row.get("name", "")) for row in records if isinstance(row, Mapping))
    if source_names != destination_names or record_names != source_names:
        errors.append("consumer output directory differs from the complete saved producer inventory")
    for row in records:
        if not isinstance(row, Mapping):
            errors.append("saved output manifest contains a non-object entry")
            continue
        name = str(row.get("name", ""))
        source_path = Path(str(row.get("source_path", "")))
        destination_path = Path(str(row.get("path", "")))
        if (
            not name
            or Path(name).name != name
            or source_path.resolve() != source / name
            or destination_path.resolve() != destination / name
        ):
            errors.append(f"saved output manifest path escapes its expected directory: {name!r}")
            continue
        source_file = source / name
        destination_file = destination / name
        if (
            source_file.is_symlink()
            or destination_file.is_symlink()
            or not source_file.is_file()
            or not destination_file.is_file()
        ):
            errors.append(f"saved output is no longer a regular file: {name}")
            continue
        source_stat = source_file.stat()
        destination_stat = destination_file.stat()
        expected_sha = str(row.get("sha256", ""))
        actual_source_sha = _sha256(source_file)
        actual_destination_sha = _sha256(destination_file)
        if (
            source_stat.st_size != row.get("size_bytes")
            or destination_stat.st_size != row.get("size_bytes")
            or actual_source_sha != expected_sha
            or actual_destination_sha != expected_sha
            or (source_stat.st_dev, source_stat.st_ino)
            != (destination_stat.st_dev, destination_stat.st_ino)
            or row.get("same_inode") is not True
        ):
            errors.append(f"saved producer bytes changed or continuation link is not read-only: {name}")
    return {
        "passed": not errors,
        "source_file_count": len(source_names),
        "consumer_file_count": len(destination_names),
        "errors": errors,
    }


def task41_diagnostic_diffraction_inventory(
    metrics: Mapping[str, Any],
    orders: Any,
    *,
    expected_m_max: int,
    expected_n_max: int,
) -> dict[str, Any]:
    """Recheck output orders against the frozen reporting bounds, not row count alone."""
    rows = orders if isinstance(orders, list) else []
    m_max = metrics.get("diffraction_order_max_m_resolved")
    n_max = metrics.get("diffraction_order_max_n_resolved")
    requested_m = metrics.get("diffraction_order_max_m_requested")
    requested_n = metrics.get("diffraction_order_max_n_requested")
    valid_bounds = (
        type(expected_m_max) is int
        and expected_m_max >= 0
        and type(expected_n_max) is int
        and expected_n_max >= 0
    )
    expected_keys: set[tuple[int, int, str]] = set()
    if valid_bounds:
        expected_keys = {
            (m, n, polarization)
            for m in range(-expected_m_max, expected_m_max + 1)
            for n in range(-expected_n_max, expected_n_max + 1)
            for polarization in ("s", "p")
        }
    actual_keys = []
    malformed_rows = 0
    for row in rows:
        if (
            not isinstance(row, Mapping)
            or type(row.get("m")) is not int
            or type(row.get("n")) is not int
            or row.get("polarization") not in {"s", "p"}
        ):
            malformed_rows += 1
            continue
        actual_keys.append((int(row["m"]), int(row["n"]), str(row["polarization"])))
    order_count = (
        (2 * expected_m_max + 1) * (2 * expected_n_max + 1)
        if valid_bounds
        else 0
    )
    channel_count = 2 * order_count
    checks = {
        "requested_bounds_cover_resolved_bounds": bool(
            valid_bounds
            and requested_m == expected_m_max
            and requested_n == expected_n_max
            and m_max == expected_m_max
            and n_max == expected_n_max
        ),
    "order_row_count_matches_grid": len(rows) == channel_count,
        "channel_count_matches_two_polarizations": (
            metrics.get("diffraction_channel_count") == channel_count
        ),
        "spatial_order_count_matches_grid": (
            metrics.get("diffraction_order_count") == order_count
            and metrics.get("diffraction_fit_order_count") == order_count
        ),
        "all_order_polarization_keys_are_unique_and_complete": (
            malformed_rows == 0
            and len(actual_keys) == len(set(actual_keys))
            and set(actual_keys) == expected_keys
        ),
    }
    return {
        "schema": "task41.p0.diagnostic_diffraction_inventory.v1",
        "frozen_reporting_order_bounds": {
            "m_max": expected_m_max,
            "n_max": expected_n_max,
        },
        "expected_spatial_order_count": order_count,
        "expected_channel_count": channel_count,
        "actual_order_rows": len(rows),
        "malformed_order_rows": malformed_rows,
        "checks": checks,
        "passed": all(checks.values()),
        "inventory_scope": "full frozen diagnostic order grid with s/p polarization; official DtN port-table identity is independently checked",
    }


def _source_identity(repo_root: Path) -> tuple[str, str]:
    def git(*arguments: str) -> str:
        result = subprocess.run(
            ["git", *arguments], cwd=repo_root, check=True, capture_output=True, text=True
        )
        return result.stdout.strip()

    return git("rev-parse", "HEAD"), git("branch", "--show-current")


def _require_service_envelope(
    contract: Mapping[str, Any], contract_path: Path, digest: str, repo_root: Path
) -> None:
    contract_path = contract_path.resolve() if contract_path.is_absolute() else (repo_root / contract_path).resolve()
    raw_window = Path(str(contract["window"]["path"]))
    window_path = raw_window.resolve() if raw_window.is_absolute() else (repo_root / raw_window).resolve()
    expected_environment = {
        "TASK41_P0_STRICT_EXECUTION": "1",
        "TASK41_P0_CONTRACT_PATH": str(contract_path),
        "TASK41_P0_CONTRACT_SHA256": digest,
        "TASK41_P0_EXECUTION_WINDOW_PATH": str(window_path),
        "TASK41_P0_EXECUTION_WINDOW_SHA256": str(contract["window"]["sha256"]),
        "TASK41_P0_MEMORY_SWAP_MAX_BYTES": "0",
    }
    if any(os.environ.get(key) != value for key, value in expected_environment.items()):
        raise RuntimeError("saved-output continuation lacks the frozen Task41 service envelope")
    source_sha, branch = _source_identity(repo_root)
    if (
        os.environ.get("TASK41_P0_SAVED_OUTPUT_CONTINUATION") != "1"
        or os.environ.get("TASK41_P0_CONSUMER_SOURCE_SHA") != source_sha
        or os.environ.get("TASK41_P0_EXPECTED_SOURCE_SHA") != contract["source"]["sha"]
        or os.environ.get("_MYFENICS_CLOUD_ABI_MANIFEST_SHA256")
        != contract["runtime"]["abi_receipt_sha256"]
        or branch != contract["branch"]
        or source_sha == contract["source"]["sha"]
    ):
        raise RuntimeError("saved-output continuation producer and consumer source identities are not distinct and bound")
    for key, expected in (
        ("TASK41_P0_TASK_MEMORY_MAX_BYTES", contract["resources"]["task_memory_max_bytes"]),
        ("TASK41_P0_HOST_RESERVE_BYTES", contract["resources"]["host_reserve_bytes"]),
    ):
        if int(os.environ.get(key, "-1")) != int(expected):
            raise RuntimeError(f"saved-output continuation {key} differs from the contract")
    parent = int(os.environ.get("PHYSICAL_WATCHDOG_PARENT_PID", "-1"))
    if parent <= 0 or parent == os.getpid() or not Path(f"/proc/{parent}").is_dir():
        raise RuntimeError("saved-output continuation requires its dedicated subreaper watchdog")
    from benchmarks.subreaper_watchdog import cgroup_snapshot

    cgroup = cgroup_snapshot(os.getpid())
    if (
        cgroup.get("dedicated_job_cgroup") is not True
        or cgroup.get("readable") is not True
        or cgroup.get("memory_limit_bytes") != contract["resources"]["task_memory_max_bytes"]
        or cgroup.get("swap_current_bytes") != 0
    ):
        raise RuntimeError("saved-output continuation cgroup differs from Task41 memory/zero-swap gates")


class _SavedOutputRuntime:
    """Small event/resource adapter for the existing comparison and packet writer."""

    def __init__(self, directory: Path, contract: Mapping[str, Any]) -> None:
        self.directory = directory
        self.parent_pid = int(os.environ["PHYSICAL_WATCHDOG_PARENT_PID"])
        self.task_cap = int(contract["resources"]["task_memory_max_bytes"])
        self.host_reserve = int(contract["resources"]["host_reserve_bytes"])
        self.stage = "TASK41_A2_SAVED_OUTPUT_CONTINUATION"
        self.phase = "preflight"
        self.events = directory / "task41_p0_saved_output_events.jsonl"
        self.workspace_live_bytes = 0
        self.workspace_reservations: dict[str, int] = {}

    def marker(self, name: str, facts: Mapping[str, Any] | None = None) -> None:
        from benchmarks.task038_full3d_jit_staging import append_jsonl

        append_jsonl(
            self.events,
            {
                "event": name,
                "stage": self.stage,
                "timestamp_ns": time.time_ns(),
                "facts": {} if facts is None else dict(facts),
            },
        )

    def sample(self, label: str | None = None, *, enforce: bool = True) -> dict[str, Any]:
        from benchmarks.task038_full3d_jit_staging import process_tree_snapshot

        facts = process_tree_snapshot(self.parent_pid, self.phase, None)
        if (
            facts.get("all_status_readable") is not True
            or facts.get("identity_complete") is not True
            or not isinstance(facts.get("rss_bytes"), int)
            or facts.get("swap_bytes") != 0
            or facts["rss_bytes"] >= self.task_cap
        ):
            raise RuntimeError("saved-output continuation resource sample failed Task41 gates")
        facts = {**facts, "label": label, "task_memory_cap_bytes": self.task_cap}
        self.marker("task41_saved_output_resource_sample", facts)
        return facts

    def check_projected(
        self,
        label: str,
        amount: int,
        *,
        workspace_bytes: int = 0,
        future_bytes: int = 0,
    ) -> dict[str, Any]:
        from benchmarks.subreaper_watchdog import (
            PHYSICAL_MEMORY_PRESSURE_POLICY,
            memory_envelope,
        )

        sample = self.sample(f"{label}_projected")
        envelope = memory_envelope(
            PHYSICAL_MEMORY_PRESSURE_POLICY,
            host_reserve_bytes=self.host_reserve,
            task_cgroup_reserve_bytes=0,
            require_cgroup_memory_details=True,
        )
        headroom = int(
            envelope["effective_available_after_reserves_bytes"]
            if envelope.get("reserve_domains_separated") is True
            else envelope["effective_available_bytes"] - envelope["reserve_bytes"]
        )
        amounts = (int(amount), int(workspace_bytes), int(future_bytes))
        if any(value < 0 for value in amounts):
            raise ValueError("saved-output continuation allocation estimates cannot be negative")
        increment = sum(amounts)
        projected = int(sample["rss_bytes"]) + increment
        result = {
            "label": label,
            "rss_bytes": int(sample["rss_bytes"]),
            "projected_rss_bytes": projected,
            "task_memory_cap_bytes": self.task_cap,
            "incremental_headroom_bytes": headroom,
            "projected_increment_bytes": increment,
            "declared_future_co_resident_bytes": int(future_bytes),
            "passed": bool(projected < self.task_cap and increment <= headroom),
        }
        self.marker("task41_saved_output_allocation_gate", result)
        if not result["passed"]:
            raise RuntimeError(f"saved-output continuation projected allocation exceeds Task41 gate: {label}")
        return result

    def reserve_workspace(self, label: str, size: int) -> None:
        self.check_projected(label, int(size))
        if label in self.workspace_reservations:
            raise RuntimeError(f"saved-output workspace label was reserved twice: {label}")
        self.workspace_reservations[label] = int(size)
        self.workspace_live_bytes += int(size)

    def release_workspace(self, label: str) -> None:
        reserved = self.workspace_reservations.pop(label, None)
        if reserved is None or self.workspace_live_bytes < reserved:
            raise RuntimeError(f"saved-output packet workspace accounting underflow: {label}")
        self.workspace_live_bytes -= reserved


def _load_saved_output(
    run_root: Path, numerical_output: Path, cfg: Any
) -> dict[str, Any]:
    port = _json_object(numerical_output / "dtn_port_power_metrics_3d.json", "A2 port metrics")
    volume = _json_object(numerical_output / "volume_absorption.json", "A2 volume metrics")
    diffraction = _json_object(
        numerical_output / "diffraction_orders_3d.json", "A2 diffraction metrics"
    )
    with np.load(numerical_output / "dtn_port_modal_amplitudes_3d.npz", allow_pickle=False) as modal:
        required = {"solver_auxiliary_amplitude_total_projection", "physical_boundary_outgoing_amplitude"}
        if not required.issubset(modal.files):
            raise ValueError("saved A2 modal archive omits the full port inventory")
        auxiliary = np.asarray(modal["solver_auxiliary_amplitude_total_projection"], dtype=np.complex128).copy()
        modal_finite = all(
            np.isfinite(np.asarray(modal[key])).all()
            for key in ("solver_auxiliary_amplitude_total_projection", "physical_boundary_outgoing_amplitude")
        )
    with np.load(numerical_output / "airbox_fields_3d_scientific.npz", allow_pickle=False) as fields:
        required_fields = {"E_total_code", "H_curl_A_per_m", "coordinates_nm", "vtk_cells", "cell_domain_tags"}
        if not required_fields.issubset(fields.files):
            raise ValueError("saved A2 scientific field archive is incomplete")
        fields_finite = all(
            np.isfinite(np.asarray(fields[key])).all()
            for key in ("E_total_code", "H_curl_A_per_m")
        )
    metrics = diffraction.get("metrics")
    if not isinstance(metrics, Mapping) or type(metrics.get("diffraction_channel_count")) is not int:
        raise ValueError("saved A2 diffraction output omits its spatial/polarization channel count")
    inventory = task41_diagnostic_diffraction_inventory(
        metrics,
        diffraction.get("orders"),
        expected_m_max=cfg.reporting_diffraction_order_max_m,
        expected_n_max=cfg.reporting_diffraction_order_max_n,
    )
    return {
        "port_metrics": port,
        "volume_metrics": volume,
        "diffraction_metrics": dict(metrics),
        "diffraction_channel_count": int(metrics["diffraction_channel_count"]),
        "diagnostic_diffraction_inventory": inventory,
        "electric_finite": bool(fields_finite),
        "auxiliary_finite": bool(modal_finite and np.isfinite(auxiliary).all()),
        "auxiliary": auxiliary,
        "field_export": {"preserved_source_run": str(run_root)},
    }


def _make_output_packet(
    *,
    runtime: _SavedOutputRuntime,
    producer_summary: Mapping[str, Any],
    producer_identity: Mapping[str, Any],
    consumer_source_sha: str,
    post_release_record: Mapping[str, Any],
    full_solution: np.ndarray,
    post_release_path: Path,
    numerical_output: Path,
    output: Mapping[str, Any],
    comparison: Mapping[str, Any],
    output_pass: bool,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    from src.runners.task40_v10_worker import _file_manifest, _hash_arrays, _save_packet

    port = output["port_metrics"]
    volume = output["volume_metrics"]
    power = {
        "R": float(port["R_total"]),
        "T": float(port["T_total"]),
        "A": float(port["A_balance"]),
        "A_volume": float(volume["A_volume_total"]),
    }
    energy_error = abs(power["R"] + power["T"] + power["A_volume"] - 1.0)
    absorption_error = abs(power["A"] - power["A_volume"])
    files = _file_manifest(numerical_output)
    producer_sha = str(producer_summary["source_sha"])
    summary_identity = {
        **dict(producer_identity),
        "continuation_consumer_source_sha": consumer_source_sha,
    }
    mode_identity = producer_identity["mode_and_carrier_identity"]
    scientific_identity = {
        "schema": "task40extra.review_v10_scientific_output_identity.v1",
        "source_sha": producer_sha,
        "consumer_source_sha": consumer_source_sha,
        "input_sha256": producer_identity["input_sha256"],
        "physical_model_sha256": producer_identity["physical_model_sha256"],
        "ordered_physical_mode_sha256": producer_identity["target_ordered_mode_sha256"],
        "carrier_assembly_manifest_sha256": mode_identity["target_carrier_assembly_manifest_sha256"],
        "carrier_payload_rows_values_sha256": mode_identity["target_carrier_payload_sha256"],
        "full_solution_storage_sha256": _hash_arrays(
            {"full_solution_storage": np.asarray(full_solution, dtype=np.complex128)}
        ),
        "modal_amplitudes_sha256": _hash_arrays(
            {"modal_amplitudes": np.asarray(output["auxiliary"], dtype=np.complex128)}
        ),
        "full_solution_packet": post_release_record["arrays"],
        "full_solution_packet_json": str(post_release_path.resolve()),
        "field_mode_and_diffraction_files": files,
        "field_file_count": len(files),
        "q_assembly_strategy": producer_summary["q_assembly_strategy"],
        "profile_identity": producer_summary["profile"],
        "run_id": producer_summary["run_id"],
        "stage": producer_summary["stage"],
        "task41_a1_a2_comparison": dict(comparison),
        "independent_reevaluation": {
            "entrypoint": "src.runners.task41_p0_saved_output_continuation.check_task41_p0_saved_output_continuation",
            "scope": "reopen producer q/reference receipts, saved A6 residuals, output hashes, modes, powers, and FE metric packet",
        },
    }
    packet_identity = {
        **summary_identity,
        "source_sha": producer_sha,
        "input_sha256": producer_identity["input_sha256"],
        "physical_model_sha256": producer_identity["physical_model_sha256"],
        "run_id": producer_summary["run_id"],
        "stage": producer_summary["stage"],
        "profile_identity": producer_summary["profile"],
        "q_assembly_strategy": producer_summary["q_assembly_strategy"],
    }
    packet = _save_packet(
        runtime,
        "task41_saved_output_official_output",
        {
            "schema": "task41.p0.saved_output_official_output.v1",
            "identity": packet_identity,
            "scientific_identity": scientific_identity,
            "output": dict(output),
            "power": power,
            "R_plus_T_plus_A_volume_minus_one": energy_error,
            "A_minus_A_volume": absorption_error,
            "passed": bool(output_pass and comparison.get("pass") is True),
        },
    )
    return packet, scientific_identity, {
        "power": power,
        "energy_closure_absolute": energy_error,
        "absorption_consistency_absolute": absorption_error,
        "field_output_manifest": files,
    }


def _check_comparison_outputs(
    *,
    receipt_path: Path,
    contract_path: Path,
    contract_sha256: str,
    repo_root: Path,
) -> dict[str, Any]:
    from src.runners.task41_p0_checker import _task41_a2_numerical_checks
    from src.runners.task41_p0_contract import require_task41_p0_contract

    contract, contract_digest = require_task41_p0_contract(
        contract_path,
        expected_sha256=contract_sha256,
        current_root=repo_root,
        check_current_source=False,
        require_clean_source=True,
        case_id="A2",
    )
    receipt = _json_object(receipt_path, "saved-output continuation receipt")
    producer = receipt.get("producer")
    consumer = receipt.get("consumer")
    if (
        receipt_path.name != CONTINUATION_CHECKER_INPUT
        or receipt.get("schema") != CONTINUATION_SCHEMA
        or receipt.get("status") != "OUTPUTS_READY"
        or not isinstance(producer, Mapping)
        or not isinstance(consumer, Mapping)
        or contract_digest != contract_sha256
    ):
        raise ValueError("saved-output continuation receipt or contract identity is invalid")
    source_sha, branch = _source_identity(repo_root)
    if (
        source_sha != consumer.get("source_sha")
        or branch != "task41extra_phi90_p50x50_g17x20"
        or producer.get("source_sha") != contract["source"]["sha"]
        or Path(str(consumer.get("run_directory", ""))).resolve() != receipt_path.parent.resolve()
        or Path(str(producer.get("run_directory", ""))).resolve().is_relative_to(receipt_path.parent.resolve())
    ):
        raise ValueError("saved-output continuation producer/consumer source or directory identity changed")
    _require_service_envelope(contract, contract_path, contract_digest, repo_root)
    original_root = Path(str(producer["run_directory"])).resolve(strict=True)
    original_worker, _, _, _ = _validate_original_attempt(
        original_root, contract, contract_digest
    )
    if any(
        _sha256(Path(str(producer[key]["path"]))) != producer[key]["sha256"]
        for key in ("worker_summary", "run_summary", "run_manifest")
    ):
        raise ValueError("original failed A2 run evidence changed after continuation")
    numerical_output = (receipt_path.parent / "numerical_output").resolve(strict=True)
    continuation_summary_path = receipt_path.parent / "task40_v10_p6_candidate_summary.json"
    continuation_manifest_path = receipt_path.parent / "run_manifest.json"
    continuation_summary = _json_object(continuation_summary_path, "continuation worker summary")
    continuation_manifest = _json_object(continuation_manifest_path, "continuation run manifest")
    case = contract["case"]
    for key, expected in (
        ("model_id", case["model_id"]),
        ("run_id", case["run_id"]),
        ("method", case["method"]),
        ("mpi_size", case["mpi_size"]),
        ("input_sha256", case["input_sha256"]),
        ("physical_model_sha256", case["physical_model_sha256"]),
        ("resolved_config_sha256", case["resolved_config_sha256"]),
        ("source_sha", contract["source"]["sha"]),
        ("consumer_source_sha", source_sha),
    ):
        if continuation_manifest.get(key) != expected:
            raise ValueError(f"continuation manifest {key} differs from its producer/consumer contract")
    if (
        continuation_summary.get("status") != "PASS"
        or continuation_summary.get("original_result_classification") != "WORKER_FAILED"
        or continuation_summary.get("consumer_source_sha") != source_sha
        or continuation_summary.get("source_sha") != contract["source"]["sha"]
    ):
        raise ValueError("continuation summary does not distinguish producer failure from consumer result")
    reference_output = Path(str(producer["numerical_output_path"])).resolve(strict=True)
    result = _task41_a2_numerical_checks(
        continuation_summary,
        numerical_output,
        contract,
        repo_root=repo_root,
        reference_audit_source=(original_worker, reference_output),
    )
    errors = list(result["errors"])
    output_identity = _verify_linked_output_manifest(producer, consumer)
    if output_identity.get("passed") is not True:
        errors.append("saved producer numerical-output bytes or continuation hard links changed")
    checker_payload = {
        "schema": "task41.p0.saved_output_checker.v1",
        "status": "PASS" if not errors else "FAIL",
        "checker_passed": not errors,
        "producer_source_sha": contract["source"]["sha"],
        "consumer_source_sha": source_sha,
        "contract_sha256": contract_digest,
        "checker_input_snapshot_path": str(receipt_path),
        "checker_input_snapshot_sha256": _sha256(receipt_path),
        "original_worker_result_classification": original_worker["result_classification"],
        "independent_rechecks": result,
        "saved_numerical_output_identity": output_identity,
        "errors": errors,
        "raw_evidence_retained": True,
    }
    result_path = receipt_path.parent / CONTINUATION_CHECKER_RECEIPT
    _write_json(result_path, checker_payload)
    checker_payload["checker_result_path"] = str(result_path)
    checker_payload["checker_result_sha256"] = _sha256(result_path)
    return checker_payload


def check_task41_p0_saved_output_continuation(
    receipt_path: Path,
    *,
    contract_path: Path,
    contract_sha256: str,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    """Independently recheck producer evidence and consumer outputs."""
    root = Path(repo_root or Path(__file__).resolve().parents[2]).resolve()
    return _check_comparison_outputs(
        receipt_path.resolve(strict=True),
        contract_path=contract_path,
        contract_sha256=contract_sha256,
        repo_root=root,
    )


def continue_task41_p0_saved_output(
    *,
    run_root: Path,
    output_root: Path,
    contract_path: Path,
    contract_sha256: str,
    consumer_source_sha: str,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    """Rebuild only the P6 FE/MPC identity and finish comparison from saved A2 outputs."""
    from mpi4py import MPI

    from src.io.input_validation import simulation_config_3d_from_normalized
    from src.runners.task40_v10_worker import _task41_a2_comparison
    from src.runners.task41_p0_contract import (
        load_task41_p0_fixed_window,
        require_task41_p0_contract,
    )
    from src.solvers.fullspace_same_mesh_hcurl_pmg_global import _build_same_mesh_levels

    root = Path(repo_root or Path(__file__).resolve().parents[2]).resolve()
    run_root = run_root.resolve(strict=True)
    output_root = output_root.resolve()
    contract, digest = require_task41_p0_contract(
        contract_path,
        expected_sha256=contract_sha256,
        current_root=root,
        check_current_source=False,
        require_clean_source=True,
        case_id="A2",
    )
    if digest != contract_sha256:
        raise ValueError("Task41 continuation execution contract SHA changed")
    source_sha, branch = _source_identity(root)
    if (
        source_sha != consumer_source_sha
        or branch != "task41extra_phi90_p50x50_g17x20"
        or not output_root.is_relative_to(root)
        or output_root == run_root
        or output_root.exists()
        or run_root.is_relative_to(output_root)
        or output_root.is_relative_to(run_root)
    ):
        raise ValueError("saved-output continuation source or new output directory is invalid")
    _require_service_envelope(contract, contract_path, digest, root)
    load_task41_p0_fixed_window(contract, current_root=root, require_current_boot=True)
    producer, _, _, old_evidence = _validate_original_attempt(
        run_root, contract, digest
    )
    identity = producer.get("identity_packet")
    if not isinstance(identity, Mapping):
        raise ValueError("original A2 summary omits its solver identity packet")
    for key, expected in (
        ("input_sha256", contract["case"]["input_sha256"]),
        ("physical_model_sha256", contract["case"]["physical_model_sha256"]),
        ("resolved_config_sha256", contract["case"]["resolved_config_sha256"]),
    ):
        if identity.get(key) != expected:
            raise ValueError(f"original A2 solver identity differs from the contract: {key}")
    post_reference = producer.get("post_release_final_residual_packet")
    pre_reference = producer.get("pre_release_final_residual_packet")
    if not isinstance(pre_reference, Mapping) or not isinstance(post_reference, Mapping):
        raise ValueError("original A2 summary omits the pre/post-release full A6 packets")
    pre_path = Path(str(pre_reference.get("arrays", {}).get("path", ""))).with_suffix(".json")
    post_path = Path(str(post_reference.get("arrays", {}).get("path", ""))).with_suffix(".json")
    pre_solution, pre_facts = validate_saved_a6_packet(
        pre_path,
        run_root=run_root,
        expected_source_sha=str(producer["source_sha"]),
        expected_input_sha256=str(contract["case"]["input_sha256"]),
        expected_physical_model_sha256=str(contract["case"]["physical_model_sha256"]),
    )
    post_solution, post_facts = validate_saved_a6_packet(
        post_path,
        run_root=run_root,
        expected_source_sha=str(producer["source_sha"]),
        expected_input_sha256=str(contract["case"]["input_sha256"]),
        expected_physical_model_sha256=str(contract["case"]["physical_model_sha256"]),
    )
    if (
        pre_facts["solution_storage_sha256"] != post_facts["solution_storage_sha256"]
        or not np.array_equal(pre_solution, post_solution)
        or abs(
            float(producer["independent_final_A6_relative_residual"])
            - pre_facts["residual_checks"][0]["relative_residual"]
        ) > 1.0e-12
        or abs(
            float(producer["post_release_final_A6_relative_residual"])
            - post_facts["residual_checks"][0]["relative_residual"]
        ) > 1.0e-12
        or abs(
            float(producer["independent_final_native_witness_relative_residual"])
            - pre_facts["residual_checks"][1]["relative_residual"]
        ) > 1.0e-12
        or abs(
            float(producer["post_release_native_witness_relative_residual"])
            - post_facts["residual_checks"][1]["relative_residual"]
        ) > 1.0e-12
    ):
        raise ValueError("original A2 summary and pre/post-release A6 packets do not agree")
    del pre_solution

    output_root.mkdir(parents=True, exist_ok=False)
    receipt_path = output_root / CONTINUATION_RECEIPT
    _write_json(
        receipt_path,
        {
            "schema": CONTINUATION_SCHEMA,
            "status": "IN_PROGRESS",
            "producer": {
                "run_directory": str(run_root),
                "source_sha": producer["source_sha"],
                "original_result_classification": "WORKER_FAILED",
                "original_error": producer["error"],
                "pre_release_a6": pre_facts,
                "post_release_a6": post_facts,
                **old_evidence,
            },
            "consumer": {
                "run_directory": str(output_root),
                "source_sha": consumer_source_sha,
                "branch": branch,
                "contract_path": str(contract_path.resolve()),
                "contract_sha256": digest,
                "campaign_window_sha256": contract["window"]["sha256"],
                "numerical_output_directory": str((output_root / "numerical_output").resolve()),
            },
        },
    )
    runtime = _SavedOutputRuntime(output_root, contract)
    runtime.phase = "saved_output_validation"
    runtime.sample("continuation_preflight")
    source_output = Path(old_evidence["numerical_output_path"])
    numerical_output = output_root / "numerical_output"
    copied_output_manifest = _link_saved_output(source_output, numerical_output)

    resolved_path = (run_root / "resolved_config.json").resolve(strict=True)
    if _sha256(resolved_path) != contract["case"]["resolved_config_sha256"]:
        raise ValueError("original A2 resolved configuration hash changed")
    resolved_payload = _json_object(resolved_path, "original A2 resolved configuration")
    cfg = simulation_config_3d_from_normalized(resolved_payload)
    runtime.phase = "p6_fe_mpc_map_and_metric"
    def allocation_gate(label: str, facts: Mapping[str, Any]) -> dict[str, Any]:
        return runtime.check_projected(
            label,
            int(facts.get("additional_payload_bytes", 0)),
            workspace_bytes=int(facts.get("workspace_bytes", 0)),
            future_bytes=int(facts.get("declared_future_co_resident_bytes", 0)),
        )
    runtime.check_projected(
        "task41_saved_output_p6_space_rebuild",
        int(4 * np.dtype(np.complex128).itemsize * post_solution.size),
    )
    levels = _build_same_mesh_levels(
        cfg, MPI.COMM_SELF, (6,), include_positive_coefficients=False
    )
    output = _load_saved_output(run_root, numerical_output, cfg)
    comparison = _task41_a2_comparison(
        runtime,
        cfg,
        levels,
        resolved_payload=resolved_payload,
        a2_full_solution=post_solution,
        a2_output=output,
        output_directory=numerical_output,
        campaign_authority=producer["campaign_authority"],
        allocation_gate=allocation_gate,
    )
    output_gate = bool(
        output.get("electric_finite") is True
        and output.get("auxiliary_finite") is True
        and output["diagnostic_diffraction_inventory"].get("passed") is True
        and np.isfinite(
            [
                float(output["port_metrics"]["R_total"]),
                float(output["port_metrics"]["T_total"]),
                float(output["port_metrics"]["A_balance"]),
                float(output["volume_metrics"]["A_volume_total"]),
            ]
        ).all()
        and abs(
            float(output["port_metrics"]["R_total"])
            + float(output["port_metrics"]["T_total"])
            + float(output["volume_metrics"]["A_volume_total"])
            - 1.0
        )
        <= 1.0e-5
        and abs(
            float(output["port_metrics"]["A_balance"])
            - float(output["volume_metrics"]["A_volume_total"])
        )
        <= 1.0e-5
    )
    packet, scientific_identity, output_facts = _make_output_packet(
        runtime=runtime,
        producer_summary=producer,
        producer_identity=identity,
        consumer_source_sha=consumer_source_sha,
        post_release_record=_json_object(post_path, "post-release A6 packet"),
        full_solution=post_solution,
        post_release_path=post_path,
        numerical_output=numerical_output,
        output=output,
        comparison=comparison,
        output_pass=output_gate,
    )
    continuation_pass = bool(output_gate and comparison.get("pass") is True)
    consumer_summary = dict(producer)
    consumer_summary.update(
        {
            "producer_source_sha": producer["source_sha"],
            "consumer_source_sha": consumer_source_sha,
            "original_status": producer["status"],
            "original_result_classification": producer["result_classification"],
            "status": "PASS" if continuation_pass else "FAILED",
            "result_classification": (
                "SAVED_OUTPUT_CONTINUATION_PASS"
                if continuation_pass
                else "SAVED_OUTPUT_CONTINUATION_GATE_FAIL"
            ),
            "official_result": continuation_pass,
            "numeric_gates_passed": True,
            "output_gates_passed": bool(output_gate and comparison.get("pass") is True),
            "task41_a1_a2_comparison": comparison,
            "output_packet": packet,
            "scientific_identity": scientific_identity,
            "output_facts": {
                key: value for key, value in output.items() if key != "auxiliary"
            },
            **output_facts,
            "saved_output_continuation": {
                "schema": CONTINUATION_SCHEMA,
                "consumer_source_sha": consumer_source_sha,
                "source_output_hardlinks": copied_output_manifest,
                "pre_release_a6": pre_facts,
                "post_release_a6": post_facts,
                "q_factor_or_ksp_restarted": False,
            },
        }
    )
    _write_json(output_root / "task40_v10_p6_candidate_summary.json", consumer_summary)
    case = contract["case"]
    manifest = {
        "schema": CONTINUATION_SCHEMA,
        "model_id": case["model_id"],
        "run_id": case["run_id"],
        "method": case["method"],
        "mpi_size": case["mpi_size"],
        "input_sha256": case["input_sha256"],
        "physical_model_sha256": case["physical_model_sha256"],
        "resolved_config_sha256": case["resolved_config_sha256"],
        "source_sha": producer["source_sha"],
        "consumer_source_sha": consumer_source_sha,
        "profile": producer["profile"],
        "stage": producer["stage"],
        "q_assembly_strategy": producer["q_assembly_strategy"],
        "result_classification": consumer_summary["result_classification"],
        "output_directory": str(output_root),
        "numerical_output_directory": str(numerical_output.resolve()),
        "producer_run_directory": str(run_root),
        "producer_run_manifest_sha256": old_evidence["run_manifest"]["sha256"],
        "task41_contract_sha256": digest,
        "campaign_window_sha256": contract["window"]["sha256"],
    }
    _write_json(output_root / "run_manifest.json", manifest)
    run_summary = {
        "schema": CONTINUATION_SCHEMA,
        "status": "finished",
        "exit_status": 0 if continuation_pass else 1,
        "result_classification": consumer_summary["result_classification"],
        "run_id": case["run_id"],
        "source_sha": producer["source_sha"],
        "consumer_source_sha": consumer_source_sha,
        "output_directory": str(output_root),
        "numerical_output_directory": str(numerical_output.resolve()),
        "producer_run_directory": str(run_root),
        "pre_release_a6_sha256": pre_facts["packet_npz_sha256"],
        "post_release_a6_sha256": post_facts["packet_npz_sha256"],
    }
    _write_json(output_root / "run_summary.json", run_summary)
    receipt = _json_object(receipt_path, "saved-output continuation receipt")
    receipt["status"] = "OUTPUTS_READY"
    receipt["consumer"].update(
        {
            "numerical_output_manifest": copied_output_manifest,
            "output_packet": packet,
            "comparison_pass": comparison.get("pass") is True,
            "official_output_pass": output_gate,
        }
    )
    _write_json(receipt_path, receipt)
    checker_input_path = output_root / CONTINUATION_CHECKER_INPUT
    _write_json(checker_input_path, receipt)
    runtime.marker(
        "task41_saved_output_continuation_outputs_ready",
        {"output_gate_pass": output_gate, "comparison_pass": comparison.get("pass") is True},
    )
    return {
        "status": "OUTPUTS_READY" if continuation_pass else "FAILED",
        "receipt_path": str(receipt_path),
        "checker_input_snapshot_path": str(checker_input_path),
        "comparison_pass": comparison.get("pass") is True,
        "output_gate_pass": output_gate,
        "pre_release_a6": pre_facts,
        "post_release_a6": post_facts,
        "original_result_classification": producer["result_classification"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--run-root", type=Path)
    mode.add_argument("--check-input", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--contract-sha256", required=True)
    parser.add_argument("--consumer-source-sha")
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[2]
    if args.check_input is not None:
        try:
            result = check_task41_p0_saved_output_continuation(
                args.check_input,
                contract_path=args.contract,
                contract_sha256=args.contract_sha256,
                repo_root=root,
            )
        except Exception as exc:
            result = {"checker_passed": False, "error": {"type": type(exc).__name__, "message": str(exc)}}
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0 if result.get("checker_passed") is True else 2
    if args.output_dir is None or args.consumer_source_sha is None:
        parser.error("continuation mode requires --output-dir and --consumer-source-sha")
    try:
        result = continue_task41_p0_saved_output(
            run_root=args.run_root,
            output_root=args.output_dir,
            contract_path=args.contract,
            contract_sha256=args.contract_sha256,
            consumer_source_sha=args.consumer_source_sha,
            repo_root=root,
        )
    except Exception as exc:
        result = {
            "status": "FAILED",
            "error": {"type": type(exc).__name__, "message": str(exc)},
            "original_result_preserved": True,
        }
        output_root = args.output_dir.resolve()
        if output_root.is_dir():
            receipt_path = output_root / CONTINUATION_RECEIPT
            current = {}
            if receipt_path.is_file():
                current = _json_object(receipt_path, "saved-output continuation receipt")
            current.update(
                {
                    "schema": CONTINUATION_SCHEMA,
                    "status": "FAILED",
                    "consumer_error": result["error"],
                }
            )
            _write_json(receipt_path, current)
            result["receipt_path"] = str(receipt_path)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result.get("status") == "OUTPUTS_READY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
