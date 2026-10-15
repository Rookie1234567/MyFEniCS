"""Focused H1f checks for the borrowed BAL_H block-LDU factory."""

from __future__ import annotations

import base64
import copy
import hashlib
import inspect
import json
import linecache
import os
import sys
from collections.abc import Mapping
from decimal import Decimal, localcontext
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest
from mpi4py import MPI
from petsc4py import PETSc

import src.solvers.hybrid_fem_modal_block_ldu as block_ldu
from src.solvers.hybrid_fem_modal_augmented_direct import (
    HybridAugmentedLayout,
    internal_modal_constraint_matrix,
    internal_modal_rhs_correction,
)
from src.solvers.hybrid_fem_modal_iterative import (
    HybridBlockOperator,
    create_hybrid_assembled_block_action,
)
from src.solvers.physical_balanced_h6 import H6_DEGREE, FixedH6
from src.solvers.physical_balanced_physical_operator import (
    P4PhysicalResidualGateError,
)
from src.solvers.physical_balanced_side_inverse import (
    FIXED_PHYSICAL_BALH_MODAL_FEEDBACK_METHOD,
    FixedH6ActiveTraceAction,
    FixedPhysicalBalancedActiveTraceAction,
    SideBalancedInverse,
)
from src.test.test_241_task037b_hybrid_action_modal_schur import (
    _destroy_fixture,
    _gather_matrix,
    _gather_vector,
    _matrix_from_dense,
    _tiny_fixture,
)
from src.test.test_349_task041_balh_side_inverse import (
    _build_fixture,
    _FullAction,
    _IdentityP4,
    _IdentityTransfer,
)

pytestmark = pytest.mark.skipif(
    MPI.COMM_WORLD.size not in (1, 2),
    reason="Task041 H1f focused block-LDU tests are serial/MPI2 only",
)


def _set_vector(vector: PETSc.Vec, values: np.ndarray) -> None:
    first, last = (int(value) for value in vector.getOwnershipRange())
    vector.getArray()[:] = np.asarray(values[first:last], dtype=PETSc.ScalarType)
    vector.assemble()


def _relative_or_absolute(actual: np.ndarray, expected: np.ndarray) -> float:
    difference = float(np.linalg.norm(np.asarray(actual) - np.asarray(expected)))
    denominator = float(np.linalg.norm(np.asarray(expected)))
    return difference / denominator if denominator > 0.0 else difference


def _decimal_complex_pair(value: complex) -> tuple[Decimal, Decimal]:
    item = complex(value)
    return Decimal.from_float(item.real), Decimal.from_float(item.imag)


def _decimal_complex_matvec(
    matrix: np.ndarray, vector: np.ndarray
) -> list[tuple[Decimal, Decimal]]:
    """Independent exact-decimal complex multiply/add on binary64 inputs."""

    values = np.asarray(matrix, dtype=np.complex128)
    rhs = np.asarray(vector, dtype=np.complex128)
    if values.ndim != 2 or rhs.ndim != 1 or values.shape[1] != rhs.size:
        raise ValueError("Decimal matrix oracle received an incompatible shape")
    output: list[tuple[Decimal, Decimal]] = []
    with localcontext() as decimal_context:
        decimal_context.prec = 180
        for row in values:
            real_sum = Decimal(0)
            imag_sum = Decimal(0)
            for coefficient, value in zip(row, rhs, strict=True):
                coeff_real, coeff_imag = _decimal_complex_pair(coefficient)
                value_real, value_imag = _decimal_complex_pair(value)
                real_sum += coeff_real * value_real - coeff_imag * value_imag
                imag_sum += coeff_real * value_imag + coeff_imag * value_real
            output.append((real_sum, imag_sum))
    return output


def _decimal_complex_sum(
    left: tuple[Decimal, Decimal], right: tuple[Decimal, Decimal]
) -> tuple[Decimal, Decimal]:
    with localcontext() as context:
        context.prec = 180
        return left[0] + right[0], left[1] + right[1]


def _decimal_complex_difference(
    left: tuple[Decimal, Decimal], right: tuple[Decimal, Decimal]
) -> tuple[Decimal, Decimal]:
    with localcontext() as context:
        context.prec = 180
        return left[0] - right[0], left[1] - right[1]


def _decimal_complex_modulus(value: tuple[Decimal, Decimal]) -> Decimal:
    with localcontext() as context:
        context.prec = 180
        return (value[0] * value[0] + value[1] * value[1]).sqrt()


def _decimal_sum(values: Any) -> Decimal:
    with localcontext() as context:
        context.prec = 180
        return sum(values, Decimal(0))


def _validate_v15_capture_timeline(
    events: Any,
    checks: Any,
    *,
    diagnostic_apply_index: int,
    attempted_production_pc_apply_index: int,
    expected_attempt_index: int,
    prior_attempt_index: int | None,
    expected_action_identity: Any,
) -> dict[str, Any]:
    """Validate one callback followed by every same-attempt row commit/check pair."""

    errors: list[str] = []
    if not isinstance(events, list) or not events:
        return {
            "status": "rejected",
            "pair_count": 0,
            "errors": ["capture timeline is absent or empty"],
        }
    if not isinstance(checks, list):
        return {
            "status": "rejected",
            "pair_count": 0,
            "errors": ["same-attempt d checks are not a list"],
        }

    callback_events = [
        event
        for event in events
        if isinstance(event, Mapping)
        and event.get("event") == "callback_returned_arrays_copied"
    ]
    if len(callback_events) != 1 or events[0] is not callback_events[0]:
        errors.append("exactly one callback capture must be the first event")
    callback = callback_events[0] if callback_events else {}
    if callback.get("diagnostic_apply_index") != diagnostic_apply_index:
        errors.append("callback diagnostic apply identity differs")
    if (
        callback.get("attempted_production_pc_apply_index")
        != attempted_production_pc_apply_index
    ):
        errors.append("callback production apply identity differs")
    if callback.get("attempt_index") != expected_attempt_index:
        errors.append("callback belongs to a different attempt")
    callback_action = callback.get("action_identity")
    if not isinstance(callback_action, Mapping):
        errors.append("callback action identity is absent")
    if callback_action != expected_action_identity:
        errors.append("callback action identity differs from the committed row")
    if prior_attempt_index == expected_attempt_index:
        errors.append("prior committed row belongs to the current attempt")

    remaining = events[1:] if events and events[0] is callback else events
    if len(remaining) < 2 or len(remaining) % 2 != 0:
        errors.append("row commits must be followed by at least one d check")
    pair_count = len(remaining) // 2
    if len(checks) != pair_count or pair_count < 1:
        errors.append("the check list does not match the committed row count")

    for pair_index in range(pair_count):
        commit = remaining[2 * pair_index]
        check_event = remaining[2 * pair_index + 1]
        check = checks[pair_index] if pair_index < len(checks) else {}
        if not isinstance(commit, Mapping) or commit.get("event") != "production_row_record_committed":
            errors.append(f"pair {pair_index}: production row commit is out of order")
            continue
        if not isinstance(check_event, Mapping) or check_event.get("event") != "same_attempt_d_checked_after_record_commit":
            errors.append(f"pair {pair_index}: d check is not immediately after commit")
            continue
        for label, item in (("commit", commit), ("check", check_event), ("result", check)):
            if not isinstance(item, Mapping):
                errors.append(f"pair {pair_index}: {label} record is missing")
                continue
            if item.get("diagnostic_apply_index") != diagnostic_apply_index:
                errors.append(f"pair {pair_index}: {label} diagnostic apply differs")
            if (
                item.get("attempted_production_pc_apply_index")
                != attempted_production_pc_apply_index
            ):
                errors.append(f"pair {pair_index}: {label} production apply differs")
            if item.get("attempt_index") != expected_attempt_index:
                errors.append(f"pair {pair_index}: {label} attempt differs")
        for label, item in (("commit", commit), ("check", check_event), ("result", check)):
            if isinstance(item, Mapping) and item.get("action_identity") != callback_action:
                errors.append(f"pair {pair_index}: {label} action identity differs")
        if not isinstance(check, Mapping):
            continue
        if check.get("status") != "passed":
            errors.append(f"pair {pair_index}: same-attempt d check failed")
        if check.get("binary64_d_equals_w_minus_r") is not True:
            errors.append(f"pair {pair_index}: d is not the current binary64 w-r")
        if check.get("prior_attempt_was_not_used") is not True:
            errors.append(f"pair {pair_index}: prior attempt was reused")
        if check.get("compared_only_after_production_record_delegate") is not True:
            errors.append(f"pair {pair_index}: d check preceded production commit")

    return {
        "status": "passed" if not errors else "rejected",
        "diagnostic_apply_index": diagnostic_apply_index,
        "attempted_production_pc_apply_index": attempted_production_pc_apply_index,
        "expected_attempt_index": expected_attempt_index,
        "prior_attempt_index": prior_attempt_index,
        "callback_count": len(callback_events),
        "pair_count": pair_count,
        "check_count": len(checks),
        "errors": errors,
    }


def _sample_contract() -> tuple[list[int], dict[str, list[str]], str]:
    columns = [0, 1, 2, 3]
    roles = {
        "0": ["head", "bottom_positive_unattenuated"],
        "1": ["interior", "bottom_positive_unattenuated"],
        "2": ["head", "top_negative_unattenuated"],
        "3": ["tail", "top_negative_unattenuated"],
    }
    contract = {
        "columns": columns,
        "mode_count_per_direction": 2,
        "roles": roles,
    }
    contract_sha = hashlib.sha256(
        json.dumps(contract, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return columns, roles, contract_sha


def _side_block_fixture() -> dict[str, object]:
    tiny = _tiny_fixture()
    bottom_inverse, bottom_owned = _build_fixture(size=4)
    top_inverse, top_owned = _build_fixture(size=4)
    bottom = bottom_owned["side_system"]
    top = top_owned["side_system"]
    comm = MPI.COMM_WORLD
    for system, side in ((bottom, "bottom"), (top, "top")):
        system.side = side
        system.global_size = 4
        system.local_mesh = SimpleNamespace(mesh=SimpleNamespace(comm=comm))
        system.b = system.A.createVecRight()
    _set_vector(
        bottom.b,
        np.asarray([0.4 + 0.1j, -0.2 + 0.3j, 0.7 - 0.2j, -0.5 + 0.4j]),
    )
    _set_vector(
        top.b,
        np.asarray([-0.3 + 0.2j, 0.6 - 0.1j, -0.4 - 0.5j, 0.8 + 0.3j]),
    )
    coupling = tiny["coupling"]
    coupling.internal_equation_count = 4
    coupling.bottom.modal_rhs_correction = np.asarray(
        [0.13 - 0.07j, -0.22 + 0.11j], dtype=np.complex128
    )
    coupling.top.modal_rhs_correction = np.asarray(
        [-0.31 + 0.05j, 0.17 + 0.19j], dtype=np.complex128
    )
    layout = HybridAugmentedLayout.build(bottom, top, 4)
    return {
        "tiny": tiny,
        "bottom_inverse": bottom_inverse,
        "top_inverse": top_inverse,
        "bottom_owned": bottom_owned,
        "top_owned": top_owned,
        "bottom": bottom,
        "top": top,
        "coupling": tiny["coupling"],
        "layout": layout,
    }


def _fixed_h6_side_block_fixture() -> dict[str, object]:
    """Use real FixedH6 recurrences behind the existing tiny side inverses."""

    fixture = _side_block_fixture()
    for side in ("bottom", "top"):
        old_inverse = fixture[f"{side}_inverse"]
        old_inverse.destroy()
        h6_bundle = _tiny_fixed_h6_bundle(side)
        side_system = fixture[side]
        side_system.static_condensation.condensed = h6_bundle["condensed"]
        full_action = _FullAction(int(h6_bundle["h6_matrix"].getSize()[0]))
        p4_factor = _IdentityP4(int(h6_bundle["h6_matrix"].getSize()[0]))
        transfer = _IdentityTransfer()
        inverse = SideBalancedInverse(
            side_system,
            full_action,
            p4_factor,
            transfer,
            h6_bundle["h6"],
        )
        fixture[f"{side}_inverse"] = inverse
        fixture[f"{side}_owned"].update(
            {
                "full_action": full_action,
                "p4_factor": p4_factor,
                "transfer": transfer,
                "h6": h6_bundle["h6"],
            }
        )
        # The modal bridge borrows the same H6 and condensed map from the
        # SideBalancedInverse; its separate active test operator is unused.
        h6_bundle["active_operator"].destroy()
    return fixture


def _pack(
    layout: HybridAugmentedLayout,
    bottom: object,
    top: object,
    bottom_values: np.ndarray,
    top_values: np.ndarray,
    modal_values: np.ndarray,
) -> PETSc.Vec:
    bottom_vector = bottom.A.createVecRight()
    top_vector = top.A.createVecRight()
    _set_vector(bottom_vector, bottom_values)
    _set_vector(top_vector, top_values)
    packed = layout.pack(bottom_vector, top_vector, modal_values)
    bottom_vector.destroy()
    top_vector.destroy()
    return packed


def _destroy_side_block_fixture(fixture: dict[str, object]) -> None:
    bottom_inverse = fixture["bottom_inverse"]
    top_inverse = fixture["top_inverse"]
    bottom_owned = fixture["bottom_owned"]
    top_owned = fixture["top_owned"]
    bottom_inverse.destroy()
    top_inverse.destroy()
    bottom_owned["operator"].destroy()
    top_owned["operator"].destroy()
    fixture["bottom"].b.destroy()
    fixture["top"].b.destroy()
    _destroy_fixture(fixture["tiny"])


class _TinyPositiveWindow:
    """Matrix carrier for the real FixedH6 recurrence on a tiny PETSc matrix."""

    def __init__(self, matrix: PETSc.Mat) -> None:
        self.matrix = matrix
        self.audit = {"apply_count": 0}
        self.destroyed = False

    def destroy(self) -> None:
        if self.destroyed:
            return
        self.destroyed = True
        self.matrix.destroy()


def _tiny_fixed_h6_bundle(side: str) -> dict[str, object]:
    comm = MPI.COMM_WORLD
    full_rows = 8
    active_rows = 4
    full_template = PETSc.Vec().createMPI(
        (full_rows // comm.size, full_rows), comm=comm
    )
    active_local_rows = active_rows // comm.size
    active_template = PETSc.Vec().createMPI(
        (active_local_rows, active_rows), comm=comm
    )
    diagonal_factor = np.diag(np.sqrt(np.arange(2.0, 10.0))).astype(
        np.complex128
    )
    phase = 1.0 if side == "bottom" else -1.0
    for index in range(full_rows - 1):
        diagonal_factor[index, index + 1] = phase * (0.05 + 0.03j)
        diagonal_factor[index + 1, index] = phase * (0.02 - 0.04j)
    dense_h6 = diagonal_factor.conj().T @ diagonal_factor + 3.0 * np.eye(
        full_rows, dtype=np.complex128
    )
    h6_matrix = _matrix_from_dense(full_template, full_template, dense_h6)
    active_operator = _matrix_from_dense(
        active_template,
        active_template,
        np.diag(np.asarray([1.0, 1.2, 1.4, 1.6], dtype=np.complex128)),
    )
    diagonal = h6_matrix.createVecRight()
    first, last = map(int, diagonal.getOwnershipRange())
    diagonal.getArray()[:] = np.real(np.diag(dense_h6))[first:last]
    diagonal.assemble()
    seed = h6_matrix.createVecRight()
    first, last = map(int, seed.getOwnershipRange())
    seed.getArray()[:] = np.asarray(
        [1.0 + 0.1j * (row + 1) for row in range(first, last)],
        dtype=PETSc.ScalarType,
    )
    seed.assemble()
    window = _TinyPositiveWindow(h6_matrix)
    h6 = FixedH6(
        window,
        diagonal,
        seed,
        {"source": "test350 tiny SPD PETSc matrix"},
        {"source": "deterministic nonzero test seed"},
    )
    seed.destroy()

    selected_full_rows = np.asarray([0, 2, 4, 6], dtype=PETSc.IntType)
    full_first, full_last = map(int, full_template.getOwnershipRange())
    local_active_original = selected_full_rows[
        (selected_full_rows >= full_first) & (selected_full_rows < full_last)
    ].copy()

    def create_active_vector() -> PETSc.Vec:
        return PETSc.Vec().createMPI(
            (len(local_active_original), active_rows), comm=comm
        )

    condensed = SimpleNamespace(
        full_rows=full_rows,
        active_rows=active_rows,
        owned_active_rows=len(local_active_original),
        trace_constraints=SimpleNamespace(
            owned_active_original_dofs=local_active_original
        ),
        comm=comm,
        create_active_vector=create_active_vector,
    )
    full_template.destroy()
    active_template.destroy()
    return {
        "side": side,
        "selected_full_rows": selected_full_rows,
        "local_active_original": local_active_original,
        "h6_matrix": h6_matrix,
        "active_operator": active_operator,
        "window": window,
        "h6": h6,
        "condensed": condensed,
    }


def _tiny_h6_dense_action(h6: FixedH6) -> np.ndarray:
    rhs = h6.matrix.createVecRight()
    target = h6.matrix.createVecLeft()
    dense = np.empty(h6.matrix.getSize(), dtype=np.complex128)
    first, last = map(int, rhs.getOwnershipRange())
    try:
        for column in range(int(rhs.getSize())):
            rhs.set(0.0)
            if first <= column < last:
                rhs.getArray()[column - first] = 1.0
            rhs.assemble()
            h6.apply_into(rhs, target)
            dense[:, column] = _gather_vector(target)
    finally:
        target.destroy()
        rhs.destroy()
    return dense


def _tiny_fixed_h6_modal_oracle(
    fixture: dict[str, object],
    bottom_h6: np.ndarray,
    top_h6: np.ndarray,
    selected_full_rows: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    coupling = fixture["coupling"]
    blocks = fixture["blocks"]
    mode_count = int(coupling.mode_count_per_direction)
    active_h6 = [
        matrix[np.ix_(selected_full_rows, selected_full_rows)]
        for matrix in (bottom_h6, top_h6)
    ]
    backward = np.asarray(coupling.propagation.backward.factors)
    forward = np.asarray(coupling.propagation.forward.factors)
    bottom_traction = np.concatenate(
        (
            blocks["bottom_positive"],
            blocks["bottom_negative"] * backward[np.newaxis, :],
        ),
        axis=1,
    )
    top_traction = np.concatenate(
        (
            blocks["top_positive"] * forward[np.newaxis, :],
            blocks["top_negative"],
        ),
        axis=1,
    )
    bottom_feedback = np.zeros((2 * mode_count, 2 * mode_count), dtype=np.complex128)
    top_feedback = np.zeros_like(bottom_feedback)
    bottom_feedback[:mode_count, :] = (
        blocks["bottom_projection"] @ active_h6[0] @ bottom_traction
    )
    top_feedback[mode_count:, :] = (
        blocks["top_projection"] @ active_h6[1] @ top_traction
    )
    constraint = np.asarray(
        internal_modal_constraint_matrix(coupling), dtype=np.complex128
    )
    return constraint - bottom_feedback - top_feedback, bottom_feedback, top_feedback


def _fixed_h6_modal_krylov_components():
    """Build the tiny real-H6 recurrence with a dense modal-action oracle."""
    fixture = _tiny_fixture()
    bundles: list[dict[str, object]] = []
    try:
        for side in ("bottom", "top"):
            bundle = _tiny_fixed_h6_bundle(side)
            bundles.append(bundle)
            bundle["adapter"] = FixedH6ActiveTraceAction(
                bundle["active_operator"], bundle["condensed"], bundle["h6"]
            )
        selected = bundles[0]["selected_full_rows"]
        bottom_h6 = _tiny_h6_dense_action(bundles[0]["h6"])
        top_h6 = _tiny_h6_dense_action(bundles[1]["h6"])
        expected, bottom_feedback, top_feedback = _tiny_fixed_h6_modal_oracle(
            fixture, bottom_h6, top_h6, selected
        )
        assert np.linalg.norm(bottom_feedback) > 0.0
        assert np.linalg.norm(top_feedback) > 0.0
        return fixture, bundles, expected
    except BaseException:
        _destroy_fixed_h6_modal_krylov_components(fixture, bundles, None)
        raise


def _destroy_fixed_h6_modal_krylov_components(
    fixture: dict[str, object],
    bundles: list[dict[str, object]],
    system: object | None,
) -> None:
    if system is not None:
        system.destroy()
    for bundle in bundles:
        adapter = bundle.get("adapter")
        if adapter is not None:
            adapter.destroy()
        h6 = bundle.get("h6")
        if h6 is not None:
            h6.destroy()
        operator = bundle.get("active_operator")
        if operator is not None:
            operator.destroy()
    for matrix in fixture.get("v12_owned_matrices", []):
        matrix.destroy()
    _destroy_fixture(fixture)


def _v12_fixed_h6_modal_components():
    """Build actual tiny H6 adapters with a test-injected 40x40 modal matrix."""

    fixture = _tiny_fixture()
    bundles: list[dict[str, object]] = []
    owned_matrices: list[PETSc.Mat] = []
    fixture["v12_owned_matrices"] = owned_matrices
    try:
        for side in ("bottom", "top"):
            bundle = _tiny_fixed_h6_bundle(side)
            bundles.append(bundle)
            bundle["adapter"] = FixedH6ActiveTraceAction(
                bundle["active_operator"], bundle["condensed"], bundle["h6"]
            )

        mode_count = 20
        comm = MPI.COMM_WORLD
        owner = comm.size - 1
        modal_template = PETSc.Vec().createMPI(
            (mode_count if comm.rank == owner else 0, mode_count), comm=comm
        )
        active_template = bundles[0]["active_operator"].createVecRight()
        rng = np.random.default_rng(41012)
        side_blocks = []
        try:
            for _side in ("bottom", "top"):
                projection_dense = (
                    rng.standard_normal((mode_count, 4))
                    + 1j * rng.standard_normal((mode_count, 4))
                ) / 8.0
                positive_dense = (
                    rng.standard_normal((4, mode_count))
                    + 1j * rng.standard_normal((4, mode_count))
                ) / 9.0
                negative_dense = (
                    rng.standard_normal((4, mode_count))
                    + 1j * rng.standard_normal((4, mode_count))
                ) / 11.0
                projection = _matrix_from_dense(
                    modal_template, active_template, projection_dense
                )
                positive = _matrix_from_dense(
                    active_template, modal_template, positive_dense
                )
                negative = _matrix_from_dense(
                    active_template, modal_template, negative_dense
                )
                owned_matrices.extend((projection, positive, negative))
                side_blocks.append(
                    SimpleNamespace(
                        projection=projection,
                        positive_traction=positive,
                        negative_traction=negative,
                        positive_interior_correction=np.zeros(
                            (mode_count, mode_count), dtype=np.complex128
                        ),
                        negative_interior_correction=np.zeros(
                            (mode_count, mode_count), dtype=np.complex128
                        ),
                        modal_rhs_correction=np.zeros(
                            mode_count, dtype=np.complex128
                        ),
                    )
                )
        finally:
            active_template.destroy()
            modal_template.destroy()

        factors = np.asarray(
            [0.35 + 0.004j * (index + 1) for index in range(mode_count)],
            dtype=np.complex128,
        )
        coupling = SimpleNamespace(
            mode_count_per_direction=mode_count,
            internal_unknown_count=2 * mode_count,
            negative_trace_to_positive=np.eye(mode_count, dtype=np.complex128),
            propagation=SimpleNamespace(
                forward=SimpleNamespace(factors=factors.copy()),
                backward=SimpleNamespace(
                    factors=np.asarray(0.68 - 0.003j * np.arange(1, mode_count + 1))
                ),
            ),
            bottom=side_blocks[0],
            top=side_blocks[1],
        )
        fixture["v12_coupling"] = coupling
        constraint = np.asarray(
            internal_modal_constraint_matrix(coupling), dtype=np.complex128
        )
        diagonal = np.geomspace(0.03, 30.0, 2 * mode_count) * np.exp(
            1j * np.linspace(-0.2, 0.25, 2 * mode_count)
        )
        schur = np.diag(diagonal) @ constraint
        assert np.isfinite(schur).all()
        assert np.linalg.norm(schur - schur.conj().T) > 1.0
        return fixture, bundles, coupling, schur
    except BaseException:
        _destroy_fixed_h6_modal_krylov_components(fixture, bundles, None)
        raise


def _set_v12_test_schur(
    system: block_ldu._FixedH6ModalKrylovSystem,
    dense_schur: np.ndarray,
) -> None:
    matrix = np.asarray(dense_schur, dtype=np.complex128)
    system._modal_action.apply = lambda values: np.asarray(
        matrix @ np.asarray(values, dtype=np.complex128), dtype=np.complex128
    )


def _v12_fixed_physical_backup_fixture(snapshot_callback):
    """Join the real tiny side inverses to the 40-mode modal test coupling."""

    side_fixture = _fixed_h6_side_block_fixture()
    modal_fixture, modal_bundles, coupling, schur = _v12_fixed_h6_modal_components()
    primary_actions = []
    solver = bundle = None
    try:
        for side in ("bottom", "top"):
            inverse = side_fixture[f"{side}_inverse"]
            inverse.configure_diagnostic_p4_corrections(
                0, None, refinement_target_tolerance=5.0e-13
            )
            transfer = inverse._owner_transfer

            def project(source: PETSc.Vec, *, timing=None) -> PETSc.Vec:
                del timing
                result = source.duplicate()
                source.copy(result)
                first, last = map(int, result.getOwnershipRange())
                local_rows = np.arange(first, last, dtype=np.int64)
                retained = np.isin(local_rows, np.asarray([0, 1, 4, 5]))
                result.getArray()[~retained] = PETSc.ScalarType(0.0)
                result.assemble()
                return result

            transfer.apply_adjoint = project
            transfer.apply_primal = project
            primary_actions.append(inverse.create_fixed_h6_active_trace_action())

        # Keep the backup candidate close to C^-1's exact operator so the
        # tiny same-factor solve tests the switch and its gates, not a hard
        # synthetic conditioning problem in the physical branch.
        for side in (coupling.bottom, coupling.top):
            for name in ("projection", "positive_traction", "negative_traction"):
                getattr(side, name).scale(1.0e-4)
        solver = block_ldu._FixedH6ModalKrylovSystem(
            coupling,
            primary_actions[0],
            primary_actions[1],
            modal_owner=MPI.COMM_WORLD.size - 1,
            modal_solver_policy=block_ldu.TASK041_V12_MODAL_BACKUP_POLICY_ID,
            snapshot_callback=snapshot_callback,
        )
        bundle = block_ldu._FixedH6ModalGmresResearchBundle(
            solver,
            primary_actions[0],
            primary_actions[1],
            coupling=coupling,
            backup_side_inverses=(
                side_fixture["bottom_inverse"],
                side_fixture["top_inverse"],
            ),
        )
        primary_actions = []
        return {
            "side_fixture": side_fixture,
            "modal_fixture": modal_fixture,
            "modal_bundles": modal_bundles,
            "coupling": coupling,
            "primary_schur": schur,
            "solver": solver,
            "bundle": bundle,
        }
    except BaseException:
        if bundle is not None:
            bundle.destroy()
        elif solver is not None:
            solver.destroy()
        for action in reversed(primary_actions):
            action.destroy()
        _destroy_fixed_h6_modal_krylov_components(
            modal_fixture, modal_bundles, None
        )
        _destroy_side_block_fixture(side_fixture)
        raise


def _destroy_v12_fixed_physical_backup_fixture(fixture) -> None:
    if fixture["bundle"] is not None and not fixture["bundle"]._destroyed:
        fixture["bundle"].destroy()
    _destroy_fixed_h6_modal_krylov_components(
        fixture["modal_fixture"], fixture["modal_bundles"], None
    )
    _destroy_side_block_fixture(fixture["side_fixture"])


def test_fixed_h6_modal_gmres_matches_dense_solve_and_borrows_adapters() -> None:
    fixture, bundles, dense_operator = _fixed_h6_modal_krylov_components()
    system = None
    owner_cumulative_attempts = 0
    owner_cumulative_successes = 0
    local_cumulative_attempts = 0
    local_cumulative_successes = 0
    try:
        system = block_ldu._FixedH6ModalKrylovSystem(
            fixture["coupling"],
            bundles[0]["adapter"],
            bundles[1]["adapter"],
            modal_owner=MPI.COMM_WORLD.size - 1,
        )
        rhs = np.asarray(
            [0.31 + 0.27j, -0.18 + 0.42j, 0.53 - 0.36j, -0.24 - 0.11j],
            dtype=np.complex128,
        )
        rhs_before = rhs.copy()
        for _ in range(2):
            side_applies_before = [bundle["adapter"].audit["apply_count"] for bundle in bundles]
            h6_mults_before = [int(bundle["h6"].matrix_mult_count) for bundle in bundles]
            solution = system.solve(rhs)
            expected_solution = np.linalg.solve(dense_operator, rhs_before)
            independent_residual = dense_operator @ solution - rhs_before
            independent_residual_norm = float(np.linalg.norm(independent_residual))
            independent_relative = independent_residual_norm / float(np.linalg.norm(rhs_before))
            condition_number = float(np.linalg.cond(dense_operator))
            solution_error = _relative_or_absolute(solution, expected_solution)
            # For A x* = b, ||x-x*||/||x*|| is bounded by
            # cond(A) * ||A x-b||/||b||, up to floating-point roundoff.
            roundoff_allowance = (
                32.0 * np.finfo(np.float64).eps * condition_number
            )
            residual_condition_bound = (
                condition_number * independent_relative + roundoff_allowance
            )
            solve = system.diagnostics["last_solve"]

            assert np.isfinite(condition_number)
            assert independent_relative <= system.rtol
            assert solution_error <= residual_condition_bound, (
                f"dense solution relative error {solution_error:.6e} exceeds "
                f"conditioned residual bound {residual_condition_bound:.6e} "
                f"(cond={condition_number:.6e}, relative residual={independent_relative:.6e})"
            )
            assert np.array_equal(rhs, rhs_before)
            assert np.allclose(
                _gather_vector(system._rhs), rhs_before, rtol=0.0, atol=0.0
            )
            assert solve["status"] == "converged"
            assert solve["zero_initial_guess"] is True
            assert solve["initial_solution_norm"] == 0.0
            assert solve["final_residual_evaluated"] is True
            assert np.isclose(
                solve["final_residual_norm"],
                independent_residual_norm,
                rtol=1.0e-10,
                atol=1.0e-13,
            )
            assert solve["constraint_lu_factorizations"] == 1
            assert solve["local_constraint_lu_factorizations"] == (
                1 if MPI.COMM_WORLD.rank == MPI.COMM_WORLD.size - 1 else 0
            )
            owner_attempts = solve["owner_constraint_lu_solve_attempts"]
            owner_successes = solve["owner_constraint_lu_solve_successes"]
            assert solve["local_constraint_lu_solve_attempts"] == (
                owner_attempts
                if MPI.COMM_WORLD.rank == MPI.COMM_WORLD.size - 1
                else 0
            )
            assert solve["local_constraint_lu_solve_successes"] == (
                owner_successes
                if MPI.COMM_WORLD.rank == MPI.COMM_WORLD.size - 1
                else 0
            )
            assert owner_attempts == owner_successes
            owner_cumulative_attempts += owner_attempts
            owner_cumulative_successes += owner_successes
            local_cumulative_attempts += solve[
                "local_constraint_lu_solve_attempts"
            ]
            local_cumulative_successes += solve[
                "local_constraint_lu_solve_successes"
            ]
            assert solve["constraint_lu_solve_count_scope"] == (
                "owner_authoritative_replicated_report"
            )
            assert solve["owner_constraint_lu_solve_counts_authoritative"] is True
            assert solve["cumulative_owner_constraint_lu_solve_attempts"] == (
                owner_cumulative_attempts
            )
            assert solve["cumulative_owner_constraint_lu_solve_successes"] == (
                owner_cumulative_successes
            )
            assert solve["cumulative_owner_constraint_lu_solve_status"] == "complete"
            cumulative = system.diagnostics
            assert cumulative["cumulative_constraint_lu_solve_attempts"] == (
                local_cumulative_attempts
            )
            assert cumulative["cumulative_constraint_lu_solve_successes"] == (
                local_cumulative_successes
            )
            assert cumulative["cumulative_constraint_lu_solve_count_scope"] == (
                "rank_local_cumulative; do_not_sum_across_ranks"
            )
            rank_counts = MPI.COMM_WORLD.allgather(
                (
                    cumulative["cumulative_constraint_lu_solve_attempts"],
                    cumulative["cumulative_owner_constraint_lu_solve_attempts"],
                    cumulative["cumulative_owner_constraint_lu_solve_successes"],
                )
            )
            assert all(
                (record[1], record[2])
                == (owner_cumulative_attempts, owner_cumulative_successes)
                for record in rank_counts
            )
            if MPI.COMM_WORLD.rank != MPI.COMM_WORLD.size - 1:
                assert cumulative["cumulative_constraint_lu_solve_attempts"] == 0
            assert [
                bundle["adapter"].audit["apply_count"] - before
                for bundle, before in zip(bundles, side_applies_before, strict=True)
            ] == [solve["total_matmult_calls"]] * 2
            assert [
                int(bundle["h6"].matrix_mult_count) - before
                for bundle, before in zip(bundles, h6_mults_before, strict=True)
            ] == [2 * solve["total_matmult_calls"]] * 2

        zero = np.zeros(4, dtype=np.complex128)
        zero_before = zero.copy()
        zero_applies_before = [bundle["adapter"].audit["apply_count"] for bundle in bundles]
        zero_solution = system.solve(zero)
        zero_solve = system.diagnostics["last_solve"]
        assert np.array_equal(zero_solution, zero)
        assert np.array_equal(zero, zero_before)
        assert np.allclose(_gather_vector(system._rhs), zero, rtol=0.0, atol=0.0)
        assert zero_solve["status"] == "zero_rhs_exact"
        assert zero_solve["final_residual_norm"] == 0.0
        assert zero_solve["solver_matmult_calls"] == 0
        assert zero_solve["total_matmult_calls"] == 1
        assert zero_solve["owner_constraint_lu_solve_attempts"] == 0
        assert zero_solve["owner_constraint_lu_solve_successes"] == 0
        assert zero_solve["owner_constraint_lu_solve_counts_authoritative"] is True
        assert zero_solve["owner_constraint_lu_solve_counts_scope"] == (
            "zero_rhs_no_ksp_no_owner_lu_calls"
        )
        assert zero_solve["cumulative_owner_constraint_lu_solve_attempts"] == (
            owner_cumulative_attempts
        )
        assert zero_solve["cumulative_owner_constraint_lu_solve_successes"] == (
            owner_cumulative_successes
        )
        assert zero_solve["cumulative_owner_constraint_lu_solve_status"] == "complete"
        after_zero = system.diagnostics
        assert after_zero["cumulative_constraint_lu_solve_attempts"] == (
            local_cumulative_attempts
        )
        assert after_zero["cumulative_constraint_lu_solve_successes"] == (
            local_cumulative_successes
        )
        replicated_owner_totals = MPI.COMM_WORLD.allgather(
            (
                after_zero["cumulative_owner_constraint_lu_solve_attempts"],
                after_zero["cumulative_owner_constraint_lu_solve_successes"],
            )
        )
        assert len(set(replicated_owner_totals)) == 1
        assert [
            bundle["adapter"].audit["apply_count"] - before
            for bundle, before in zip(bundles, zero_applies_before, strict=True)
        ] == [1, 1]

        system.destroy()
        destroyed_diagnostics = system.diagnostics
        assert destroyed_diagnostics["destroyed"] is True
        assert destroyed_diagnostics[
            "cumulative_owner_constraint_lu_solve_attempts"
        ] == owner_cumulative_attempts
        assert destroyed_diagnostics[
            "cumulative_owner_constraint_lu_solve_successes"
        ] == owner_cumulative_successes
        assert destroyed_diagnostics[
            "cumulative_constraint_lu_solve_attempts"
        ] == local_cumulative_attempts
        system = None
        for bundle in bundles:
            adapter = bundle["adapter"]
            assert adapter.audit["destroyed"] is False
            source = bundle["active_operator"].createVecRight()
            target = bundle["active_operator"].createVecLeft()
            try:
                values = np.asarray([0.2 + 0.1j, -0.3 + 0.4j, 0.5 - 0.2j, 0.1 + 0.6j])
                _set_vector(source, values)
                adapter.apply(source, target)
                assert np.all(np.isfinite(_gather_vector(target)))
                assert adapter.audit["destroyed"] is False
            finally:
                target.destroy()
                source.destroy()
    finally:
        _destroy_fixed_h6_modal_krylov_components(fixture, bundles, system)


def test_fixed_h6_modal_gmres_synchronizes_preflight_pc_and_budget_failures() -> None:
    fixture, bundles, _dense_operator = _fixed_h6_modal_krylov_components()
    system = None
    try:
        owner = MPI.COMM_WORLD.size - 1
        wrong_owner = owner
        if MPI.COMM_WORLD.rank == 0:
            wrong_owner = owner - 1 if owner > 0 else -1
        with pytest.raises(RuntimeError, match="input preflight") as owner_error:
            block_ldu._FixedH6ModalKrylovSystem(
                fixture["coupling"],
                bundles[0]["adapter"],
                bundles[1]["adapter"],
                modal_owner=wrong_owner,
            )
        owner_errors = MPI.COMM_WORLD.allgather(str(owner_error.value))
        assert len(set(owner_errors)) == 1
        assert "rank 0" in owner_errors[0]
        assert all(bundle["adapter"].audit["destroyed"] is False for bundle in bundles)

        system = block_ldu._FixedH6ModalKrylovSystem(
            fixture["coupling"],
            bundles[0]["adapter"],
            bundles[1]["adapter"],
            modal_owner=owner,
        )
        rhs = np.asarray(
            [0.31 + 0.27j, -0.18 + 0.42j, 0.53 - 0.36j, -0.24 - 0.11j],
            dtype=np.complex128,
        )
        system.solve(rhs)
        successful = system.diagnostics
        successful_owner_attempts = successful[
            "cumulative_owner_constraint_lu_solve_attempts"
        ]
        successful_owner_successes = successful[
            "cumulative_owner_constraint_lu_solve_successes"
        ]
        assert successful_owner_attempts > 0
        assert successful_owner_successes == successful_owner_attempts

        real_ksp = system._ksp

        class RaiseAfterKspReturn:
            def __init__(self, ksp):
                self._ksp = ksp

            def __getattr__(self, name):
                return getattr(self._ksp, name)

            def solve(self, *args):
                self._ksp.solve(*args)
                raise RuntimeError("injected after KSP return before owner-count broadcast")

        system._ksp = RaiseAfterKspReturn(real_ksp)
        try:
            with pytest.raises(
                RuntimeError,
                match="injected after KSP return before owner-count broadcast",
            ):
                system.solve(rhs)
        finally:
            system._ksp = real_ksp
        missing_broadcast = system.diagnostics
        incomplete_solve = missing_broadcast["last_solve"]
        assert incomplete_solve["owner_constraint_lu_solve_counts_authoritative"] is False
        assert incomplete_solve["constraint_lu_solve_count_scope"] == (
            "owner_value_unavailable_without_post_callback_collective"
        )
        assert missing_broadcast[
            "cumulative_owner_constraint_lu_solve_attempts"
        ] is None
        assert missing_broadcast[
            "cumulative_owner_constraint_lu_solve_successes"
        ] is None
        assert missing_broadcast[
            "cumulative_owner_constraint_lu_solve_status"
        ] == "unknown_missing_per_solve_owner_broadcast"
        if MPI.COMM_WORLD.rank != owner:
            assert incomplete_solve["owner_constraint_lu_solve_attempts"] is None
            assert incomplete_solve["owner_constraint_lu_solve_successes"] is None
        missing_states = MPI.COMM_WORLD.allgather(
            (
                missing_broadcast[
                    "cumulative_owner_constraint_lu_solve_attempts"
                ],
                missing_broadcast[
                    "cumulative_owner_constraint_lu_solve_successes"
                ],
                missing_broadcast[
                    "cumulative_owner_constraint_lu_solve_status"
                ],
            )
        )
        assert len(set(missing_states)) == 1

        system.solve(rhs)
        after_later_success = system.diagnostics
        assert after_later_success["last_solve"][
            "owner_constraint_lu_solve_counts_authoritative"
        ] is True
        assert after_later_success[
            "cumulative_owner_constraint_lu_solve_attempts"
        ] is None
        assert after_later_success[
            "cumulative_owner_constraint_lu_solve_successes"
        ] is None
        assert after_later_success[
            "cumulative_owner_constraint_lu_solve_status"
        ] == "unknown_missing_per_solve_owner_broadcast"

        system._reset_attempt()
        wrong_local_size = system.modal_count - 1 if MPI.COMM_WORLD.rank == owner else 0
        wrong_global_size = system.modal_count - 1
        bad_source = PETSc.Vec().createMPI(
            (wrong_local_size, wrong_global_size), comm=system._matrix.getComm()
        )
        bad_target = PETSc.Vec().createMPI(
            (wrong_local_size, wrong_global_size), comm=system._matrix.getComm()
        )
        try:
            h6_counts = [int(bundle["h6"].apply_count) for bundle in bundles]
            messages = []
            try:
                # Exercise the synchronized MatMult preflight directly.  The
                # local petsc4py files do not establish cross-rank C-callback
                # exception semantics, so this does not claim that bridge.
                system._mat_mult(bad_source, bad_target)
            except RuntimeError as exc:
                messages.append(str(exc))
            else:
                pytest.fail("malformed S_H Mat vectors were not rejected")
            preflight_messages = MPI.COMM_WORLD.allgather(messages[0])
            assert len(set(preflight_messages)) == 1
            assert f"rank {owner}" in preflight_messages[0]
            assert [int(bundle["h6"].apply_count) for bundle in bundles] == h6_counts
        finally:
            bad_target.destroy()
            bad_source.destroy()

        pc_source = system._matrix.createVecRight()
        pc_target = system._matrix.createVecRight()
        try:
            pc_source.set(1.0)
            saved_lu = system._constraint_lu
            if MPI.COMM_WORLD.rank == owner:
                system._constraint_lu = None
            try:
                system._ksp.getPC().apply(pc_source, pc_target)
            finally:
                system._constraint_lu = saved_lu
            pc_errors = MPI.COMM_WORLD.allgather(system._pc_failure_error)
            assert len(set(pc_errors)) == 1
            assert pc_errors[0] is not None
            assert np.isinf(float(pc_target.norm()))
            owner_lu_attempts = int(
                MPI.COMM_WORLD.bcast(
                    system._constraint_lu_solve_attempts
                    if MPI.COMM_WORLD.rank == owner
                    else None,
                    root=owner,
                )
            )
            owner_lu_successes = int(
                MPI.COMM_WORLD.bcast(
                    system._constraint_lu_solve_successes
                    if MPI.COMM_WORLD.rank == owner
                    else None,
                    root=owner,
                )
            )
            assert owner_lu_attempts == 1
            assert owner_lu_successes == 0
            assert system._constraint_lu_solve_attempts == (
                1 if MPI.COMM_WORLD.rank == owner else 0
            )
            assert system._constraint_lu_solve_successes == 0
        finally:
            pc_target.destroy()
            pc_source.destroy()

        saved_lu = system._constraint_lu
        if MPI.COMM_WORLD.rank == owner:
            system._constraint_lu = None
        try:
            with pytest.raises(RuntimeError):
                system.solve(rhs)
        finally:
            system._constraint_lu = saved_lu
        snapshot = system.diagnostics
        solve = snapshot["last_solve"]
        budget_exhausted = snapshot["budget_exhausted"]
        assert solve["status"] == (
            "budget_exhausted" if budget_exhausted else "pc_apply_failed"
        )
        assert solve["ksp_status"] in {
            "raised_after_synchronized_pc_failure",
            "returned_after_marked_pc_failure",
            "raised_after_budget_exhaustion",
        }
        assert solve["pc_failure"] is not None
        assert solve["final_residual_evaluated"] is False
        assert solve["final_residual_status"] == "not_evaluated"
        assert solve.get("final_residual_norm") is None
        assert solve.get("final_relative_residual") is None
        expected_not_evaluated_reason = (
            "budget_exhausted_before_trusted_KSP_iterate"
            if budget_exhausted
            else "PC_failure_no_trusted_KSP_iterate"
        )
        assert solve["final_residual_not_evaluated_reason"] == (
            expected_not_evaluated_reason
        )
        assert solve["local_constraint_lu_solve_attempts"] == (
            1 if MPI.COMM_WORLD.rank == owner else 0
        )
        assert solve["local_constraint_lu_solve_successes"] == 0
        assert solve["cumulative_constraint_lu_solve_count_scope"] == (
            "rank_local_cumulative; do_not_sum_across_ranks"
        )
        assert snapshot["cumulative_owner_constraint_lu_solve_attempts"] is None
        assert snapshot["cumulative_owner_constraint_lu_solve_successes"] is None
        assert snapshot["cumulative_owner_constraint_lu_solve_status"] == (
            "unknown_missing_per_solve_owner_broadcast"
        )
        if solve["constraint_lu_solve_count_scope"] == (
            "owner_authoritative_replicated_report"
        ):
            assert solve["owner_constraint_lu_solve_attempts"] == 1
            assert solve["owner_constraint_lu_solve_successes"] == 0
        else:
            assert solve["constraint_lu_solve_count_scope"] == (
                "owner_value_unavailable_without_post_callback_collective"
            )
            assert solve["owner_constraint_lu_solve_attempts"] == (
                1 if MPI.COMM_WORLD.rank == owner else None
            )
            assert solve["owner_constraint_lu_solve_successes"] == (
                0 if MPI.COMM_WORLD.rank == owner else None
            )
        assert solve["ksp_reason"] is not None
        assert all(bundle["adapter"].audit["destroyed"] is False for bundle in bundles)
        system.destroy()
        system = None
        assert all(bundle["adapter"].audit["destroyed"] is False for bundle in bundles)

        system = block_ldu._FixedH6ModalKrylovSystem(
            fixture["coupling"],
            bundles[0]["adapter"],
            bundles[1]["adapter"],
            modal_owner=owner,
        )
        system._reset_attempt()
        source = system._matrix.createVecRight()
        target = system._matrix.createVecLeft()
        try:
            _set_vector(source, rhs)
            side_before = [bundle["adapter"].audit["apply_count"] for bundle in bundles]
            h6_before = [int(bundle["h6"].apply_count) for bundle in bundles]
            # This remains method-level budget coverage: the following direct
            # _mat_mult calls do not exercise PETSc's KSP Mat callback boundary.
            for _ in range(system.solver_matmult_limit):
                system._mat_mult(source, target)
            assert system._solver_matmult_calls == 9
            assert system._total_matmult_calls == 9
            assert [
                bundle["adapter"].audit["apply_count"] - before
                for bundle, before in zip(bundles, side_before, strict=True)
            ] == [9, 9]
            assert [
                int(bundle["h6"].apply_count) - before
                for bundle, before in zip(bundles, h6_before, strict=True)
            ] == [9, 9]
            messages = []
            try:
                # Nine real S_H actions consume the solver budget; this tenth
                # attempted solver action is rejected before side actions run.
                system._mat_mult(source, target)
            except RuntimeError as exc:
                messages.append(str(exc))
            else:
                pytest.fail("S_H MatMult budget did not reject the extra action")
            budget_messages = MPI.COMM_WORLD.allgather(messages[0])
            assert len(set(budget_messages)) == 1
            assert "budget exhausted" in budget_messages[0]
            relative, finite = system._final_residual(float(np.linalg.norm(rhs)))
            solve = system.diagnostics["last_solve"]
            assert relative is None
            assert finite is False
            assert solve["status"] == "budget_exhausted"
            assert solve["final_residual_evaluated"] is False
            assert solve["final_residual_status"] == "not_evaluated"
            assert solve["budget_used_solver_matmult_calls"] == 9
            assert solve["budget_used_total_matmult_calls"] == 9
            assert solve["blocked_matmult_attempts"] == 1
            assert system._total_matmult_calls == 9
        finally:
            target.destroy()
            source.destroy()
    finally:
        _destroy_fixed_h6_modal_krylov_components(fixture, bundles, system)


def test_fixed_h6_modal_gmres_budget_failure_crosses_real_ksp_callback() -> None:
    fixture, bundles, _dense_operator = _fixed_h6_modal_krylov_components()
    system = None
    try:
        owner = MPI.COMM_WORLD.size - 1
        system = block_ldu._FixedH6ModalKrylovSystem(
            fixture["coupling"],
            bundles[0]["adapter"],
            bundles[1]["adapter"],
            modal_owner=owner,
        )
        system.solver_matmult_limit = 1
        system.total_matmult_limit = 2
        rhs = np.asarray(
            [0.31 + 0.27j, -0.18 + 0.42j, 0.53 - 0.36j, -0.24 - 0.11j],
            dtype=np.complex128,
        )
        rhs_before = rhs.copy()
        side_before = [bundle["adapter"].audit["apply_count"] for bundle in bundles]
        h6_apply_before = [int(bundle["h6"].apply_count) for bundle in bundles]
        returned_solution = None
        solve_error = None
        try:
            returned_solution = system.solve(rhs)
        except Exception as exc:  # noqa: BLE001 - gather each rank's real KSP outcome
            solve_error = f"{type(exc).__name__}: {exc}"

        snapshot = system.diagnostics
        solve = dict(snapshot["last_solve"])
        local_record = {
            "rank": MPI.COMM_WORLD.rank,
            "solution_returned": returned_solution is not None,
            "solve_error": solve_error,
            "ksp_reason": solve.get("ksp_reason"),
            "ksp_reason_present": "ksp_reason" in solve,
            "ksp_status": solve.get("ksp_status"),
            "iterations": solve.get("iterations"),
            "status": solve.get("status"),
            "budget_exhausted": snapshot["budget_exhausted"],
            "solver_matmult_limit": system.solver_matmult_limit,
            "total_matmult_limit": system.total_matmult_limit,
            "solver_matmult_calls": solve.get("solver_matmult_calls"),
            "total_matmult_calls": solve.get("total_matmult_calls"),
            "blocked_matmult_attempts": snapshot["blocked_matmult_attempts"],
            "side_apply_deltas": [
                bundle["adapter"].audit["apply_count"] - before
                for bundle, before in zip(bundles, side_before, strict=True)
            ],
            "h6_apply_deltas": [
                int(bundle["h6"].apply_count) - before
                for bundle, before in zip(bundles, h6_apply_before, strict=True)
            ],
            "final_residual_evaluated": solve.get("final_residual_evaluated"),
            "final_residual_state": solve.get("final_residual_status"),
            "final_residual_norm": solve.get("final_residual_norm"),
            "final_relative_residual": solve.get("final_relative_residual"),
            "final_residual_not_evaluated_reason": solve.get(
                "final_residual_not_evaluated_reason"
            ),
            "raw_residual_pass": solve.get("raw_residual_pass"),
            "rhs_unchanged": bool(np.array_equal(rhs, rhs_before)),
        }
        del returned_solution
        destroy_error = None
        try:
            system.destroy()
        except Exception as exc:  # noqa: BLE001 - capture cleanup outcome before gather
            destroy_error = f"{type(exc).__name__}: {exc}"
        local_record["system_destroyed"] = system._destroyed
        local_record["destroy_error"] = destroy_error
        local_record["owned_objects_released"] = (
            system._ksp is None
            and system._matrix is None
            and system._modal_action is None
            and all(
                getattr(system, name) is None
                for name in ("_rhs", "_solution", "_image", "_residual")
            )
            and system._constraint_lu is None
            and system._constraint_pivots is None
        )
        adapter_alive = []
        h6_alive = []
        for bundle in bundles:
            try:
                adapter_alive.append(bundle["adapter"].audit["destroyed"] is False)
            except Exception:  # noqa: BLE001 - report liveness instead of rank-local exit
                adapter_alive.append(False)
            try:
                rows, columns = map(int, bundle["h6"].matrix.getSize())
                h6_alive.append(rows > 0 and rows == columns)
            except Exception:  # noqa: BLE001 - report liveness instead of rank-local exit
                h6_alive.append(False)
        local_record["borrowed_adapters_alive"] = adapter_alive
        local_record["borrowed_h6_alive"] = h6_alive

        # Each rank captures its real KSP callback outcome before this single
        # post-solve collective; returning from it proves all ranks progressed.
        records = MPI.COMM_WORLD.allgather(local_record)
        if MPI.COMM_WORLD.rank == 0:
            print(
                "FIXED_H6_KSP_BUDGET_CALLBACK="
                + json.dumps(records, sort_keys=True),
                flush=True,
            )

        collective_fields = (
            "solution_returned",
            "status",
            "budget_exhausted",
            "solver_matmult_limit",
            "total_matmult_limit",
            "solver_matmult_calls",
            "total_matmult_calls",
            "blocked_matmult_attempts",
            "final_residual_evaluated",
            "final_residual_state",
            "side_apply_deltas",
            "h6_apply_deltas",
        )
        for field in collective_fields:
            assert len({json.dumps(record[field], sort_keys=True) for record in records}) == 1
        assert len(records) == MPI.COMM_WORLD.size
        for record in records:
            assert record["solution_returned"] is False
            assert record["solve_error"] is not None
            assert record["destroy_error"] is None
            assert record["status"] == "budget_exhausted"
            assert record["budget_exhausted"] is True
            assert record["solver_matmult_limit"] == 1
            assert record["total_matmult_limit"] == 2
            assert record["solver_matmult_calls"] == 1
            assert record["total_matmult_calls"] == 1
            assert record["blocked_matmult_attempts"] == 1
            assert record["final_residual_evaluated"] is False
            assert record["final_residual_state"] == "not_evaluated"
            assert record["final_residual_norm"] is None
            assert record["final_relative_residual"] is None
            assert record["final_residual_not_evaluated_reason"] is not None
            assert record["raw_residual_pass"] is None
            assert record["side_apply_deltas"] == [1, 1]
            assert record["h6_apply_deltas"] == [1, 1]
            assert record["rhs_unchanged"] is True
            assert record["system_destroyed"] is True
            assert record["owned_objects_released"] is True
            assert record["borrowed_adapters_alive"] == [True, True]
            assert record["borrowed_h6_alive"] == [True, True]
            assert record["ksp_reason_present"] is True
    finally:
        _destroy_fixed_h6_modal_krylov_components(fixture, bundles, system)


def test_fixed_h6_active_trace_action_matches_full_modal_feedback_oracle() -> None:
    """Exercise the real FixedH6 recurrence on tiny noncontiguous trace rows."""

    fixture = _tiny_fixture()
    bundles: list[dict[str, object]] = []
    modal_action = None
    inputs = (
        np.asarray([0.3 + 0.7j, -0.2 + 0.1j, 0.6 - 0.4j, 0.5 + 0.2j]),
        np.asarray([-0.4 + 0.2j, 0.8 - 0.3j, 0.1 + 0.9j, -0.7 + 0.5j]),
    )
    modal_inputs = (
        np.asarray([0.2 + 0.5j, -0.6 + 0.1j, 0.7 - 0.3j, -0.1 + 0.8j]),
        np.asarray([-0.3 + 0.4j, 0.5 - 0.7j, 0.2 + 0.6j, 0.9 - 0.2j]),
    )
    try:
        assert H6_DEGREE == 3
        for side in ("bottom", "top"):
            bundle = _tiny_fixed_h6_bundle(side)
            bundles.append(bundle)
            bundle["adapter"] = FixedH6ActiveTraceAction(
                bundle["active_operator"], bundle["condensed"], bundle["h6"]
            )

        selected = bundles[0]["selected_full_rows"]
        assert np.array_equal(selected, np.asarray([0, 2, 4, 6]))
        for bundle in bundles:
            assert np.array_equal(bundle["selected_full_rows"], selected)
            bundle["matrix_before"] = _gather_matrix(bundle["h6_matrix"])
            bundle["dense_h6"] = _tiny_h6_dense_action(bundle["h6"])
        expected, bottom_feedback, top_feedback = _tiny_fixed_h6_modal_oracle(
            fixture,
            bundles[0]["dense_h6"],
            bundles[1]["dense_h6"],
            selected,
        )
        assert np.linalg.norm(bottom_feedback) > 0.0
        assert np.linalg.norm(top_feedback) > 0.0

        for bundle in bundles:
            adapter = bundle["adapter"]
            h6 = bundle["h6"]
            source = bundle["active_operator"].createVecRight()
            target = bundle["active_operator"].createVecLeft()
            alias_target = bundle["active_operator"].createVecLeft()
            active_h6 = bundle["dense_h6"][np.ix_(selected, selected)]
            try:
                _set_vector(source, inputs[0])
                source_before = _gather_vector(source)
                h6_applies = int(h6.apply_count)
                h6_mults = int(h6.matrix_mult_count)
                adapter_applies = adapter.audit["apply_count"]
                adapter_mults = adapter.audit["matrix_mult_count"]
                rank_target = source if MPI.COMM_WORLD.rank == 0 else alias_target
                with pytest.raises(
                    ValueError, match="source and target PETSc vectors alias"
                ) as alias_error:
                    adapter.apply(source, rank_target)
                alias_errors = MPI.COMM_WORLD.allgather(str(alias_error.value))
                assert len(set(alias_errors)) == 1
                assert "rank 0" in alias_errors[0]
                assert np.array_equal(_gather_vector(source), source_before)
                assert int(h6.apply_count) == h6_applies
                assert int(h6.matrix_mult_count) == h6_mults
                assert adapter.audit["apply_count"] == adapter_applies
                assert adapter.audit["matrix_mult_count"] == adapter_mults

                for values in (*inputs, inputs[0], np.zeros(4, dtype=np.complex128)):
                    _set_vector(source, values)
                    source_before = _gather_vector(source)
                    h6_applies = int(h6.apply_count)
                    h6_mults = int(h6.matrix_mult_count)
                    adapter.apply(source, target)
                    assert _relative_or_absolute(
                        _gather_vector(target), active_h6 @ values
                    ) <= 2.0e-12
                    assert np.array_equal(_gather_vector(source), source_before)
                    assert int(h6.apply_count) - h6_applies == 1
                    assert int(h6.matrix_mult_count) - h6_mults == 2
                assert adapter.audit["apply_count"] == 4
                assert adapter.audit["matrix_mult_count"] == 8
                assert "frozen for adapter lifetime" in adapter.audit[
                    "linearity_condition"
                ]
                assert adapter.audit["reentrant"] is False
                assert adapter.audit["h6_is_positive_surrogate"] is True
                assert adapter.audit["action"] == "J H6 J^H"
            finally:
                alias_target.destroy()
                target.destroy()
                source.destroy()

        modal_action = block_ldu.HybridActionModalSchurApply(
            fixture["coupling"], bundles[0]["adapter"], bundles[1]["adapter"]
        )
        vectors = (
            modal_inputs[0],
            modal_inputs[1],
            modal_inputs[0],
            np.zeros(4, dtype=np.complex128),
            (0.37 + 0.21j) * modal_inputs[0]
            + (-0.13 + 0.29j) * modal_inputs[1],
        )
        outputs = []
        for values in vectors:
            values_before = values.copy()
            h6_before = [int(bundle["h6"].apply_count) for bundle in bundles]
            mult_before = [int(bundle["h6"].matrix_mult_count) for bundle in bundles]
            output = modal_action.apply(values)
            outputs.append(output)
            assert _relative_or_absolute(output, expected @ values) <= 2.0e-12
            assert np.array_equal(values, values_before)
            assert [
                int(bundle["h6"].apply_count) - before
                for bundle, before in zip(bundles, h6_before, strict=True)
            ] == [1, 1]
            assert [
                int(bundle["h6"].matrix_mult_count) - before
                for bundle, before in zip(bundles, mult_before, strict=True)
            ] == [2, 2]
        assert _relative_or_absolute(outputs[2], outputs[0]) <= 2.0e-12
        assert np.linalg.norm(outputs[3]) <= 2.0e-12
        assert _relative_or_absolute(
            outputs[4], (0.37 + 0.21j) * outputs[0] + (-0.13 + 0.29j) * outputs[1]
        ) <= 2.0e-12
        for bundle in bundles:
            adapter = bundle["adapter"]
            assert adapter.audit["apply_count"] == 9
            assert adapter.audit["matrix_mult_count"] == 18
            assert np.array_equal(
                _gather_matrix(bundle["h6_matrix"]), bundle["matrix_before"]
            )

        modal_action.destroy()
        modal_action = None
        for bundle in bundles:
            adapter = bundle["adapter"]
            operator = bundle["active_operator"]
            h6 = bundle["h6"]
            window = bundle["window"]
            adapter.destroy()
            assert adapter.audit["destroyed"] is True
            assert h6.matrix is bundle["h6_matrix"]
            assert window.destroyed is False
            assert operator.isAssembled()
            h6.destroy()
            bundle["h6_destroyed"] = True
            assert window.destroyed is True
    finally:
        if modal_action is not None:
            modal_action.destroy()
        for bundle in bundles:
            adapter = bundle.get("adapter")
            if adapter is not None:
                adapter.destroy()
            h6 = bundle.get("h6")
            if h6 is not None:
                h6.destroy()
            operator = bundle.get("active_operator")
            if operator is not None:
                operator.destroy()
        _destroy_fixture(fixture)


def test_side_balh_block_factory_preserves_global_action_and_borrows_sides() -> None:
    fixture = _side_block_fixture()
    original_action = None
    original_context = None
    context = None
    q1 = q2 = q1_repeat = zero = None
    pc1 = pc2 = pc1_repeat = None
    original1 = original2 = None
    original_zero = pc_zero_expected = None
    full_rhs_before = full_rhs_after = None
    try:
        bottom = fixture["bottom"]
        top = fixture["top"]
        layout = fixture["layout"]
        coupling = fixture["coupling"]
        full_rhs_before = layout.pack(
            bottom.b,
            top.b,
            internal_modal_rhs_correction(coupling),
        )
        full_rhs_before_values = _gather_vector(full_rhs_before)
        layout_before = (
            layout.global_size,
            layout.local_size,
            layout.combined_offsets,
            layout.bottom_local_sizes,
            layout.top_local_sizes,
        )
        q1 = _pack(
            layout,
            bottom,
            top,
            np.asarray([1.0 + 0.2j, -0.3 + 0.5j, 0.7 - 0.4j, -0.2 + 0.1j]),
            np.asarray([-0.4 + 0.3j, 0.6 - 0.2j, 0.1 + 0.8j, -0.7 - 0.1j]),
            np.asarray([0.2 + 0.4j, -0.5 + 0.1j, 0.7 - 0.3j, -0.2 - 0.6j]),
        )
        q2 = _pack(
            layout,
            bottom,
            top,
            np.asarray([-0.2 + 0.6j, 0.8 - 0.1j, -0.5 + 0.2j, 0.3 + 0.7j]),
            np.asarray([0.5 - 0.4j, -0.1 + 0.9j, 0.6 + 0.2j, -0.8 + 0.3j]),
            np.asarray([-0.6 + 0.2j, 0.3 + 0.8j, -0.4 - 0.5j, 0.9 + 0.1j]),
        )
        q1_repeat = q1.copy()
        q1_values = _gather_vector(q1)
        q2_values = _gather_vector(q2)
        zero = layout.create_vector()
        zero.set(0.0)
        original_action, original_context = create_hybrid_assembled_block_action(
            bottom,
            top,
            coupling,
        )
        original1 = original_action.createVecLeft()
        original2 = original_action.createVecLeft()
        original_action.mult(q1, original1)
        original_action.mult(q2, original2)
        original1_values = _gather_vector(original1)
        original2_values = _gather_vector(original2)
        columns, roles, contract_sha = _sample_contract()
        context = block_ldu.create_side_balh_block_ldu_preconditioner(
            layout,
            bottom,
            top,
            coupling,
            fixture["bottom_inverse"],
            fixture["top_inverse"],
            sampled_columns=columns,
            sampled_column_roles=roles,
            sampled_column_contract_sha256=contract_sha,
        )
        inventory = context.inventory
        assert inventory["modal_block_name"] == (
            "finite_nonlinear_side_inverse_response_columns"
        )
        assert inventory["modal_schur_scope"] == "approximate_preconditioner_only"
        assert inventory["not_original_global_operator"] is True
        assert inventory["not_original_reduced_operator"] is True
        assert inventory["global_direct_factor_count"] == 0
        assert inventory["global_hybrid_direct_factor_count"] == 0
        assert inventory["p6_factor_count"] == 0
        assert inventory["p4_factor_count"] == 2
        assert inventory["nested_iterative_ksp_count"] == 2
        assert inventory["nested_iterative_ksp_created_count"] == 2
        assert inventory["nested_iterative_ksp_destroy_count"] == 0
        modal_diagnostics = inventory["modal_schur"]
        assert modal_diagnostics["build_apply_count"] == {"bottom": 12, "top": 12}
        assert modal_diagnostics["sampled_column_diagnostics"]["columns"] == columns
        assert modal_diagnostics["sampled_column_diagnostics"]["modal_batch_size"] == 32
        assert modal_diagnostics["sampled_column_diagnostics"]["early_sample_first"] is True
        assert modal_diagnostics["batch_diagnostics"]["early_sample"]["pass"] is True
        assert modal_diagnostics["batch_diagnostics"]["full_vs_first_sample"]["pass"] is True

        pc1 = layout.create_vector()
        pc2 = layout.create_vector()
        pc1_repeat = layout.create_vector()
        context.apply(None, q1, pc1)
        context.apply(None, q2, pc2)
        context.apply(None, q1_repeat, pc1_repeat)
        assert _relative_or_absolute(_gather_vector(pc1), _gather_vector(pc1_repeat)) <= 1.0e-12
        assert np.linalg.norm(_gather_vector(pc2)) > 0.0
        original_action.mult(q1, original1)
        original_action.mult(q2, original2)
        action1_diff = _relative_or_absolute(_gather_vector(original1), original1_values)
        action2_diff = _relative_or_absolute(_gather_vector(original2), original2_values)
        assert action1_diff <= 1.0e-12
        assert action2_diff <= 1.0e-12
        assert _relative_or_absolute(_gather_vector(q1), q1_values) <= 1.0e-12
        assert _relative_or_absolute(_gather_vector(q2), q2_values) <= 1.0e-12
        full_rhs_after = layout.pack(
            bottom.b,
            top.b,
            internal_modal_rhs_correction(coupling),
        )
        rhs_diff = _relative_or_absolute(
            _gather_vector(full_rhs_after), full_rhs_before_values
        )
        assert rhs_diff <= 1.0e-12
        assert layout_before == (
            layout.global_size,
            layout.local_size,
            layout.combined_offsets,
            layout.bottom_local_sizes,
            layout.top_local_sizes,
        )

        original_zero = original_action.createVecLeft()
        pc_zero_expected = layout.create_vector()
        original_action.mult(zero, original_zero)
        context.apply(None, zero, pc_zero_expected)
        assert _relative_or_absolute(
            _gather_vector(original_zero), np.zeros(layout.global_size, dtype=np.complex128)
        ) == 0.0
        assert _relative_or_absolute(
            _gather_vector(pc_zero_expected), np.zeros(layout.global_size, dtype=np.complex128)
        ) == 0.0
        assert context.inventory["pc_apply_count"] == 4
        if MPI.COMM_WORLD.rank == 0:
            print(
                "H1f action1/action2/RHS diffs="
                f"{action1_diff:.3e}/{action2_diff:.3e}/{rhs_diff:.3e}; "
                "limit=1.000e-12; Schur apply counts="
                f"{modal_diagnostics['build_apply_count']}",
                flush=True,
            )

        context.destroy()
        assert context.inventory["modal_schur"]["destroyed"] is True
        assert fixture["bottom_inverse"].diagnostics["destroyed"] is False
        assert fixture["top_inverse"].diagnostics["destroyed"] is False
        fixture["bottom_inverse"].destroy()
        fixture["top_inverse"].destroy()
        after_side_destroy = context.inventory
        assert after_side_destroy["p4_factor_count"] == 0
        assert after_side_destroy["p4_factor_created_count"] == 2
        assert after_side_destroy["p4_factor_destroy_count"] == 2
        assert after_side_destroy["nested_iterative_ksp_count"] == 0
        assert after_side_destroy["nested_iterative_ksp_created_count"] == 2
        assert after_side_destroy["nested_iterative_ksp_destroy_count"] == 2
    finally:
        for vector in (
            original_zero,
            pc_zero_expected,
            pc1,
            pc2,
            pc1_repeat,
            q1,
            q2,
            q1_repeat,
            zero,
            original1,
            original2,
            full_rhs_before,
            full_rhs_after,
        ):
            if vector is not None:
                vector.destroy()
        if context is not None and not context._destroyed:
            context.destroy()
        if original_action is not None:
            original_action.destroy()
        if original_context is not None:
            original_context.destroy()
        if not fixture["bottom_inverse"].diagnostics["destroyed"]:
            fixture["bottom_inverse"].destroy()
        if not fixture["top_inverse"].diagnostics["destroyed"]:
            fixture["top_inverse"].destroy()
        _destroy_side_block_fixture(fixture)


def test_side_balh_block_factory_releases_modal_on_constructor_error(monkeypatch) -> None:
    fixture = _side_block_fixture()
    built_modal = []
    real_builder = block_ldu.build_hybrid_action_modal_schur

    def capture_modal(*args, **kwargs):
        modal = real_builder(*args, **kwargs)
        built_modal.append(modal)
        return modal

    def fail_constructor(*_args, **_kwargs):
        raise RuntimeError("focused H1f constructor failure")

    monkeypatch.setattr(block_ldu, "build_hybrid_action_modal_schur", capture_modal)
    monkeypatch.setattr(block_ldu, "HybridBlockLduPreconditioner", fail_constructor)
    try:
        columns, roles, contract_sha = _sample_contract()
        with pytest.raises(RuntimeError, match="focused H1f constructor failure"):
            block_ldu.create_side_balh_block_ldu_preconditioner(
                fixture["layout"],
                fixture["bottom"],
                fixture["top"],
                fixture["coupling"],
                fixture["bottom_inverse"],
                fixture["top_inverse"],
                sampled_columns=columns,
                sampled_column_roles=roles,
                sampled_column_contract_sha256=contract_sha,
            )
        assert len(built_modal) == 1
        assert built_modal[0].diagnostics["destroyed"] is True
        assert fixture["bottom_inverse"].diagnostics["destroyed"] is False
        assert fixture["top_inverse"].diagnostics["destroyed"] is False
    finally:
        _destroy_side_block_fixture(fixture)


@pytest.mark.parametrize(
    ("complex_qr_research", "expected_mixing_method"),
    [
        (False, "petsc_snes_anderson_default"),
        (True, "complex_qr_type_ii_research"),
    ],
)
def test_side_balh_anderson_inner_reuses_owner_factor_and_keeps_true_operator(
    monkeypatch, complex_qr_research: bool, expected_mixing_method: str
) -> None:
    fixture = _side_block_fixture()
    original_action = original_context = context = result = rhs = None
    action_before = action_after = None
    try:
        bottom = fixture["bottom"]
        top = fixture["top"]
        layout = fixture["layout"]
        coupling = fixture["coupling"]
        rhs = layout.pack(
            bottom.b,
            top.b,
            internal_modal_rhs_correction(coupling),
        )
        rhs_before = _gather_vector(rhs)
        original_action, original_context = create_hybrid_assembled_block_action(
            bottom,
            top,
            coupling,
        )
        action_before = original_action.createVecLeft()
        action_after = original_action.createVecLeft()
        original_action.mult(rhs, action_before)
        action_before_values = _gather_vector(action_before)

        def reject_full_schur(*_args, **_kwargs):
            raise AssertionError("on-demand modal inner must not build Schur columns")

        monkeypatch.setattr(
            block_ldu, "build_hybrid_action_modal_schur", reject_full_schur
        )
        context = block_ldu.create_side_balh_block_ldu_preconditioner(
            layout,
            bottom,
            top,
            coupling,
            fixture["bottom_inverse"],
            fixture["top_inverse"],
            sampled_columns=None,
            sampled_column_roles=None,
            sampled_column_contract_sha256=None,
            use_anderson_modal_inner=True,
            complex_qr_research=complex_qr_research,
        )
        initial_inventory = context.inventory
        initial_inner = initial_inventory["modal_inner_solver"]
        assert initial_inner["mixing_method"] == expected_mixing_method
        assert context.modal_schur is None
        assert context.modal_constraint.shape == (
            layout.modal_count,
            layout.modal_count,
        )
        assert initial_inventory["modal_schur"] is None
        assert initial_inventory["modal_schur_materialized"] is False
        assert initial_inventory["modal_schur_storage_bytes"] == 0
        assert initial_inventory["modal_block_condition"] is None
        assert initial_inventory["early_sample_gate"]["status"] == "not_run"
        assert initial_inventory["early_sample_gate"]["pass"] is None
        assert "repeat_diagnostics" not in initial_inner
        assert initial_inventory["modal_count"] == layout.modal_count
        assert initial_inner["constraint_lu_factorizations"] == 1
        assert initial_inner["constraint_lu_owner_rank"] == layout.modal_owner
        assert (initial_inner["constraint_lu_local_bytes"] > 0) is (
            MPI.COMM_WORLD.rank == layout.modal_owner
        )

        with pytest.raises(ValueError, match="requires right-preconditioned FGMRES"):
            block_ldu.solve_hybrid_block_ldu_iterative(
                original_action,
                rhs,
                context,
                config=block_ldu.HybridBlockLduIterativeConfig(
                    restart=10,
                    max_it=10,
                    ksp_type="gmres",
                    fixed_preconditioner=True,
                ),
            )

        result = block_ldu.solve_hybrid_block_ldu_iterative(
            original_action,
            rhs,
            context,
            config=block_ldu.HybridBlockLduIterativeConfig(
                restart=20,
                max_it=80,
                threshold=5.0e-9,
                ksp_type="fgmres",
            ),
        )
        original_action.mult(rhs, action_after)
        action_diff = _relative_or_absolute(
            _gather_vector(action_after), action_before_values
        )
        rhs_diff = _relative_or_absolute(_gather_vector(rhs), rhs_before)
        assert action_diff <= 1.0e-12
        assert rhs_diff <= 1.0e-12
        assert result.postsolve_audit["pass"] is True
        for key in (
            "reported_relative_residual",
            "global_true_relative_residual",
            "bottom_true_relative_residual",
            "top_true_relative_residual",
            "modal_true_relative_residual",
        ):
            value = float(result.postsolve_audit[key])
            assert np.isfinite(value) and 0.0 <= value <= 5.0e-9
        inner = result.inventory["modal_inner_solver"]
        assert inner["last_solve"]["mixing_method"] == expected_mixing_method
        assert result.inventory["modal_schur"] is None
        assert inner["constraint_lu_factorizations"] == 1
        assert inner["last_solve"]["max_iterations"] == 14
        assert inner["last_solve"]["s_evaluation_count"] <= 16
        assert inner["solve_count"] == result.inventory["pc_apply_count"]
        assert inner["solve_count"] > 1
        assert inner["s_evaluation_count"] >= inner["solve_count"]
        assert all("modal_inner_solve_count" in row for row in result.history[1:])
        if MPI.COMM_WORLD.rank == 0:
            print(
                "on-demand modal inner: "
                f"PC={inner['solve_count']}, S={inner['s_evaluation_count']}, "
                f"C_LU=1@rank{layout.modal_owner}, "
                f"five_max={result.postsolve_audit['max_true_residual']:.3e}, "
                f"operator_diff={action_diff:.3e}, RHS_diff={rhs_diff:.3e}",
                flush=True,
            )
        result.destroy()
        assert context.inventory["modal_inner_solver"]["destroyed"] is True
        assert context.inventory["modal_inner_solver"]["constraint_lu_local_bytes"] == 0
        assert fixture["bottom_inverse"].diagnostics["destroyed"] is False
        assert fixture["top_inverse"].diagnostics["destroyed"] is False
    finally:
        if result is not None and not result._destroyed:
            result.destroy()
        if context is not None and not context._destroyed:
            context.destroy()
        for vector in (rhs, action_before, action_after):
            if vector is not None:
                vector.destroy()
        if original_action is not None:
            original_action.destroy()
        if original_context is not None:
            original_context.destroy()
        _destroy_side_block_fixture(fixture)


def test_side_balh_fixed_h6_modal_gmres_factory_keeps_true_outer_gates() -> None:
    fixture = _fixed_h6_side_block_fixture()
    original_action = original_context = context = result = rhs = None
    action_before = action_after = None
    original_side_applies_before = {
        side: fixture[f"{side}_inverse"].diagnostics["apply_count"]
        for side in ("bottom", "top")
    }
    try:
        layout = fixture["layout"]
        coupling = fixture["coupling"]
        rhs = layout.pack(
            fixture["bottom"].b,
            fixture["top"].b,
            internal_modal_rhs_correction(coupling),
        )
        rhs_before = _gather_vector(rhs)
        original_action, original_context = create_hybrid_assembled_block_action(
            fixture["bottom"], fixture["top"], coupling
        )
        action_before = original_action.createVecLeft()
        action_after = original_action.createVecLeft()
        original_action.mult(rhs, action_before)
        action_values = _gather_vector(action_before)
        context = block_ldu.create_side_balh_block_ldu_preconditioner(
            layout,
            fixture["bottom"],
            fixture["top"],
            coupling,
            fixture["bottom_inverse"],
            fixture["top_inverse"],
            sampled_columns=None,
            sampled_column_roles=None,
            sampled_column_contract_sha256=None,
            fixed_h6_modal_gmres_research=True,
        )
        initial = context.inventory
        assert context.requires_right_fgmres is True
        assert context.modal_schur is None
        assert context.modal_constraint.shape == (layout.modal_count,) * 2
        assert initial["preconditioner_identity"] == (
            "fixed_h6_modal_gmres_research"
        )
        assert initial["modal_block_name"] == (
            "fixed_h6_surrogate_on_demand_modal_gmres"
        )
        assert "modal_feedback_method" not in initial
        assert "fixed_physical_balh_modal_solver" not in initial
        assert initial["fixed_h6_modal_solver"]["method"] == (
            "fixed_h6_modal_gmres_research"
        )
        assert initial["modal_schur_materialized"] is False
        assert initial["modal_schur_column_count"] == 0
        assert initial["modal_schur"] is None
        assert initial["modal_schur_condition"] == "not_measured"
        gate = initial["early_sample_gate"]
        assert gate["status"] == "passed"
        assert gate["pass"] is True
        assert gate["mode"] == "fixed_h6_modal_feedback_complex_repeat_linearity"
        assert gate["requested_s_h_actions"] == 8
        assert gate["relative_limit"] == 1.0e-10
        assert gate["absolute_limit"] == 1.0e-10
        assert gate["input_definition"]["alpha"] == [0.5, 0.75]
        assert gate["input_definition"]["epsilon"] == 1.0e-12
        assert gate["input_definition"]["x_norm"] == pytest.approx(1.0)
        assert gate["input_definition"]["y_norm"] == pytest.approx(1.0)
        assert gate["input_definition"]["x_sha256"]
        assert gate["input_definition"]["y_sha256"]
        assert gate["metric_formulas"] == {
            "zero_absolute": "||F(0)||",
            "repeat_x": "||F(x)_1-F(x)_2||/max(||F(x)_1||,||F(x)_2||)",
            "complex_homogeneity": (
                "||F(alpha*x)-alpha*F(x)||/"
                "max(||F(alpha*x)||,|alpha|*||F(x)||)"
            ),
            "repeat_y": "||F(y)_1-F(y)_2||/max(||F(y)_1||,||F(y)_2||)",
            "additivity": (
                "||F(x+y)-F(x)-F(y)||/"
                "max(||F(x+y)||,||F(x)||+||F(y)||)"
            ),
            "near_zero_absolute": "||F(epsilon*x)-epsilon*F(x)||",
        }
        assert all(
            all(support)
            for support in gate["input_definition"][
                "positive_negative_block_support"
            ].values()
        )
        assert gate["constraint_lu_factorizations_owner"] == 1
        assert gate["constraint_lu_solve_attempts_at_owner_during_gate"] == 0
        assert gate["gmres_solver_and_final_check_budget_unchanged"] == {
            "solver_matmult_limit": 9,
            "total_matmult_limit_including_final": 10,
        }
        assert len(gate["rank_results"]) == MPI.COMM_WORLD.size
        json.dumps(gate, allow_nan=False)
        local_metrics = gate["rank_results"][MPI.COMM_WORLD.rank]["metrics"]
        assert local_metrics["zero_absolute"]["branch"] == "absolute_zero_input"
        assert local_metrics["zero_absolute"]["absolute_error"] <= 1.0e-10
        for metric_name in (
            "repeat_x",
            "complex_homogeneity",
            "repeat_y",
            "additivity",
        ):
            metric = local_metrics[metric_name]
            assert metric["status"] == "evaluated"
            assert metric["pass"] is True
            if metric["denominator"] is not None and metric["denominator"] > 0.0:
                assert metric["branch"] == "relative"
                assert metric["relative_error"] <= 1.0e-10
            else:
                assert metric["branch"] == "absolute_zero_denominator"
                assert metric["absolute_error"] <= 1.0e-10
        near_zero = local_metrics["near_zero_absolute"]
        assert near_zero["branch"] == "absolute_near_zero_input"
        assert near_zero["denominator"] is None
        assert near_zero["input_norm"] == pytest.approx(1.0e-12)
        assert near_zero["output_norm"] is not None
        assert near_zero["reference_norm"] is not None
        assert near_zero["absolute_error"] <= 1.0e-10
        for row in gate["rank_results"]:
            assert row["operator_action_attempts"] == 8
            assert row["operator_action_completions"] == 8
            assert row["modal_constraint_matvec_calls"] == 8
            assert row["constraint_lu_solve_attempts"] == 0
            assert all(row["input_unchanged_by_action"].values())
            for side in ("bottom", "top"):
                side_counts = row["fixed_h6_side_counts"][side]
                assert side_counts["fixed_h6_apply_calls"] == 8
                assert side_counts["fixed_h6_h6_degree"] == H6_DEGREE
                assert side_counts["expected_matrix_mult_calls_from_degree"] == 16
                assert side_counts["fixed_h6_matrix_mult_calls"] == 16
                assert side_counts["matrix_mult_matches_h6_degree"] is True
        original_side_applies_after = {
            side: fixture[f"{side}_inverse"].diagnostics["apply_count"]
            for side in ("bottom", "top")
        }
        assert original_side_applies_after == original_side_applies_before

        result = block_ldu.solve_hybrid_block_ldu_iterative(
            original_action,
            rhs,
            context,
            config=block_ldu.HybridBlockLduIterativeConfig(
                restart=20,
                max_it=80,
                threshold=5.0e-9,
                ksp_type="fgmres",
            ),
        )
        original_action.mult(rhs, action_after)
        assert _relative_or_absolute(_gather_vector(action_after), action_values) <= 1e-12
        assert _relative_or_absolute(_gather_vector(rhs), rhs_before) <= 1e-12
        assert result.postsolve_audit["pass"] is True
        assert result.postsolve_audit["ksp_type"] == "fgmres"
        for key in (
            "reported_relative_residual",
            "global_true_relative_residual",
            "bottom_true_relative_residual",
            "top_true_relative_residual",
            "modal_true_relative_residual",
        ):
            value = float(result.postsolve_audit[key])
            assert np.isfinite(value) and 0.0 <= value <= 5e-9

        inventory = result.inventory
        inner = inventory["modal_inner_solver"]
        last = inner["last_solve"]
        assert last["status"] == "converged"
        assert last["raw_residual_pass"] is True
        assert last["final_relative_residual"] <= 1.0e-3
        assert last["solver_matmult_calls"] <= 9
        assert last["total_matmult_calls"] <= 10
        assert inner["constraint_lu_factorizations"] == 1
        assert inner["owner_constraint_lu_factorizations"] == 1
        assert inner["solve_count"] == inventory["pc_apply_count"]
        side_counts = inventory["fixed_h6_pc_side_apply_counts"]
        whole_run_work = inventory["fixed_h6_whole_run_work"]
        assert whole_run_work["setup_gate_s_h_actions"] == 8
        assert whole_run_work["gmres_solver_and_final_check_s_h_actions"] == (
            inner["cumulative_total_matmult_calls"]
        )
        assert whole_run_work["total_s_h_actions_including_setup_gate"] == (
            8 + inner["cumulative_total_matmult_calls"]
        )
        assert whole_run_work["total_c_matvec_calls_including_setup_gate"] == (
            8 + inner["cumulative_total_matmult_calls"]
        )
        for side in ("bottom", "top"):
            assert side_counts[side]["first"] == inventory["pc_apply_count"]
            assert side_counts[side]["delta"] == inventory["pc_apply_count"]
            gate_side = gate["rank_results"][MPI.COMM_WORLD.rank][
                "fixed_h6_side_counts"
            ][side]
            assert whole_run_work["setup_gate_h6_calls_by_side"][side] == gate_side
            assert whole_run_work["total_h6_apply_calls_by_side"][side] == (
                inner["fixed_h6_modal_apply_calls"][side]
            )
            assert whole_run_work["total_h6_matrix_mult_calls_by_side"][side] == (
                inner["fixed_h6_modal_matrix_mult_calls"][side]
            )
            assert inner["fixed_h6_modal_apply_calls"][side] == (
                gate_side["fixed_h6_apply_calls"]
                + inner["cumulative_total_matmult_calls"]
            )
        assert result.release["borrowed_side_actions_retained"] is True
        result.destroy()
        assert context.inventory["fixed_h6_modal_solver"]["destroyed"] is True
        assert fixture["bottom_inverse"].diagnostics["destroyed"] is False
        assert fixture["top_inverse"].diagnostics["destroyed"] is False
        assert fixture["bottom_inverse"]._h6._destroyed is False
        assert fixture["top_inverse"]._h6._destroyed is False
    finally:
        if result is not None and not result._destroyed:
            result.destroy()
        if context is not None and not context._destroyed:
            context.destroy()
        for vector in (rhs, action_before, action_after):
            if vector is not None:
                vector.destroy()
        if original_action is not None:
            original_action.destroy()
        if original_context is not None:
            original_context.destroy()
        _destroy_side_block_fixture(fixture)


def test_side_balh_fixed_physical_action_matches_dense_and_borrows_factors() -> None:
    fixture = _fixed_h6_side_block_fixture()
    context = None
    vectors: list[PETSc.Vec] = []
    try:
        side_inverses = (
            fixture["bottom_inverse"],
            fixture["top_inverse"],
        )
        for inverse in side_inverses:
            inverse.configure_diagnostic_p4_corrections(
                0, None, refinement_target_tolerance=5.0e-13
            )
            transfer = inverse._owner_transfer
            assert transfer is not None

            def project(source: PETSc.Vec, *, timing=None) -> PETSc.Vec:
                del timing
                result = source.duplicate()
                source.copy(result)
                first, last = map(int, result.getOwnershipRange())
                local_rows = np.arange(first, last, dtype=np.int64)
                retained = np.isin(local_rows, np.asarray([0, 1, 4, 5]))
                result.getArray()[~retained] = PETSc.ScalarType(0.0)
                result.assemble()
                return result

            transfer.apply_adjoint = project
            transfer.apply_primal = project

        p4_solve_calls: dict[str, list[dict[str, object]]] = {}
        for side, inverse in zip(("bottom", "top"), side_inverses, strict=True):
            factor = inverse._p4_factor
            calls: list[dict[str, object]] = []
            p4_solve_calls[side] = calls
            original_solve = factor.solve_with_refinement

            def capture_solve(
                rhs: PETSc.Vec,
                solution: PETSc.Vec,
                *,
                residual_tolerance: float,
                _calls=calls,
                _original_solve=original_solve,
                **kwargs,
            ):
                _calls.append(
                    {
                        "residual_tolerance": residual_tolerance,
                        **kwargs,
                    }
                )
                return _original_solve(
                    rhs,
                    solution,
                    residual_tolerance=residual_tolerance,
                    **kwargs,
                )

            factor.solve_with_refinement = capture_solve

        side_apply_counts_before = {
            side: inverse.diagnostics["apply_count"]
            for side, inverse in zip(("bottom", "top"), side_inverses, strict=True)
        }
        context = block_ldu.create_side_balh_block_ldu_preconditioner(
            fixture["layout"],
            fixture["bottom"],
            fixture["top"],
            fixture["coupling"],
            side_inverses[0],
            side_inverses[1],
            sampled_columns=None,
            sampled_column_roles=None,
            sampled_column_contract_sha256=None,
            fixed_h6_modal_gmres_research=True,
            fixed_h6_modal_feedback_method=FIXED_PHYSICAL_BALH_MODAL_FEEDBACK_METHOD,
        )
        inventory = context.inventory
        assert inventory["preconditioner_identity"] == (
            "fixed_physical_balh_once_modal_gmres_research"
        )
        assert inventory["modal_feedback_method"] == (
            FIXED_PHYSICAL_BALH_MODAL_FEEDBACK_METHOD
        )
        assert "fixed_h6_modal_solver" not in inventory
        assert "fixed_h6_actions" not in inventory
        gate = inventory["early_sample_gate"]
        assert gate["pass"] is True
        assert gate["mode"] == (
            "fixed_physical_balh_modal_feedback_complex_repeat_linearity"
        )
        assert gate["rank_results"][MPI.COMM_WORLD.rank][
            "operator_action_completions"
        ] == 8
        assert gate["rank_results"][MPI.COMM_WORLD.rank][
            "modal_feedback_side_counts"
        ]
        for side, calls in p4_solve_calls.items():
            assert calls
            assert all(row["residual_tolerance"] == 1.0e-10 for row in calls)
            assert all(row["diagnostic_correction_steps"] == 1 for row in calls)
            assert all("refinement_target_tolerance" not in row for row in calls)
            inverse = side_inverses[0 if side == "bottom" else 1]
            assert inverse._p4_refinement_target_tolerance == 5.0e-13

        modal_bundle = context.action_modal_schur_system
        action = modal_bundle._side_actions[0]
        assert type(action) is FixedPhysicalBalancedActiveTraceAction
        dense_h6 = _tiny_h6_dense_action(side_inverses[0]._h6)
        selected = np.asarray([0, 2, 4, 6], dtype=np.int64)
        selector = np.zeros((len(selected), 8), dtype=np.complex128)
        selector[np.arange(len(selected)), selected] = 1.0
        q = np.diag(
            np.asarray([row in {0, 1, 4, 5} for row in range(8)], dtype=np.float64)
        ).astype(np.complex128)
        identity = np.eye(8, dtype=np.complex128)
        expected_matrix = (
            selector
            @ (q + (identity - q) @ dense_h6 @ (identity - q))
            @ selector.conj().T
        )
        assert np.linalg.norm(expected_matrix) > 0.0

        x = np.asarray(
            [0.2 + 0.3j, -0.4 + 0.1j, 0.7 - 0.2j, -0.1 - 0.5j],
            dtype=np.complex128,
        )
        y = np.asarray(
            [-0.3 + 0.2j, 0.5 + 0.4j, -0.6 + 0.1j, 0.8 - 0.3j],
            dtype=np.complex128,
        )
        alpha = -0.25 + 0.75j

        def apply_active(values: np.ndarray) -> np.ndarray:
            source = fixture["bottom"].A.createVecRight()
            target = fixture["bottom"].A.createVecLeft()
            vectors.extend((source, target))
            _set_vector(source, values)
            before = _gather_vector(source)
            action.apply(source, target)
            np.testing.assert_array_equal(_gather_vector(source), before)
            return _gather_vector(target)

        factor_counts_before = {
            side: inverse._p4_factor.solve_count
            for side, inverse in zip(("bottom", "top"), side_inverses, strict=True)
        }
        fixed_q_work_before = action.audit["fixed_q_actual_work_cumulative"]
        fx = apply_active(x)
        fy = apply_active(y)
        fxy = apply_active(x + y)
        falpha = apply_active(alpha * x)
        np.testing.assert_allclose(
            fx, expected_matrix @ x, rtol=1.0e-11, atol=1.0e-12
        )
        np.testing.assert_allclose(
            fy, expected_matrix @ y, rtol=1.0e-11, atol=1.0e-12
        )
        np.testing.assert_allclose(
            fxy, expected_matrix @ (x + y), rtol=1.0e-11, atol=1.0e-12
        )
        np.testing.assert_allclose(
            falpha, expected_matrix @ (alpha * x), rtol=1.0e-11, atol=1.0e-12
        )
        np.testing.assert_allclose(fxy, fx + fy, rtol=1.0e-11, atol=1.0e-12)
        np.testing.assert_allclose(falpha, alpha * fx, rtol=1.0e-11, atol=1.0e-12)
        for side, inverse in zip(("bottom", "top"), side_inverses, strict=True):
            if side == "bottom":
                assert inverse._p4_factor.solve_count - factor_counts_before[side] == 16
            else:
                assert inverse._p4_factor.solve_count == factor_counts_before[side]
            assert inverse.diagnostics["apply_count"] == side_apply_counts_before[side]
        assert action.audit["last_q_factor_solve_deltas"] == [2, 2]
        fixed_q_work = action.audit["fixed_q_actual_work_cumulative"]
        q_calls_in_this_scope = 4 * 2
        assert (
            fixed_q_work["mathematical_correction_steps_requested"]
            - fixed_q_work_before["mathematical_correction_steps_requested"]
            == q_calls_in_this_scope
        )
        assert fixed_q_work[
            "mathematical_correction_steps_completed_with_valid_q_audit"
        ] - fixed_q_work_before[
            "mathematical_correction_steps_completed_with_valid_q_audit"
        ] == q_calls_in_this_scope
        assert (
            fixed_q_work["successful_q_audit_count"]
            - fixed_q_work_before["successful_q_audit_count"]
            == q_calls_in_this_scope
        )
        assert (
            fixed_q_work["q_attempts_missing_complete_audit"]
            - fixed_q_work_before["q_attempts_missing_complete_audit"]
            == 0
        )
        assert (
            fixed_q_work["successful_factor_solve_delta_total"]
            - fixed_q_work_before["successful_factor_solve_delta_total"]
            == 16
        )
        assert (
            fixed_q_work["failed_q_attempt_count"]
            - fixed_q_work_before["failed_q_attempt_count"]
            == 0
        )
        for step_name in ("initial", "correction"):
            step_work = fixed_q_work["factor_solve_deltas_by_step"][step_name]
            step_work_before = fixed_q_work_before["factor_solve_deltas_by_step"][
                step_name
            ]
            audited_q_delta = (
                step_work["audited_q_count"] - step_work_before["audited_q_count"]
            )
            assert audited_q_delta == q_calls_in_this_scope
            assert (
                step_work["factor_solve_delta_total"]
                - step_work_before["factor_solve_delta_total"]
                == 8
            )
            assert (
                step_work["direct_zero_status_audited_q_count"]
                - step_work_before["direct_zero_status_audited_q_count"]
                + step_work["direct_zero_status_missing_q_count"]
                - step_work_before["direct_zero_status_missing_q_count"]
                == audited_q_delta
            )
            assert (
                0
                <= step_work["direct_zero_count"]
                - step_work_before["direct_zero_count"]
                <= step_work["direct_zero_status_audited_q_count"]
                - step_work_before["direct_zero_status_audited_q_count"]
            )
        assert "not the fixed mathematical correction-step count" in fixed_q_work[
            "p4_refinement_counter_semantics"
        ]
        assert action.audit["p4_refinement_target_tolerance_used"] is None
        assert action.audit["ordinary_side_refinement_target_tolerance"] == 5.0e-13
        assert action.audit["physical_residual_gate"] == 1.0e-10
        assert action.audit["augmented_residual_gate"] == 1.0e-10
        assert modal_bundle.diagnostics["method"] == (
            "fixed_physical_balh_once_modal_gmres_research"
        )
        assert modal_bundle.diagnostics["feedback_method"] == (
            FIXED_PHYSICAL_BALH_MODAL_FEEDBACK_METHOD
        )

        failed_p4 = side_inverses[0]._p4_factor

        def reject_residual(*_args, **_kwargs):
            raise P4PhysicalResidualGateError(
                {
                    "relative_residual": 2.0e-10,
                    "residual_tolerance": 1.0e-10,
                    "physical_gate_passed": False,
                    "augmented_gate_passed": False,
                }
            )

        failed_p4.solve_with_refinement = reject_residual
        source = fixture["bottom"].A.createVecRight()
        target = fixture["bottom"].A.createVecLeft()
        vectors.extend((source, target))
        _set_vector(source, x)
        source_before = _gather_vector(source)
        with pytest.raises(P4PhysicalResidualGateError) as residual_error:
            action.apply(source, target)
        np.testing.assert_array_equal(_gather_vector(source), source_before)
        assert residual_error.value.audit["relative_residual"] > 1.0e-10
        assert failed_p4.destroy_count == 0
        assert side_inverses[0]._h6._destroyed is False
        assert action.audit["last_balh_coupling"]["status"] == "ACTION_FAILED"
        assert action.audit["last_balh_coupling"]["live_after_cleanup"] == 0
        failed_q_work = action.audit["fixed_q_actual_work_cumulative"]
        assert (
            failed_q_work["mathematical_correction_steps_requested"]
            - fixed_q_work["mathematical_correction_steps_requested"]
            == 1
        )
        assert failed_q_work[
            "mathematical_correction_steps_completed_with_valid_q_audit"
        ] == fixed_q_work[
            "mathematical_correction_steps_completed_with_valid_q_audit"
        ]
        assert failed_q_work["successful_q_audit_count"] == fixed_q_work[
            "successful_q_audit_count"
        ]
        assert failed_q_work["failed_q_attempt_count"] - fixed_q_work[
            "failed_q_attempt_count"
        ] == 1
        assert failed_q_work["q_attempts_missing_complete_audit"] - fixed_q_work[
            "q_attempts_missing_complete_audit"
        ] == 1
        assert failed_q_work["successful_factor_solve_delta_total"] == fixed_q_work[
            "successful_factor_solve_delta_total"
        ]
        assert failed_q_work[
            "failed_live_factor_backsolve_delta_unknown_count"
        ] == fixed_q_work["failed_live_factor_backsolve_delta_unknown_count"]
        failed_q_attempt = failed_q_work["last_failed_q_attempt"]
        assert failed_q_attempt["mathematical_correction_steps_requested"] == 1
        assert failed_q_attempt["mathematical_correction_steps_completed"] is None
        assert failed_q_attempt[
            "mathematical_correction_steps_completed_with_valid_q_audit"
        ] == 0
        assert failed_q_attempt["live_factor_backsolve_delta"] == 0
        assert failed_q_attempt["factor_solve_deltas_by_step"] is None
        assert failed_q_attempt["direct_zero_status_by_step"] is None
        assert failed_q_attempt["exact_zero_audit_status"] == (
            "not_available_for_failed_q_attempt"
        )
        assert failed_q_attempt["successful_q_audit_count_includes_attempt"] is False

        context.destroy()
        assert context.inventory["fixed_physical_balh_modal_solver"]["destroyed"] is True
        for inverse in side_inverses:
            assert inverse.diagnostics["destroyed"] is False
            assert inverse._p4_factor.destroy_count == 0
            assert inverse._h6._destroyed is False
    finally:
        if context is not None and not context._destroyed:
            context.destroy()
        for vector in vectors:
            vector.destroy()
        _destroy_side_block_fixture(fixture)


def test_v13_factory_passes_the_same_fixed_b_actions_to_modal_and_ldu(
    monkeypatch,
) -> None:
    """Exercise the real V13 factory selector and its action identities.

    Only the dense Schur builder is replaced so this remains a selector and
    ownership fixture.  The factory creates the real fixed physical actions
    and the real LDU context; it must route those exact objects to both sides.
    """

    fixture = _fixed_h6_side_block_fixture()
    context = None
    original_operator = None
    row_source = None
    row_target = None
    captured: dict[str, object] = {}
    inverses = {
        "bottom": fixture["bottom_inverse"],
        "top": fixture["top_inverse"],
    }
    counts_before = {
        side: {
            key: int(inverse.diagnostics[key])
            for key in ("apply_count", "total_iterations")
        }
        for side, inverse in inverses.items()
    }

    def make_v13_system(
        coupling,
        bottom_action,
        top_action,
        *,
        modal_owner,
        **kwargs,
    ):
        del kwargs
        captured["bottom_action"] = bottom_action
        captured["top_action"] = top_action
        captured["modal_owner"] = modal_owner
        owner = int(modal_owner)
        rank = MPI.COMM_WORLD.rank
        modal_constraint = np.asarray(
            internal_modal_constraint_matrix(coupling), dtype=np.complex128
        )
        fixture_modal_count = int(modal_constraint.shape[0])
        schur = (
            np.eye(fixture_modal_count, dtype=np.complex128)
            if rank == owner
            else None
        )
        lu = (
            np.eye(fixture_modal_count, dtype=np.complex128)
            if rank == owner
            else None
        )
        pivots = (
            np.arange(fixture_modal_count, dtype=np.int32)
            if rank == owner
            else None
        )
        baseline = {
            side: block_ldu._v13_side_operation_counts(action)
            for side, action in (
                ("bottom", bottom_action),
                ("top", top_action),
            )
        }
        assert all(isinstance(value, dict) for value in baseline.values())
        system = block_ldu.Task041V13ConsistentModalSurrogateSystem(
            modal_schur=schur,
            modal_constraint=modal_constraint,
            lu=lu,
            pivots=pivots,
            modal_owner=owner,
            comm=MPI.COMM_WORLD,
            condition=None,
            storage_plan={"fixture": "factory-selector-only"},
            build_audit={
                "fixture": "factory-selector-only; real V13 builder not exercised",
                "full_owner_matrix_pages_materialized_before_sample_gate": True,
                "sample_columns_written_directly_to_final_matrix": list(
                    range(fixture_modal_count)
                ),
                "remaining_columns_applied_once": [],
                "side_solver_entry_zero_supported": True,
            },
            bottom_action=bottom_action,
            top_action=top_action,
            side_operation_baseline=baseline,
        )
        system.record_side_operation_counts(
            {
                side: block_ldu._v13_side_operation_counts(action)
                for side, action in (
                    ("bottom", bottom_action),
                    ("top", top_action),
                )
            }
        )
        return system

    monkeypatch.setattr(
        block_ldu,
        "build_task041_v13_consistent_modal_surrogate",
        make_v13_system,
    )
    columns, roles, contract_sha = _sample_contract()
    policy = block_ldu.resolve_task041_modal_solver_policy(
        block_ldu.TASK041_V13_CONSISTENT_MODAL_POLICY_ID
    )
    try:
        context = block_ldu.create_side_balh_block_ldu_preconditioner(
            fixture["layout"],
            fixture["bottom"],
            fixture["top"],
            fixture["coupling"],
            inverses["bottom"],
            inverses["top"],
            sampled_columns=columns,
            sampled_column_roles=roles,
            sampled_column_contract_sha256=contract_sha,
            fixed_h6_modal_gmres_research=True,
            modal_solver_policy=policy,
            v13_fresh_authority_callback=lambda _phase, _report: {},
        )
        bottom_b = captured["bottom_action"]
        top_b = captured["top_action"]
        assert context.bottom_action is bottom_b
        assert context.top_action is top_b
        assert context.action_modal_schur_system.bottom_action is bottom_b
        assert context.action_modal_schur_system.top_action is top_b
        assert context.bottom_action is not inverses["bottom"]
        assert context.top_action is not inverses["top"]
        assert context.inventory["v13_same_B_objects_for_schur_and_LDU"] is True
        assert context.inventory["side_solver_entry_zero_supported"] is True
        assert context.inventory["modal_block_condition"] is None
        assert context.inventory["modal_block_condition_status"] == "not_measured"
        assert context.inventory["v13_side_operation_deltas"] == {
            "bottom": {"apply_count": 0, "total_iterations": 0},
            "top": {"apply_count": 0, "total_iterations": 0},
        }
        for side, inverse in inverses.items():
            after = inverse.diagnostics
            assert {
                key: int(after[key])
                for key in ("apply_count", "total_iterations")
            } == counts_before[side]
        assert bottom_b.audit["apply_count"] == 0
        assert top_b.audit["apply_count"] == 0

        # Keep this selector's fixed-B action identity/ownership assertions.
        # Exact-zero and near-zero same-system original-A capture now live in
        # test_v13_unmocked_builder_owner_lu_and_original_modal_row_math;
        # test347 continues to cover the registered tiny real-FE route.
    finally:
        if context is not None and not context._destroyed:
            context.destroy()
        if original_operator is not None:
            original_operator.destroy()
        for vector in (row_source, row_target):
            if vector is not None:
                vector.destroy()
        for action in (captured.get("bottom_action"), captured.get("top_action")):
            if action is not None and not action.audit["destroyed"]:
                action.destroy()
        _destroy_side_block_fixture(fixture)


def test_v15_original_modal_row_metrics_match_decimal_complex_oracle():
    """Independently check row scaling, exact-zero semantics, and raw d=w-r."""

    def decimal_complex(value: complex) -> tuple[Decimal, Decimal]:
        return _decimal_complex_pair(value)

    def decimal_abs(value: complex) -> Decimal:
        real, imag = decimal_complex(value)
        return (real * real + imag * imag).sqrt()

    # Row 0 establishes a 1e100 scale.  Row 1 is 180 orders smaller but has a
    # representable cancellation residual; the rowwise gate must retain it.
    r = np.asarray([0.0j, 1.0e-80 - 2.0e-80j, 0.0j], dtype=np.complex128)
    tb = np.asarray([1.0e100 + 0.0j, 0.0j, 2.0 + 0.0j], dtype=np.complex128)
    tt = np.asarray([-1.0e100 + 0.0j, 0.0j, -2.0 + 0.0j], dtype=np.complex128)
    tiny_w = complex(
        np.nextafter(1.0e-80, np.inf),
        np.nextafter(-2.0e-80, np.inf),
    )
    tc = np.asarray([0.0j, tiny_w, 0.0j], dtype=np.complex128)
    w = np.asarray([0.0j, tiny_w, 0.0j], dtype=np.complex128)
    metrics, residual = block_ldu._v13_original_modal_row_metrics(
        r, w, tb, tt, tc
    )
    expected_raw = np.subtract(w, r)
    np.testing.assert_array_equal(residual, expected_raw)
    assert (
        metrics["contract_id"]
        == "task041.v15.original_modal_row.terms_backward.v1"
    )
    assert metrics["rhs_exact_zero"] is False
    assert metrics["legacy_rhs_relative_status"] == "passed"
    assert metrics["eta_terms_inf"] < 1.0e-10
    assert metrics["decomposition_passed"] is True
    assert metrics["row_relative_error"][1] > 1.0e-17

    with localcontext() as context:
        context.prec = 120
        oracle_rows = []
        for index in range(r.size):
            numerator = decimal_abs(complex(expected_raw[index]))
            denominator = sum(
                (
                    decimal_abs(complex(array[index]))
                    for array in (tb, tt, tc, r)
                ),
                Decimal(0),
            )
            oracle_rows.append(
                Decimal(0) if denominator == 0 else numerator / denominator
            )
        oracle_max = max(oracle_rows)
        assert float(oracle_rows[1]) == pytest.approx(
            float(metrics["row_relative_error"][1]), rel=2.0e-15
        )
        assert float(oracle_max) == pytest.approx(
            float(metrics["eta_terms_inf"]), rel=2.0e-15
        )

    # Overall complex scaling must preserve each row's ratio without using a
    # largest-row scale.  The non-real phase and 2**+-200 cases cover a broad
    # representable range while retaining the deliberately weak row.
    phase = np.complex128(0.6 + 0.8j)
    scaled_eta = []
    scale_tb = np.asarray(
        [3.0 - 1.0j, 2.0**-78 + 1j * (2.0**-79)], dtype=np.complex128
    )
    scale_tt = np.asarray(
        [-2.0 + 0.5j, -(2.0**-79) + 1j * (2.0**-80)],
        dtype=np.complex128,
    )
    scale_tc = np.asarray(
        [0.25 + 0.125j, 2.0**-77 - 1j * (2.0**-80)],
        dtype=np.complex128,
    )
    assert scale_tb[1].imag == 2.0**-79
    assert scale_tt[1].real == -(2.0**-79)
    assert scale_tt[1].imag == 2.0**-80
    assert scale_tc[1].real == 2.0**-77
    assert scale_tc[1].imag == -(2.0**-80)
    scale_r = scale_tc.copy()
    scale_r += scale_tb
    scale_r += scale_tt
    scale_w = scale_r.copy()
    scale_w += np.asarray(
        [1.0e-12 - 2.0e-12j, 2.0**-115 + 1j * (2.0**-116)],
        dtype=np.complex128,
    )
    weak_row_scale = sum(
        abs(complex(values[1]))
        for values in (scale_tb, scale_tt, scale_tc, scale_r)
    )
    weak_row_relative_residual = abs(complex(scale_w[1] - scale_r[1])) / (
        weak_row_scale
    )
    assert 1.0e-23 < weak_row_scale < 3.0e-23
    assert 1.0e-12 < weak_row_relative_residual < 1.0e-10
    for exponent in (-200, -40, 0, 40, 200):
        scale = np.ldexp(1.0, exponent) * phase
        scaled_arrays = tuple(
            np.asarray(value * scale, dtype=np.complex128)
            for value in (scale_r, scale_w, scale_tb, scale_tt, scale_tc)
        )
        scaled_metrics, scaled_d = block_ldu._v13_original_modal_row_metrics(
            *scaled_arrays
        )
        assert scaled_metrics["status"] == "passed"
        with localcontext() as context:
            context.prec = 180
            scaled_oracle_rows = []
            for index in range(scale_r.size):
                numerator = decimal_abs(complex(scaled_d[index]))
                denominator = sum(
                    (
                        decimal_abs(complex(array[index]))
                        for array in scaled_arrays[2:] + (scaled_arrays[0],)
                    ),
                    Decimal(0),
                )
                scaled_oracle_rows.append(
                    Decimal(0)
                    if denominator == 0
                    else numerator / denominator
                )
            scaled_expected = max(scaled_oracle_rows)
            assert float(scaled_expected) == pytest.approx(
                scaled_metrics["eta_terms_inf"], rel=5.0e-14, abs=1.0e-300
            )
            assert float(scaled_oracle_rows[1]) == pytest.approx(
                scaled_metrics["row_relative_error"][1],
                rel=5.0e-14,
                abs=1.0e-300,
            )
            assert scaled_metrics["row_relative_error"][1] > 0.0
        scaled_eta.append(float(scaled_metrics["eta_terms_inf"]))
    assert all(np.isfinite(value) for value in scaled_eta)

    # Apply distinct complex scales to the two rows of this same case.  The
    # weak row remains independently represented and decides the rowwise gate.
    row_scales = np.asarray(
        [phase * np.ldexp(1.0, 40), np.conjugate(phase) * np.ldexp(1.0, -40)],
        dtype=np.complex128,
    )
    row_scaled_arrays = tuple(
        np.asarray(values * row_scales, dtype=np.complex128)
        for values in (scale_r, scale_w, scale_tb, scale_tt, scale_tc)
    )
    row_scaled_metrics, row_scaled_residual = (
        block_ldu._v13_original_modal_row_metrics(*row_scaled_arrays)
    )
    assert row_scaled_metrics["status"] == "passed"
    with localcontext() as context:
        context.prec = 180
        rowwise_oracle = []
        for index in range(row_scaled_arrays[0].size):
            numerator = decimal_abs(complex(row_scaled_residual[index]))
            denominator = sum(
                (
                    decimal_abs(complex(values[index]))
                    for values in (
                        row_scaled_arrays[2],
                        row_scaled_arrays[3],
                        row_scaled_arrays[4],
                        row_scaled_arrays[0],
                    )
                ),
                Decimal(0),
            )
            rowwise_oracle.append(
                Decimal(0) if denominator == 0 else numerator / denominator
            )
        for index, oracle_error in enumerate(rowwise_oracle):
            assert float(oracle_error) == pytest.approx(
                row_scaled_metrics["row_relative_error"][index],
                rel=5.0e-14,
                abs=1.0e-300,
            )
            assert (oracle_error <= Decimal.from_float(1.0e-10)) == bool(
                row_scaled_metrics["row_relative_error"][index] <= 1.0e-10
            )
        assert rowwise_oracle[1] > rowwise_oracle[0]

        # Pollute only the weak row by a representable amount well above the
        # same row's scale; the unchanged gate must reject that row.
        polluted_w = row_scaled_arrays[1].copy()
        weak_row_scale = sum(
            (
                decimal_abs(complex(values[1]))
                for values in (
                    row_scaled_arrays[2],
                    row_scaled_arrays[3],
                    row_scaled_arrays[4],
                    row_scaled_arrays[0],
                )
            ),
            Decimal(0),
        )
        weak_pollution = float(weak_row_scale / Decimal(4))
        polluted_w[1] += weak_pollution * (0.6 + 0.8j)
        polluted_arrays = (
            row_scaled_arrays[0],
            polluted_w,
            *row_scaled_arrays[2:],
        )
        polluted_metrics, polluted_residual = (
            block_ldu._v13_original_modal_row_metrics(*polluted_arrays)
        )
        polluted_oracle_numerator = decimal_abs(complex(polluted_residual[1]))
        polluted_oracle = polluted_oracle_numerator / weak_row_scale
        assert float(polluted_oracle) == pytest.approx(
            polluted_metrics["row_relative_error"][1], rel=5.0e-14
        )
        assert polluted_oracle > Decimal.from_float(1.0e-10)
        assert polluted_metrics["status"] == "rejected"
        assert polluted_metrics["row_relative_error"][1] > 1.0e-10

    # Different supports make ||sum_i |x_i|||_2 distinct from
    # sum_i ||x_i||_2.  The v1 eta_terms_2 contract uses the latter.
    terms_2_rhs = np.asarray([0.0j, 0.0j, 5.0 + 0.0j])
    terms_2_bottom = np.asarray([3.0 + 0.0j, 0.0j, 0.0j])
    terms_2_top = np.asarray([0.0j, 4.0 + 0.0j, 0.0j])
    terms_2_constraint = np.asarray([0.0j, 0.0j, 12.0 + 0.0j])
    terms_2_output = terms_2_rhs + np.asarray(
        [0.25 + 0.0j, 0.5 + 0.0j, 0.75 + 0.0j]
    )
    terms_2_metrics, terms_2_residual = block_ldu._v13_original_modal_row_metrics(
        terms_2_rhs,
        terms_2_output,
        terms_2_bottom,
        terms_2_top,
        terms_2_constraint,
    )
    np.testing.assert_array_equal(
        terms_2_residual, np.subtract(terms_2_output, terms_2_rhs)
    )
    with localcontext() as context:
        context.prec = 120

        def decimal_l2(values: np.ndarray) -> Decimal:
            return sum(
                (
                    decimal_abs(complex(value)) ** 2
                    for value in values
                ),
                Decimal(0),
            ).sqrt()

        expected_terms_2 = decimal_l2(terms_2_residual) / sum(
            (
                decimal_l2(values)
                for values in (
                    terms_2_bottom,
                    terms_2_top,
                    terms_2_constraint,
                    terms_2_rhs,
                )
            ),
            Decimal(0),
        )
        wrong_rowwise_norm = (
            sum(
                (
                    _decimal_sum(
                        (
                            decimal_abs(complex(array[index]))
                            for array in (
                                terms_2_bottom,
                                terms_2_top,
                                terms_2_constraint,
                                terms_2_rhs,
                            )
                        ),
                    )
                    ** 2
                    for index in range(terms_2_rhs.size)
                ),
                Decimal(0),
            ).sqrt()
        )
        wrong_terms_2 = decimal_l2(terms_2_residual) / wrong_rowwise_norm
        assert float(expected_terms_2) == pytest.approx(
            terms_2_metrics["eta_terms_2"], rel=2.0e-15
        )
        assert abs(float(expected_terms_2) - float(wrong_terms_2)) > 1.0e-4
    assert terms_2_metrics["eta_terms_2_denominator_formula"] == (
        "||t_bottom||_2 + ||t_top||_2 + ||t_constraint||_2 + ||r_modal||_2"
    )

    # Deliberate floating-point order sensitivity is an observation, not an
    # extra exact-equality gate: the independent Decimal sum identifies the
    # exact value while the componentwise tolerance remains authoritative.
    order_constraint = np.asarray([1.0e16 + 0.0j])
    order_bottom = np.asarray([1.0 + 0.0j])
    order_top = np.asarray([-1.0e16 + 0.0j])
    production_order = order_constraint.copy()
    production_order += order_bottom
    production_order += order_top
    alternate_order = order_constraint.copy()
    alternate_order += order_top
    alternate_order += order_bottom
    assert production_order[0] == 0.0
    assert alternate_order[0] == 1.0
    exact_sum = _decimal_complex_sum(
        _decimal_complex_sum(
            _decimal_complex_pair(order_constraint[0]),
            _decimal_complex_pair(order_bottom[0]),
        ),
        _decimal_complex_pair(order_top[0]),
    )
    assert exact_sum == (Decimal(1), Decimal(0))
    order_metrics, _ = block_ldu._v13_original_modal_row_metrics(
        np.asarray([0.0j]),
        production_order,
        order_bottom,
        order_top,
        order_constraint,
    )
    assert order_metrics["decomposition_exact"] is True
    assert order_metrics["decomposition_passed"] is True

    exact_zero_metrics, exact_zero_d = block_ldu._v13_original_modal_row_metrics(
        np.zeros(1, dtype=np.complex128),
        np.asarray([2.0**-52 + 0.0j]),
        np.asarray([1.0 + 0.0j]),
        np.zeros(1, dtype=np.complex128),
        np.asarray([-1.0 + 2.0**-52 + 0.0j]),
    )
    assert exact_zero_d[0] == pytest.approx(2.0**-52)
    assert exact_zero_metrics["rhs_exact_zero"] is True
    assert exact_zero_metrics["legacy_rhs_relative_status"] == "not_defined"
    assert exact_zero_metrics["status"] == "passed"
    assert exact_zero_metrics["decomposition_passed"] is True

    tiny_rhs = np.asarray([1.0e-300 + 0.0j], dtype=np.complex128)
    tiny_w = np.asarray([np.nextafter(1.0e-300, np.inf) + 0.0j])
    tiny_constraint = tiny_w.copy()
    tiny_metrics, tiny_d = block_ldu._v13_original_modal_row_metrics(
        tiny_rhs,
        tiny_w,
        np.zeros(1, dtype=np.complex128),
        np.zeros(1, dtype=np.complex128),
        tiny_constraint,
    )
    assert tiny_metrics["rhs_exact_zero"] is False
    assert tiny_metrics["legacy_rhs_relative_status"] == "passed"
    assert tiny_d[0] != 0.0
    assert tiny_metrics["decomposition_passed"] is True

    cancellation_bottom = np.asarray([1.0e6 + 0.0j])
    cancellation_constraint = np.asarray([1.0e-7 + 0.0j])
    cancellation_top = np.asarray([-1.0e6 + 0.0j])
    cancellation_w = cancellation_constraint.copy()
    cancellation_w += cancellation_bottom
    cancellation_w += cancellation_top
    cancellation_rhs = cancellation_w * (1.0 + 1.0e-4)
    cancellation_metrics, _ = block_ldu._v13_original_modal_row_metrics(
        cancellation_rhs,
        cancellation_w,
        cancellation_bottom,
        cancellation_top,
        cancellation_constraint,
    )
    assert cancellation_metrics["status"] == "passed"
    assert cancellation_metrics["legacy_rhs_relative_status"] == "rejected"
    assert cancellation_metrics["legacy_rhs_relative_error"] > 1.0e-10
    assert cancellation_metrics["decomposition_passed"] is True

    decomposition_inside_metrics, _ = block_ldu._v13_original_modal_row_metrics(
        np.asarray([1.0e16 + 0.0j]),
        np.asarray([1.0e16 + 0.0j]),
        np.asarray([1.0e16 + 0.0j]),
        np.asarray([1.0e6 + 0.0j]),
        np.asarray([0.0j]),
    )
    assert decomposition_inside_metrics["status"] == "passed"
    assert decomposition_inside_metrics["decomposition_exact"] is False
    assert decomposition_inside_metrics["decomposition_passed"] is True
    assert decomposition_inside_metrics["decomposition_eta_terms_inf"] <= 1.0e-10
    assert decomposition_inside_metrics["decomposition_max_abs_difference"] == pytest.approx(
        1.0e6
    )

    decomposition_outside_metrics, _ = block_ldu._v13_original_modal_row_metrics(
        np.asarray([1.0e16 + 0.0j]),
        np.asarray([1.0e16 + 0.0j]),
        np.asarray([1.0e16 + 0.0j]),
        np.asarray([4.0e6 + 0.0j]),
        np.asarray([0.0j]),
    )
    assert decomposition_outside_metrics["status"] == "passed"
    assert decomposition_outside_metrics["decomposition_exact"] is False
    assert decomposition_outside_metrics["decomposition_passed"] is False
    assert decomposition_outside_metrics["decomposition_eta_terms_inf"] > 1.0e-10
    assert decomposition_outside_metrics[
        "decomposition_max_abs_difference"
    ] == pytest.approx(4.0e6)

    nonfinite = np.asarray([complex(float("nan"), float("inf"))])
    nonfinite_metrics, nonfinite_d = block_ldu._v13_original_modal_row_metrics(
        np.zeros(1, dtype=np.complex128),
        nonfinite,
        np.zeros(1, dtype=np.complex128),
        np.zeros(1, dtype=np.complex128),
        np.zeros(1, dtype=np.complex128),
    )
    assert nonfinite_metrics["status"] == "rejected"
    assert nonfinite_metrics["reason"] == "non_finite_component"
    assert np.isnan(nonfinite_d.real[0]) or np.isinf(nonfinite_d.imag[0])

    overflow_metrics, overflow_d = block_ldu._v13_original_modal_row_metrics(
        np.asarray([-1.0e308 + 0.0j]),
        np.asarray([1.0e308 + 0.0j]),
        np.asarray([1.0e308 + 0.0j]),
        np.zeros(1, dtype=np.complex128),
        np.zeros(1, dtype=np.complex128),
    )
    assert overflow_metrics["status"] == "rejected"
    assert overflow_metrics["reason"] == "unrepresentable_binary64_residual"
    assert np.isinf(overflow_d.real[0])

    shape_metrics, _ = block_ldu._v13_original_modal_row_metrics(
        np.zeros(2, dtype=np.complex128),
        np.zeros(1, dtype=np.complex128),
        np.zeros(2, dtype=np.complex128),
        np.zeros(2, dtype=np.complex128),
        np.zeros(2, dtype=np.complex128),
    )
    assert shape_metrics["status"] == "rejected"
    assert shape_metrics["reason"] == "shape_mismatch"


@pytest.mark.skipif(
    MPI.COMM_WORLD.size != 2,
    reason="rank-local V13 timing canonicalization requires an MPI2 fixture",
)
def test_v13_sample_admission_report_hash_uses_canonical_rank_times() -> None:
    """Different local durations produce one shared admission request hash."""

    comm = MPI.COMM_WORLD
    report = block_ldu._v13_canonicalize_rank_elapsed(
        comm,
        {
            "method": block_ldu.TASK041_V13_CONSISTENT_MODAL_POLICY_ID,
            "sample_columns_written_to_final_matrix": list(range(8)),
            "remaining_column_count": 12,
        },
        metric="assembly",
        local_elapsed_seconds=0.25 + 0.5 * comm.rank,
    )
    assert report["assembly_elapsed_seconds_max_rank"] == pytest.approx(0.75)
    assert report["assembly_elapsed_seconds_by_rank"] == [
        {"rank": 0, "elapsed_seconds": 0.25},
        {"rank": 1, "elapsed_seconds": 0.75},
    ]
    reports = comm.allgather(report)
    assert all(candidate == reports[0] for candidate in reports)
    request_hashes = [
        hashlib.sha256(
            json.dumps(candidate, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        for candidate in reports
    ]
    assert len(set(request_hashes)) == 1


def test_v13_restart_loss_uses_complete_dynamic_denominator_windows() -> None:
    """Synthetic rows check V13 window selection and denominator provenance."""

    keys = (
        "global_true_relative_residual",
        "bottom_true_relative_residual",
        "top_true_relative_residual",
        "modal_true_relative_residual",
    )
    threshold = float(block_ldu._TASK041_V13_CONSISTENT_MODAL_POLICY["outer_threshold"])

    def row(iteration: int, values: Mapping[str, float]) -> dict[str, Any]:
        components = {
            "global": {"original_rhs_norm": 4.0, "floor": 1.0e-30},
            "bottom": {
                "rhs_block_norm": 1.0,
                "A_x_block_norm": 2.0 + 0.01 * iteration,
                "coupling_block_norm": 0.5,
                "floor": 1.0e-30,
            },
            "top": {
                "rhs_block_norm": 1.0,
                "A_x_block_norm": 1.5 + 0.005 * iteration,
                "coupling_block_norm": 0.25,
                "floor": 1.0e-30,
            },
            "modal": {
                "rhs_modal_norm": 1.0,
                "bottom_projection_norm": 1.25 + 0.003 * iteration,
                "top_projection_norm": 1.5,
                "modal_constraint_action_norm": 2.0 + 0.002 * iteration,
                "floor": 1.0e-30,
            },
        }
        metric = {
            "global": keys[0],
            "bottom": keys[1],
            "top": keys[2],
            "modal": keys[3],
        }
        scope = {
            "global": "original_rhs_norm_for_this_solve",
            "bottom": "recomputed_from_this_true_residual_row",
            "top": "recomputed_from_this_true_residual_row",
            "modal": "recomputed_from_this_true_residual_row",
        }
        operands = {
            name: {
                "numerator_norm": float(values[metric[name]])
                * max(parts.values()),
                "denominator_norm": max(parts.values()),
                "denominator_components": parts,
                "denominator_scope": scope[name],
            }
            for name, parts in components.items()
        }
        return {
            "iteration": iteration,
            **{key: float(value) for key, value in values.items()},
            "true_residual_operands": {
                "scope": "one_true_residual_snapshot_row",
                **operands,
            },
        }

    def history(case: str) -> dict[int, dict[str, Any]]:
        result = {}
        for iteration in range(16, 49):
            fraction = (iteration - 16) / 16.0
            if case == "pre_progress_then_stall":
                values = (
                    {
                        keys[0]: 1.0 - 0.30 * fraction,
                        keys[1]: 0.8 - 0.16 * fraction,
                        keys[2]: 0.8 * threshold,
                        keys[3]: 0.6 - 0.12 * fraction,
                    }
                    if iteration <= 32
                    else {
                        keys[0]: 0.7,
                        keys[1]: 0.64,
                        keys[2]: 0.8 * threshold,
                        keys[3]: 0.48,
                    }
                )
                if iteration in {24, 40}:
                    values[keys[0]] += 0.2
            elif case == "no_pre_progress":
                values = (
                    {
                        keys[0]: 0.5 - 0.01 * fraction,
                        keys[1]: 0.7,
                        keys[2]: 0.6,
                        keys[3]: 0.4,
                    }
                    if iteration <= 32
                    else {
                        keys[0]: 0.49,
                        keys[1]: 0.7,
                        keys[2]: 0.6,
                        keys[3]: 0.4,
                    }
                )
                if iteration == 24:
                    values[keys[0]] += 0.2
            else:
                post_fraction = max(0.0, (iteration - 32) / 16.0)
                values = (
                    {
                        keys[0]: 1.0 - 0.30 * fraction,
                        keys[1]: 0.9 - 0.1 * fraction,
                        keys[2]: 0.8,
                        keys[3]: 0.7,
                    }
                    if iteration <= 32
                    else {
                        keys[0]: 0.7,
                        keys[1]: 0.8 - 0.12 * post_fraction,
                        keys[2]: 0.8,
                        keys[3]: 0.7,
                    }
                )
            result[iteration] = row(iteration, values)
        return result

    accepted = block_ldu._task041_v13_outer_restart_loss_evidence(
        history("pre_progress_then_stall"), threshold=threshold
    )
    assert accepted["clear_restart_loss"] is True
    assert len(accepted["pre_window_samples"]) == 17
    assert len(accepted["post_window_samples"]) == 17
    assert keys[2] not in accepted["required_unpassed_metrics_at_boundary"]
    assert accepted["denominator_basis"]["bottom_top_modal"] == (
        "existing per-row component-max formula with operands retained per sample"
    )
    assert accepted["post_window_samples"][0]["true_residual_operands"]["bottom"][
        "denominator_norm"
    ] != accepted["post_window_samples"][-1]["true_residual_operands"]["bottom"][
        "denominator_norm"
    ]

    no_progress = block_ldu._task041_v13_outer_restart_loss_evidence(
        history("no_pre_progress"), threshold=threshold
    )
    assert no_progress["pre_restart_global_progress_at_least_10_percent"] is False
    assert no_progress["clear_restart_loss"] is False

    improving_block = block_ldu._task041_v13_outer_restart_loss_evidence(
        history("post_block_progress"), threshold=threshold
    )
    assert improving_block["clear_restart_loss"] is False
    assert keys[1] in improving_block["unpassed_blocks_with_sustained_effective_progress"]

    accepted_history = history("pre_progress_then_stall")
    boundary_values = {
        key: float(accepted_history[32][key]) for key in keys
    }
    finite_window = block_ldu._task041_v13_outer_best_window(
        boundary_values,
        [accepted_history[index] for index in range(33, 49)],
        start_iteration=32,
        end_iteration=48,
        threshold=threshold,
    )
    assert finite_window["status"] == "complete"
    assert len(finite_window["samples"]) == 16
    assert all(
        sample["true_residual_operands"]["bottom"]["denominator_scope"]
        == "recomputed_from_this_true_residual_row"
        for sample in finite_window["samples"]
    )
    corrupted_history = copy.deepcopy(accepted_history)
    corrupted_history[40]["true_residual_operands"]["bottom"][
        "denominator_components"
    ]["A_x_block_norm"] += 1.0
    corrupted = block_ldu._task041_v13_outer_restart_loss_evidence(
        corrupted_history, threshold=threshold
    )
    assert corrupted["clear_restart_loss"] is False
    assert corrupted["evidence_status"] == (
        "missing_complete_pre_or_post_true_residual_window"
    )


@pytest.mark.parametrize(
    "scenario",
    (
        "restart64_pass",
        "restart64_fresh_cap_refusal",
        "finite_stop_after_restart64_control_injection",
    ),
)
def test_v13_solve_entry_resumes_same_ksp_with_nonzero_x_and_total_limit(
    monkeypatch, scenario: str
) -> None:
    """Exercise V13 safe-boundary branches through the real outer solve entry.

    This is a 64-row PETSc control-path fixture, not an FE or natural
    restart-loss result.  Its explicitly isolated workspace-report substitute
    records the real Vec ownership but does not qualify the production builder
    workspace model.  The spectral diagonal keeps ordinary restarted
    FGMRES active through the injected iteration-48 safe boundary; the real
    solve function then either resumes that same KSP at restart 64 or continues
    at restart 32 after a field-bound synthetic cap refusal.  The finite-stop
    case injects only the two-window stalled decision after restart64; it does
    not claim naturally stalled FE behavior or production resource authority.
    """

    comm = MPI.COMM_WORLD
    side_size = 31
    modal_count = 2
    modal_owner = comm.size - 1
    local_side_size = side_size // comm.size + int(
        comm.rank < side_size % comm.size
    )
    owned_matrices: list[PETSc.Mat] = []
    owned_vectors: list[PETSc.Vec] = []
    result = None
    context = None

    def diagonal_matrix(values: np.ndarray) -> PETSc.Mat:
        template = PETSc.Vec().createMPI(
            (local_side_size, side_size), comm=comm
        )
        try:
            dense = np.diag(np.asarray(values, dtype=np.complex128))
            matrix = _matrix_from_dense(template, template, dense)
        finally:
            template.destroy()
        owned_matrices.append(matrix)
        return matrix

    bottom_diagonal = np.geomspace(1.0, 1.0e5, side_size)
    top_diagonal = np.geomspace(1.5, 1.5e5, side_size)
    bottom_matrix = diagonal_matrix(bottom_diagonal)
    top_matrix = diagonal_matrix(top_diagonal)
    bottom_rhs_template = bottom_matrix.createVecRight()
    top_rhs_template = top_matrix.createVecRight()
    owned_vectors.extend((bottom_rhs_template, top_rhs_template))
    bottom_system = SimpleNamespace(
        A=bottom_matrix,
        b=bottom_rhs_template,
        global_size=side_size,
        local_mesh=SimpleNamespace(mesh=SimpleNamespace(comm=comm)),
    )
    top_system = SimpleNamespace(
        A=top_matrix,
        b=top_rhs_template,
        global_size=side_size,
        local_mesh=SimpleNamespace(mesh=SimpleNamespace(comm=comm)),
    )
    layout = HybridAugmentedLayout.build(bottom_system, top_system, modal_count)

    modal_row_local = 1 if comm.rank == modal_owner else 0
    modal_template = PETSc.Vec().createMPI(
        (modal_row_local, 1), comm=comm
    )
    bottom_col = bottom_matrix.createVecRight()
    top_col = top_matrix.createVecRight()
    bottom_row = bottom_matrix.createVecLeft()
    top_row = top_matrix.createVecLeft()
    owned_vectors.extend((modal_template, bottom_col, top_col, bottom_row, top_row))

    def zero_coupling_matrix(
        row_template: PETSc.Vec,
        column_template: PETSc.Vec,
        rows: int,
        columns: int,
    ) -> PETSc.Mat:
        matrix = _matrix_from_dense(
            row_template,
            column_template,
            np.zeros((rows, columns), dtype=np.complex128),
        )
        owned_matrices.append(matrix)
        return matrix

    bottom_projection = zero_coupling_matrix(
        modal_template, bottom_col, 1, side_size
    )
    top_projection = zero_coupling_matrix(modal_template, top_col, 1, side_size)
    bottom_positive = zero_coupling_matrix(bottom_row, modal_template, side_size, 1)
    bottom_negative = zero_coupling_matrix(bottom_row, modal_template, side_size, 1)
    top_positive = zero_coupling_matrix(top_row, modal_template, side_size, 1)
    top_negative = zero_coupling_matrix(top_row, modal_template, side_size, 1)
    coupling = SimpleNamespace(
        mode_count_per_direction=1,
        internal_equation_count=modal_count,
        bottom=SimpleNamespace(
            projection=bottom_projection,
            positive_traction=bottom_positive,
            negative_traction=bottom_negative,
            modal_rhs_correction=np.zeros(1, dtype=np.complex128),
        ),
        top=SimpleNamespace(
            projection=top_projection,
            positive_traction=top_positive,
            negative_traction=top_negative,
            modal_rhs_correction=np.zeros(1, dtype=np.complex128),
        ),
        propagation=SimpleNamespace(
            forward=SimpleNamespace(factors=np.ones(1, dtype=np.complex128)),
            backward=SimpleNamespace(factors=np.ones(1, dtype=np.complex128)),
        ),
        negative_trace_to_positive=np.zeros((1, 1), dtype=np.complex128),
    )

    class BorrowedIdentitySideAction:
        def __init__(self, operator: PETSc.Mat) -> None:
            self.operator = operator
            self.apply_count = 0
            self.destroyed = False
            self._side_inverse = SimpleNamespace(
                diagnostics={
                    "apply_count": 0,
                    "total_iterations": 0,
                    "direct_factor_count": 0,
                    "p4_factor_count": 0,
                    "nested_iterative_ksp_count": 0,
                    "destroyed": False,
                }
            )

        def apply(self, source: PETSc.Vec, target: PETSc.Vec) -> None:
            source.copy(target)
            self.apply_count += 1

        def diagnostics(self) -> dict[str, Any]:
            return {
                "apply_count": self.apply_count,
                "direct_factor_count": 0,
                "base_factor_count": 0,
                "p4_factor_count": 0,
                "nested_iterative_ksp_count": 0,
                "destroyed": self.destroyed,
            }

        def destroy(self) -> None:
            self.destroyed = True

    bottom_action = BorrowedIdentitySideAction(bottom_matrix)
    top_action = BorrowedIdentitySideAction(top_matrix)
    side_baseline = {
        "bottom": block_ldu._v13_side_operation_counts(bottom_action),
        "top": block_ldu._v13_side_operation_counts(top_action),
    }
    assert all(isinstance(value, dict) for value in side_baseline.values())

    cap = 85_899_345_920
    reserve = 8_589_934_592
    floor = 412_316_860_416
    rank_pids = comm.allgather(int(os.getpid()))
    external_keys = {
        "bound_fresh_supervisor_sample",
        "tree_cgroup_and_all_mpi_ranks",
        "initial_aggregate_memfree_gate",
        "initial_node1_memfree_gate",
        "aggregate_floor_headroom",
        "node1_phase_headroom",
        "host_floor_headroom",
        "cgroup_ancestor_headroom",
        "case_cap_projection",
        "sample_cost_contract",
    }

    def synthetic_resource_receipt(
        phase: str, report: Mapping[str, Any]
    ) -> dict[str, Any]:
        projection = report["phase_memory_projection"]
        selected_phase = projection["selected_phase"]
        selected = projection["phase_reports"][selected_phase]
        additional = list(selected["additional_bytes_by_rank"])
        temporary = list(selected["additional_temporary_bytes_by_rank"])
        replicated = list(selected["additional_replicated_bytes_by_rank"])
        known = list(selected["known_additional_bytes_by_rank"])
        delta = sum(additional)
        cap_refusal = (
            scenario == "restart64_fresh_cap_refusal"
            and phase == "outer_restart64_workspace"
        )
        fresh = (
            cap - reserve - delta + 1
            if cap_refusal
            else 1_000_000_000
        )
        projected = fresh + delta + reserve
        required = delta + reserve
        gate_status = "refused" if cap_refusal else "pass"
        gate_decision = "stop" if cap_refusal else "continue"
        gate_reasons = (
            ["fresh_B_plus_delta_plus_W_exceeds_case_cap"]
            if cap_refusal
            else []
        )
        root_pid = rank_pids[0]
        sample_sha = "e" * 64
        node0_free = floor + required + 1_000_000_000
        node1_free = 80 * 2**30 + delta
        aggregate_free = node0_free + node1_free
        aggregate_headroom = aggregate_free - floor
        node1_headroom = node1_free - delta
        host_available = floor + required + 1_000_000_000
        host_headroom = host_available - floor
        request_sha = hashlib.sha256(
            json.dumps(
                dict(report), sort_keys=True, separators=(",", ":"), allow_nan=False
            ).encode()
        ).hexdigest()
        payload = {
            "phase": phase,
            "request_sha256": request_sha,
            "resource_B_bytes": fresh,
            "node0_memfree_bytes": node0_free,
            "node1_memfree_bytes": node1_free,
            "aggregate_memfree_bytes": aggregate_free,
            "aggregate_memfree_reserve_bytes": floor,
            "aggregate_floor_headroom_bytes": aggregate_headroom,
            "node1_phase_additional_bytes": delta,
            "node1_headroom_after_phase_additional_bytes": node1_headroom,
            "initial_resource_gate": {
                "required": False,
                "source": "supervisor_resource_preflight",
                "initial_aggregate_memfree_minimum_bytes": 464 * 2**30,
                "initial_node1_memfree_minimum_bytes": 80 * 2**30,
            },
            "host_available_bytes": host_available,
            "host_headroom_after_aggregate_reserve_bytes": host_headroom,
            "sample_root_pid": root_pid,
            "rank_pids": rank_pids,
            "sample_row_sha256": sample_sha,
            "invocation_id": "synthetic-v13-outer-resume",
            "source_sha": "b" * 64,
            "unit": "synthetic-v13-outer-resume.service",
            "cap_bytes": cap,
            "W_policy_reserve_bytes": reserve,
            "floor_bytes": floor,
            "cgroup_limit_state": "max_or_unlimited",
            "cgroup_headroom_bytes": None,
            "selected_memory_phase": selected_phase,
            "selected_memory_phase_payload_bytes": delta,
            "additional_bytes_by_rank": additional,
            "projected_B_plus_delta_plus_W_bytes": projected,
            "status": gate_status,
            "decision": gate_decision,
            "reasons": gate_reasons,
        }
        receipt_sha = hashlib.sha256(
            json.dumps(
                payload, sort_keys=True, separators=(",", ":"), allow_nan=False
            ).encode()
        ).hexdigest()
        return {
            "schema": "task041.v13.modal_builder_admission.v1",
            "phase": phase,
            "request_sha256": request_sha,
            "status": gate_status,
            "decision": gate_decision,
            "reasons": gate_reasons,
            "authority_receipt_payload": payload,
            "authority_receipt_sha256": receipt_sha,
            "root_pid": root_pid,
            "rank_pids": rank_pids,
            "sample_row_sha256": sample_sha,
            "sample_age_seconds": 0.25,
            "fresh_job_authority_bytes": fresh,
            "cap_bytes": cap,
            "W_policy_reserve_bytes": reserve,
            "floor_bytes": floor,
            "node0_memfree_bytes": payload["node0_memfree_bytes"],
            "node1_memfree_bytes": payload["node1_memfree_bytes"],
            "aggregate_memfree_bytes": payload["aggregate_memfree_bytes"],
            "aggregate_memfree_reserve_bytes": payload[
                "aggregate_memfree_reserve_bytes"
            ],
            "aggregate_floor_headroom_bytes": payload[
                "aggregate_floor_headroom_bytes"
            ],
            "node1_phase_additional_bytes": payload[
                "node1_phase_additional_bytes"
            ],
            "node1_headroom_after_phase_additional_bytes": payload[
                "node1_headroom_after_phase_additional_bytes"
            ],
            "host_available_bytes": payload["host_available_bytes"],
            "host_headroom_after_aggregate_reserve_bytes": payload[
                "host_headroom_after_aggregate_reserve_bytes"
            ],
            "initial_resource_gate": dict(payload["initial_resource_gate"]),
            "cgroup_limit_state": "max_or_unlimited",
            "cgroup_headroom_bytes": None,
            "selected_memory_phase": selected_phase,
            "selected_memory_phase_payload_bytes": delta,
            "known_additional_bytes_by_rank": known,
            "additional_bytes_by_rank": additional,
            "additional_temporary_bytes_by_rank": temporary,
            "additional_replicated_bytes_by_rank": replicated,
            "projected_B_plus_delta_plus_W_bytes": projected,
            "external_resource_gates": {
                key: key != "case_cap_projection" or not cap_refusal
                for key in sorted(external_keys)
            },
            "cost_assessment": {
                "scope": "outer_ksp_workspace_admission",
                "status": (
                    "case_cap_refused"
                    if cap_refusal
                    else "workspace_model_valid"
                ),
                "target_restart": int(report["target_restart"]),
                "W_policy_reserve_bytes": reserve,
                "target_is_elapsed_stop": False,
            },
        }

    modal_schur = np.eye(modal_count, dtype=np.complex128)
    if comm.rank == modal_owner:
        owner_schur = modal_schur.copy()
        owner_lu = modal_schur.copy()
        owner_pivots = np.arange(modal_count, dtype=np.int32)
    else:
        owner_schur = owner_lu = owner_pivots = None
    modal_system = block_ldu.Task041V13ConsistentModalSurrogateSystem(
        modal_schur=owner_schur,
        modal_constraint=modal_schur,
        lu=owner_lu,
        pivots=owner_pivots,
        modal_owner=modal_owner,
        comm=comm,
        condition=1.0,
        storage_plan={"fixture": "outer KSP continuation only"},
        build_audit={
            "full_owner_matrix_pages_materialized_before_sample_gate": True,
            "sample_columns_written_directly_to_final_matrix": [0, 1],
            "remaining_columns_applied_once": [],
            "side_solver_entry_zero_supported": True,
        },
        bottom_action=bottom_action,
        top_action=top_action,
        side_operation_baseline=side_baseline,
        fresh_authority_callback=synthetic_resource_receipt,
    )
    context = block_ldu.HybridBlockLduPreconditioner(
        layout,
        bottom_system,
        top_system,
        coupling,
        bottom_action,
        top_action,
        modal_system,
    )

    total = layout.global_size
    full_diagonal = np.ones(total, dtype=np.complex128)
    full_diagonal[layout.map_bottom(np.arange(side_size, dtype=PETSc.IntType))] = (
        bottom_diagonal
    )
    full_diagonal[layout.map_top(np.arange(side_size, dtype=PETSc.IntType))] = (
        top_diagonal
    )
    full_operator_template = layout.create_vector()
    full_operator = _matrix_from_dense(
        full_operator_template,
        full_operator_template,
        np.diag(full_diagonal),
    )
    full_operator_template.destroy()
    owned_matrices.append(full_operator)
    rhs = full_operator.createVecLeft()
    owned_vectors.append(rhs)
    first, last = (int(value) for value in rhs.getOwnershipRange())
    rhs.getArray()[:] = np.asarray(
        [1.0 + 0.0j for _ in range(first, last)], dtype=PETSc.ScalarType
    )
    rhs.assemble()
    rhs_before = np.asarray(rhs.getArray(readonly=True)).copy()
    rhs_global_norm_before = float(rhs.norm())

    def isolated_workspace_report(
        operator: PETSc.Mat,
        report_rhs: PETSc.Vec,
        solution_vector: PETSc.Vec,
        _context: Any,
        report_comm: Any,
        *,
        phase: str,
    ) -> dict[str, Any]:
        rank_rows = report_comm.allgather(
            {
                "rank": int(report_comm.rank),
                "operator_size": [int(value) for value in operator.getSize()],
                "rhs_local_entries": int(report_rhs.getLocalSize()),
                "solution_local_entries": int(solution_vector.getLocalSize()),
            }
        )
        rank_count = int(report_comm.size)
        target_restart = 32 if phase == "outer_restart32_workspace" else 64
        zeros = [0] * rank_count
        phase_name = "test_only_control_workspace_placeholder"
        phase_report = {
            "known_additional_bytes_by_rank": list(zeros),
            "additional_temporary_bytes_by_rank": list(zeros),
            "additional_replicated_bytes_by_rank": list(zeros),
            "additional_bytes_by_rank": list(zeros),
        }
        return {
            "phase": phase,
            "target_restart": target_restart,
            "test_coverage": (
                "control-path-only synthetic resource report; actual Vec layouts "
                "recorded, production builder/PC workspace not qualified"
            ),
            "actual_vec_layouts_by_rank": rank_rows,
            "known_additional_bytes_by_rank": list(zeros),
            "additional_temporary_bytes_by_rank": list(zeros),
            "additional_replicated_bytes_by_rank": list(zeros),
            "phase_memory_projection": {
                "selected_phase": phase_name,
                "selected_phase_payload_bytes": 0,
                "phase_total_bytes": {phase_name: 0},
                "phase_reports": {phase_name: phase_report},
            },
        }

    monkeypatch.setattr(
        block_ldu,
        "_task041_v13_outer_restart_workspace_report",
        isolated_workspace_report,
    )

    def injected_restart_candidate(_history, *, threshold):
        return {
            "rule_id": "synthetic_restart_candidate_for_same_ksp_control_path",
            "clear_restart_loss": True,
            "evidence_status": "synthetic_trigger_injected_not_numerically_qualified",
            "threshold": float(threshold),
        }

    monkeypatch.setattr(
        block_ldu,
        "_task041_v13_outer_restart_loss_evidence",
        injected_restart_candidate,
    )
    if scenario == "finite_stop_after_restart64_control_injection":
        actual_window_evaluator = block_ldu._task041_v13_outer_best_window

        def inject_complete_stalled_window(
            baseline: Mapping[str, float],
            samples: list[Mapping[str, Any]],
            *,
            start_iteration: int,
            end_iteration: int,
            threshold: float,
        ) -> dict[str, Any]:
            record = actual_window_evaluator(
                baseline,
                samples,
                start_iteration=start_iteration,
                end_iteration=end_iteration,
                threshold=threshold,
            )
            if start_iteration >= 48 and record.get("status") == "complete":
                record["stalled"] = True
                record["control_only_decision_injection"] = (
                    "two_complete_post_restart_windows_stalled"
                )
            return record

        monkeypatch.setattr(
            block_ldu,
            "_task041_v13_outer_best_window",
            inject_complete_stalled_window,
        )
    try:
        result = block_ldu.solve_hybrid_block_ldu_iterative(
            full_operator,
            rhs,
            context,
            config=block_ldu.HybridBlockLduIterativeConfig(
                restart=32,
                max_it=(96 if scenario == "finite_stop_after_restart64_control_injection" else 64),
                threshold=5.0e-9,
                ksp_type="fgmres",
            ),
        )
        control = result.inventory["task041_v13_outer_control"]
        decision = control["restart64_decision"]
        assert control["initial_restart"] == 32
        assert result.iterations == control["total_iterations"]
        assert result.converged_reason == control["final_reason"]
        total_limit = (
            96
            if scenario == "finite_stop_after_restart64_control_injection"
            else 64
        )
        assert 48 < result.iterations <= total_limit
        assert decision["candidate"]["observed_at_iteration"] == 48
        assert decision["candidate"]["evidence"]["evidence_status"] == (
            "synthetic_trigger_injected_not_numerically_qualified"
        )
        if scenario == "restart64_fresh_cap_refusal":
            assert decision["status"] == "restart64_refused_continue_restart32"
            assert decision["authority_status"] == "refused"
            assert decision["restart_before"] == 32
            assert decision["restart_selected"] is False
            refusal_payload = control["restart64_authority"][
                "authority_receipt_payload"
            ]
            assert refusal_payload["status"] == "refused"
            assert refusal_payload["decision"] == "stop"
            assert refusal_payload["cap_bytes"] == cap
            assert refusal_payload["projected_B_plus_delta_plus_W_bytes"] == (
                cap + 1
            )
            assert (
                refusal_payload["resource_B_bytes"]
                + refusal_payload["selected_memory_phase_payload_bytes"]
                + refusal_payload["W_policy_reserve_bytes"]
                == refusal_payload["projected_B_plus_delta_plus_W_bytes"]
            )
            assert refusal_payload["reasons"] == [
                "fresh_B_plus_delta_plus_W_exceeds_case_cap"
            ]
            assert control["restart64_authority"]["decision"] == "stop"
            assert control["restart64_authority"]["external_resource_gates"][
                "case_cap_projection"
            ] is False
            assert control["restart64_trial_count"] == 0
            assert control["final_restart"] == 32
            assert control["restart_history"][-1]["reason"] == (
                "restart64_fresh_authority_refused_continue_same_ksp_at_48"
            )
        else:
            assert decision["status"] == "restart64_selected_once"
            assert control["restart64_trial_count"] == 1
            assert control["final_restart"] == 64
        resume_rows = decision["same_ksp_nonzero_x_resume"]
        assert len(resume_rows) == comm.size
        assert all(
            row["same_ksp_object_retained"]
            and row["same_pc_context_retained"]
            and row["initial_guess_nonzero_requested"]
            and row["solution_local_sha256_before"]
            == row["solution_local_sha256_after_setup"]
            and row["rhs_local_sha256_before"]
            == row["rhs_local_sha256_before_resume"]
            and row["solution_local_norm_before_resume"] > 0.0
            and row["initial_guess_nonzero_readback"] is True
            and row["remaining_total_iterations_before_resume"]
            == total_limit - 48
            for row in resume_rows
        )
        resume_work = decision["same_ksp_nonzero_x_resume_work"]
        assert resume_work["iterations_after_resume"] == result.iterations
        assert resume_work["local_iteration_count_after_resume"] == (
            result.iterations - 48
        )
        assert 0 < resume_work["local_iteration_count_after_resume"] <= (
            total_limit - 48
        )
        assert resume_work["max_it_remaining_after_resume"] == (
            total_limit - result.iterations
        )
        assert resume_work["elapsed_seconds_after_resume"] > 0.0
        local_resume_row = resume_rows[comm.rank]
        assert all(
            resume_work[after_key] >= local_resume_row[before_key]
            for after_key, before_key in (
                (
                    "cumulative_pc_apply_count_after_resume",
                    "cumulative_pc_apply_count_before_resume",
                ),
                (
                    "cumulative_bottom_action_apply_count_after_resume",
                    "cumulative_bottom_action_apply_count_before_resume",
                ),
                (
                    "cumulative_top_action_apply_count_after_resume",
                    "cumulative_top_action_apply_count_before_resume",
                ),
            )
        )
        independent_residual = rhs.duplicate()
        try:
            full_operator.mult(result.solution, independent_residual)
            independent_residual.scale(PETSc.ScalarType(-1.0))
            independent_residual.axpy(PETSc.ScalarType(1.0), rhs)
            independent_relative = float(independent_residual.norm()) / max(
                rhs_global_norm_before, np.finfo(float).tiny
            )
            assert np.isfinite(independent_relative)
            assert np.isclose(
                independent_relative,
                result.postsolve_audit["global_true_relative_residual"],
                rtol=1.0e-10,
                atol=1.0e-14,
            )
        finally:
            independent_residual.destroy()
        assert np.array_equal(
            np.asarray(rhs.getArray(readonly=True)), rhs_before
        )
        # The V13 LDU context owns and destroys each action adapter (and its
        # adapter work vectors).  These identity doubles hold a borrowed
        # operator/inverse-state placeholder but no P4 handle, so this only
        # checks wrapper cleanup and that the borrowed fixture objects remain
        # usable; it does not qualify production P4 lifetime.
        assert bottom_action.destroyed is True
        assert top_action.destroyed is True
        assert bottom_action.operator.getSize() == (side_size, side_size)
        assert top_action.operator.getSize() == (side_size, side_size)
        assert bottom_action._side_inverse.diagnostics["destroyed"] is False
        assert top_action._side_inverse.diagnostics["destroyed"] is False
        assert decision["same_ksp_nonzero_x_resume_work"][
            "cumulative_pc_apply_count_after_resume"
        ] == control["cumulative_pc_apply_count"]
        assert decision["same_ksp_nonzero_x_resume_work"][
            "cumulative_bottom_action_apply_count_after_resume"
        ] == control["cumulative_bottom_action_apply_count"]
        assert decision["same_ksp_nonzero_x_resume_work"][
            "cumulative_top_action_apply_count_after_resume"
        ] == control["cumulative_top_action_apply_count"]
        if scenario == "finite_stop_after_restart64_control_injection":
            finite_stop = control["finite_stop"]
            assert finite_stop["schema"] == "task041.v13.outer_finite_stop.v1"
            assert finite_stop["status"] == (
                "two_consecutive_complete_16_step_windows_stalled"
            )
            assert finite_stop["iterations_at_stop"] == 80
            assert finite_stop["configured_max_it"] == 96
            assert finite_stop["max_it_reached"] is False
            assert finite_stop["converged"] is False
            assert finite_stop["reason_code"] == int(
                PETSc.KSP.ConvergedReason.DIVERGED_MAX_IT
            )
            assert finite_stop["reason_code"] < 0
            assert result.converged_reason == finite_stop["reason_code"]
            assert result.iterations == 80
            assert result.postsolve_audit["pass"] is False
            assert finite_stop["current_trusted_solution_retained"] is True
            assert finite_stop["original_rhs_unchanged"] is True
            assert finite_stop["original_rhs_norm_at_solve_entry"] == pytest.approx(
                rhs_global_norm_before
            )
            retained_rows = finite_stop["rank_local_solution_rhs_binding"][
                "records"
            ]
            assert len(retained_rows) == comm.size
            assert [row["rank"] for row in retained_rows] == list(range(comm.size))
            assert all(
                row["solution_finite"] is True
                and row["rhs_unchanged"] is True
                and len(row["solution_local_sha256"]) == 64
                and row["rhs_local_sha256_before"]
                == row["rhs_local_sha256_after"]
                for row in retained_rows
            )
            assert finite_stop["post_stop_true_residuals"] == pytest.approx(
                {
                    key: result.postsolve_audit[key]
                    for key in (
                        "reported_relative_residual",
                        "global_true_relative_residual",
                        "bottom_true_relative_residual",
                        "top_true_relative_residual",
                        "modal_true_relative_residual",
                    )
                }
            )
            assert len(finite_stop["windows"]) == 2
            assert all(
                window["control_only_decision_injection"]
                == "two_complete_post_restart_windows_stalled"
                for window in finite_stop["windows"]
            )
            assert control["total_wall_seconds"] > 0.0
            assert control["cumulative_pc_apply_count"] == result.inventory[
                "pc_apply_count"
            ]
            assert result.inventory["pc_apply_count"] > 0
    finally:
        if result is not None:
            result.destroy()
        elif context is not None and not context._destroyed:
            context.destroy()
        for vector in owned_vectors:
            vector.destroy()
        for matrix in owned_matrices:
            matrix.destroy()


def _exercise_v13_unmocked_builder_owner_lu_and_original_modal_row_math(
    monkeypatch,
    tmp_path,
    *,
    inject_owner_writer_failure: bool = False,
) -> None:
    """Run the tiny V13 build, owner LU, full PC, and independent A modal row."""

    from benchmarks import task041_exact_side_workflow as exact_side
    from src.io.input_validation import (
        TASK041_BALH_CELL_CONDENSED_RESERVE_BYTES,
        TASK041_BALH_W0P7NM_P6_PILOT_HARD_MEMORY_BYTES,
        TASK041_BALH_W0P7NM_P6_PILOT_WARNING_MEMORY_BYTES,
    )

    comm = MPI.COMM_WORLD
    side_size = 6
    modal_per_side = 6
    internal_count = 2 * modal_per_side
    side_fixture = _fixed_h6_side_block_fixture()
    owned_matrices: list[PETSc.Mat] = []
    side_actions = []
    system = context = None
    original_operator = source = target = None
    original_operator_contexts: list[HybridBlockOperator] = []
    outer_workspace_rhs = outer_workspace_solution = None

    def dense_matrix(
        rows: int,
        columns: int,
        entries: Mapping[tuple[int, int], complex],
        *,
        local_rows: int | None = None,
        local_columns: int | None = None,
    ) -> PETSc.Mat:
        row = PETSc.Vec().createMPI(
            (rows // comm.size if local_rows is None else local_rows, rows),
            comm=comm,
        )
        column = PETSc.Vec().createMPI(
            (
                columns // comm.size if local_columns is None else local_columns,
                columns,
            ),
            comm=comm,
        )
        values = np.zeros((rows, columns), dtype=np.complex128)
        for (row_index, column_index), value in entries.items():
            values[row_index, column_index] = value
        matrix = _matrix_from_dense(row, column, values)
        row.destroy()
        column.destroy()
        owned_matrices.append(matrix)
        return matrix

    # The real V13 builder's workspace inventory reads these P4 layout
    # descriptors.  This fixture deliberately uses _IdentityP4 rather than a
    # cell-condensed P4 factor, so provide only matching full/coarse identity
    # matrices and an empty recovery-map list; no FE cells or P4 solve audit is
    # being modeled here.  The full matrix aliases the existing _FullAction
    # matrix, which remains owned by the side fixture.  Each coarse matrix is
    # owned by this test's owned_matrices cleanup below.
    for side in ("bottom", "top"):
        side_layout = side_fixture[side].static_condensation.condensed
        full_rows = int(side_layout.full_rows)
        coarse_rows = int(side_layout.active_rows)
        p4_factor = side_fixture[f"{side}_owned"]["p4_factor"]
        full_action = side_fixture[f"{side}_owned"]["full_action"]
        full_matrix = full_action.matrix
        assert int(p4_factor.size) == full_rows
        assert full_matrix.getSize() == (full_rows, full_rows)
        assert full_matrix.getLocalSize() == (
            full_rows // comm.size,
            full_rows // comm.size,
        )
        coarse_matrix = dense_matrix(
            coarse_rows,
            coarse_rows,
            {(index, index): 1.0 for index in range(coarse_rows)},
        )
        assert coarse_matrix.getSize() == (coarse_rows, coarse_rows)
        assert coarse_matrix.getLocalSize() == (
            int(side_layout.owned_active_rows),
            int(side_layout.owned_active_rows),
        )
        p4_factor.physical_action.matrix = full_matrix
        p4_factor.inverse = SimpleNamespace(
            condensed=SimpleNamespace(
                matrix=coarse_matrix,
                cell_recovery_maps=(),
            )
        )
        assert p4_factor.physical_action.matrix is full_action.matrix
        assert p4_factor.inverse.condensed.matrix is coarse_matrix
        assert p4_factor.inverse.condensed.cell_recovery_maps == ()

    class CountingAction:
        def __init__(self, operator: PETSc.Mat, side_inverse: SideBalancedInverse):
            self.operator = operator
            self._side_inverse = side_inverse
            self.audit = {"apply_count": 0, "destroyed": False}

        def apply(self, rhs: PETSc.Vec, result: PETSc.Vec) -> None:
            self.operator.mult(rhs, result)
            self.audit["apply_count"] += 1

        def diagnostics(self) -> dict[str, int]:
            return {
                "apply_count": int(self.audit["apply_count"]),
                "direct_factor_count": 0,
            }

        def destroy(self) -> None:
            self.audit["destroyed"] = True

    bottom_operator = dense_matrix(
        side_size,
        side_size,
        {
            (0, 0): 1.0 + 0.2j,
            (0, 1): 0.3 - 0.1j,
            (1, 0): -0.2 + 0.15j,
            (1, 1): 1.4 - 0.1j,
            (2, 2): 0.9 + 0.3j,
            (3, 3): 1.2 - 0.25j,
            (4, 4): 0.85 + 0.12j,
            (5, 5): 1.05 - 0.18j,
        },
    )
    top_operator = dense_matrix(
        side_size,
        side_size,
        {
            (0, 0): 1.1 - 0.1j,
            (0, 1): -0.25 + 0.2j,
            (1, 0): 0.4 + 0.05j,
            (1, 1): 1.3 + 0.15j,
            (2, 2): 1.0 - 0.2j,
            (3, 3): 0.8 + 0.1j,
            (4, 4): 1.15 + 0.08j,
            (5, 5): 0.92 - 0.14j,
        },
    )
    bottom_B = dense_matrix(
        side_size,
        side_size,
        {
            (0, 0): 0.6 - 0.2j,
            (0, 1): 0.15 + 0.3j,
            (1, 0): -0.1 + 0.05j,
            (1, 1): 0.8 + 0.1j,
            (2, 2): 1.1 + 0.05j,
            (3, 3): 0.7 - 0.3j,
            (4, 4): 0.9 + 0.16j,
            (5, 5): 1.02 - 0.11j,
        },
    )
    top_B = dense_matrix(
        side_size,
        side_size,
        {
            (0, 0): 0.75 + 0.1j,
            (0, 1): -0.2 + 0.25j,
            (1, 0): 0.12 - 0.08j,
            (1, 1): 0.65 - 0.15j,
            (2, 2): 1.2 + 0.2j,
            (3, 3): 0.95 - 0.05j,
            (4, 4): 0.88 + 0.2j,
            (5, 5): 1.08 - 0.09j,
        },
    )
    # The fixed B actions are complex non-Hermitian and intentionally differ
    # from the exact side-operator inverses.
    exact_bottom_inverse = np.linalg.inv(_gather_matrix(bottom_operator))
    exact_top_inverse = np.linalg.inv(_gather_matrix(top_operator))
    assert not np.allclose(_gather_matrix(bottom_B), exact_bottom_inverse)
    assert not np.allclose(_gather_matrix(top_B), exact_top_inverse)
    assert not np.allclose(
        _gather_matrix(bottom_B), _gather_matrix(bottom_B).conj().T
    )
    assert not np.allclose(_gather_matrix(top_B), _gather_matrix(top_B).conj().T)
    bottom_action = CountingAction(bottom_B, side_fixture["bottom_inverse"])
    top_action = CountingAction(top_B, side_fixture["top_inverse"])
    side_actions = [bottom_action, top_action]
    projection_entries = {
        (index, index): 1.0 + 0.1j * (index + 1)
        for index in range(modal_per_side)
    }
    projection_entries[(0, 1)] = -0.2 + 0.3j
    traction_entries = {
        (index, index): 0.8 + 0.05j * (index + 1)
        for index in range(modal_per_side)
    }
    traction_entries[(1, 0)] = 0.1 - 0.25j
    modal_owner_local = modal_per_side if comm.rank == comm.size - 1 else 0
    bottom_projection = dense_matrix(
        modal_per_side,
        side_size,
        projection_entries,
        local_rows=modal_owner_local,
        local_columns=side_size // comm.size,
    )
    top_projection = dense_matrix(
        modal_per_side,
        side_size,
        {(row, col): value * (0.9 - 0.1j) for (row, col), value in projection_entries.items()},
        local_rows=modal_owner_local,
        local_columns=side_size // comm.size,
    )
    bottom_positive = dense_matrix(
        side_size,
        modal_per_side,
        traction_entries,
        local_rows=side_size // comm.size,
        local_columns=modal_owner_local,
    )
    bottom_negative = dense_matrix(
        side_size,
        modal_per_side,
        {(row, col): value * (0.7 + 0.2j) for (row, col), value in traction_entries.items()},
        local_rows=side_size // comm.size,
        local_columns=modal_owner_local,
    )
    top_positive = dense_matrix(
        side_size,
        modal_per_side,
        {(row, col): value * (0.6 - 0.15j) for (row, col), value in traction_entries.items()},
        local_rows=side_size // comm.size,
        local_columns=modal_owner_local,
    )
    top_negative = dense_matrix(
        side_size,
        modal_per_side,
        {(row, col): value * (1.1 + 0.05j) for (row, col), value in traction_entries.items()},
        local_rows=side_size // comm.size,
        local_columns=modal_owner_local,
    )
    for matrix in (
        bottom_operator,
        top_operator,
        bottom_B,
        top_B,
        bottom_projection,
        top_projection,
        bottom_positive,
        bottom_negative,
        top_positive,
        top_negative,
    ):
        matrix.setOption(PETSc.Mat.Option.SYMMETRIC, False)
    blocks = {
        "bottom": SimpleNamespace(
            projection=bottom_projection,
            positive_traction=bottom_positive,
            negative_traction=bottom_negative,
            positive_interior_correction=(
                0.013 + 0.004j
            ) * np.eye(modal_per_side, dtype=np.complex128),
            negative_interior_correction=(
                0.002 - 0.003j
            ) * np.eye(modal_per_side, dtype=np.complex128),
            modal_rhs_correction=np.zeros(modal_per_side, dtype=np.complex128),
        ),
        "top": SimpleNamespace(
            projection=top_projection,
            positive_traction=top_positive,
            negative_traction=top_negative,
            positive_interior_correction=(
                -0.003 + 0.002j
            ) * np.eye(modal_per_side, dtype=np.complex128),
            negative_interior_correction=(
                0.009 + 0.001j
            ) * np.eye(modal_per_side, dtype=np.complex128),
            modal_rhs_correction=np.zeros(modal_per_side, dtype=np.complex128),
        ),
    }
    coupling = SimpleNamespace(
        mode_count_per_direction=modal_per_side,
        internal_equation_count=internal_count,
        bottom=blocks["bottom"],
        top=blocks["top"],
        propagation=SimpleNamespace(
            forward=SimpleNamespace(
                factors=np.asarray([1.0 + 0.1j] * modal_per_side)
            ),
            backward=SimpleNamespace(
                factors=np.asarray([0.9 - 0.05j] * modal_per_side)
            ),
        ),
        negative_trace_to_positive=np.asarray(
            np.diag([0.95 + 0.02j] * modal_per_side), dtype=np.complex128
        ),
    )
    sample_offsets = [0, 1, modal_per_side // 2, modal_per_side - 1]
    columns = [
        *sample_offsets,
        *(modal_per_side + offset for offset in sample_offsets),
    ]
    roles = {
        str(column): [
            "head" if column in {0, modal_per_side, 2 * modal_per_side - 1} else "interior",
            (
                "bottom_positive_unattenuated"
                if column < modal_per_side
                else "top_negative_unattenuated"
            ),
        ]
        for column in columns
    }
    contract = {
        "columns": columns,
        "mode_count_per_direction": modal_per_side,
        "roles": roles,
    }
    contract_sha = hashlib.sha256(
        json.dumps(contract, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    fresh_reports = []
    fresh_responses = []
    markers = []
    authority_request_hashes = []
    rank_pids = comm.allgather(int(os.getpid()))
    sample_root_pid = 913579
    supervisor_binding = {
        "invocation_id": "v13-builder-fixture-invocation",
        "source_sha": "b" * 64,
        "unit": "v13-builder-fixture.service",
        "launch_manifest_sha256": "c" * 64,
        "supervisor_root_pid": sample_root_pid,
    }
    monitor_sample = {
        **supervisor_binding,
        "sample_root_pid": sample_root_pid,
        "file_age_seconds": 0.25,
        "phase": "public_command",
        "sample_role": "phase_running",
        "sample_row_sha256": "d" * 64,
    }
    raw_sample = {
        "process_tree": {
            "all_status_readable": True,
            "rss_bytes": 1_000_000,
            "pids": [sample_root_pid, *rank_pids],
        },
        "job_cgroup": {
            "dedicated_job_cgroup": True,
            "memory_current_bytes": 2_000_000,
            "ancestor_hard_limit_state": "max_or_unlimited",
            "ancestor_memory_headroom_bytes": None,
        },
        "host_memory": {"mem_available_bytes": 1_000_000_000_000},
        "memory_authority_bytes": 2_000_000,
    }
    monkeypatch.setattr(
        exact_side,
        "_task041_latest_supervisor_memory_sample",
        lambda _binding: dict(monitor_sample),
    )
    monkeypatch.setattr(exact_side, "_resource_snapshot", lambda _pid: raw_sample)
    monkeypatch.setattr(
        exact_side, "_task041_node0_memfree_bytes", lambda: 1_000_000_000_000
    )
    node_free_by_id = {0: 1_000_000_000_000, 1: 1_000_000_000_000}
    monkeypatch.setattr(
        exact_side,
        "_task041_node_memfree_bytes",
        lambda node: node_free_by_id[int(node)],
    )
    v13_limits = {
        "hard_memory_bytes": TASK041_BALH_W0P7NM_P6_PILOT_HARD_MEMORY_BYTES,
        "process_tree_rss_warning_bytes": TASK041_BALH_W0P7NM_P6_PILOT_WARNING_MEMORY_BYTES,
        "min_memavailable_bytes": TASK041_BALH_CELL_CONDENSED_RESERVE_BYTES,
    }

    def authority(phase, report):
        fresh_reports.append((phase, dict(report)))
        request_hash = hashlib.sha256(
            json.dumps(
                report,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode()
        ).hexdigest()
        authority_request_hashes.append(request_hash)
        request_hash_rows = comm.allgather(request_hash)
        assert len(set(request_hash_rows)) == 1
        result = exact_side._task041_v13_fresh_authority_callback(
            phase,
            report,
            comm=comm,
            supervisor_memory_binding=supervisor_binding,
            limits=v13_limits,
        )
        fresh_responses.append(result)
        return result

    def marker(name, detail):
        markers.append((name, dict(detail)))

    from pathlib import Path

    evidence_root_path = (
        str(Path(tmp_path) / "v15-modal-evidence")
        if comm.rank == 0
        else None
    )
    evidence_root = Path(comm.bcast(evidence_root_path, root=0))
    owner_writer_failure_armed = False
    packet_manifest_sha256 = hashlib.sha256(
        b"test350 synthetic packet identity; not a registered FE packet"
    ).hexdigest()

    def write_modal_snapshot(payload: Mapping[str, Any]) -> Mapping[str, Any]:
        nonlocal owner_writer_failure_armed
        kind = payload.get("snapshot_kind")
        if (
            inject_owner_writer_failure
            and comm.size == 2
            and comm.rank == comm.size - 1
            and owner_writer_failure_armed
            and kind == "v15_terminal_numeric_reject"
        ):
            owner_writer_failure_armed = False
            raise OSError("injected real tiny owner snapshot failure")
        if kind == "v15_capture_failure_rank":
            return exact_side._write_task041_v13_capture_failure_rank(
                evidence_root, payload, rank=int(comm.rank)
            )
        if kind == "v15_terminal_rank_vectors":
            return exact_side._write_task041_v13_terminal_rank_vectors(
                evidence_root, payload, rank=int(comm.rank)
            )
        return exact_side._write_task041_v13_modal_evidence_snapshot(
            evidence_root,
            payload,
            source_sha=supervisor_binding["source_sha"],
            identity={
                "test": "test350 synthetic original-A MatPython capture",
                "invocation_id": supervisor_binding["invocation_id"],
                "rank": int(comm.rank),
            },
            packet_manifest_sha256=packet_manifest_sha256,
            consumer_binding={"scope": "synthetic_contract_only_not_FE"},
        )

    bottom_D = _gather_matrix(bottom_operator)
    top_D = _gather_matrix(top_operator)
    bottom_B_dense = _gather_matrix(bottom_B)
    top_B_dense = _gather_matrix(top_B)
    bottom_projection_dense = _gather_matrix(bottom_projection)
    top_projection_dense = _gather_matrix(top_projection)
    bottom_positive_dense = _gather_matrix(bottom_positive)
    bottom_negative_dense = _gather_matrix(bottom_negative)
    top_positive_dense = _gather_matrix(top_positive)
    top_negative_dense = _gather_matrix(top_negative)
    forward = np.asarray(coupling.propagation.forward.factors, dtype=np.complex128)
    backward = np.asarray(coupling.propagation.backward.factors, dtype=np.complex128)
    negative_map = np.asarray(
        coupling.negative_trace_to_positive, dtype=np.complex128
    )
    identity = np.eye(modal_per_side, dtype=np.complex128)
    bottom_correction = np.hstack(
        (
            coupling.bottom.positive_interior_correction,
            coupling.bottom.negative_interior_correction @ np.diag(backward),
        )
    )
    top_correction = np.hstack(
        (
            coupling.top.positive_interior_correction @ np.diag(forward),
            coupling.top.negative_interior_correction,
        )
    )
    # This is the original A modal block written from its defining blocks,
    # independently of the production helper that builds C for S_B.
    original_C = np.block(
        [
            [-identity, -(negative_map @ np.diag(backward))],
            [-np.diag(forward), -negative_map],
        ]
    ) + np.vstack((bottom_correction, top_correction))
    np.testing.assert_allclose(
        internal_modal_constraint_matrix(coupling), original_C, rtol=0.0, atol=0.0
    )
    original_G_bottom = np.hstack(
        (bottom_positive_dense, bottom_negative_dense @ np.diag(backward))
    )
    original_G_top = np.hstack(
        (top_positive_dense @ np.diag(forward), top_negative_dense)
    )

    def original_operator_for(layout: HybridAugmentedLayout) -> PETSc.Mat:
        """Use the production MatPython original-A context on tiny matrices."""

        bottom_system = SimpleNamespace(
            A=bottom_operator,
            global_size=side_size,
            local_mesh=SimpleNamespace(mesh=SimpleNamespace(comm=comm)),
        )
        top_system = SimpleNamespace(
            A=top_operator,
            global_size=side_size,
            local_mesh=SimpleNamespace(mesh=SimpleNamespace(comm=comm)),
        )
        coupling.internal_unknown_count = internal_count
        context = HybridBlockOperator(bottom_system, top_system, coupling)
        original_operator_contexts.append(context)
        matrix = PETSc.Mat().createPython(
            ((layout.local_size, layout.global_size),) * 2,
            context=context,
            comm=comm,
        )
        matrix.setUp()
        owned_matrices.append(matrix)
        return matrix

    def assert_full_original_action(
        layout: HybridAugmentedLayout,
        operator: PETSc.Mat,
        value: PETSc.Vec,
    ) -> None:
        bottom_indices = layout.map_bottom(
            np.arange(side_size, dtype=PETSc.IntType)
        )
        top_indices = layout.map_top(np.arange(side_size, dtype=PETSc.IntType))
        modal_indices = layout.map_modal(
            np.arange(internal_count, dtype=PETSc.IntType)
        )
        values = _gather_vector(value)
        expected = np.zeros(layout.global_size, dtype=np.complex128)
        expected[bottom_indices] = (
            bottom_D @ values[bottom_indices]
            + original_G_bottom @ values[modal_indices]
        )
        expected[top_indices] = (
            top_D @ values[top_indices]
            + original_G_top @ values[modal_indices]
        )
        expected[modal_indices] = (
            np.concatenate(
                (
                    bottom_projection_dense @ values[bottom_indices],
                    top_projection_dense @ values[top_indices],
                )
            )
            + original_C @ values[modal_indices]
        )
        action = operator.createVecLeft()
        try:
            operator.mult(value, action)
            np.testing.assert_allclose(
                _gather_vector(action), expected, rtol=1.0e-13, atol=1.0e-13
            )
        finally:
            action.destroy()

    layout = HybridAugmentedLayout.build(
        SimpleNamespace(
            A=bottom_operator,
            global_size=side_size,
            local_mesh=SimpleNamespace(mesh=SimpleNamespace(comm=comm)),
        ),
        SimpleNamespace(
            A=top_operator,
            global_size=side_size,
            local_mesh=SimpleNamespace(mesh=SimpleNamespace(comm=comm)),
        ),
        internal_count,
    )
    try:
        system = block_ldu.build_task041_v13_consistent_modal_surrogate(
            coupling,
            bottom_action,
            top_action,
            modal_owner=comm.size - 1,
            sampled_columns=columns,
            sampled_column_roles=roles,
            sampled_column_contract_sha256=contract_sha,
            original_augmented_local_size=layout.local_size,
            fresh_authority_callback=authority,
            marker_callback=marker,
            snapshot_callback=write_modal_snapshot,
        )
        assert (system.lu is not None) == (comm.rank == comm.size - 1)
        assert (system.pivots is not None) == (comm.rank == comm.size - 1)
        audit = system.build_audit
        assert audit["sample_columns_written_directly_to_final_matrix"] == columns
        assert audit["full_owner_matrix_pages_materialized_before_sample_gate"] is True
        remaining_columns = sorted(set(range(internal_count)) - set(columns))
        assert len(columns) == 8
        assert audit["remaining_columns_applied_once"] == remaining_columns
        assert len(remaining_columns) == 4
        assert audit["assembly_B_apply_count_by_side"] == {
            "bottom": internal_count,
            "top": internal_count,
        }
        assert audit["independent_action_validation"]["B_apply_count_by_side"] == {
            "bottom": 7,
            "top": 7,
        }
        assert audit["independent_action_validation"]["inputs"] == [
            "x",
            "y",
            "complex_homogeneity",
            "additivity",
            "repeat_x",
            "zero",
            "near_zero",
        ]
        assert audit["independent_action_validation"]["covers_all_modal_components"] is True
        assert audit["independent_action_validation"][
            "uses_validated_constraint_storage"
        ] is True
        assert len(audit["independent_action_validation"]["relative_errors"]) == 7
        phase_snapshots = audit["actual_work_phase_snapshots"]
        assert tuple(phase_snapshots) == (
            "before_build",
            "after_eight_columns",
            "after_all_columns",
            "after_independent_validation",
        )
        phase_apply_counts = {
            "before_build": 0,
            "after_eight_columns": 8,
            "after_all_columns": internal_count,
            "after_independent_validation": internal_count + 7,
        }
        for phase, expected_count in phase_apply_counts.items():
            phase_record = phase_snapshots[phase]
            assert phase_record["rank_count"] == comm.size
            assert len(phase_record["rank_rows"]) == comm.size
            for row in phase_record["rank_rows"]:
                assert row["actions"]["bottom"]["action_apply_count"] == expected_count
                assert row["actions"]["top"]["action_apply_count"] == expected_count
                # This fixture substitutes only the action implementation; it
                # has no P4 solver audit and must not invent one.
                assert row["actions"]["bottom"][
                    "shared_side_inverse_callback_counts"
                ] is None
                assert row["actions"]["top"][
                    "shared_side_inverse_callback_counts"
                ] is None
                assert row["actions"]["bottom"][
                    "fixed_q_actual_work_cumulative"
                ] is None
                assert row["actions"]["top"][
                    "fixed_q_actual_work_cumulative"
                ] is None
        for phase, expected_delta in (
            ("after_eight_columns", 8),
            ("after_all_columns", len(remaining_columns)),
            ("after_independent_validation", 7),
        ):
            for row in phase_snapshots[phase]["rank_rows"]:
                deltas = row["action_work_delta_since_previous_phase"]
                assert deltas["bottom"]["action_apply_count"] == expected_delta
                assert deltas["top"]["action_apply_count"] == expected_delta
        phase_markers = {name: detail for name, detail in markers}
        assert phase_markers["v13_modal_sample8_complete"][
            "sample_column_count"
        ] == 8
        complete_marker = phase_markers["v13_modal_schur_columns_complete"]
        assert complete_marker["phase"] == "after_all_columns"
        assert complete_marker["rank_count"] == comm.size
        complete_rows = complete_marker["rank_rows"]
        assert len(complete_rows) == comm.size
        assert [row["rank"] for row in complete_rows] == list(range(comm.size))
        for row in complete_rows:
            assert row["completed_column_count"] == internal_count
            assert row["remaining_column_count"] == 0
        assert all(
            record["input_unchanged"]
            and record["finite"]
            and record["relative_error_vs_owner_S_B"] <= 1.0e-10
            for record in audit["independent_action_validation"]["input_records"]
        )
        for record in audit["independent_action_validation"]["input_records"]:
            if record["algebra_identity_applicable"]:
                absolute = record["algebra_identity_absolute_error"]
                relative = record["algebra_identity_relative_error"]
                assert absolute is not None and relative is not None
                assert np.isfinite(absolute) and np.isfinite(relative)
            else:
                assert record["algebra_identity_absolute_error"] is None
                assert record["algebra_identity_relative_error"] is None
        assert set(
            audit["independent_action_validation"]["complex_linearity_errors"]
        ) == {
            "complex_homogeneity",
            "additivity",
            "repeat_x",
            "zero",
            "near_zero",
        }
        expected_schur = original_C - np.vstack(
            (
                bottom_projection_dense @ bottom_B_dense @ original_G_bottom,
                top_projection_dense @ top_B_dense @ original_G_top,
            )
        )
        if comm.rank == comm.size - 1:
            np.testing.assert_allclose(
                system.modal_schur, expected_schur, rtol=1.0e-12, atol=1.0e-12
            )
        assert [phase for phase, _ in fresh_reports] == [
            "before_dense_allocation",
            "after_eight_columns",
        ]
        reports_by_rank = comm.allgather(fresh_reports)
        assert all(rows == reports_by_rank[0] for rows in reports_by_rank)
        assert len(set(authority_request_hashes)) == 2
        for response in fresh_responses:
            receipt_payload = response["authority_receipt_payload"]
            assert hashlib.sha256(
                json.dumps(
                    receipt_payload,
                    sort_keys=True,
                    separators=(",", ":"),
                    allow_nan=False,
                ).encode()
            ).hexdigest() == response["authority_receipt_sha256"]
        sample_report = fresh_reports[1][1]
        malformed_rank_report = copy.deepcopy(sample_report)
        if comm.rank == 0:
            malformed_rank_report["rank_local_nonfinite_probe"] = float("nan")
        malformed_report_error = None
        try:
            exact_side._task041_v13_fresh_authority_callback(
                "after_eight_columns",
                malformed_rank_report,
                comm=comm,
                supervisor_memory_binding=supervisor_binding,
                limits=v13_limits,
            )
        except Exception as exc:  # noqa: BLE001 - each rank records the same refusal
            malformed_report_error = f"{type(exc).__name__}: {exc}"
        malformed_report_errors = comm.allgather(malformed_report_error)
        assert len(set(malformed_report_errors)) == 1
        assert isinstance(malformed_report_errors[0], str)
        assert "V13 authority report is unbindable" in malformed_report_errors[0]
        assert "rank 0" in malformed_report_errors[0]
        assert sample_report["sample_column_count"] == 8
        assert sample_report["remaining_column_count"] == len(remaining_columns)
        assert all(
            row["bottom_B_apply_count"] == 8
            and row["top_B_apply_count"] == 8
            for row in sample_report["rank_local_sample_work"]
        )
        assert sample_report["assembly_elapsed_seconds_max_rank"] == max(
            row["elapsed_seconds"]
            for row in sample_report["assembly_elapsed_seconds_by_rank"]
        )
        assert len(sample_report["assembly_elapsed_seconds_by_rank"]) == comm.size
        assert sample_report["phase"] == "after_eight_columns"
        assert sample_report["remaining_projected_work_scopes"] == {
            "remaining_matrix_columns": len(remaining_columns),
            "independent_full_complex_action_checks": 7,
        }
        assert sample_report["remaining_projected_B_apply_count_by_side"] == {
            "bottom": len(remaining_columns) + 7,
            "top": len(remaining_columns) + 7,
        }
        assert sample_report["full_run_cost_target_seconds"] == 172800
        assert sample_report["full_run_cost_target_semantics"] == (
            "planning_target_only_no_elapsed_stop"
        )
        assert all(
            response["status"] == "pass"
            and response["external_resource_gates"]["sample_cost_contract"] is True
            and response["cost_assessment"]["target_is_elapsed_stop"] is False
            for response in fresh_responses
        )
        assert fresh_responses[0]["cost_assessment"]["status"] == "not_yet_sampled"
        assert fresh_responses[0]["cost_assessment"]["decision"] == (
            "continue_to_eight_column_sample_if_resource_gates_pass"
        )
        assert fresh_responses[1]["cost_assessment"]["status"] == (
            "sample_projection_valid"
        )
        assert fresh_responses[1]["cost_assessment"]["decision"] == (
            "continue_if_resource_gates_pass"
        )
        assert any(
            value > 0
            for value in sample_report["workspace_inventory"][
                "additional_temporary_petcs_and_cell_numpy_bytes_by_rank"
            ]
        )
        assert any(
            value > 0
            for value in sample_report["workspace_inventory"][
                "additional_replicated_numpy_bytes_by_rank"
            ]
        )
        bad_cost_report = copy.deepcopy(sample_report)
        bad_cost_report["remaining_projected_B_apply_count_by_side"]["top"] -= 1
        refused_cost = exact_side._task041_v13_fresh_authority_callback(
            "after_eight_columns",
            bad_cost_report,
            comm=comm,
            supervisor_memory_binding=supervisor_binding,
            limits=v13_limits,
        )
        assert refused_cost["status"] == "refused"
        assert refused_cost["decision"] == "stop"
        assert refused_cost["external_resource_gates"]["sample_cost_contract"] is False
        assert refused_cost["cost_assessment"]["decision"] == (
            "refuse_incomplete_cost_evidence"
        )
        assert refused_cost["cost_assessment"]["reasons"]
        unaffordable_builder = copy.deepcopy(sample_report)
        projected = float(
            unaffordable_builder["remaining_projected_seconds"]
        )
        target_elapsed = 172800.0 - projected
        assembly_rows = unaffordable_builder[
            "assembly_elapsed_seconds_by_rank"
        ]
        slowest_rank = max(
            assembly_rows, key=lambda row: row["elapsed_seconds"]
        )["rank"]
        assembly_rows[slowest_rank]["elapsed_seconds"] = target_elapsed
        unaffordable_builder["assembly_elapsed_seconds_max_rank"] = target_elapsed
        unaffordable_builder["estimated_builder_seconds_at_sample"] = (
            target_elapsed + projected
        )
        refused_48h = exact_side._task041_v13_fresh_authority_callback(
            "after_eight_columns",
            unaffordable_builder,
            comm=comm,
            supervisor_memory_binding=supervisor_binding,
            limits=v13_limits,
        )
        assert refused_48h["status"] == "refused"
        assert refused_48h["cost_assessment"]["target_is_elapsed_stop"] is False
        assert refused_48h["cost_assessment"]["decision"] == (
            "refuse_remaining_columns_builder_projection_at_or_above_172800_seconds"
        )
        assert (
            "sampled_builder_projection_at_or_above_172800_second_planning_target"
            in refused_48h["cost_assessment"]["reasons"]
        )
        assert refused_48h["cost_assessment"]["first_eight_max_rank_seconds"] == (
            sample_report["max_rank_sample_seconds"]
        )
        refused_receipt = refused_48h["authority_receipt_payload"]
        assert hashlib.sha256(
            json.dumps(
                refused_receipt,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode()
        ).hexdigest() == refused_48h["authority_receipt_sha256"]
        assert audit["setup_work_counts"]["owner_lu_factorization_attempts"] == 1
        assert audit["setup_work_counts"]["owner_lu_repeat_solve_attempts"] == 2
        assert audit["setup_work_counts"][
            "owner_original_schur_rhs_residual_checks"
        ] == 2
        assert audit["owner_original_schur_rhs_residual_pass"] is True
        assert audit["owner_original_schur_rhs_input_unchanged"] == [True, True]
        assert all(
            value <= 1.0e-10
            for value in audit["owner_original_schur_rhs_residuals"]
        )
        assert audit["setup_work_counts"]["outer_PC_calls"] == 0
        assert audit["setup_work_counts"]["modal_KSP_solves"] == 0
        assert len(markers) > 0

        context = block_ldu.HybridBlockLduPreconditioner(
            layout,
            SimpleNamespace(A=bottom_operator),
            SimpleNamespace(A=top_operator),
            coupling,
            bottom_action,
            top_action,
            system,
        )
        system = None
        original_operator = original_operator_for(layout)
        outer_workspace_rhs = original_operator.createVecRight()
        outer_workspace_solution = original_operator.createVecRight()
        outer_restart32_report = block_ldu._task041_v13_outer_restart_workspace_report(
            original_operator,
            outer_workspace_rhs,
            outer_workspace_solution,
            context,
            comm,
            phase="outer_restart32_workspace",
        )
        assert exact_side._task041_v13_sample_cost_errors(
            "outer_restart32_workspace", outer_restart32_report, comm.size
        ) == []
        assert outer_restart32_report[
            "original_A_binding_vecs_are_already_in_fresh_B"
        ] is False
        outer_restart32_authority = (
            context.action_modal_schur_system.authorize_outer_workspace(
                "outer_restart32_workspace", outer_restart32_report
            )
        )
        assert outer_restart32_authority["status"] == "pass"
        context.bind_v13_original_global_operator(original_operator)
        outer_restart64_report = block_ldu._task041_v13_outer_restart_workspace_report(
            original_operator,
            outer_workspace_rhs,
            outer_workspace_solution,
            context,
            comm,
            phase="outer_restart64_workspace",
        )
        assert exact_side._task041_v13_sample_cost_errors(
            "outer_restart64_workspace", outer_restart64_report, comm.size
        ) == []
        assert outer_restart64_report[
            "original_A_binding_vecs_are_already_in_fresh_B"
        ] is True
        outer_restart64_authority = (
            context.action_modal_schur_system.authorize_outer_workspace(
                "outer_restart64_workspace", outer_restart64_report
            )
        )
        assert outer_restart64_authority["status"] == "pass"
        for outer_phase, outer_report, outer_authority in (
            (
                "outer_restart32_workspace",
                outer_restart32_report,
                outer_restart32_authority,
            ),
            (
                "outer_restart64_workspace",
                outer_restart64_report,
                outer_restart64_authority,
            ),
        ):
            assert block_ldu._task041_v13_outer_workspace_pass_resource_contract_valid(
                outer_phase,
                outer_report,
                outer_authority,
                rank_count=comm.size,
            )
            from src.runners import task041_supervisor

            assert task041_supervisor._v13_outer_authority_pass_matches_report(
                outer_phase,
                outer_report,
                outer_authority,
                rank_count=comm.size,
            )
            bad_B = copy.deepcopy(outer_authority)
            bad_B["fresh_job_authority_bytes"] += 1
            assert not block_ldu._task041_v13_outer_workspace_pass_resource_contract_valid(
                outer_phase, outer_report, bad_B, rank_count=comm.size
            )
            assert not task041_supervisor._v13_outer_authority_pass_matches_report(
                outer_phase, outer_report, bad_B, rank_count=comm.size
            )
            bad_delta = copy.deepcopy(outer_authority)
            bad_delta["additional_bytes_by_rank"][0] += 1
            assert not block_ldu._task041_v13_outer_workspace_pass_resource_contract_valid(
                outer_phase, outer_report, bad_delta, rank_count=comm.size
            )
            missing_external = copy.deepcopy(outer_authority)
            missing_external["external_resource_gates"] = {}
            assert not block_ldu._task041_v13_outer_workspace_pass_resource_contract_valid(
                outer_phase, outer_report, missing_external, rank_count=comm.size
            )
            assert not task041_supervisor._v13_outer_authority_pass_matches_report(
                outer_phase,
                outer_report,
                missing_external,
                rank_count=comm.size,
            )

            insufficient_node1 = copy.deepcopy(outer_authority)
            insufficient_node1["external_resource_gates"][
                "node1_phase_headroom"
            ] = False
            insufficient_free = (
                insufficient_node1["node1_phase_additional_bytes"] - 1
            )
            insufficient_node1["node1_memfree_bytes"] = insufficient_free
            insufficient_node1["node1_headroom_after_phase_additional_bytes"] = -1
            insufficient_payload = insufficient_node1[
                "authority_receipt_payload"
            ]
            insufficient_payload["node1_memfree_bytes"] = insufficient_free
            insufficient_payload[
                "node1_headroom_after_phase_additional_bytes"
            ] = -1
            insufficient_node1["aggregate_memfree_bytes"] = (
                insufficient_node1["node0_memfree_bytes"] + insufficient_free
            )
            insufficient_node1["aggregate_floor_headroom_bytes"] = (
                insufficient_node1["aggregate_memfree_bytes"]
                - insufficient_node1["floor_bytes"]
            )
            insufficient_payload["aggregate_memfree_bytes"] = (
                insufficient_node1["aggregate_memfree_bytes"]
            )
            insufficient_payload["aggregate_floor_headroom_bytes"] = (
                insufficient_node1["aggregate_floor_headroom_bytes"]
            )
            insufficient_node1["authority_receipt_sha256"] = hashlib.sha256(
                json.dumps(
                    insufficient_payload,
                    sort_keys=True,
                    separators=(",", ":"),
                    allow_nan=False,
                ).encode()
            ).hexdigest()
            assert not block_ldu._task041_v13_outer_workspace_pass_resource_contract_valid(
                outer_phase,
                outer_report,
                insufficient_node1,
                rank_count=comm.size,
            )
            assert not task041_supervisor._v13_outer_authority_pass_matches_report(
                outer_phase,
                outer_report,
                insufficient_node1,
                rank_count=comm.size,
            )

            if outer_phase == "outer_restart32_workspace":
                previous_invocation = monitor_sample["invocation_id"]
                monitor_sample["invocation_id"] = "wrong-fixture-invocation"
                identity_refusal = exact_side._task041_v13_fresh_authority_callback(
                    outer_phase,
                    outer_report,
                    comm=comm,
                    supervisor_memory_binding=supervisor_binding,
                    limits=v13_limits,
                )
                monitor_sample["invocation_id"] = previous_invocation
                assert identity_refusal["status"] == "refused"
                assert identity_refusal["external_resource_gates"][
                    "bound_fresh_supervisor_sample"
                ] is False
                assert not block_ldu._task041_v13_outer_workspace_pass_resource_contract_valid(
                    outer_phase,
                    outer_report,
                    identity_refusal,
                    rank_count=comm.size,
                )
                assert not task041_supervisor._v13_outer_authority_pass_matches_report(
                    outer_phase,
                    outer_report,
                    identity_refusal,
                    rank_count=comm.size,
                )

                node_free_by_id[1] = 0
                resource_refusal = exact_side._task041_v13_fresh_authority_callback(
                    outer_phase,
                    outer_report,
                    comm=comm,
                    supervisor_memory_binding=supervisor_binding,
                    limits=v13_limits,
                )
                node_free_by_id[1] = 1_000_000_000_000
                assert resource_refusal["status"] == "refused"
                assert resource_refusal["external_resource_gates"][
                    "node1_phase_headroom"
                ] is False
                assert not block_ldu._task041_v13_outer_workspace_pass_resource_contract_valid(
                    outer_phase,
                    outer_report,
                    resource_refusal,
                    rank_count=comm.size,
                )
                assert not task041_supervisor._v13_outer_authority_pass_matches_report(
                    outer_phase,
                    outer_report,
                    resource_refusal,
                    rank_count=comm.size,
                )
        source = layout.create_vector()
        target = layout.create_vector()
        original_a_context = original_operator.getPythonContext()
        capture_token = 987654321
        capture_exception = None
        try:
            original_a_context.arm_v13_modal_row_capture(
                capture_token,
                matrix_handle=-1,
                pc_source_handle=int(source.handle),
                pc_target_handle=int(target.handle),
                operator_input_handle=int(source.handle),
                operator_output_handle=int(target.handle),
            )
            original_operator.mult(source, target)
        except Exception as exc:  # noqa: BLE001 - assert one-shot cleanup on capture failure
            capture_exception = exc
        finally:
            original_a_context.clear_v13_modal_row_capture(capture_token)
        capture_failure_rows = comm.allgather(
            None
            if capture_exception is None
            else f"{type(capture_exception).__name__}: {capture_exception}"
        )
        assert all(row is not None for row in capture_failure_rows)
        assert original_a_context._v13_modal_row_capture_request is None
        assert original_a_context._v13_modal_row_capture_result is None
        bottom_indices = layout.map_bottom(
            np.arange(side_size, dtype=PETSc.IntType)
        )
        top_indices = layout.map_top(np.arange(side_size, dtype=PETSc.IntType))
        modal_indices = layout.map_modal(
            np.arange(internal_count, dtype=PETSc.IntType)
        )
        side_bottom_rhs = np.asarray(
            [0.4 + 0.2j, -0.1 + 0.3j, 0.2 - 0.15j, 0.07 + 0.11j, -0.2j, 0.13],
            dtype=np.complex128,
        )
        side_top_rhs = np.asarray(
            [-0.1 + 0.3j, 0.08 - 0.12j, 0.15 + 0.07j, -0.22j, 0.03 + 0.09j, 0.17],
            dtype=np.complex128,
        )

        def set_source(modal_rhs: np.ndarray, *, side_scale: float = 1.0) -> None:
            input_values = np.zeros(layout.global_size, dtype=np.complex128)
            input_values[bottom_indices] = side_scale * side_bottom_rhs
            input_values[top_indices] = side_scale * side_top_rhs
            input_values[modal_indices] = np.asarray(modal_rhs, dtype=np.complex128)
            _set_vector(source, input_values)

        set_source(np.asarray([0.2 - 0.15j] + [0.0j] * (internal_count - 1)))
        source_before = _gather_vector(source)
        context.apply(None, source, target)
        np.testing.assert_array_equal(_gather_vector(source), source_before)
        assert original_a_context._v13_modal_row_capture_request is None
        assert original_a_context._v13_modal_row_capture_result is None
        ordinary_call_count = original_a_context._matmult_call_count
        assert_full_original_action(layout, original_operator, target)
        assert original_a_context._matmult_call_count == ordinary_call_count + 1
        assert original_a_context._v13_modal_row_capture_request is None
        assert original_a_context._v13_modal_row_capture_result is None
        modal_system = context.action_modal_schur_system
        row_record = modal_system.diagnostics["last_original_modal_row"]
        assert row_record["status"] == "passed"
        assert row_record["metrics"]["eta_terms_inf"] <= 1.0e-10
        assert row_record["same_attempt_owner_solve"] is True
        assert row_record["owner_lu_solve_record"]["status"] == "passed"
        assert row_record["owner_lu_solve_record"]["input_unchanged"] is True
        assert row_record["B_P4_counter_delta_by_rank"] is not None
        assert len(row_record["B_P4_counter_delta_by_rank"]) == comm.size
        for rank_delta in row_record["B_P4_counter_delta_by_rank"]:
            for side in ("bottom", "top"):
                side_delta = rank_delta["p4_and_B_by_side"][side]
                assert side_delta["action_apply_count"] == 2
                assert side_delta["p4_factor_count"] == 0
        assert row_record["capture_identity"]["attempt_index"] == 1
        first_call_ids = row_record["capture_identity"]["matmult_call_id_by_rank"]
        assert len(first_call_ids) == comm.size
        assert len(set(first_call_ids)) == 1
        assert all(type(call_id) is int and call_id > 0 for call_id in first_call_ids)
        first_arrays = modal_system.frozen_original_modal_row()["arrays"]
        assert first_arrays is not None
        assert first_arrays["d"].shape == (internal_count,)
        assert first_arrays["t_bottom"].shape == (internal_count,)
        assert first_arrays["t_top"].shape == (internal_count,)
        expected_build_and_first_pc_calls = internal_count + 7 + 2
        assert bottom_action.audit["apply_count"] == expected_build_and_first_pc_calls
        assert top_action.audit["apply_count"] == expected_build_and_first_pc_calls
        assert modal_system.diagnostics["solve_count"] == 1
        lu_solve_counts = comm.allgather(
            modal_system.diagnostics["owner_lu_solve_count"]
        )
        assert lu_solve_counts == [0] * (comm.size - 1) + [1]

        # The complete V13 LDU action, not only its old fixed-H6 or
        # fixed-Q component, must remain a repeatable complex-linear map.
        # Reuse this same built context and its owner LU for every assertion.
        linear_rhs_x = layout.create_vector()
        linear_rhs_y = layout.create_vector()
        linear_rhs_sum = layout.create_vector()
        linear_out_x = layout.create_vector()
        linear_out_y = layout.create_vector()
        linear_out_sum = layout.create_vector()
        linear_out_repeat = layout.create_vector()
        try:
            x_values = np.asarray(
                [0.07 - 0.03j * index for index in range(layout.global_size)],
                dtype=np.complex128,
            )
            y_values = np.asarray(
                [-0.02j + 0.011 * index for index in range(layout.global_size)],
                dtype=np.complex128,
            )
            alpha = 0.31 - 0.47j
            _set_vector(linear_rhs_x, x_values)
            _set_vector(linear_rhs_y, y_values)
            _set_vector(linear_rhs_sum, x_values + y_values)
            linear_rhs_x_before = _gather_vector(linear_rhs_x)
            linear_rhs_y_before = _gather_vector(linear_rhs_y)
            context.apply(None, linear_rhs_x, linear_out_x)
            context.apply(None, linear_rhs_y, linear_out_y)
            context.apply(None, linear_rhs_sum, linear_out_sum)
            context.apply(None, linear_rhs_x, linear_out_repeat)
            np.testing.assert_allclose(
                _gather_vector(linear_out_sum),
                _gather_vector(linear_out_x) + _gather_vector(linear_out_y),
                rtol=2.0e-12,
                atol=2.0e-12,
            )
            # A separate complex homogeneity check rules out conjugate-linear
            # behavior in the full LDU application.
            _set_vector(linear_rhs_sum, alpha * x_values)
            context.apply(None, linear_rhs_sum, linear_out_sum)
            np.testing.assert_allclose(
                _gather_vector(linear_out_sum),
                alpha * _gather_vector(linear_out_x),
                rtol=2.0e-12,
                atol=2.0e-12,
            )
            np.testing.assert_allclose(
                _gather_vector(linear_out_repeat),
                _gather_vector(linear_out_x),
                rtol=0.0,
                atol=0.0,
            )
            np.testing.assert_array_equal(
                _gather_vector(linear_rhs_x), linear_rhs_x_before
            )
            np.testing.assert_array_equal(
                _gather_vector(linear_rhs_y), linear_rhs_y_before
            )
            assert modal_system.diagnostics["modal_ksp_solve_count"] == 0
            assert modal_system.diagnostics["side_solver_entry_zero_supported"] is True
            assert modal_system.diagnostics["side_operation_deltas"] == {
                "bottom": {"apply_count": 0, "total_iterations": 0},
                "top": {"apply_count": 0, "total_iterations": 0},
            }

            # A finite LU result that solves the mutated RHS must still be
            # rejected: residual success cannot excuse input mutation.
            original_lu_solve = block_ldu.lu_solve

            def mutate_rhs_then_solve(factor, rhs, **kwargs):
                rhs[0] += 1.0e-7 + 2.0e-7j
                return original_lu_solve(factor, rhs, **kwargs)

            mutation_rhs = np.asarray(
                [0.2 - 0.1j * index for index in range(internal_count)],
                dtype=np.complex128,
            )
            mutation_rhs_before = mutation_rhs.copy()
            monkeypatch.setattr(block_ldu, "lu_solve", mutate_rhs_then_solve)
            try:
                with pytest.raises(FloatingPointError, match="a-g residual gate"):
                    modal_system.solve(mutation_rhs)
            finally:
                monkeypatch.setattr(block_ldu, "lu_solve", original_lu_solve)
            mutation_record = modal_system.diagnostics["last_solve"]
            assert mutation_record["status"] == "rejected"
            assert mutation_record["residual_passed"] is True
            assert mutation_record["input_unchanged"] is False
            assert mutation_record["trusted_iterate"] is False
            mutation_by_rank = comm.allgather(
                not np.array_equal(mutation_rhs, mutation_rhs_before)
            )
            assert mutation_by_rank == [False] * (comm.size - 1) + [True]

            # The all-input-zero case is distinct from a nonzero side input
            # whose original modal row cancels exactly to zero.
            _set_vector(linear_rhs_sum, np.zeros(layout.global_size))
            context.apply(None, linear_rhs_sum, linear_out_sum)
            np.testing.assert_array_equal(
                _gather_vector(linear_out_sum),
                np.zeros(layout.global_size, dtype=np.complex128),
            )
            np.testing.assert_array_equal(
                _gather_vector(linear_rhs_sum),
                np.zeros(layout.global_size, dtype=np.complex128),
            )
        finally:
            for vector in (
                linear_out_repeat,
                linear_out_sum,
                linear_out_y,
                linear_out_x,
                linear_rhs_sum,
                linear_rhs_y,
                linear_rhs_x,
            ):
                vector.destroy()

        # Nonzero side and modal terms cancel to an exact-zero modal RHS.
        set_source(
            np.zeros(internal_count, dtype=np.complex128), side_scale=1.0e-9
        )
        source_before = _gather_vector(source)
        context.apply(None, source, target)
        zero_record = modal_system.diagnostics["last_original_modal_row"]
        assert zero_record["metrics"]["rhs_exact_zero"] is True
        assert zero_record["metrics"]["legacy_rhs_relative_status"] == "not_defined"
        zero_arrays = modal_system.frozen_original_modal_row()["arrays"]
        assert zero_arrays is not None
        assert np.array_equal(zero_arrays["r_modal"], np.zeros(internal_count))
        side_norm = np.linalg.norm(
            zero_arrays["t_bottom"] + zero_arrays["t_top"]
        )
        constraint_norm = np.linalg.norm(zero_arrays["t_constraint"])
        assert side_norm > 0.0
        assert constraint_norm > 0.0
        assert zero_record["metrics"]["legacy_exact_zero_terms_relative"] == pytest.approx(
            np.linalg.norm(zero_arrays["d"]) / (side_norm + constraint_norm)
        )
        assert zero_record["metrics"]["eta_terms_inf"] <= 1.0e-10
        np.testing.assert_array_equal(_gather_vector(source), source_before)
        assert_full_original_action(layout, original_operator, target)

        near_rhs = np.zeros(internal_count, dtype=np.complex128)
        near_rhs[0] = 1.0e-12
        near_rhs[1] = (1.0 - 2.0**-34) * 1.0e-12j
        set_source(near_rhs, side_scale=1.0e-9)
        near_source_before = _gather_vector(source)
        context.apply(None, source, target)
        near_record = modal_system.diagnostics["last_original_modal_row"]
        assert near_record["metrics"]["rhs_exact_zero"] is False
        assert near_record["metrics"]["eta_terms_inf"] <= 1.0e-10
        near_arrays = modal_system.frozen_original_modal_row()["arrays"]
        assert near_arrays is not None
        np.testing.assert_array_equal(near_arrays["r_modal"], near_rhs)
        assert 0.0 < np.linalg.norm(near_arrays["r_modal"]) < 1.0e-10
        assert near_record["capture_identity"]["attempt_index"] == near_record[
            "attempt_index"
        ]
        np.testing.assert_array_equal(_gather_vector(source), near_source_before)
        assert_full_original_action(layout, original_operator, target)

        set_source(np.zeros(internal_count, dtype=np.complex128), side_scale=1.0e-9)
        context.apply(None, source, target)
        assert modal_system.diagnostics["last_original_modal_row"]["status"] == "passed"
        assert abs(_gather_vector(target)[modal_indices[0]]) > 0.0

        # Exercise the actual full original A with right FGMRES and this same
        # fixed block-LDU context as its Python preconditioner.  The final
        # acceptance check recomputes A*x-f independently of KSP's estimate.
        exact_solution = layout.create_vector()
        outer_rhs = original_operator.createVecLeft()
        outer_solution = original_operator.createVecRight()
        outer_build_solution_scratch = original_operator.createVecRight()
        outer_residual = outer_rhs.duplicate()
        outer_ksp = PETSc.KSP().create(comm)
        build_solution_probe_rows: list[dict[str, Any]] = []

        class BorrowedV13BlockLduPc:
            def apply(self, _pc, pc_source, pc_target):
                context.apply(_pc, pc_source, pc_target)

            def destroy(self, _pc=None):
                return None

        outer_pc_context = BorrowedV13BlockLduPc()

        def capture_build_solution_capability(
            current_ksp, iteration: int, reported_rnorm: float
        ) -> None:
            del reported_rnorm
            if int(iteration) != 1 or build_solution_probe_rows:
                return
            try:
                build_solution = getattr(current_ksp, "buildSolution", None)
                local_availability = {
                    "rank": int(comm.rank),
                    "callable": callable(build_solution),
                    "lookup_error": None,
                }
            except Exception as lookup_error:  # noqa: BLE001 - noncollective method lookup
                build_solution = None
                local_availability = {
                    "rank": int(comm.rank),
                    "callable": False,
                    "lookup_error": {
                        "type": type(lookup_error).__name__,
                        "message": str(lookup_error)[:320],
                    },
                }
            availability_by_rank = comm.allgather(local_availability)
            callable_states = [bool(row["callable"]) for row in availability_by_rank]
            if (
                any(row["lookup_error"] for row in availability_by_rank)
                or len(set(callable_states)) != 1
            ):
                raise AssertionError(
                    "synthetic buildSolution availability differs before call: "
                    + json.dumps(availability_by_rank, sort_keys=True)
                )
            if not callable_states[0]:
                build_solution_probe_rows.append(
                    {
                        "rank": int(comm.rank),
                        "iteration": int(iteration),
                        "status": "unavailable",
                        "call_attempted": False,
                        "reason": "no_callable_buildSolution_before_call",
                        "reported_norm_semantics": (
                            "PETSc reported KSP norm; not an independent true residual"
                        ),
                    }
                )
                return

            original_A_matmult_before = int(
                original_a_context._matmult_call_count
            )
            pc_apply_count_before = int(context._pc_apply_count)
            pc_apply_attempt_count_before = int(
                context._pc_apply_attempt_count
            )
            capture_request_clear_before = (
                original_a_context._v13_modal_row_capture_request is None
            )
            capture_result_clear_before = (
                original_a_context._v13_modal_row_capture_result is None
            )
            sentinel = PETSc.ScalarType(12345.0 + 6789.0j)
            outer_build_solution_scratch.set(sentinel)
            preparation_error = None
            try:
                rhs_before_local = np.asarray(
                    outer_rhs.getArray(readonly=True)
                ).copy()
                output_before_local = np.asarray(
                    outer_solution.getArray(readonly=True)
                ).copy()
                scratch_before_local = np.asarray(
                    outer_build_solution_scratch.getArray(readonly=True)
                ).copy()
            except Exception as local_preparation_error:  # noqa: BLE001 - local reads precede buildSolution
                preparation_error = {
                    "type": type(local_preparation_error).__name__,
                    "message": str(local_preparation_error)[:320],
                }
                rhs_before_local = np.empty(0, dtype=np.complex128)
                output_before_local = np.empty(0, dtype=np.complex128)
                scratch_before_local = np.empty(0, dtype=np.complex128)
            preparation_by_rank = comm.allgather(
                {
                    "rank": int(comm.rank),
                    "status": (
                        "ready" if preparation_error is None else "local_error"
                    ),
                    "error": preparation_error,
                }
            )
            if any(row.get("status") != "ready" for row in preparation_by_rank):
                raise AssertionError(
                    "synthetic buildSolution local preparation failed: "
                    + json.dumps(preparation_by_rank, sort_keys=True)
                )
            try:
                returned = build_solution(outer_build_solution_scratch)
            except BaseException as probe_error:  # local receipt only, then preserve original
                probe_row = {
                    "rank": int(comm.rank),
                    "iteration": int(iteration),
                    "status": "buildSolution_exception",
                    "error_type": type(probe_error).__name__,
                    "error_message": str(probe_error)[:320],
                    "call_attempted": True,
                    "other_rank_status": "not_claimed",
                }
                probe_path = evidence_root / (
                    "TASK041_V16_BUILD_SOLUTION_CAPABILITY_ERROR_"
                    f"rank-{comm.rank}.json"
                )
                try:
                    probe_path.parent.mkdir(parents=True, exist_ok=True)
                    if probe_path.exists():
                        raise FileExistsError(str(probe_path))
                    probe_path.write_text(
                        json.dumps(probe_row, sort_keys=True, indent=2) + "\n",
                        encoding="utf-8",
                    )
                    probe_error.add_note(
                        "secondary local capability receipt: " + str(probe_path)
                    )
                except Exception as receipt_error:  # noqa: BLE001 - secondary only
                    try:
                        probe_error.add_note(
                            "capability error receipt also failed: "
                            + type(receipt_error).__name__
                        )
                    except Exception:  # noqa: BLE001, S110
                        pass
                raise

            try:
                returned_handle = getattr(returned, "handle", None)
                scratch_handle = int(outer_build_solution_scratch.handle)
                scratch_after = np.asarray(
                    outer_build_solution_scratch.getArray(readonly=True)
                ).copy()
                probe_row = {
                    "rank": int(comm.rank),
                    "iteration": int(iteration),
                    "status": "supported",
                    "call_attempted": True,
                    "reported_norm_semantics": (
                        "PETSc reported KSP norm; not an independent true residual"
                    ),
                    "returned_none": returned is None,
                    "returned_is_scratch": (
                        returned is outer_build_solution_scratch
                    ),
                    "returned_handle": (
                        None if returned_handle is None else int(returned_handle)
                    ),
                    "scratch_handle": scratch_handle,
                    "returned_uses_scratch": (
                        returned is None
                        or returned is outer_build_solution_scratch
                        or (
                            returned_handle is not None
                            and int(returned_handle) == scratch_handle
                        )
                    ),
                    "scratch_is_ksp_solution": (
                        scratch_handle == int(outer_solution.handle)
                    ),
                    "scratch_is_rhs": scratch_handle == int(outer_rhs.handle),
                    "scratch_changed_from_sentinel": not np.array_equal(
                        scratch_after, scratch_before_local
                    ),
                    "scratch_finite": bool(np.isfinite(scratch_after).all()),
                    "rhs_unchanged": np.array_equal(
                        np.asarray(outer_rhs.getArray(readonly=True)),
                        rhs_before_local,
                    ),
                    "ksp_solution_unchanged": np.array_equal(
                        np.asarray(outer_solution.getArray(readonly=True)),
                        output_before_local,
                    ),
                    "pc_apply_count_before": pc_apply_count_before,
                    "pc_apply_count_after": int(context._pc_apply_count),
                    "pc_apply_attempt_count_before": (
                        pc_apply_attempt_count_before
                    ),
                    "pc_apply_attempt_count_after": int(
                        context._pc_apply_attempt_count
                    ),
                    "original_A_matmult_delta": (
                        int(original_a_context._matmult_call_count)
                        - original_A_matmult_before
                    ),
                    "capture_request_clear_before": (
                        capture_request_clear_before
                    ),
                    "capture_request_clear_after": (
                        original_a_context._v13_modal_row_capture_request is None
                    ),
                    "capture_result_clear_before": (
                        capture_result_clear_before
                    ),
                    "capture_result_clear_after": (
                        original_a_context._v13_modal_row_capture_result is None
                    ),
                }
                probe_row["status"] = (
                    "supported"
                    if probe_row["returned_uses_scratch"] is True
                    and probe_row["scratch_is_ksp_solution"] is False
                    and probe_row["scratch_is_rhs"] is False
                    and probe_row["scratch_changed_from_sentinel"] is True
                    and probe_row["scratch_finite"] is True
                    and probe_row["rhs_unchanged"] is True
                    and probe_row["ksp_solution_unchanged"] is True
                    and probe_row["pc_apply_count_after"]
                    == probe_row["pc_apply_count_before"]
                    and probe_row["pc_apply_attempt_count_after"]
                    == probe_row["pc_apply_attempt_count_before"]
                    and probe_row["original_A_matmult_delta"] == 0
                    and probe_row["capture_request_clear_before"] is True
                    and probe_row["capture_request_clear_after"] is True
                    and probe_row["capture_result_clear_before"] is True
                    and probe_row["capture_result_clear_after"] is True
                    else "invariant_failed"
                )
            except Exception as local_inspection_error:  # noqa: BLE001 - buildSolution returned before this local check
                probe_row = {
                    "rank": int(comm.rank),
                    "iteration": int(iteration),
                    "status": "local_inspection_error",
                    "error_type": type(local_inspection_error).__name__,
                    "error_message": str(local_inspection_error)[:320],
                }
            probe_rows = comm.allgather(probe_row)
            if any(row.get("status") != "supported" for row in probe_rows):
                raise AssertionError(
                    "synthetic buildSolution violated scratch/input/PC/A invariants: "
                    + json.dumps(probe_rows, sort_keys=True)
                )
            build_solution_probe_rows.append(probe_row)

        try:
            exact_values = np.asarray(
                [0.17 + 0.013j * index for index in range(layout.global_size)],
                dtype=np.complex128,
            )
            _set_vector(exact_solution, exact_values)
            original_operator.mult(exact_solution, outer_rhs)
            outer_rhs_before = _gather_vector(outer_rhs)
            outer_ksp.setOperators(original_operator)
            outer_ksp.setType(PETSc.KSP.Type.FGMRES)
            outer_ksp.setGMRESRestart(layout.global_size)
            outer_ksp.setPCSide(PETSc.PC.Side.RIGHT)
            outer_ksp.setNormType(PETSc.KSP.NormType.UNPRECONDITIONED)
            outer_ksp.setInitialGuessNonzero(False)
            outer_ksp.setTolerances(
                rtol=5.0e-9,
                atol=0.0,
                max_it=2 * layout.global_size,
            )
            outer_pc = outer_ksp.getPC()
            outer_pc.setType(PETSc.PC.Type.PYTHON)
            outer_pc.setPythonContext(outer_pc_context)
            outer_ksp.setUp()
            outer_ksp.setMonitor(capture_build_solution_capability)
            outer_ksp.solve(outer_rhs, outer_solution)
            original_operator.mult(outer_solution, outer_residual)
            outer_residual.axpy(PETSc.ScalarType(-1.0), outer_rhs)
            outer_rhs_norm = float(outer_rhs.norm())
            outer_true_relative = float(outer_residual.norm()) / outer_rhs_norm
            probe_rows_by_rank = comm.allgather(build_solution_probe_rows)
            capability_rank_rows = [
                rows[0]
                if len(rows) == 1
                else {
                    "rank": rank,
                    "status": "missing_or_duplicate_probe_row",
                    "observed_row_count": len(rows),
                }
                for rank, rows in enumerate(probe_rows_by_rank)
            ]
            capability_write_status = None
            if comm.rank == 0:
                capability_path = (
                    evidence_root / "TASK041_V16_BUILD_SOLUTION_CAPABILITY.json"
                )
                capability_temporary = capability_path.with_name(
                    capability_path.name + ".tmp"
                )
                try:
                    if capability_path.exists() or capability_temporary.exists():
                        raise FileExistsError(str(capability_path))
                    capability_document = {
                        "schema": "task041.v16.synthetic_tiny_build_solution_capability.v1",
                        "classification": "synthetic_tiny_KSP_PC_capability_only_not_registered_FE_qualification",
                        "selector": "src/test/test_350_task041_balh_block_ldu.py::test_v13_unmocked_builder_owner_lu_and_original_modal_row_math",
                        "source_sha256": supervisor_binding["source_sha"],
                        "source_identity_scope": "synthetic test fixture binding; not a registered-configuration source qualification",
                        "invocation_id": supervisor_binding["invocation_id"],
                        "invocation_identity_scope": "synthetic test fixture binding",
                        "mpi_size": int(comm.size),
                        "rank_rows": capability_rank_rows,
                    }
                    with capability_temporary.open("x", encoding="utf-8") as stream:
                        json.dump(
                            capability_document,
                            stream,
                            sort_keys=True,
                            indent=2,
                            allow_nan=False,
                        )
                        stream.write("\n")
                        stream.flush()
                        os.fsync(stream.fileno())
                    os.replace(capability_temporary, capability_path)
                    capability_write_status = {
                        "status": "written",
                        "path": str(capability_path),
                        "sha256": hashlib.sha256(
                            capability_path.read_bytes()
                        ).hexdigest(),
                    }
                except BaseException as capability_write_error:  # noqa: BLE001 - preserve numerical assertions and report evidence failure
                    capability_write_status = {
                        "status": "failed",
                        "error_type": type(capability_write_error).__name__,
                        "error_message": str(capability_write_error)[:320],
                    }
            capability_write_status = comm.bcast(
                capability_write_status, root=0
            )
            assert capability_write_status.get("status") == "written", (
                capability_write_status
            )
            assert all(len(rows) == 1 for rows in probe_rows_by_rank), probe_rows_by_rank
            probe_statuses = [rows[0]["status"] for rows in probe_rows_by_rank]
            assert len(set(probe_statuses)) == 1, probe_statuses
            for rows in probe_rows_by_rank:
                probe_row = rows[0]
                assert probe_row["status"] in {"supported", "unavailable"}, probe_row
                if probe_row["status"] == "supported":
                    assert probe_row["returned_uses_scratch"] is True
                    assert probe_row["scratch_is_ksp_solution"] is False
                    assert probe_row["scratch_is_rhs"] is False
                    assert probe_row["scratch_changed_from_sentinel"] is True
                    assert probe_row["scratch_finite"] is True
                    assert probe_row["rhs_unchanged"] is True
                    assert probe_row["ksp_solution_unchanged"] is True
                    assert (
                        probe_row["pc_apply_count_after"]
                        == probe_row["pc_apply_count_before"]
                    )
                    assert (
                        probe_row["pc_apply_attempt_count_after"]
                        == probe_row["pc_apply_attempt_count_before"]
                    )
            assert int(outer_ksp.getConvergedReason()) > 0
            assert np.isfinite(outer_true_relative)
            assert outer_true_relative <= 5.0e-9
            np.testing.assert_array_equal(_gather_vector(outer_rhs), outer_rhs_before)
            assert context.inventory["pc_apply_count"] > 0
            assert (
                modal_system.diagnostics["last_original_modal_row"]["status"]
                == "passed"
            )
        finally:
            outer_ksp.destroy()
            for vector in (
                outer_residual,
                outer_build_solution_scratch,
                outer_solution,
                outer_rhs,
                exact_solution,
            ):
                vector.destroy()

        # Capture at most two real RIGHT-FGMRES PC applications with an
        # initially exact-zero modal RHS and nonzero side RHS.  The recorder
        # delegates to the real callback, row recorder, and apply method; it
        # only copies evidence before the fixture destroys its PETSc objects.
        diagnostic_rhs = original_operator.createVecLeft()
        diagnostic_solution = original_operator.createVecRight()
        diagnostic_ksp = PETSc.KSP().create(comm)
        diagnostic_records: list[dict[str, Any]] = []
        active_diagnostic_record: dict[str, Any] | None = None
        diagnostic_apply_count = 0

        def diagnostic_jsonable(value: Any) -> Any:
            if isinstance(value, Mapping):
                return {
                    str(key): diagnostic_jsonable(item)
                    for key, item in value.items()
                }
            if isinstance(value, (list, tuple)):
                return [diagnostic_jsonable(item) for item in value]
            if isinstance(value, np.ndarray):
                return diagnostic_jsonable(value.tolist())
            if isinstance(value, (np.generic,)):
                return diagnostic_jsonable(value.item())
            if isinstance(value, complex):
                real = float(value.real)
                imag = float(value.imag)
                return [
                    real if np.isfinite(real) else str(real),
                    imag if np.isfinite(imag) else str(imag),
                ]
            if isinstance(value, float) and not np.isfinite(value):
                return str(value)
            if value is None or isinstance(value, (str, int, float, bool)):
                return value
            return repr(value)

        def diagnostic_exception(exc: BaseException) -> dict[str, str]:
            return {
                "type": type(exc).__name__,
                "message": str(exc)[:1000],
            }

        def diagnostic_capture(
            record: dict[str, Any], field: str, read: Any
        ) -> None:
            try:
                record[field] = diagnostic_jsonable(read())
            except Exception as capture_error:  # noqa: BLE001 - capture never changes gate
                record.setdefault("capture_errors", []).append(
                    diagnostic_exception(capture_error)
                )

        def write_diagnostic_mini_record(
            record: Mapping[str, Any],
        ) -> dict[str, Any]:
            """Owner-write one completed PC-apply record and broadcast its receipt."""

            rank_rows = comm.gather(diagnostic_jsonable(record), root=0)
            owner_result = None
            if comm.rank == 0:
                try:
                    if not isinstance(rank_rows, list) or len(rank_rows) != comm.size:
                        raise RuntimeError("mini-record gather omitted a rank")
                    if [row.get("rank") for row in rank_rows] != list(range(comm.size)):
                        raise RuntimeError("mini-record ranks are incomplete or unordered")
                    path = evidence_root / "TASK041_V15_MODAL_ROW_PC_APPLY_MINI_RECORDS.json"
                    document = (
                        json.loads(path.read_text(encoding="utf-8"))
                        if path.is_file()
                        else {
                            "schema": "task041.v15.test350_pc_apply_mini_records.v1",
                            "rank_count": int(comm.size),
                            "captures": [],
                        }
                    )
                    if (
                        not isinstance(document, dict)
                        or document.get("schema")
                        != "task041.v15.test350_pc_apply_mini_records.v1"
                        or document.get("rank_count") != comm.size
                        or not isinstance(document.get("captures"), list)
                    ):
                        raise ValueError("existing mini-record document has invalid identity")
                    apply_index = int(record["diagnostic_apply_index"])
                    if any(
                        item.get("diagnostic_apply_index") == apply_index
                        for item in document["captures"]
                    ):
                        raise FileExistsError(
                            f"mini-record apply index {apply_index} already exists"
                        )
                    document["captures"].append(
                        {
                            "diagnostic_apply_index": apply_index,
                            "rank_rows": rank_rows,
                        }
                    )
                    temporary = path.with_name(path.name + ".tmp")
                    if temporary.exists():
                        raise FileExistsError(f"mini-record temporary path exists: {temporary}")
                    encoded = (
                        json.dumps(
                            document,
                            sort_keys=True,
                            indent=2,
                            allow_nan=False,
                        )
                        + "\n"
                    ).encode("utf-8")
                    with temporary.open("xb") as stream:
                        stream.write(encoded)
                        stream.flush()
                        os.fsync(stream.fileno())
                    os.replace(temporary, path)
                    owner_result = {
                        "status": "written",
                        "path": str(path),
                        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                        "diagnostic_apply_index": apply_index,
                        "rank_rows": len(rank_rows),
                    }
                except Exception as exc:  # noqa: BLE001 - caller preserves any PC failure
                    owner_result = {
                        "status": "failed",
                        "error": diagnostic_exception(exc),
                    }
            result = comm.bcast(owner_result, root=0)
            if not isinstance(result, Mapping):
                return {
                    "status": "failed",
                    "error": {
                        "type": "ProtocolError",
                        "message": "mini-record write receipt was not broadcast",
                    },
                }
            return dict(result)

        def diagnostic_vector_snapshot(vector: PETSc.Vec) -> dict[str, Any]:
            first, last = (int(value) for value in vector.getOwnershipRange())
            values = np.asarray(
                vector.getArray(readonly=True), dtype=np.complex128
            ).copy()
            return {
                "ownership_range": [first, last],
                "local_values_real_imag": [
                    [float(value.real), float(value.imag)] for value in values
                ],
            }

        def diagnostic_petsc_handle(vector: PETSc.Vec) -> int | None:
            try:
                return int(vector.handle)
            except Exception:  # noqa: BLE001 - PETSc handle access varies by build
                return None

        def diagnostic_side_counts() -> dict[str, Any]:
            return {
                "bottom": block_ldu._v13_side_operation_counts(
                    context.bottom_action
                ),
                "top": block_ldu._v13_side_operation_counts(context.top_action),
            }

        def diagnostic_decimal_matrix_oracle(
            pc_source: PETSc.Vec,
            pc_target: PETSc.Vec,
            capture: Mapping[str, Any],
        ) -> dict[str, Any]:
            """Recompute the real tiny original-A row from matrix inputs."""

            source_values = _gather_vector(pc_source)
            target_values = _gather_vector(pc_target)
            modal_values = target_values[modal_indices]
            bottom_values = target_values[bottom_indices]
            top_values = target_values[top_indices]
            exact_constraint = _decimal_complex_matvec(
                original_C, modal_values
            )
            exact_bottom_product = _decimal_complex_matvec(
                bottom_projection_dense, bottom_values
            )
            exact_top_product = _decimal_complex_matvec(
                top_projection_dense, top_values
            )
            exact_bottom = [
                *exact_bottom_product,
                *((Decimal(0), Decimal(0)) for _ in range(modal_per_side)),
            ]
            exact_top = [
                *((Decimal(0), Decimal(0)) for _ in range(modal_per_side)),
                *exact_top_product,
            ]
            exact_r = [
                _decimal_complex_pair(value)
                for value in source_values[modal_indices]
            ]
            exact_w = [
                _decimal_complex_sum(
                    _decimal_complex_sum(constraint, bottom), top
                )
                for constraint, bottom, top in zip(
                    exact_constraint, exact_bottom, exact_top, strict=True
                )
            ]
            exact_d = [
                _decimal_complex_difference(output, rhs)
                for output, rhs in zip(exact_w, exact_r, strict=True)
            ]
            actual_by_name = {
                name: np.asarray(capture[name], dtype=np.complex128)
                for name in (
                    "r_modal",
                    "w_modal",
                    "t_bottom",
                    "t_top",
                    "t_constraint",
                )
            }
            exact_by_name = {
                "r_modal": exact_r,
                "w_modal": exact_w,
                "t_bottom": exact_bottom,
                "t_top": exact_top,
                "t_constraint": exact_constraint,
            }
            product_bounds = {
                "t_constraint": [
                    sum(
                        (
                            _decimal_complex_modulus(
                                _decimal_complex_pair(coefficient)
                            )
                            * _decimal_complex_modulus(
                                _decimal_complex_pair(value)
                            )
                            for coefficient, value in zip(
                                row, modal_values, strict=True
                            )
                        ),
                        Decimal(0),
                    )
                    for row in original_C
                ],
                "t_bottom": [
                    *[
                        _decimal_sum(
                            (
                                _decimal_complex_modulus(
                                    _decimal_complex_pair(coefficient)
                                )
                                * _decimal_complex_modulus(
                                    _decimal_complex_pair(value)
                                )
                                for coefficient, value in zip(
                                    row, bottom_values, strict=True
                                )
                            ),
                        )
                        for row in bottom_projection_dense
                    ],
                    *((Decimal(0)) for _ in range(modal_per_side)),
                ],
                "t_top": [
                    *((Decimal(0)) for _ in range(modal_per_side)),
                    *[
                        _decimal_sum(
                            (
                                _decimal_complex_modulus(
                                    _decimal_complex_pair(coefficient)
                                )
                                * _decimal_complex_modulus(
                                    _decimal_complex_pair(value)
                                )
                                for coefficient, value in zip(
                                    row, top_values, strict=True
                                )
                            ),
                        )
                        for row in top_projection_dense
                    ],
                ],
            }
            epsilon = Decimal.from_float(np.finfo(np.float64).eps)
            actual_w = actual_by_name["w_modal"]
            actual_r = actual_by_name["r_modal"]
            component_rows: dict[str, Any] = {}
            for name, exact_rows in exact_by_name.items():
                actual_rows = actual_by_name[name]
                if actual_rows.shape != (internal_count,):
                    component_rows[name] = {"status": "shape_mismatch"}
                    continue
                errors = [
                    _decimal_complex_modulus(
                        _decimal_complex_difference(
                            _decimal_complex_pair(actual), expected
                        )
                    )
                    for actual, expected in zip(
                        actual_rows, exact_rows, strict=True
                    )
                ]
                if name == "r_modal":
                    bounds = [Decimal(0)] * internal_count
                elif name == "w_modal":
                    bounds = [
                        _decimal_sum(
                            (
                                product_bounds["t_constraint"][index],
                                product_bounds["t_bottom"][index],
                                product_bounds["t_top"][index],
                            )
                        )
                        for index in range(internal_count)
                    ]
                else:
                    bounds = product_bounds[name]
                allowed = [Decimal(512) * epsilon * bound for bound in bounds]
                component_rows[name] = {
                    "status": (
                        "passed"
                        if all(error <= limit for error, limit in zip(errors, allowed, strict=True))
                        else "failed"
                    ),
                    "max_abs_error_decimal": str(max(errors, default=Decimal(0))),
                    "max_roundoff_bound_decimal": str(
                        max(allowed, default=Decimal(0))
                    ),
                }
            with localcontext() as decimal_context:
                decimal_context.prec = 180
                d_error = max(
                    (
                        _decimal_complex_modulus(
                            _decimal_complex_difference(
                                _decimal_complex_pair(actual), expected
                            )
                        )
                        for actual, expected in zip(
                            np.subtract(
                                actual_by_name["w_modal"],
                                actual_by_name["r_modal"],
                            ),
                            exact_d,
                            strict=True,
                        )
                    ),
                    default=Decimal(0),
                )
                d_bounds = [
                    _decimal_sum(
                        (
                            product_bounds["t_constraint"][index],
                            product_bounds["t_bottom"][index],
                            product_bounds["t_top"][index],
                            _decimal_complex_modulus(
                                _decimal_complex_pair(w_value)
                            ),
                            _decimal_complex_modulus(
                                _decimal_complex_pair(r_value)
                            ),
                        )
                    )
                    for index, (w_value, r_value) in enumerate(
                        zip(actual_w, actual_r, strict=True)
                    )
                ]
                d_bound = max(
                    d_bounds,
                    default=Decimal(0),
                )
            d_allowed = Decimal(512) * epsilon * d_bound
            return {
                "arithmetic": "Decimal.from_float matrix products and ordered sums",
                "input_identity": capture.get("capture_identity"),
                "source_modal_rhs_zero": bool(np.all(actual_r == 0.0)),
                "components": component_rows,
                "d_exact_decimal_max_abs_error": str(d_error),
                "d_roundoff_bound_decimal": str(d_allowed),
                "d_roundoff_bound_formula": (
                    "512*eps*max_i(sum_j(|C_ij||a_j| + "
                    "|Gbottom_ij||xbottom_j| + |Gtop_ij||xtop_j|) "
                    "+ |r_i| + |w_i|)"
                ),
                "d_within_roundoff_bound": bool(d_error <= d_allowed),
            }

        diagnostic_rhs_values = np.zeros(
            layout.global_size, dtype=np.complex128
        )
        diagnostic_rhs_values[bottom_indices] = side_bottom_rhs
        diagnostic_rhs_values[top_indices] = side_top_rhs
        _set_vector(diagnostic_rhs, diagnostic_rhs_values)
        diagnostic_initial_rhs = _gather_vector(diagnostic_rhs)
        diagnostic_initial_modal = diagnostic_initial_rhs[modal_indices].copy()
        diagnostic_initial_side = diagnostic_initial_rhs[
            np.concatenate((bottom_indices, top_indices))
        ].copy()
        assert np.all(diagnostic_initial_modal == 0.0)
        assert float(np.linalg.norm(diagnostic_initial_side)) > 0.0

        original_diagnostic_apply = context.apply
        original_diagnostic_callback = context._v13_original_modal_row_callback
        original_diagnostic_row_recorder = (
            modal_system.record_original_modal_row
        )
        active_diagnostic_capture: Mapping[str, Any] | None = None

        def diagnostic_action_identity(
            capture_identity: Any,
            binding_record: Mapping[str, Any] | None = None,
        ) -> dict[str, Any]:
            binding = (
                binding_record
                if isinstance(binding_record, Mapping)
                else active_diagnostic_record
            )
            return diagnostic_jsonable(
                {
                    "capture_identity": capture_identity,
                    "diagnostic_apply_index": (
                        None
                        if not isinstance(binding, Mapping)
                        else binding.get("diagnostic_apply_index")
                    ),
                    "attempted_production_pc_apply_index": (
                        None
                        if not isinstance(binding, Mapping)
                        else binding.get("attempted_production_pc_apply_index")
                    ),
                    "source_object_id": (
                        None
                        if not isinstance(binding, Mapping)
                        else binding.get("source_object_id")
                    ),
                    "target_object_id": (
                        None
                        if not isinstance(binding, Mapping)
                        else binding.get("target_object_id")
                    ),
                    "source_petsc_handle": (
                        None
                        if not isinstance(binding, Mapping)
                        else binding.get("source_petsc_handle")
                    ),
                    "target_petsc_handle": (
                        None
                        if not isinstance(binding, Mapping)
                        else binding.get("target_petsc_handle")
                    ),
                }
            )

        def diagnostic_callback(*args: Any, **kwargs: Any) -> Any:
            nonlocal active_diagnostic_capture
            try:
                result = original_diagnostic_callback(*args, **kwargs)
            except Exception as exc:
                if active_diagnostic_record is not None:
                    callback_error = diagnostic_exception(exc)
                    diagnostic_capture(
                        active_diagnostic_record,
                        "callback_exception",
                        lambda: callback_error,
                    )
                raise
            if active_diagnostic_record is not None:
                try:
                    owned_capture = dict(result)
                    for name in (
                        "r_modal",
                        "w_modal",
                        "t_bottom",
                        "t_top",
                        "t_constraint",
                    ):
                        owned_capture[name] = np.asarray(
                            result[name], dtype=np.complex128
                        ).copy()
                    active_diagnostic_capture = owned_capture
                    callback_action_identity = diagnostic_action_identity(
                        owned_capture.get("capture_identity")
                    )
                    active_diagnostic_record[
                        "callback_action_identity"
                    ] = callback_action_identity
                    active_diagnostic_record["callback_capture_attempt_index"] = (
                        owned_capture.get("capture_identity", {}).get("attempt_index")
                    )
                    active_diagnostic_record.setdefault(
                        "capture_timeline", []
                    ).append(
                        {
                            "event": "callback_returned_arrays_copied",
                            "diagnostic_apply_index": active_diagnostic_record.get(
                                "diagnostic_apply_index"
                            ),
                            "attempted_production_pc_apply_index": (
                                active_diagnostic_record.get(
                                    "attempted_production_pc_apply_index"
                                )
                            ),
                            "attempt_index": (
                                callback_action_identity.get("capture_identity", {}).get(
                                    "attempt_index"
                                )
                                if isinstance(
                                    callback_action_identity.get("capture_identity"),
                                    Mapping,
                                )
                                else None
                            ),
                            "action_identity": callback_action_identity,
                        }
                    )
                except Exception as exc:  # noqa: BLE001 - observer must not alter the production gate
                    active_diagnostic_capture = None
                    copy_error = diagnostic_exception(exc)
                    diagnostic_capture(
                        active_diagnostic_record,
                        "callback_owned_copy_error",
                        lambda: copy_error,
                    )
                diagnostic_capture(
                    active_diagnostic_record,
                    "callback_result",
                    lambda: {
                        "capture_identity": result.get("capture_identity"),
                        "arrays_real_imag": {
                            name: result.get(name)
                            for name in (
                                "r_modal",
                                "w_modal",
                                "t_bottom",
                                "t_top",
                                "t_constraint",
                            )
                        },
                        "capture_timeline": list(
                            active_diagnostic_record.get("capture_timeline", [])
                        ),
                    },
                )
                if active_diagnostic_capture is not None:
                    diagnostic_capture(
                        active_diagnostic_record,
                        "decimal_original_A_oracle",
                        lambda: diagnostic_decimal_matrix_oracle(
                            args[0], args[1], active_diagnostic_capture
                        ),
                    )
            return result

        def diagnostic_row_recorder(
            record: Mapping[str, Any], arrays: Mapping[str, np.ndarray] | None = None
        ) -> None:
            frozen_before_commit = modal_system.frozen_original_modal_row()
            frozen_record_before_commit = (
                None
                if not isinstance(frozen_before_commit, Mapping)
                else frozen_before_commit.get("record")
            )
            frozen_arrays_before_commit = (
                None
                if not isinstance(frozen_before_commit, Mapping)
                else frozen_before_commit.get("arrays")
            )
            previous_frozen_attempt_before_commit = (
                frozen_record_before_commit.get("attempt_index")
                if isinstance(frozen_record_before_commit, Mapping)
                else None
            )
            if arrays is not None:
                commit_arrays: Mapping[str, np.ndarray] | None = arrays
                commit_arrays_source = "record_arrays_argument"
            elif (
                previous_frozen_attempt_before_commit == record.get("attempt_index")
                and isinstance(frozen_arrays_before_commit, Mapping)
            ):
                commit_arrays = frozen_arrays_before_commit
                commit_arrays_source = "prior_frozen_arrays_same_attempt"
            else:
                commit_arrays = None
                commit_arrays_source = "unavailable"
            if active_diagnostic_record is not None:
                diagnostic_capture(
                    active_diagnostic_record,
                    "original_modal_row_record",
                    lambda: dict(record),
                )
                diagnostic_capture(
                    active_diagnostic_record,
                    "original_modal_row_arrays_real_imag",
                    lambda: {} if arrays is None else dict(arrays),
                )
                diagnostic_capture(
                    active_diagnostic_record,
                    "owner_schur_solve_audit_at_row",
                    lambda: modal_system.diagnostics.get("last_solve"),
                )
                diagnostic_capture(
                    active_diagnostic_record,
                    "side_operation_counts_at_row",
                    diagnostic_side_counts,
                )
            original_diagnostic_row_recorder(record, arrays)
            if active_diagnostic_record is not None:
                capture = active_diagnostic_capture
                current_attempt = record.get("attempt_index")
                capture_identity = (
                    None
                    if not isinstance(capture, Mapping)
                    else capture.get("capture_identity")
                )
                callback_attempt = (
                    capture_identity.get("attempt_index")
                    if isinstance(capture_identity, Mapping)
                    else None
                )
                frozen = modal_system.frozen_original_modal_row()
                frozen_record = (
                    None
                    if not isinstance(frozen, Mapping)
                    else frozen.get("record")
                )
                frozen_arrays = (
                    None
                    if not isinstance(frozen, Mapping)
                    else frozen.get("arrays")
                )
                frozen_attempt = (
                    frozen_record.get("attempt_index")
                    if isinstance(frozen_record, Mapping)
                    else None
                )
                row_action_identity = diagnostic_action_identity(
                    record.get("capture_identity")
                )
                frozen_action_identity = diagnostic_action_identity(
                    None
                    if not isinstance(frozen_record, Mapping)
                    else frozen_record.get("capture_identity")
                )
                active_diagnostic_record.setdefault(
                    "capture_timeline", []
                ).append(
                    {
                        "event": "production_row_record_committed",
                        "diagnostic_apply_index": active_diagnostic_record.get(
                            "diagnostic_apply_index"
                        ),
                        "attempted_production_pc_apply_index": (
                            active_diagnostic_record.get(
                                "attempted_production_pc_apply_index"
                            )
                        ),
                        "attempt_index": current_attempt,
                        "action_identity": row_action_identity,
                        "frozen_record_attempt_index_after_delegate": frozen_attempt,
                    }
                )
                previous_attempt = active_diagnostic_record.get(
                    "prior_committed_row_attempt_index_before_apply"
                )
                capture_arrays = (
                    {}
                    if not isinstance(capture, Mapping)
                    else capture
                )
                actual_arrays = {} if commit_arrays is None else commit_arrays
                stored_d = (
                    frozen_arrays.get("d")
                    if isinstance(frozen_arrays, Mapping)
                    else None
                )
                actual_d = actual_arrays.get("d")
                current_w = capture_arrays.get("w_modal")
                current_r = capture_arrays.get("r_modal")
                try:
                    can_compare = all(
                        isinstance(value, np.ndarray)
                        for value in (actual_d, current_w, current_r)
                    )
                    current_expected_d = (
                        np.subtract(current_w, current_r)
                        if can_compare
                        else None
                    )
                    binary64_matches = bool(
                        can_compare
                        and np.array_equal(actual_d, current_expected_d)
                    )
                    frozen_arrays_match = (
                        None
                        if stored_d is None
                        else bool(np.array_equal(stored_d, actual_d))
                    )
                except Exception as compare_error:  # noqa: BLE001 - diagnostic result only
                    can_compare = False
                    binary64_matches = False
                    frozen_arrays_match = False
                    compare_error_record = diagnostic_exception(compare_error)
                else:
                    compare_error_record = None
                callback_action_identity = active_diagnostic_record.get(
                    "callback_action_identity"
                )
                identity_matches = bool(
                    isinstance(capture_identity, Mapping)
                    and isinstance(record.get("capture_identity"), Mapping)
                    and isinstance(frozen_record, Mapping)
                    and callback_attempt == current_attempt == frozen_attempt
                    and record.get("capture_identity", {}).get("attempt_index")
                    == callback_attempt
                    and frozen_record.get("capture_identity", {}).get("attempt_index")
                    == callback_attempt
                    and row_action_identity == callback_action_identity
                    and frozen_action_identity == callback_action_identity
                )
                prior_attempt_not_reused = (
                    previous_attempt is None or previous_attempt != callback_attempt
                )
                check = {
                    "status": (
                        "passed"
                        if can_compare
                        and binary64_matches
                        and frozen_arrays_match is not False
                        and identity_matches
                        and prior_attempt_not_reused
                        else "failed"
                    ),
                    "diagnostic_apply_index": active_diagnostic_record.get(
                        "diagnostic_apply_index"
                    ),
                    "attempted_production_pc_apply_index": (
                        active_diagnostic_record.get(
                            "attempted_production_pc_apply_index"
                        )
                    ),
                    "callback_attempt_index": callback_attempt,
                    "row_record_attempt_index": current_attempt,
                    "attempt_index": current_attempt,
                    "frozen_record_attempt_index_after_delegate": frozen_attempt,
                    "prior_committed_row_attempt_index_before_apply": previous_attempt,
                    "prior_attempt_was_not_used": prior_attempt_not_reused,
                    "callback_row_frozen_identity_matches": identity_matches,
                    "binary64_d_equals_w_minus_r": binary64_matches,
                    "frozen_d_matches_checked_d": frozen_arrays_match,
                    "d_source": commit_arrays_source,
                    "same_attempt_d_source_index": current_attempt,
                    "action_identity": callback_action_identity,
                    "compared_only_after_production_record_delegate": True,
                }
                if compare_error_record is not None:
                    check["comparison_error"] = compare_error_record
                active_diagnostic_record.setdefault(
                    "same_attempt_binary64_d_checks", []
                ).append(check)
                active_diagnostic_record.setdefault(
                    "capture_timeline", []
                ).append(
                    {
                        "event": "same_attempt_d_checked_after_record_commit",
                        "diagnostic_apply_index": active_diagnostic_record.get(
                            "diagnostic_apply_index"
                        ),
                        "attempted_production_pc_apply_index": (
                            active_diagnostic_record.get(
                                "attempted_production_pc_apply_index"
                            )
                        ),
                        "attempt_index": current_attempt,
                        "action_identity": callback_action_identity,
                        "status": check["status"],
                    }
                )

        def diagnostic_apply(
            pc: PETSc.PC | None,
            pc_source: PETSc.Vec,
            pc_target: PETSc.Vec,
        ) -> None:
            nonlocal active_diagnostic_capture, active_diagnostic_record
            nonlocal diagnostic_apply_count
            diagnostic_apply_count += 1
            capture_this_attempt = diagnostic_apply_count <= 2
            source_handle = diagnostic_petsc_handle(pc_source)
            target_handle = diagnostic_petsc_handle(pc_target)
            prior_frozen = modal_system.frozen_original_modal_row()
            prior_record = (
                None
                if not isinstance(prior_frozen, Mapping)
                else prior_frozen.get("record")
            )
            record: dict[str, Any] = {
                "rank": int(comm.rank),
                "diagnostic_apply_index": diagnostic_apply_count,
                "production_pc_apply_count_before": int(context._pc_apply_count),
                "attempted_production_pc_apply_index": int(
                    context._pc_apply_count + 1
                ),
                "source_object_id": id(pc_source),
                "target_object_id": id(pc_target),
                "source_target_same_object": pc_source is pc_target,
                "source_target_same_petsc_handle": (
                    None
                    if source_handle is None or target_handle is None
                    else source_handle == target_handle
                ),
                "prior_committed_row_attempt_index_before_apply": (
                    prior_record.get("attempt_index")
                    if isinstance(prior_record, Mapping)
                    else None
                ),
                "capture_timeline": [],
                "same_attempt_binary64_d_checks": [],
            }
            source_modal_local = np.asarray(
                pc_source.getArray(readonly=True), dtype=np.complex128
            )[layout.local_modal_slice]
            record["pc_source_modal_local_size"] = int(source_modal_local.size)
            record["pc_source_modal_exact_zero"] = bool(
                np.all(source_modal_local == 0.0)
            )
            record["source_petsc_handle"] = source_handle
            record["target_petsc_handle"] = target_handle
            if capture_this_attempt:
                diagnostic_capture(
                    record,
                    "source_before",
                    lambda: diagnostic_vector_snapshot(pc_source),
                )
                diagnostic_capture(
                    record,
                    "target_before",
                    lambda: diagnostic_vector_snapshot(pc_target),
                )
                diagnostic_capture(
                    record,
                    "owner_schur_solve_audit_before",
                    lambda: modal_system.diagnostics.get("last_solve"),
                )
                diagnostic_capture(
                    record,
                    "side_operation_counts_before",
                    diagnostic_side_counts,
                )
                diagnostic_records.append(record)
            active_diagnostic_capture = None
            active_diagnostic_record = record if capture_this_attempt else None
            try:
                original_diagnostic_apply(pc, pc_source, pc_target)
            except Exception as exc:
                apply_error = diagnostic_exception(exc)
                diagnostic_capture(
                    record,
                    "apply_exception",
                    lambda: apply_error,
                )
                raise
            finally:
                if capture_this_attempt:
                    diagnostic_capture(
                        record,
                        "source_after",
                        lambda: diagnostic_vector_snapshot(pc_source),
                    )
                    diagnostic_capture(
                        record,
                        "target_after",
                        lambda: diagnostic_vector_snapshot(pc_target),
                    )
                    diagnostic_capture(
                        record,
                        "production_pc_apply_count_after",
                        lambda: int(context._pc_apply_count),
                    )
                    diagnostic_capture(
                        record,
                        "owner_schur_solve_audit_after",
                        lambda: modal_system.diagnostics.get("last_solve"),
                    )
                    diagnostic_capture(
                        record,
                        "side_operation_counts_after",
                        diagnostic_side_counts,
                    )
                    if record.get("original_modal_row_record") is not None:
                        try:
                            receipt = write_diagnostic_mini_record(record)
                            record["mini_snapshot_receipt"] = diagnostic_jsonable(
                                receipt
                            )
                            if receipt.get("status") != "written":
                                record.setdefault("capture_errors", []).append(
                                    {
                                        "type": "MiniRecordWriteFailed",
                                        "message": str(receipt.get("error"))[:1000],
                                        "secondary": True,
                                    }
                                )
                        except BaseException as exc:  # noqa: BLE001 - keep apply failure primary
                            record.setdefault("capture_errors", []).append(
                                {
                                    "type": type(exc).__name__,
                                    "message": str(exc)[:1000],
                                    "secondary": True,
                                }
                            )
                active_diagnostic_record = None

        diagnostic_ksp_reason: int | None = None
        diagnostic_ksp_iterations: int | None = None
        diagnostic_rhs_norm: float | None = None
        diagnostic_ax_minus_f_numerator: float | None = None
        diagnostic_true_relative_residual: float | None = None
        diagnostic_primary_exception: dict[str, str] | None = None
        diagnostic_write_result: dict[str, Any] | None = None
        diagnostic_evidence_written = False
        diagnostic_rhs_before = diagnostic_initial_rhs.copy()
        diagnostic_residual = diagnostic_rhs.duplicate()
        try:
            diagnostic_ksp.setOperators(original_operator)
            diagnostic_ksp.setType(PETSc.KSP.Type.FGMRES)
            diagnostic_ksp.setGMRESRestart(layout.global_size)
            diagnostic_ksp.setPCSide(PETSc.PC.Side.RIGHT)
            diagnostic_ksp.setNormType(PETSc.KSP.NormType.UNPRECONDITIONED)
            diagnostic_ksp.setInitialGuessNonzero(False)
            diagnostic_ksp.setTolerances(
                rtol=5.0e-9,
                atol=0.0,
                max_it=2 * layout.global_size,
            )
            diagnostic_pc = diagnostic_ksp.getPC()
            diagnostic_pc.setType(PETSc.PC.Type.PYTHON)
            diagnostic_pc.setPythonContext(BorrowedV13BlockLduPc())
            with monkeypatch.context() as diagnostic_patch:
                diagnostic_patch.setattr(context, "apply", diagnostic_apply)
                diagnostic_patch.setattr(
                    context,
                    "_v13_original_modal_row_callback",
                    diagnostic_callback,
                )
                diagnostic_patch.setattr(
                    modal_system,
                    "record_original_modal_row",
                    diagnostic_row_recorder,
                )
                diagnostic_ksp.setUp()
                try:
                    diagnostic_ksp.solve(diagnostic_rhs, diagnostic_solution)
                except BaseException as exc:
                    diagnostic_primary_exception = diagnostic_exception(exc)
                    raise
            diagnostic_ksp_reason = int(diagnostic_ksp.getConvergedReason())
            diagnostic_ksp_iterations = int(diagnostic_ksp.getIterationNumber())
            original_operator.mult(diagnostic_solution, diagnostic_residual)
            diagnostic_residual.axpy(
                PETSc.ScalarType(-1.0), diagnostic_rhs
            )
            diagnostic_rhs_norm = float(diagnostic_rhs.norm())
            diagnostic_ax_minus_f_numerator = float(diagnostic_residual.norm())
            diagnostic_true_relative_residual = (
                diagnostic_ax_minus_f_numerator / diagnostic_rhs_norm
                if diagnostic_rhs_norm > 0.0
                else None
            )
            diagnostic_rhs_after = _gather_vector(diagnostic_rhs)
            for record in diagnostic_records:
                row = record.get("original_modal_row_record")
                record["capture_timeline_validation"] = (
                    _validate_v15_capture_timeline(
                        record.get("capture_timeline"),
                        record.get("same_attempt_binary64_d_checks"),
                        diagnostic_apply_index=int(
                            record.get("diagnostic_apply_index", -1)
                        ),
                        attempted_production_pc_apply_index=int(
                            record.get("attempted_production_pc_apply_index", -1)
                        ),
                        expected_attempt_index=(
                            int(row.get("attempt_index", -1))
                            if isinstance(row, Mapping)
                            else -1
                        ),
                        prior_attempt_index=record.get(
                            "prior_committed_row_attempt_index_before_apply"
                        ),
                        expected_action_identity=(
                            diagnostic_action_identity(
                                row.get("capture_identity"), record
                            )
                            if isinstance(row, Mapping)
                            else None
                        ),
                    )
                )

            diagnostic_evidence = {
                "schema": "task041.v15.zero_modal_rhs_right_fgmres_capture.v1",
                "classification": (
                    "solve_exception_before_ax_minus_f"
                    if diagnostic_primary_exception is not None
                    else "right_fgmres_diagnostic_captured_before_assertions"
                ),
                "bound": "one fixed tiny RHS solve; max_it=2*layout.global_size",
                "source_sha256": supervisor_binding["source_sha"],
                "invocation_id": supervisor_binding["invocation_id"],
                "modal_layout": {
                    "modal_owner": int(layout.modal_owner),
                    "modal_count": int(layout.modal_count),
                    "global_size": int(layout.global_size),
                    "modal_indices": [int(value) for value in modal_indices],
                },
                "initial_modal_rhs_exact_zero": bool(
                    np.all(diagnostic_initial_modal == 0.0)
                ),
                "initial_side_rhs_norm": float(
                    np.linalg.norm(diagnostic_initial_side)
                ),
                "captured_first_applications_only": 2,
                "total_pc_application_count": diagnostic_apply_count,
                "captured_pc_application_count": len(diagnostic_records),
                "ksp_reason": diagnostic_ksp_reason,
                "ksp_iterations": diagnostic_ksp_iterations,
                "ax_minus_f_numerator_norm": diagnostic_ax_minus_f_numerator,
                "rhs_denominator_norm": diagnostic_rhs_norm,
                "ax_minus_f_relative_residual": diagnostic_true_relative_residual,
                "rhs_unchanged_after_solve": bool(
                    np.array_equal(diagnostic_rhs_after, diagnostic_rhs_before)
                ),
                "primary_solve_exception": diagnostic_primary_exception,
                "captured_applications": diagnostic_records,
            }
            all_rank_diagnostics = comm.gather(
                diagnostic_jsonable(diagnostic_evidence), root=0
            )
            diagnostic_write_result = None
            if comm.rank == 0:
                try:
                    diagnostic_json_path = (
                        evidence_root
                        / "TASK041_V15_MODAL_ROW_ZERO_RHS_RIGHT_FGMRES.json"
                    )
                    diagnostic_json_path.write_text(
                        json.dumps(
                            {
                                "schema": "task041.v15.zero_modal_rhs_right_fgmres_capture.v1",
                                "rank_rows": all_rank_diagnostics,
                            },
                            sort_keys=True,
                            indent=2,
                            allow_nan=False,
                        )
                        + "\n",
                        encoding="utf-8",
                    )
                    diagnostic_write_result = {
                        "status": "written",
                        "path": str(diagnostic_json_path),
                        "sha256": hashlib.sha256(
                            diagnostic_json_path.read_bytes()
                        ).hexdigest(),
                    }
                    diagnostic_evidence_written = True
                except Exception as exc:  # noqa: BLE001 - the numerical/timeline result remains primary
                    diagnostic_write_result = {
                        "status": "failed",
                        "error": diagnostic_exception(exc),
                    }
            diagnostic_write_result = comm.bcast(
                diagnostic_write_result, root=0
            )
            diagnostic_evidence_written = bool(
                isinstance(diagnostic_write_result, Mapping)
                and diagnostic_write_result.get("status") == "written"
            )

            # Numeric and same-attempt identity results have been persisted before
            # assertions; writer errors are checked only after those primary gates.
            assert diagnostic_ksp_reason is not None and diagnostic_ksp_reason > 0
            assert diagnostic_ksp_iterations is not None
            assert diagnostic_ksp_iterations >= 2
            assert diagnostic_apply_count >= 2
            assert len(diagnostic_records) == 2
            assert diagnostic_records[0]["pc_source_modal_exact_zero"] is True
            assert diagnostic_records[0]["pc_source_modal_local_size"] == (
                internal_count if comm.rank == layout.modal_owner else 0
            )
            assert diagnostic_rhs_norm is not None and diagnostic_rhs_norm > 0.0
            assert diagnostic_ax_minus_f_numerator is not None
            assert diagnostic_true_relative_residual is not None
            assert np.isfinite(diagnostic_ax_minus_f_numerator)
            assert np.isfinite(diagnostic_true_relative_residual)
            assert diagnostic_true_relative_residual <= 5.0e-9
            np.testing.assert_array_equal(diagnostic_rhs_after, diagnostic_rhs_before)
            for record in diagnostic_records:
                row = record.get("original_modal_row_record")
                assert isinstance(row, Mapping)
                assert row.get("status") == "passed"
                assert row.get("capture_identity", {}).get("attempt_index") == (
                    row.get("attempt_index")
                )
                assert row.get("same_attempt_owner_solve") is True
                assert row.get("owner_lu_solve_record", {}).get("status") == "passed"
                assert len(row.get("attempt_binding_by_rank", [])) == comm.size
                assert row.get("successful_pc_apply_count_before") == (
                    record["production_pc_apply_count_before"]
                )
                capture_identity = row["capture_identity"]
                assert len(capture_identity["matmult_call_id_by_rank"]) == comm.size
                assert len(set(capture_identity["matmult_call_id_by_rank"])) == 1
                assert capture_identity["pc_source_unchanged_by_rank"] == [
                    True
                ] * comm.size
                assert capture_identity[
                    "pc_target_unchanged_by_original_A_by_rank"
                ] == [True] * comm.size
                assert row["outer_iteration"] == {
                    "status": "not_available_inside_pc_apply",
                    "value": None,
                }
                norms = row["metrics"].get("absolute_l2_norms")
                log_norms = row["metrics"].get("absolute_l2_log_norms")
                assert isinstance(norms, Mapping)
                assert isinstance(log_norms, Mapping)
                assert set(norms) == {
                    "r_modal",
                    "w_modal",
                    "d_w_minus_r",
                    "t_bottom",
                    "t_top",
                    "t_constraint",
                }
                assert all(
                    value is None
                    or (isinstance(value, (int, float)) and np.isfinite(value))
                    for value in norms.values()
                )
                oracle = record.get("decimal_original_A_oracle")
                assert isinstance(oracle, Mapping)
                assert oracle.get("d_within_roundoff_bound") is True
                assert all(
                    row.get("status") == "passed"
                    for row in oracle["components"].values()
                )
                assert record.get("capture_timeline_validation", {}).get(
                    "status"
                ) == "passed"
                assert all(
                    item.get("status") == "passed"
                    and item.get("binary64_d_equals_w_minus_r") is True
                    and item.get("prior_attempt_was_not_used") is True
                    and item.get(
                        "compared_only_after_production_record_delegate"
                    ) is True
                    for item in record.get("same_attempt_binary64_d_checks", [])
                )
            assert all(
                record["production_pc_apply_count_after"]
                == record["production_pc_apply_count_before"] + 1
                for record in diagnostic_records
            )
            # Capture/snapshot writer failures are secondary to numeric and
            # timeline failures and therefore asserted only now.
            assert diagnostic_write_result is not None
            assert diagnostic_write_result.get("status") == "written"
            for record in diagnostic_records:
                assert record.get("capture_errors", []) == []
                assert record.get("mini_snapshot_receipt", {}).get(
                    "status"
                ) == "written"
        finally:
            cleanup_primary = sys.exc_info()[1]
            diagnostic_status_capture_errors: list[dict[str, str]] = []
            if not diagnostic_evidence_written:
                try:
                    if diagnostic_ksp_reason is None:
                        try:
                            diagnostic_ksp_reason = int(
                                diagnostic_ksp.getConvergedReason()
                            )
                        except BaseException as status_error:  # noqa: BLE001 - secondary evidence only
                            diagnostic_status_capture_errors.append(
                                diagnostic_exception(status_error)
                            )
                    if diagnostic_ksp_iterations is None:
                        try:
                            diagnostic_ksp_iterations = int(
                                diagnostic_ksp.getIterationNumber()
                            )
                        except BaseException as status_error:  # noqa: BLE001 - secondary evidence only
                            diagnostic_status_capture_errors.append(
                                diagnostic_exception(status_error)
                            )
                    partial = {
                        "schema": "task041.v15.zero_modal_rhs_right_fgmres_rank_partial.v1",
                        "classification": "finally_capture_before_assertions_or_after_exception",
                        "source_sha256": supervisor_binding["source_sha"],
                        "invocation_id": supervisor_binding["invocation_id"],
                        "rank": int(comm.rank),
                        "ksp_reason": diagnostic_ksp_reason,
                        "ksp_iterations": diagnostic_ksp_iterations,
                        "ax_minus_f_numerator_norm": diagnostic_ax_minus_f_numerator,
                        "rhs_denominator_norm": diagnostic_rhs_norm,
                        "ax_minus_f_relative_residual": diagnostic_true_relative_residual,
                        "primary_solve_exception": diagnostic_primary_exception,
                        "status_capture_errors": diagnostic_status_capture_errors,
                        "captured_applications": diagnostic_records,
                    }
                    partial_path = evidence_root / (
                        "TASK041_V15_MODAL_ROW_ZERO_RHS_RIGHT_FGMRES_"
                        f"rank-{comm.rank}.json"
                    )
                    temporary_path = partial_path.with_name(
                        partial_path.name + ".tmp"
                    )
                    with temporary_path.open("xb") as stream:
                        stream.write(
                            (
                                json.dumps(
                                    diagnostic_jsonable(partial),
                                    sort_keys=True,
                                    indent=2,
                                    allow_nan=False,
                                )
                                + "\n"
                            ).encode("utf-8")
                        )
                        stream.flush()
                        os.fsync(stream.fileno())
                    os.replace(temporary_path, partial_path)
                except BaseException as writer_error:  # noqa: BLE001 - cleanup/writer never masks primary
                    if diagnostic_records:
                        diagnostic_records[0].setdefault(
                            "capture_errors", []
                        ).append(
                            {
                                "type": type(writer_error).__name__,
                                "message": str(writer_error)[:1000],
                                "secondary": True,
                            }
                        )
            cleanup_errors: list[BaseException] = []
            for owned_object in (
                diagnostic_ksp,
                diagnostic_residual,
                diagnostic_rhs,
                diagnostic_solution,
            ):
                try:
                    owned_object.destroy()
                except BaseException as cleanup_error:  # noqa: BLE001 - preserve primary solve/assertion
                    cleanup_errors.append(cleanup_error)
            if cleanup_errors:
                first_cleanup_error = cleanup_errors[0]
                if cleanup_primary is not None:
                    cleanup_primary.add_note(
                        "diagnostic PETSc cleanup error preserved as secondary: "
                        f"{type(first_cleanup_error).__name__}: "
                        f"{str(first_cleanup_error)[:500]}"
                    )
                else:
                    raise first_cleanup_error

        def assert_collective_gate_reject(label: str) -> list[str]:
            local_error = None
            matmult_count_before = original_a_context._matmult_call_count
            try:
                context.apply(None, source, target)
            except FloatingPointError as exc:
                local_error = {
                    "type": type(exc).__name__,
                    "message": str(exc),
                }
            except Exception as exc:  # noqa: BLE001 - report wrong failure class collectively
                local_error = {
                    "type": type(exc).__name__,
                    "message": str(exc),
                }
            rank_errors = comm.allgather(local_error)
            assert all(isinstance(item, Mapping) for item in rank_errors), label
            assert len({item["message"] for item in rank_errors}) == 1, label
            assert all(item["type"] == "FloatingPointError" for item in rank_errors), label
            assert "original global modal-row" in rank_errors[0]["message"], label
            assert original_a_context._matmult_call_count == matmult_count_before + 1, label
            return [str(item["message"]) for item in rank_errors]

        # Corrupt the real MatPython context's copied C input on every rank.
        # HybridBlockOperator has no Mat.setValues callback; the actual
        # original-A MatMult and its armed capture/check remain in the path.
        original_a_context = original_operator.getPythonContext()
        original_constraint = original_a_context.modal_constraint
        saved_constraint_entry = complex(original_constraint[0, 0])
        set_source(
            np.asarray([0.2 - 0.15j] + [0.0j] * (internal_count - 1))
        )
        try:
            original_constraint[0, 0] = -saved_constraint_entry
            if inject_owner_writer_failure:
                owner_writer_failure_armed = True
            wrong_sign_errors = assert_collective_gate_reject("wrong-sign C input")
        finally:
            original_constraint[0, 0] = saved_constraint_entry
        wrong_sign_record = modal_system.diagnostics["last_original_modal_row"]
        assert wrong_sign_record["status"] == "rejected"
        assert wrong_sign_record["metrics"]["eta_terms_inf"] > 1.0e-10
        if inject_owner_writer_failure:
            writer_failure_armed_by_rank = comm.allgather(
                owner_writer_failure_armed
            )
            expected_writer_failure_armed_by_rank = [
                rank != modal_system.modal_owner for rank in range(comm.size)
            ]
            assert all(type(value) is bool for value in writer_failure_armed_by_rank)
            assert writer_failure_armed_by_rank == expected_writer_failure_armed_by_rank
            assert all(error == wrong_sign_errors[0] for error in wrong_sign_errors)
            assert "secondary evidence writer error(s)" in wrong_sign_errors[0]
            assert "injected real tiny owner snapshot failure" in wrong_sign_errors[0]
            assert wrong_sign_record["writer_errors"]
            failure_system = modal_system
            frozen_before_destroy = failure_system.frozen_original_modal_row()
            context.destroy()
            context = None
            frozen_after_destroy = failure_system.frozen_original_modal_row()
            assert failure_system._destroyed is True
            assert frozen_before_destroy["record"] == frozen_after_destroy["record"]
            assert frozen_after_destroy["record"]["status"] == "rejected"
            assert frozen_after_destroy["record"]["attempt_index"] == (
                wrong_sign_record["attempt_index"]
            )
            assert frozen_after_destroy["arrays"] is not None
            np.testing.assert_array_equal(
                frozen_after_destroy["arrays"]["d"],
                frozen_before_destroy["arrays"]["d"],
            )
            assert frozen_after_destroy["record"]["writer_errors"]
        else:
            context.apply(None, source, target)
            assert modal_system.diagnostics["last_original_modal_row"]["status"] == (
                "passed"
            )

            # A channel swap changes the actual fixture projection inputs
            # consumed by the same production MatMult, then restores them.
            bottom_projection_input = coupling.bottom.projection
            top_projection_input = coupling.top.projection
            set_source(np.zeros(internal_count, dtype=np.complex128))
            try:
                coupling.bottom.projection = top_projection_input
                coupling.top.projection = bottom_projection_input
                wrong_channel_errors = assert_collective_gate_reject(
                    "swapped bottom/top projection inputs"
                )
            finally:
                coupling.bottom.projection = bottom_projection_input
                coupling.top.projection = top_projection_input
            wrong_channel_record = modal_system.diagnostics[
                "last_original_modal_row"
            ]
            assert wrong_channel_record["status"] == "rejected"
            assert wrong_channel_record["metrics"]["eta_terms_inf"] > 1.0e-10
            assert len(set(wrong_channel_errors)) == 1
            context.apply(None, source, target)
            assert modal_system.diagnostics["last_original_modal_row"]["status"] == (
                "passed"
            )

            # Omission and contamination mutate an existing fixture projection
            # entry collectively.  No MatPython setValue/setValues surrogate
            # is involved; each case restores the exact coefficient.
            nonzero_projection_entries = np.argwhere(
                np.abs(bottom_projection_dense) > 0.0
            )
            selected_projection_entry = next(
                (int(row), int(column))
                for row, column in nonzero_projection_entries
                if abs(side_bottom_rhs[int(column)]) > 0.0
            )
            projection_row, projection_column = selected_projection_entry
            original_projection_value = complex(
                bottom_projection_dense[projection_row, projection_column]
            )
            projection_row_start, projection_row_end = (
                int(value)
                for value in bottom_projection.getOwnershipRange()
            )

            def set_bottom_projection_entry(value: complex) -> None:
                if projection_row_start <= projection_row < projection_row_end:
                    bottom_projection.setValue(
                        projection_row,
                        projection_column,
                        PETSc.ScalarType(value),
                    )
                bottom_projection.assemble()

            set_source(np.zeros(internal_count, dtype=np.complex128))
            try:
                set_bottom_projection_entry(0.0)
                omission_errors = assert_collective_gate_reject(
                    "omitted bottom projection coefficient"
                )
            finally:
                set_bottom_projection_entry(original_projection_value)
            omission_record = modal_system.diagnostics["last_original_modal_row"]
            assert omission_record["status"] == "rejected"
            assert omission_record["metrics"]["eta_terms_inf"] > 1.0e-10
            assert len(set(omission_errors)) == 1
            context.apply(None, source, target)
            assert modal_system.diagnostics["last_original_modal_row"]["status"] == (
                "passed"
            )

            try:
                set_bottom_projection_entry(original_projection_value + 0.37j)
                contamination_errors = assert_collective_gate_reject(
                    "contaminated bottom projection coefficient"
                )
            finally:
                set_bottom_projection_entry(original_projection_value)
            contamination_record = modal_system.diagnostics[
                "last_original_modal_row"
            ]
            assert contamination_record["status"] == "rejected"
            assert contamination_record["metrics"]["eta_terms_inf"] > 1.0e-10
            assert len(set(contamination_errors)) == 1
            context.apply(None, source, target)
            assert modal_system.diagnostics["last_original_modal_row"]["status"] == (
                "passed"
            )

        if context is not None:
            context.destroy()
        context = None
        assert bottom_action.audit["destroyed"] is True
        assert top_action.audit["destroyed"] is True
        assert bottom_operator.getSize() == (side_size, side_size)
        assert top_operator.getSize() == (side_size, side_size)
        for side in ("bottom", "top"):
            inverse = side_fixture[f"{side}_inverse"]
            assert inverse.diagnostics["destroyed"] is False
            assert inverse._p4_factor.destroy_count == 0
            assert inverse._h6._destroyed is False

        # A full-complex input must expose a channel/order error that is not
        # visible when checking only retained sample basis columns.
        wrong_bottom_action = CountingAction(bottom_B, side_fixture["bottom_inverse"])
        wrong_top_action = CountingAction(top_B, side_fixture["top_inverse"])
        side_actions.extend((wrong_bottom_action, wrong_top_action))
        original_apply = block_ldu.HybridActionModalSchurApply.apply
        wrong_probe = np.asarray(
            np.arange(1, internal_count + 1, dtype=np.float64)
            + 1j * (np.arange(internal_count, 0, -1, dtype=np.float64) + 0.5),
            dtype=np.complex128,
        )

        def wrong_full_action(action, modal):
            result = original_apply(action, modal)
            if np.array_equal(modal, wrong_probe):
                result = result.copy()
                result[-1] += 0.125 - 0.0625j
            return result

        with monkeypatch.context() as localized:
            localized.setattr(
                block_ldu.HybridActionModalSchurApply,
                "apply",
                wrong_full_action,
            )
            with pytest.raises(
                ValueError,
                match="independent full-complex action validation rejected x",
            ):
                block_ldu.build_task041_v13_consistent_modal_surrogate(
                    coupling,
                    wrong_bottom_action,
                    wrong_top_action,
                    modal_owner=comm.size - 1,
                    sampled_columns=columns,
                    sampled_column_roles=roles,
                    sampled_column_contract_sha256=contract_sha,
                    original_augmented_local_size=layout.local_size,
                    fresh_authority_callback=authority,
                )
        assert wrong_bottom_action.audit["apply_count"] == internal_count + 1
        assert wrong_top_action.audit["apply_count"] == internal_count + 1

        # A true singular Schur matrix must be rejected by the unmocked owner
        # factorization, rather than hidden by a regularization or mock LU.
        zero_bottom = dense_matrix(side_size, side_size, {})
        zero_top = dense_matrix(side_size, side_size, {})
        zero_bottom_action = CountingAction(
            zero_bottom, side_fixture["bottom_inverse"]
        )
        zero_top_action = CountingAction(zero_top, side_fixture["top_inverse"])
        side_actions.extend((zero_bottom_action, zero_top_action))
        singular_coupling = copy.copy(coupling)
        singular_coupling.bottom = SimpleNamespace(
            **{
                key: getattr(coupling.bottom, key)
                for key in (
                    "projection",
                    "positive_traction",
                    "negative_traction",
                    "modal_rhs_correction",
                )
            },
            positive_interior_correction=np.zeros(
                (modal_per_side, modal_per_side), dtype=np.complex128
            ),
            negative_interior_correction=np.zeros(
                (modal_per_side, modal_per_side), dtype=np.complex128
            ),
        )
        singular_coupling.top = SimpleNamespace(
            **{
                key: getattr(coupling.top, key)
                for key in (
                    "projection",
                    "positive_traction",
                    "negative_traction",
                    "modal_rhs_correction",
                )
            },
            positive_interior_correction=np.zeros(
                (modal_per_side, modal_per_side), dtype=np.complex128
            ),
            negative_interior_correction=np.zeros(
                (modal_per_side, modal_per_side), dtype=np.complex128
            ),
        )
        singular_coupling.propagation = SimpleNamespace(
            forward=SimpleNamespace(factors=np.ones(modal_per_side, dtype=np.complex128)),
            backward=SimpleNamespace(factors=np.ones(modal_per_side, dtype=np.complex128)),
        )
        singular_coupling.negative_trace_to_positive = np.eye(
            modal_per_side, dtype=np.complex128
        )
        with pytest.raises(ValueError, match="owner Schur factorization rejected"):
            block_ldu.build_task041_v13_consistent_modal_surrogate(
                singular_coupling,
                zero_bottom_action,
                zero_top_action,
                modal_owner=comm.size - 1,
                sampled_columns=columns,
                sampled_column_roles=roles,
                sampled_column_contract_sha256=contract_sha,
                original_augmented_local_size=layout.local_size,
                fresh_authority_callback=authority,
            )
        assert zero_bottom_action.audit["apply_count"] == internal_count + 7
        assert zero_top_action.audit["apply_count"] == internal_count + 7

        # Two repeatable but deliberately wrong owner solutions must fail the
        # original S_B a-g gate before a ready system can be returned.
        original_lu_solve = block_ldu.lu_solve

        def repeatable_wrong_lu_solve(_factor, rhs, **_kwargs):
            return np.zeros_like(rhs, dtype=np.complex128)

        refused_markers: list[tuple[str, dict[str, Any]]] = []
        with monkeypatch.context() as localized:
            localized.setattr(
                block_ldu, "lu_solve", repeatable_wrong_lu_solve
            )
            with pytest.raises(
                ValueError,
                match="owner Schur factorization rejected:.*S_B a-g residual gate failed",
            ):
                block_ldu.build_task041_v13_consistent_modal_surrogate(
                    coupling,
                    bottom_action,
                    top_action,
                    modal_owner=comm.size - 1,
                    sampled_columns=columns,
                    sampled_column_roles=roles,
                    sampled_column_contract_sha256=contract_sha,
                    original_augmented_local_size=layout.local_size,
                    fresh_authority_callback=authority,
                    marker_callback=lambda name, detail: refused_markers.append(
                        (name, dict(detail))
                    ),
                )
        assert block_ldu.lu_solve is original_lu_solve
        refusal_rows = [
            detail
            for name, detail in refused_markers
            if name == "v13_modal_schur_lu_refused"
        ]
        assert len(refusal_rows) == 1
        refusal = refusal_rows[0]
        assert refusal["original_schur_rhs_residual_pass"] is False
        assert refusal["original_schur_rhs_relative_residuals"] == [1.0, 1.0]
        assert refusal["setup_work_counts"]["owner_repeat_lu_solve_attempts"] == 2
        assert refusal["setup_work_counts"][
            "owner_original_schur_rhs_residual_checks"
        ] == 2
        refusal_marker_counts = comm.allgather(len(refusal_rows))
        assert refusal_marker_counts == [1] * comm.size
    finally:
        if context is not None and not context._destroyed:
            context.destroy()
        if system is not None and not system._destroyed:
            system.destroy()
        if original_operator is not None:
            # It is already present in owned_matrices; destroy it in the common
            # matrix cleanup below so every PETSc handle is released once.
            original_operator = None
        for vector in (
            source,
            target,
            outer_workspace_rhs,
            outer_workspace_solution,
        ):
            if vector is not None:
                vector.destroy()
        for action in side_actions:
            action.destroy()
        _destroy_side_block_fixture(side_fixture)
        # The P4 identity doubles borrow their full/coarse layout matrices.
        # Their fixture-owned factors are now destroyed; release the local
        # coarse matrices only after their borrowers are gone.
        for matrix in owned_matrices:
            matrix.destroy()
        for original_context in original_operator_contexts:
            if not original_context._destroyed:
                original_context.destroy()


def test_v13_unmocked_builder_owner_lu_and_original_modal_row_math(
    monkeypatch, tmp_path
) -> None:
    _exercise_v13_unmocked_builder_owner_lu_and_original_modal_row_math(
        monkeypatch, tmp_path
    )


def test_fixed_physical_action_is_rejected_by_unselected_or_mixed_modal_method() -> None:
    fixture = _fixed_h6_side_block_fixture()
    bottom_physical = fixture["bottom_inverse"].create_fixed_physical_balh_active_trace_action()
    top_h6 = fixture["top_inverse"].create_fixed_h6_active_trace_action()
    try:
        with pytest.raises(
            RuntimeError,
            match="Fixed-H6 modal input preflight failed.*modal feedback actions do not match",
        ):
            block_ldu._FixedH6ModalKrylovSystem(
                fixture["coupling"],
                bottom_physical,
                top_h6,
                modal_owner=fixture["layout"].modal_owner,
                feedback_method=None,
            )
        with pytest.raises(
            RuntimeError,
            match="Fixed-H6 modal input preflight failed.*modal feedback actions do not match",
        ):
            block_ldu._FixedH6ModalKrylovSystem(
                fixture["coupling"],
                bottom_physical,
                top_h6,
                modal_owner=fixture["layout"].modal_owner,
                feedback_method=FIXED_PHYSICAL_BALH_MODAL_FEEDBACK_METHOD,
            )
    finally:
        for action in (top_h6, bottom_physical):
            action.destroy()
        _destroy_side_block_fixture(fixture)


@pytest.mark.parametrize(
    "fault",
    ("repeat_drift", "conjugate_antilinear", "nonlinear", "nonfinite"),
)
def test_side_balh_fixed_h6_feedback_gate_rejects_invalid_outputs_and_cleans_up(
    fault: str, monkeypatch
) -> None:
    fixture = _fixed_h6_side_block_fixture()
    comm = MPI.COMM_WORLD
    rank = int(comm.rank)
    size = int(comm.size)
    original_factory = SideBalancedInverse.create_fixed_h6_active_trace_action
    original_apply = block_ldu.HybridActionModalSchurApply.apply
    created_adapters: list[FixedH6ActiveTraceAction] = []
    side_counts_before = {
        side: fixture[f"{side}_inverse"].diagnostics["apply_count"]
        for side in ("bottom", "top")
    }
    events: list[tuple[str, dict[str, object]]] = []
    calls = 0
    local_errors: list[str] = []
    caught_gate_message: str | None = None
    cleanup_completed = False

    def check(condition: bool, description: str) -> None:
        if fault == "nonfinite":
            if not condition:
                local_errors.append(description)
        else:
            assert condition, description

    def capture_adapter(owner: SideBalancedInverse) -> FixedH6ActiveTraceAction:
        adapter = original_factory(owner)
        created_adapters.append(adapter)
        return adapter

    def corrupted_apply(
        action: block_ldu.HybridActionModalSchurApply, values: np.ndarray
    ) -> np.ndarray:
        nonlocal calls
        calls += 1
        output = np.asarray(original_apply(action, values), dtype=np.complex128).copy()
        if fault == "repeat_drift" and calls == 3:
            output[0] += 0.25 - 0.125j
        elif fault == "conjugate_antilinear":
            output = np.conjugate(output)
        elif fault == "nonlinear":
            output[0] += 0.2 * float(np.vdot(values, values).real) * (1.0 + 0.25j)
        elif fault == "nonfinite" and rank == size - 1:
            output[0] = np.nan + 0.0j
        return output

    monkeypatch.setattr(
        SideBalancedInverse,
        "create_fixed_h6_active_trace_action",
        capture_adapter,
    )
    monkeypatch.setattr(block_ldu.HybridActionModalSchurApply, "apply", corrupted_apply)
    try:
        def create_candidate():
            return block_ldu.create_side_balh_block_ldu_preconditioner(
                fixture["layout"],
                fixture["bottom"],
                fixture["top"],
                fixture["coupling"],
                fixture["bottom_inverse"],
                fixture["top_inverse"],
                sampled_columns=None,
                sampled_column_roles=None,
                sampled_column_contract_sha256=None,
                marker_callback=lambda event, detail: events.append(
                    (event, dict(detail))
                ),
                fixed_h6_modal_gmres_research=True,
            )

        if fault == "nonfinite":
            unexpected_candidate = None
            try:
                unexpected_candidate = create_candidate()
            except ValueError as exc:
                caught_gate_message = str(exc)
            if unexpected_candidate is not None:
                destroy = getattr(unexpected_candidate, "destroy", None)
                if callable(destroy):
                    destroy()
            check(
                caught_gate_message is not None
                and "Fixed-H6 modal feedback repeat/linearity Gate failed"
                in caught_gate_message,
                "all ranks must catch the fixed-H6 feedback gate failure",
            )
        else:
            with pytest.raises(
                ValueError,
                match="Fixed-H6 modal feedback repeat/linearity Gate failed",
            ):
                create_candidate()

        check(calls == 8, "the gate must perform eight requested S_H actions")
        ready = [detail for event, detail in events if event == "modal_sample_ready"]
        check(len(ready) == 1, "the gate must emit one modal_sample_ready marker")
        failed_gate = ready[0].get("early_sample_gate", {}) if ready else {}
        check(ready[0].get("status") == "failed" if ready else False,
              "the marker must report failed status")
        check(ready[0].get("pass") is False if ready else False,
              "the marker must report global failure")
        check(failed_gate.get("requested_s_h_actions") == 8,
              "the gate must record eight requested S_H actions")
        rank_results = failed_gate.get("rank_results", [])
        check(len(rank_results) == size,
              "the gate must retain one local result per communicator rank")
        check(
            [row.get("rank") for row in rank_results] == list(range(size)),
            "rank-local gate results must be ordered by rank",
        )
        check(failed_gate.get("pass") is False,
              "the global gate must fail when one rank has a nonfinite output")
        try:
            json.dumps(failed_gate, allow_nan=False)
        except (TypeError, ValueError) as exc:
            check(False, f"gate diagnostics must be strict-JSON serializable: {exc}")
        for row in rank_results:
            check(row.get("operator_action_attempts") == 8,
                  "each rank must record eight action attempts")
            check(row.get("operator_action_completions") == 8,
                  "each rank must record eight completed actions")
            check(row.get("modal_constraint_matvec_calls") == 8,
                  "each rank must record eight constraint matvecs")
            unchanged = row.get("input_unchanged_by_action", {})
            check(bool(unchanged) and all(unchanged.values()),
                  "each rank must retain the input-unchanged checks")
            for side in ("bottom", "top"):
                side_counts = row.get("fixed_h6_side_counts", {}).get(side, {})
                check(side_counts.get("fixed_h6_apply_calls") == 8,
                      f"{side} must record eight H6 applies per rank")
                check(side_counts.get("fixed_h6_matrix_mult_calls") == 16,
                      f"{side} must record sixteen H6 matrix multiplies per rank")
                check(side_counts.get("matrix_mult_matches_h6_degree") is True,
                      f"{side} matrix multiplies must match the recorded H6 degree")
        if fault == "nonfinite":
            for row in rank_results:
                local_pass = row.get("pass")
                metrics = row.get("metrics", {})
                is_bad_rank = row.get("rank") == size - 1
                check(
                    local_pass is (not is_bad_rank),
                    "only the last rank should fail its local finite-output gate",
                )
                check(bool(metrics), "each rank must retain its local gate metrics")
                if is_bad_rank:
                    check(
                        any(
                            metric.get("finite") is False
                            for metric in metrics.values()
                            if isinstance(metric, dict)
                        ),
                        "the corrupted rank's own metrics must identify nonfinite output",
                    )
                else:
                    check(
                        all(
                            metric.get("finite") is True
                            and metric.get("pass") is True
                            for metric in metrics.values()
                            if isinstance(metric, dict)
                        ),
                        "the uncorrupted rank's local metrics must pass",
                    )
        else:
            failed_metrics = failed_gate["metrics"]
            if fault == "repeat_drift":
                check(failed_metrics["repeat_x"]["pass"] is False,
                      "repeat drift must fail the repeated-x metric")
            elif fault == "conjugate_antilinear":
                check(failed_metrics["complex_homogeneity"]["pass"] is False,
                      "conjugate mapping must fail complex homogeneity")
            elif fault == "nonlinear":
                check(
                    failed_metrics["complex_homogeneity"]["pass"] is False
                    or failed_metrics["additivity"]["pass"] is False,
                    "nonlinear mapping must fail homogeneity or additivity",
                )
        check(len(created_adapters) == 2,
              "both borrowed-side adapters must be constructed")
        check(
            all(adapter.audit["destroyed"] for adapter in created_adapters),
            "both constructed adapters must be destroyed on gate failure",
        )
        check(fixture["bottom_inverse"].diagnostics["destroyed"] is False,
              "the borrowed bottom inverse must remain alive")
        check(fixture["top_inverse"].diagnostics["destroyed"] is False,
              "the borrowed top inverse must remain alive")
        check(fixture["bottom_inverse"]._h6._destroyed is False,
              "the borrowed bottom H6 action must remain alive")
        check(fixture["top_inverse"]._h6._destroyed is False,
              "the borrowed top H6 action must remain alive")
        check(
            {
                side: fixture[f"{side}_inverse"].diagnostics["apply_count"]
                for side in ("bottom", "top")
            }
            == side_counts_before,
            "the feedback gate must not call the original adaptive side inverse",
        )
    finally:
        _destroy_side_block_fixture(fixture)
        cleanup_completed = True

    if fault == "nonfinite":
        completion_records = comm.allgather(
            {
                "rank": rank,
                "caught_gate_message": caught_gate_message,
                "local_errors": list(local_errors),
                "cleanup_completed": cleanup_completed,
                "adapters_destroyed": all(
                    adapter.audit["destroyed"] for adapter in created_adapters
                ),
            }
        )
        # All ranks reach this point only after fixture cleanup and the real allgather.
        assert [record["rank"] for record in completion_records] == list(range(size))
        assert all(record["cleanup_completed"] for record in completion_records)
        assert all(record["adapters_destroyed"] for record in completion_records)
        assert all(not record["local_errors"] for record in completion_records), (
            completion_records
        )
        messages = {record["caught_gate_message"] for record in completion_records}
        assert len(messages) == 1
        assert next(iter(messages)) is not None
        assert "Fixed-H6 modal feedback repeat/linearity Gate failed" in next(iter(messages))


def test_side_balh_fixed_h6_modal_gmres_options_and_constructor_cleanup(
    monkeypatch,
) -> None:
    fixture = _fixed_h6_side_block_fixture()
    original_factory = SideBalancedInverse.create_fixed_h6_active_trace_action
    created_adapters: list[FixedH6ActiveTraceAction] = []

    def capture_adapter(owner: SideBalancedInverse) -> FixedH6ActiveTraceAction:
        adapter = original_factory(owner)
        created_adapters.append(adapter)
        return adapter

    def fail_constructor(*_args, **_kwargs):
        raise RuntimeError("injected fixed-H6 modal construction failure")

    monkeypatch.setattr(
        SideBalancedInverse,
        "create_fixed_h6_active_trace_action",
        capture_adapter,
    )
    monkeypatch.setattr(block_ldu, "_FixedH6ModalKrylovSystem", fail_constructor)
    try:
        columns, roles, contract_sha = _sample_contract()
        for option in (
            "use_anderson_modal_inner",
            "complex_qr_research",
            "raw_metric_mixing",
            "capture_modal_solve_trace",
        ):
            with pytest.raises(ValueError, match="mutually exclusive"):
                block_ldu.create_side_balh_block_ldu_preconditioner(
                    fixture["layout"],
                    fixture["bottom"],
                    fixture["top"],
                    fixture["coupling"],
                    fixture["bottom_inverse"],
                    fixture["top_inverse"],
                    sampled_columns=columns,
                    sampled_column_roles=roles,
                    sampled_column_contract_sha256=contract_sha,
                    fixed_h6_modal_gmres_research=True,
                    **{option: True},
                )
        with pytest.raises(RuntimeError, match="injected fixed-H6 modal construction failure"):
            block_ldu.create_side_balh_block_ldu_preconditioner(
                fixture["layout"],
                fixture["bottom"],
                fixture["top"],
                fixture["coupling"],
                fixture["bottom_inverse"],
                fixture["top_inverse"],
                sampled_columns=columns,
                sampled_column_roles=roles,
                sampled_column_contract_sha256=contract_sha,
                fixed_h6_modal_gmres_research=True,
            )
        assert len(created_adapters) == 2
        assert all(adapter.audit["destroyed"] for adapter in created_adapters)
        assert fixture["bottom_inverse"].diagnostics["destroyed"] is False
        assert fixture["top_inverse"].diagnostics["destroyed"] is False
        fixture["bottom_inverse"].destroy()
        with pytest.raises(RuntimeError, match="destroyed side inverse"):
            fixture["bottom_inverse"].create_fixed_h6_active_trace_action()
    finally:
        _destroy_side_block_fixture(fixture)


def test_side_balh_fixed_h6_modal_inner_error_propagates_without_fallback(
    monkeypatch,
) -> None:
    """Exercise synchronized KSP Mat failure cleanup, not numerical quality."""

    fixture = _fixed_h6_side_block_fixture()
    original_action = original_context = context = rhs = None

    def reject_full_schur(*_args, **_kwargs):
        raise AssertionError("fixed-H6 failure must not fall back to full Schur")

    monkeypatch.setattr(block_ldu, "build_hybrid_action_modal_schur", reject_full_schur)
    try:
        columns, roles, contract_sha = _sample_contract()
        context = block_ldu.create_side_balh_block_ldu_preconditioner(
            fixture["layout"],
            fixture["bottom"],
            fixture["top"],
            fixture["coupling"],
            fixture["bottom_inverse"],
            fixture["top_inverse"],
            sampled_columns=columns,
            sampled_column_roles=roles,
            sampled_column_contract_sha256=contract_sha,
            fixed_h6_modal_gmres_research=True,
        )
        rhs = fixture["layout"].pack(
            fixture["bottom"].b,
            fixture["top"].b,
            internal_modal_rhs_correction(fixture["coupling"]),
        )
        original_action, original_context = create_hybrid_assembled_block_action(
            fixture["bottom"], fixture["top"], fixture["coupling"]
        )
        modal_bundle = context.action_modal_schur_system

        def nonfinite_modal_action(_modal: np.ndarray) -> np.ndarray:
            return np.full(
                context.modal_count,
                np.nan,
                dtype=np.complex128,
            )

        monkeypatch.setattr(modal_bundle._solver._modal_action, "apply", nonfinite_modal_action)
        with pytest.raises(RuntimeError, match="Fixed-H6 modal KSP failed"):
            block_ldu.solve_hybrid_block_ldu_iterative(
                original_action,
                rhs,
                context,
                config=block_ldu.HybridBlockLduIterativeConfig(
                    restart=20,
                    max_it=80,
                    threshold=5.0e-9,
                    ksp_type="fgmres",
                ),
            )
        assert context._destroyed is True
        failed = context.inventory
        assert failed["pc_apply_count"] == 0
        assert failed["fixed_h6_pc_side_apply_counts"]["bottom"] == {
            "first": 1,
            "delta": 0,
        }
        assert failed["fixed_h6_pc_side_apply_counts"]["top"] == {
            "first": 1,
            "delta": 0,
        }
        solver_diagnostics = failed["fixed_h6_modal_solver"]
        assert solver_diagnostics["destroyed"] is True
        assert solver_diagnostics["last_solve"]["status"] == "ksp_callback_failed"
        assert solver_diagnostics["last_solve"]["solver_matmult_calls"] == 1
        assert solver_diagnostics["last_solve"]["final_residual_status"] == (
            "not_evaluated"
        )
        assert solver_diagnostics["last_solve"]["final_residual_evaluated"] is False
        assert fixture["bottom_inverse"].diagnostics["destroyed"] is False
        assert fixture["top_inverse"].diagnostics["destroyed"] is False
    finally:
        if context is not None and not context._destroyed:
            context.destroy()
        if rhs is not None:
            rhs.destroy()
        if original_action is not None:
            original_action.destroy()
        if original_context is not None:
            original_context.destroy()
        _destroy_side_block_fixture(fixture)


def test_task041_v12_modal_policy_is_bounded_and_keeps_legacy_defaults():
    policy_id = "task041_v12_bounded_inexact_modal"
    policy = block_ldu.resolve_task041_modal_solver_policy(policy_id)
    assert policy == {
        "policy_id": policy_id,
        "target_rtol": 1.0e-3,
        "max_it": 32,
        "restart": 32,
        "solver_matmult_limit": 34,
        "total_matmult_limit_including_final": 35,
        "approximate_return_eta_max": 0.1,
        "accepted_normal_return_conditions": (
            "runtime_DIVERGED_ITS_at_max_it_or_positive_reason_with_raw_target_miss"
        ),
        "raw_reason_and_residual_preserved": True,
    }
    assert block_ldu.resolve_task041_modal_solver_policy(None) is None
    backup_policy = block_ldu.resolve_task041_modal_solver_policy(
        block_ldu.TASK041_V12_MODAL_BACKUP_POLICY_ID
    )
    assert backup_policy == json.loads(json.dumps(backup_policy))
    assert backup_policy["policy_id"] == (
        block_ldu.TASK041_V12_MODAL_BACKUP_POLICY_ID
    )
    assert backup_policy["maximum_backup_switches"] == 1
    assert backup_policy["side_restart64_trial"]["enabled_by_default"] is False
    assert backup_policy["side_restart64_trial"]["status"] == (
        "registered_once_trial_requires_live_fresh_authority_callback"
    )
    assert backup_policy["side_restart64_trial"]["selection_rule"] == (
        "same_rhs_eta64_at_most_0.9_eta32_and_max_rank_trial_wall_with_one_setup_not_higher"
        "_and_log_residual_reduction_per_wall_not_lower"
    )
    assert block_ldu._FixedH6ModalKrylovSystem.rtol == 1.0e-3
    assert block_ldu._FixedH6ModalKrylovSystem.max_it == 8
    assert block_ldu._FixedH6ModalKrylovSystem.solver_matmult_limit == 9
    assert block_ldu._FixedH6ModalKrylovSystem.total_matmult_limit == 10

    reason_enum = PETSc.KSP.ConvergedReason
    diverged_its = getattr(reason_enum, "DIVERGED_ITS", None)
    if diverged_its is None:
        diverged_its = reason_enum.DIVERGED_MAX_IT
    accepted_reason = int(reason_enum.CONVERGED_RTOL)

    def classify(**changes):
        values = {
            "policy": policy,
            "reason": int(diverged_its),
            "iterations": 32,
            "raw_relative_residual": 0.05,
            "raw_residual_pass": False,
            "trusted_iterate": True,
            "input_unchanged": True,
            "budget_exhausted": False,
            "mat_preflight_failure": None,
            "modal_action_failure": None,
            "pc_failure": None,
        }
        values.update(changes)
        return block_ldu._bounded_modal_return_eligibility(**values)

    exhausted_its = classify()
    assert exhausted_its["pc_usable"] is True
    assert exhausted_its["status"] == "INNER_TARGET_NOT_MET_APPROX_RETURN"
    positive_raw_miss = classify(reason=accepted_reason, iterations=7)
    assert positive_raw_miss["pc_usable"] is True

    rejected = (
        classify(reason=-5),
        classify(iterations=31),
        classify(reason=accepted_reason, iterations=33),
        classify(
            reason=accepted_reason,
            raw_relative_residual=5.0e-4,
            raw_residual_pass=False,
        ),
        classify(raw_relative_residual=0.1000001),
        classify(raw_relative_residual=None),
        classify(raw_residual_pass=True),
        classify(trusted_iterate=False),
        classify(input_unchanged=False),
        classify(budget_exhausted=True),
        classify(mat_preflight_failure="injected MatMult preflight failure"),
        classify(modal_action_failure="injected S_H action failure"),
        classify(pc_failure="injected PC failure"),
    )
    assert all(item["pc_usable"] is False for item in rejected)


def test_v12_modal_wrapper_extends_legacy_budget_and_writes_solver_snapshot(
    tmp_path,
):
    """Exercise KSP policy returns and all three real owner snapshot slots.

    The 40x40 complex non-Hermitian Schur action is deliberately injected at
    the modal action boundary; the production wrapper, PETSc KSP, C-LU PC,
    raw residual, policy decision and snapshot callback remain real.
    """

    from benchmarks.task041_exact_side_workflow import (
        _write_task041_modal_inner_snapshot,
    )

    fixture, bundles, coupling, schur = _v12_fixed_h6_modal_components()
    systems: list[block_ldu._FixedH6ModalKrylovSystem] = []
    policy_id = block_ldu.TASK041_V12_MODAL_SOLVER_POLICY_ID
    owner = MPI.COMM_WORLD.size - 1
    run_root = tmp_path / "solver_callback_snapshot"
    identity = {"model_id": "test_only_modal_matrix", "mpi_size": MPI.COMM_WORLD.size}
    binding = {"producer_source_sha": "c" * 40, "consumer_source_sha": "d" * 40}

    def new_system(*, policy=None, snapshot_callback=None):
        system = block_ldu._FixedH6ModalKrylovSystem(
            coupling,
            bundles[0]["adapter"],
            bundles[1]["adapter"],
            modal_owner=owner,
            modal_solver_policy=policy,
            snapshot_callback=snapshot_callback,
        )
        _set_v12_test_schur(system, schur)
        systems.append(system)
        return system

    def write_snapshot(payload):
        return _write_task041_modal_inner_snapshot(
            run_root,
            payload,
            source_sha="a" * 40,
            identity=identity,
            packet_manifest_sha256="b" * 64,
            consumer_binding=binding,
        )

    easy_rhs = np.zeros(40, dtype=np.complex128)
    easy_indices = np.asarray([0, 1, 2, 3, 4, 5, 34, 35, 36, 37, 38, 39])
    easy_rhs[easy_indices] = np.asarray(
        [1.0 + 0.1j * index for index in range(easy_indices.size)],
        dtype=np.complex128,
    )
    hard_rhs = np.zeros(40, dtype=np.complex128)
    hard_rhs[:32] = np.asarray(
        [1.0 + 0.01j * index for index in range(32)], dtype=np.complex128
    )
    hard_rhs[32] = 0.05 - 0.01j

    try:
        legacy = new_system()
        assert legacy.max_it == 8
        assert legacy.solver_matmult_limit == 9
        assert legacy.total_matmult_limit == 10
        assert legacy._rhs_input_bytes is None
        assert legacy._rhs_input_sha256 is None
        legacy_rhs = easy_rhs.copy()
        with pytest.raises(RuntimeError, match="did not converge"):
            legacy.solve(legacy_rhs)
        legacy_result = dict(legacy.diagnostics["last_solve"])
        assert legacy_result["iterations"] == 8
        assert legacy_result["raw_residual_pass"] is False
        assert legacy_result["final_relative_residual"] > legacy.rtol
        assert "trusted_iterate" not in legacy_result
        assert np.array_equal(legacy_rhs, easy_rhs)

        policy_system = new_system(policy=policy_id, snapshot_callback=write_snapshot)
        assert policy_system.max_it == 32
        assert policy_system.rtol == pytest.approx(1.0e-3)
        assert policy_system.diagnostics["restart"] == 32
        assert policy_system.solver_matmult_limit == 34
        assert policy_system.total_matmult_limit == 35
        assert legacy.max_it == 8
        assert legacy.solver_matmult_limit == 9
        assert legacy.total_matmult_limit == 10
        legacy.destroy()
        expected_local = 40 if MPI.COMM_WORLD.rank == owner else 0
        assert policy_system._rhs.getLocalSize() == expected_local

        zero_result = policy_system.solve(np.zeros(40, dtype=np.complex128))
        zero_record = dict(policy_system.diagnostics["last_solve"])
        np.testing.assert_array_equal(zero_result, np.zeros(40, dtype=np.complex128))
        assert zero_record["status"] == "zero_rhs_exact"
        assert zero_record["ksp_status"] == "not_run_zero_rhs"
        assert zero_record["trusted_iterate"] is True
        assert zero_record["input_unchanged"] is True
        zero_states = MPI.COMM_WORLD.allgather(
            (zero_record["status"], zero_record["pc_usable"])
        )
        assert len(set(zero_states)) == 1

        first_unmet_rhs = hard_rhs.copy()
        policy_system.solve(first_unmet_rhs)
        first_unmet = dict(policy_system.diagnostics["last_solve"])
        diverged_its = getattr(PETSc.KSP.ConvergedReason, "DIVERGED_ITS", None)
        if diverged_its is None:
            diverged_its = PETSc.KSP.ConvergedReason.DIVERGED_MAX_IT
        assert first_unmet["iterations"] == 32
        assert first_unmet["status"] == "INNER_TARGET_NOT_MET_APPROX_RETURN"
        assert first_unmet["ksp_reason"] == int(diverged_its)
        assert first_unmet["raw_residual_pass"] is False
        assert 1.0e-3 < first_unmet["final_relative_residual"] <= 0.1
        assert first_unmet["solver_matmult_calls"] <= 34
        assert first_unmet["total_matmult_calls"] <= 35
        assert first_unmet["total_matmult_calls"] == (
            first_unmet["solver_matmult_calls"] + 1
        )
        assert first_unmet["final_residual_evaluated"] is True
        assert policy_system.diagnostics["budget_exhausted"] is False
        assert first_unmet["pc_usable"] is True
        assert first_unmet["trusted_iterate"] is True
        assert first_unmet["input_unchanged"] is True
        assert first_unmet["snapshot_record"]["status"] == "written"
        assert np.array_equal(first_unmet_rhs, hard_rhs)
        first_path = run_root / first_unmet["snapshot_record"]["path"]
        first_snapshot_sha_before_repeat = (
            hashlib.sha256(first_path.read_bytes()).hexdigest()
            if MPI.COMM_WORLD.rank == owner
            else None
        )
        first_snapshot_sha_before_repeat = MPI.COMM_WORLD.bcast(
            first_snapshot_sha_before_repeat, root=owner
        )
        approximate_states = MPI.COMM_WORLD.allgather(
            (
                first_unmet["status"],
                first_unmet["ksp_reason"],
                first_unmet["pc_usable"],
            )
        )
        assert len(set(approximate_states)) == 1

        success_rhs = easy_rhs.copy()
        policy_system.solve(success_rhs)
        success_record = dict(policy_system.diagnostics["last_solve"])
        assert success_record["status"] == "converged"
        assert success_record["raw_residual_pass"] is True
        assert success_record["pc_usable"] is True
        assert success_record["trusted_iterate"] is True
        assert success_record["input_unchanged"] is True
        assert success_record["snapshot_record"]["status"] == "written"
        assert np.array_equal(success_rhs, easy_rhs)

        # A later unmet solve must not replace the first owner snapshot.
        policy_system.solve(hard_rhs.copy())
        terminal_constraint = np.asarray(
            internal_modal_constraint_matrix(coupling), dtype=np.complex128
        )
        terminal_schur_diagonal = np.geomspace(1.0e-12, 1.0e12, 40) * np.exp(
            1j * np.linspace(-0.2, 0.25, 40)
        )
        terminal_schur = np.diag(terminal_schur_diagonal) @ terminal_constraint
        assert np.isfinite(terminal_schur).all()
        _set_v12_test_schur(policy_system, terminal_schur)
        terminal_rhs = np.ones(40, dtype=np.complex128)
        terminal_rhs_before = terminal_rhs.copy()
        with pytest.raises(RuntimeError, match="did not converge"):
            policy_system.solve(terminal_rhs)
        terminal = dict(policy_system.diagnostics["last_solve"])
        assert terminal["trusted_iterate"] is True
        assert terminal["input_unchanged"] is True
        assert terminal["raw_residual_pass"] is False
        assert terminal["final_relative_residual"] > 0.1
        assert terminal["pc_usable"] is False
        assert terminal["status"] not in {
            "converged",
            "INNER_TARGET_NOT_MET_APPROX_RETURN",
            "PRIMARY_MODAL_TARGET_NOT_MET_BACKUP_ELIGIBLE",
        }
        assert terminal["status"] in {
            "ksp_not_converged",
            "final_residual_failed",
        }
        assert terminal["approximate_return_decision"]["status"] == "rejected"
        assert np.array_equal(terminal_rhs, terminal_rhs_before)
        assert policy_system.diagnostics[
            "terminal_normal_reject_snapshot_saved"
        ] is True
        assert set(terminal["snapshot_records"]) == {"terminal_normal_reject"}
        assert terminal["snapshot_record"] == terminal["snapshot_records"][
            "terminal_normal_reject"
        ]
        terminal_path = run_root / terminal["snapshot_record"]["path"]
        terminal_snapshot_sha = terminal["snapshot_record"]["sha256"]

        index_path = run_root / "numerical_output/modal_inner_snapshots/index.json"
        owner_record = None
        if MPI.COMM_WORLD.rank == owner:
            index = json.loads(index_path.read_text(encoding="utf-8"))
            assert set(index["records"]) == {
                "first_unmet_target",
                "first_success_control",
                "terminal_normal_reject",
            }
            with np.load(first_path, allow_pickle=False) as archive:
                g = np.asarray(archive["g"], dtype=np.complex128)
                m = np.asarray(archive["m"], dtype=np.complex128)
                raw = np.asarray(archive["raw_residual"], dtype=np.complex128)
            independently_recomputed = g - schur @ m
            response_error = float(np.linalg.norm(raw - independently_recomputed))
            residual_norm_error = abs(
                float(np.linalg.norm(raw))
                - float(first_unmet["final_residual_norm"])
            )
            after_sha = hashlib.sha256(first_path.read_bytes()).hexdigest()
            with np.load(terminal_path, allow_pickle=False) as archive:
                terminal_g = np.asarray(archive["g"], dtype=np.complex128)
                terminal_m = np.asarray(archive["m"], dtype=np.complex128)
                terminal_raw = np.asarray(
                    archive["raw_residual"], dtype=np.complex128
                )
            terminal_residual = terminal_g - terminal_schur @ terminal_m
            terminal_response_error = float(
                np.linalg.norm(terminal_raw - terminal_residual)
            )
            terminal_residual_norm_error = abs(
                float(np.linalg.norm(terminal_raw))
                - float(terminal["final_residual_norm"])
            )
            terminal_after_sha = hashlib.sha256(
                terminal_path.read_bytes()
            ).hexdigest()
            terminal_metadata = index["records"]["terminal_normal_reject"][
                "metadata"
            ]
            terminal_metadata_check = (
                terminal_metadata["status"] == terminal["status"],
                terminal_metadata["input_unchanged"] is True,
                terminal_metadata["final_residual_evaluated"] is True,
                terminal_metadata["ksp_reason"] == terminal["ksp_reason"],
            )
            owner_record = (
                first_snapshot_sha_before_repeat,
                after_sha,
                len(index["records"]),
                response_error,
                residual_norm_error,
                terminal_response_error,
                terminal_residual_norm_error,
                terminal_after_sha,
                terminal_metadata_check,
            )
        owner_record = MPI.COMM_WORLD.bcast(owner_record, root=owner)
        assert owner_record[0] == owner_record[1]
        assert owner_record[2] == 3
        assert owner_record[3] <= 1.0e-12 * max(float(np.linalg.norm(hard_rhs)), 1.0)
        assert owner_record[4] <= 1.0e-10 * max(
            float(first_unmet["final_residual_norm"]), 1.0
        )
        assert owner_record[5] <= 1.0e-12 * max(
            float(np.linalg.norm(terminal_rhs_before)), 1.0
        )
        assert owner_record[6] <= 1.0e-10 * max(
            float(terminal["final_residual_norm"]), 1.0
        )
        assert owner_record[7] == terminal_snapshot_sha
        assert all(owner_record[8])
    finally:
        for system in systems:
            system.destroy()
        _destroy_fixed_h6_modal_krylov_components(fixture, bundles, None)


def test_v12_modal_wrapper_rejects_input_mutation_and_eta_above_bound():
    fixture, bundles, coupling, schur = _v12_fixed_h6_modal_components()
    systems: list[block_ldu._FixedH6ModalKrylovSystem] = []
    policy_id = block_ldu.TASK041_V12_MODAL_SOLVER_POLICY_ID
    owner = MPI.COMM_WORLD.size - 1
    easy_rhs = np.zeros(40, dtype=np.complex128)
    easy_rhs[[0, 2, 5, 9, 14, 20, 25, 31, 36, 39]] = (
        1.0 + 0.2j * np.arange(10)
    )

    def new_system():
        system = block_ldu._FixedH6ModalKrylovSystem(
            coupling,
            bundles[0]["adapter"],
            bundles[1]["adapter"],
            modal_owner=owner,
            modal_solver_policy=policy_id,
            snapshot_callback=lambda payload: {
                "status": "test_snapshot",
                "snapshot_kind": payload["snapshot_kind"],
            },
        )
        _set_v12_test_schur(system, schur)
        systems.append(system)
        return system

    try:
        system = new_system()
        rhs = np.zeros(40, dtype=np.complex128)
        rhs[[0, 2, 5, 9, 14, 20, 25, 31, 36, 39]] = (
            1.0 + 0.2j * np.arange(10)
        )
        original_rhs = rhs.copy()
        mutated = False

        def mutate_input_during_real_mat_mult(values):
            nonlocal mutated
            if not mutated:
                rhs[0] += 0.25 - 0.1j
                mutated = True
            return schur @ np.asarray(values, dtype=np.complex128)

        system._modal_action.apply = mutate_input_during_real_mat_mult
        with pytest.raises(RuntimeError, match="did not converge"):
            system.solve(rhs)
        mutation_record = dict(system.diagnostics["last_solve"])
        assert mutation_record["ksp_reason"] > 0
        assert mutation_record["raw_residual_pass"] is True
        assert mutation_record["trusted_iterate"] is True
        assert mutation_record["input_unchanged"] is False
        assert mutation_record["status"] == "modal_rhs_input_modified"
        assert mutation_record["pc_usable"] is False
        assert mutation_record["normal_return_rejection_reason"]
        assert not np.array_equal(rhs, original_rhs)
        assert (
            system.diagnostics["terminal_normal_reject_snapshot_saved"] is False
        )
        assert "snapshot_records" not in mutation_record

        # Use a deliberately ill-conditioned, finite test Schur action so the
        # real wrapper reaches eta>0.1 after its bounded KSP solve.  The right
        # preconditioner still solves the same test constraint matrix; only
        # this test-injected 40x40 action changes.
        bad_eta_system = new_system()
        test_constraint = np.asarray(
            internal_modal_constraint_matrix(coupling), dtype=np.complex128
        )
        bad_eta_diagonal = np.geomspace(1.0e-12, 1.0e12, 40) * np.exp(
            1j * np.linspace(-0.2, 0.25, 40)
        )
        bad_eta_schur = np.diag(bad_eta_diagonal) @ test_constraint
        assert np.isfinite(bad_eta_schur).all()
        assert np.linalg.norm(bad_eta_schur - bad_eta_schur.conj().T) > 1.0
        _set_v12_test_schur(bad_eta_system, bad_eta_schur)
        bad_eta_rhs = np.ones(40, dtype=np.complex128)
        with pytest.raises(RuntimeError, match="did not converge"):
            bad_eta_system.solve(bad_eta_rhs)
        bad_eta = dict(bad_eta_system.diagnostics["last_solve"])
        assert 0 < bad_eta["iterations"] <= 32
        assert isinstance(bad_eta["ksp_reason"], int)
        assert bad_eta["raw_residual_pass"] is False
        assert bad_eta["final_relative_residual"] > 0.1
        assert bad_eta["pc_usable"] is False
        assert bad_eta["approximate_return_decision"]["status"] == "rejected"
        assert bad_eta["trusted_iterate"] is True
        assert bad_eta["input_unchanged"] is True
        assert bad_eta_system.diagnostics[
            "terminal_normal_reject_snapshot_saved"
        ] is True
        assert bad_eta["snapshot_record"]["status"] == "test_snapshot"
        assert bad_eta["snapshot_record"]["snapshot_kind"] == (
            "terminal_normal_reject"
        )
        assert set(bad_eta["snapshot_records"]) == {
            "first_unmet_target",
            "terminal_normal_reject",
        }

        # Positive KSP reason with an independently missed raw target is
        # explicitly injected here; it is wrapper-path evidence, not a natural
        # PETSc reason observed from this matrix.
        _set_v12_test_schur(system, schur)
        real_ksp = system._ksp

        class PositiveReasonKspProxy:
            def __getattr__(self, name):
                return getattr(real_ksp, name)

            def getConvergedReason(self):
                return int(PETSc.KSP.ConvergedReason.CONVERGED_RTOL)

        system._ksp = PositiveReasonKspProxy()
        injected = system.solve(
            np.asarray(
                [1.0 + 0.01j * index for index in range(32)]
                + [0.05 - 0.01j]
                + [0.0j] * 7,
                dtype=np.complex128,
            )
        )
        injected_record = dict(system.diagnostics["last_solve"])
        assert injected.shape == (40,)
        assert injected_record["ksp_reason"] > 0
        assert injected_record["raw_residual_pass"] is False
        assert 1.0e-3 < injected_record["final_relative_residual"] <= 0.1
        assert injected_record["approximate_return_decision"][
            "positive_reason_with_raw_target_miss"
        ] is True
        assert injected_record["pc_usable"] is True
        assert injected_record["status"] == "INNER_TARGET_NOT_MET_APPROX_RETURN"

        # Exceptions and non-finite actions remain hard failures on the real
        # policy wrapper path; neither is converted to approximate usability.
        for failure_kind in ("action_exception", "nonfinite_action", "pc_exception"):
            failing = new_system()
            if failure_kind == "action_exception":
                def fail_action(_values):
                    raise RuntimeError("injected policy MatMult exception")

                failing._modal_action.apply = fail_action
            elif failure_kind == "nonfinite_action":
                failing._modal_action.apply = lambda values: np.full_like(
                    np.asarray(values, dtype=np.complex128), np.nan
                )
            else:
                def fail_pc(_pc, _source, _target):
                    raise RuntimeError("injected policy C-LU PC exception")

                failing._apply_constraint_pc = fail_pc
            with pytest.raises(RuntimeError):
                failing.solve(easy_rhs)
            failure_record = dict(failing.diagnostics["last_solve"])
            assert failure_record.get("pc_usable") is False
            assert failure_record[
                "policy_exception_rejection_reason"
            ] == "exception_prevented_a_usable_V12_modal_return"
            assert failure_record["final_residual_evaluated"] is False
            assert (
                failing.diagnostics[
                    "terminal_normal_reject_snapshot_saved"
                ]
                is False
            )
    finally:
        for system in systems:
            system.destroy()
        _destroy_fixed_h6_modal_krylov_components(fixture, bundles, None)


def test_v12_modal_approximate_pc_is_usable_by_outer_right_fgmres():
    fixture, bundles, coupling, schur = _v12_fixed_h6_modal_components()
    systems: list[block_ldu._FixedH6ModalKrylovSystem] = []
    outer_ksp = outer_matrix = outer_pc_context = rhs_vec = solution = None
    policy_id = block_ldu.TASK041_V12_MODAL_SOLVER_POLICY_ID
    comm = MPI.COMM_WORLD
    owner = comm.size - 1
    mode_template = PETSc.Vec().createMPI(
        (40 if comm.rank == owner else 0, 40), comm=comm
    )
    try:
        system = block_ldu._FixedH6ModalKrylovSystem(
            coupling,
            bundles[0]["adapter"],
            bundles[1]["adapter"],
            modal_owner=owner,
            modal_solver_policy=policy_id,
            snapshot_callback=lambda _payload: {"status": "test_snapshot"},
        )
        _set_v12_test_schur(system, schur)
        systems.append(system)
        # The outer system is deliberately distinct from the inner modal
        # action, so the residual below checks the original outer A/f rather
        # than reusing the inner KSP's own S_H residual.
        outer_operator = 0.95 * schur + 0.05 * np.eye(40, dtype=np.complex128)
        assert np.linalg.norm(outer_operator - outer_operator.conj().T) > 1.0
        outer_matrix = _matrix_from_dense(
            mode_template, mode_template, outer_operator
        )
        rhs_vec = outer_matrix.createVecRight()
        solution = outer_matrix.createVecRight()
        modal_rhs = np.zeros(40, dtype=np.complex128)
        modal_rhs[:32] = 1.0 + 0.01j * np.arange(32)
        modal_rhs[32] = 0.05 - 0.01j
        _set_vector(rhs_vec, modal_rhs)

        class ModalApproximatePc:
            def __init__(self):
                self.inner_statuses = []

            def apply(self, _pc, source, target):
                local = (
                    np.asarray(source.getArray(readonly=True), dtype=np.complex128).copy()
                    if comm.rank == owner
                    else None
                )
                full_rhs = np.asarray(comm.bcast(local, root=owner), dtype=np.complex128)
                result = system.solve(full_rhs)
                self.inner_statuses.append(
                    dict(system.diagnostics["last_solve"])
                )
                target.set(0.0)
                if comm.rank == owner:
                    target.getArray()[:] = result

            def destroy(self, _pc=None):
                return None

        outer_pc_context = ModalApproximatePc()
        outer_ksp = PETSc.KSP().create(comm)
        outer_ksp.setOperators(outer_matrix)
        outer_ksp.setType(PETSc.KSP.Type.FGMRES)
        outer_ksp.setGMRESRestart(40)
        outer_ksp.setPCSide(PETSc.PC.Side.RIGHT)
        outer_ksp.setNormType(PETSc.KSP.NormType.UNPRECONDITIONED)
        outer_ksp.setInitialGuessNonzero(False)
        outer_ksp.setTolerances(rtol=1.0e-8, atol=0.0, max_it=40)
        pc = outer_ksp.getPC()
        pc.setType(PETSc.PC.Type.PYTHON)
        pc.setPythonContext(outer_pc_context)
        outer_ksp.setUp()
        outer_ksp.solve(rhs_vec, solution)

        computed = _gather_vector(solution)
        independent_residual = outer_operator @ computed - modal_rhs
        relative = float(
            np.linalg.norm(independent_residual) / np.linalg.norm(modal_rhs)
        )
        assert int(outer_ksp.getConvergedReason()) > 0
        assert relative <= 1.0e-8
        assert any(
            row.get("status") == "INNER_TARGET_NOT_MET_APPROX_RETURN"
            and 1.0e-3 < row.get("final_relative_residual", 0.0) <= 0.1
            and row.get("pc_usable") is True
            for row in outer_pc_context.inner_statuses
        )
        np.testing.assert_array_equal(_gather_vector(rhs_vec), modal_rhs)
    finally:
        if outer_ksp is not None:
            outer_ksp.destroy()
        if solution is not None:
            solution.destroy()
        if rhs_vec is not None:
            rhs_vec.destroy()
        if outer_matrix is not None:
            outer_matrix.destroy()
        mode_template.destroy()
        for system in systems:
            system.destroy()
        _destroy_fixed_h6_modal_krylov_components(fixture, bundles, None)


def test_v12_backup_switches_after_normal_primary_refusal_and_keeps_outer_residual():
    """Exercise one same-factor backup after a trusted normal primary return."""

    snapshot_calls: list[str] = []
    snapshot_scalar_histories: list[list[dict[str, Any]]] = []
    comm = MPI.COMM_WORLD
    owner = comm.size - 1

    def record_snapshot(payload):
        snapshot_calls.append(str(payload["snapshot_kind"]))
        snapshot_scalar_histories.append(list(payload.get("scalar_history", ())))
        return {
            "status": "written",
            "snapshot_kind": str(payload["snapshot_kind"]),
        }

    fixture = _v12_fixed_physical_backup_fixture(record_snapshot)
    bundle = fixture["bundle"]
    solver = fixture["solver"]
    side_inverses = (
        fixture["side_fixture"]["bottom_inverse"],
        fixture["side_fixture"]["top_inverse"],
    )
    factors_before = tuple(inverse._p4_factor for inverse in side_inverses)
    factor_destroy_counts_before = tuple(
        int(inverse._p4_factor.destroy_count) for inverse in side_inverses
    )
    modal_count = int(bundle.modal_count)
    bad_diagonal = np.geomspace(1.0e-12, 1.0e12, modal_count) * np.exp(
        1j * np.linspace(-0.2, 0.25, modal_count)
    )
    bad_schur = np.diag(bad_diagonal) @ np.asarray(
        solver.modal_constraint, dtype=np.complex128
    )
    _set_v12_test_schur(solver, bad_schur)
    primary_rhs = np.ones(modal_count, dtype=np.complex128)
    primary_rhs_before = primary_rhs.copy()
    outer_ksp = outer_matrix = outer_rhs = outer_solution = mode_template = None
    outer_pc_context = None
    try:
        backup_solution = bundle.solve(primary_rhs)
        assert np.array_equal(primary_rhs, primary_rhs_before)
        diagnostics = bundle.diagnostics
        audit = diagnostics["backup_switch_audit"]
        assert diagnostics["method"] == (
            "fixed_physical_balh_once_modal_gmres_research"
        )
        assert diagnostics["method_history"] == [
            "fixed_h6_modal_gmres_research",
            "fixed_physical_balh_once_modal_gmres_research",
        ]
        assert audit["requested"] is True
        assert audit["allowed"] is True
        assert audit["actual"] is True
        assert audit["switch_count"] == 1
        assert audit["same_live_side_factor_handles_verified"] is True
        assert audit["backup_linearity_gate"]["pass"] is True
        trigger = audit["trigger"]
        assert trigger["kind"] == (
            "normal_trusted_primary_return_eta_above_0.1"
        )
        assert trigger["safe_boundary"] == (
            "after_primary_modal_KSP_return_before_backup_modal_KSP_entry"
        )
        primary = trigger["primary_normal_return"]
        assert primary["status"] == (
            "PRIMARY_MODAL_TARGET_NOT_MET_BACKUP_ELIGIBLE"
        )
        assert primary["normal_primary_return_completed"] is True
        assert primary["trusted_iterate"] is True
        assert primary["input_unchanged"] is True
        assert primary["raw_residual_pass"] is False
        assert primary["final_residual_evaluated"] is True
        assert primary["backup_eligibility"]["eligible"] is True
        assert primary["backup_eligibility"]["raw_relative_residual"] > 0.1
        rank_rows = primary["rank_local_accounting"]
        assert [row["rank"] for row in rank_rows] == list(range(comm.size))
        owner_attempts = primary["owner_constraint_lu_solve_attempts"]
        assert isinstance(owner_attempts, int) and owner_attempts > 0
        for row in rank_rows:
            assert row["local_constraint_lu_solve_attempts"] == (
                owner_attempts if row["rank"] == owner else 0
            )
        trigger_rows = comm.allgather(
            json.dumps(trigger, sort_keys=True, separators=(",", ":"), allow_nan=False)
        )
        assert len(set(trigger_rows)) == 1
        primary_total = primary["cumulative_total_matmult_calls"]
        backup_record = diagnostics["last_solve"]
        assert backup_record["pc_usable"] is True
        assert backup_record["final_relative_residual"] <= 0.1
        assert diagnostics["cumulative_total_matmult_calls"] == (
            primary_total + backup_record["total_matmult_calls"]
        )
        assert audit["primary_diagnostics"]["primary_solver_record"] == primary
        assert audit["primary_diagnostics"]["method"] == (
            "fixed_h6_modal_gmres_research"
        )
        assert audit["primary_diagnostics"]["solve_count"] >= 1
        assert audit["primary_diagnostics"]["cumulative_solver_matmult_calls"] == (
            primary["cumulative_solver_matmult_calls"]
        )
        assert audit["primary_diagnostics"]["cumulative_total_matmult_calls"] == (
            primary["cumulative_total_matmult_calls"]
        )
        primary_scalar_history = audit["primary_diagnostics"]["scalar_history"]
        owner_snapshot_scalar_history = comm.bcast(
            snapshot_scalar_histories[0] if comm.rank == owner else None,
            root=owner,
        )
        assert primary_scalar_history == owner_snapshot_scalar_history
        assert all(
            row["iteration"] in (8, 16, 32)
            for row in primary_scalar_history
        )
        assert np.isfinite(backup_solution).all()
        snapshot_call_rows = comm.allgather(list(snapshot_calls))
        owner_snapshot_calls = snapshot_call_rows[owner]
        assert len(owner_snapshot_calls) <= 2
        assert owner_snapshot_calls.count("first_unmet_target") == 1
        assert owner_snapshot_calls.count("first_success_control") <= 1
        assert all(
            not kinds
            for rank, kinds in enumerate(snapshot_call_rows)
            if rank != owner
        )
        assert tuple(inverse._p4_factor for inverse in side_inverses) == factors_before
        assert bundle._backup_p4_factor_handles == factors_before
        assert all(
            action._side_inverse is inverse
            for action, inverse in zip(
                bundle._side_actions, side_inverses, strict=True
            )
        )
        assert tuple(
            int(inverse._p4_factor.destroy_count) for inverse in side_inverses
        ) == factor_destroy_counts_before
        assert all(inverse.diagnostics["destroyed"] is False for inverse in side_inverses)

        # The switched PC is then used by a small, independent right-FGMRES
        # outer equation; the acceptance check recomputes that outer A x - f.
        constraint = np.asarray(solver.modal_constraint, dtype=np.complex128).copy()
        mode_template = PETSc.Vec().createMPI(
            (modal_count if comm.rank == owner else 0, modal_count), comm=comm
        )
        outer_matrix = _matrix_from_dense(mode_template, mode_template, constraint)
        outer_rhs = outer_matrix.createVecRight()
        outer_solution = outer_matrix.createVecRight()
        outer_values = np.asarray(
            [0.7 + 0.03j * index for index in range(modal_count)],
            dtype=np.complex128,
        )
        _set_vector(outer_rhs, outer_values)
        class SwitchedModalPc:
            def __init__(self):
                self.calls = 0

            def apply(self, _pc, source, target):
                self.calls += 1
                bundle.set_outer_pc_apply_index(self.calls)
                local = (
                    np.asarray(source.getArray(readonly=True), dtype=np.complex128).copy()
                    if comm.rank == owner
                    else None
                )
                full = np.asarray(comm.bcast(local, root=owner), dtype=np.complex128)
                result = bundle.solve(full)
                target.set(0.0)
                if comm.rank == owner:
                    target.getArray()[:] = result

            def destroy(self, _pc=None):
                return None

        outer_pc_context = SwitchedModalPc()
        outer_ksp = PETSc.KSP().create(comm)
        outer_ksp.setOperators(outer_matrix)
        outer_ksp.setType(PETSc.KSP.Type.FGMRES)
        outer_ksp.setGMRESRestart(modal_count)
        outer_ksp.setPCSide(PETSc.PC.Side.RIGHT)
        outer_ksp.setNormType(PETSc.KSP.NormType.UNPRECONDITIONED)
        outer_ksp.setInitialGuessNonzero(False)
        outer_ksp.setTolerances(rtol=1.0e-8, atol=0.0, max_it=modal_count)
        outer_ksp.getPC().setType(PETSc.PC.Type.PYTHON)
        outer_ksp.getPC().setPythonContext(outer_pc_context)
        outer_ksp.setUp()
        outer_ksp.solve(outer_rhs, outer_solution)
        outer_x = _gather_vector(outer_solution)
        outer_residual = constraint @ outer_x - outer_values
        outer_relative = float(np.linalg.norm(outer_residual) / np.linalg.norm(outer_values))
        assert int(outer_ksp.getConvergedReason()) > 0
        assert outer_relative <= 1.0e-8
        np.testing.assert_array_equal(_gather_vector(outer_rhs), outer_values)
        assert bundle.diagnostics["method_history"] == diagnostics["method_history"]
    finally:
        if outer_ksp is not None:
            outer_ksp.destroy()
        for vector in (outer_solution, outer_rhs, mode_template):
            if vector is not None:
                vector.destroy()
        if outer_matrix is not None:
            outer_matrix.destroy()
        _destroy_v12_fixed_physical_backup_fixture(fixture)


def test_v12_backup_outer_stagnation_switches_at_next_pc_and_terminal_can_cancel():
    metrics = (
        "global_true_relative_residual",
        "bottom_true_relative_residual",
        "top_true_relative_residual",
        "modal_true_relative_residual",
    )

    def residual_point(iteration, **changes):
        values = {name: 1.0 for name in metrics}
        values.update(changes)
        return {"iteration": iteration, **values}

    def feed_rows(bundle, rows):
        observations = {}
        for row in rows:
            observed = bundle.observe_outer_true_residual(
                row, gate_threshold=5.0e-9
            )
            if row["iteration"] in (8, 16):
                observations[row["iteration"]] = observed
        return observations

    callback = lambda _payload: {"status": "recorded"}
    fixture = _v12_fixed_physical_backup_fixture(callback)
    try:
        bundle = fixture["bundle"]
        solver = fixture["solver"]
        primary_rhs = np.full(
            bundle.modal_count, 0.25 + 0.1j, dtype=np.complex128
        )
        primary_rhs_before = primary_rhs.copy()
        primary_solution = bundle.solve(primary_rhs)
        assert np.isfinite(primary_solution).all()
        np.testing.assert_array_equal(primary_rhs, primary_rhs_before)
        assert isinstance(bundle.diagnostics["last_solve"], dict)
        assert solver._backup_switches == 0
        assert solver.method == "fixed_h6_modal_gmres_research"
        observations = feed_rows(
            bundle, [residual_point(iteration) for iteration in range(17)]
        )
        assert observations[8]["status"] == "outer_progress_not_stalled"
        observation = observations[16]
        assert observation["status"] == "two_consecutive_outer_windows_stalled"
        assert observation["next_safe_boundary"] == (
            "next_outer_PC_modal_solve_before_KSP_entry"
        )
        assert observation["stalled_window_end_iterations"] == [8, 16]
        assert len(observation["windows"]) == 2
        assert [len(window["samples"]) for window in observation["windows"]] == [9, 9]
        assert all(window["stalled"] for window in observation["windows"])
        assert solver.method == "fixed_h6_modal_gmres_research"
        assert solver._backup_pending is True
        assert solver._backup_switches == 0
        zero_rhs = np.zeros(bundle.modal_count, dtype=np.complex128)
        result = bundle.solve(zero_rhs)
        np.testing.assert_array_equal(result, np.zeros_like(zero_rhs))
        assert bundle.diagnostics["backup_switch_audit"]["actual"] is True
        assert bundle.diagnostics["backup_switch_audit"]["trigger"]["status"] == (
            "two_consecutive_outer_windows_stalled"
        )
        assert solver._backup_pending is False
    finally:
        _destroy_v12_fixed_physical_backup_fixture(fixture)

    terminal_fixture = _v12_fixed_physical_backup_fixture(callback)
    try:
        bundle = terminal_fixture["bundle"]
        solver = terminal_fixture["solver"]
        terminal_observations = feed_rows(
            bundle, [residual_point(iteration) for iteration in range(17)]
        )
        assert terminal_observations[16]["status"] == (
            "two_consecutive_outer_windows_stalled"
        )
        terminal = {
            "identity": "multimetric_true_residual_gate.v1",
            "iteration": 17,
            "threshold": 5.0e-9,
            "all_finite_nonnegative": True,
            "positive": True,
            "decision": "CONVERGED_USER",
            "reason": "all true residuals passed",
            "residuals": {name: 1.0e-9 for name in metrics},
        }
        bundle.record_outer_terminal(terminal)
        assert solver._backup_pending is False
        assert solver._backup_switches == 0
        assert solver.method == "fixed_h6_modal_gmres_research"
        assert bundle.diagnostics["backup_switch_audit"]["status"] == (
            "backup_not_needed_outer_converged_before_next_PC_boundary"
        )
    finally:
        _destroy_v12_fixed_physical_backup_fixture(terminal_fixture)

    rebound_fixture = _v12_fixed_physical_backup_fixture(callback)
    try:
        rows = []
        for iteration in range(17):
            value = 0.2 if 3 <= iteration <= 7 else 1.0
            rows.append(residual_point(iteration, **{name: value for name in metrics}))
        observations = feed_rows(rebound_fixture["bundle"], rows)
        first_window = observations[8]["windows"][-1]
        assert first_window["end_residual_by_metric"][metrics[0]] == 1.0
        assert first_window["best_residual_by_metric"][metrics[0]] == 0.2
        assert first_window["improvement_fraction_by_metric"][metrics[0]] == 0.8
        assert observations[8]["status"] == "outer_progress_not_stalled"
        assert observations[16]["status"] == "outer_progress_not_stalled"
        assert rebound_fixture["solver"]._backup_pending is False
    finally:
        _destroy_v12_fixed_physical_backup_fixture(rebound_fixture)

    spike_fixture = _v12_fixed_physical_backup_fixture(callback)
    try:
        rows = [
            residual_point(
                iteration,
                **(
                    {"bottom_true_relative_residual": 10.0}
                    if iteration == 4
                    else {}
                ),
            )
            for iteration in range(17)
        ]
        for row in rows:
            if row["iteration"] >= 9:
                row.update({name: 0.7 for name in metrics})
        observations = feed_rows(spike_fixture["bundle"], rows)
        assert observations[8]["windows"][-1]["best_residual_by_metric"][
            "bottom_true_relative_residual"
        ] == 1.0
        assert observations[8]["windows"][-1]["stalled"] is True
        assert observations[16]["windows"][-1]["stalled"] is False
        assert observations[16]["status"] == "outer_progress_not_stalled"
        assert spike_fixture["solver"]._backup_pending is False
    finally:
        _destroy_v12_fixed_physical_backup_fixture(spike_fixture)

    block_progress_fixture = _v12_fixed_physical_backup_fixture(callback)
    try:
        rows = [
            residual_point(
                iteration,
                bottom_true_relative_residual=1.0 - 0.02 * iteration,
            )
            for iteration in range(17)
        ]
        observations = feed_rows(block_progress_fixture["bundle"], rows)
        assert observations[8]["windows"][-1]["improvement_fraction_by_metric"][
            "bottom_true_relative_residual"
        ] >= 0.1
        assert observations[16]["windows"][-1]["improvement_fraction_by_metric"][
            "bottom_true_relative_residual"
        ] >= 0.1
        assert observations[8]["windows"][-1]["unmet_block_metrics"] == list(
            metrics[1:]
        )
        assert observations[16]["status"] == "outer_progress_not_stalled"
        assert block_progress_fixture["solver"]._backup_pending is False
    finally:
        _destroy_v12_fixed_physical_backup_fixture(block_progress_fixture)

    passed_block_fixture = _v12_fixed_physical_backup_fixture(callback)
    try:
        rows = [
            residual_point(
                iteration,
                top_true_relative_residual=1.0e-10,
            )
            for iteration in range(17)
        ]
        observations = feed_rows(passed_block_fixture["bundle"], rows)
        first_window = observations[8]["windows"][-1]
        assert first_window["passed_metrics_at_window_end"] == [
            "top_true_relative_residual"
        ]
        assert first_window["required_metrics_at_window_end"] == [
            "global_true_relative_residual",
            "bottom_true_relative_residual",
            "modal_true_relative_residual",
        ]
        assert first_window["global_metric_required"] is True
        assert first_window["unmet_block_metrics"] == [
            "bottom_true_relative_residual",
            "modal_true_relative_residual",
        ]
        assert first_window["stalled"] is True
        assert observations[16]["status"] == (
            "two_consecutive_outer_windows_stalled"
        )
        assert passed_block_fixture["solver"]._backup_pending is True
    finally:
        _destroy_v12_fixed_physical_backup_fixture(passed_block_fixture)

    passed_then_rebounded_fixture = _v12_fixed_physical_backup_fixture(callback)
    try:
        rows = [
            residual_point(
                iteration,
                top_true_relative_residual=(
                    1.0e-10 if iteration == 3 else 1.0
                ),
            )
            for iteration in range(17)
        ]
        observations = feed_rows(passed_then_rebounded_fixture["bundle"], rows)
        second_window = observations[16]["windows"][-1]
        assert second_window["passed_metrics_in_window"] == []
        assert second_window["passed_metrics_in_segment"] == [
            "top_true_relative_residual"
        ]
        assert second_window["required_metrics_for_stagnation"] == [
            "global_true_relative_residual",
            "bottom_true_relative_residual",
            "top_true_relative_residual",
            "modal_true_relative_residual",
        ]
        assert second_window["unmet_block_metrics"] == [
            "bottom_true_relative_residual",
            "top_true_relative_residual",
            "modal_true_relative_residual",
        ]
        assert second_window["stalled"] is True
        # The first window made genuine best-residual progress; a transient
        # gate crossing does not make the regressed block disappear later.
        assert observations[16]["status"] == "outer_progress_not_stalled"
        assert passed_then_rebounded_fixture["solver"]._backup_pending is False
    finally:
        _destroy_v12_fixed_physical_backup_fixture(
            passed_then_rebounded_fixture
        )


def test_v12_finite_stop_waits_for_resolved_trial_and_two_fresh_windows():
    """A resolved one-trial route may stop finitely before outer max-it."""

    metrics = (
        "global_true_relative_residual",
        "bottom_true_relative_residual",
        "top_true_relative_residual",
        "modal_true_relative_residual",
    )
    fixture = _v12_fixed_physical_backup_fixture(
        lambda _payload: {"status": "recorded"}
    )
    solver = fixture["solver"]
    bundle = fixture["bundle"]
    try:
        solver._backup_switches = 1
        state = {
            "schema": "task041.v12.side_restart64_trial_state.v1",
            "policy_id": block_ldu.TASK041_V12_MODAL_BACKUP_POLICY_ID,
            "status": "candidate_captured",
            "resolved": False,
            "pending": True,
            "trial_count": 0,
        }
        solver._side_restart64_trial_state = state
        solver._start_outer_observation_segment(
            "post_backup_waiting_for_side_trial_resolution",
            boundary_reason="test_candidate_not_yet_resolved",
        )
        for iteration in range(17):
            observation = bundle.observe_outer_true_residual(
                {"iteration": iteration, **{name: 1.0 for name in metrics}},
                gate_threshold=5.0e-9,
            )
        assert observation["status"] == "two_consecutive_outer_windows_stalled"
        assert solver._post_backup_stop_pending is None
        assert solver.post_backup_stop_decision() is None

        state.update(
            {
                "status": "not_required_no_eligible_restart32_rhs",
                "resolved": True,
                "pending": False,
                "trial_count": 1,
                "result": {
                    "status": "not_required_no_eligible_restart32_rhs",
                    "side_solve_seen": {"bottom": True, "top": True},
                },
            }
        )
        solver._start_outer_observation_segment(
            "post_side_restart64_trial",
            boundary_reason="test_trial_resolved",
        )
        end_observation = None
        for iteration in range(17):
            end_observation = bundle.observe_outer_true_residual(
                {"iteration": iteration, **{name: 1.0 for name in metrics}},
                gate_threshold=5.0e-9,
            )
        stop = solver.post_backup_stop_decision()
        assert end_observation["status"] == "two_consecutive_outer_windows_stalled"
        assert stop is not None
        assert [row["end_iteration"] for row in stop["windows"]] == [8, 16]
        assert stop["converged"] is False
        assert stop["max_it_reached"] is False

        reason_code = int(PETSc.KSP.ConvergedReason.DIVERGED_MAX_IT)
        stop_request = {
            **stop,
            "reason_name": "DIVERGED_MAX_IT",
            "runtime_reason_source": (
                "petsc4py.PETSc.KSP.ConvergedReason.DIVERGED_MAX_IT"
            ),
            "reason_code": reason_code,
            "configured_max_it": 2048,
            "iterations_at_stop": 16,
            "current_ksp_iterate_available": True,
            "current_trusted_solution_retained": False,
            "original_rhs_retained": True,
        }
        solver.record_post_backup_policy_stop(stop_request)
        owned_rows = [
            {
                "rank": rank,
                "range": [rank, rank + 1],
                "global_size": MPI.COMM_WORLD.size,
                "solution_local_sha256": "a" * 64,
                "rhs_local_sha256_before": "b" * 64,
                "rhs_local_sha256_after": "b" * 64,
                "solution_finite_local": True,
                "rhs_unchanged_local": True,
            }
            for rank in range(MPI.COMM_WORLD.size)
        ]
        finite_record = {
            **stop_request,
            "current_trusted_solution_retained": True,
            "original_rhs_unchanged": True,
            "postsolve_all_finite_nonnegative": True,
            "postsolve_original_residual_pass": False,
            "original_rhs_global_size": MPI.COMM_WORLD.size,
            "rank_local_solution_rhs_binding": {
                "scope": "one owned record per MPI rank; no vector gather",
                "records": owned_rows,
            },
            "postsolve_true_residuals": {
                "reported_relative_residual": 0.2,
                "global_true_relative_residual": 0.2,
                "bottom_true_relative_residual": 0.2,
                "top_true_relative_residual": 0.2,
                "modal_true_relative_residual": 0.2,
            },
            "result_checkpoint_path": (
                "HybridBlockLduIterativeResult.solution -> "
                "Task039 retained_solution_checkpoint -> owner_sharded packet"
            ),
        }
        solver.finalize_post_backup_policy_stop(finite_record)
        retained = solver.diagnostics["post_backup_stop_record"]
        assert retained["current_trusted_solution_retained"] is True
        assert retained["original_rhs_unchanged"] is True
        assert retained["postsolve_original_residual_pass"] is False
        assert "owner_sharded packet" in retained["result_checkpoint_path"]
    finally:
        _destroy_v12_fixed_physical_backup_fixture(fixture)


def test_v12_restart32_restore_capacity_stop_retains_x_and_rhs(monkeypatch):
    """A real byte-refusal classification has a distinct finite stop path.

    The byte-gate schema is independently covered by the W0.7 callback tests;
    this state-machine fixture isolates the post-refusal outer handoff and x/f
    retention without claiming a real resource admission.
    """

    fixture = _v12_fixed_physical_backup_fixture(
        lambda _payload: {"status": "unused"}
    )
    solver = fixture["solver"]
    bundle = fixture["bundle"]
    refusal_gate = {"phase": "restore_restart32", "fixture_only": True}
    restart64_refusal_gate = {
        "phase": "allocate_restart64",
        "fixture_only": True,
    }
    monkeypatch.setattr(
        block_ldu,
        "_task041_v12_capacity_gate_has_byte_refusal",
            lambda gate: gate == refusal_gate or gate == restart64_refusal_gate,
    )
    trial = {
        "status": "capacity_gate_refused_restart32_restore",
        "stage": "restore_restart32",
        "gate": refusal_gate,
        "restart64_gate": restart64_refusal_gate,
        "restart32_restore_required": True,
        "restart32_restored": False,
        "restart32_restored_handle_live": False,
        "restore_capacity_stop_required": True,
        "restart64_trial_selected_restart": None,
        "selected_restart": None,
        "same_p4_factor_handle_all_ranks": True,
    }
    try:
        solver._backup_switches = 1
        solver._side_restart64_trial_state = {
            "schema": "task041.v12.side_restart64_trial_state.v1",
            "policy_id": block_ldu.TASK041_V12_MODAL_BACKUP_POLICY_ID,
            "status": "candidate_captured",
            "resolved": False,
            "pending": True,
            "trial_count": 0,
        }
        solver.resolve_side_restart64_trial(trial)
        solver._outer_last_observed_iteration = 16
        stop = bundle.post_backup_stop_decision()
        assert stop is not None
        assert stop["schema"] == "task041.v12.post_backup_capacity_stop.v1"
        assert stop["stop_reason"] == (
            "task041_v12_restart32_restore_workspace_capacity_refused"
        )
        assert stop.get("windows") in (None, [])
        assert stop["current_ksp_iterate_available"] is True
        assert stop["original_rhs_retained"] is True

        reason_code = int(PETSc.KSP.ConvergedReason.DIVERGED_MAX_IT)
        stop_request = {
            **stop,
            "reason_name": "DIVERGED_MAX_IT",
            "runtime_reason_source": (
                "petsc4py.PETSc.KSP.ConvergedReason.DIVERGED_MAX_IT"
            ),
            "reason_code": reason_code,
            "configured_max_it": 2048,
            "iterations_at_stop": 16,
            "max_it_reached": False,
            "converged": False,
            "current_ksp_iterate_available": True,
            "current_trusted_solution_retained": False,
            "original_rhs_retained": True,
        }
        solver.record_post_backup_policy_stop(stop_request)
        owner_rows = [
            {
                "rank": rank,
                "range": [rank, rank + 1],
                "global_size": MPI.COMM_WORLD.size,
                "solution_local_sha256": "a" * 64,
                "rhs_local_sha256_before": "b" * 64,
                "rhs_local_sha256_after": "b" * 64,
                "solution_finite_local": True,
                "rhs_unchanged_local": True,
            }
            for rank in range(MPI.COMM_WORLD.size)
        ]
        finalized = {
            **stop_request,
            "current_trusted_solution_retained": True,
            "original_rhs_unchanged": True,
            "postsolve_all_finite_nonnegative": True,
            "postsolve_original_residual_pass": False,
            "original_rhs_global_size": MPI.COMM_WORLD.size,
            "rank_local_solution_rhs_binding": {
                "scope": "one owned record per MPI rank; no vector gather",
                "records": owner_rows,
            },
            "postsolve_true_residuals": {
                "reported_relative_residual": 0.2,
                "global_true_relative_residual": 0.2,
                "bottom_true_relative_residual": 0.2,
                "top_true_relative_residual": 0.2,
                "modal_true_relative_residual": 0.2,
            },
            "result_checkpoint_path": (
                "HybridBlockLduIterativeResult.solution -> "
                "Task039 retained_solution_checkpoint -> owner_sharded packet"
            ),
        }
        solver.finalize_post_backup_policy_stop(finalized)
        retained = solver.diagnostics["post_backup_stop_record"]
        assert retained["status"] == "post_backup_restart32_restore_capacity_stop"
        assert retained["current_trusted_solution_retained"] is True
        assert retained["original_rhs_unchanged"] is True
        assert retained["postsolve_original_residual_pass"] is False
        assert "owner_sharded packet" in retained["result_checkpoint_path"]
    finally:
        _destroy_v12_fixed_physical_backup_fixture(fixture)


def test_v12_backup_does_not_fallback_after_primary_matmult_exception():
    fixture = _v12_fixed_physical_backup_fixture(
        lambda _payload: {"status": "unused"}
    )
    bundle = fixture["bundle"]
    solver = fixture["solver"]
    try:
        def fail_primary(_values):
            raise RuntimeError("injected primary MatMult failure")

        solver._modal_action.apply = fail_primary
        with pytest.raises(RuntimeError, match="modal KSP failed"):
            bundle.solve(np.ones(bundle.modal_count, dtype=np.complex128))
        diagnostics = bundle.diagnostics
        assert diagnostics["method"] == "fixed_h6_modal_gmres_research"
        assert diagnostics["backup_switches"] == 0
        assert diagnostics["backup_switch_audit"]["actual"] is False
        assert diagnostics["last_solve"]["status"] == "ksp_callback_failed"
        assert (
            "injected primary MatMult failure"
            in diagnostics["last_solve"]["error"]
        )
        for inverse in (
            fixture["side_fixture"]["bottom_inverse"],
            fixture["side_fixture"]["top_inverse"],
        ):
            assert inverse.diagnostics["destroyed"] is False
            assert inverse._p4_factor.destroy_count == 0
    finally:
        _destroy_v12_fixed_physical_backup_fixture(fixture)


def test_v12_modal_constructor_collectively_rejects_rank_local_bad_policy():
    if MPI.COMM_WORLD.size != 2:
        pytest.skip("rank-local policy validation requires MPI2")
    fixture, bundles, _dense_operator = _fixed_h6_modal_krylov_components()
    policy_id = block_ldu.TASK041_V12_MODAL_SOLVER_POLICY_ID
    policy_value = "not-a-registered-policy" if MPI.COMM_WORLD.rank == 0 else policy_id
    local_error = None
    try:
        try:
            block_ldu._FixedH6ModalKrylovSystem(
                fixture["coupling"],
                bundles[0]["adapter"],
                bundles[1]["adapter"],
                modal_owner=MPI.COMM_WORLD.size - 1,
                modal_solver_policy=policy_value,
                snapshot_callback=lambda _payload: {"status": "unused"},
            )
        except RuntimeError as exc:
            local_error = str(exc)
        assert local_error is not None
        synchronized_errors = MPI.COMM_WORLD.allgather(local_error)
        assert len(set(synchronized_errors)) == 1
        assert "input preflight failed" in local_error
        assert "rank 0: ValueError" in local_error
        assert all(bundle["adapter"].audit["destroyed"] is False for bundle in bundles)
    finally:
        _destroy_fixed_h6_modal_krylov_components(fixture, bundles, None)


def test_side_balh_anderson_inner_failure_is_synchronized_without_fallback(
    monkeypatch,
) -> None:
    fixture = _side_block_fixture()
    original_action = original_context = context = rhs = outer_result = None
    try:
        layout = fixture["layout"]
        context = block_ldu.create_side_balh_block_ldu_preconditioner(
            layout,
            fixture["bottom"],
            fixture["top"],
            fixture["coupling"],
            fixture["bottom_inverse"],
            fixture["top_inverse"],
            sampled_columns=None,
            sampled_column_roles=None,
            sampled_column_contract_sha256=None,
            use_anderson_modal_inner=True,
        )
        rhs = layout.pack(
            fixture["bottom"].b,
            fixture["top"].b,
            internal_modal_rhs_correction(fixture["coupling"]),
        )
        original_action, original_context = create_hybrid_assembled_block_action(
            fixture["bottom"],
            fixture["top"],
            fixture["coupling"],
        )
        before = {
            "bottom": fixture["bottom_inverse"].diagnostics["apply_count"],
            "top": fixture["top_inverse"].diagnostics["apply_count"],
        }
        solver_options = []

        def nonconverged(*_args, **kwargs):
            solver_options.append(dict(kwargs))
            return {
                "status": "not_converged",
                "stop_reason": "max_iterations",
                "solution": np.ones(context.modal_count, dtype=np.complex128),
                "unscaled_residual_norm": 0.25,
                "rhs_norm": 1.0,
                "relative_residual": 0.25,
                "iterations": 8,
                "max_iterations": 14,
                "function_evaluations": 8,
                "s_evaluation_count": 9,
                "constraint_lu_solve_calls": 8,
                "snes_converged_reason": int(
                    PETSc.SNES.ConvergedReason.DIVERGED_MAX_IT
                ),
                "callback_converged_reason": int(
                    PETSc.SNES.ConvergedReason.DIVERGED_MAX_IT
                ),
                "budget_exhausted": False,
                "side_action_calls": {"bottom": 0, "top": 0},
                "real_coordinate_embedding": True,
                "modal_coordinate_representation": (
                    "real_parts_then_imag_parts_in_complex128"
                ),
                "modal_coordinate_count": 2 * context.modal_count,
                "modal_coordinate_extra_bytes_per_explicit_vec": (
                    context.modal_count * np.dtype(PETSc.ScalarType).itemsize
                ),
                "modal_coordinate_extra_bytes_two_explicit_vecs": (
                    2 * context.modal_count * np.dtype(PETSc.ScalarType).itemsize
                ),
                "real_coordinate_subspace_violation": False,
                "residual_evaluation_history": [
                    {
                        "evaluation": 9,
                        "source": "final_validation",
                        "raw_residual_norm": 0.25,
                        "raw_target_metric": 0.25,
                        "finite": True,
                    }
                ],
            }

        monkeypatch.setattr(
            block_ldu, "solve_action_modal_schur_anderson", nonconverged
        )
        caught = None
        try:
            outer_result = block_ldu.solve_hybrid_block_ldu_iterative(
                original_action,
                rhs,
                context,
                config=block_ldu.HybridBlockLduIterativeConfig(
                    restart=5,
                    max_it=5,
                    threshold=5.0e-9,
                    ksp_type="fgmres",
                ),
            )
        except (RuntimeError, PETSc.Error, ValueError) as exc:
            caught = exc
        local_inner = context.inventory["modal_inner_solver"]["last_solve"]
        outcomes = MPI.COMM_WORLD.allgather(
            (
                caught is not None,
                local_inner["stop_reason"],
                local_inner["unscaled_residual_norm"],
                local_inner["s_evaluation_count"],
            )
        )
        assert all(outcome[0] for outcome in outcomes)
        assert len(set(outcomes)) == 1
        assert len(solver_options) == 1
        assert solver_options[0]["max_iterations"] == 14
        assert context._destroyed is True
        assert context.inventory["pc_apply_count"] == 0
        assert context.inventory["modal_inner_solver"]["not_converged_count"] == 1
        failed_inner = context.inventory["modal_inner_solver"]["last_solve"]
        assert failed_inner["max_iterations"] == 14
        assert failed_inner["s_evaluation_count"] == 9
        assert failed_inner["s_evaluation_count"] <= 16
        assert failed_inner["residual_evaluation_history"]
        after = {
            "bottom": fixture["bottom_inverse"].diagnostics["apply_count"],
            "top": fixture["top_inverse"].diagnostics["apply_count"],
        }
        assert after["bottom"] - before["bottom"] == 1
        assert after["top"] - before["top"] == 1
        assert fixture["bottom_inverse"].diagnostics["destroyed"] is False
        assert fixture["top_inverse"].diagnostics["destroyed"] is False
    finally:
        if outer_result is not None:
            outer_result.destroy()
        if context is not None and not context._destroyed:
            context.destroy()
        if rhs is not None:
            rhs.destroy()
        if original_action is not None:
            original_action.destroy()
        if original_context is not None:
            original_context.destroy()
        _destroy_side_block_fixture(fixture)


def test_side_balh_anderson_inner_repeats_frozen_sample_without_schur(monkeypatch):
    fixture = _side_block_fixture()
    context = None
    try:
        columns, roles, contract_sha = _sample_contract()
        before = {
            side: fixture[f"{side}_inverse"].diagnostics["apply_count"]
            for side in ("bottom", "top")
        }
        events = []

        def reject_full_schur(*_args, **_kwargs):
            raise AssertionError("sample gate must not build Schur columns")

        monkeypatch.setattr(
            block_ldu, "build_hybrid_action_modal_schur", reject_full_schur
        )
        context = block_ldu.create_side_balh_block_ldu_preconditioner(
            fixture["layout"],
            fixture["bottom"],
            fixture["top"],
            fixture["coupling"],
            fixture["bottom_inverse"],
            fixture["top_inverse"],
            sampled_columns=columns,
            sampled_column_roles=roles,
            sampled_column_contract_sha256=contract_sha,
            marker_callback=lambda event, detail: events.append(
                (event, dict(detail))
            ),
            use_anderson_modal_inner=True,
        )
        inventory = context.inventory
        gate = inventory["early_sample_gate"]
        assert gate["status"] == "passed"
        assert gate["pass"] is True
        assert gate["columns"] == columns
        assert gate["roles"] == roles
        assert gate["sha256"] == contract_sha
        assert gate["early_sample_repeat"]["finite"] is True
        assert gate["early_sample_repeat"]["limit"] == 1.0e-10
        assert gate["early_sample_repeat"]["pass"] is True
        assert gate["full_vs_sample"] == (
            "not_applicable_full_schur_not_materialized"
        )
        for key in ("full_vs_sample", "schur_lu_repeat"):
            assert inventory[key]["status"] == "not_applicable"
            assert "pass" not in inventory[key]
        assert inventory["modal_schur"] is None
        assert inventory["modal_schur_materialized"] is False
        assert inventory["modal_schur_column_count"] == 0
        assert [event for event, _ in events] == [
            "modal_sample_begin",
            "modal_sample_ready",
        ]
        after = {
            side: fixture[f"{side}_inverse"].diagnostics["apply_count"]
            for side in ("bottom", "top")
        }
        assert all(
            after[side] - before[side] == 2 * len(columns)
            for side in ("bottom", "top")
        )
        context.destroy()
        context = None
        assert fixture["bottom_inverse"].diagnostics["destroyed"] is False
        assert fixture["top_inverse"].diagnostics["destroyed"] is False
    finally:
        if context is not None:
            context.destroy()
        _destroy_side_block_fixture(fixture)


def test_side_balh_anderson_inner_stops_before_outer_on_sample_repeat_failure(
    monkeypatch,
):
    fixture = _side_block_fixture()
    try:
        columns, roles, contract_sha = _sample_contract()
        before = {
            side: fixture[f"{side}_inverse"].diagnostics["apply_count"]
            for side in ("bottom", "top")
        }
        original_apply = block_ldu.HybridActionModalSchurApply.apply
        call_count = 0

        def nonrepeating_apply(modal_action, modal_values):
            nonlocal call_count
            call_count += 1
            result = original_apply(modal_action, modal_values)
            if call_count > len(columns):
                result[0] += 1.0e-5
            return result

        monkeypatch.setattr(
            block_ldu.HybridActionModalSchurApply,
            "apply",
            nonrepeating_apply,
        )
        with pytest.raises(ValueError, match="Early sampled modal repeat Gate failed"):
            block_ldu.create_side_balh_block_ldu_preconditioner(
                fixture["layout"],
                fixture["bottom"],
                fixture["top"],
                fixture["coupling"],
                fixture["bottom_inverse"],
                fixture["top_inverse"],
                sampled_columns=columns,
                sampled_column_roles=roles,
                sampled_column_contract_sha256=contract_sha,
                use_anderson_modal_inner=True,
            )
        assert call_count == 2 * len(columns)
        after = {
            side: fixture[f"{side}_inverse"].diagnostics["apply_count"]
            for side in ("bottom", "top")
        }
        assert all(
            after[side] - before[side] == 2 * len(columns)
            for side in ("bottom", "top")
        )
        assert fixture["bottom_inverse"].diagnostics["destroyed"] is False
        assert fixture["top_inverse"].diagnostics["destroyed"] is False
    finally:
        _destroy_side_block_fixture(fixture)


def test_modal_real_coordinate_embedding_is_isometric_for_complex_values() -> None:
    modal_values = np.asarray(
        [0.4 + 0.3j, -0.2 + 0.8j, 0.7 - 0.6j, -0.5 - 0.1j],
        dtype=np.complex128,
    )
    original = modal_values.copy()

    coordinates = block_ldu._encode_modal_real_coordinates(modal_values)
    restored = block_ldu._decode_modal_real_coordinates(
        coordinates, modal_values.size
    )

    assert coordinates.shape == (2 * modal_values.size,)
    assert coordinates.dtype == np.complex128
    assert np.all(coordinates.imag == 0.0)
    assert np.array_equal(restored, modal_values)
    assert np.linalg.norm(coordinates) == pytest.approx(
        np.linalg.norm(modal_values), rel=0.0, abs=1.0e-15
    )
    assert np.array_equal(modal_values, original)
    assert (
        block_ldu.solve_action_modal_schur_anderson.__kwdefaults__[
            "real_coordinate_embedding"
        ]
        is False
    )
    assert (
        block_ldu.solve_action_modal_schur_anderson.__kwdefaults__[
            "max_iterations"
        ]
        == 8
    )


def test_side_balh_modal_inner_explicitly_selects_real_coordinates(monkeypatch) -> None:
    fixture = _side_block_fixture()
    modal_action = None
    modal_system = None
    original_rhs = np.asarray(
        [0.2 + 0.4j, -0.5 + 0.1j, 0.7 - 0.3j, -0.2 - 0.6j],
        dtype=np.complex128,
    )
    rhs_before = original_rhs.copy()
    captured = {}

    def solver_stub(action, rhs, **kwargs):
        captured["action"] = action
        captured["rhs"] = np.asarray(rhs, dtype=np.complex128).copy()
        captured["kwargs"] = dict(kwargs)
        return {
            "status": "not_converged",
            "stop_reason": "synthetic_route_probe",
            "solution": np.asarray(rhs, dtype=np.complex128).copy(),
            "unscaled_residual_norm": 1.0,
            "rhs_norm": float(np.linalg.norm(rhs)),
            "relative_residual": 1.0,
            "iterations": 0,
            "max_iterations": 14,
            "function_evaluations": 0,
            "s_evaluation_count": 0,
            "constraint_lu_solve_calls": 0,
            "snes_converged_reason": int(
                PETSc.SNES.ConvergedReason.DIVERGED_INNER
            ),
            "callback_converged_reason": int(
                PETSc.SNES.ConvergedReason.DIVERGED_INNER
            ),
            "budget_exhausted": False,
            "side_action_calls": {"bottom": 0, "top": 0},
            "residual_evaluation_history": [],
            "real_coordinate_embedding": True,
            "modal_coordinate_representation": (
                "real_parts_then_imag_parts_in_complex128"
            ),
            "modal_coordinate_count": 2 * len(rhs),
            "modal_coordinate_extra_bytes_per_explicit_vec": (
                len(rhs) * np.dtype(PETSc.ScalarType).itemsize
            ),
            "modal_coordinate_extra_bytes_two_explicit_vecs": (
                2 * len(rhs) * np.dtype(PETSc.ScalarType).itemsize
            ),
            "real_coordinate_subspace_violation": False,
        }

    monkeypatch.setattr(
        block_ldu, "solve_action_modal_schur_anderson", solver_stub
    )
    try:
        modal_action = block_ldu.HybridActionModalSchurApply(
            fixture["coupling"],
            fixture["bottom_inverse"],
            fixture["top_inverse"],
        )
        modal_system = block_ldu.HybridActionModalSchurAndersonSystem(
            modal_action,
            modal_owner=fixture["layout"].modal_owner,
        )
        with pytest.raises(RuntimeError, match="synthetic_route_probe"):
            modal_system.solve(original_rhs)

        assert np.array_equal(original_rhs, rhs_before)
        assert captured["action"] is modal_action
        assert np.array_equal(captured["rhs"], original_rhs)
        assert captured["kwargs"]["scale_residual_by_constraint"] is True
        assert captured["kwargs"]["real_coordinate_embedding"] is True
        assert captured["kwargs"]["max_iterations"] == 14
        assert captured["kwargs"]["_borrowed_constraint_factor"] is modal_system
        diagnostics = modal_system.diagnostics
        assert diagnostics["real_coordinate_embedding"] is True
        assert diagnostics["modal_coordinate_count"] == 2 * modal_system.modal_count
        assert diagnostics["modal_coordinate_extra_bytes_per_explicit_vec"] == (
            modal_system.modal_count * np.dtype(PETSc.ScalarType).itemsize
        )
        assert diagnostics["modal_coordinate_extra_bytes_two_explicit_vecs"] == (
            2 * modal_system.modal_count * np.dtype(PETSc.ScalarType).itemsize
        )
        assert diagnostics["constraint_lu_factorizations"] == 1
        assert diagnostics["not_converged_count"] == 1
        assert fixture["bottom_inverse"].diagnostics["destroyed"] is False
        assert fixture["top_inverse"].diagnostics["destroyed"] is False
    finally:
        if modal_system is not None:
            modal_system.destroy()
        elif modal_action is not None and not modal_action._destroyed:
            modal_action.destroy()
        _destroy_side_block_fixture(fixture)


def test_complex_qr_anderson_coefficients_match_independent_complex_lstsq() -> None:
    delta_f = np.asarray(
        [
            [1.0 + 0.5j, -0.2 + 0.9j, 0.7 - 0.4j],
            [0.3 - 0.8j, 1.1 + 0.2j, -0.6 + 0.5j],
            [-0.4 + 0.6j, 0.8 - 0.3j, 0.2 + 1.0j],
            [0.9 + 0.1j, -0.5 - 0.7j, 1.2 + 0.3j],
        ],
        dtype=np.complex128,
    )
    current_f = np.asarray(
        [0.2 + 0.7j, -0.9 + 0.1j, 0.5 - 0.6j, 0.3 + 0.4j],
        dtype=np.complex128,
    )
    original_matrix = delta_f.copy()
    original_vector = current_f.copy()

    coefficients, diagnostics = block_ldu._complex_anderson_qr_coefficients(
        delta_f, current_f
    )
    _, capture_diagnostics = block_ldu._complex_anderson_candidate_update(
        np.zeros(delta_f.shape[0], dtype=np.complex128),
        current_f,
        np.zeros_like(delta_f),
        delta_f,
        capture_coefficients=True,
    )
    expected = np.linalg.lstsq(delta_f, current_f, rcond=None)[0]
    fit_residual = delta_f @ coefficients - current_f

    assert diagnostics["effective_rank"] == delta_f.shape[1]
    assert diagnostics["discarded_column_count"] == 0
    assert np.array_equal(capture_diagnostics["_capture_gamma"], coefficients)
    assert np.allclose(coefficients, expected, rtol=2.0e-13, atol=2.0e-14)
    assert np.linalg.norm(delta_f.conj().T @ fit_residual) <= 2.0e-13
    assert np.linalg.norm(fit_residual) == pytest.approx(
        np.linalg.norm(delta_f @ expected - current_f), rel=2.0e-13, abs=2.0e-14
    )
    assert np.array_equal(delta_f, original_matrix)
    assert np.array_equal(current_f, original_vector)


def test_complex_qr_raw_metric_changes_gamma_objective_only() -> None:
    modal = np.asarray([0.2 + 0.4j, -0.3 + 0.1j, 0.7 - 0.2j], dtype=np.complex128)
    fixed_point = np.asarray([0.1 - 0.2j, 0.4 + 0.3j, -0.2 + 0.6j])
    delta_m = np.asarray(
        [[0.3 + 0.1j, -0.2 + 0.4j], [0.5 - 0.2j, 0.1 + 0.7j], [-0.4 + 0.3j, 0.6 - 0.1j]],
        dtype=np.complex128,
    )
    delta_f = np.asarray(
        [[0.2 + 0.8j, -0.5 + 0.1j], [0.9 - 0.4j, 0.3 + 0.6j], [-0.1 + 0.2j, 0.7 - 0.5j]],
        dtype=np.complex128,
    )
    raw_residual = np.asarray([0.6 + 0.2j, -0.1 + 0.9j, 0.4 - 0.7j])
    delta_raw = np.asarray(
        [[0.8 + 0.1j, -0.3 + 0.5j], [0.2 - 0.6j, 0.7 + 0.2j], [-0.5 + 0.4j, 0.1 + 0.9j]],
        dtype=np.complex128,
    )
    originals = tuple(
        values.copy() for values in (modal, fixed_point, delta_m, delta_f, raw_residual, delta_raw)
    )

    raw_candidate, raw_info = block_ldu._complex_anderson_candidate_update(
        modal,
        fixed_point,
        delta_m,
        delta_f,
        capture_coefficients=True,
        mixing_metric="raw_residual",
        raw_residual=raw_residual,
        delta_raw_residual=delta_raw,
    )
    expected_gamma = np.linalg.lstsq(delta_raw, raw_residual, rcond=None)[0]
    expected_fit = delta_raw @ expected_gamma - raw_residual
    expected_candidate = modal + fixed_point - (delta_m + delta_f) @ expected_gamma

    assert raw_info["mixing_metric"] == "raw_residual"
    assert raw_info["effective_rank"] == delta_raw.shape[1]
    assert np.allclose(raw_info["_capture_gamma"], expected_gamma, rtol=2.0e-13, atol=2.0e-14)
    assert np.linalg.norm(delta_raw.conj().T @ expected_fit) <= 2.0e-13
    assert raw_info["fit_residual_norm"] == pytest.approx(
        np.linalg.norm(expected_fit), rel=2.0e-13, abs=2.0e-14
    )
    assert np.allclose(raw_candidate, expected_candidate, rtol=2.0e-13, atol=2.0e-14)
    assert all(np.array_equal(actual, before) for actual, before in zip(
        (modal, fixed_point, delta_m, delta_f, raw_residual, delta_raw), originals
    ))

    identity_scaled, scaled_info = block_ldu._complex_anderson_candidate_update(
        modal,
        -raw_residual,
        delta_m,
        -delta_raw,
        capture_coefficients=True,
    )
    identity_raw, identity_info = block_ldu._complex_anderson_candidate_update(
        modal,
        -raw_residual,
        delta_m,
        -delta_raw,
        capture_coefficients=True,
        mixing_metric="raw_residual",
        raw_residual=raw_residual,
        delta_raw_residual=delta_raw,
    )
    assert scaled_info["mixing_metric"] == "C_scaled_residual"
    assert identity_info["mixing_metric"] == "raw_residual"
    assert np.allclose(
        scaled_info["_capture_gamma"], identity_info["_capture_gamma"],
        rtol=2.0e-13, atol=2.0e-14,
    )
    assert np.allclose(identity_scaled, identity_raw, rtol=2.0e-13, atol=2.0e-14)
    with pytest.raises(FloatingPointError, match="Raw Anderson residual is non-finite"):
        block_ldu._complex_anderson_candidate_update(
            modal,
            fixed_point,
            delta_m,
            delta_f,
            mixing_metric="raw_residual",
            raw_residual=np.full(modal.shape, np.nan + 0.0j),
            delta_raw_residual=delta_raw,
        )


def test_complex_qr_anderson_startup_rank_deficiency_and_nonfinite_history() -> None:
    modal = np.asarray([0.2 + 0.3j, -0.4 + 0.1j], dtype=np.complex128)
    fixed_point = np.asarray([0.05 - 0.2j, 0.3 + 0.4j], dtype=np.complex128)
    startup, startup_info = block_ldu._complex_anderson_candidate_update(
        modal, fixed_point, None, None
    )
    assert np.array_equal(startup, modal + fixed_point)
    assert startup_info["update"] == "fixed_point_startup"
    assert startup_info["history_column_count"] == 0

    independent = np.asarray([1.0 + 1.0j, 0.5 - 0.2j], dtype=np.complex128)
    dependent_history = np.column_stack((independent, 2.0 * independent))
    delta_m = np.column_stack(
        (
            np.asarray([0.3 + 0.2j, -0.1 + 0.5j]),
            np.asarray([-0.2 + 0.4j, 0.7 - 0.3j]),
        )
    ).astype(np.complex128)
    target = np.asarray([0.8 - 0.1j, -0.6 + 0.9j], dtype=np.complex128)
    candidate, rank_info = block_ldu._complex_anderson_candidate_update(
        modal, target, delta_m, dependent_history
    )
    expected_fit = np.linalg.lstsq(dependent_history, target, rcond=None)[0]
    expected_fit_residual = dependent_history @ expected_fit - target
    assert candidate is not None
    assert rank_info["effective_rank"] == 1
    assert rank_info["discarded_column_count"] == 1
    assert rank_info["fit_residual_norm"] == pytest.approx(
        np.linalg.norm(expected_fit_residual), rel=2.0e-13, abs=2.0e-14
    )

    zero_candidate, zero_info = block_ldu._complex_anderson_candidate_update(
        modal,
        fixed_point,
        np.zeros((modal.size, 1), dtype=np.complex128),
        np.zeros((modal.size, 1), dtype=np.complex128),
    )
    assert zero_candidate is None
    assert zero_info["update"] == "rank_zero_history"
    assert zero_info["effective_rank"] == 0
    with pytest.raises(FloatingPointError, match="history is non-finite"):
        block_ldu._complex_anderson_qr_coefficients(
            np.asarray([[np.nan + 0.0j], [1.0 + 0.0j]]),
            np.asarray([0.5 + 0.1j, -0.2 + 0.3j]),
        )


@pytest.mark.parametrize(
    ("raw_metric_mixing", "capture_trace", "expected_metric"),
    [
        (False, True, "C_scaled_residual"),
        (True, False, "raw_residual"),
    ],
)
def test_side_balh_complex_qr_modal_inner_keeps_raw_gate_and_borrows_sides(
    raw_metric_mixing: bool,
    capture_trace: bool,
    expected_metric: str,
) -> None:
    fixture = _side_block_fixture()
    context = None
    modal_system = None
    modal_action = None
    solution = None
    rhs = np.asarray(
        [0.2 + 0.4j, -0.5 + 0.1j, 0.7 - 0.3j, -0.2 - 0.6j],
        dtype=np.complex128,
    )
    assert np.linalg.norm(rhs) > 0.0
    rhs_before = rhs.copy()
    before = {
        side: fixture[f"{side}_inverse"].diagnostics["apply_count"]
        for side in ("bottom", "top")
    }
    try:
        context = block_ldu.create_side_balh_block_ldu_preconditioner(
            fixture["layout"],
            fixture["bottom"],
            fixture["top"],
            fixture["coupling"],
            fixture["bottom_inverse"],
            fixture["top_inverse"],
            sampled_columns=None,
            sampled_column_roles=None,
            sampled_column_contract_sha256=None,
            use_anderson_modal_inner=True,
            complex_qr_research=True,
            raw_metric_mixing=raw_metric_mixing,
            capture_modal_solve_trace=capture_trace,
        )
        modal_system = context.action_modal_schur_system
        modal_action = modal_system.modal_action
        assert modal_system.diagnostics["mixing_method"] == (
            "complex_qr_type_ii_research"
        )
        assert modal_system.diagnostics["mixing_metric"] == expected_metric
        assert modal_system.diagnostics["real_coordinate_embedding"] is False
        oversized_rhs = np.full(rhs.shape, 1.0e308 + 0.0j, dtype=np.complex128)
        with pytest.raises(ValueError, match="RHS norm is non-finite"):
            modal_system.solve(oversized_rhs)
        assert {
            side: fixture[f"{side}_inverse"].diagnostics["apply_count"]
            for side in ("bottom", "top")
        } == before
        try:
            solution = modal_system.solve(rhs)
        except RuntimeError as exc:
            assert "Modal Anderson inner solve did not converge" in str(exc)

        diagnostics = modal_system.diagnostics
        last_solve = diagnostics["last_solve"]
        assert last_solve["mixing_method"] == "complex_qr_type_ii_research"
        assert last_solve["mixing_metric"] == expected_metric
        assert last_solve["mixing_beta"] == 1.0
        assert last_solve["real_coordinate_embedding"] is False
        assert last_solve["modal_coordinate_representation"] == "complex128_modal_values"
        assert last_solve["max_iterations"] == 14
        assert last_solve["anderson_history"] == 4
        assert 1 <= last_solve["iterations"] <= 14
        assert 2 <= last_solve["s_evaluation_count"] <= 16
        assert last_solve["constraint_lu_solve_calls"] == last_solve[
            "s_evaluation_count"
        ]
        assert last_solve["constraint_lu_factorizations"] == 0
        assert last_solve["constraint_lu_borrowed"] is True
        assert last_solve["residual_evaluation_history"][-1]["source"] == (
            "final_validation"
        )
        assert last_solve["residual_evaluation_history"][0]["source"] == (
            "complex_qr_iteration"
        )
        assert last_solve["complex_qr_mixing_history"][0]["update"] == (
            "fixed_point_startup"
        )
        assert np.isfinite(last_solve["relative_residual"])
        expected_success = (
            last_solve["convergence_callback_target_reached"] is True
            and last_solve["final_unscaled_target_reached"] is True
            and last_solve["target_reached"] is True
            and last_solve["budget_exhausted"] is False
            and last_solve["invalid_failure"] is False
            and last_solve["stop_reason"] == "unscaled_residual_target"
        )
        assert (solution is not None) is expected_success
        if solution is not None:
            assert np.all(np.isfinite(solution))
            assert last_solve["status"] == "converged"
            assert last_solve["relative_residual"] <= 1.0e-2
        else:
            assert last_solve["status"] == "not_converged"
        assert np.array_equal(rhs, rhs_before)
        after = {
            side: fixture[f"{side}_inverse"].diagnostics["apply_count"]
            for side in ("bottom", "top")
        }
        for side in ("bottom", "top"):
            actual_calls = after[side] - before[side]
            assert actual_calls == last_solve["side_action_calls"][side]
            assert actual_calls == last_solve["s_evaluation_count"]
            assert diagnostics["side_action_call_count"][side] == actual_calls
        assert diagnostics["constraint_lu_factorizations"] == 1
        capture = modal_system.export_modal_solve_capture(MPI.COMM_WORLD)
        if capture_trace:
            if MPI.COMM_WORLD.rank == 0:
                assert capture["capture_status"] == "incomplete"
                assert [row["solve_id"] for row in capture["traces"]] == [1, 2]
                assert capture["traces"][0]["capture_complete"] is False
                real_solve_trace = capture["traces"][1]
                assert real_solve_trace["rhs_sha256"] == hashlib.sha256(
                    rhs.tobytes()
                ).hexdigest()
                assert real_solve_trace["s_evaluation_count"] == len(
                    real_solve_trace["evaluations"]
                )
                if last_solve["iterations"] > 1:
                    assert any(
                        update.get("gamma") is not None
                        for update in real_solve_trace["updates"]
                    )
            else:
                assert capture is None
        else:
            assert capture is None
        assert fixture["bottom_inverse"].diagnostics["destroyed"] is False
        assert fixture["top_inverse"].diagnostics["destroyed"] is False
        if MPI.COMM_WORLD.rank == 0:
            print(
                "complex QR modal candidate: "
                f"status={last_solve['status']}, raw={last_solve['relative_residual']:.6e}, "
                f"iterations={last_solve['iterations']}, S={last_solve['s_evaluation_count']}, "
                f"side_calls={last_solve['side_action_calls']}, "
                f"mixing={last_solve['mixing_metric']}, "
                f"mixing_steps={len(last_solve['complex_qr_mixing_history'])}",
                flush=True,
            )
    finally:
        if context is not None and not context._destroyed:
            context.destroy()
        elif modal_system is not None:
            modal_system.destroy()
        elif modal_action is not None and not modal_action._destroyed:
            modal_action.destroy()
        _destroy_side_block_fixture(fixture)


@pytest.mark.parametrize("raw_metric_mixing", [False, True])
def test_side_balh_complex_qr_budget_reserves_real_final_check(
    monkeypatch, raw_metric_mixing: bool
) -> None:
    fixture = _side_block_fixture()
    modal_action = None
    modal_system = None
    rhs = np.asarray(
        [0.2 + 0.4j, -0.5 + 0.1j, 0.7 - 0.3j, -0.2 - 0.6j],
        dtype=np.complex128,
    )
    rhs_before = rhs.copy()
    before = {
        side: fixture[f"{side}_inverse"].diagnostics["apply_count"]
        for side in ("bottom", "top")
    }
    monkeypatch.setattr(block_ldu, "_MODAL_ANDERSON_S_EVALUATION_LIMIT", 2)
    try:
        modal_action = block_ldu.HybridActionModalSchurApply(
            fixture["coupling"],
            fixture["bottom_inverse"],
            fixture["top_inverse"],
        )
        modal_system = block_ldu.HybridActionModalSchurAndersonSystem(
            modal_action,
            modal_owner=fixture["layout"].modal_owner,
            complex_qr_research=True,
            raw_metric_mixing=raw_metric_mixing,
        )
        with pytest.raises(RuntimeError, match="did not converge"):
            modal_system.solve(rhs)

        last_solve = modal_system.diagnostics["last_solve"]
        assert last_solve["status"] == "not_converged"
        assert last_solve["mixing_metric"] == (
            "raw_residual" if raw_metric_mixing else "C_scaled_residual"
        )
        assert last_solve["stop_reason"] == "budget_exhausted"
        assert last_solve["budget_exhausted"] is True
        assert last_solve["budget_reason"] == "S_EVALUATION_LIMIT"
        assert last_solve["invalid_failure"] is False
        assert last_solve["convergence_callback_target_reached"] is False
        assert last_solve["final_validation_evaluations"] == 1
        assert last_solve["budget_callback_skipped"] is False
        assert last_solve["function_evaluations"] == 1
        assert last_solve["iterations"] == 1
        assert last_solve["s_evaluation_count"] == 2
        assert [
            row["source"] for row in last_solve["residual_evaluation_history"]
        ] == ["complex_qr_iteration", "final_validation"]
        assert last_solve["constraint_lu_solve_calls"] == 2
        assert last_solve["constraint_lu_borrowed"] is True
        after = {
            side: fixture[f"{side}_inverse"].diagnostics["apply_count"]
            for side in ("bottom", "top")
        }
        assert last_solve["side_action_calls"] == {
            side: after[side] - before[side] for side in ("bottom", "top")
        }
        assert last_solve["side_action_calls"] == {"bottom": 2, "top": 2}
        assert np.array_equal(rhs, rhs_before)
        assert fixture["bottom_inverse"].diagnostics["destroyed"] is False
        assert fixture["top_inverse"].diagnostics["destroyed"] is False
    finally:
        if modal_system is not None:
            modal_system.destroy()
        elif modal_action is not None and not modal_action._destroyed:
            modal_action.destroy()
        _destroy_side_block_fixture(fixture)


@pytest.mark.parametrize("raw_metric_mixing", [False, True])
def test_side_balh_complex_qr_zero_rhs_uses_absolute_raw_gate(
    raw_metric_mixing: bool,
) -> None:
    fixture = _side_block_fixture()
    modal_action = None
    modal_system = None
    rhs = np.zeros(fixture["layout"].modal_count, dtype=np.complex128)
    rhs_before = rhs.copy()
    before = {
        side: fixture[f"{side}_inverse"].diagnostics["apply_count"]
        for side in ("bottom", "top")
    }
    try:
        modal_action = block_ldu.HybridActionModalSchurApply(
            fixture["coupling"],
            fixture["bottom_inverse"],
            fixture["top_inverse"],
        )
        modal_system = block_ldu.HybridActionModalSchurAndersonSystem(
            modal_action,
            modal_owner=fixture["layout"].modal_owner,
            complex_qr_research=True,
            raw_metric_mixing=raw_metric_mixing,
        )
        solution = modal_system.solve(rhs)
        last_solve = modal_system.diagnostics["last_solve"]
        assert np.array_equal(solution, np.zeros_like(solution))
        assert last_solve["status"] == "converged"
        assert last_solve["mixing_metric"] == (
            "raw_residual" if raw_metric_mixing else "C_scaled_residual"
        )
        assert last_solve["stop_reason"] == "unscaled_residual_target"
        assert last_solve["zero_rhs_absolute_residual"] is True
        assert last_solve["rhs_norm"] == 0.0
        assert last_solve["relative_residual"] == 0.0
        assert last_solve["convergence_callback_target_reached"] is True
        assert last_solve["final_unscaled_target_reached"] is True
        assert last_solve["budget_exhausted"] is False
        assert last_solve["invalid_failure"] is False
        assert last_solve["iterations"] == 0
        assert last_solve["function_evaluations"] == 1
        assert last_solve["final_validation_evaluations"] == 1
        assert last_solve["s_evaluation_count"] == 2
        assert last_solve["constraint_lu_solve_calls"] == 2
        assert last_solve["constraint_lu_borrowed"] is True
        after = {
            side: fixture[f"{side}_inverse"].diagnostics["apply_count"]
            for side in ("bottom", "top")
        }
        assert last_solve["side_action_calls"] == {
            side: after[side] - before[side] for side in ("bottom", "top")
        }
        assert last_solve["side_action_calls"] == {"bottom": 2, "top": 2}
        assert np.array_equal(rhs, rhs_before)
        assert fixture["bottom_inverse"].diagnostics["destroyed"] is False
        assert fixture["top_inverse"].diagnostics["destroyed"] is False
    finally:
        if modal_system is not None:
            modal_system.destroy()
        elif modal_action is not None and not modal_action._destroyed:
            modal_action.destroy()
        _destroy_side_block_fixture(fixture)


def test_side_balh_modal_trace_keeps_two_solves_and_gathers_owner_payload(
    monkeypatch,
) -> None:
    fixture = _side_block_fixture()
    rhs = np.asarray(
        [0.2 + 0.4j, -0.5 + 0.1j, 0.7 - 0.3j, -0.2 - 0.6j],
        dtype=np.complex128,
    )
    original_rhs = rhs.copy()
    owned_objects = []

    def run_two_solves(capture: bool):
        action = block_ldu.HybridActionModalSchurApply(
            fixture["coupling"],
            fixture["bottom_inverse"],
            fixture["top_inverse"],
        )
        system = block_ldu.HybridActionModalSchurAndersonSystem(
            action,
            modal_owner=fixture["layout"].modal_owner,
            complex_qr_research=True,
            capture_modal_solve_trace=capture,
        )
        owned_objects.append(system)
        before = {
            side: fixture[f"{side}_inverse"].diagnostics["apply_count"]
            for side in ("bottom", "top")
        }
        solutions = []
        summaries = []
        errors = []
        for _ in range(2):
            try:
                solutions.append(system.solve(rhs).copy())
                errors.append(None)
            except RuntimeError as exc:
                solutions.append(None)
                errors.append(str(exc))
            summaries.append(copy.deepcopy(system.diagnostics["last_solve"]))
        after = {
            side: fixture[f"{side}_inverse"].diagnostics["apply_count"]
            for side in ("bottom", "top")
        }
        calls = {side: after[side] - before[side] for side in ("bottom", "top")}
        return system, solutions, summaries, errors, calls

    try:
        off_system, off_solutions, off_summaries, off_errors, off_calls = (
            run_two_solves(False)
        )
        assert off_system.export_modal_solve_capture(MPI.COMM_WORLD) is None
        on_system, on_solutions, on_summaries, on_errors, on_calls = (
            run_two_solves(True)
        )
        calls_before_export = {
            side: fixture[f"{side}_inverse"].diagnostics["apply_count"]
            for side in ("bottom", "top")
        }
        capture = on_system.export_modal_solve_capture(MPI.COMM_WORLD)
        calls_after_export = {
            side: fixture[f"{side}_inverse"].diagnostics["apply_count"]
            for side in ("bottom", "top")
        }
        assert off_calls == on_calls
        assert off_calls == {
            side: sum(summary["side_action_calls"][side] for summary in off_summaries)
            for side in ("bottom", "top")
        }
        assert calls_before_export == calls_after_export
        assert np.array_equal(rhs, original_rhs)
        assert off_errors == on_errors
        for off_solution, on_solution, off_summary, on_summary in zip(
            off_solutions, on_solutions, off_summaries, on_summaries
        ):
            assert off_summary["status"] == on_summary["status"]
            assert off_summary["stop_reason"] == on_summary["stop_reason"]
            assert off_summary["target_reached"] == on_summary["target_reached"]
            assert off_summary["unscaled_residual_norm"] == pytest.approx(
                on_summary["unscaled_residual_norm"], rel=0.0, abs=0.0
            )
            off_scaled = off_summary["residual_evaluation_history"][-1][
                "scaled_residual_norm"
            ]
            on_scaled = on_summary["residual_evaluation_history"][-1][
                "scaled_residual_norm"
            ]
            assert off_scaled == pytest.approx(on_scaled, rel=0.0, abs=0.0)
            assert off_summary["s_evaluation_count"] == on_summary["s_evaluation_count"]
            assert off_summary["side_action_calls"] == on_summary["side_action_calls"]
            assert off_summary["relative_residual"] == pytest.approx(
                on_summary["relative_residual"], rel=0.0, abs=0.0
            )
            assert (off_solution is None) == (on_solution is None)
            if off_solution is not None:
                assert np.array_equal(off_solution, on_solution)
                assert off_summary["status"] == "converged"
                assert off_summary["relative_residual"] <= 1.0e-2
        if MPI.COMM_WORLD.rank == 0:
            assert capture["owner_rank"] == fixture["layout"].modal_owner
            assert capture["writer_rank"] == 0
            assert [row["solve_id"] for row in capture["traces"]] == [1, 2]
            assert [row["rhs_sha256"] for row in capture["traces"]] == [
                hashlib.sha256(rhs.tobytes()).hexdigest()
            ] * 2
            assert capture["array_payload_bytes"] <= capture[
                "array_payload_limit_bytes"
            ]
            assert capture["array_payload_limit_bytes"] == (
                block_ldu._modal_trace_array_limit_bytes(rhs.size)
            )
            assert capture["serialized_payload_size_basis"] == "compact_utf8_json"
            encoded_capture_size = len(
                json.dumps(
                    capture,
                    sort_keys=True,
                    separators=(",", ":"),
                    allow_nan=False,
                ).encode("utf-8")
            )
            assert encoded_capture_size <= capture[
                "serialized_payload_limit_bytes"
            ]
            assert capture["capture_complete"] is True
            assert capture["capture_status"] == "complete"
            for trace, summary in zip(capture["traces"], on_summaries):
                assert summary["status"] in {"converged", "not_converged"}
                assert trace["solver_status"] == summary["status"]
                assert trace["solver_stop_reason"] == summary["stop_reason"]
                assert trace["s_evaluation_count"] == summary["s_evaluation_count"]
                assert trace["capture_complete"] is True
                assert trace.get("capture_incomplete_reason") is None
                assert trace["g"] is not None
                assert len(trace["evaluations"]) == summary["s_evaluation_count"]
                assert all(
                    row["capture_complete"] is True
                    and all(row.get(key) is not None for key in ("m", "raw", "scaled"))
                    for row in trace["evaluations"]
                )
                assert trace["evaluations"][-1]["raw_target_metric"] == pytest.approx(
                    summary["relative_residual"], rel=0.0, abs=0.0
                )
                encoded = trace["g"]
                encoded_arrays = [encoded]
                encoded_arrays.extend(
                    row[key]
                    for row in trace["evaluations"]
                    for key in ("m", "raw", "scaled")
                    if row.get(key) is not None
                )
                encoded_arrays.extend(
                    row["gamma"]
                    for row in trace["updates"]
                    if row.get("gamma") is not None
                )
                trace_array_bytes = 0
                for descriptor in encoded_arrays:
                    raw = base64.b64decode(descriptor["data"], validate=True)
                    assert descriptor["dtype"] == "complex128"
                    assert descriptor["order"] == "C"
                    assert hashlib.sha256(raw).hexdigest() == descriptor["sha256"]
                    assert len(raw) == (
                        np.prod(descriptor["shape"]) * np.dtype(np.complex128).itemsize
                    )
                    trace_array_bytes += len(raw)
                assert trace_array_bytes == trace["captured_array_bytes"]
                g_raw = base64.b64decode(encoded["data"], validate=True)
                assert np.array_equal(
                    np.frombuffer(g_raw, dtype=np.complex128).reshape(encoded["shape"]),
                    rhs,
                )
                iteration_rows = [
                    row
                    for row in trace["evaluations"]
                    if row["source"] == "complex_qr_iteration"
                ]
                gamma_updates = [
                    row for row in trace["updates"] if row.get("gamma") is not None
                ]
                assert gamma_updates
                for update in gamma_updates:
                    source_count = update["source_evaluation_index"]
                    states = [
                        row
                        for row in iteration_rows
                        if row["evaluation"] <= source_count
                    ][-block_ldu._MODAL_SOLVE_TRACE_HISTORY_LIMIT - 1 :]
                    fixed_point_history = [
                        -np.frombuffer(
                            base64.b64decode(row["scaled"]["data"], validate=True),
                            dtype=np.complex128,
                        ).reshape(row["scaled"]["shape"])
                        for row in states
                    ]
                    delta_f = np.column_stack(
                        [
                            fixed_point_history[index + 1] - fixed_point_history[index]
                            for index in range(len(fixed_point_history) - 1)
                        ]
                    )
                    rcond = np.finfo(np.float64).eps * max(delta_f.shape)
                    expected_gamma, _, oracle_rank, _ = np.linalg.lstsq(
                        delta_f, fixed_point_history[-1], rcond=rcond
                    )
                    encoded_gamma = update["gamma"]
                    decoded_gamma = np.frombuffer(
                        base64.b64decode(encoded_gamma["data"], validate=True),
                        dtype=np.complex128,
                    ).reshape(encoded_gamma["shape"])
                    actual_fit = delta_f @ decoded_gamma - fixed_point_history[-1]
                    oracle_fit = delta_f @ expected_gamma - fixed_point_history[-1]
                    assert np.allclose(
                        delta_f @ decoded_gamma,
                        delta_f @ expected_gamma,
                        rtol=2.0e-13,
                        atol=2.0e-14,
                    )
                    assert np.linalg.norm(actual_fit) == pytest.approx(
                        np.linalg.norm(oracle_fit), rel=2.0e-13, abs=2.0e-14
                    )
                    if oracle_rank == delta_f.shape[1]:
                        assert update["mixing_scalars"]["effective_rank"] == oracle_rank
                        assert np.allclose(
                            decoded_gamma,
                            expected_gamma,
                            rtol=2.0e-13,
                            atol=2.0e-14,
                        )
                        orthogonality = np.linalg.norm(delta_f.conj().T @ actual_fit)
                        orthogonality_scale = max(
                            1.0,
                            np.linalg.norm(delta_f)
                            * np.linalg.norm(fixed_point_history[-1]),
                        )
                        assert orthogonality <= 5.0e-13 * orthogonality_scale
                for side in ("bottom", "top"):
                    side_rows = [
                        item["side_actions"][side]
                        for item in trace["evaluations"]
                    ]
                    assert all(
                        row["audit_index"] == "unknown"
                        and row["apply_count_source"] == "action_apply_count"
                        and row["apply_count"] > 0
                        for row in side_rows
                    )
                    last_applies = [row["last_apply"] for row in side_rows]
                    assert all(
                        "residual_norm" in row
                        and "iterations" in row
                        and "reason" in row
                        for row in last_applies
                    )
                    zero_rhs_records = [
                        row
                        for row in last_applies
                        if row["status"] == "ZERO_RHS_EXACT"
                    ]
                    assert zero_rhs_records
                    assert all(
                        row["reason"] is None
                        and row["iterations"] == 0
                        and row["rhs_norm"] == 0.0
                        and row["residual_norm"] == 0.0
                        for row in zero_rhs_records
                    )
                    nonzero_ksp_records = [
                        row for row in last_applies if row["rhs_norm"] > 0.0
                    ]
                    assert nonzero_ksp_records
                    assert all(
                        row["reason"] is not None and row["iterations"] > 0
                        for row in nonzero_ksp_records
                    )
            assert capture["serialized_payload_limit_bytes"] == 640 * 1024
            assert capture["array_payload_bytes"] == sum(
                trace["captured_array_bytes"] for trace in capture["traces"]
            )
        else:
            assert capture is None
        if MPI.COMM_WORLD.rank == fixture["layout"].modal_owner:
            assert on_system._modal_solve_trace_records == []

        overflow_solver_state = {
            "status": "not_converged",
            "stop_reason": "synthetic_existing_failure",
            "error": "original solver error remains unchanged " + ("x" * 4096),
        }
        on_system._last_solve = copy.deepcopy(overflow_solver_state)
        overflow_records = [
            {
                "solve_id": solve_id,
                "captured_array_bytes": 0,
                "capture_complete": True,
                "capture_incomplete_reason": None,
                "evaluations": [],
                "updates": [],
                "solver_status": overflow_solver_state["status"],
                "solver_stop_reason": overflow_solver_state["stop_reason"],
                "solver_error": overflow_solver_state["error"],
            }
            for solve_id in (1, 2)
        ]
        if MPI.COMM_WORLD.rank == fixture["layout"].modal_owner:
            on_system._modal_solve_trace_records.extend(
                copy.deepcopy(overflow_records)
            )
        monkeypatch.setattr(
            block_ldu, "_MODAL_SOLVE_TRACE_JSON_LIMIT_BYTES", 2048
        )
        overflow_capture = on_system.export_modal_solve_capture(MPI.COMM_WORLD)
        assert on_system.diagnostics["last_solve"] == overflow_solver_state
        if MPI.COMM_WORLD.rank == 0:
            assert overflow_capture["capture_status"] == "incomplete"
            assert overflow_capture["capture_complete"] is False
            assert overflow_capture["capture_incomplete_reason"] == (
                "serialized_payload_limit_exceeded"
            )
            assert overflow_capture["traces"] == []
            assert overflow_capture["trace_arrays_omitted"] is True
            assert overflow_capture["array_payload_bytes"] == 0
            assert overflow_capture["array_payload_bytes"] <= overflow_capture[
                "array_payload_limit_bytes"
            ]
            assert overflow_capture["serialized_payload_size_basis"] == (
                "compact_utf8_json"
            )
            overflow_json_bytes = len(
                json.dumps(
                    overflow_capture,
                    sort_keys=True,
                    separators=(",", ":"),
                    allow_nan=False,
                ).encode("utf-8")
            )
            assert overflow_json_bytes <= overflow_capture[
                "serialized_payload_limit_bytes"
            ]
            assert overflow_records[0]["solver_status"] == "not_converged"
            assert overflow_records[0]["solver_error"] == (
                overflow_solver_state["error"]
            )
        else:
            assert overflow_capture is None

        pending_trace = {
            "solve_id": 1,
            "captured_array_bytes": 0,
            "capture_complete": True,
            "evaluations": [],
            "updates": [],
        }
        if MPI.COMM_WORLD.rank == fixture["layout"].modal_owner:
            off_system._modal_solve_trace_records.append(pending_trace)
        calls_before_destroy = {
            side: fixture[f"{side}_inverse"].diagnostics["apply_count"]
            for side in ("bottom", "top")
        }
        off_system.destroy()
        assert off_system._modal_solve_trace_records == []
        calls_after_destroy = {
            side: fixture[f"{side}_inverse"].diagnostics["apply_count"]
            for side in ("bottom", "top")
        }
        assert calls_before_destroy == calls_after_destroy
        assert fixture["bottom_inverse"].diagnostics["destroyed"] is False
        assert fixture["top_inverse"].diagnostics["destroyed"] is False
    finally:
        for system in owned_objects:
            system.destroy()
        _destroy_side_block_fixture(fixture)


def test_side_balh_modal_trace_handoff_survives_real_ksp_pc_cleanup(
    monkeypatch,
) -> None:
    fixture = _side_block_fixture()
    original_action = original_context = context = rhs = None
    outer_result = None
    try:
        layout = fixture["layout"]
        rhs = layout.pack(
            fixture["bottom"].b,
            fixture["top"].b,
            internal_modal_rhs_correction(fixture["coupling"]),
        )
        original_action, original_context = create_hybrid_assembled_block_action(
            fixture["bottom"], fixture["top"], fixture["coupling"]
        )
        context = block_ldu.create_side_balh_block_ldu_preconditioner(
            layout,
            fixture["bottom"],
            fixture["top"],
            fixture["coupling"],
            fixture["bottom_inverse"],
            fixture["top_inverse"],
            sampled_columns=None,
            sampled_column_roles=None,
            sampled_column_contract_sha256=None,
            use_anderson_modal_inner=True,
            complex_qr_research=True,
            capture_modal_solve_trace=True,
        )
        real_context_destroy = block_ldu.HybridBlockLduPreconditioner.destroy
        destroy_events = []

        def observe_context_destroy(instance, pc=None):
            if instance is context:
                frame = inspect.currentframe()
                caller = None
                try:
                    caller = None if frame is None else frame.f_back
                    if caller is None:
                        caller_function = "unknown"
                        caller_filename = "unknown"
                        caller_lineno = None
                        caller_source_line = "unknown"
                    else:
                        caller_function = caller.f_code.co_name
                        caller_filename = caller.f_code.co_filename
                        caller_lineno = int(caller.f_lineno)
                        caller_source_line = linecache.getline(
                            caller_filename, caller_lineno
                        ).strip()[:180]
                    if "ksp.destroy()" in caller_source_line:
                        cleanup_entry = "ksp_destroy_call"
                    elif "context.destroy()" in caller_source_line:
                        cleanup_entry = "context_destroy_fallback"
                    else:
                        cleanup_entry = "unknown"
                    handoff = instance._modal_solve_trace_handoff
                    destroy_events.append(
                        {
                            "rank": int(layout.comm.rank),
                            "pc_argument_is_none": pc is None,
                            "handoff_trace_count_before_destroy": (
                                0 if handoff is None else len(handoff)
                            ),
                            "adapter_trace_count_before_destroy": len(
                                instance.action_modal_schur_system._modal_solve_trace_records
                            ),
                            "caller_function": caller_function,
                            "caller_filename": caller_filename,
                            "caller_lineno": caller_lineno,
                            "caller_source_line": caller_source_line,
                            "cleanup_entry": cleanup_entry,
                        }
                    )
                finally:
                    del caller
                    del frame
            return real_context_destroy(instance, pc)

        monkeypatch.setattr(
            block_ldu.HybridBlockLduPreconditioner,
            "destroy",
            observe_context_destroy,
        )
        modal_system = context.action_modal_schur_system
        real_candidate_update = block_ldu._complex_anderson_candidate_update
        failure_triggered = {"value": False}

        def fail_second_inner_update(*args, **kwargs):
            if modal_system._solve_count == 2:
                failure_triggered["value"] = True
                raise np.linalg.LinAlgError("controlled bounded inner failure")
            return real_candidate_update(*args, **kwargs)

        monkeypatch.setattr(
            block_ldu,
            "_complex_anderson_candidate_update",
            fail_second_inner_update,
        )
        side_calls_before = {
            side: fixture[f"{side}_inverse"].diagnostics["apply_count"]
            for side in ("bottom", "top")
        }
        caught = None
        try:
            outer_result = block_ldu.solve_hybrid_block_ldu_iterative(
                original_action,
                rhs,
                context,
                config=block_ldu.HybridBlockLduIterativeConfig(
                    restart=20,
                    max_it=80,
                    threshold=5.0e-9,
                    ksp_type="fgmres",
                ),
            )
        except (RuntimeError, PETSc.Error, ValueError) as exc:
            caught = exc

        assert caught is not None
        assert "Modal Anderson inner solve did not converge" in str(caught)
        failure_triggered_by_rank = MPI.COMM_WORLD.allgather(
            bool(failure_triggered["value"])
        )
        assert [
            rank for rank, triggered in enumerate(failure_triggered_by_rank) if triggered
        ] == [layout.modal_owner]
        assert modal_system._solve_count == 2
        assert context._destroyed is True
        destroy_call_counts = MPI.COMM_WORLD.allgather(len(destroy_events))
        assert destroy_call_counts == [1] * MPI.COMM_WORLD.size
        destroy_event = destroy_events[0]
        destroy_handoff_counts = MPI.COMM_WORLD.allgather(
            destroy_event["handoff_trace_count_before_destroy"]
        )
        assert destroy_handoff_counts == [
            2 if rank == layout.modal_owner else 0
            for rank in range(MPI.COMM_WORLD.size)
        ]
        destroy_adapter_trace_counts = MPI.COMM_WORLD.allgather(
            destroy_event["adapter_trace_count_before_destroy"]
        )
        assert destroy_adapter_trace_counts == [0] * MPI.COMM_WORLD.size
        destroy_events_by_rank = MPI.COMM_WORLD.allgather(destroy_event)
        if MPI.COMM_WORLD.rank == 0:
            print(
                json.dumps(
                    {"destroy_events_by_rank": destroy_events_by_rank},
                    sort_keys=True,
                ),
                flush=True,
            )
        assert modal_system.diagnostics["destroyed"] is True
        assert modal_system.constraint_lu is None
        assert fixture["bottom_inverse"].diagnostics["destroyed"] is False
        assert fixture["top_inverse"].diagnostics["destroyed"] is False

        handoff = context._modal_solve_trace_handoff
        handoff_counts = MPI.COMM_WORLD.allgather(
            0 if handoff is None else len(handoff)
        )
        assert handoff_counts == [
            2 if rank == layout.modal_owner else 0
            for rank in range(MPI.COMM_WORLD.size)
        ]
        assert modal_system._modal_solve_trace_records == []
        s_evaluations_before_export = modal_system._s_evaluation_count
        side_calls_before_export = {
            side: fixture[f"{side}_inverse"].diagnostics["apply_count"]
            for side in ("bottom", "top")
        }
        capture = modal_system.export_modal_solve_capture(
            MPI.COMM_WORLD,
            writer_rank=0,
            trace_records=handoff,
        )
        context._modal_solve_trace_handoff = None
        assert modal_system._s_evaluation_count == s_evaluations_before_export
        assert side_calls_before_export == {
            side: fixture[f"{side}_inverse"].diagnostics["apply_count"]
            for side in ("bottom", "top")
        }
        side_calls_for_solver = {
            side: fixture[f"{side}_inverse"].diagnostics["apply_count"]
            - side_calls_before[side]
            for side in ("bottom", "top")
        }
        assert all(value > 0 for value in side_calls_for_solver.values())
        if MPI.COMM_WORLD.rank == 0:
            assert capture is not None
            assert capture["owner_rank"] == layout.modal_owner
            assert capture["writer_rank"] == 0
            assert [trace["solve_id"] for trace in capture["traces"]] == [1, 2]
            assert capture["traces"][0]["solver_status"] == "converged"
            assert capture["traces"][0]["capture_complete"] is True
            assert capture["traces"][1]["solver_status"] == "not_converged"
            assert capture["traces"][1]["s_evaluation_count"] <= 16
            assert capture["traces"][1]["solver_stop_reason"] == (
                "nonfinite_or_invalid_anderson_update"
            )
            assert capture["traces"][1]["capture_incomplete_reason"] == (
                "anderson_update_failed"
            )
            assert capture["array_payload_bytes"] > 0
            assert capture["array_payload_bytes"] <= capture[
                "array_payload_limit_bytes"
            ]
        else:
            assert capture is None
        assert context._modal_solve_trace_handoff is None
        unconsumed = [{"solve_id": 99}]
        context._modal_solve_trace_handoff = unconsumed
        context.release_modal_solve_trace_handoff()
        assert unconsumed == []
        assert context._modal_solve_trace_handoff is None
    finally:
        if outer_result is not None:
            outer_result.destroy()
        if context is not None and not context._destroyed:
            context.destroy()
        if rhs is not None:
            rhs.destroy()
        if original_action is not None:
            original_action.destroy()
        if original_context is not None:
            original_context.destroy()
        _destroy_side_block_fixture(fixture)
