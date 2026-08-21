"""Focused contracts for the fixed second-order local impedance candidate."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path

import numpy as np
import pytest
import ufl
from dolfinx import fem
from mpi4py import MPI

from benchmarks import task038_full3d_r4_checker as r4_checker
from src.solvers.common_3d_fields import incident_air_plane_wave_field
from src.solvers.fullspace_physical_action import FullspacePhysicalAction
from src.solvers.fullspace_second_order_impedance import (
    FIXED_SECOND_ORDER_FORM,
    FIXED_SECOND_ORDER_LOCAL_IMPEDANCE,
    FixedSecondOrderLocalImpedance,
    fixed_second_order_coefficients,
)
from src.solvers.fullspace_sweep import (
    FULLSPACE_R4_BACKWARD_ORDER,
    FULLSPACE_R4_C_TRANSMISSION,
    FULLSPACE_R4_FORWARD_ORDER,
    build_candidate_c,
)
from src.test.test_278_task038_fullspace_r4_sweep import _real_split_case


def _direct_coefficients(k0: float, n: complex) -> tuple[complex, complex, complex, complex]:
    n = complex(n)
    y0 = complex(-1j * k0 * n)
    a_s = complex(1j * k0 / (2.0 * n))
    a_p = complex(-1j * k0 / (2.0 * n))
    return y0, a_s, a_p, complex(a_p - a_s)


def _direct_pairing(topology, source_field, test_field, direction: str) -> complex:
    """Fresh assembled scalar oracle with explicit fixed coefficients."""

    u_plus = source_field("+")
    v_plus = test_field("+")
    u_t = ufl.as_vector((u_plus[0], u_plus[1]))
    v_t = ufl.as_vector((v_plus[0], v_plus[1]))
    grad_u = ufl.grad(u_plus)
    grad_v = ufl.grad(v_plus)
    grad_t_u = ufl.as_tensor(
        ((grad_u[0, 0], grad_u[0, 1]), (grad_u[1, 0], grad_u[1, 1]))
    )
    grad_t_v = ufl.as_tensor(
        ((grad_v[0, 0], grad_v[0, 1]), (grad_v[1, 0], grad_v[1, 1]))
    )
    div_t_u = grad_u[0, 0] + grad_u[1, 1]
    div_t_v = grad_v[0, 0] + grad_v[1, 1]
    dS = ufl.Measure(
        "dS",
        domain=topology.mesh,
        subdomain_data=topology.interface_facet_tags,
    )
    expression = 0
    for tag, lower, upper in topology.global_material_pairs:
        material = upper if direction == "forward" else lower
        y0, a_s, _a_p, d = _direct_coefficients(
            topology.cfg.k0,
            material.refractive_index,
        )
        expression += (
            y0 * ufl.inner(u_t, v_t)
            + (a_s / float(topology.cfg.k0**2)) * ufl.inner(grad_t_u, grad_t_v)
            + (d / float(topology.cfg.k0**2)) * div_t_u * ufl.conj(div_t_v)
        ) * dS(int(tag))
    local = fem.assemble_scalar(fem.form(expression))
    return complex(topology.mesh.comm.allreduce(local, op=MPI.SUM))


def _active_pairing(topology, output, test_field) -> complex:
    output_values = np.asarray(output.getArray(readonly=True), dtype=np.complex128)
    test_values = np.asarray(
        test_field.x.petsc_vec.getArray(readonly=True), dtype=np.complex128
    )
    local = np.vdot(
        test_values[topology.owned_trace_local_rows],
        output_values[topology.owned_trace_local_rows],
    )
    return complex(topology.mesh.comm.allreduce(local, op=MPI.SUM))


def _copy_field_vector(field):
    vector = field.x.petsc_vec.duplicate()
    field.x.petsc_vec.copy(vector)
    return vector


def _scaled_mpc_field(space, cfg, floquet_data, scale: complex):
    field = incident_air_plane_wave_field(space, cfg)
    field.x.array[:] *= scale
    field.x.scatter_forward()
    floquet_data.mpc.homogenize(field)
    floquet_data.mpc.backsubstitution(field)
    field.x.scatter_forward()
    return field


def _destroy_result(result) -> None:
    result.delta.destroy()
    result.action_delta.destroy()
    result.residual.destroy()


def _synthetic_candidate_c_record() -> dict:
    k0 = float(r4_checker.EXPECTED_K0)
    manifest = []
    for direction, n, class_key, classification, lower_tag, upper_tag in (
        ("forward", 1.0 + 0.0j, [1.0, 0.0, 1.0, 0.0, 1.0, 0.0, 1.0, 0.0], "homogeneous", 1, 1),
        ("backward", 1.0 + 0.0j, [1.0, 0.0, 1.0, 0.0, 1.0, 0.0, 1.0, 0.0], "homogeneous", 1, 1),
        ("forward", 1.0 + 0.2j, [1.0, 0.0, 1.0, 0.0, 2.0, 0.0, 1.0, 0.0], "nonhomogeneous", 1, 2),
        ("backward", 1.0 + 0.2j, [1.0, 0.0, 1.0, 0.0, 2.0, 0.0, 1.0, 0.0], "nonhomogeneous", 1, 2),
    ):
        y0, a_s, a_p, d = _direct_coefficients(k0, n)
        manifest.append(
            {
                "class_key": class_key,
                "direction": direction,
                "classification": classification,
                "lower_material_tag": lower_tag,
                "upper_material_tag": upper_tag,
                "neighbor_side": "upper" if direction == "forward" else "lower",
                "neighbor_n": [n.real, n.imag],
                "y0": [y0.real, y0.imag],
                "a_s": [a_s.real, a_s.imag],
                "a_p": [a_p.real, a_p.imag],
                "d": [d.real, d.imag],
            }
        )
    manifest_bytes = json.dumps(
        manifest, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    action_audit = {
        "slave_row_identity": False,
        "phase_application": "finalized_floquet_mpc_once",
        "global_matrix_materialized": False,
        "global_constraint_matrix_materialized": False,
        "global_condensed_schur_materialized": False,
        "cell_schur_matrix_materialized": False,
        "slab_matrix_materialized": False,
        "numeric_allgather": False,
        "factor_count": 0,
    }
    transmission = {
        "schema": "task038.fullspace-fixed-second-order-impedance.v1",
        "candidate": "C",
        "transmission": FIXED_SECOND_ORDER_LOCAL_IMPEDANCE,
        "operator_name": "fixed_second_order_local_impedance",
        "exact_local_dtn": False,
        "weak_form": FIXED_SECOND_ORDER_FORM,
        "weak_form_support": "interface_facet_dS_material_pair_tags_only",
        "derivative_semantics": "per_facet_broken_tangential_derivative",
        "forward_neighbor": "upper",
        "backward_neighbor": "lower",
        "parameters_frozen_before_rho": True,
        "spectral_threshold": "not_used",
        "local_patch_range": "not_used",
        "local_krylov_steps": 0,
        "factor_count": 0,
        "per_cell_retained_tensor_count": 0,
        "global_aij_materialized": False,
        "global_schur_materialized": False,
        "dense_interface_matrix_materialized": False,
        "growing_slab_factor_materialized": False,
        "numeric_allgather": False,
        "phase_application": "finalized_floquet_mpc_once",
        "slave_row_identity": False,
        "action_audits": {"forward": action_audit, "backward": dict(action_audit)},
        "class_count": 2,
        "class_manifest": manifest,
        "class_manifest_serialized_bytes": len(manifest_bytes),
        "class_manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "retained_numeric_payload": {
            "fem_constant_complex_scalar_count": 12,
            "fem_constant_complex_scalar_bytes": 16,
            "fem_constant_values_bytes": 192,
            "a_p_storage": "derived_from_a_s_plus_d_not_retained_as_constant",
            "scaling": "O(material_pair_class_count)",
        },
        "retained_numeric_payload_bytes": 192,
        "retained_numeric_payload_scaling": "O(material_pair_class_count)",
    }
    return {
        "schema": r4_checker.R4_C_SCHEMA,
        "candidate": "C",
        "candidate_identity": {
            "candidate": "C",
            "schema": r4_checker.R4_C_SCHEMA,
            "transmission": FIXED_SECOND_ORDER_LOCAL_IMPEDANCE,
            "k0": k0,
        },
        "transmission_audit": transmission,
        "candidate_audit": {"transmission_audit": deepcopy(transmission)},
    }


def test_fixed_second_order_coefficients_are_frozen_te_tm_constants() -> None:
    k0 = 2.0
    n = 1.7 + 0.03j
    expected = _direct_coefficients(k0, n)
    observed = fixed_second_order_coefficients(k0, n)
    assert np.allclose(
        (observed.y0, observed.a_s, observed.a_p, observed.d),
        expected,
        rtol=0.0,
        atol=1.0e-15,
    )
    assert observed.d == observed.a_p - observed.a_s


@pytest.mark.skipif(MPI.COMM_WORLD.size not in {1, 2}, reason="serial or MPI2 fixture")
@pytest.mark.parametrize("degree", [2, 3])
def test_real_mixed_interface_action_matches_fresh_assembled_oracle(
    tmp_path: Path,
    degree: int,
) -> None:
    case = _real_split_case(tmp_path, degree)
    (
        cfg,
        _mesh_data,
        space,
        floquet_data,
        topology,
        _plan,
        full,
        split,
        dtn,
        source_field,
        source,
    ) = case
    test_field = _scaled_mpc_field(space, cfg, floquet_data, 0.6 - 0.2j)
    impedance = FixedSecondOrderLocalImpedance(
        space,
        topology,
        mpc=floquet_data.mpc,
    )
    try:
        audit = impedance.audit
        assert audit["transmission"] == FIXED_SECOND_ORDER_LOCAL_IMPEDANCE
        assert audit["weak_form"] == FIXED_SECOND_ORDER_FORM
        assert audit["exact_local_dtn"] is False
        assert audit["derivative_semantics"] == "per_facet_broken_tangential_derivative"
        assert audit["phase_application"] == "finalized_floquet_mpc_once"
        assert audit["class_count"] == 2
        assert len(audit["class_manifest"]) == 2 * audit["class_count"]
        assert {row["classification"] for row in audit["class_manifest"]} == {
            "homogeneous",
            "nonhomogeneous",
        }
        assert audit["parameters_frozen_before_rho"] is True
        assert audit["spectral_threshold"] == "not_used"
        assert audit["local_patch_range"] == "not_used"
        assert audit["local_krylov_steps"] == 0
        assert audit["factor_count"] == 0
        assert audit["per_cell_retained_tensor_count"] == 0
        assert audit["global_aij_materialized"] is False
        assert audit["global_schur_materialized"] is False
        assert audit["dense_interface_matrix_materialized"] is False
        assert audit["growing_slab_factor_materialized"] is False
        assert audit["numeric_allgather"] is False
        pair_by_tags = {
            (int(lower.tag), int(upper.tag)): (lower, upper)
            for _tag, lower, upper in topology.global_material_pairs
        }
        for row in audit["class_manifest"]:
            lower, upper = pair_by_tags[
                (row["lower_material_tag"], row["upper_material_tag"])
            ]
            material = upper if row["direction"] == "forward" else lower
            expected = _direct_coefficients(
                cfg.k0,
                material.refractive_index,
            )
            assert row["neighbor_side"] == (
                "upper" if row["direction"] == "forward" else "lower"
            )
            assert np.allclose(
                row["neighbor_n"],
                [material.refractive_index.real, material.refractive_index.imag],
                rtol=0.0,
                atol=1.0e-15,
            )
            for field, value in zip(
                ("y0", "a_s", "a_p", "d"),
                expected,
                strict=True,
            ):
                assert np.allclose(
                    row[field],
                    [value.real, value.imag],
                    rtol=0.0,
                    atol=1.0e-15,
                )
        manifest_bytes = json.dumps(
            audit["class_manifest"],
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        assert audit["class_manifest_serialized_bytes"] == len(manifest_bytes)
        assert audit["class_manifest_sha256"] == hashlib.sha256(
            manifest_bytes
        ).hexdigest()
        payload = audit["retained_numeric_payload"]
        expected_scalar_count = 2 * audit["class_count"] * 3
        assert payload["fem_constant_complex_scalar_count"] == expected_scalar_count
        assert payload["fem_constant_complex_scalar_bytes"] == np.dtype(
            np.complex128
        ).itemsize
        assert payload["fem_constant_values_bytes"] == (
            expected_scalar_count * np.dtype(np.complex128).itemsize
        )
        assert payload["a_p_storage"] == (
            "derived_from_a_s_plus_d_not_retained_as_constant"
        )
        assert payload["scaling"] == "O(material_pair_class_count)"
        assert audit["retained_numeric_payload_bytes"] == payload[
            "fem_constant_values_bytes"
        ]
        assert audit["retained_numeric_payload_scaling"] == (
            "O(material_pair_class_count)"
        )
        for action_audit in audit["action_audits"].values():
            assert action_audit["slave_row_identity"] is False
            assert action_audit["phase_application"] == "finalized_floquet_mpc_once"
        manifest_payload = json.dumps(audit["class_manifest"], sort_keys=True)
        assert len(set(MPI.COMM_WORLD.allgather(manifest_payload))) == 1
        assert len(set(MPI.COMM_WORLD.allgather(topology.canonical_sha256))) == 1
        assert len(set(MPI.COMM_WORLD.allgather(topology.canonical_global_count))) == 1

        for direction in ("forward", "backward"):
            observed = impedance.apply(source, direction)
            try:
                expected = _direct_pairing(
                    topology,
                    source_field,
                    test_field,
                    direction,
                )
                actual = _active_pairing(topology, observed, test_field)
                assert abs(actual - expected) <= 1.0e-11 * max(abs(expected), 1.0)
                assert observed.norm() > 0.0
            finally:
                observed.destroy()

            source_two_field = _scaled_mpc_field(
                space,
                cfg,
                floquet_data,
                -0.35 + 0.4j,
            )
            source_two = _copy_field_vector(source_two_field)
            observed_two = impedance.apply(source_two, direction)
            try:
                expected_two = _direct_pairing(
                    topology,
                    source_two_field,
                    test_field,
                    direction,
                )
                actual_two = _active_pairing(topology, observed_two, test_field)
                assert abs(actual_two - expected_two) <= 1.0e-11 * max(
                    abs(expected_two), 1.0
                )
            finally:
                observed_two.destroy()
                source_two.destroy()
    finally:
        impedance.destroy()
        for action in (full, *split):
            action.destroy()
        dtn.destroy()
        source.destroy()


@pytest.mark.skipif(MPI.COMM_WORLD.size not in {1, 2}, reason="serial or MPI2 fixture")
def test_candidate_c_reuses_four_step_sweep_and_closes_exact_action(
    tmp_path: Path,
) -> None:
    case = _real_split_case(tmp_path, 2)
    (
        cfg,
        _mesh_data,
        space,
        floquet_data,
        topology,
        plan,
        full,
        split,
        dtn,
        _source_field,
        source,
    ) = case
    impedance = FixedSecondOrderLocalImpedance(space, topology, mpc=floquet_data.mpc)
    physical = FullspacePhysicalAction(full, dtn)
    candidate = build_candidate_c(plan, split, dtn, impedance, physical)
    try:
        first = candidate.sweep(source)
        try:
            assert candidate.audit["candidate"] == "C"
            assert candidate.audit["transmission"] == FIXED_SECOND_ORDER_LOCAL_IMPEDANCE
            assert candidate.audit["transmission_audit"] == dict(impedance.audit)
            assert candidate.audit["forward_order"] == (0, 1)
            assert candidate.audit["backward_order"] == (1, 0)
            assert [(row["direction"], row["slab"]) for row in first.ledger] == [
                ("forward", 0),
                ("forward", 1),
                ("backward", 1),
                ("backward", 0),
            ]
            assert first.audit["exact_update_apply_count"] == 5
            assert first.audit["local_ksp_count"] == 2
            assert first.audit["local_ksp_restart"] == 8
            assert first.audit["local_ksp_max_it"] == 8
            assert first.audit["residual_propagation"] is True
            assert first.audit["recursive_residual_closure_relative_error"] <= 1.0e-11
            assert np.all(np.isfinite(first.residual.getArray(readonly=True)))
            assert first.audit["global_aij_materialized"] is False
            assert first.audit["global_schur_materialized"] is False
            assert first.audit["dense_interface_materialized"] is False
            assert first.audit["growing_slab_factor_materialized"] is False
        finally:
            first_ledger = first.ledger
            first_delta = np.asarray(
                first.delta.getArray(readonly=True), dtype=np.complex128
            ).copy()
            first_residual = np.asarray(
                first.residual.getArray(readonly=True), dtype=np.complex128
            ).copy()
            _destroy_result(first)

        repeat = candidate.sweep(source)
        try:
            assert repeat.ledger == first_ledger
            assert np.array_equal(repeat.delta.getArray(readonly=True), first_delta)
            assert np.array_equal(
                repeat.residual.getArray(readonly=True), first_residual
            )
            assert repeat.audit["exact_update_apply_count"] == 5
            assert repeat.audit["exact_update_apply_count_cumulative"] == 10
            assert repeat.audit["recursive_residual_closure_relative_error"] <= 1.0e-11
        finally:
            _destroy_result(repeat)
    finally:
        candidate.destroy()
        impedance.destroy()
        physical.destroy()
        source.destroy()


def test_candidate_c_checker_recomputes_manifest_coefficients_fail_closed() -> None:
    record = json.loads(json.dumps(_synthetic_candidate_c_record()))
    assert r4_checker._check_candidate_c_audit(record) == []

    missing = deepcopy(record)
    del missing["transmission_audit"]["class_manifest"][0]["a_p"]
    missing["candidate_audit"]["transmission_audit"] = deepcopy(
        missing["transmission_audit"]
    )
    assert any(
        "manifest coefficient a_p" in error
        for error in r4_checker._check_candidate_c_audit(missing)
    )

    wrong = deepcopy(record)
    wrong["transmission_audit"]["class_manifest"][0]["y0"] = [0.0, 0.0]
    wrong["candidate_audit"]["transmission_audit"] = deepcopy(
        wrong["transmission_audit"]
    )
    assert any(
        "manifest coefficient y0" in error
        for error in r4_checker._check_candidate_c_audit(wrong)
    )

    malformed = deepcopy(record)
    malformed["transmission_audit"]["class_manifest"][0]["class_key"] = [1.0, 2.0]
    malformed["candidate_audit"]["transmission_audit"] = deepcopy(
        malformed["transmission_audit"]
    )
    assert any(
        "class_key" in error
        for error in r4_checker._check_candidate_c_audit(malformed)
    )

    wrong_k0 = deepcopy(record)
    wrong_k0["candidate_identity"]["k0"] = 2.0
    assert any(
        "wavelength_nm=13.5" in error
        for error in r4_checker._check_candidate_c_audit(wrong_k0)
    )


def test_candidate_c_runner_checker_identity_contracts() -> None:
    runner = Path("benchmarks/run_task038_full3d_r4.py").read_text(encoding="utf-8")
    checker = Path("benchmarks/task038_full3d_r4_checker.py").read_text(encoding="utf-8")
    assert 'choices=("A", "C"), default="A"' in runner
    assert "FixedSecondOrderLocalImpedance" in runner
    assert "build_candidate_c" in runner
    assert 'R4_C_SCHEMA = "task038.full3d.iterative.r4.candidate-c-record.v1"' in checker
    assert "--candidate" in checker
    assert "from src.solvers" not in checker
    assert "petsc4py" not in checker
    assert "mpi4py" not in checker
    assert FULLSPACE_R4_C_TRANSMISSION == FIXED_SECOND_ORDER_LOCAL_IMPEDANCE
