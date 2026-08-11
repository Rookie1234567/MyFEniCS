from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from inspect import signature, getsource
import json
from pathlib import Path

import numpy as np
import pytest

from src.solvers import hcurl_h2b_canonical_congruence as c0


ROOT = Path(__file__).resolve().parents[2]
R2_MANIFEST = ROOT / (
    "benchmarks/artifacts/task037_extra_development/"
    "h2a_r2_da8ddbb_run1/factor_store/manifest.json"
)


def _cell(
    class_key: str,
    constraint_key: str,
    expansion_key: str,
    independent_rows: tuple[int, ...],
    phase: complex = 1.0 + 0.0j,
    *,
    material: str = "epsilon-1",
    operator: str = "B0",
    numeric_authority: str = "9" * 64,
    orientation: object | None = None,
) -> dict[str, object]:
    base = np.asarray(
        (
            (1.0 + 0.0j, 0.5 + 0.25j),
            (0.75 - 0.25j, -0.25 + 0.5j),
            (1.25 + 0.0j, 0.0 + 0.75j),
            (0.5 - 0.5j, 0.25 + 0.25j),
        ),
        dtype=np.complex128,
    )
    cell = {
        "class_key_sha256": class_key,
        "constraint_pattern_sha256": constraint_key,
        "expansion_pattern_sha256": expansion_key,
        "numeric_matrix_sha256": numeric_authority,
        "orientation_identity": orientation or {"edge_signs": (1, -1, 1, -1)},
        "material_identity": {"tag": material, "epsilon": 1.0},
        "operator_identity": {"form": operator, "scalar": "complex128"},
        "cell_metric_identity": {"widths": (0.5, 0.5, 0.5)},
        "independent_global_rows": independent_rows,
        "csr_offsets": (0, 2, 4, 6, 8),
        "csr_columns": (0, 1, 1, 2, 0, 3, 2, 3),
        "coefficients": (base * phase).reshape(-1),
    }
    return cell


def _reference_cells():
    return (
        _cell("a" * 64, "b" * 64, "c" * 64, (100, 101, 102, 103)),
        _cell("d" * 64, "e" * 64, "f" * 64, (200, 101, 102, 103)),
    )


def _reference_and_member():
    reference = _reference_cells()
    member = (
        _cell("1" * 64, "2" * 64, "3" * 64, (200, 101, 102, 103), 1j),
        _cell("4" * 64, "5" * 64, "6" * 64, (100, 101, 102, 103), 1j),
    )
    reference_tokens = c0.build_canonical_row_tokens(
        (100, 101, 102, 103), reference, task037_extra_h2b=True
    )
    member_tokens = c0.build_canonical_row_tokens(
        (103, 100, 101, 102), member, task037_extra_h2b=True
    )
    return reference_tokens, member_tokens


def test_c0_tokens_are_immutable_and_enumeration_invariant():
    reference, _member = _reference_and_member()
    reversed_tokens = c0.build_canonical_row_tokens(
        (100, 101, 102, 103),
        (
            _cell("d" * 64, "e" * 64, "f" * 64, (200, 101, 102, 103)),
            _cell("a" * 64, "b" * 64, "c" * 64, (100, 101, 102, 103)),
        ),
        task037_extra_h2b=True,
    )
    assert c0.canonical_tokens_sha256(reference) == c0.canonical_tokens_sha256(
        reversed_tokens
    )
    assert tuple(token.token_sha256 for token in reference) == tuple(
        token.token_sha256 for token in reversed_tokens
    )
    assert tuple(token.provenance_sha256 for token in reference) == tuple(
        token.provenance_sha256 for token in reversed_tokens
    )
    renumbered = tuple(
        {
            **cell,
            "independent_global_rows": tuple(
                int(row) + 1000 for row in cell["independent_global_rows"]
            ),
        }
        for cell in _reference_cells()
    )
    renumbered_tokens = c0.build_canonical_row_tokens(
        (1100, 1101, 1102, 1103), renumbered, task037_extra_h2b=True
    )
    assert tuple(token.token_sha256 for token in reference) == tuple(
        token.token_sha256 for token in renumbered_tokens
    )
    assert hash(reference[0].structural_key)
    with pytest.raises((TypeError, FrozenInstanceError)):
        reference[0].structural_key += ("mutation",)

    _, reversed_member = _reference_and_member()
    normal_member = c0.build_canonical_row_tokens(
        (103, 100, 101, 102),
        (
            _cell("4" * 64, "5" * 64, "6" * 64, (100, 101, 102, 103), 1j),
            _cell("1" * 64, "2" * 64, "3" * 64, (200, 101, 102, 103), 1j),
        ),
        task037_extra_h2b=True,
    )
    reversed_transform = c0.build_monomial_transform(
        reference, reversed_member, task037_extra_h2b=True
    )
    normal_transform = c0.build_monomial_transform(
        reference, normal_member, task037_extra_h2b=True
    )
    assert reversed_transform.transform_sha256 == normal_transform.transform_sha256


def test_c0_raw_pattern_sha_is_provenance_not_matching_core():
    reference = _reference_cells()
    member = (
        _cell("4" * 64, "5" * 64, "6" * 64, (200, 101, 102, 103), 1j),
        _cell("7" * 64, "8" * 64, "0" * 64, (100, 101, 102, 103), 1j),
    )
    reference_tokens = c0.build_canonical_row_tokens(
        (100, 101, 102, 103), reference, task037_extra_h2b=True
    )
    member_tokens = c0.build_canonical_row_tokens(
        (103, 100, 101, 102), member, task037_extra_h2b=True
    )
    baseline = c0.build_monomial_transform(
        *_reference_and_member(), task037_extra_h2b=True
    )
    transform = c0.build_monomial_transform(
        reference_tokens, member_tokens, task037_extra_h2b=True
    )
    assert np.all(transform.phases == 1j)
    assert c0.canonical_tokens_sha256(reference_tokens) == c0.canonical_tokens_sha256(
        member_tokens
    )
    assert c0.canonical_tokens_provenance_sha256(reference_tokens) != (
        c0.canonical_tokens_provenance_sha256(member_tokens)
    )
    assert transform.audit()["reference_provenance_sha256"] != transform.audit()[
        "member_provenance_sha256"
    ]
    assert np.array_equal(transform.permutation, baseline.permutation)
    assert np.array_equal(transform.phases, baseline.phases)
    assert transform.transform_sha256 != baseline.transform_sha256


def test_c0_provenance_binds_actual_anchor_and_profile_with_fixed_raw_sha():
    baseline = c0.build_canonical_row_tokens(
        (100, 101, 102, 103), _reference_cells(), task037_extra_h2b=True
    )
    cells = _reference_cells()
    anchor_changed = dict(cells[0])
    anchor_changed["coefficients"] = tuple(
        complex(value) * (1.0 + 1.0e-6)
        for value in cells[0]["coefficients"]
    )
    anchor_tokens = c0.build_canonical_row_tokens(
        (100, 101, 102, 103),
        (anchor_changed, cells[1]),
        task037_extra_h2b=True,
    )
    profile_changed = dict(cells[0])
    profile_coefficients = np.array(
        cells[0]["coefficients"], dtype=np.complex128, copy=True
    )
    profile_coefficients[1] *= 1.0 + 1.0e-6
    profile_changed["coefficients"] = tuple(profile_coefficients)
    profile_tokens = c0.build_canonical_row_tokens(
        (100, 101, 102, 103),
        (profile_changed, cells[1]),
        task037_extra_h2b=True,
    )
    baseline_sha = c0.canonical_tokens_provenance_sha256(baseline)
    assert c0.canonical_tokens_provenance_sha256(anchor_tokens) != baseline_sha
    assert c0.canonical_tokens_provenance_sha256(profile_tokens) != baseline_sha


def test_c0_provenance_preserves_structural_pairing_in_aggregate_and_transform_sha():
    reference, member = _reference_and_member()
    provenance = tuple(token.provenance_sha256 for token in member)
    swapped = tuple(
        replace(
            token,
            provenance_sha256=provenance[(index + 1) % len(provenance)],
        )
        for index, token in enumerate(member)
    )
    assert sorted(token.provenance_sha256 for token in member) == sorted(
        token.provenance_sha256 for token in swapped
    )
    assert c0.canonical_tokens_provenance_sha256(member) != (
        c0.canonical_tokens_provenance_sha256(swapped)
    )
    baseline = c0.build_monomial_transform(
        reference, member, task037_extra_h2b=True
    )
    changed = c0.build_monomial_transform(
        reference, swapped, task037_extra_h2b=True
    )
    assert changed.transform_sha256 != baseline.transform_sha256


def test_known_permutation_and_unit_phases_apply_T_and_T_h():
    reference, member = _reference_and_member()
    transform = c0.build_monomial_transform(
        reference, member, task037_extra_h2b=True
    )
    assert np.array_equal(transform.permutation, np.asarray((3, 0, 1, 2), dtype=np.int32))
    assert np.array_equal(
        transform.phases,
        np.full(4, 1j, dtype=np.complex128),
    )
    assert transform.phase_unit_error <= 1.0e-14
    assert transform.unitary_error <= 1.0e-14
    vector = np.asarray((1.0 + 2j, 2.0 - 1j, -0.5 + 0.25j, 3.0 + 0j), dtype=np.complex128)
    transformed = transform.apply_t(vector)
    assert np.array_equal(
        transformed,
        np.asarray((1j * vector[1], 1j * vector[2], 1j * vector[3], 1j * vector[0])),
    )
    assert np.array_equal(transform.apply_t_h(transformed), vector)
    audit = transform.audit()
    assert audit["bijection"] is True
    assert audit["matrix_materialized"] is False
    assert audit["transform_sha256"] == transform.transform_sha256


def test_c0_nontrivial_floquet_phase_matches_without_profile_clustering():
    phase = np.exp(0.37j)
    reference = _reference_cells()
    member = (
        _cell("4" * 64, "5" * 64, "6" * 64, (200, 101, 102, 103), phase),
        _cell("7" * 64, "8" * 64, "0" * 64, (100, 101, 102, 103), phase),
    )
    reference_tokens = c0.build_canonical_row_tokens(
        (100, 101, 102, 103), reference, task037_extra_h2b=True
    )
    member_tokens = c0.build_canonical_row_tokens(
        (103, 100, 101, 102), member, task037_extra_h2b=True
    )
    transform = c0.build_monomial_transform(
        reference_tokens, member_tokens, task037_extra_h2b=True
    )
    assert np.allclose(transform.phases, phase, rtol=0.0, atol=1.0e-14)
    vector = np.arange(4, dtype=np.float64).astype(np.complex128) + 1j
    assert np.allclose(transform.apply_t_h(transform.apply_t(vector)), vector)


def test_c0_nonproportional_profile_over_tolerance_fails_closed():
    phase = np.exp(0.37j)
    reference_tokens = c0.build_canonical_row_tokens(
        (100, 101, 102, 103), _reference_cells(), task037_extra_h2b=True
    )
    changed = _cell("4" * 64, "5" * 64, "6" * 64, (200, 101, 102, 103), phase)
    coefficients = np.array(changed["coefficients"], dtype=np.complex128, copy=True)
    coefficients[2] *= 1.0 + 5.0e-14
    changed["coefficients"] = coefficients
    member_tokens = c0.build_canonical_row_tokens(
        (103, 100, 101, 102),
        (
            changed,
            _cell("7" * 64, "8" * 64, "0" * 64, (100, 101, 102, 103), phase),
        ),
        task037_extra_h2b=True,
    )
    with pytest.raises(
        c0.MonomialTransformNotProven,
        match="profile",
    ):
        c0.build_monomial_transform(
            reference_tokens, member_tokens, task037_extra_h2b=True
        )


def test_c0_small_profile_difference_uses_relative_not_absolute_tolerance():
    phase = 1j
    reference_cell = dict(_reference_cells()[0])
    reference_coefficients = np.array(
        reference_cell["coefficients"], dtype=np.complex128, copy=True
    )
    reference_coefficients[1] = 1.0 + 0.0j
    reference_coefficients[2] = 1.0e-10 + 0.0j
    reference_cell["coefficients"] = tuple(reference_coefficients)
    member_cell = _cell(
        "4" * 64,
        "5" * 64,
        "6" * 64,
        (200, 101, 102, 103),
        phase,
    )
    member_coefficients = np.array(
        member_cell["coefficients"], dtype=np.complex128, copy=True
    )
    member_coefficients[1] = phase
    member_coefficients[2] = (1.0e-10 * (1.0 + 5.0e-14)) * phase
    member_cell["coefficients"] = tuple(member_coefficients)
    reference_tokens = c0.build_canonical_row_tokens(
        (100, 101, 102, 103),
        (reference_cell, _reference_cells()[1]),
        task037_extra_h2b=True,
    )
    member_tokens = c0.build_canonical_row_tokens(
        (103, 100, 101, 102),
        (
            member_cell,
            _cell(
                "7" * 64,
                "8" * 64,
                "0" * 64,
                (100, 101, 102, 103),
                phase,
            ),
        ),
        task037_extra_h2b=True,
    )
    with pytest.raises(
        c0.MonomialTransformNotProven,
        match="profile",
    ):
        c0.build_monomial_transform(
            reference_tokens, member_tokens, task037_extra_h2b=True
        )


def test_c0_unitary_gate_checks_squared_modulus():
    phases = np.asarray((1.0 + 8.0e-15 + 0.0j,), dtype=np.complex128)
    assert abs(abs(phases[0]) - 1.0) <= 1.0e-14
    assert abs(abs(phases[0]) ** 2 - 1.0) > 1.0e-14
    permutation = np.asarray((0,), dtype=np.int32)
    with pytest.raises(c0.MonomialTransformNotProven):
        c0.MonomialTransform(
            permutation=permutation,
            phases=phases,
            reference_metadata_sha256="a" * 64,
            member_metadata_sha256="b" * 64,
            reference_provenance_sha256="c" * 64,
            member_provenance_sha256="d" * 64,
            transform_sha256=c0._transform_sha(
                "a" * 64,
                "b" * 64,
                "c" * 64,
                "d" * 64,
                permutation,
                phases,
            ),
        )


def test_c0_phase_is_from_csr_ratio_and_conflicts_fail_closed():
    reference, member = _reference_and_member()
    transform = c0.build_monomial_transform(reference, member, task037_extra_h2b=True)
    assert np.all(transform.phases == 1j)
    assert any(len(profile) > 1 for profile in reference[1].phase_profiles)

    conflicting = (
        _cell("d" * 64, "e" * 64, "f" * 64, (200, 101, 102, 103), -1j),
        _cell("a" * 64, "b" * 64, "c" * 64, (100, 101, 102, 103), 1j),
    )
    conflicting_tokens = c0.build_canonical_row_tokens(
        (100, 101, 102, 103), conflicting, task037_extra_h2b=True
    )
    with pytest.raises(c0.MonomialTransformNotProven, match="phases conflict"):
        c0.build_monomial_transform(
            reference, conflicting_tokens, task037_extra_h2b=True
        )



def test_c0_repeated_structural_contribution_is_not_guessable():
    cells = (
        _cell("a" * 64, "b" * 64, "c" * 64, (100, 101, 102, 103)),
        _cell("d" * 64, "e" * 64, "f" * 64, (100, 101, 102, 103), 1j),
    )
    for candidate in (cells, tuple(reversed(cells))):
        with pytest.raises(
            c0.MonomialTransformNotProven,
            match="not unique",
        ):
            c0.build_canonical_row_tokens(
                (100, 101, 102, 103), candidate, task037_extra_h2b=True
            )


def test_c0_rejects_orientation_monomial_map():
    cell = _cell("a" * 64, "b" * 64, "c" * 64, (0, 1, 2, 3))
    cell["orientation_monomial_map"] = (0, 1, 2, 3)
    with pytest.raises(
        c0.MonomialTransformNotProven,
        match="orientation_monomial_map",
    ):
        c0.build_canonical_row_tokens((0, 1, 2, 3), (cell,), task037_extra_h2b=True)


@pytest.mark.parametrize(
    "mutation",
    (
        "material",
        "operator",
        "numeric",
        "orientation",
        "incidence",
        "nonunit",
        "nonbijection",
    ),
)
def test_c0_metadata_mismatch_is_fail_closed(mutation):
    reference, member = _reference_and_member()
    if mutation == "material":
        cells = (
            _cell("d" * 64, "e" * 64, "f" * 64, (200, 101, 102, 103), 1j, material="other"),
            _cell("a" * 64, "b" * 64, "c" * 64, (100, 101, 102, 103), 1j),
        )
        changed = c0.build_canonical_row_tokens((100, 101, 102, 103), cells, task037_extra_h2b=True)
    elif mutation == "operator":
        cells = (
            _cell("d" * 64, "e" * 64, "f" * 64, (200, 101, 102, 103), 1j, operator="other"),
            _cell("a" * 64, "b" * 64, "c" * 64, (100, 101, 102, 103), 1j),
        )
        changed = c0.build_canonical_row_tokens((100, 101, 102, 103), cells, task037_extra_h2b=True)
    elif mutation == "numeric":
        cells = (
            _cell(
                "d" * 64,
                "e" * 64,
                "f" * 64,
                (200, 101, 102, 103),
                1j,
                numeric_authority="8" * 64,
            ),
            _cell("a" * 64, "b" * 64, "c" * 64, (100, 101, 102, 103), 1j),
        )
        changed = c0.build_canonical_row_tokens((100, 101, 102, 103), cells, task037_extra_h2b=True)
    elif mutation == "orientation":
        cells = (
            _cell(
                "d" * 64,
                "e" * 64,
                "f" * 64,
                (200, 101, 102, 103),
                1j,
                orientation={"edge_signs": (1, 1, 1, 1)},
            ),
            _cell("a" * 64, "b" * 64, "c" * 64, (100, 101, 102, 103), 1j),
        )
        changed = c0.build_canonical_row_tokens((100, 101, 102, 103), cells, task037_extra_h2b=True)
    elif mutation == "incidence":
        cells = (
            _cell("d" * 64, "e" * 64, "f" * 64, (200, 101, 100, 103), 1j),
            _cell("a" * 64, "b" * 64, "c" * 64, (100, 101, 102, 103), 1j),
        )
        changed = c0.build_canonical_row_tokens((100, 101, 102, 103), cells, task037_extra_h2b=True)
    elif mutation == "nonunit":
        cells = (
            _cell("d" * 64, "e" * 64, "f" * 64, (200, 101, 102, 103), 2.0 + 0j),
            _cell("a" * 64, "b" * 64, "c" * 64, (100, 101, 102, 103), 2.0 + 0j),
        )
        changed = c0.build_canonical_row_tokens((100, 101, 102, 103), cells, task037_extra_h2b=True)
    else:
        changed = member[:-1] + (member[0],)
    with pytest.raises((ValueError, c0.MonomialTransformNotProven)):
        c0.build_monomial_transform(reference, changed, task037_extra_h2b=True)


def test_c0_api_has_no_patch_matrix_or_factor_materialization_surface():
    assert "matrix" not in signature(c0.build_canonical_row_tokens).parameters
    assert "matrix" not in signature(c0.build_monomial_transform).parameters
    source = getsource(c0)
    assert "lu_factor" not in source
    assert "factorize" not in source
    assert "global_matrix" not in source


def test_c0_inverts_csr_columns_in_one_pass_and_checks_column_slots():
    source = getsource(c0._contributions_for_cell)
    assert "entries_by_column" in source
    assert source.count("for local_row in range") == 1
    invalid = _cell("a" * 64, "b" * 64, "c" * 64, (0, 1, 2, 3))
    invalid.pop("independent_global_rows")
    invalid["column_patch_slots"] = (0, 1, 2, 4)
    with pytest.raises(ValueError, match="column_patch_slots"):
        c0.build_canonical_row_tokens((0, 1, 2, 3), (invalid,), task037_extra_h2b=True)
    duplicate = _cell("a" * 64, "b" * 64, "c" * 64, (0, 1, 2, 3))
    duplicate.pop("independent_global_rows")
    duplicate["column_patch_slots"] = (0, 0, 2, 3)
    with pytest.raises(ValueError, match="one slot"):
        c0.build_canonical_row_tokens((0, 1, 2, 3), (duplicate,), task037_extra_h2b=True)


def test_real_r2_manifest_csr_ingestion_smoke_without_jit():
    """Smoke-test CSR ingestion only; R2 orientation qualification is separate."""
    manifest = json.loads(R2_MANIFEST.read_text())
    metadata = manifest["metadata"]
    item = metadata["classes"][0]
    root = R2_MANIFEST.parent
    offsets = np.load(root / item["offsets_path"], allow_pickle=False)
    columns = np.load(root / item["columns_path"], allow_pickle=False)
    coefficients = np.load(root / item["coefficients_path"], allow_pickle=False)
    tokens = c0.build_canonical_row_tokens(
        tuple(range(882)),
        (
            {
                "class_key_sha256": item["class_key_sha256"],
                "constraint_pattern_sha256": item["constraint_pattern_sha256"],
                "expansion_pattern_sha256": item["expansion_pattern_sha256"],
                "numeric_matrix_sha256": item["numeric_matrix_sha256"],
                "orientation_identity": {"pattern_identity": item["pattern_identity"]},
                "material_identity": metadata["config_identity"],
                "operator_identity": metadata["form_identity"],
                "cell_metric_identity": {
                    "shape": item["numeric_matrix_shape"],
                    "dtype": item["numeric_matrix_dtype"],
                },
                "independent_global_rows": tuple(range(882)),
                "csr_offsets": offsets,
                "csr_columns": columns,
                "coefficients": coefficients,
            },
        ),
        task037_extra_h2b=True,
    )
    assert len(tokens) == 882
    assert len(c0.canonical_tokens_sha256(tokens)) == 64
