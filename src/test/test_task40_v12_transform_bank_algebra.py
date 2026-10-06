from __future__ import annotations

import numpy as np

from src.solvers.task40_v10_p6_yorbit import YOrbitEntities
from src.solvers.y_orbit_transform_bank import RunLocalTransformBank, TransformKey
from src.runners.task40_v10_worker import _v12_memory_admission_bounds


def test_v12_memory_admission_keeps_total_rss_and_incremental_headroom_separate():
    admitted = _v12_memory_admission_bounds(
        live_rss_bytes=700,
        total_rss_cap_bytes=1000,
        incremental_headroom_bytes=300,
        delta_bytes=250,
        reserve_bytes=50,
    )
    assert admitted["total_rss_inequality_passed"] is True
    assert admitted["incremental_headroom_inequality_passed"] is True
    assert admitted["projected_process_tree_rss_bytes"] == 1000
    assert admitted["projected_incremental_capacity_bytes"] == 300

    rss_limited = _v12_memory_admission_bounds(
        live_rss_bytes=700,
        total_rss_cap_bytes=999,
        incremental_headroom_bytes=300,
        delta_bytes=250,
        reserve_bytes=50,
    )
    assert rss_limited["total_rss_inequality_passed"] is False
    assert rss_limited["incremental_headroom_inequality_passed"] is True

    headroom_limited = _v12_memory_admission_bounds(
        live_rss_bytes=700,
        total_rss_cap_bytes=1000,
        incremental_headroom_bytes=299,
        delta_bytes=250,
        reserve_bytes=50,
    )
    assert headroom_limited["total_rss_inequality_passed"] is True
    assert headroom_limited["incremental_headroom_inequality_passed"] is False


def test_nonunitary_complex_template_keeps_all_six_transform_directions_distinct():
    native_to_canonical = np.asarray(
        [[2.0 + 1.0j, 0.5 - 0.3j], [-0.2 + 0.7j, 1.4 - 0.2j]],
        dtype=np.complex128,
    )
    bank = RunLocalTransformBank()
    basis = bank.bind_basis({"fixture": "nonunitary-complex", "actual_D4_states": []})
    base = (3, 0)
    record_key = (0, base)
    key = TransformKey(
        basis=basis,
        dimension=3,
        shape=(2, 2),
        channels=(0, 1),
        state=("cell_info", 0),
        semantics=("nonunitary-complex-algebra-fixture.v1",),
    )
    matrix = bank.matrix(key, lambda: native_to_canonical.copy())
    entities = YOrbitEntities(
        independent=np.arange(2, dtype=np.int64),
        full_rows=2,
        ny=1,
        width=2,
        bases=(base,),
        records={record_key: (np.arange(2, dtype=np.int64), matrix)},
        slots={base: (0, 2)},
        dimension_counts={3: 2},
        y_widths=np.asarray([2], dtype=np.float64),
        _transform_bank=bank,
        _template_keys={record_key: key},
    )
    inverse = bank.inverse(matrix)
    assert not np.allclose(inverse, matrix.T)
    assert not np.allclose(matrix.T, matrix.conj().T)

    rng = np.random.default_rng(4012)
    native = rng.normal(size=(2, 3)) + 1j * rng.normal(size=(2, 3))
    canonical = rng.normal(size=(2, 3)) + 1j * rng.normal(size=(2, 3))
    expected = {
        "primal_to_canonical": inverse @ native,
        "primal_from_canonical": matrix @ canonical,
        "dual_to_canonical": matrix.conj().T @ native,
        "dual_from_canonical": inverse.conj().T @ canonical,
        "functional_to_canonical": matrix.T @ native,
        "functional_from_canonical": inverse.T @ canonical,
    }
    for direction, wanted in expected.items():
        source = canonical if direction.endswith("from_canonical") else native
        np.testing.assert_allclose(
            entities.transform(source, direction=direction), wanted, rtol=2e-14, atol=2e-14
        )

    primal = entities.transform(canonical, direction="primal_from_canonical")
    dual = entities.transform(native, direction="dual_to_canonical")
    functional = entities.transform(native, direction="functional_to_canonical")
    np.testing.assert_allclose(np.vdot(native, primal), np.vdot(dual, canonical),
                               rtol=2e-14, atol=2e-14)
    np.testing.assert_allclose(np.dot(native.ravel(), primal.ravel()),
                               np.dot(functional.ravel(), canonical.ravel()),
                               rtol=2e-14, atol=2e-14)
    assert entities._inverses[record_key] is inverse
    assert bank.receipt(stage="nonunitary_complex_algebra")["inverse_builds"] == 1

    entities._transform_bank = None
    entities._template_keys.clear()
    entities._inverses.clear()
    bank.close()
