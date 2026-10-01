"""Thin artifact loader for the Task40 saved-field P1 comparison."""

from __future__ import annotations

import argparse
import hashlib
import json
import resource
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from src.postprocessing.task40_saved_field_h_comparison import (
    compare_common_subcell_volume,
    compare_material_interface_traces,
    restore_p6_total_field,
    total_field_sample_witness,
)


DEFAULT_G0 = Path(
    "results/task40extra_nonseparable_0p7nm/"
    "task40extra_0p7nm_nonseparable_g0_iterative_review_v1__full3d_iterative__mpi1__Mna/"
    "20260930T102148.356966Z"
)
DEFAULT_G1 = Path(
    "results/task40extra_nonseparable_0p7nm/"
    "task40extra_0p7nm_nonseparable_g1_iterative_review_v1__full3d_iterative__mpi1__Mna/"
    "20260930T105500.302324Z"
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _git_facts(root: Path) -> dict[str, Any]:
    try:
        head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
        status = subprocess.check_output(["git", "status", "--porcelain"], cwd=root, text=True)
    except (OSError, subprocess.CalledProcessError) as exc:
        return {"head": None, "status": None, "error": str(exc)}
    return {"head": head, "status": status.splitlines()}


def _qualified_environment() -> dict[str, Any]:
    import os
    import sys

    from mpi4py import MPI
    from petsc4py import PETSc

    if os.environ.get("_MYFENICS_WSL_QUALIFIED_ACTIVATION") != "1":
        raise RuntimeError("P1 requires scripts/activate_myfenics_wsl.sh in this shell")
    if sys.platform != "linux":
        raise RuntimeError("P1 must execute in the qualified WSL/Linux environment")
    if np.dtype(PETSc.ScalarType) != np.dtype(np.complex128):
        raise RuntimeError(f"P1 requires complex128 PETSc, got {PETSc.ScalarType}")
    if MPI.COMM_WORLD.size != 1:
        raise RuntimeError("saved G0/G1 P1 comparison is frozen to MPI size 1")
    return {
        "activation": os.environ.get("_MYFENICS_WSL_QUALIFIED_ACTIVATION"),
        "python": sys.executable,
        "platform": sys.platform,
        "petsc_scalar_type": np.dtype(PETSc.ScalarType).name,
        "petsc_int_type": np.dtype(PETSc.IntType).name,
        "mpi_size": int(MPI.COMM_WORLD.size),
    }


def _complex_pair(value: Any) -> list[float]:
    number = complex(value)
    return [float(number.real), float(number.imag)]


def _physical_signature(resolved: dict[str, Any], cfg: Any) -> dict[str, Any]:
    """Compare physical sections while allowing input and mesh identities to differ."""

    return {
        "resolved_sections": {
            name: resolved.get(name)
            for name in ("geometry", "materials", "incidence", "boundary")
        },
        "derived_physical_values": {
            "k0": float(cfg.k0),
            "mu_r": _complex_pair(cfg.mu_r),
            "epsilon_grating": _complex_pair(cfg.eps_grating),
            "epsilon_substrate": _complex_pair(cfg.eps_substrate),
            "incident_amplitude": _complex_pair(cfg.incident_amplitude),
            "electric_field_scale_V_per_m": float(cfg.electric_field_scale_V_per_m),
            "magnetic_field_scale_A_per_m": float(cfg.magnetic_field_scale_A_per_m),
        },
    }


@dataclass
class RunInput:
    label: str
    root: Path
    packet: dict[str, Any]
    manifest: dict[str, Any]
    resolved: dict[str, Any]
    cfg: Any
    vector: np.ndarray
    vector_sha256: str
    packet_sha256: str
    vector_archive: Path
    vector_archive_sha256: str
    sample_metadata: dict[str, Any]
    sample_archive: Path
    sample_archive_sha256: str
    samples: dict[str, np.ndarray]
    run_summary: dict[str, Any]
    official_power: dict[str, Any]
    official_volume: dict[str, Any]
    input_signature: dict[str, Any]


def _load_run(label: str, run_root: Path) -> RunInput:
    from src.io.input_validation import simulation_config_3d_from_normalized

    run_root = run_root.resolve()
    packet_path = run_root / "x2_retained_final.json"
    packet = _read_json(packet_path)
    descriptor = packet["full_solution"]
    arrays_metadata = packet["arrays"]
    vector_archive = Path(arrays_metadata["path"])
    if not vector_archive.is_absolute():
        vector_archive = (run_root / vector_archive).resolve()
    vector_archive_sha256 = _sha256(vector_archive)
    if vector_archive_sha256 != arrays_metadata["sha256"]:
        raise ValueError(f"{label}: retained full-field archive SHA mismatch")
    with np.load(vector_archive, allow_pickle=False) as arrays:
        vector = np.asarray(arrays[descriptor["array_key"]]).copy()
    if list(vector.shape) != descriptor["shape"]:
        raise ValueError(f"{label}: saved FE vector shape differs from packet")
    if str(vector.dtype) != descriptor["dtype"] or vector.dtype != np.dtype(np.complex128):
        raise ValueError(f"{label}: saved FE vector is not packet-bound complex128")
    if not np.isfinite(vector).all():
        raise ValueError(f"{label}: saved FE vector contains nonfinite values")

    manifest = _read_json(run_root / "run_manifest.json")
    run_summary = _read_json(run_root / "run_summary.json")
    if (
        run_summary.get("run_id") != manifest.get("run_id")
        or run_summary.get("status") != "finished"
        or run_summary.get("result_classification") != "worker_exit0"
        or int(run_summary.get("exit_status", -1)) != 0
    ):
        raise ValueError(f"{label}: original run_summary final Gate is not worker_exit0")
    swap_gate = run_summary.get("task40_swap_qualification", {})
    if (
        swap_gate.get("status") != "qualified_zero"
        or int(swap_gate.get("process_tree_peak_swap_bytes", -1)) != 0
        or not swap_gate.get("process_tree_all_status_readable")
        or swap_gate.get("process_tree_identity_coverage") != "complete"
    ):
        raise ValueError(f"{label}: original process-tree swap Gate did not qualify")
    input_path = run_root / "input_original.dat"
    input_sha = _sha256(input_path)
    if input_sha != manifest["input_sha256"]:
        raise ValueError(f"{label}: input_original.dat differs from run manifest SHA")
    packet_identity = packet["identity"]
    if manifest["source_sha"] != packet_identity["source_sha"]:
        raise ValueError(f"{label}: manifest and retained-field source SHA differ")
    if manifest["physical_model_sha256"] != packet_identity["physical_model_sha256"]:
        raise ValueError(f"{label}: manifest and retained-field physical identity differ")

    resolved_path = run_root / "resolved_config.json"
    resolved = _read_json(resolved_path)
    cfg = simulation_config_3d_from_normalized(resolved)
    numerical = Path(manifest["numerical_output_directory"])
    if not numerical.is_absolute():
        numerical = (run_root / numerical).resolve()
    sample_metadata_path = numerical / "full3d_reference_samples.json"
    sample_metadata = _read_json(sample_metadata_path)
    sample_archive = numerical / str(sample_metadata["archive"])
    sample_archive_sha256 = _sha256(sample_archive)
    if sample_archive_sha256 != sample_metadata["archive_sha256"]:
        raise ValueError(f"{label}: reference-sample archive SHA mismatch")
    with np.load(sample_archive, allow_pickle=False) as arrays:
        samples = {
            name: np.asarray(arrays[name]).copy()
            for name in ("x_nm", "y_nm", "z_nm", "E_V_per_m", "H_A_per_m")
        }
    power_path = numerical / "dtn_port_power_metrics_3d.json"
    volume_path = numerical / "volume_absorption.json"
    official_power = _read_json(power_path)
    official_volume = _read_json(volume_path)
    if official_volume.get("status") != "ok":
        raise ValueError(f"{label}: saved official A_volume record is not status=ok")
    if official_power.get("power_source") != "dtn_port_modal_amplitudes":
        raise ValueError(f"{label}: saved R/T/A is not the official DtN port-modal record")
    for name in ("R_total", "T_total", "A_balance"):
        value = official_power.get(name)
        if value is None or not np.isfinite(float(value)):
            raise ValueError(f"{label}: saved official power record has no finite {name}")

    return RunInput(
        label=label,
        root=run_root,
        packet=packet,
        manifest=manifest,
        resolved=resolved,
        cfg=cfg,
        vector=vector,
        vector_sha256=hashlib.sha256(vector.tobytes()).hexdigest(),
        packet_sha256=_sha256(packet_path),
        vector_archive=vector_archive,
        vector_archive_sha256=vector_archive_sha256,
        sample_metadata=sample_metadata,
        sample_archive=sample_archive,
        sample_archive_sha256=sample_archive_sha256,
        samples=samples,
        run_summary=run_summary,
        official_power=official_power,
        official_volume=official_volume,
        input_signature=_physical_signature(resolved, cfg),
    )


def _official_power_summary(run: RunInput) -> dict[str, Any]:
    return {
        "role": run.official_power.get("role"),
        "power_source": run.official_power.get("power_source"),
        "R_total": run.official_power.get("R_total"),
        "T_total": run.official_power.get("T_total"),
        "A_balance": run.official_power.get("A_balance"),
        "A_volume_total": run.official_volume.get("A_volume_total"),
        "A_volume_grating": run.official_volume.get("A_volume_grating"),
        "A_volume_substrate": run.official_volume.get("A_volume_substrate"),
        "A_port_balance_minus_A_volume_total": run.official_volume.get(
            "A_port_balance_minus_A_volume_total"
        ),
        "volume_power_source": run.official_volume.get("power_source"),
        "original_final_run_gate": {
            "run_id": run.run_summary["run_id"],
            "status": run.run_summary["status"],
            "result_classification": run.run_summary["result_classification"],
            "exit_status": run.run_summary["exit_status"],
            "task_process_tree_swap_status": run.run_summary[
                "task40_swap_qualification"
            ]["status"],
            "task_process_tree_peak_swap_bytes": run.run_summary[
                "task40_swap_qualification"
            ]["process_tree_peak_swap_bytes"],
            "task_process_tree_identity_coverage": run.run_summary[
                "task40_swap_qualification"
            ]["process_tree_identity_coverage"],
        },
    }


def _official_power_differences(first: RunInput, second: RunInput) -> dict[str, Any]:
    left, right = _official_power_summary(first), _official_power_summary(second)
    fields = (
        "R_total",
        "T_total",
        "A_balance",
        "A_volume_total",
    )
    differences = {}
    for name in fields:
        if left[name] is None or right[name] is None:
            differences[name] = {"status": "not_recorded", "g0": left[name], "g1": right[name]}
            continue
        absolute = abs(float(right[name]) - float(left[name]))
        differences[name] = {
            "g0": float(left[name]),
            "g1": float(right[name]),
            "g1_minus_g0": float(right[name]) - float(left[name]),
            "absolute_difference": absolute,
            "limit_absolute": 1.0e-3,
            "pass": bool(absolute <= 1.0e-3),
        }
    passes = [item.get("pass", False) for item in differences.values()]
    return {
        "source": "already-qualified official DtN-port R/T/A and volume_absorption A_volume; no flux or power recomputation",
        "G0": left,
        "G1": right,
        "G1_minus_G0": differences,
        "gate": {
            "limit_absolute": 1.0e-3,
            "pass": bool(passes and all(passes)),
            "classification": "reviewed G0/G1 engineering h power gate",
        },
    }


def _model_facts(run: RunInput, field: Any, witness: dict[str, Any]) -> dict[str, Any]:
    return {
        "run_id": run.manifest["run_id"],
        "source_sha": run.manifest["source_sha"],
        "input_sha256": run.manifest["input_sha256"],
        "physical_model_sha256": run.manifest["physical_model_sha256"],
        "run_root": str(run.root),
        "retained_packet_sha256": run.packet_sha256,
        "full_field_archive": str(run.vector_archive),
        "full_field_archive_sha256": run.vector_archive_sha256,
        "full_field_vector_sha256": run.vector_sha256,
        "full_field_shape": list(run.vector.shape),
        "sample_archive": str(run.sample_archive),
        "sample_archive_sha256": run.sample_archive_sha256,
        "total_field_sample_witness": witness,
        "mesh_cell_count": int(field.levels["mesh"].topology.index_map(3).size_global),
        "p6_dof_count": int(field.levels["spaces"][6].dofmap.index_map.size_global),
        "axis_point_counts": [int(axis.size) for axis in field.axes],
        "official_power": _official_power_summary(run),
    }


def compare_saved_fields(
    root: Path,
    g0_root: Path,
    g1_root: Path,
    output: Path,
    *,
    progress: bool = True,
) -> dict[str, Any]:
    started = time.monotonic()
    environment = _qualified_environment()
    g0 = _load_run("G0", g0_root)
    g1 = _load_run("G1", g1_root)
    if g0.input_signature != g1.input_signature:
        different = [
            key for key in g0.input_signature
            if g0.input_signature[key] != g1.input_signature[key]
        ]
        raise ValueError(f"G0/G1 physical configurations differ in sections: {different}")
    if progress:
        print("P1: rebuilding p6 mesh/space and restoring saved total fields", flush=True)
    field0 = restore_p6_total_field("G0", g0.cfg, g0.vector)
    field1 = restore_p6_total_field("G1", g1.cfg, g1.vector)
    witness0 = total_field_sample_witness(field0, g0.samples, g0.sample_metadata)
    witness1 = total_field_sample_witness(field1, g1.samples, g1.sample_metadata)
    if progress:
        print(
            "P1: fixed total-field semantics; saved-sample witnesses "
            f"G0 E/H={witness0['electric_relative_l2']:.3e}/{witness0['magnetic_relative_l2_from_direct_fe_curl']:.3e}, "
            f"G1 E/H={witness1['electric_relative_l2']:.3e}/{witness1['magnetic_relative_l2_from_direct_fe_curl']:.3e}",
            flush=True,
        )
    volume = compare_common_subcell_volume(field0, field1, progress=progress)
    axes = tuple(
        np.unique(np.concatenate((field0.axes[i], field1.axes[i]))) for i in range(3)
    )
    if progress:
        print("P1: comparing same-side traces on configured grating and void faces", flush=True)
    interface_traces = compare_material_interface_traces(field0, field1, axes)
    powers = _official_power_differences(g0, g1)
    h_pass = bool(volume["field_scaled_curl_h_gate"]["pass"])
    witness_pass = bool(witness0["pass"] and witness1["pass"])
    power_pass = bool(powers["gate"]["pass"])
    result = {
        "schema": "task40extra.p1.saved-field-common-subcells.v1",
        "status": "PASS" if (h_pass and witness_pass and power_pass) else "ENGINEERING_H_GATE_FAILED",
        "execution": {
            "status": "OFFLINE_SAVED_FIELD_POSTPROCESS_ONLY",
            "pde_started": False,
            "physical_operator_built": False,
            "factor_started": False,
            "ksp_started": False,
            "duration_seconds": time.monotonic() - started,
            "process_peak_rss_bytes": int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss) * 1024,
            "abi": environment,
        },
        "source": {
            "checker_script": str(Path(__file__).resolve()),
            "checker_script_sha256": _sha256(Path(__file__).resolve()),
            "repository": _git_facts(root.resolve()),
        },
        "physical_configuration_identity": {
            "sections_compared": ["geometry", "materials", "incidence", "boundary", "derived physical values"],
            "signature_sha256": hashlib.sha256(
                json.dumps(g0.input_signature, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest(),
            "input_sha256_equal": g0.manifest["input_sha256"] == g1.manifest["input_sha256"],
            "G0_input_sha256": g0.manifest["input_sha256"],
            "G1_input_sha256": g1.manifest["input_sha256"],
            "physical_model_sha256_equal": g0.manifest["physical_model_sha256"] == g1.manifest["physical_model_sha256"],
            "mesh_and_DoF_identities_may_differ": True,
        },
        "field_semantics": {
            "selected_by_production_contract": "total_field",
            "evidence": "recover_p0_outputs names the Function E_total, records field_model=total_field, passes it directly to total-field volume absorption, and calls diffraction without E_scattered",
            "samples_are_a_fixed_semantics_witness": True,
        },
        "models": {
            "G0": _model_facts(g0, field0, witness0),
            "G1": _model_facts(g1, field1, witness1),
        },
        "common_union_volume_comparison": volume,
        "same_side_material_interface_traces": interface_traces,
        "official_power_comparison": powers,
        "gates": {
            "sample_witness_G0": witness0["pass"],
            "sample_witness_G1": witness1["pass"],
            "global_field_scaled_curl_h_gate": volume["field_scaled_curl_h_gate"]["pass"],
            "official_power_h_gate": power_pass,
            "overall": bool(h_pass and witness_pass and power_pass),
            "continuum_convergence_claim": False,
        },
        "cleanup": {
            "status": "COMPLETED",
            "operation_stack": "p6 mesh/space/MPC only; no physical operator, factor, or KSP",
            "direct_curl": "UFL derivative into DG6",
        },
    }
    _write_json(output, result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--g0-root", type=Path, default=DEFAULT_G0)
    parser.add_argument("--g1-root", type=Path, default=DEFAULT_G1)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(
            "benchmarks/artifacts/task40extra_0p7nm_engineering/"
            "p1_saved_field_common_subcells/p1_g0_g1.json"
        ),
    )
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    result = compare_saved_fields(
        args.root.resolve(), args.g0_root, args.g1_root, args.output.resolve()
    )
    print(
        json.dumps(
            {
                "status": result["status"],
                "output": str(args.output.resolve()),
                "h_gate": result["gates"]["global_field_scaled_curl_h_gate"],
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
