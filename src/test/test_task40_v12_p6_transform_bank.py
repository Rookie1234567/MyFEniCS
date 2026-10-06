"""Real p6 DOLFINx matrix witnesses for the Task40 V12 transform bank.

The fixture uses a synthetic MPC slave-row set. It qualifies the actual p6
entity matrices and algebraic coordinate identities, not full MPC coefficient
or physical-port recovery behavior; those remain for the frozen B0 run.
"""
from __future__ import annotations

from types import SimpleNamespace

import basix
from dolfinx import fem, mesh
from mpi4py import MPI
import numpy as np

from src.solvers.task40_v10_p6_yorbit import (
    TwoCellNativeTransport,
    collect_y_orbit_entities,
)
from src.solvers.y_orbit_transform_bank import RunLocalTransformBank, _backing


def _real_p6_space(ny: int):
    domain = mesh.create_box(
        MPI.COMM_SELF,
        np.asarray([[0.0, 0.0, 0.0], [1.0, float(ny), 1.0]]),
        [1, ny, 1],
        cell_type=mesh.CellType.hexahedron,
    )
    element = basix.ufl.element("N1curl", "hexahedron", 6)
    space = fem.functionspace(domain, element)
    basix_element = space.element.basix_element
    assert basix_element.degree == 6
    assert str(basix_element.cell_type).lower().endswith("hexahedron")
    assert str(basix_element.family.name).lower() == "n1e"
    assert space.element.space_dimension == basix_element.dim == 882
    assert len(basix_element.entity_dofs[3][0]) == 450

    fdim = domain.topology.dim - 1
    facets = mesh.locate_entities_boundary(
        domain, fdim, lambda x: np.isclose(x[1], float(ny))
    )
    slaves = fem.locate_dofs_topological(space, fdim, facets)
    floquet = SimpleNamespace(mpc=SimpleNamespace(slaves=np.asarray(slaves, dtype=np.int32)))
    cfg = SimpleNamespace(nedelec_degree=6)
    axes = {
        "x": (0.0, 1.0),
        "y": tuple(float(value) for value in range(ny + 1)),
        "z": (0.0, 1.0),
    }
    return space, floquet, cfg, axes


def _expected_transform(entities, values: np.ndarray, direction: str) -> np.ndarray:
    result = np.empty_like(values)
    inverse_directions = {
        "primal_to_canonical",
        "dual_from_canonical",
        "functional_from_canonical",
    }
    for orbit in range(entities.ny):
        for base in entities.bases:
            rows, stored = entities.records[(orbit, base)]
            first, size = entities.slots[base]
            canonical = slice(orbit * entities.width + first, orbit * entities.width + first + size)
            matrix = np.linalg.inv(stored) if direction in inverse_directions else stored
            if direction == "primal_to_canonical":
                result[canonical] = matrix @ values[rows]
            elif direction == "primal_from_canonical":
                result[rows] = matrix @ values[canonical]
            elif direction == "dual_to_canonical":
                result[canonical] = matrix.conj().T @ values[rows]
            elif direction == "dual_from_canonical":
                result[rows] = matrix.conj().T @ values[canonical]
            elif direction == "functional_to_canonical":
                result[canonical] = matrix.T @ values[rows]
            else:
                result[rows] = matrix.T @ values[canonical]
    return result


def _compare_old_full_builder(space_data, shared):
    space, floquet, cfg, axes = space_data
    legacy = collect_y_orbit_entities(space, floquet, cfg, axes)
    np.testing.assert_array_equal(shared.independent, legacy.independent)
    np.testing.assert_array_equal(shared.y_widths, legacy.y_widths)
    assert shared.full_rows == legacy.full_rows
    assert shared.ny == legacy.ny
    assert shared.width == legacy.width
    assert shared.dimension_counts == legacy.dimension_counts
    assert set(shared.records) == set(legacy.records)
    cell_records = 0
    for record_key, (shared_rows, shared_matrix) in shared.records.items():
        legacy_rows, legacy_matrix = legacy.records[record_key]
        np.testing.assert_array_equal(shared_rows, legacy_rows)
        if record_key[1][0] == 3:
            cell_records += 1
            # This is a fresh, separate call through the original Tt_apply builder,
            # never a second lookup through the bank's cache-hit path.
            np.testing.assert_array_equal(shared_matrix, legacy_matrix)
            assert shared_matrix.dtype == np.complex128
            assert not shared_matrix.flags.writeable
            assert isinstance(_backing(shared_matrix)[0], bytes)
        else:
            np.testing.assert_array_equal(shared_matrix, legacy_matrix)
    return cell_records


def test_real_p6_cell_transform_is_shared_across_global_and_both_local_spaces():
    allocation_requests = []
    bank = RunLocalTransformBank(
        allocation_gate=lambda label, facts: allocation_requests.append((label, dict(facts)))
    )
    full_data = _real_p6_space(4)
    local0_data = _real_p6_space(2)
    local1_data = _real_p6_space(2)
    banked = [
        collect_y_orbit_entities(*full_data, transform_bank=bank),
        collect_y_orbit_entities(*local0_data, transform_bank=bank),
        collect_y_orbit_entities(*local1_data, transform_bank=bank),
    ]
    pending_legacy_inverses = [
        entities.future_legacy_inverse_reserve() for entities in banked
    ]
    assert all(row["future_legacy_inverse_count"] > 0 for row in pending_legacy_inverses)
    assert all(row["future_legacy_inverse_payload_bytes"] > 0 for row in pending_legacy_inverses)
    assert all(
        row["future_legacy_inverse_count_by_dimension"].get("3", 0) == 0
        for row in pending_legacy_inverses
    )
    bank.seal()

    legacy_cell_builds = 0
    for data, shared in zip((full_data, local0_data, local1_data), banked, strict=True):
        legacy_cell_builds += _compare_old_full_builder(data, shared)

    cell_arrays_by_key = {}
    logical_cell_matrix_bytes = 0
    for entities in banked:
        for record_key, (_rows, matrix) in entities.records.items():
            if record_key[1][0] != 3:
                continue
            logical_cell_matrix_bytes += matrix.nbytes
            key = entities.transform_key(record_key)
            previous = cell_arrays_by_key.setdefault(key, matrix)
            assert previous is matrix
            witness = entities.actual_state_witness(record_key)
            assert witness["dimension"] == 3
            assert witness["cell_info"] == key.state[1]

    receipt_arrays = {}
    for index, entities in enumerate(banked):
        receipt_arrays.update(entities.named_backing_arrays(f"space{index}"))
    receipt = bank.receipt(receipt_arrays, stage="actual_p6_small_space_qualification")
    reserve = bank.future_inverse_reserve()
    unique_matrix_ids = {id(matrix) for matrix in cell_arrays_by_key.values()}
    unique_matrix_count = len(unique_matrix_ids)
    assert receipt["basis_count"] == 1
    assert receipt["migration_provenance"]["source_commit"] == (
        "15713d3e09b63f65511c7b7f61fa043fdb23dca5"
    )
    assert "no p6 qualification inherited" in receipt["migration_provenance"][
        "original_qualification_scope"
    ]
    assert "450 cell-interior channels" in receipt["migration_provenance"]["p6_adaptation"]
    assert receipt["actual_state_count"] == len(cell_arrays_by_key)
    assert receipt["matrix_template_count"] == unique_matrix_count
    assert receipt["matrix_requests"] == legacy_cell_builds
    assert receipt["matrix_builder_calls"] == len(cell_arrays_by_key)
    assert receipt["matrix_cache_hits"] == legacy_cell_builds - len(cell_arrays_by_key)
    assert receipt["lazy_inverse_count"] == 0
    assert logical_cell_matrix_bytes > reserve["unique_matrix_template_bytes"]
    assert reserve["unique_matrix_template_bytes"] == unique_matrix_count * 450 * 450 * 16
    assert reserve["future_unique_inverse_payload_bytes"] == reserve["unique_matrix_template_bytes"]
    assert receipt["sharing_scope"] == "p6 internal cell block only; edge/face keep legacy path"
    assert len(allocation_requests) == len(cell_arrays_by_key)
    assert all(label == "task40_v12_shared_transform_matrix" for label, _ in allocation_requests)
    assert all(facts["additional_payload_bytes"] == 450 * 450 * 16 for _, facts in allocation_requests)

    directions = (
        "primal_to_canonical",
        "primal_from_canonical",
        "dual_to_canonical",
        "dual_from_canonical",
        "functional_to_canonical",
        "functional_from_canonical",
    )
    rng = np.random.default_rng(20261006)
    full = banked[0]
    native = rng.normal(size=(len(full.independent), 3)) + 1j * rng.normal(
        size=(len(full.independent), 3)
    )
    canonical = rng.normal(size=(len(full.independent), 3)) + 1j * rng.normal(
        size=(len(full.independent), 3)
    )
    for direction in directions:
        source = canonical if direction.endswith("from_canonical") else native
        expected = _expected_transform(full, source, direction)
        actual = full.transform(source, direction=direction)
        np.testing.assert_allclose(actual, expected, rtol=2e-13, atol=2e-13)
    primal = full.transform(canonical, direction="primal_from_canonical")
    dual = full.transform(native, direction="dual_to_canonical")
    np.testing.assert_allclose(np.vdot(native, primal), np.vdot(dual, canonical), rtol=2e-12, atol=2e-12)
    functional = full.transform(native, direction="functional_to_canonical")
    np.testing.assert_allclose(np.dot(native.ravel(), primal.ravel()),
                               np.dot(functional.ravel(), canonical.ravel()),
                               rtol=2e-12, atol=2e-12)

    inverse_records = [
        entities._inverses[key]
        for entities in banked
        for key, (_rows, _matrix) in entities.records.items()
        if key[1][0] == 3 and key in entities._inverses
    ]
    assert inverse_records
    assert all(value is inverse_records[0] for value in inverse_records)
    assert not inverse_records[0].flags.writeable
    assert isinstance(_backing(inverse_records[0])[0], bytes)
    post_inverse = bank.receipt(receipt_arrays, stage="actual_p6_directions_and_adjoint")
    assert post_inverse["inverse_builds"] == unique_matrix_count
    assert post_inverse["lazy_inverse_count"] == unique_matrix_count

    ky = 0.125
    phase = np.exp(1j * ky * 4.0)
    cfg = SimpleNamespace(ky=ky + 0j, period_y=4.0, floquet_phase_y=phase)
    rhs = rng.normal(size=len(full.independent)) + 1j * rng.normal(size=len(full.independent))
    local_primal = rng.normal(size=len(banked[1].independent)) + 1j * rng.normal(
        size=len(banked[1].independent)
    )
    assert np.linalg.norm(rhs) > 0.0 and np.linalg.norm(local_primal) > 0.0
    for twist in (0, 1):
        eta = np.exp(1j * (ky * 4.0 + 2.0 * np.pi * twist) / 4.0)
        transport = TwoCellNativeTransport(
            full, banked[twist + 1], twist_index=twist, eta=eta, cfg=cfg
        )
        folded = transport.fold_dual(rhs)
        lifted = transport.lift_primal(local_primal)
        np.testing.assert_allclose(np.vdot(rhs, lifted), np.vdot(folded, local_primal),
                                   rtol=2e-12, atol=2e-12)
        extracted = transport.extract_primal(rhs)
        local_dual = rng.normal(size=len(extracted)) + 1j * rng.normal(size=len(extracted))
        np.testing.assert_allclose(
            np.vdot(local_dual, extracted),
            np.vdot(transport.lift_dual(local_dual), rhs),
            rtol=2e-12,
            atol=2e-12,
        )

    assert bank._matrix_requests == legacy_cell_builds
    assert bank._matrix_builder_calls == len(cell_arrays_by_key)
    for entities in banked:
        entities._transform_bank = None
        entities._template_keys.clear()
        entities._actual_state_witnesses.clear()
    del banked
    bank.close()
    assert bank._closed
