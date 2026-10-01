from __future__ import annotations

from types import SimpleNamespace

import basix
import numpy as np
import pytest
import ufl
from basix.ufl import element

from src.solvers.task39extra_p6_raw_tensor import Task39ExtraP6RawTensorCandidate
from src.solvers.task40extra_p6_reference_metric import (
    Task40ExtraP6ReferenceMetricCandidate,
)
from benchmarks.run_task39extra_v29_p6_tensor_pair import (
    _task40_ffcx_representatives,
    _task40_local_gate,
)


def _form_and_cfg():
    space_element = element("N1curl", "hexahedron", 6)
    coordinate_element = element("P", "hexahedron", 1, shape=(3,))
    domain = ufl.Mesh(coordinate_element)
    space = ufl.FunctionSpace(domain, space_element)
    trial, test = ufl.TrialFunction(space), ufl.TestFunction(space)
    mass_coefficient = 2.5 - 0.2j
    full_form = (
        ufl.inner(ufl.curl(trial), ufl.curl(test))
        + mass_coefficient * ufl.inner(trial, test)
    ) * ufl.dx(domain=domain)
    full_form += (
        np.complex128(0.0)
        * ufl.inner(ufl.curl(trial), ufl.curl(test))
        * ufl.dx(domain=domain)
    )
    cfg = SimpleNamespace(
        use_pml=False,
        divergence_penalty=0.0,
        mu_r=1.0,
        k0=1.0,
        eps_r=-mass_coefficient,
        substrate_index=1.0,
        grating_index=1.0,
        tags=SimpleNamespace(air=1, substrate=2, grating=3),
    )
    return space_element, full_form, cfg


def test_reference_metric_matches_blocked_gram_for_permuted_exact_geometry():
    space_element, full_form, cfg = _form_and_cfg()
    common = {
        "tag_aliases": {"otherwise": 1},
        "require_all_material_tags": False,
    }
    blocked = Task39ExtraP6RawTensorCandidate(
        space_element.basix_element, cfg, full_form, **common
    )
    candidate = Task40ExtraP6ReferenceMetricCandidate(
        space_element.basix_element, cfg, full_form, **common
    )

    reference_vertices = np.asarray(basix.geometry(basix.CellType.hexahedron))
    jacobian = np.asarray(
        [[0.0, 2.0, 0.0], [3.0, 0.0, 0.0], [0.0, 0.0, 4.0]],
        dtype=np.float64,
    )
    assert np.linalg.det(jacobian) < 0.0
    coordinates = (np.asarray([7.0, -5.0, 11.0]) + reference_vertices @ jacobian.T)

    expected = blocked.build(coordinates, tag=1, dimension=882)
    actual = candidate.build(coordinates, tag=1, dimension=882)
    error = np.linalg.norm(actual - expected)
    scale = max(np.linalg.norm(expected), np.finfo(float).tiny)
    assert error / scale < 2.0e-13
    assert np.isfinite(actual).all()

    audit = candidate.audit()
    assert audit["template_unique_backing_count"] == 6
    assert audit["template_unique_backing_bytes"] == 6 * 882 * 882 * 8
    assert audit["metric_contract"]["requires_exact_signed_permutation_jacobian"] is True
    assert audit["mass_coefficient_conjugated"] is False
    assert audit["full_matrix_built_before_schur"] is True


@pytest.mark.parametrize("shear", [0.25, 1.0e-14])
def test_reference_metric_falls_back_to_ffcx_for_non_axis_aligned_geometry(
    monkeypatch, shear
):
    space_element, full_form, cfg = _form_and_cfg()
    class _FFI:
        @staticmethod
        def string(value):
            return value

    compiled_form = SimpleNamespace(
        dtype=np.dtype(np.complex128),
        module=SimpleNamespace(ffi=_FFI()),
        ufcx_form=SimpleNamespace(signature=b"fixture-signature"),
    )
    candidate = Task40ExtraP6ReferenceMetricCandidate(
        space_element.basix_element,
        cfg,
        full_form,
        compiled_form=compiled_form,
        tag_aliases={"otherwise": 1},
        require_all_material_tags=False,
    )
    reference_vertices = np.asarray(basix.geometry(basix.CellType.hexahedron))
    jacobian = np.asarray(
        [[1.0, shear, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
        dtype=np.float64,
    )
    coordinates = reference_vertices @ jacobian.T

    with pytest.raises(NotImplementedError, match="axis-aligned"):
        candidate.build(coordinates, tag=1, dimension=882)

    fallback_tensor = np.full((882, 882), 3.0 + 2.0j, dtype=np.complex128)
    monkeypatch.setattr(
        "src.solvers.hcurl_assembly_time_condensation._tabulate_raw_tensor_class",
        lambda *_args, **_kwargs: fallback_tensor.copy(),
    )
    kernels = {tag: (object(),) for tag in (1, 2, 3)}
    actual = candidate(
        compiled_form,
        kernels,
        coordinates,
        tag=1,
        dimension=882,
    )
    assert np.array_equal(actual, fallback_tensor)
    audit = candidate.audit()
    assert audit["ffcx_geometry_fallback_count"] == 1
    assert audit["class_count"] == 1
    assert "axis-aligned" in next(iter(audit["ffcx_geometry_fallback_reasons"]))


def test_task40_ffcx_sample_selection_keeps_only_one_round12_collision_pair():
    classes = {
        (1, 1.0000000000001, 1.0, 1.0): np.zeros(1),
        (1, 1.0000000000002, 1.0, 1.0): np.zeros(1),
        (1, 2.0000000000001, 1.0, 1.0): np.zeros(1),
        (1, 2.0000000000002, 1.0, 1.0): np.zeros(1),
        (2, 3.0, 1.0, 1.0): np.zeros(1),
    }
    selected = _task40_ffcx_representatives(classes, {}, air_tag=99)
    collision_keys = [
        key
        for key, reasons in selected.items()
        if "distinct_exact_widths_collide_under_old_round12_key" in reasons
    ]
    assert len(collision_keys) == 2
    rounded_collision_groups = {
        (key[0], tuple(np.round(key[1:], 12))) for key in collision_keys
    }
    assert len(rounded_collision_groups) == 1


def test_task40_local_gate_applies_strict_internal_rhs_closure_limit():
    checks = {
        "matrix_frobenius_relative": 1.0e-11,
        "action_relative": 1.0e-12,
        "schur_relative": 1.0e-9,
        "recovery_map_relative": 1.0e-9,
        "nonzero_rhs_recovery_solution_relative": 1.0e-9,
        "native_nonzero_rhs_recovery_closure": 1.0e-9,
        "candidate_nonzero_rhs_recovery_closure": 1.0e-12,
    }
    assert not _task40_local_gate(checks)
    checks["native_nonzero_rhs_recovery_closure"] = 1.0e-11
    assert _task40_local_gate(checks)
