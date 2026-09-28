"""Pure-array return checks, using an analytic complex triangular toy equation.

The fixture is not Maxwell, a teacher, FGMRES, or a deployed low-memory PC.
It deliberately supplies controlled states so independent witnesses can reject
incorrect native, cumulative-port, recovery and constraint results.
"""

import hashlib
from dataclasses import replace

import numpy as np
import pytest

from src.solvers.coarse_inverse_protocol import (
    CoarseReturnRejected,
    CoarseRHS,
    CoarseState,
    FactorDeclaration,
    InversePlan,
    IterationReport,
    ResidualWitness,
    StrictCoarseReturn,
)

A = np.array(
    [[2 + 1j, 0.3 - 0.1j, 0], [0, 3 - 0.5j, 0.2j], [0, 0, 1.5 + 0.2j]],
    dtype=np.complex128,
)
B = np.array([1j, 0.25, 0.1], dtype=np.complex128)
H = np.array([0.2, -0.1j, 0.05], dtype=np.complex128)
IDENTITY = hashlib.sha256(A.tobytes() + B.tobytes() + H.tobytes()).hexdigest()


def norm(x):
    scale = np.max(np.abs(x), initial=0.0)
    return float(scale * np.sqrt(np.sum(np.abs(x / scale) ** 2))) if scale else 0.0


def rhs_for(x=None, g=1 + 0.5j):
    x = np.array([1 + 2j, -0.25j, 0.75 - 0.1j], dtype=np.complex128) if x is None else x
    return CoarseRHS(
        np.append(A @ x - B * g, 0j).astype(np.complex128),
        np.array([g], dtype=np.complex128),
    )


def analytic_state(rhs):
    f = rhs.fe[:3] + B * rhs.port[0]
    # Back substitution for this toy only; no global factor or library solve.
    z = f[2] / A[2, 2]
    y = (f[1] - A[1, 2] * z) / A[1, 1]
    x = (f[0] - A[0, 1] * y) / A[0, 0]
    fe = np.array([x, y, z, 0j], dtype=np.complex128)
    return CoarseState(fe, rhs.port + H @ fe[:3])


class ControlledBackend:
    def __init__(self, transform=lambda state: state, report=None):
        self.plan = InversePlan(IDENTITY)
        self.transform = transform
        self.report = IterationReport(3) if report is None else report
        self.calls = 0

    def solve(self, rhs):
        self.calls += 1
        return self.transform(analytic_state(rhs)), self.report


def checks():
    def original(state, rhs):
        effective = rhs.fe[:3] + B * rhs.port[0]
        return ResidualWitness(A @ state.fe[:3] - effective, norm(effective))

    def ports(state, rhs):
        expected = rhs.port + H @ state.fe[:3]
        return ResidualWitness(state.port - expected, norm(expected))

    def recovery(state, rhs):
        expected = (rhs.fe[2] + B[2] * rhs.port[0]) / A[2, 2]
        return ResidualWitness(
            np.array([state.fe[2] - expected], dtype=np.complex128), abs(expected)
        )

    return {"original_a4": original, "port_closure": ports, "recovery": recovery}


def checker(backend=None, **overrides):
    kwargs = (
        checks() | {"witness_operator_sha256": IDENTITY, "slave_dofs": (3,)} | overrides
    )
    return StrictCoarseReturn(backend or ControlledBackend(), **kwargs)


@pytest.mark.parametrize("amplitude", [1.0, 1e-200, 1e100])
@pytest.mark.parametrize("phase", [1.0, 1j, np.exp(0.7j)])
def test_original_equation_and_cumulative_ports_under_complex_scaling(amplitude, phase):
    original = rhs_for()
    rhs = CoarseRHS(original.fe * amplitude * phase, original.port * amplitude * phase)
    verified = checker()
    result = verified.solve(rhs)
    assert verified.last_audit["status"] == "STRICT_RETURN_CHECK_PASS"
    assert max(verified.last_audit["checks"].values()) <= 1e-10
    assert result.fe[3] == 0
    assert not result.fe.flags.writeable and not result.port.flags.writeable


def test_nonzero_port_load_with_zero_fe_rhs_is_not_zero_rhs():
    backend = ControlledBackend()
    rhs = CoarseRHS(
        np.zeros(4, dtype=np.complex128), np.array([1j], dtype=np.complex128)
    )
    result = checker(backend).solve(rhs)
    assert backend.calls == 1 and norm(result.fe) > 0


def test_zero_rhs_returns_exact_zero_without_backend_but_checks_witnesses():
    backend = ControlledBackend()
    verified = checker(backend)
    state = verified.solve(
        CoarseRHS(np.zeros(4, dtype=np.complex128), np.zeros(1, dtype=np.complex128))
    )
    assert backend.calls == 0 and not np.any(state.fe) and not np.any(state.port)
    assert set(verified.last_audit["checks"]) == {
        "original_a4",
        "port_closure",
        "recovery",
    }


def test_native_equation_rejects_false_backend_success_and_preserves_failure_packet():
    packets = []
    backend = ControlledBackend(lambda s: CoarseState(s.fe * 1.001, s.port))
    verified = checker(backend, failure_sink=packets.append)
    rhs = rhs_for()
    with pytest.raises(CoarseReturnRejected, match="original_a4 residual"):
        verified.solve(rhs)
    assert packets[0]["rhs"] is rhs and packets[0]["state"] is not None
    assert packets[0]["audit"]["checks"]["original_a4"] > 1e-10


def test_increments_instead_of_cumulative_port_state_are_rejected():
    backend = ControlledBackend(lambda s: CoarseState(s.fe, s.port - H @ s.fe[:3]))
    verified = checker(backend)
    with pytest.raises(CoarseReturnRejected, match="port_closure residual"):
        verified.solve(rhs_for())
    assert verified.last_audit["checks"]["original_a4"] <= 1e-10


def test_recovery_check_is_independent_and_cannot_be_skipped():
    def bad_recovery(state, rhs):
        return ResidualWitness(np.array([2e-10 + 0j], dtype=np.complex128), 1.0)

    verified = checker(recovery=bad_recovery)
    with pytest.raises(CoarseReturnRejected, match="recovery residual"):
        verified.solve(rhs_for())
    assert len(verified.last_audit["checks"]) == 3


@pytest.mark.parametrize(
    "report",
    [
        IterationReport(257),
        IterationReport(1, restart=16),
        IterationReport(1, pc_side="left"),
        IterationReport(1, zero_start=False),
    ],
)
def test_iteration_contract_cannot_be_relaxed(report):
    with pytest.raises(CoarseReturnRejected, match="FGMRES32"):
        checker(ControlledBackend(report=report)).solve(rhs_for())


@pytest.mark.parametrize("input_bad", [True, False])
def test_slave_zero_is_exact_on_input_and_return(input_bad):
    rhs = rhs_for()
    if input_bad:
        fe = rhs.fe.copy()
        fe[3] = 1e-30
        rhs = CoarseRHS(fe, rhs.port)
        backend = ControlledBackend()
    else:
        backend = ControlledBackend(
            lambda s: CoarseState(s.fe + np.array([0j, 0j, 0j, 1e-30]), s.port)
        )
    with pytest.raises(CoarseReturnRejected, match="slave-zero"):
        checker(backend).solve(rhs)


@pytest.mark.parametrize(
    "wrong",
    [
        np.array([np.nan + 0j]),
        np.array([1j], dtype=np.complex64),
        np.array([[1j]], dtype=np.complex128),
    ],
)
def test_nonfinite_lower_precision_and_wrong_storage_are_rejected(wrong):
    with pytest.raises(ValueError):
        CoarseRHS(wrong, np.zeros(1, dtype=np.complex128))


def test_shape_mismatch_rejected_before_witnesses():
    backend = ControlledBackend(
        lambda s: CoarseState(s.fe, np.zeros(2, dtype=np.complex128))
    )
    with pytest.raises(CoarseReturnRejected, match="shape mismatch"):
        checker(backend).solve(rhs_for())


def test_operator_identity_and_immutable_plan_are_required():
    with pytest.raises(ValueError, match="identities differ"):
        checker(witness_operator_sha256="b" * 64)
    backend = ControlledBackend()
    verified = checker(backend)
    backend.plan = replace(backend.plan, representation_bytes=1)
    with pytest.raises(CoarseReturnRejected, match="plan changed"):
        verified.solve(rhs_for())


def test_bad_witness_cannot_report_pass_and_sink_failure_cannot_mask_rejection():
    def bad_witness(state, rhs):
        return ResidualWitness(np.array([1j]), float("nan"))

    def bad_sink(packet):
        raise OSError("simulated disk failure")

    verified = checker(original_a4=bad_witness, failure_sink=bad_sink)
    with pytest.raises(CoarseReturnRejected) as rejected:
        verified.solve(rhs_for())
    assert rejected.value.audit["failure_sink_error"] == "simulated disk failure"


@pytest.mark.parametrize(
    "scope,rows", [("global_p4", 53084), ("patch", 6001), ("bottom", 2049)]
)
def test_factor_construction_declarations_reject_forbidden_scopes_and_sizes(
    scope, rows
):
    with pytest.raises(ValueError):
        FactorDeclaration(scope, rows, 1)


def test_total_factor_and_representation_capacity_not_just_largest_object():
    factors = (FactorDeclaration("patch", 6000, 300 * 2**20),) * 2
    with pytest.raises(ValueError, match="total factor payload"):
        InversePlan(IDENTITY, factors=factors)
    with pytest.raises(ValueError, match="online buffers"):
        InversePlan(IDENTITY, representation_bytes=512 * 2**20 + 1)
    InversePlan(
        IDENTITY,
        factors=(FactorDeclaration("bottom", 2048, 512 * 2**20),),
        representation_bytes=512 * 2**20,
    )


def test_packet_owns_its_arrays_without_mutating_caller():
    source = np.array([1j, 2j], dtype=np.complex128)
    packet = CoarseRHS(source, np.array([0j], dtype=np.complex128))
    source[0] = 99j
    assert packet.fe[0] == 1j and source.flags.writeable


def test_p_transfer_then_condense_differs_from_trace_projection_after_condense():
    # Fine interior has two coordinates; coarse interior retains only one.
    a6 = np.array([[2, 0, 1], [0, 3, 2], [4, 5, 10]], dtype=np.complex128)
    p = np.array([[1, 0], [0, 0], [0, 1]], dtype=np.complex128)
    a4 = p.conj().T @ a6 @ p
    independently_condensed_p4 = a4[1, 1] - a4[1, 0] * a4[0, 1] / a4[0, 0]
    condensed_p6 = (
        a6[2, 2] - a6[2, 0] * a6[0, 2] / a6[0, 0] - a6[2, 1] * a6[1, 2] / a6[1, 1]
    )
    assert independently_condensed_p4 == 8
    assert abs(independently_condensed_p4 - condensed_p6) > 3


def test_curl_and_mass_must_be_combined_before_condensing():
    curl = np.array([[2, 1], [1, 3]], dtype=np.complex128)
    mass = np.array([[1, 0.5j], [-0.5j, 2]], dtype=np.complex128)

    def schur(a):
        return a[1, 1] - a[1, 0] * a[0, 1] / a[0, 0]

    assert abs(schur(curl - mass) - (schur(curl) - schur(mass))) > 0.1
