from __future__ import annotations

import json
import os
from pathlib import Path
from types import MappingProxyType, SimpleNamespace

from mpi4py import MPI
import numpy as np
from petsc4py import PETSc
import pytest

from src.adaptivity.blind_controller.contracts import FORMAL_GOAL_IDS
from src.adaptivity.dyadic_hexa_refinement import DyadicHexKey
import src.adaptivity.task035e_actual_dwr as actual_dwr
from src.adaptivity.task035e_actual_dwr import (
    CELLWISE_DWR_PARTITION_SCHEMA,
    Task035eActualDWRError,
    _CellwiseDWRAccumulator,
    _CellwiseRowPartition,
    _build_cellwise_row_partition,
    evaluate_task035e_actual_dwr,
)
from src.adaptivity.task035e_hp_transition import (
    canonical_hp_cell_target_id,
)


def _vector(values: np.ndarray, comm: MPI.Intracomm) -> PETSc.Vec:
    vector = PETSc.Vec().createMPI(len(values), comm=comm)
    start, end = map(int, vector.getOwnershipRange())
    vector.getArray()[:] = np.asarray(
        values[start:end],
        dtype=PETSc.ScalarType,
    )
    vector.assemble()
    return vector


def _partition(size: int) -> _CellwiseRowPartition:
    keys = (
        (0, 1, 0, 0, 0),
        (0, 1, 1, 0, 0),
        (1, 0, 0, 0, 0),
    )
    target_ids = tuple(
        canonical_hp_cell_target_id(DyadicHexKey(*key))
        for key in keys
    )
    designation = {
        "schema_version": "fixture",
        "designation_sha256": "a" * 64,
    }
    return _CellwiseRowPartition(
        target_ids=target_ids,
        current_leaf_keys=keys,
        current_leaf_boxes=(
            (0.0, 0.0, 0.0, 0.5, 1.0, 1.0),
            (0.5, 0.0, 0.0, 1.0, 1.0, 1.0),
            (1.0, 0.0, 0.0, 2.0, 1.0, 1.0),
        ),
        current_leaf_degrees=(4, 5, 6),
        row_to_leaf=np.asarray(
            [index % 3 for index in range(size)],
            dtype=np.int64,
        ),
        independent_trace_rows=size - 2,
        current_plan_identity=MappingProxyType(
            {"forest_leaf_catalog_sha256": "b" * 64}
        ),
        shadow_plan_identity=MappingProxyType(
            {"forest_leaf_catalog_sha256": "c" * 64}
        ),
        designation_identity=MappingProxyType(designation),
    )


def _exercise_accumulator(comm: MPI.Intracomm) -> None:
    size = max(17, 2 * comm.size + 5)
    indices = np.arange(size, dtype=np.float64)
    residual_values = (
        0.2 * np.cos(0.13 * (indices + 1.0))
        + 0.11j * np.sin(0.17 * (indices + 1.0))
    ).astype(np.complex128)
    residual = _vector(residual_values, comm)
    partition = _partition(size)
    accumulator = _CellwiseDWRAccumulator(
        partition,
        residual,
        comm,
    )
    signed_eta: dict[str, float] = {}
    expected = np.zeros(
        (len(partition.target_ids), len(FORMAL_GOAL_IDS)),
        dtype=np.float64,
    )
    try:
        for goal_index, goal_id in enumerate(FORMAL_GOAL_IDS):
            adjoint_values = (
                0.31
                * np.cos(
                    0.07 * (goal_index + 1)
                    + 0.09 * (indices + 1.0)
                )
                + 0.19j
                * np.sin(
                    0.05 * (goal_index + 1)
                    + 0.12 * (indices + 1.0)
                )
            ).astype(np.complex128)
            adjoint = _vector(adjoint_values, comm)
            try:
                signed_eta[goal_id] = float(
                    np.vdot(adjoint_values, residual_values).real
                )
                products = (
                    np.conjugate(adjoint_values) * residual_values
                ).real
                np.add.at(
                    expected[:, goal_index],
                    partition.row_to_leaf,
                    products,
                )
                accumulator.consume(goal_id, adjoint)
            finally:
                adjoint.destroy()
        result = accumulator.finalize(signed_eta)
    finally:
        residual.destroy()

    assert result["schema_version"] == CELLWISE_DWR_PARTITION_SCHEMA
    assert result["status"] == "cellwise_signed_dwr_partition_pass"
    assert result["method"] == "element_residual_adjoint_pairing"
    assert result["global_eta_evenly_distributed"] is False
    assert result["endpoint_delta_consumed"] is False
    assert result["formal_goal_count"] == 59
    assert len(result["rows"]) == 3
    assert len(result["partition_sha256"]) == 64
    for leaf_index, row in enumerate(result["rows"]):
        assert row["target_id"] == partition.target_ids[leaf_index]
        assert len(row["local_residual_partition_sha256"]) == 64
        assert len(row["local_adjoint_partition_sha256"]) == 64
        assert len(row["row_sha256"]) == 64
        observed = np.asarray(
            [
                row["signed_dwr_contribution"][goal_id]
                for goal_id in FORMAL_GOAL_IDS
            ]
        )
        np.testing.assert_allclose(
            observed,
            expected[leaf_index],
            rtol=2.0e-14,
            atol=2.0e-14,
        )
    for goal_index, goal_id in enumerate(FORMAL_GOAL_IDS):
        assert sum(
            row["signed_dwr_contribution"][goal_id]
            for row in result["rows"]
        ) == pytest.approx(
            signed_eta[goal_id],
            rel=2.0e-14,
            abs=2.0e-14,
        )


@pytest.mark.skipif(
    MPI.COMM_WORLD.size != 1,
    reason="serial cellwise DWR fixture",
)
def test_serial_cellwise_partition_closes_true_owner_row_pairings() -> None:
    _exercise_accumulator(MPI.COMM_WORLD)


@pytest.mark.skipif(
    MPI.COMM_WORLD.size != 8
    or os.environ.get("MYFENICS_RUN_TASK035E_CELLWISE_DWR_MPI8") != "1",
    reason="opt-in lightweight MPI8 cellwise DWR fixture",
)
def test_opt_in_mpi8_cellwise_partition_closes_true_pairings() -> None:
    _exercise_accumulator(MPI.COMM_WORLD)


def test_row_designation_uses_actual_incident_cells_and_dtn_side_support(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    comm = MPI.COMM_WORLD
    keys = (
        DyadicHexKey(0, 1, 0, 0, 0),
        DyadicHexKey(0, 1, 1, 0, 0),
    )
    leaves = (
        SimpleNamespace(
            key=keys[0],
            box=(0.0, 0.0, 0.0, 0.5, 1.0, 1.0),
        ),
        SimpleNamespace(
            key=keys[1],
            box=(0.5, 0.0, 0.0, 1.0, 1.0, 1.0),
        ),
    )
    plan_path = tmp_path / "current-plan.json"
    plan_path.write_text(
        json.dumps(
            {
                "base_config": {
                    "domain_z_min": 0.0,
                    "domain_z_max": 1.0,
                }
            }
        ),
        encoding="utf-8",
    )
    current_identity = {
        "path": str(plan_path),
        "file_sha256": "1" * 64,
        "forest_leaf_catalog_sha256": "2" * 64,
        "cell_degree_plan_sha256": "3" * 64,
        "domain_z_min": 0.0,
        "domain_z_max": 1.0,
    }

    def fake_current_authority(*_args, **_kwargs):
        return (
            SimpleNamespace(leaves=leaves),
            (4, 5),
            current_identity,
        )

    monkeypatch.setattr(
        actual_dwr,
        "_current_leaf_authority",
        fake_current_authority,
    )
    constraints = SimpleNamespace(
        owned_cells=(
            SimpleNamespace(
                canonical_leaf=0,
                independent_rows=np.asarray([0, 2]),
            ),
            SimpleNamespace(
                canonical_leaf=1,
                independent_rows=np.asarray([1, 2]),
            ),
        )
    )
    quotient, remainder = divmod(5, comm.size)
    row_start = quotient * comm.rank + min(comm.rank, remainder)
    row_end = row_start + quotient + int(comm.rank < remainder)
    view = SimpleNamespace(
        mesh_data=SimpleNamespace(
            mesh=SimpleNamespace(comm=comm),
            local_h_context=SimpleNamespace(
                forest=SimpleNamespace(leaves=leaves)
            ),
        ),
        reduction=SimpleNamespace(
            system=SimpleNamespace(
                trace_constraints=constraints,
                active_trace_rows=3,
                appended_rows=2,
            )
        ),
        goal_context={
            "modes": (
                SimpleNamespace(side="top"),
                SimpleNamespace(side="bottom"),
            )
        },
        A=SimpleNamespace(getSize=lambda: (5, 5)),
        x=SimpleNamespace(
            getOwnershipRange=lambda: (row_start, row_end)
        ),
    )
    result = _build_cellwise_row_partition(
        view,
        source_sha="4" * 40,
        current_plan_path=plan_path,
        expected_current_plan_sha256="5" * 64,
        shadow_plan_identity={"file_sha256": "6" * 64},
    )
    assert result.target_ids == tuple(
        canonical_hp_cell_target_id(key) for key in keys
    )
    # Shared trace row 2 is designated exactly once to canonical leaf 0.
    # Both global DtN equations retain an indivisible assignment to one
    # actual side-support leaf instead of being repeated over every leaf.
    np.testing.assert_array_equal(
        result.row_to_leaf,
        np.asarray([0, 1, 0, 0, 0], dtype=np.int64),
    )
    assert (
        result.designation_identity["global_eta_evenly_distributed"]
        is False
    )


def test_cellwise_mapping_and_required_plan_fail_closed() -> None:
    with pytest.raises(
        ValueError,
        match="required cellwise partition lacks",
    ):
        evaluate_task035e_actual_dwr(
            SimpleNamespace(),
            None,
            {},
            source_sha="1" * 40,
            expected_shadow_plan_sha256="2" * 64,
            shadow_kind="p-shadow",
            require_cellwise_partition=True,
        )

    partition = _partition(9)
    residual_values = np.ones(9, dtype=np.complex128)
    residual = _vector(residual_values, MPI.COMM_WORLD)
    accumulator = _CellwiseDWRAccumulator(
        partition,
        residual,
        MPI.COMM_WORLD,
    )
    try:
        for goal_id in FORMAL_GOAL_IDS:
            adjoint = _vector(
                np.ones(9, dtype=np.complex128),
                MPI.COMM_WORLD,
            )
            try:
                accumulator.consume(goal_id, adjoint)
            finally:
                adjoint.destroy()
        wrong = {goal_id: 9.0 for goal_id in FORMAL_GOAL_IDS}
        wrong[FORMAL_GOAL_IDS[0]] = 8.0
        with pytest.raises(
            Task035eActualDWRError,
            match="do not close global eta",
        ):
            accumulator.finalize(wrong)
    finally:
        residual.destroy()


def test_cellwise_partition_source_has_no_full_vector_gather() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "adaptivity"
        / "task035e_actual_dwr.py"
    ).read_text(encoding="utf-8")
    assert ".allgather(" not in source
    assert ".gather(" not in source
    assert "global_eta_evenly_distributed" in source
    assert "np.conjugate(values) * self.residual_values" in source
