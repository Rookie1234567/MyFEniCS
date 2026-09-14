"""Small reference-free tests for the V19 p6 action-only algebra."""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

import numpy as np
import pytest
from mpi4py import MPI
from petsc4py import PETSc
from scipy.linalg import lu_factor, lu_solve

from src.solvers.hcurl_assembly_time_condensation import CellRecoveryMap
from src.solvers.p6_cell_condensed_action import (
    P6CellCondensedAction,
    P6CellPortTerms,
    P6RetainedBALHBridge,
    build_p6_cell_condensed_action_from_carrier,
    condense_physical_cell_blocks,
    native_residual_from_augmented,
)


def _matrix(rng: np.random.Generator, rows: int, columns: int, diagonal: float = 0.0) -> np.ndarray:
    value = rng.normal(size=(rows, columns)) + 1j * rng.normal(size=(rows, columns))
    if rows == columns:
        value += diagonal * np.eye(rows)
    return value.astype(np.complex128)


@dataclass
class _FakeCondensed:
    blocks: tuple[dict[str, np.ndarray], ...]

    def __post_init__(self) -> None:
        self.matrix = None
        self.active_rows = 2
        self.appended_rows = 2
        self.full_rows = 4
        self.owned_active_rows = 2
        self.owned_appended_rows = 2
        self.comm = MPI.COMM_SELF
        trace = np.asarray([2, 3], dtype=PETSc.IntType)
        self.owned_trace_original_dofs = trace.copy()
        self.trace_constraints = SimpleNamespace(
            owned_active_original_dofs=trace.copy(),
            original_to_active={2: 0, 3: 1},
            expansion_by_original={
                2: (np.asarray([0], dtype=PETSc.IntType), np.asarray([1.0 + 0.0j])),
                3: (np.asarray([1], dtype=PETSc.IntType), np.asarray([1.0 + 0.0j])),
            },
        )
        self.cell_recovery_maps = tuple(
            CellRecoveryMap(
                interior_original_dofs=np.asarray([0, 1], dtype=PETSc.IntType),
                trace_original_dofs=trace.copy(),
                class_key=(index,),
            )
            for index, _block in enumerate(self.blocks)
        )
        self.interior_lu_by_class = {}
        self.interior_from_trace_by_class = {}
        self.trace_from_interior_rhs_by_class = {}
        self.retained_local_schur_by_class = {}
        for index, block in enumerate(self.blocks):
            factor = lu_factor(block["Vii"])
            xit = lu_solve(factor, block["Vit"])
            self.interior_lu_by_class[(index,)] = factor
            self.interior_from_trace_by_class[(index,)] = -xit
            self.trace_from_interior_rhs_by_class[(index,)] = -block["Vti"] @ lu_solve(
                factor, np.eye(2, dtype=np.complex128)
            )
            self.retained_local_schur_by_class[(index,)] = block["Vtt"] - block["Vti"] @ xit
        self.build_audit = {}

    def create_augmented_vector(self) -> PETSc.Vec:
        return PETSc.Vec().createSeq(self.active_rows + self.appended_rows, comm=PETSc.COMM_SELF)

    def destroy(self) -> None:
        self.matrix = None


def _problem() -> tuple[_FakeCondensed, dict[str, np.ndarray], P6CellCondensedAction]:
    rng = np.random.default_rng(20260914)
    block = {
        "Vii": _matrix(rng, 2, 2, 5.0),
        "Vit": _matrix(rng, 2, 2),
        "Vti": _matrix(rng, 2, 2),
        "Vtt": _matrix(rng, 2, 2, 3.0),
        "Bi": _matrix(rng, 2, 2),
        "Bt": _matrix(rng, 2, 2),
        "Di": _matrix(rng, 2, 2),
        "Dt": _matrix(rng, 2, 2),
        "H": _matrix(rng, 2, 2, 4.0),
    }
    condensed = _FakeCondensed((block,))
    terms = {
        0: P6CellPortTerms(
            block["Bi"], block["Di"], np.asarray([0, 1], dtype=PETSc.IntType),
            Bt=block["Bt"], Dt=block["Dt"], H=block["H"],
        )
    }
    action = P6CellCondensedAction(condensed, H_p=block["H"] * 0.0 + _matrix(rng, 2, 2, 6.0), port_terms=terms)
    return condensed, block, action


def test_nonhermitian_local_condensation_and_recovery_match_dense_blocks() -> None:
    rng = np.random.default_rng(19)
    ni, nt, np_ = 3, 2, 2
    blocks = {
        name: _matrix(rng, rows, columns, diagonal)
        for name, rows, columns, diagonal in (
            ("Vii", ni, ni, 5.0), ("Vit", ni, nt, 0.0), ("Vti", nt, ni, 0.0),
            ("Vtt", nt, nt, 3.0), ("Bi", ni, np_, 0.0), ("Bt", nt, np_, 0.0),
            ("Di", np_, ni, 0.0), ("Dt", np_, nt, 0.0), ("H", np_, np_, 4.0),
        )
    }
    cell = condense_physical_cell_blocks(*(blocks[name] for name in (
        "Vii", "Vit", "Vti", "Vtt", "Bi", "Bt", "Di", "Dt", "H"
    )))
    inverse = np.linalg.inv(blocks["Vii"])
    np.testing.assert_allclose(cell.S_V, blocks["Vtt"] - blocks["Vti"] @ inverse @ blocks["Vit"])
    np.testing.assert_allclose(cell.Bhat, blocks["Bt"] - blocks["Vti"] @ inverse @ blocks["Bi"])
    np.testing.assert_allclose(cell.Dhat, blocks["Dt"] - blocks["Di"] @ inverse @ blocks["Vit"])
    np.testing.assert_allclose(cell.Hhat, blocks["H"] + blocks["Di"] @ inverse @ blocks["Bi"])
    trace = _matrix(rng, nt, 1)[:, 0]
    alpha = _matrix(rng, np_, 1)[:, 0]
    rhs_i = _matrix(rng, ni, 1)[:, 0]
    expected = inverse @ (rhs_i - blocks["Vit"] @ trace - blocks["Bi"] @ alpha)
    np.testing.assert_allclose(cell.recover(trace, alpha, rhs_i), expected, rtol=2e-12, atol=2e-12)
    assert not np.allclose(blocks["Di"], blocks["Bi"].conj().T)


def test_action_rhs_recovery_and_native_residual_identity_match_oracle() -> None:
    _condensed, block, action = _problem()
    hp = action.H_p
    inverse = np.linalg.inv(block["Vii"])
    sv = block["Vtt"] - block["Vti"] @ inverse @ block["Vit"]
    bhat = block["Bt"] - block["Vti"] @ inverse @ block["Bi"]
    dhat = block["Dt"] - block["Di"] @ inverse @ block["Vit"]
    hhat = hp + block["Di"] @ inverse @ block["Bi"]
    reduced = np.block([[sv, bhat], [-dhat, hhat]])
    rng = np.random.default_rng(77)
    y = _matrix(rng, 4, 1)[:, 0]
    np.testing.assert_allclose(action.apply(y), reduced @ y, rtol=2e-12, atol=2e-12)
    np.testing.assert_allclose(action.apply(y + 0.25j * y), action.apply(y) + 0.25j * action.apply(y))
    b = _matrix(rng, 4, 1)[:, 0]
    rp = _matrix(rng, 2, 1)[:, 0]
    expected_rhs = np.r_[b[2:] - block["Vti"] @ inverse @ b[:2], rp + block["Di"] @ inverse @ b[:2]]
    np.testing.assert_allclose(action.reduce_rhs(b, port_rhs=rp), expected_rhs, rtol=2e-12, atol=2e-12)
    np.testing.assert_allclose(
        action.recover_storage(y, full_rhs=b)[:2],
        inverse @ b[:2] - inverse @ block["Vit"] @ y[:2] - inverse @ block["Bi"] @ y[2:],
        rtol=2e-12,
        atol=2e-12,
    )

    V = np.block([[block["Vii"], block["Vit"]], [block["Vti"], block["Vtt"]]])
    B = np.vstack([block["Bi"], block["Bt"]])
    D = np.hstack([block["Di"], block["Dt"]])
    x = _matrix(rng, 4, 1)[:, 0]
    alpha = y[2:]
    rhs = _matrix(rng, 4, 1)[:, 0]
    top_error = rhs - V @ x - B @ alpha
    port_error = D @ x - hp @ alpha
    native = rhs - (V + B @ np.linalg.solve(hp, D)) @ x
    np.testing.assert_allclose(
        native_residual_from_augmented(action, top_error, port_error),
        native,
        rtol=2e-12,
        atol=2e-12,
    )
    evaluated = action.evaluate_native_residual(
        y,
        b,
        lambda value: (V + B @ np.linalg.solve(hp, D)) @ value,
    )
    assert evaluated["strict_zero_slave_storage"] is True
    assert evaluated["internal_residual_relative"] <= 2e-12
    np.testing.assert_allclose(
        evaluated["native_residual"],
        b - (V + B @ np.linalg.solve(hp, D)) @ evaluated["storage_solution"],
        rtol=2e-12,
        atol=2e-12,
    )
    np.testing.assert_allclose(
        evaluated["native_identity_difference"],
        0.0,
        rtol=0.0,
        atol=3e-12,
    )
    reduced_rhs = action.reduce_rhs(b)
    supplied_residual = reduced_rhs - action.apply(y)
    apply_count_before = action.audit["apply_count"]
    supplied = action.evaluate_native_residual(
        y,
        b,
        lambda value: (V + B @ np.linalg.solve(hp, D)) @ value,
        reduced_residual=supplied_residual,
    )
    assert supplied["reduced_residual_supplied"] is True
    assert action.audit["apply_count"] == apply_count_before
    for key in (
        "native_rhs_operation_scale",
        "native_identity_operation_scale",
        "port_operation_scale",
        "internal_operation_scale",
        "schur_operation_scale",
        "schur_port_identity_operation_scale",
    ):
        assert supplied[key] >= 0.0
    assert action.audit["global_s6_allocated"] is False
    assert action.audit["global_a6_allocated"] is False


def test_retained_bal_h_bridge_uses_original_hp_and_one_bal_h_call() -> None:
    _condensed, block, action = _problem()
    hp = action.H_p
    V = np.block([[block["Vii"], block["Vit"]], [block["Vti"], block["Vtt"]]])
    B = np.vstack([block["Bi"], block["Bt"]])
    D = np.hstack([block["Di"], block["Dt"]])
    a6 = V + B @ np.linalg.solve(hp, D)
    sv = block["Vtt"] - block["Vti"] @ np.linalg.solve(block["Vii"], block["Vit"])
    bhat = block["Bt"] - block["Vti"] @ np.linalg.solve(block["Vii"], block["Bi"])
    dhat = block["Dt"] - block["Di"] @ np.linalg.solve(block["Vii"], block["Vit"])
    reduced = np.block([[sv, bhat], [-dhat, action.Hhat]])
    bridge = P6RetainedBALHBridge(action, lambda rhs: np.linalg.solve(a6, rhs))
    rhs = np.asarray([1.0 + 0.2j, -0.3 + 0.7j, 0.4 - 0.5j, -0.8 + 0.1j])
    rhs_before = rhs.copy()
    observed = bridge.apply(rhs)
    np.testing.assert_allclose(observed, np.linalg.solve(reduced, rhs), rtol=2e-11, atol=2e-11)
    assert bridge.apply_count == bridge.bal_h_count == 1
    assert action.hp_solve_count == 2
    assert not np.allclose(action.Hhat, action.H_p)
    np.testing.assert_array_equal(rhs, rhs_before)

    second = np.asarray([-0.2 + 0.4j, 0.9 - 0.1j, -0.7 - 0.6j, 0.3 + 0.8j])
    second_before = second.copy()
    repeated = bridge.apply(rhs)
    combined = bridge.apply(rhs + second)
    np.testing.assert_allclose(repeated, observed, rtol=0.0, atol=0.0)
    np.testing.assert_allclose(
        combined,
        observed + bridge.apply(second),
        rtol=2e-11,
        atol=2e-11,
    )
    np.testing.assert_allclose(
        bridge.apply((0.37 - 0.22j) * rhs),
        (0.37 - 0.22j) * observed,
        rtol=2e-11,
        atol=2e-11,
    )
    np.testing.assert_array_equal(rhs, rhs_before)
    np.testing.assert_array_equal(second, second_before)

    bal_h_before = bridge.bal_h_count
    zero = bridge.apply(np.zeros_like(rhs))
    np.testing.assert_array_equal(zero, np.zeros_like(rhs))
    assert bridge.apply_count == 6
    assert bridge.bal_h_count == bal_h_before


def test_direct_trace_carrier_and_mpc_slave_are_fail_closed() -> None:
    condensed, block, _action = _problem()

    class Entry:
        def __init__(self, port: int) -> None:
            self.normalization_h = 2.0 + 0.5j + port
            self.coupling_rows = np.asarray([0, 2] if port == 0 else [1, 3], dtype=np.int64)
            self.coupling_values = np.asarray([1.0 + 0.1j, 0.4 - 0.2j] if port == 0 else [0.3 + 0.4j, -0.1 + 0.2j])
            self.projection_rows = np.asarray([1, 3] if port == 0 else [0, 2], dtype=np.int64)
            self.projection_values = np.asarray([-0.2 + 0.3j, 0.6 + 0.1j] if port == 0 else [0.7 - 0.2j, 0.2 + 0.3j])

    carrier = SimpleNamespace(entries=(Entry(0), Entry(1)))
    carrier_action = build_p6_cell_condensed_action_from_carrier(condensed, carrier)
    assert carrier_action.audit["direct_trace_B_entry_count"] == 2
    assert carrier_action.audit["direct_trace_D_entry_count"] == 2
    assert np.all(np.isfinite(carrier_action.Hhat))
    carrier_action.destroy()

    slave_constraints = SimpleNamespace(
        owned_active_original_dofs=np.asarray([2], dtype=PETSc.IntType),
        original_to_active={2: 0},
        expansion_by_original={
            2: (np.asarray([0], dtype=PETSc.IntType), np.asarray([1.0 + 0j])),
            3: (np.asarray([0], dtype=PETSc.IntType), np.asarray([0.5 + 0.2j])),
        },
    )
    condensed.trace_constraints = slave_constraints
    with pytest.raises(ValueError, match="MPC slave"):
        build_p6_cell_condensed_action_from_carrier(condensed, carrier)


def test_action_cleanup_releases_shell_resources_and_rejects_reuse() -> None:
    _condensed, _block, action = _problem()
    matrix = action.create_matrix()
    source = matrix.createVecRight()
    target = matrix.createVecLeft()
    source.set(1.0)
    matrix.mult(source, target)
    assert action.audit["apply_count"] == 1
    action.destroy()
    source.destroy()
    target.destroy()
    with pytest.raises(RuntimeError, match="destroyed"):
        action.apply(np.ones(4, dtype=np.complex128))


def test_action_owns_mutated_hp_and_destroys_vec_result_on_mult_failure() -> None:
    condensed, block, base_action = _problem()
    base_action.destroy()
    rng = np.random.default_rng(404)
    hp = _matrix(rng, 2, 2, 7.0)
    hp_before = hp.copy()
    action = P6CellCondensedAction(
        condensed,
        H_p=hp,
        port_terms={
            0: P6CellPortTerms(
                block["Bi"], block["Di"], np.asarray([0, 1], dtype=PETSc.IntType),
                Bt=block["Bt"], Dt=block["Dt"], H=_matrix(rng, 2, 2, 0.0),
            )
        },
    )
    try:
        np.testing.assert_array_equal(hp, hp_before)
        source = action.create_reduced_rhs_vector()
        source.set(1.0)
        try:
            def fail(_matrix: PETSc.Mat | None, _source: PETSc.Vec, _target: PETSc.Vec) -> None:
                raise RuntimeError("intentional MatShell failure")

            action.mult = fail  # type: ignore[method-assign]
            with pytest.raises(RuntimeError, match="intentional MatShell failure"):
                action.apply(source)
        finally:
            source.destroy()
    finally:
        action.destroy()


def test_noncommuting_sum_adjoint_bilinear_repeat_and_input_immutability() -> None:
    rng = np.random.default_rng(3920)
    fields = []
    for seed in (1, 2):
        local = np.random.default_rng(seed)
        fields.append(
            {
                name: _matrix(local, rows, columns, diagonal)
                for name, rows, columns, diagonal in (
                    ("Vii", 2, 2, 5.0), ("Vit", 2, 2, 0.0),
                    ("Vti", 2, 2, 0.0), ("Vtt", 2, 2, 3.0),
                    ("Bi", 2, 2, 0.0), ("Bt", 2, 2, 0.0),
                    ("Di", 2, 2, 0.0), ("Dt", 2, 2, 0.0),
                    ("H", 2, 2, 4.0),
                )
            }
        )
    condensed_cells = [
        condense_physical_cell_blocks(
            *(field[name] for name in (
                "Vii", "Vit", "Vti", "Vtt", "Bi", "Bt", "Di", "Dt", "H"
            ))
        )
        for field in fields
    ]
    combined = {
        name: fields[0][name] + fields[1][name]
        for name in fields[0]
    }
    combined_cell = condense_physical_cell_blocks(
        *(combined[name] for name in (
            "Vii", "Vit", "Vti", "Vtt", "Bi", "Bt", "Di", "Dt", "H"
        ))
    )
    assert not np.allclose(
        combined_cell.S_V,
        condensed_cells[0].S_V + condensed_cells[1].S_V,
    )

    _condensed, block, action = _problem()
    hp = action.H_p
    inverse = np.linalg.inv(block["Vii"])
    reduced = np.block([
        [block["Vtt"] - block["Vti"] @ inverse @ block["Vit"],
         block["Bt"] - block["Vti"] @ inverse @ block["Bi"]],
        [-(block["Dt"] - block["Di"] @ inverse @ block["Vit"]),
         hp + block["Di"] @ inverse @ block["Bi"]],
    ])
    x = _matrix(rng, 4, 1)[:, 0]
    y = _matrix(rng, 4, 1)[:, 0]
    y_before = y.copy()
    inventory_before = dict(action.buffer_inventory)
    observed = action.apply(y)
    repeated = action.apply(y)
    np.testing.assert_array_equal(y, y_before)
    np.testing.assert_allclose(observed, repeated, rtol=0.0, atol=0.0)
    np.testing.assert_allclose(
        np.vdot(x, observed),
        np.vdot(reduced.conj().T @ x, y),
        rtol=2e-12,
        atol=2e-12,
    )
    assert dict(action.buffer_inventory) == inventory_before
    with pytest.raises(ValueError, match="expected"):
        action.apply(np.ones(3, dtype=np.complex128))
    action.destroy()


def test_fixed_p64_galerkin_then_condense_does_not_equal_trace_condense() -> None:
    """Keep the two fine internal DoFs needed to expose non-commutation.

    ``A4=P64^H A6 P64`` is constructed exactly.  The comparison then uses
    the scalar coarse trace Schur complement versus the fine two-internal-DoF
    Schur complement restricted by the trace block of ``P64``.
    """

    A6 = np.asarray(
        [
            [4.0 + 0.2j, 0.7 - 0.1j, 1.2 + 0.3j],
            [-0.4 + 0.5j, 3.3 - 0.2j, -0.8 + 0.4j],
            [0.6 - 0.7j, 1.1 + 0.2j, 2.4 + 0.6j],
        ],
        dtype=np.complex128,
    )
    P64 = np.asarray(
        [
            [1.0 + 0.1j, 0.0 + 0.0j],
            [0.25 - 0.2j, 0.0 + 0.0j],
            [0.0 + 0.0j, 1.0 + 0.0j],
        ],
        dtype=np.complex128,
    )
    A4 = P64.conj().T @ A6 @ P64
    np.testing.assert_allclose(
        A4,
        np.asarray(
            [
                [4.31225 + 0.026j, 0.95 + 0.12j],
                [0.985 - 0.81j, 2.4 + 0.6j],
            ],
            dtype=np.complex128,
        ),
        rtol=0.0,
        atol=2e-15,
    )

    fine_internal = slice(0, 2)
    fine_trace = slice(2, 3)
    coarse_internal = slice(0, 1)
    coarse_trace = slice(1, 2)
    S6 = A6[fine_trace, fine_trace] - (
        A6[fine_trace, fine_internal]
        @ np.linalg.solve(A6[fine_internal, fine_internal], A6[fine_internal, fine_trace])
    )
    S4 = A4[coarse_trace, coarse_trace] - (
        A4[coarse_trace, coarse_internal]
        @ np.linalg.solve(
            A4[coarse_internal, coarse_internal], A4[coarse_internal, coarse_trace]
        )
    )
    P_trace = P64[fine_trace, coarse_trace]
    restricted_fine_schur = P_trace.conj().T @ S6 @ P_trace

    assert abs(complex(S4[0, 0] - restricted_fine_schur[0, 0])) > 1.0e-3
    np.testing.assert_allclose(
        S4,
        np.asarray([[2.16138079 + 0.75247356j]], dtype=np.complex128),
        rtol=2e-8,
        atol=2e-8,
    )
    np.testing.assert_allclose(
        restricted_fine_schur,
        np.asarray([[2.40110146 + 0.77955336j]], dtype=np.complex128),
        rtol=2e-8,
        atol=2e-8,
    )


def test_real_ffcx_mpc_action_only_matches_augmented_schur_and_nonzero_rhs() -> None:
    """Exercise the retained action on a real two-cell complex MPC fixture."""

    import dolfinx_mpc
    import ufl
    from basix.ufl import element
    from dolfinx import fem, mesh
    from dolfinx import default_real_type
    from dolfinx.fem import petsc as fem_petsc
    from scipy.sparse import csr_matrix

    from src.solvers.hcurl_assembly_time_condensation import (
        build_unconstrained_assembly_time_condensation,
    )
    from src.solvers.hcurl_cell_static_condensation import owned_hcurl_cell_interior_dofs

    domain = mesh.create_unit_cube(
        MPI.COMM_SELF, 2, 1, 1, cell_type=mesh.CellType.hexahedron
    )
    tags = mesh.meshtags(
        domain,
        3,
        np.asarray([0, 1], dtype=np.int32),
        np.asarray([1, 2], dtype=np.int32),
    )
    space = fem.functionspace(
        domain,
        element("N1curl", domain.basix_cell(), 2, dtype=default_real_type),
    )
    u, v = ufl.TrialFunction(space), ufl.TestFunction(space)
    dx = ufl.Measure("dx", domain=domain, subdomain_data=tags)
    form = fem.form(
        (
            (ufl.inner(ufl.curl(u), ufl.curl(v))
             + PETSc.ScalarType(2.5 - 0.2j) * ufl.inner(u, v)) * dx(1)
            + (ufl.inner(ufl.curl(u), ufl.curl(v))
               + PETSc.ScalarType(1.7 + 0.1j) * ufl.inner(u, v)) * dx(2)
        )
    )
    interiors = np.concatenate(owned_hcurl_cell_interior_dofs(space))
    n = int(space.dofmap.index_map.size_global)
    trace = np.setdiff1d(np.arange(n), interiors)
    master, slave = int(trace[0]), int(trace[-1])
    mpc = dolfinx_mpc.MultiPointConstraint(space)
    mpc.add_constraint(
        space,
        np.asarray([slave], dtype=np.int32),
        np.asarray([master], dtype=np.int64),
        np.asarray([np.exp(0.43j)], dtype=np.complex128),
        np.asarray([0], dtype=np.int32),
        np.asarray([0, 1], dtype=np.int32),
    )
    mpc.finalize()
    full = dolfinx_mpc.assemble_matrix(form, mpc, bcs=[])
    full.assemble()
    unconstrained_full = fem_petsc.assemble_matrix(form, bcs=[])
    unconstrained_full.assemble()
    condensed = build_unconstrained_assembly_time_condensation(
        form,
        space,
        tags,
        mpc=mpc,
        appended_global_rows=2,
        materialize_global_matrix=False,
        retain_local_schur_for_matrix_free=True,
        sum_duplicate_cell_integrals=True,
    )
    rng = np.random.default_rng(3919)
    B = 0.02 * (rng.normal(size=(n, 2)) + 1j * rng.normal(size=(n, 2))
                ).astype(np.complex128)
    D = 0.03 * (rng.normal(size=(2, n)) + 1j * rng.normal(size=(2, n))
                ).astype(np.complex128)
    B[slave, :] = 0.0
    D[:, slave] = 0.0
    H = np.diag(np.asarray([1.1 + 0.3j, 0.9 - 0.2j], dtype=np.complex128))
    entries = tuple(
        SimpleNamespace(
            coupling_rows=np.flatnonzero(B[:, port]).astype(PETSc.IntType),
            coupling_values=B[B[:, port] != 0.0, port].copy(),
            projection_rows=np.flatnonzero(D[port] != 0.0).astype(PETSc.IntType),
            projection_values=D[port, D[port] != 0.0].copy(),
            normalization_h=H[port, port],
        )
        for port in range(2)
    )
    carrier = SimpleNamespace(entries=entries)
    action = None
    try:
        action = build_p6_cell_condensed_action_from_carrier(condensed, carrier)
        tensor_identities = condensed.build_audit["action_only_complete_tensor_identities"]
        assert len(tensor_identities) == len(condensed.retained_local_schur_by_class)
        assert tensor_identities
        for identity in tensor_identities.values():
            assert identity["dtype"] == "complex128"
            assert len(identity["shape"]) == 2
            assert len(identity["raw_sha256"]) == 64
            assert len(identity["oriented_sha256"]) == 64
        indptr, indices, values = full.getValuesCSR()
        volume = csr_matrix((values, indices, indptr), shape=(n, n)).toarray()
        indptr_u, indices_u, values_u = unconstrained_full.getValuesCSR()
        volume_unconstrained = csr_matrix(
            (values_u, indices_u, indptr_u), shape=(n, n)
        ).toarray()
        augmented = np.block([[volume, B], [-D, H]])
        retained = np.r_[
            condensed.trace_constraints.owned_active_original_dofs,
            n + np.arange(2),
        ]
        eliminated = interiors
        expected = augmented[np.ix_(retained, retained)] - (
            augmented[np.ix_(retained, eliminated)]
            @ np.linalg.solve(
                augmented[np.ix_(eliminated, eliminated)],
                augmented[np.ix_(eliminated, retained)],
            )
        )
        for seed in (11, 12, 13):
            vector = rng.normal(size=action.reduced_size) + 1j * rng.normal(size=action.reduced_size)
            np.testing.assert_allclose(action.apply(vector), expected @ vector, rtol=2e-10, atol=2e-11)
        rhs = rng.normal(size=n) + 1j * rng.normal(size=n)
        rhs[slave] = 0.0
        port_rhs = rng.normal(size=2) + 1j * rng.normal(size=2)
        expected_rhs = np.r_[rhs, port_rhs][retained] - (
            augmented[np.ix_(retained, eliminated)]
            @ np.linalg.solve(
                augmented[np.ix_(eliminated, eliminated)],
                rhs[eliminated],
            )
        )
        np.testing.assert_allclose(
            action.reduce_rhs(rhs, port_rhs=port_rhs, rhs_is_mpc_dual=True),
            expected_rhs,
            rtol=2e-10,
            atol=2e-11,
        )
        solution = np.linalg.solve(expected, expected_rhs)
        recovered = action.recover_storage(solution, full_rhs=rhs)
        assert recovered[slave] == 0.0
        phase = np.exp(0.43j)

        def native_action(value: np.ndarray) -> np.ndarray:
            primal = value.copy()
            primal[slave] = phase * primal[master]
            raw = (volume_unconstrained + B @ np.linalg.solve(H, D)) @ primal
            projected = raw.copy()
            projected[master] += np.conjugate(phase) * raw[slave]
            projected[slave] = 0.0
            return projected

        evaluated = action.evaluate_native_residual(
            solution,
            rhs,
            native_action,
            port_rhs=port_rhs,
            rhs_is_mpc_dual=True,
        )
        assert evaluated["internal_residual_relative"] <= 3e-10
        assert evaluated["port_residual_relative"] <= 3e-10
        assert evaluated["native_identity_relative"] <= 3e-10, {
            key: evaluated[key]
            for key in (
                "native_identity_relative",
                "native_residual_relative",
                "internal_residual_relative",
                "port_residual_relative",
                "schur_port_identity_relative",
                "native_identity_operation_scale",
            )
        } | {
            "norm_native_residual": float(np.linalg.norm(evaluated["native_residual"])),
            "norm_derived_native_residual": float(np.linalg.norm(evaluated["derived_native_residual"])),
            "norm_augmented_fe": float(np.linalg.norm(evaluated["augmented_fe_residual"])),
            "norm_difference": float(np.linalg.norm(evaluated["native_identity_difference"])),
        }
        assert evaluated["schur_port_identity_relative"] <= 3e-10
        assert evaluated["storage_solution"][slave] == 0.0
        assert action.buffer_inventory["unique_S_V_buffers"] <= action.buffer_inventory["class_count"]
        assert action.buffer_inventory["unique_recovery_buffers"] <= action.buffer_inventory["class_count"]
        assert action.operator_recipe["global_S6_matrix"] is False
    finally:
        if action is not None:
            action.destroy()
        else:
            condensed.destroy()
        unconstrained_full.destroy()
        full.destroy()
