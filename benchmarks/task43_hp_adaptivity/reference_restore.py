"""Restore inventoried historical fields without solving a PDE.

The default role permits only Y6_1/Y6_2. Reserved holdout and control fields
require an explicit, hash-bound post-selection stop decision and asset manifest.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
from mpi4py import MPI

from src.constraints.floquet_3d import build_double_floquet_mpc
from src.geometry.mesh_builder_3d import build_airbox_mesh_3d
from src.io.input_validation import simulation_config_3d_from_normalized
from src.postprocessing.full3d_reference import (
    _sample_distributed_function,
    reference_plane_sides,
)
from src.postprocessing.physical_field_comparison import (
    magnetic_field_from_electric_curl,
)
from src.postprocessing.physical_field_sampling import (
    prepare_cell_local_vector_field_export,
)
from src.solvers.common_3d_solve import _create_nedelec_space
from src.solvers.fullspace_dtn_action import build_dynamic_mode_inventory
from src.solvers.fullspace_same_mesh_hcurl_pmg_physical import (
    restore_p0_full_field,
)

ROOT = Path(__file__).resolve().parents[2]
INVENTORY = ROOT / "docs/task43_hp_adaptivity/outcomes/records/existing_validation_fields_v1.json"
DEFAULT_OUTPUT_ROOT = ROOT / "benchmarks/artifacts/task43/reference_imports"
STORAGE_NAME = "recovered_p6_storage_coefficients.npy"

_ASSET_NAMES = (
    "resolved_config.json",
    "p6_condensed_direct_summary.json",
    "numerical_output/full3d_reference_samples.npz",
    "numerical_output/full3d_reference_samples.json",
    "numerical_output/dtn_port_diffraction_orders_3d.json",
    "numerical_output/dtn_auxiliary_amplitudes_3d.json",
)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _array_identity(value: np.ndarray) -> dict[str, object]:
    array = np.ascontiguousarray(value)
    digest = hashlib.sha256()
    digest.update(array.dtype.str.encode("ascii"))
    digest.update(json.dumps(list(array.shape)).encode("ascii"))
    digest.update(array.view(np.uint8))
    return {
        "dtype": array.dtype.str,
        "shape": list(array.shape),
        "sha256": digest.hexdigest(),
    }


def _relative_l2(actual: np.ndarray, reference: np.ndarray) -> float:
    delta = np.asarray(actual) - np.asarray(reference)
    denominator = float(np.linalg.norm(np.asarray(reference).ravel()))
    return float(np.linalg.norm(delta.ravel()) / max(denominator, 1.0e-300))


def _copy_verified_assets(label: str, entry: dict[str, Any], out_dir: Path) -> dict[str, Path]:
    support = entry["supporting_artifact_identities"]
    sources: dict[str, tuple[Path, dict[str, Any]]] = {
        relative: (Path(support[relative]["path"]), support[relative])
        for relative in _ASSET_NAMES
    }
    storage = entry["storage"]
    sources[STORAGE_NAME] = (Path(storage["path"]), storage)

    copied: dict[str, Path] = {}
    for relative, (source, expected) in sources.items():
        if not source.is_file():
            raise FileNotFoundError(f"{label}: inventoried source file is missing: {source}")
        actual_size = source.stat().st_size
        actual_hash = _sha256_file(source)
        if actual_size != int(expected["bytes"]):
            raise ValueError(f"{label}: inventoried byte count mismatch for {source}")
        if actual_hash != str(expected["sha256"]):
            raise ValueError(f"{label}: inventoried SHA256 mismatch for {source}")
        target = out_dir / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists() or _sha256_file(target) != actual_hash:
            shutil.copyfile(source, target)
        if target.stat().st_size != actual_size or _sha256_file(target) != actual_hash:
            raise OSError(f"{label}: copied asset verification failed: {target}")
        copied[relative] = target
    return copied


def _post_selection_binding(record_path: Path) -> dict[str, Any]:
    """Validate the immutable stop decision before opening reserved fields."""
    from benchmarks.task43_hp_adaptivity.candidate_records import (
        load_accepted_parent_artifacts,
    )

    decision = json.loads(Path(record_path).read_text())
    if (
        decision.get("schema") != "task43.rejected-candidate-closeout.v1"
        or decision.get("status")
        != "REJECTED_UNDER_FROZEN_G_NOISE_GATE_SELECTION_STOPPED"
        or decision.get("transition10_created") is not False
        or decision.get("last_accepted_state", {}).get("frozen_after_selection_stop")
        is not True
    ):
        raise ValueError("post-selection validation requires a frozen stop decision")
    selection = decision["evidence"]["last_accepted_selection"]
    selection_path = Path(selection["path"])
    if not selection_path.is_absolute():
        selection_path = ROOT / selection_path
    if (
        _sha256_file(selection_path) != selection["sha256"]
        or selection["sha256"]
        != decision["last_accepted_state"]["selection_sha256"]
    ):
        raise ValueError("post-selection frozen selection hash differs")
    accepted = load_accepted_parent_artifacts(
        selection_path,
        artifact_root=ROOT,
        acceptance_contract_path=ROOT / "docs/task43_hp_adaptivity/outcomes/records/round1_acceptance_contract_v1.json",
    )
    if accepted["candidate_id"] != decision["last_accepted_state"]["candidate_id"]:
        raise ValueError("post-selection accepted candidate differs")
    return {"decision": decision, "accepted": accepted,
            "stop_sha256": _sha256_file(Path(record_path)),
            "selection_sha256": selection["sha256"]}


def _load_inventory_entry(
    label: str,
    *,
    post_selection_record: Path | None = None,
    assets_manifest: Path | None = None,
) -> dict[str, Any]:
    reserved = label in {"Y5_1", "Y3", "Y3_2"}
    if label not in {"Y6_1", "Y6_2"} and not reserved:
        raise ValueError("unknown historical field label")
    if reserved and (post_selection_record is None or assets_manifest is None):
        raise ValueError("reserved fields require explicit post-selection binding")
    payload = json.loads(INVENTORY.read_text(encoding="utf-8"))
    matches = [entry for entry in payload["cases"] if entry.get("label") == label]
    if len(matches) != 1:
        raise ValueError(f"inventory must contain exactly one {label} entry")
    entry = matches[0]
    if not reserved:
        if post_selection_record is not None or assets_manifest is not None:
            raise ValueError("selection/calibration restoration cannot use post-selection arguments")
        return entry
    binding = _post_selection_binding(post_selection_record)
    manifest = json.loads(assets_manifest.read_text())
    if (
        manifest.get("schema") != "task43.post-selection-assets.v1"
        or manifest.get("selection_eligible") is not False
        or manifest["selection_stop_record"]["sha256"] != binding["stop_sha256"]
        or manifest["frozen_selection"]["sha256"] != binding["selection_sha256"]
        or manifest["original_inventory"]["sha256"] != _sha256_file(INVENTORY)
    ):
        raise ValueError("post-selection asset manifest binding differs")
    augmented = [case for case in manifest["cases"] if case.get("label") == label]
    if len(augmented) != 1 or any(augmented[0].get(k) != v for k, v in entry.items()):
        raise ValueError("post-selection assets altered the original inventory")
    if label in {"Y3", "Y3_2"}:
        contract_path = ROOT / "docs/task43_hp_adaptivity/outcomes/records/final_control_contract_v1.json"
        if manifest["controls_contract"]["sha256"] != _sha256_file(contract_path):
            raise ValueError("frozen control contract hash differs")
        control = json.loads(contract_path.read_text())["controls"][("Y3", "Y3_2").index(label)]
        if augmented[0]["axis_values_nm"] != control["axes_nm"]:
            raise ValueError("post-selection control axes differ from frozen contract")
    return augmented[0]


def _configure_historical_direct_route(config: dict[str, Any], entry: dict[str, Any]):
    cfg = simulation_config_3d_from_normalized(config)
    expected_axes = entry["axis_values_nm"]
    for axis in ("x", "y", "z"):
        configured = tuple(float(value) for value in getattr(cfg, f"mesh_axis_{axis}_values"))
        inventoried = tuple(float(value) for value in expected_axes[axis])
        if configured != inventoried:
            raise ValueError(f"resolved config {axis}-axis differs from its inventory")

    # The Task40 native direct profile overrode the public auto-propagating
    # default.  Bind those actual settings explicitly for reconstruction.
    cfg.stage4_dtn_order_policy = "explicit_rectangle"
    cfg.stage4_dtn_rectangle_max_m = 4
    cfg.stage4_dtn_rectangle_max_n = 8
    cfg.stage4_dtn_quadrature_degree = int(entry["surface_q"])
    cfg.stage4_incident_quadrature_degree = int(entry["surface_q"])
    volume_quadrature = entry["volume_q"]
    if len(volume_quadrature) != 2 or volume_quadrature[0] != volume_quadrature[1]:
        raise ValueError("historical volume quadrature metadata is inconsistent")
    cfg.stage4_volume_quadrature_degree = int(volume_quadrature[0]["quadrature_degree"])
    cfg.stage4_volume_quadrature_rule = str(volume_quadrature[0]["quadrature_rule"])
    cfg.stage4_dtn_sparse_cutoff_policy = str(entry["cutoff"])
    cfg.stage4_dtn_sparse_cutoff_relative_tolerance = float(
        entry["residuals"]["dtn_sparse_cutoff_relative_tolerance"]
    )
    # The inventoried Task40 modes use the historical unscaled basis (scale 1).
    # This is intentionally not changed to Task43's boundary-scaled basis.
    for name in (
        "stage4_port_boundary_amplitude_scale_policy",
        "task40_port_boundary_amplitude_scale_policy",
    ):
        setattr(cfg, name, None)
    return cfg


def _verify_historical_modes(
    modes,
    mode_rows,
    mode_hash: str,
    entry: dict[str, Any],
    orders_payload: dict[str, Any],
    auxiliary_rows: list[dict[str, Any]],
) -> tuple[list[dict[str, object]], str, dict[str, np.ndarray]]:
    if len(modes) != int(entry["mode_count"]):
        raise ValueError("reconstructed port mode count differs from the inventory")
    if len(mode_rows) != len(modes):
        raise ValueError("reconstructed mode manifest length differs from its mode list")
    if mode_hash != str(entry["mode_sha256"]):
        raise ValueError("reconstructed ordered port mode identity hash differs")
    metrics = orders_payload["metrics"]
    for key, expected in (
        ("active_mode_count", int(entry["mode_count"])),
        ("parent_mode_count", int(entry["mode_count"])),
        ("active_mode_sha256", str(entry["mode_sha256"])),
        ("parent_mode_sha256", str(entry["mode_sha256"])),
        ("dtn_sparse_cutoff_policy", str(entry["cutoff"])),
        (
            "dtn_sparse_cutoff_relative_tolerance",
            float(entry["residuals"]["dtn_sparse_cutoff_relative_tolerance"]),
        ),
        (
            "dtn_sparse_cutoff_identity_sha256",
            str(entry["residuals"]["dtn_sparse_cutoff_identity_sha256"]),
        ),
    ):
        if metrics.get(key) != expected:
            raise ValueError(f"historical order record {key} differs from inventory")
    for key, power_key in (("R_total", "R"), ("T_total", "T")):
        if not np.isclose(
            float(metrics[key]),
            float(entry["power"][power_key]),
            rtol=1.0e-14,
            atol=1.0e-14,
        ):
            raise ValueError(f"historical {key} differs from the inventoried power row")

    order_rows = orders_payload["orders"]
    if len(order_rows) != len(modes) or len(auxiliary_rows) != len(modes):
        raise ValueError("saved mode output does not contain all 612 ordered rows")

    keys = np.empty((len(modes), 4), dtype="U16")
    mode_alpha = np.empty(len(modes), dtype=np.complex128)
    mode_gamma = np.empty(len(modes), dtype=np.complex128)
    mode_beta = np.empty(len(modes), dtype=np.complex128)
    mode_e = np.empty((len(modes), 3), dtype=np.complex128)
    mode_k = np.empty((len(modes), 3), dtype=np.complex128)
    mode_h = np.empty((len(modes), 3), dtype=np.complex128)
    mode_scale = np.empty(len(modes), dtype=np.float64)
    boundary_phase = np.empty(len(modes), dtype=np.complex128)
    boundary_amp_reconstruction = np.empty(len(modes), dtype=np.complex128)
    amplitudes: dict[str, np.ndarray] = {
        name: np.empty(len(modes), dtype=np.complex128)
        for name in (
            "auxiliary_amplitude_total_projection",
            "incident_projection",
            "outgoing_amplitude",
            "outgoing_amplitude_at_boundary",
        )
    }
    for index, (mode, identity, row, aux) in enumerate(
        zip(modes, mode_rows, order_rows, auxiliary_rows)
    ):
        key = (str(mode.side), int(mode.m), int(mode.n), str(mode.polarization))
        identity_key = (
            str(identity["side"]),
            int(identity["m"]),
            int(identity["n"]),
            str(identity["polarization"]),
        )
        row_key = (
            str(row["side"]),
            int(row["m"]),
            int(row["n"]),
            str(row["polarization"]),
        )
        aux_key = (
            str(aux["side"]),
            int(aux["m"]),
            int(aux["n"]),
            str(aux["polarization"]),
        )
        if (
            int(identity["mode_index"]) != index
            or key != identity_key
            or key != row_key
            or key != aux_key
        ):
            raise ValueError(f"mode ordering mismatch at auxiliary index {index}")
        if int(aux["auxiliary_index"]) != index:
            raise ValueError("historical auxiliary vector is not in solver mode order")
        for name, actual in (
            ("alpha", complex(mode.alpha)),
            ("gamma", complex(mode.gamma)),
            ("beta", complex(mode.beta)),
        ):
            pair = row[name]
            archived = complex(float(pair[0]), float(pair[1]))
            if not np.isclose(actual, archived, rtol=5e-14, atol=5e-14):
                raise ValueError(f"historical {name} differs at mode index {index}")
        mode_scale[index] = float(mode.boundary_amplitude_scale)
        if "boundary_amplitude_scale" in aux:
            archived_scale = float(aux["boundary_amplitude_scale"])
            if not np.isclose(mode_scale[index], archived_scale, rtol=0.0, atol=1e-14):
                raise ValueError(f"historical port scale differs at mode index {index}")
        elif mode_scale[index] != 1.0:
            raise ValueError("historical output omitted scale metadata for a scaled mode")
        keys[index] = key
        mode_alpha[index] = mode.alpha
        mode_gamma[index] = mode.gamma
        mode_beta[index] = mode.beta
        mode_e[index] = mode.e_vector
        mode_k[index] = mode.k_vector
        mode_h[index] = mode.h_vector
        for name, values in amplitudes.items():
            pair = aux[name]
            values[index] = complex(float(pair[0]), float(pair[1]))
            order_pair = row.get(name)
            if order_pair is None or not np.array_equal(
                np.asarray(pair, dtype=np.float64),
                np.asarray(order_pair, dtype=np.float64),
            ):
                raise ValueError(f"auxiliary/order modal field {name} differs at index {index}")
        phase_pair = aux["boundary_phase"]
        order_phase_pair = row.get("boundary_phase")
        if order_phase_pair is None or not np.array_equal(
            np.asarray(phase_pair, dtype=np.float64),
            np.asarray(order_phase_pair, dtype=np.float64),
        ):
            raise ValueError(f"auxiliary/order boundary phase differs at index {index}")
        boundary_phase[index] = complex(float(phase_pair[0]), float(phase_pair[1]))
        boundary_amp_reconstruction[index] = (
            amplitudes["outgoing_amplitude"][index] * boundary_phase[index]
        )
        if not np.array_equal(
            np.asarray(row["outgoing_amplitude_at_boundary"], dtype=np.float64),
            np.asarray(aux["outgoing_amplitude_at_boundary"], dtype=np.float64),
        ):
            raise ValueError(f"outgoing boundary amplitude differs at index {index}")
    if not np.all(np.isfinite(mode_scale)):
        raise ValueError("historical mode basis scale contains a non-finite value")
    if any(not np.all(np.isfinite(values)) for values in amplitudes.values()):
        raise ValueError("saved historical modal amplitudes contain non-finite values")
    arrays = {
        "mode_keys": keys,
        "mode_alpha": mode_alpha,
        "mode_gamma": mode_gamma,
        "mode_beta": mode_beta,
        "mode_e_vector": mode_e,
        "mode_k_vector": mode_k,
        "mode_h_vector": mode_h,
        "mode_boundary_amplitude_scale": mode_scale,
        "mode_boundary_phase": boundary_phase,
        "mode_outgoing_amplitude_reconstructed_at_boundary": boundary_amp_reconstruction,
        **amplitudes,
    }
    return mode_rows, mode_hash, arrays


def restore_reference(
    label: str, output_root: Path, *,
    post_selection_record: Path | None = None,
    assets_manifest: Path | None = None,
) -> dict[str, object]:
    if MPI.COMM_WORLD.size != 1:
        raise RuntimeError("historical reference restoration is qualified for MPI1 only")
    started = time.perf_counter()
    entry = _load_inventory_entry(label, post_selection_record=post_selection_record,
                                  assets_manifest=assets_manifest)
    out_dir = output_root / label
    if out_dir.exists():
        raise FileExistsError(
            f"refusing to overwrite an earlier reference attempt: {out_dir}"
        )
    out_dir.mkdir(parents=True, exist_ok=True)
    print(json.dumps({"label": label, "stage": "begin", "output": str(out_dir)}), flush=True)
    copied = _copy_verified_assets(label, entry, out_dir)
    copied_seconds = time.perf_counter() - started
    print(
        json.dumps({"label": label, "stage": "assets_verified", "seconds": copied_seconds}),
        flush=True,
    )

    config = json.loads(copied["resolved_config.json"].read_text(encoding="utf-8"))
    cfg = _configure_historical_direct_route(config, entry)
    mesh_dir = out_dir / "restored_mesh"
    mesh_data = build_airbox_mesh_3d(cfg, mesh_dir)
    mesh = mesh_data.mesh
    if mesh.comm.size != 1:
        raise RuntimeError("the reconstructed mesh is unexpectedly distributed")
    axis_values = {
        axis: np.unique(np.asarray(mesh.geometry.x[:, index], dtype=np.float64))
        for index, axis in enumerate(("x", "y", "z"))
    }
    for axis in ("x", "y", "z"):
        expected = np.asarray(entry["axis_values_nm"][axis], dtype=np.float64)
        if not np.array_equal(axis_values[axis], expected):
            raise ValueError(f"reconstructed mesh {axis}-axis differs from saved coordinates")
    global_cells = int(mesh.topology.index_map(mesh.topology.dim).size_global)
    expected_cells = int(np.prod(np.asarray(entry["axes"], dtype=np.int64)))
    if global_cells != expected_cells:
        raise ValueError(f"reconstructed cell count {global_cells} != {expected_cells}")
    for axis in ("x", "y", "z"):
        if len(axis_values[axis]) != int(entry["axes"][("x", "y", "z").index(axis)]) + 1:
            raise ValueError(f"reconstructed mesh {axis}-axis cell count differs")
    mesh_seconds = time.perf_counter() - started - copied_seconds
    print(
        json.dumps(
            {"label": label, "stage": "mesh_verified", "global_cells": global_cells, "seconds": mesh_seconds}
        ),
        flush=True,
    )

    mesh.topology.create_connectivity(mesh.topology.dim, 0)
    mesh.topology.create_entity_permutations()
    space = _create_nedelec_space(mesh, cfg)
    floquet = build_double_floquet_mpc(space, mesh_data, cfg)
    actual_fe = None
    if label in {"Y5_1", "Y3", "Y3_2"}:
        storage_rows = int(space.dofmap.index_map.size_global * space.dofmap.index_map_bs)
        slave_rows = np.asarray(floquet.mpc.slaves, dtype=np.int64)
        if len(np.unique(slave_rows)) != len(slave_rows):
            raise ValueError("restored Floquet slave rows are not unique")
        independent_rows = storage_rows - len(slave_rows)
        nx, ny, nz = (len(axis_values[a]) - 1 for a in ("x", "y", "z"))
        degree = int(cfg.nedelec_degree)
        interior = global_cells * 3 * degree * (degree - 1) ** 2
        edges = nx * ny * (3 * nz + 2)
        faces = nx * ny * (3 * nz + 1)
        trace_formula = edges * degree + faces * 2 * degree * (degree - 1)
        if independent_rows != trace_formula + interior:
            raise ValueError("restored independent Floquet rows differ from periodic entity count")
        actual_fe = {"storage_rows": storage_rows, "actual_Floquet_slave_rows": len(slave_rows),
                     "independent_FE_from_restored_constraint_rows": independent_rows,
                     "cell_interiors": interior, "independent_trace": independent_rows - interior,
                     "periodic_entity_trace_crosscheck": trace_formula,
                     "scope": "MPI1 actual restored space minus unique Floquet slaves; independent periodic entity crosscheck, not coefficient length renamed as FE"}
    floquet_seconds = time.perf_counter() - started - copied_seconds - mesh_seconds
    print(
        json.dumps({"label": label, "stage": "space_and_floquet_ready", "seconds": floquet_seconds}),
        flush=True,
    )

    storage_path = copied[STORAGE_NAME]
    storage = np.load(storage_path, allow_pickle=False)
    storage = np.asarray(storage)
    if storage.dtype != np.dtype(np.complex128):
        raise ValueError(f"historical FE storage dtype is {storage.dtype}, expected complex128")
    if tuple(storage.shape) != tuple(entry["storage"]["shape"]):
        raise ValueError("historical FE storage shape differs from the inventory")
    field = restore_p0_full_field(floquet, storage, name=f"{label}_restored_E_total")
    slave_ids = np.asarray(floquet.mpc.slaves, dtype=np.int64).reshape(-1)
    if slave_ids.size and (slave_ids.min() < 0 or slave_ids.max() >= storage.size):
        raise ValueError("Floquet slave indices are outside the stored FE coefficient vector")
    input_slaves_zero = bool(not slave_ids.size or np.all(storage[slave_ids] == 0.0))
    if not input_slaves_zero:
        raise ValueError("saved historical storage is not zero on the Floquet slave rows")
    if field.x.array.shape != storage.shape:
        raise ValueError("restored full field storage shape differs from the input vector")
    field.x.scatter_forward()
    restore_seconds = time.perf_counter() - started - copied_seconds - mesh_seconds - floquet_seconds
    print(
        json.dumps(
            {
                "label": label,
                "stage": "full_field_recovered",
                "storage_size": int(storage.size),
                "seconds": restore_seconds,
            }
        ),
        flush=True,
    )

    modes, mode_rows, mode_hash = build_dynamic_mode_inventory(cfg)
    orders_payload = json.loads(
        copied["numerical_output/dtn_port_diffraction_orders_3d.json"].read_text(
            encoding="utf-8"
        )
    )
    auxiliary_rows = json.loads(
        copied["numerical_output/dtn_auxiliary_amplitudes_3d.json"].read_text(
            encoding="utf-8"
        )
    )
    _mode_rows, mode_hash, modal_arrays = _verify_historical_modes(
        modes, mode_rows, mode_hash, entry, orders_payload, auxiliary_rows
    )

    samples_path = copied["numerical_output/full3d_reference_samples.npz"]
    with np.load(samples_path, allow_pickle=False) as archive:
        x_nm = np.asarray(archive["x_nm"], dtype=np.float64)
        y_nm = np.asarray(archive["y_nm"], dtype=np.float64)
        z_nm = np.asarray(archive["z_nm"], dtype=np.float64)
        expected_e = np.asarray(archive["E_V_per_m"], dtype=np.complex128)
        expected_h = np.asarray(archive["H_A_per_m"], dtype=np.complex128)
    expected_shape = (len(z_nm), len(y_nm), len(x_nm), 3)
    if expected_e.shape != expected_shape or expected_h.shape != expected_shape:
        raise ValueError("historical sample archive has an unexpected shape")
    if int(np.prod(expected_shape[:-1])) != 12800:
        raise ValueError("historical reference sample count differs from 12,800")
    zz, yy, xx = np.meshgrid(z_nm, y_nm, x_nm, indexing="ij")
    points_nm = np.column_stack((xx.ravel(), yy.ravel(), zz.ravel()))
    z_sides = reference_plane_sides(len(z_nm), len(x_nm) * len(y_nm))

    field_export = prepare_cell_local_vector_field_export(field)
    e_code_direct = _sample_distributed_function(field, points_nm, z_sides)
    e_code_dgq6 = _sample_distributed_function(
        field_export.electric_dgq6, points_nm, z_sides
    )
    curl_code = _sample_distributed_function(
        field_export.curl_electric_dgq6, points_nm, z_sides
    )
    e_v_per_m = (
        e_code_direct.reshape(expected_shape) * cfg.electric_field_scale_V_per_m
    )
    e_dgq6_v_per_m = (
        e_code_dgq6.reshape(expected_shape) * cfg.electric_field_scale_V_per_m
    )
    h_a_per_m = magnetic_field_from_electric_curl(
        curl_code,
        magnetic_field_scale_A_per_m=cfg.magnetic_field_scale_A_per_m,
        k0_per_nm=cfg.k0,
        mu_r=cfg.mu_r,
    ).reshape(expected_shape)
    e_sample_relative = _relative_l2(e_v_per_m, expected_e)
    h_sample_relative = _relative_l2(h_a_per_m, expected_h)
    e_dgq6_transfer_relative = _relative_l2(e_dgq6_v_per_m, e_v_per_m)
    sample_identity_pass = (
        e_sample_relative <= 1.0e-8
        and h_sample_relative <= 1.0e-8
        and e_dgq6_transfer_relative <= 1.0e-10
    )
    sample_seconds = time.perf_counter() - started - copied_seconds - mesh_seconds - floquet_seconds - restore_seconds
    print(
        json.dumps(
            {
                "label": label,
                "stage": "historical_samples_recomputed",
                "E_relative_L2": e_sample_relative,
                "H_relative_L2": h_sample_relative,
                "DGQ6_E_relative_L2": e_dgq6_transfer_relative,
                "seconds": sample_seconds,
            }
        ),
        flush=True,
    )

    cell_map = mesh.topology.index_map(mesh.topology.dim)
    cell_connectivity = mesh.topology.connectivity(mesh.topology.dim, 0)
    if cell_connectivity is None:
        raise RuntimeError("restored mesh has no cell-to-vertex connectivity")
    dofmap = field.function_space.dofmap
    dof_index_map = dofmap.index_map
    cell_owned_ids = cell_map.local_to_global(
        np.arange(cell_map.size_local, dtype=np.int32)
    )
    dof_owned_ids = dof_index_map.local_to_global(
        np.arange(dof_index_map.size_local, dtype=np.int32)
    )
    arrays: dict[str, np.ndarray] = {
        "historical_zero_slave_storage_coefficients": np.asarray(storage).copy(),
        "recovered_full_local_coefficients": np.asarray(field.x.array).copy(),
        "mesh_geometry_coordinates_nm": np.asarray(mesh.geometry.x).copy(),
        "mesh_geometry_dofmap": np.asarray(mesh.geometry.dofmap).copy(),
        "mesh_owned_cell_global_ids": np.asarray(cell_owned_ids, dtype=np.int64),
        "mesh_cell_vertex_dofmap": np.asarray(cell_connectivity.array).copy(),
        "p6_function_space_cell_dofmap": np.asarray(dofmap.list).copy(),
        "p6_owned_global_dof_block_ids": np.asarray(dof_owned_ids, dtype=np.int64),
        "p6_ghost_global_dof_block_ids": np.asarray(dof_index_map.ghosts, dtype=np.int64).copy(),
        "sample_points_nm": points_nm,
        "sample_z_side_selectors": z_sides,
        "sample_E_V_per_m_recomputed_direct": e_v_per_m,
        "sample_E_V_per_m_recomputed_DGQ6": e_dgq6_v_per_m,
        "sample_H_A_per_m_recomputed": h_a_per_m,
        "sample_E_V_per_m_historical": expected_e,
        "sample_H_A_per_m_historical": expected_h,
        "sample_curl_E_code_recomputed": curl_code.reshape(expected_shape),
        "sample_x_nm": x_nm,
        "sample_y_nm": y_nm,
        "sample_z_nm": z_nm,
        **modal_arrays,
    }
    bundle_path = out_dir / "recovered_reference_bundle.npz"
    np.savez_compressed(bundle_path, **arrays)

    cfg_identity = {
        "model_id": config["model_id"],
        "wavelength_nm": float(cfg.lambda0),
        "indices": {
            "air": [float(complex(cfg.n_air).real), float(complex(cfg.n_air).imag)],
            "substrate": [float(complex(cfg.substrate_index).real), float(complex(cfg.substrate_index).imag)],
            "grating": [float(complex(cfg.grating_index).real), float(complex(cfg.grating_index).imag)],
        },
        "incidence": {
            "theta_deg": float(cfg.incident_theta_deg),
            "phi_deg": float(cfg.incident_phi_deg),
            "polarization": str(cfg.polarization_kind),
            "amplitude": [float(complex(cfg.incident_amplitude).real), float(complex(cfg.incident_amplitude).imag)],
            "wavevector": [[float(complex(value).real), float(complex(value).imag)] for value in cfg.wavevector],
        },
        "mesh_axes_nm": {axis: values.tolist() for axis, values in axis_values.items()},
        "global_cells": global_cells,
        "nedelec_degree": int(cfg.nedelec_degree),
        "floquet_constraint_mode": str(floquet.constraint_mode_resolved),
        "storage_recovery": "zero_slave_storage -> scatter_forward/homogenize/backsubstitution/scatter_forward -> full FE coefficients",
        "storage_shape": list(storage.shape),
        "recovered_field_shape": list(field.x.array.shape),
        "floquet_slave_count": int(slave_ids.size),
        "input_storage_zero_on_slaves": input_slaves_zero,
        "ordered_mode_count": len(modes),
        "ordered_mode_inventory_sha256": mode_hash,
        "historical_modal_basis": {
            "scale_policy": "implicit unscaled Task40 basis; historical records omit scale fields",
            "minimum_boundary_amplitude_scale": float(np.min(modal_arrays["mode_boundary_amplitude_scale"])),
            "maximum_boundary_amplitude_scale": float(np.max(modal_arrays["mode_boundary_amplitude_scale"])),
            "comparison_amplitude_vector": "outgoing_amplitude_at_boundary from saved 612-row Task40 output; no phase fit",
            "auxiliary_order_row_match": "all 612 keys and amplitude/phase fields compared exactly",
            "max_boundary_amplitude_product_difference": float(
                np.max(
                    np.abs(
                        modal_arrays["mode_outgoing_amplitude_reconstructed_at_boundary"]
                        - modal_arrays["outgoing_amplitude_at_boundary"]
                    )
                )
            ),
        },
        "quadrature_and_cutoff": {
            "surface_and_incident_degree": int(cfg.stage4_dtn_quadrature_degree),
            "volume_degree": int(cfg.stage4_volume_quadrature_degree),
            "volume_rule": str(cfg.stage4_volume_quadrature_rule),
            "cutoff_policy": str(cfg.stage4_dtn_sparse_cutoff_policy),
            "cutoff_relative_tolerance": float(cfg.stage4_dtn_sparse_cutoff_relative_tolerance),
            "cutoff_identity_sha256": str(entry["residuals"]["dtn_sparse_cutoff_identity_sha256"]),
        },
        "historical_power_diagnostic": entry["power"],
        "field_sample_identity": {
            "point_count": int(points_nm.shape[0]),
            "array_shape": list(expected_shape),
            "E_relative_L2_vs_archived_V_per_m": e_sample_relative,
            "H_relative_L2_vs_archived_A_per_m": h_sample_relative,
            "DGQ6_E_transfer_relative_L2": e_dgq6_transfer_relative,
            "pass_tolerances": {
                "E_and_H_relative_L2": 1.0e-8,
                "DGQ6_E_transfer_relative_L2": 1.0e-10,
            },
            "status": "pass" if sample_identity_pass else "failed",
        },
        "qualification_boundary": "restoration and historical sparse-sample identity only; not Task43 reference qualification, full-domain G, or four-sidewall qualification",
    }
    if label in {"Y5_1", "Y3", "Y3_2"}:
        binding = _post_selection_binding(post_selection_record)
        cfg_identity.update({
            "run_role": "post_selection_validation_only",
            "selection_eligible": False,
            "frozen_selection_sha256": binding["selection_sha256"],
            "selection_stop_record_sha256": binding["stop_sha256"],
            "assets_manifest_sha256": _sha256_file(assets_manifest),
            "actual_FE_from_restored_constraints": actual_fe,
        })
    record = {
        "schema_version": 1,
        "label": label,
        "role": entry["role"],
        "source_directory": entry["directory"],
        "source_sha": entry["source_sha"],
        "input_artifacts": {
            relative: {
                "source": str(Path(entry["supporting_artifact_identities"][relative]["path"])),
                "copied": str(path),
                "sha256": _sha256_file(path),
            }
            for relative, path in copied.items()
            if relative in entry["supporting_artifact_identities"]
        }
        | {
            STORAGE_NAME: {
                "source": str(Path(entry["storage"]["path"])),
                "copied": str(storage_path),
                "sha256": _sha256_file(storage_path),
            }
        },
        "source_module_sha256": {
            str(Path(__import__(module_name, fromlist=["__file__"]).__file__).resolve()): _sha256_file(
                Path(__import__(module_name, fromlist=["__file__"]).__file__).resolve()
            )
            for module_name in (
                "src.io.input_validation",
                "src.geometry.mesh_builder_3d",
                "src.common.modes_3d",
                "src.constraints.floquet_3d",
                "src.postprocessing.full3d_reference",
                "src.postprocessing.physical_field_sampling",
                "src.postprocessing.physical_field_comparison",
                "src.solvers.common_3d_solve",
                "src.solvers.fullspace_same_mesh_hcurl_pmg_physical",
                "src.solvers.fullspace_dtn_action",
            )
        },
        "execution_identity": {
            "git_head": subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=ROOT,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip(),
            "git_status_short": subprocess.run(
                ["git", "status", "--short"],
                cwd=ROOT,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.splitlines(),
            "importer_sha256": _sha256_file(Path(__file__).resolve()),
            "python_executable": sys.executable,
            "mpi_size": int(MPI.COMM_WORLD.size),
        },
        "recovered_bundle": {
            "path": str(bundle_path),
            "sha256": _sha256_file(bundle_path),
            "array_identities": {
                name: _array_identity(value) for name, value in arrays.items()
            },
        },
        "resolved_identity": cfg_identity,
        "timing_seconds": {
            "asset_copy_and_verification": copied_seconds,
            "mesh_build_and_axis_check": mesh_seconds,
            "space_and_floquet_setup": floquet_seconds,
            "field_recovery": restore_seconds,
            "mode_and_sample_identity": sample_seconds,
            "total": time.perf_counter() - started,
        },
        "status": (
            "RESTORATION_IDENTITY_PASS_NOT_TASK43_QUALIFIED"
            if sample_identity_pass
            else "RESTORATION_IDENTITY_FAILED"
        ),
    }
    record_path = out_dir / "restore_identity_record.json"
    record_path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if not sample_identity_pass:
        raise RuntimeError(f"{label}: restored field did not match its historical samples; see {record_path}")
    print(
        json.dumps(
            {
                "label": label,
                "status": record["status"],
                "mesh_cells": global_cells,
                "active_modes": len(modes),
                "mode_sha256": mode_hash,
                "E_relative_L2": e_sample_relative,
                "H_relative_L2": h_sample_relative,
                "bundle": str(bundle_path),
                "record": str(record_path),
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    return record


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", choices=("Y6_1", "Y6_2", "Y5_1", "Y3", "Y3_2"), required=True)
    parser.add_argument("--attempt-id", default="attempt1")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--post-selection-record", type=Path)
    parser.add_argument("--assets-manifest", type=Path)
    args = parser.parse_args()
    if not args.attempt_id or any(
        char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
        for char in args.attempt_id
    ):
        raise ValueError("attempt id may contain only letters, digits, underscore and hyphen")
    restore_reference(args.label, (args.output_root / args.attempt_id).resolve(),
                      post_selection_record=args.post_selection_record,
                      assets_manifest=args.assets_manifest)


if __name__ == "__main__":
    main()
