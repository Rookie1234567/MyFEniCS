"""Pure setup-bundle and retained-ledger contracts for the p6 candidate."""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
from mpi4py import MPI
from petsc4py import PETSc
import pytest
from dolfinx import fem

import src.solvers.fullspace_same_mesh_hcurl_pmg_setup as setup_impl
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


def test_setup_seeds_are_injected_once_and_destroyed_on_success_or_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    captured: dict[str, object] = {}
    seeds: list[object] = []
    fail_lower = False

    class _Owned:
        def __init__(self, name: str) -> None:
            self.name = name
            self.destroyed = False

        def destroy(self) -> None:
            self.destroyed = True
            events.append(self.name)

    class _Seed(_Owned):
        pass

    class _Shell(_Owned):
        def __init__(self, action: object, diagonal: object) -> None:
            super().__init__("shell")
            self.action = action
            self.diagonal = diagonal

        def destroy(self) -> None:
            if not self.destroyed:
                super().destroy()
                self.action.destroy()
                self.diagonal.destroy()

    def _levels(_cfg: object, _comm: object, _degrees: tuple[int, ...]):
        spaces = {}
        floquets = {}
        for degree in (6, 3, 1):
            index_map = SimpleNamespace(size_local=4, num_ghosts=0)
            space = SimpleNamespace(
                dofmap=SimpleNamespace(index_map=index_map, index_map_bs=1)
            )
            spaces[degree] = space
            floquets[degree] = SimpleNamespace(
                mpc=SimpleNamespace(
                    slaves=np.asarray([0], dtype=np.int32),
                    function_space=space,
                )
            )
        return {
            "mesh": "mesh",
            "mesh_data": SimpleNamespace(),
            "spaces": spaces,
            "floquets": floquets,
            "mu": "mu",
            "mass": "mass",
            "coefficient_audit": {},
        }

    def _source(_space: object, _floquet: object, _cfg: object, name: str):
        seed = _Seed(f"seed-{len(seeds)}-{name}")
        seeds.append(seed)
        return seed, {"name": name}

    def _lower(*_args: object, smoother_power_seed: object, **_kwargs: object):
        captured["lower"] = smoother_power_seed
        if fail_lower:
            raise RuntimeError("lower construction failed")
        return _Owned("lower")

    def _upper(*_args: object, smoother_power_seed: object, **_kwargs: object):
        captured["upper"] = smoother_power_seed
        return _Owned("upper")

    monkeypatch.setattr(setup_impl, "_build_same_mesh_levels", _levels)
    monkeypatch.setattr(
        setup_impl, "build_frozen_fullspace_primal_source", _source
    )
    monkeypatch.setattr(setup_impl, "same_mesh_positive_form", lambda *_a, **_k: "form")
    monkeypatch.setattr(
        setup_impl, "build_fullspace_mpc_form_action", lambda *_a, **_k: _Owned("action")
    )
    monkeypatch.setattr(
        setup_impl, "build_constrained_jacobi_diagonal", lambda *_a, **_k: _Owned("diagonal")
    )
    monkeypatch.setattr(setup_impl, "SameMeshP6MatrixFreeShell", _Shell)
    monkeypatch.setattr(
        setup_impl, "assemble_same_mesh_positive_matrix", lambda *_a, **_k: _Owned("matrix")
    )
    monkeypatch.setattr(
        setup_impl, "build_same_mesh_hcurl_transfer", lambda *_a, **_k: _Owned("local")
    )
    monkeypatch.setattr(
        setup_impl,
        "build_same_mesh_hcurl_owner_transfer",
        lambda *_a, **_k: _Owned("owner"),
    )
    monkeypatch.setattr(setup_impl, "SameMeshHcurlPmg", _lower)
    monkeypatch.setattr(setup_impl, "SameMeshP6NestedVcycle", _upper)
    monkeypatch.setattr(fem, "form", lambda *_a, **_k: "compiled")
    cfg = SimpleNamespace(nedelec_degree=6, mesh_target_size=10.0, lambda0=13.5)

    bundle = setup_impl.build_p6_same_mesh_setup(cfg, MPI.COMM_SELF)
    assert captured["lower"] is seeds[0]
    assert captured["upper"] is seeds[1]
    assert all(seed.destroyed for seed in seeds)
    assert all(not any(value is seed for value in bundle.values()) for seed in seeds)
    setup_impl.destroy_p6_same_mesh_setup_bundle(bundle)

    captured.clear()
    seeds.clear()
    fail_lower = True
    with pytest.raises(RuntimeError, match="lower construction failed"):
        setup_impl.build_p6_same_mesh_setup(cfg, MPI.COMM_SELF)
    assert len(seeds) == 1
    assert seeds[0].destroyed is True
    assert "upper" not in captured
