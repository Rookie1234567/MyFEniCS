"""Small contracts for the Task42 A2 shared Hybrid-direct route."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import tomllib
from mpi4py import MPI

from benchmarks.run_task032_phase6_augmented import (
    _TASK039_DIRECT_PAYLOAD_KEYS,
    _task039_direct_payload,
)
from src.common.task42_phase_admission import (
    TASK42_HYBRID_A2_PHASE_OBJECTS,
    require_task42_phase_admission,
    task42_assembly_stage_gate_adapter,
    task42_phase_inventory,
)
from src.io import build_execution_plan, load_and_resolve
from src.io.execution_plan import TASK42_HYBRID_DIRECT_ADAPTER
from src.io.input_validation import (
    TASK42_13P5_HYBRID_MODEL_ID,
    task42_hybrid_direct_profile_errors,
)
from src.io.task42_hybrid_budget import (
    TASK42_HYBRID_PHASE_BUDGET_SCHEMA,
    load_task42_hybrid_phase_budget,
    phase_budget_for_job,
    phase_budget_for_rank,
    task42_phase_budget_basis_sha256,
)
from src.postprocessing.hybrid_direct_output import (
    validate_external_auxiliary_mapping,
    validate_external_key_rows,
    validate_hybrid_sampled_field_arrays,
    write_task42_hybrid_direct_payload,
    write_task42_hybrid_direct_payload_collectively,
)
from src.runners import task038_input_worker
from src.runners.task42_hybrid_direct import run_task42_hybrid_direct

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
TASK42_A2_INPUT = (
    REPOSITORY_ROOT
    / "input/official/task42hybrid_az90_50x50_17x20_0p7nm/"
    / "13p5nm_p6h10_m120_hybrid_direct_mpi8.dat"
)


def _phase_manifest(specification, *, mpi_size: int) -> dict[str, object]:
    phases: dict[str, object] = {}
    for phase in TASK42_HYBRID_A2_PHASE_OBJECTS:
        inventory = task42_phase_inventory(phase)
        components = []
        for component in inventory["components"]:
            components.append(
                {
                    "name": component["name"],
                    "scope": component["scope"],
                    "unit": "bytes",
                    "formula": component["formula"],
                    "lifetime": component["lifetime"],
                    "allocation_boundary": component["allocation_boundary"],
                    "delta_bytes_by_rank": [128] * mpi_size,
                    "sizing_basis_by_rank": [
                        {
                            "fixture_source": "explicit small allocation inventory",
                            "component": component["name"],
                            "mpi_rank": rank,
                        }
                        for rank in range(mpi_size)
                    ],
                    "uncertainty": "fixture only; not an A2 sizing estimate",
                }
            )
        phases[phase] = {"components": components}
    payload = specification.as_jsonable()
    return {
        "schema": TASK42_HYBRID_PHASE_BUDGET_SCHEMA,
        "model_id": TASK42_13P5_HYBRID_MODEL_ID,
        "run_id": specification.identity["run_id"],
        "comparison_group": specification.identity["comparison_group"],
        "budget_basis_sha256": payload["provenance"][
            "phase_budget_basis_sha256"
        ],
        "physical_model_sha256": specification.physical_model_sha256,
        "material_identity_sha256": specification.derived[
            "material_provenance"
        ]["material_identity_sha256"],
        "source_sha": "a" * 40,
        "mpi_size": mpi_size,
        "phases": phases,
    }


def _reject_task42_phase(phase, _inventory):
    return {"pass": False, "errors": [f"fixture refuses {phase}"]}


def test_task42_a2_input_routes_to_its_own_p6_hybrid_adapter(tmp_path: Path) -> None:
    specification = load_and_resolve(TASK42_A2_INPUT)
    assert specification.identity["model_id"] == TASK42_13P5_HYBRID_MODEL_ID
    assert specification.method["kind"] == "hybrid_direct"
    assert specification.solver["linear_solver"] == "direct"
    assert specification.method["requested_modes_per_direction"] == 120
    assert specification.discretization["nedelec_degree"] == 6
    assert task42_hybrid_direct_profile_errors(specification.as_jsonable()) == []

    plan = build_execution_plan(
        specification,
        tmp_path / "run",
        source_sha="a" * 40,
        python_executable=REPOSITORY_ROOT / ".venv/bin/python",
        mpiexec_command="/usr/bin/mpiexec",
    )
    assert plan.method == "hybrid_direct"
    assert plan.adapter_identity == TASK42_HYBRID_DIRECT_ADAPTER
    assert plan.adapter_identity != "task039.hybrid_direct"
    assert plan.adapter_available is True


@pytest.mark.parametrize(
    ("path", "mutator"),
    [
        ("model_id", lambda config: config.__setitem__("model_id", "task039_wrong")),
        (
            "discretization.nedelec_degree",
            lambda config: config["discretization"].__setitem__("nedelec_degree", 5),
        ),
        (
            "materials.n_grating",
            lambda config: config["materials"].__setitem__("n_grating", [1.0, 0.0]),
        ),
        (
            "geometry.period_x_nm",
            lambda config: config["geometry"].__setitem__("period_x_nm", 25.0),
        ),
    ],
)
def test_task42_a2_profile_refuses_other_identity_or_physics(path, mutator) -> None:
    specification = load_and_resolve(TASK42_A2_INPUT)
    config = specification.as_jsonable()
    mutator(config)
    errors = task42_hybrid_direct_profile_errors(config)
    assert errors
    assert any(error_path == path for error_path, _message in errors)


def test_task42_pending_phase_refusal_precedes_a_sentinel_allocation() -> None:
    inventory = task42_phase_inventory("hybrid_augmented_matrix")
    assert inventory["status"] == "pending-sizing"
    assert inventory["components"]
    assert all(component["delta_bytes"] is None for component in inventory["components"])

    allocations: list[str] = []
    with pytest.raises(TypeError, match="has no resource gate callback"):
        require_task42_phase_admission(
            None,
            "hybrid_augmented_matrix",
            inventory,
        )
    with pytest.raises(RuntimeError, match="refused before allocation"):
        require_task42_phase_admission(
            lambda _phase, _inventory: {"pass": False, "errors": ["unknown Delta"]},
            "hybrid_augmented_matrix",
            inventory,
        )
    assert allocations == []


def test_task42_budget_is_source_bound_positive_and_per_rank(tmp_path: Path) -> None:
    specification = load_and_resolve(TASK42_A2_INPUT)
    inventory = task42_phase_inventory("public_worker_spawn")
    assert inventory["status"] == "pending-sizing"
    assert all(
        isinstance(component["sizing_basis"], str)
        for component in inventory["components"]
    )
    manifest = _phase_manifest(specification, mpi_size=2)
    raw = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    path = tmp_path / "phase_budget.json"
    path.write_bytes(raw)
    execution = {
        "phase_budget_manifest": str(path.resolve()),
        "phase_budget_manifest_sha256": hashlib.sha256(raw).hexdigest(),
    }
    loaded, observed_sha, error = load_task42_hybrid_phase_budget(
        execution,
        model_id=TASK42_13P5_HYBRID_MODEL_ID,
        run_id=str(specification.identity["run_id"]),
        comparison_group=str(specification.identity["comparison_group"]),
        budget_basis_sha256=specification.phase_budget_basis_sha256,
        physical_model_sha256=specification.physical_model_sha256,
        material_identity_sha256=specification.derived["material_provenance"][
            "material_identity_sha256"
        ],
        source_sha="a" * 40,
        mpi_size=2,
    )
    assert error is None
    assert observed_sha == hashlib.sha256(raw).hexdigest()
    whole_job_delta, _bound_inventory, errors = phase_budget_for_job(
        loaded,
        stage="public_worker_spawn",
        expected_inventory=inventory,
        mpi_size=2,
    )
    assert not errors
    assert whole_job_delta == 256 * len(inventory["components"])
    rank_delta, rank_inventory, rank_errors = phase_budget_for_rank(
        loaded,
        stage="public_worker_spawn",
        inventory=inventory,
        rank=0,
        mpi_size=2,
    )
    assert not rank_errors
    assert rank_delta == 128 * len(inventory["components"])
    assert rank_inventory["status"] == "budget-bound"

    # A pending description is not compared as if it were a measured basis;
    # both the whole-job pre-spawn check and the per-rank check use the
    # nonempty, hash-bound prediction mappings in the manifest.
    missing_rank_basis = json.loads(raw)
    first_phase = missing_rank_basis["phases"]["public_worker_spawn"]
    first_phase["components"][0].pop("sizing_basis_by_rank")
    missing_basis_path = tmp_path / "missing_rank_basis.json"
    missing_basis_raw = json.dumps(
        missing_rank_basis, sort_keys=True, separators=(",", ":")
    ).encode()
    missing_basis_path.write_bytes(missing_basis_raw)
    missing_basis_manifest, _sha, missing_basis_error = load_task42_hybrid_phase_budget(
        {
            "phase_budget_manifest": str(missing_basis_path.resolve()),
            "phase_budget_manifest_sha256": hashlib.sha256(
                missing_basis_raw
            ).hexdigest(),
        },
        model_id=TASK42_13P5_HYBRID_MODEL_ID,
        run_id=str(specification.identity["run_id"]),
        comparison_group=str(specification.identity["comparison_group"]),
        budget_basis_sha256=specification.phase_budget_basis_sha256,
        physical_model_sha256=specification.physical_model_sha256,
        material_identity_sha256=specification.derived["material_provenance"][
            "material_identity_sha256"
        ],
        source_sha="a" * 40,
        mpi_size=2,
    )
    assert missing_basis_error is None
    missing_job_delta, _inventory, missing_job_errors = phase_budget_for_job(
        missing_basis_manifest,
        stage="public_worker_spawn",
        expected_inventory=inventory,
        mpi_size=2,
    )
    assert missing_job_delta is None
    assert any("rank_sizing_basis_invalid" in item for item in missing_job_errors)
    missing_rank_delta, _inventory, missing_rank_errors = phase_budget_for_rank(
        missing_basis_manifest,
        stage="public_worker_spawn",
        inventory=inventory,
        rank=0,
        mpi_size=2,
    )
    assert missing_rank_delta is None
    assert any("rank_sizing_basis_invalid" in item for item in missing_rank_errors)

    missing_manifest = load_task42_hybrid_phase_budget(
        {},
        model_id=TASK42_13P5_HYBRID_MODEL_ID,
        run_id=str(specification.identity["run_id"]),
        comparison_group=str(specification.identity["comparison_group"]),
        budget_basis_sha256=specification.phase_budget_basis_sha256,
        physical_model_sha256=specification.physical_model_sha256,
        material_identity_sha256=specification.derived["material_provenance"][
            "material_identity_sha256"
        ],
        source_sha="a" * 40,
        mpi_size=2,
    )
    assert missing_manifest == (None, None, None)
    no_budget_delta, _pending, no_budget_errors = phase_budget_for_job(
        missing_manifest[0],
        stage="public_worker_spawn",
        expected_inventory=inventory,
        mpi_size=2,
    )
    assert no_budget_delta is None
    assert "phase_budget_manifest_missing_pending_sizing" in no_budget_errors

    wrong_source = load_task42_hybrid_phase_budget(
        execution,
        model_id=TASK42_13P5_HYBRID_MODEL_ID,
        run_id=str(specification.identity["run_id"]),
        comparison_group=str(specification.identity["comparison_group"]),
        budget_basis_sha256=specification.phase_budget_basis_sha256,
        physical_model_sha256=specification.physical_model_sha256,
        material_identity_sha256=specification.derived["material_provenance"][
            "material_identity_sha256"
        ],
        source_sha="b" * 40,
        mpi_size=2,
    )
    assert wrong_source[0] is None
    assert "source_sha mismatch" in str(wrong_source[2])

    wrong_input = load_task42_hybrid_phase_budget(
        execution,
        model_id=TASK42_13P5_HYBRID_MODEL_ID,
        run_id=str(specification.identity["run_id"]),
        comparison_group=str(specification.identity["comparison_group"]),
        budget_basis_sha256="d" * 64,
        physical_model_sha256=specification.physical_model_sha256,
        material_identity_sha256=specification.derived["material_provenance"][
            "material_identity_sha256"
        ],
        source_sha="a" * 40,
        mpi_size=2,
    )
    assert wrong_input[0] is None
    assert "budget_basis_sha256 mismatch" in str(wrong_input[2])

    incomplete = json.loads(raw)
    incomplete["phases"].pop("qep_cross_section_mesh")
    incomplete_path = tmp_path / "incomplete_phase_budget.json"
    incomplete_raw = json.dumps(incomplete, sort_keys=True, separators=(",", ":")).encode()
    incomplete_path.write_bytes(incomplete_raw)
    incomplete_result = load_task42_hybrid_phase_budget(
        {
            "phase_budget_manifest": str(incomplete_path.resolve()),
            "phase_budget_manifest_sha256": hashlib.sha256(incomplete_raw).hexdigest(),
        },
        model_id=TASK42_13P5_HYBRID_MODEL_ID,
        run_id=str(specification.identity["run_id"]),
        comparison_group=str(specification.identity["comparison_group"]),
        budget_basis_sha256=specification.phase_budget_basis_sha256,
        physical_model_sha256=specification.physical_model_sha256,
        material_identity_sha256=specification.derived["material_provenance"][
            "material_identity_sha256"
        ],
        source_sha="a" * 40,
        mpi_size=2,
    )
    assert incomplete_result[0] is None
    assert "complete A2 phase set" in str(incomplete_result[2])


def test_task42_budget_manifest_closes_over_real_dat_without_sha_cycle(
    tmp_path: Path,
) -> None:
    base_text = TASK42_A2_INPUT.read_text(encoding="utf-8")
    base_specification = load_and_resolve(TASK42_A2_INPUT)
    basis_sha = base_specification.phase_budget_basis_sha256
    assert basis_sha == task42_phase_budget_basis_sha256(
        tomllib.loads(base_text)
    )
    manifest = _phase_manifest(base_specification, mpi_size=2)
    manifest_path = tmp_path / "small_phase_budget.json"
    manifest_raw = json.dumps(
        manifest, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    manifest_path.write_bytes(manifest_raw)
    inserted = (
        "[execution]\n"
        f'phase_budget_manifest = "{manifest_path.resolve()}"\n'
        "phase_budget_manifest_sha256 = "
        f'"{hashlib.sha256(manifest_raw).hexdigest()}"\n'
    )
    dat_path = tmp_path / "a2_with_external_budget_binding.dat"
    dat_path.write_text(base_text.replace("[execution]\n", inserted, 1), encoding="utf-8")
    specification = load_and_resolve(dat_path)
    assert specification.input_sha256 == hashlib.sha256(dat_path.read_bytes()).hexdigest()
    assert specification.input_sha256 != base_specification.input_sha256
    assert specification.phase_budget_basis_sha256 == basis_sha

    def load_current(*, source_sha="a" * 40, mpi_size=2, basis=basis_sha):
        return load_task42_hybrid_phase_budget(
            specification.execution,
            model_id=TASK42_13P5_HYBRID_MODEL_ID,
            run_id=str(specification.identity["run_id"]),
            comparison_group=str(specification.identity["comparison_group"]),
            budget_basis_sha256=basis,
            physical_model_sha256=specification.physical_model_sha256,
            material_identity_sha256=specification.derived["material_provenance"][
                "material_identity_sha256"
            ],
            source_sha=source_sha,
            mpi_size=mpi_size,
        )

    loaded, manifest_sha, error = load_current()
    assert error is None
    assert manifest_sha == hashlib.sha256(manifest_raw).hexdigest()
    assert loaded["budget_basis_sha256"] == basis_sha
    wrong_physics_basis = task42_phase_budget_basis_sha256(
        {
            **tomllib.loads(dat_path.read_text(encoding="utf-8")),
            "geometry": {
                **tomllib.loads(dat_path.read_text(encoding="utf-8"))["geometry"],
                "period_x_nm": 51.0,
            },
        }
    )
    assert load_current(basis=wrong_physics_basis)[2] == (
        "phase budget manifest budget_basis_sha256 mismatch"
    )
    assert "source_sha mismatch" in str(load_current(source_sha="b" * 40)[2])
    assert "mpi_size mismatch" in str(load_current(mpi_size=1)[2])
    manifest_path.write_bytes(manifest_raw + b"\n")
    assert load_current()[2] == "phase budget manifest SHA mismatch"


def test_task42_pending_inventory_uses_hash_bound_predicted_basis_for_job_and_rank(
    tmp_path: Path,
) -> None:
    specification = load_and_resolve(TASK42_A2_INPUT)
    inventory = task42_phase_inventory("public_worker_spawn")
    assert inventory["status"] == "pending-sizing"
    assert all(isinstance(item["sizing_basis"], str) for item in inventory["components"])
    manifest = _phase_manifest(specification, mpi_size=2)
    delta, _bound, errors = phase_budget_for_job(
        manifest,
        stage="public_worker_spawn",
        expected_inventory=inventory,
        mpi_size=2,
    )
    assert not errors
    assert delta == 256 * len(inventory["components"])
    for rank in range(2):
        rank_delta, _rank_bound, rank_errors = phase_budget_for_rank(
            manifest,
            stage="public_worker_spawn",
            inventory=inventory,
            rank=rank,
            mpi_size=2,
        )
        assert not rank_errors
        assert rank_delta == 128 * len(inventory["components"])

    incomplete = json.loads(json.dumps(manifest))
    component = incomplete["phases"]["public_worker_spawn"]["components"][0]
    component["sizing_basis_by_rank"] = [component["sizing_basis_by_rank"][0], {}]
    _delta, _bound, errors = phase_budget_for_job(
        incomplete,
        stage="public_worker_spawn",
        expected_inventory=inventory,
        mpi_size=2,
    )
    assert any("rank_sizing_basis_invalid" in error for error in errors)


def test_task42_dynamic_assembly_delta_must_match_the_bound_manifest() -> None:
    captured: list[tuple[str, dict[str, object]]] = []

    def capture(stage, inventory):
        captured.append((stage, dict(inventory)))
        return {"pass": True}

    source_inventory = {
        "components": [
            {
                "name": "assembly_local_cell_dof_maps",
                "scope": "rank_local",
                "delta_bytes": 4096,
                "unit": "bytes",
                "basis": {"owned_cells": 2, "element_dimension": 8},
            }
        ],
        "estimate_uncertainty": "predicted from actual local dimensions",
        "evidence": {"mpi_rank": 0, "mpi_size": 1},
    }
    adapter = task42_assembly_stage_gate_adapter(capture, side="bottom")
    adapter("before_assembly_cell_maps_and_trace_expansion", 4096, source_inventory)
    stage, normalized = captured[0]
    assert stage == "local_bottom_before_assembly_cell_maps_and_trace_expansion"
    assert normalized["components"][0]["delta_bytes"] == 4096
    assert normalized["components"][0]["sizing_basis"] == {
        "owned_cells": 2,
        "element_dimension": 8,
    }

    phase = {
        "status": "budget-bound",
        "phase": stage,
        "components": [
            {
                **normalized["components"][0],
                "uncertainty": "fixture source-derived byte estimate; exact amount intentionally mismatched",
                "delta_bytes_by_rank": [4095],
                "sizing_basis_by_rank": [
                    normalized["components"][0]["sizing_basis"]
                ],
            }
        ],
    }
    local_delta, _receipt, errors = phase_budget_for_rank(
        {"phases": {stage: phase}, "manifest_file_sha256": "c" * 64},
        stage=stage,
        inventory=normalized,
        rank=0,
        mpi_size=1,
    )
    assert local_delta is None
    assert any("actual_Delta_mismatch" in item for item in errors)
    job_delta, _receipt, job_errors = phase_budget_for_job(
        {"phases": {stage: phase}, "manifest_file_sha256": "c" * 64},
        stage=stage,
        expected_inventory=normalized,
        mpi_size=1,
    )
    assert job_delta is None
    assert any("actual_sizing_basis_requires_rank" in item for item in job_errors)


def test_task42_assembly_side_and_rank_basis_are_distinct() -> None:
    stages = {
        "before_assembly_cell_maps_and_trace_expansion": "assembly_local_cell_dof_maps",
        "before_task42_trace_matrix_allocation": "task42_active_trace_petsc_aij_storage",
        "before_assembly_raw_cell_tensor_cache": "assembly_unique_raw_cell_tensor_cache_and_broadcast_buffer",
        "before_assembly_schur_recovery_and_lu_caches": "assembly_schur_recovery_lu_and_orientation_caches",
    }
    captured: dict[str, dict[int, dict[str, object]]] = {}
    deltas: dict[str, list[int]] = {}
    bases: dict[str, list[dict[str, int]]] = {}
    for side in ("bottom", "top"):
        for base_stage, component_name in stages.items():
            phase = f"local_{side}_{base_stage}"
            captured[phase] = {}
            deltas[phase] = []
            bases[phase] = []
            for rank in range(2):
                basis = {
                    "mpi_rank": rank,
                    "owned_cells": (rank + 1) * (2 if side == "bottom" else 7),
                    "local_rows": (rank + 3) * (5 if side == "bottom" else 11),
                    "local_geometry_classes": rank + (1 if side == "bottom" else 4),
                }
                amount = (
                    1024 + rank * 1024
                    if side == "bottom"
                    else 8192 + rank * 4096
                )
                source = {
                    "components": [
                        {
                            "name": component_name,
                            "scope": "rank_local",
                            "delta_bytes": amount,
                            "unit": "bytes",
                            "basis": basis,
                        }
                    ],
                    "estimate_uncertainty": "fixture dimensions vary by rank and side",
                    "evidence": {"mpi_rank": rank, "mpi_size": 2},
                }
                normalized_holder: list[dict[str, object]] = []

                def capture(_name, inventory, target=normalized_holder):
                    target.append(dict(inventory))
                    return {"pass": True}

                adapter = task42_assembly_stage_gate_adapter(capture, side=side)
                adapter(base_stage, amount, source)
                normalized = normalized_holder[0]
                captured[phase][rank] = normalized
                deltas[phase].append(amount)
                bases[phase].append(basis)

    manifest = {"phases": {}}
    for phase, rank_rows in captured.items():
        first_component = rank_rows[0]["components"][0]
        manifest["phases"][phase] = {
            "components": [
                {
                    **first_component,
                    "uncertainty": "fixture source-derived estimate with distinct side and rank bases",
                    "sizing_basis_by_rank": bases[phase],
                    "delta_bytes_by_rank": deltas[phase],
                }
            ]
        }
    for phase, rank_rows in captured.items():
        for rank in range(2):
            inventory = rank_rows[rank]
            delta, _bound, errors = phase_budget_for_rank(
                manifest,
                stage=phase,
                inventory=inventory,
                rank=rank,
                mpi_size=2,
            )
            assert not errors
            assert delta == deltas[phase][rank]

    phase = "local_bottom_before_assembly_cell_maps_and_trace_expansion"
    wrong_rank_basis = dict(manifest)
    wrong_rank_basis["phases"] = dict(manifest["phases"])
    wrong_rank_basis["phases"][phase] = {
        "components": [
            {
                **manifest["phases"][phase]["components"][0],
                "sizing_basis_by_rank": list(reversed(bases[phase])),
            }
        ]
    }
    _delta, _bound, errors = phase_budget_for_rank(
        wrong_rank_basis,
        stage=phase,
        inventory=captured[phase][0],
        rank=0,
        mpi_size=2,
    )
    assert any("sizing_basis_mismatch_rank_0" in error for error in errors)
    _delta, _bound, errors = phase_budget_for_rank(
        manifest,
        stage="local_top_before_assembly_cell_maps_and_trace_expansion",
        inventory=captured[phase][0],
        rank=0,
        mpi_size=2,
    )
    assert errors


def _task42_output_fixture(tmp_path: Path) -> dict[str, object]:
    sample_x = np.asarray([1.0, 3.0], dtype=np.float64)
    sample_y = np.asarray([2.0, 4.0, 6.0], dtype=np.float64)
    sample_z = np.asarray([-5.0, 10.0, 60.0, 125.0], dtype=np.float64)
    expected_keys = [
        {"side": "bottom", "m": 0, "n": 0, "polarization": "s"},
        {"side": "bottom", "m": 1, "n": 0, "polarization": "p"},
        {"side": "top", "m": 0, "n": 0, "polarization": "s"},
        {"side": "top", "m": 1, "n": 0, "polarization": "p"},
    ]
    inventory = {
        "source": "fixture",
        "count": len(expected_keys),
        "selection": {"strategy": "two declared fixture rows"},
        "keys": expected_keys,
    }
    inventory_sha = hashlib.sha256(
        json.dumps(
            inventory,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()
    inventory_identity = {
        "schema": "task42.a2.external-mode-inventory-identity.v1",
        "model_id": "task42.test.a2",
        "wavelength_nm": 13.5,
        "material_identity_sha256": "9" * 64,
        "inventory_sha256": inventory_sha,
        "key_count": len(expected_keys),
        "selection": inventory["selection"],
    }
    inventory["identity"] = inventory_identity
    digest = "e" * 64
    identity = {
        "model_id": "task42.test.a2",
        "run_id": "task42.test.run",
        "comparison_group": "task42.test.group",
        "input_sha256": digest,
        "physical_model_sha256": digest,
        "resolved_config_sha256": digest,
        "source_sha": "f" * 40,
        "wavelength_nm": 13.5,
        "requested_modes_per_direction": 2,
        "material_identity_sha256": "9" * 64,
        "material_record_sha256": digest,
        "canonical_export_prefix": "task42_hybrid_direct",
        "external_mode_inventory_identity": inventory_identity,
    }
    rows_in_q_order = [
        {
            **key,
            "auxiliary_index": index,
            "local_auxiliary_index": index if key["side"] == "bottom" else index - 2,
            "power_ratio": 0.0,
            "amplitude": [0.0, 0.0],
        }
        for index, key in enumerate(expected_keys)
    ]
    rows = [rows_in_q_order[index] for index in (3, 0, 2, 1)]
    return {
        "run_directory": tmp_path,
        "sample_x": sample_x,
        "sample_y": sample_y,
        "sample_z": sample_z,
        "electric": np.zeros((4, 3, 2, 3), dtype=np.complex128),
        "magnetic": np.ones((4, 3, 2, 3), dtype=np.complex128),
        "identity": identity,
        "external_mode_inventory": inventory,
        "external_diffraction_orders": rows,
        "modal_amplitudes": np.asarray(
            [1.0 + 0.0j, 0.5 + 0.0j, -1.0 + 0.0j, -0.5 + 0.0j]
        ),
        "external_auxiliary_amplitudes": {
            "bottom": np.asarray([10.0 + 1.0j, 11.0 + 1.0j]),
            "top": np.asarray([20.0 + 1.0j, 21.0 + 1.0j]),
        },
    }


def test_task42_shared_output_uses_coordinates_and_all_external_keys(tmp_path: Path) -> None:
    fixture = _task42_output_fixture(tmp_path)
    fields = validate_hybrid_sampled_field_arrays(
        sample_x=fixture["sample_x"],
        sample_y=fixture["sample_y"],
        sample_z=fixture["sample_z"],
        electric=fixture["electric"],
        magnetic=fixture["magnetic"],
    )
    inventory = fixture["external_mode_inventory"]
    rows = fixture["external_diffraction_orders"]
    assert len(validate_external_key_rows(inventory, rows)) == 4
    with pytest.raises(
        ValueError,
        match="actual external key rows differ from the complete declared inventory",
    ):
        validate_external_key_rows(inventory, rows[:1])
    with pytest.raises(ValueError, match="differ from the complete"):
        validate_external_key_rows(
            inventory,
            rows
            + [
                {
                    "side": "top",
                    "m": 1,
                    "n": 0,
                    "polarization": "s",
                    "power_ratio": 0.0,
                }
            ],
        )

    mapping = validate_external_auxiliary_mapping(
        rows, fixture["external_auxiliary_amplitudes"]
    )
    assert mapping["external_keys_auxiliary_index"].tolist() == [3, 0, 2, 1]
    assert mapping["external_keys_local_auxiliary_index"].tolist() == [1, 0, 0, 1]
    assert mapping["bottom_q_external_keys_m_n_pol"].tolist() == [
        [0, 0, 0],
        [1, 0, 1],
    ]
    assert mapping["bottom_q_external_auxiliary_index"].tolist() == [0, 1]
    duplicate_index_rows = [dict(row) for row in rows]
    duplicate_index_rows[-1]["local_auxiliary_index"] = 0
    with pytest.raises(ValueError, match="repeat local_auxiliary_index"):
        validate_external_auxiliary_mapping(
            duplicate_index_rows, fixture["external_auxiliary_amplitudes"]
        )
    missing_index_rows = [dict(row) for row in rows]
    missing_index_rows[-1]["local_auxiliary_index"] = 2
    with pytest.raises(ValueError, match="invalid local_auxiliary_index"):
        validate_external_auxiliary_mapping(
            missing_index_rows, fixture["external_auxiliary_amplitudes"]
        )
    descriptor = write_task42_hybrid_direct_payload(
        run_directory=fixture["run_directory"],
        fields=fields,
        identity=fixture["identity"],
        external_mode_inventory=inventory,
        external_diffraction_orders=rows,
        modal_amplitudes=fixture["modal_amplitudes"],
        external_auxiliary_amplitudes=fixture["external_auxiliary_amplitudes"],
    )
    with np.load(descriptor["payload_path"]) as archive:
        assert archive["E_V_per_m"].shape == (4, 3, 2, 3)
        assert archive["H_A_per_m"].shape == (4, 3, 2, 3)
        assert archive["external_keys_side_m_n_pol"].shape == (4, 4)
        assert archive["bottom_q_external_keys_m_n_pol"].tolist() == [
            [0, 0, 0],
            [1, 0, 1],
        ]
        assert archive["top_q_external_auxiliary_index"].tolist() == [2, 3]
    sidecar = json.loads(Path(descriptor["identity_path"]).read_text())
    assert sidecar["identity"]["canonical_export_prefix"] == "task42_hybrid_direct"
    assert sidecar["payload"]["coordinate_derived_shape"] == [4, 3, 2, 3]


def _shared_task42_test_directory(tmp_path: Path) -> Path:
    comm = MPI.COMM_WORLD
    root = None
    if comm.rank == 0:
        base_text = os.environ.get("TASK42_MPI_SHARED_EVIDENCE_ROOT")
        base = Path(base_text) if base_text else tmp_path
        token = hashlib.sha256(os.urandom(32)).hexdigest()[:16]
        root = str(base / f"task42-a2-output-{token}")
    return Path(comm.bcast(root, root=0))


def _prepare_shared_test_directory(comm, path: Path, *, sentinel: bytes | None = None) -> None:
    """Create a shared test directory on rank zero and broadcast preparation."""

    state = None
    if comm.rank == 0:
        try:
            path.mkdir(parents=True, exist_ok=False)
            if sentinel is not None:
                (path / "task42_hybrid_direct_fields.npz").write_bytes(sentinel)
            state = {"ok": True}
        except OSError as exc:  # filesystem setup errors must be collective
            state = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    state = comm.bcast(state, root=0)
    if not isinstance(state, dict) or state.get("ok") is not True:
        raise RuntimeError(
            "shared test directory preparation failed: "
            + str(state.get("error") if isinstance(state, dict) else "missing root status")
        )


def _persist_rank_evidence(comm, base: Path, label: str, record: dict[str, object]) -> None:
    evidence_dir = base.with_name(base.name + "_evidence")
    _prepare_shared_test_directory(comm, evidence_dir)
    path = evidence_dir / f"{label}.rank-{comm.rank}.json"
    with path.open("x", encoding="utf-8") as stream:
        json.dump(record, stream, sort_keys=True, separators=(",", ":"), allow_nan=False)
        stream.write("\n")
        stream.flush()


def _write_collectively(fixture: dict[str, object], run_directory: Path):
    return write_task42_hybrid_direct_payload_collectively(
        MPI.COMM_WORLD,
        run_directory=run_directory,
        sample_x=fixture["sample_x"],
        sample_y=fixture["sample_y"],
        sample_z=fixture["sample_z"],
        electric=fixture["electric"],
        magnetic=fixture["magnetic"],
        identity=fixture["identity"],
        external_mode_inventory=fixture["external_mode_inventory"],
        external_diffraction_orders=fixture["external_diffraction_orders"],
        modal_amplitudes=fixture["modal_amplitudes"],
        external_auxiliary_amplitudes=fixture["external_auxiliary_amplitudes"],
    )


def test_task42_collective_output_writer_success_is_root_owned(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from src.postprocessing import hybrid_direct_output

    comm = MPI.COMM_WORLD
    fixture = _task42_output_fixture(tmp_path)
    root = _shared_task42_test_directory(tmp_path)
    fixture["run_directory"] = root
    original_writer = hybrid_direct_output.write_task42_hybrid_direct_payload
    calls: list[int] = []

    def tracked_writer(**kwargs):
        calls.append(comm.rank)
        return original_writer(**kwargs)

    monkeypatch.setattr(
        hybrid_direct_output, "write_task42_hybrid_direct_payload", tracked_writer
    )
    result = _write_collectively(fixture, root)
    descriptors = comm.allgather(result["descriptor"])
    writer_calls_by_rank = comm.allgather(list(calls))
    _persist_rank_evidence(
        comm,
        root,
        "writer-success",
        {
            "rank": comm.rank,
            "errors": [],
            "descriptor": result["descriptor"],
            "all_descriptors": descriptors,
            "writer_calls": calls,
            "writer_calls_by_rank": writer_calls_by_rank,
            "writer_call_count": len(calls),
        },
    )
    assert calls == ([0] if comm.rank == 0 else [])
    assert all(item == descriptors[0] for item in descriptors)
    assert Path(result["descriptor"]["payload_path"]).is_file()
    assert Path(result["descriptor"]["identity_path"]).is_file()


def test_task42_collective_output_rejects_single_rank_bad_shape_before_writer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    comm = MPI.COMM_WORLD
    if comm.size < 2:
        pytest.skip("single-rank malformed-field propagation requires MPI2")
    from src.postprocessing import hybrid_direct_output

    fixture = _task42_output_fixture(tmp_path)
    root = _shared_task42_test_directory(tmp_path)
    original_electric = fixture["electric"]
    if comm.rank == 1:
        fixture["electric"] = np.zeros((5, 3, 2, 3), dtype=np.complex128)
    calls: list[int] = []

    def tracked_writer(**_kwargs):
        calls.append(comm.rank)
        raise AssertionError("writer ran after a rank-local shape refusal")

    monkeypatch.setattr(
        hybrid_direct_output, "write_task42_hybrid_direct_payload", tracked_writer
    )
    with pytest.raises(ValueError, match="failed collectively") as caught:
        _write_collectively(fixture, root)
    messages = comm.allgather(str(caught.value))
    writer_calls_by_rank = comm.allgather(list(calls))
    _persist_rank_evidence(
        comm,
        root,
        "malformed-shape-refusal",
        {
            "rank": comm.rank,
            "error": str(caught.value),
            "all_errors": messages,
            "descriptor": None,
            "writer_calls": calls,
            "writer_calls_by_rank": writer_calls_by_rank,
            "writer_call_count": len(calls),
            "root_output_exists": root.exists(),
        },
    )
    assert messages == [messages[0]] * comm.size
    assert "rank 1: ValueError" in messages[0]
    assert calls == []
    assert not root.exists()
    fixture["electric"] = original_electric


def test_task42_collective_output_broadcasts_root_writer_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from src.postprocessing import hybrid_direct_output

    comm = MPI.COMM_WORLD
    fixture = _task42_output_fixture(tmp_path)
    root = _shared_task42_test_directory(tmp_path)
    _prepare_shared_test_directory(comm, root, sentinel=b"existing")
    calls: list[int] = []
    original_writer = hybrid_direct_output.write_task42_hybrid_direct_payload

    def observed_writer(**kwargs):
        calls.append(comm.rank)
        return original_writer(**kwargs)

    monkeypatch.setattr(
        hybrid_direct_output, "write_task42_hybrid_direct_payload", observed_writer
    )
    with pytest.raises(RuntimeError, match="output writer failed") as caught:
        _write_collectively(fixture, root)
    messages = comm.allgather(str(caught.value))
    writer_calls_by_rank = comm.allgather(list(calls))
    _persist_rank_evidence(
        comm,
        root,
        "root-writer-refusal",
        {
            "rank": comm.rank,
            "error": str(caught.value),
            "all_errors": messages,
            "writer_calls": calls,
            "writer_calls_by_rank": writer_calls_by_rank,
            "writer_call_count": len(calls),
            "descriptor": None,
        },
    )
    assert messages == [messages[0]] * comm.size
    assert "FileExistsError" in messages[0]
    assert calls == ([0] if comm.rank == 0 else [])


def test_task42_mpi_root_resource_refusal_propagates_before_allocation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    comm = MPI.COMM_WORLD
    if comm.size < 2:
        pytest.skip("root resource-gate propagation requires MPI2")
    from benchmarks import task034_wsl_resources
    from src.io import input_validation

    monkeypatch.setattr(
        task034_wsl_resources,
        "resource_authority_sample",
        lambda _root_pid: {"sample_status": "fixture-valid"},
    )
    monkeypatch.setattr(
        input_validation,
        "task42_memory_gate_from_authority",
        lambda *_args, **_kwargs: {
            "pass": False,
            "errors": ["fixture_resource_refusal"],
        },
    )
    output = _shared_task42_test_directory(tmp_path)
    callback = task038_input_worker._task42_stage_gate_callback(
        output_directory=output,
        comm=comm,
        root_pid=1234,
    )
    inventory = {
        "components": [
            {
                "name": "fixture_rank_local_payload",
                "scope": "rank_local",
                "unit": "bytes",
                "delta_bytes": 1024 * (comm.rank + 1),
            }
        ]
    }
    decision = callback(
        "fixture_before_guarded_allocation",
        1024 * (comm.rank + 1),
        inventory,
    )
    allocation_calls: list[str] = []
    with pytest.raises(RuntimeError, match="refused before allocation") as caught:
        require_task42_phase_admission(
            lambda _phase, _inventory: decision,
            "fixture_before_guarded_allocation",
            inventory,
        )
        allocation_calls.append("guarded allocation")
    errors = comm.allgather(decision["errors"])
    _persist_rank_evidence(
        comm,
        output,
        "root-resource-refusal",
        {
            "rank": comm.rank,
            "decision": decision,
            "all_errors": errors,
            "exception": str(caught.value),
            "allocation_calls": allocation_calls,
        },
    )
    assert errors == [errors[0]] * comm.size
    assert errors[0] == ["root_resource_gate:fixture_resource_refusal"]
    assert allocation_calls == []


class _SerialCollective:
    rank = 0
    size = 1

    def bcast(self, value, root=0):
        return value

    def allgather(self, value):
        return [value]


def test_task42_root_resource_refusal_propagates_before_the_guarded_operation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from benchmarks import task034_wsl_resources
    from src.io import input_validation

    monkeypatch.setattr(
        task034_wsl_resources,
        "resource_authority_sample",
        lambda _root_pid: {"sample_status": "fixture"},
    )
    monkeypatch.setattr(
        input_validation,
        "task42_memory_gate_from_authority",
        lambda *_args, **_kwargs: {
            "pass": False,
            "errors": ["whole_job_process_tree_is_incomplete_or_unreadable"],
        },
    )
    callback = task038_input_worker._task42_stage_gate_callback(
        output_directory=tmp_path,
        comm=_SerialCollective(),
        root_pid=1234,
    )
    inventory = {
        "components": [
            {
                "name": "fixture_sparse_matrix",
                "scope": "rank_local",
                "unit": "bytes",
                "delta_bytes": 4096,
            }
        ]
    }
    allocation_calls: list[str] = []
    decision = callback("fixture_matrix_allocation", 4096, inventory)
    with pytest.raises(RuntimeError, match="refused before allocation"):
        decision = require_task42_phase_admission(
            lambda _phase, _value: decision,
            "fixture_matrix_allocation",
            inventory,
        )
        allocation_calls.append("matrix.createAIJ")
    assert allocation_calls == []
    assert decision["errors"] == [
        "root_resource_gate:whole_job_process_tree_is_incomplete_or_unreadable"
    ]


def test_task42_main_refuses_missing_gate_before_shared_kernel_entry() -> None:
    from benchmarks.run_task032_phase6_augmented import main

    with pytest.raises(SystemExit, match="phase gate"):
        main(
            [],
            config_override=SimpleNamespace(case_name=TASK42_13P5_HYBRID_MODEL_ID),
            task42_hybrid_profile=True,
            task42_output_identity={
                "model_id": TASK42_13P5_HYBRID_MODEL_ID,
                "canonical_export_prefix": "task42_hybrid_direct",
                "source_sha": "a" * 40,
            },
        )


def test_task42_cross_section_mesh_refusal_precedes_axis_plan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.modes import cross_section_spaces

    allocated: list[str] = []
    monkeypatch.setattr(
        cross_section_spaces,
        "stage4_axis_plan",
        lambda *_args, **_kwargs: allocated.append("axis_plan"),
    )
    with pytest.raises(RuntimeError, match="refused before allocation"):
        cross_section_spaces.build_matching_cross_section(
            object(), "stage4_xy", task42_phase_gate=_reject_task42_phase
        )
    assert allocated == []


def test_task42_qep_space_refusal_precedes_element_and_functionspace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.modes import cross_section_spaces

    allocated: list[str] = []

    def allocate_element(*_args, **_kwargs):
        allocated.append("finite_element")
        raise AssertionError("finite-element allocation ran after a refused gate")

    monkeypatch.setattr(cross_section_spaces, "element", allocate_element)
    with pytest.raises(RuntimeError, match="refused before allocation"):
        cross_section_spaces.build_cross_section_spaces(
            SimpleNamespace(mesh=object()),
            transverse_degree=6,
            task42_phase_gate=_reject_task42_phase,
        )
    assert allocated == []


def test_task42_augmented_matrix_refusal_precedes_layout_and_petsc_matrix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.solvers import hybrid_fem_modal_augmented_direct as direct

    allocated: list[str] = []

    def allocate_layout(*_args, **_kwargs):
        allocated.append("augmented_layout")
        raise AssertionError("augmented layout ran after a refused gate")

    monkeypatch.setattr(
        direct,
        "HybridAugmentedLayout",
        SimpleNamespace(build=allocate_layout),
    )
    with pytest.raises(RuntimeError, match="refused before allocation"):
        direct.build_hybrid_augmented_direct_system(
            SimpleNamespace(side="bottom"),
            SimpleNamespace(side="top"),
            SimpleNamespace(mode_count_per_direction=120),
            task42_phase_gate=_reject_task42_phase,
        )
    assert allocated == []


def test_task42_factor_setup_refusal_precedes_petsc_mumps_setup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.solvers import hybrid_fem_modal_augmented_direct as direct

    allocated: list[str] = []

    class _FakePC:
        class Type:
            LU = object()

        def setType(self, _value):
            return None

        def setFactorSolverType(self, _value):
            return None

    class _FakeKSP:
        class Type:
            PREONLY = object()

        def __init__(self):
            self.pc = _FakePC()

        def create(self, _comm):
            return self

        def setType(self, _value):
            return None

        def setErrorIfNotConverged(self, _value):
            return None

        def getPC(self):
            return self.pc

        def setOperators(self, _matrix):
            return None

        def setUp(self):
            allocated.append("ksp_mumps_symbolic_numeric_setup")
            raise AssertionError("MUMPS setup ran after a refused gate")

    monkeypatch.setattr(
        direct,
        "PETSc",
        SimpleNamespace(KSP=_FakeKSP, PC=_FakePC),
    )
    with pytest.raises(RuntimeError, match="refused before allocation"):
        direct.solve_hybrid_augmented_direct(
            SimpleNamespace(layout=SimpleNamespace(comm=object()), A=object()),
            SimpleNamespace(side="bottom"),
            SimpleNamespace(side="top"),
            task42_phase_gate=_reject_task42_phase,
        )
    assert allocated == []


def test_task42_solve_refusal_precedes_solution_vector_and_mat_solve(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.solvers import hybrid_fem_modal_augmented_direct as direct

    allocated: list[str] = []

    class _FakePC:
        class Type:
            LU = object()

        def setType(self, _value):
            return None

        def setFactorSolverType(self, _value):
            return None

    class _FakeKSP:
        class Type:
            PREONLY = object()

        def __init__(self):
            self.pc = _FakePC()

        def create(self, _comm):
            return self

        def setType(self, _value):
            return None

        def setErrorIfNotConverged(self, _value):
            return None

        def getPC(self):
            return self.pc

        def setOperators(self, _matrix):
            return None

        def setUp(self):
            allocated.append("mumps_setup")

        def solve(self, *_args):
            allocated.append("mumps_solve")
            raise AssertionError("MatSolve ran after a refused solve gate")

        def destroy(self):
            allocated.append("owned_ksp_destroy")

    monkeypatch.setattr(
        direct,
        "PETSc",
        SimpleNamespace(KSP=_FakeKSP, PC=_FakePC),
    )

    class _Vector:
        def duplicate(self):
            allocated.append("solution_vector")
            raise AssertionError("solution vector allocated after refused gate")

        def destroy(self):
            allocated.append("borrowed_rhs_destroy")

    class _BorrowedMatrix:
        def destroy(self):
            allocated.append("borrowed_matrix_destroy")

    class _Comm:
        def allreduce(self, value, op=None):
            return value

    def gate(phase, _inventory):
        return {
            "pass": phase == "direct_mumps_factor_setup",
            "errors": [] if phase == "direct_mumps_factor_setup" else ["refused"],
        }

    with pytest.raises(RuntimeError, match="refused before allocation"):
        direct.solve_hybrid_augmented_direct(
            SimpleNamespace(
                layout=SimpleNamespace(comm=_Comm()),
                A=_BorrowedMatrix(),
                b=_Vector(),
            ),
            SimpleNamespace(side="bottom"),
            SimpleNamespace(side="top"),
            task42_phase_gate=gate,
        )
    assert allocated == ["mumps_setup", "owned_ksp_destroy"]


def test_task42_rhs_refusal_destroys_only_owned_augmented_matrix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.solvers import hybrid_fem_modal_augmented_direct as direct

    events: list[str] = []

    class _FakeMatrix:
        class Option:
            NEW_NONZERO_ALLOCATION_ERR = object()

        class InsertMode:
            ADD_VALUES = object()

        def createAIJ(self, **_kwargs):
            events.append("augmented_matrix_create")
            return self

        def setOption(self, *_args):
            return None

        def setValues(self, *_args, **_kwargs):
            return None

        def assemble(self):
            events.append("augmented_matrix_assemble")

        def getSize(self):
            return (2, 2)

        def destroy(self):
            events.append("owned_augmented_matrix_destroy")

    class _OwnedOrBorrowed:
        def __init__(self, name):
            self.name = name

        def destroy(self):
            events.append(f"borrowed_{self.name}_destroy")

    class _Layout:
        comm = SimpleNamespace(rank=0)
        modal_owner = 0
        local_size = 2
        global_size = 2

        @staticmethod
        def map_modal(indices):
            return np.asarray(indices, dtype=np.int32)

        @staticmethod
        def map_bottom(indices):
            return np.asarray(indices, dtype=np.int32)

        @staticmethod
        def map_top(indices):
            return np.asarray(indices, dtype=np.int32)

        @staticmethod
        def pack(*_args):
            events.append("augmented_rhs_pack")
            raise AssertionError("RHS was packed after the RHS gate refused")

    bottom = SimpleNamespace(
        side="bottom",
        A=_OwnedOrBorrowed("bottom_matrix"),
        b=_OwnedOrBorrowed("bottom_rhs"),
        global_size=2,
    )
    top = SimpleNamespace(
        side="top",
        A=_OwnedOrBorrowed("top_matrix"),
        b=_OwnedOrBorrowed("top_rhs"),
        global_size=2,
    )
    coupling = SimpleNamespace(
        mode_count_per_direction=1,
        propagation=SimpleNamespace(
            forward=SimpleNamespace(factors=np.ones(1, dtype=np.complex128)),
            backward=SimpleNamespace(factors=np.ones(1, dtype=np.complex128)),
        ),
        bottom=SimpleNamespace(
            positive_traction=object(), negative_traction=object(), projection=object()
        ),
        top=SimpleNamespace(
            positive_traction=object(), negative_traction=object(), projection=object()
        ),
    )
    monkeypatch.setattr(
        direct,
        "PETSc",
        SimpleNamespace(Mat=_FakeMatrix, InsertMode=_FakeMatrix.InsertMode),
    )
    monkeypatch.setattr(
        direct,
        "HybridAugmentedLayout",
        SimpleNamespace(build=lambda *_args: _Layout()),
    )
    monkeypatch.setattr(direct, "_copy_block", lambda *_args, **_kwargs: 0)
    monkeypatch.setattr(
        direct,
        "internal_modal_constraint_matrix",
        lambda _coupling: np.zeros((2, 2), dtype=np.complex128),
    )
    monkeypatch.setattr(direct, "_petsc_matrix_stats", lambda *_args, **_kwargs: {})

    def gate(phase, _inventory):
        events.append(phase)
        return {
            "pass": phase != "hybrid_augmented_rhs",
            "errors": [] if phase != "hybrid_augmented_rhs" else ["unknown RHS Delta"],
        }

    with pytest.raises(RuntimeError, match="hybrid_augmented_rhs refused"):
        direct.build_hybrid_augmented_direct_system(
            bottom,
            top,
            coupling,
            task42_phase_gate=gate,
        )
    assert events.count("augmented_matrix_create") == 1
    assert events.count("owned_augmented_matrix_destroy") == 1
    assert "augmented_rhs_pack" not in events
    assert not any(event.startswith("borrowed_") for event in events)


def test_task42_local_side_refusal_precedes_local_mesh_builder(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.solvers import hybrid_local_dtn

    allocated: list[str] = []

    def allocate_mesh(*_args, **_kwargs):
        allocated.append("side_mesh")
        raise AssertionError("local side mesh ran after a refused gate")

    monkeypatch.setattr(hybrid_local_dtn, "build_hybrid_local_mesh", allocate_mesh)
    monkeypatch.setattr(
        hybrid_local_dtn,
        "resolve_stage4_full3d_assembly_backend",
        lambda *_args, **_kwargs: {"actual": "assembly_time_static_condensed"},
    )
    monkeypatch.setattr(
        hybrid_local_dtn,
        "qualify_stage4_full3d_assembly_backend",
        lambda *_args, **_kwargs: {"status": "fixture"},
    )
    with pytest.raises(RuntimeError, match="refused before allocation"):
        hybrid_local_dtn.assemble_hybrid_local_dtn_system(
            SimpleNamespace(stage4_dtn_assembly="auxiliary", use_pml=False),
            "bottom",
            task42_phase_gate=_reject_task42_phase,
        )
    assert allocated == []


def test_task42_qep_solve_refusal_precedes_slepc_pep_creation() -> None:
    from src.modes import quadratic_beta_eigenproblem as qep

    allocated: list[str] = []

    class _Operators:
        @property
        def K0(self):
            allocated.append("pep_operator_access")
            raise AssertionError("PEP setup ran after a refused gate")

    with pytest.raises(RuntimeError, match="refused before allocation"):
        qep.solve_quadratic_beta_modes(
            _Operators(),
            target=1.0 + 0.0j,
            requested_modes=120,
            task42_phase_gate=_reject_task42_phase,
        )
    assert allocated == []


def test_task42_adjoint_basis_refusal_precedes_adjoint_matrix_copy() -> None:
    from src.modes import mode_classification

    allocated: list[str] = []

    class _Operators:
        @property
        def K0(self):
            allocated.append("adjoint_matrix_copy")
            raise AssertionError("adjoint allocation ran after a refused gate")

    with pytest.raises(RuntimeError, match="refused before allocation"):
        mode_classification.build_biorthogonal_mode_basis(
            object(),
            object(),
            object(),
            _Operators(),
            [SimpleNamespace(direction="forward")],
            adjoint_target=1.0 + 0.0j,
            task42_phase_gate=_reject_task42_phase,
        )
    assert allocated == []


def test_task42_coupling_refusal_precedes_projection_construction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.coupling import hybrid_internal_modes

    allocated: list[str] = []

    def allocate_projection(*_args, **_kwargs):
        allocated.append("modal_trace_projection")
        raise AssertionError("projection allocation ran after a refused gate")

    monkeypatch.setattr(
        hybrid_internal_modes, "ModalTraceProjection", allocate_projection
    )
    with pytest.raises(RuntimeError, match="refused before allocation"):
        hybrid_internal_modes.build_hybrid_internal_mode_coupling(
            object(),
            object(),
            SimpleNamespace(modes=[SimpleNamespace(direction="forward")]),
            SimpleNamespace(modes=[SimpleNamespace(direction="backward")]),
            SimpleNamespace(side="bottom", assembly_backend_actual="fixture"),
            SimpleNamespace(side="top", assembly_backend_actual="fixture"),
            task42_phase_gate=_reject_task42_phase,
        )
    assert allocated == []


def test_task42_exact_traction_refusal_precedes_local_cell_construction(
    tmp_path: Path,
) -> None:
    from src.coupling.hybrid_one_cell_exact_traction_builder import (
        build_exact_one_cell_traction_matrices,
    )

    allocated: list[str] = []
    propagation = SimpleNamespace(propagation_model="full3d_uniform_cg")
    with pytest.raises(RuntimeError, match="refused before allocation"):
        build_exact_one_cell_traction_matrices(
            object(),
            [],
            [],
            object(),
            propagation,
            object(),
            object(),
            work_dir=tmp_path,
            coupling_propagation_length_nm=100.0,
            task42_phase_gate=_reject_task42_phase,
        )
    assert allocated == []


def test_task42_middle_coupling_refusal_precedes_propagation_creation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.coupling import hybrid_internal_modes

    created: list[str] = []

    class _Projection:
        def __init__(self, *_args, **_kwargs):
            created.append("projection")
            self.right_traces = [object()]

        def project(self, _trace):
            return np.asarray([1.0 + 0.0j], dtype=np.complex128)

        def destroy(self):
            created.append("projection_destroy")

    def allocate_propagation(*_args, **_kwargs):
        created.append("propagation")
        raise AssertionError("propagation allocated after a refused gate")

    monkeypatch.setattr(hybrid_internal_modes, "ModalTraceProjection", _Projection)
    monkeypatch.setattr(
        hybrid_internal_modes,
        "_trace_from_full_mode_vector",
        lambda *_args, **_kwargs: object(),
    )
    monkeypatch.setattr(
        hybrid_internal_modes,
        "_canonicalized_negative_traces",
        lambda *_args, **_kwargs: [],
    )
    monkeypatch.setattr(
        hybrid_internal_modes, "build_two_sided_propagation", allocate_propagation
    )

    def gate(phase, _inventory):
        return {
            "pass": phase == "traction_projection_and_blocks",
            "errors": [] if phase == "traction_projection_and_blocks" else ["refused"],
        }

    with pytest.raises(RuntimeError, match="refused before allocation"):
        hybrid_internal_modes.build_hybrid_internal_mode_coupling(
            SimpleNamespace(mesh_target_size=1.0, nedelec_degree=1),
            object(),
            SimpleNamespace(
                modes=[
                    SimpleNamespace(
                        direction="forward",
                        beta=1.0 + 0.0j,
                        right=SimpleNamespace(right_full=object()),
                    )
                ]
            ),
            SimpleNamespace(
                modes=[
                    SimpleNamespace(
                        direction="backward",
                        beta=1.0 + 0.0j,
                        right=SimpleNamespace(right_full=object()),
                    )
                ]
            ),
            SimpleNamespace(side="bottom", assembly_backend_actual="fixture"),
            SimpleNamespace(side="top", assembly_backend_actual="fixture"),
            task42_phase_gate=gate,
        )
    assert created == ["projection", "projection_destroy"]


def test_task42_recovery_refusal_precedes_duplicate_vector_allocations() -> None:
    from src.solvers.hybrid_static_field_recovery import (
        recover_hybrid_static_local_field,
    )

    allocated: list[str] = []

    class _Vector:
        def getSize(self):
            return 1

        def duplicate(self):
            allocated.append("recovery_vector")
            raise AssertionError("recovery vector allocated after refused gate")

    system = SimpleNamespace(
        static_condensation=object(),
        full_fe_rhs=_Vector(),
        b=_Vector(),
        global_size=1,
        side="bottom",
        local_mesh=SimpleNamespace(mesh=SimpleNamespace(comm=object())),
    )
    coupling = SimpleNamespace(internal_unknown_count=2)
    with pytest.raises(RuntimeError, match="refused before allocation"):
        recover_hybrid_static_local_field(
            system,
            coupling,
            _Vector(),
            np.zeros(2, dtype=np.complex128),
            task42_phase_gate=_reject_task42_phase,
        )
    assert allocated == []


def test_task42_adapter_does_not_turn_a_stubbed_kernel_into_a_pass(tmp_path: Path) -> None:
    specification = load_and_resolve(TASK42_A2_INPUT)
    resolved_payload = specification.as_jsonable()
    captured: dict[str, object] = {}

    def runner(argv, cfg, **kwargs):
        captured.update(kwargs)
        captured["argv"] = list(argv)
        captured["cfg_case_name"] = cfg.case_name
        return {"qualification": {"integration_pass": False}}

    result = run_task42_hybrid_direct(
        resolved_payload,
        tmp_path,
        source_sha="a" * 40,
        resolved_config_sha256="b" * 64,
        task42_phase_gate=lambda _phase, _inventory: {"pass": False},
        runner=runner,
    )
    assert captured["cfg_case_name"] == TASK42_13P5_HYBRID_MODEL_ID
    assert captured["task42_hybrid_profile"] is True
    assert captured["canonical_export_prefix"] == "task42_hybrid_direct"
    assert captured["external_mode_inventory"] == resolved_payload["derived"][
        "external_mode_inventory"
    ]
    assert callable(captured["task42_phase_gate"])
    assert result["passed"] is False
    assert result["errors"]


def test_task39_direct_payload_keeps_its_historical_schema_and_shape(tmp_path: Path) -> None:
    sample_x = np.arange(40, dtype=np.float64)
    sample_y = np.arange(20, dtype=np.float64)
    sample_z = np.asarray([10.0, 30.0, 60.0, 90.0, 110.0], dtype=np.float64)
    selected = SimpleNamespace(
        electric_V_per_m=np.zeros((5, 20, 40, 3), dtype=np.complex128),
        magnetic_A_per_m=np.ones((5, 20, 40, 3), dtype=np.complex128),
    )
    descriptor = _task039_direct_payload(
        selected_planes=selected,
        sample_x=sample_x,
        sample_y=sample_y,
        sample_z=sample_z,
        modal_amplitudes=np.asarray([1.0 + 0.0j]),
        external_auxiliary_amplitudes={
            "bottom": np.asarray([1.0 + 0.0j]),
            "top": np.asarray([1.0 + 0.0j]),
        },
        run_dir=tmp_path,
        comm=MPI.COMM_SELF,
    )
    assert descriptor["schema"] == "task039.hybrid-direct-payload.v1"
    assert descriptor["keys"] == list(_TASK039_DIRECT_PAYLOAD_KEYS)
    with np.load(tmp_path / "task039_direct_payload.npz") as archive:
        assert archive["x_nm"].shape == (40,)
        assert archive["y_nm"].shape == (20,)
        assert archive["E_V_per_m"].shape == (5, 20, 40, 3)
        assert archive["H_A_per_m"].shape == (5, 20, 40, 3)
