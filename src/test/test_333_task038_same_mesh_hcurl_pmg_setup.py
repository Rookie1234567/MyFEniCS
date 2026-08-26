"""Pure setup-bundle and retained-ledger contracts for the p6 candidate."""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
from mpi4py import MPI
from petsc4py import PETSc
import pytest

from src.common.config_3d import target_stage4_config
from src.solvers.fullspace_same_mesh_hcurl_pmg_global import (
    _same_mesh_level_config,
)
from src.solvers.fullspace_same_mesh_hcurl_pmg_setup import (
    P6_SETUP_LEVELS,
    P6_SETUP_PAIRS,
    P6_SETUP_SCHEMA,
    P6_SETUP_WAVELENGTH_NM,
    _matrix_facts,
    _retained_ledger,
    _smoother_facts,
    _work_facts,
    destroy_p6_same_mesh_setup_bundle,
    validate_p6_setup_config,
)


def _diagonal(size: int) -> PETSc.Mat:
    matrix = PETSc.Mat().createAIJ(
        ((size, size), (size, size)), comm=MPI.COMM_SELF
    )
    matrix.setUp()
    for index in range(size):
        matrix.setValue(index, index, 2.0 + index)
    matrix.assemble()
    return matrix


def test_p6_setup_profile_and_shared_level_config_are_fixed():
    cfg = target_stage4_config(degree=6, h_nm=10.0)
    validate_p6_setup_config(cfg)
    assert P6_SETUP_SCHEMA.endswith("setup.v1")
    assert P6_SETUP_LEVELS == (6, 3, 1)
    assert P6_SETUP_PAIRS == ((6, 3), (3, 1))
    assert P6_SETUP_WAVELENGTH_NM == 13.5
    lower = _same_mesh_level_config(cfg, 3)
    assert lower is not cfg
    assert lower.nedelec_degree == lower.visualization_degree == 3
    assert lower.nedelec_trace_degree is None
    assert lower.nedelec_interior_degree is None
    with pytest.raises(ValueError, match="nedelec_degree"):
        validate_p6_setup_config(target_stage4_config(degree=3, h_nm=50.0))


def test_setup_ledger_helpers_use_real_local_vec_and_matrix_facts():
    matrix = _diagonal(3)
    diagonal = None
    vectors = []
    try:
        facts = _matrix_facts(matrix)
        assert facts["rows"] == facts["cols"] == 3
        assert facts["local_rows"] == facts["local_cols"] == 3
        assert facts["global_nnz"] == 3
        vectors = [matrix.createVecRight() for _ in range(8)]
        smoother = SimpleNamespace(
            **{
                name: vector
                for name, vector in zip(
                    (
                        "_inv_sqrt",
                        "_scaled_input",
                        "_scaled_action",
                        "_rhs_scaled",
                        "_residual",
                        "_direction",
                        "_solution",
                        "_action",
                    ),
                    vectors,
                    strict=True,
                )
            }
        )
        cycle = SimpleNamespace(work_vectors=tuple(vectors[:3]))
        assert _work_facts(cycle) == {
            "count": 3,
            "local_numeric_bytes": 3 * 3 * np.dtype(PETSc.ScalarType).itemsize,
        }
        assert _smoother_facts(smoother)["count"] == 8
        assert _smoother_facts(smoother)["local_numeric_bytes"] == (
            8 * 3 * np.dtype(PETSc.ScalarType).itemsize
        )
        diagonal = matrix.createVecRight()
        ledger = _retained_ledger(
            {"p6_shell": SimpleNamespace(diagonal=diagonal)},
            matrices={
                "p3": {"petsc_reported_memory_bytes": {"local": None}},
                "p1": {"petsc_reported_memory_bytes": {"local": None}},
            },
            transfers={
                "p63": {"local_cache_array_bytes": 11},
                "p31": {"local_cache_array_bytes": 13},
            },
            action={"retained_numeric_payload_local_bytes": 17},
            work={
                "upper": {"local_numeric_bytes": 19},
                "lower": {"local_numeric_bytes": 23},
            },
            smoothers={
                "upper": {"local_numeric_bytes": 29},
                "lower": {"local_numeric_bytes": 31},
            },
            factor={"petsc_reported_memory_bytes": {"local": None}},
        )
        diagonal_bytes = 3 * np.dtype(PETSc.ScalarType).itemsize
        assert ledger["components_local_bytes"][
            "p6_exact_diagonal_local_numeric_bytes"
        ] == diagonal_bytes
        assert "p6_exact_diagonal_global_numeric_bytes" not in ledger[
            "components_local_bytes"
        ]
        assert ledger["global_facts"][
            "p6_exact_diagonal_global_numeric_bytes"
        ] == diagonal_bytes
        assert "restart_reserve_local_bytes" not in ledger[
            "components_local_bytes"
        ]
        assert ledger["not_included"] == [
            "restart20_reserve",
            "outer_ksp",
            "source",
        ]
    finally:
        if diagonal is not None:
            diagonal.destroy()
        for vector in vectors:
            vector.destroy()
        matrix.destroy()


def test_setup_bundle_destroy_delegates_nested_ownership_then_matrices():
    events: list[str] = []

    class _Owned:
        def __init__(self, name: str) -> None:
            self.name = name

        def destroy(self) -> None:
            events.append(self.name)

    bundle = {
        "upper_cycle": _Owned("upper"),
        "lower_cycle": _Owned("lower-not-directly-destroyed"),
        "p63_owner_transfer": _Owned("p63-not-directly-destroyed"),
        "p31_owner_transfer": _Owned("p31-not-directly-destroyed"),
        "p6_shell": _Owned("shell-not-directly-destroyed"),
        "p3_matrix": _Owned("p3"),
        "p1_matrix": _Owned("p1"),
        "spaces": {},
    }
    destroy_p6_same_mesh_setup_bundle(bundle)
    assert events == ["upper", "p3", "p1"]
    assert bundle == {}
