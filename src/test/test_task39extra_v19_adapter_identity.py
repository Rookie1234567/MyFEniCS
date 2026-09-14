"""Bounded metadata checks on the actual small action component."""

import numpy as np

from src.runners.physical_retained_outer_adapter import _array_identity, _cache_identity
from src.test.test_task39extra_v19_p6_cell_condensed_action import _problem


def test_empty_port_arrays_have_a_valid_content_hash():
    result = _array_identity(np.empty((450, 0), dtype=np.complex128))
    assert result["shape"] == [450, 0]
    assert result["sha256"] == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


def test_tiny_nonzero_physical_rhs_keeps_its_true_relative_residual():
    system, block, action = _problem()
    volume = np.block([[block["Vii"], block["Vit"]], [block["Vti"], block["Vtt"]]])
    B, D = np.vstack([block["Bi"], block["Bt"]]), np.hstack([block["Di"], block["Dt"]])
    native = volume + B @ np.linalg.solve(action.H_p, D)
    rhs = 1e-20 * np.array([1, 0.7j, -0.3, 0.1 + 0.6j])
    try:
        facts = action.evaluate_native_residual(np.zeros(action.reduced_size), rhs,
                                                lambda x: native @ x)
        measured = np.linalg.norm(facts["native_residual"]) / np.linalg.norm(rhs)
        assert measured > 0.01
        np.testing.assert_allclose(facts["native_residual_relative"], measured, rtol=1e-14)
    finally:
        action.destroy()


def test_actual_cache_identity_detects_content_changes_without_payload_growth():
    system, _block, action = _problem()
    # The small algebra fixture omits these optional production cache families.
    for name in ("interior_rhs_projection_by_class", "interior_solution_embedding_by_class",
                 "interior_residual_projection_by_class"):
        setattr(system, name, {})
    try:
        first = _cache_identity(action)
        again = _cache_identity(action)
        assert first == again
        assert first["unique_numpy_bytes"] > 0
        action._H_p[0, 0] += 0.125
        changed = _cache_identity(action)
        assert first["array_content_sha256"] != changed["array_content_sha256"]
        assert first["unique_numpy_bytes"] == changed["unique_numpy_bytes"]
    finally:
        action.destroy()


def test_adapter_retained_solve_checkpoint_restore_and_checker_roundtrip(tmp_path):
    from types import SimpleNamespace
    from petsc4py import PETSc
    from src.runners.physical_retained_outer_adapter import RetainedOuterAdapter
    from src.solvers.p6_cell_condensed_action import P6RetainedBALHBridge
    from src.test.test_physical_schur_v14_q4_mock import _Runtime
    from benchmarks.check_dual_cell_condensed_v19 import load_arrays, residual_facts
    import json

    system, block, action = _problem()
    for name in ("interior_rhs_projection_by_class", "interior_solution_embedding_by_class",
                 "interior_residual_projection_by_class"):
        setattr(system, name, {})
    volume = np.block([[block["Vii"], block["Vit"]], [block["Vti"], block["Vtt"]]])
    B, D = np.vstack([block["Bi"], block["Bt"]]), np.hstack([block["Di"], block["Dt"]])
    native = volume + B @ np.linalg.solve(action.H_p, D)
    runtime = _Runtime(tmp_path)
    runtime.release_inventory = lambda _label: None
    rhs = PETSc.Vec().createSeq(4, comm=PETSc.COMM_SELF)
    rhs.array[:] = [1, 0.7j, -0.3, 0.1 + 0.6j]
    counts = {"bal_h": 0, "p4_mat_solve": 0, "h6": 0}

    def exact_pc(source):
        result = source.duplicate()
        result.array[:] = np.linalg.solve(native, source.array_r)
        counts["bal_h"] += 1
        counts["p4_mat_solve"] += 2
        counts["h6"] += 1
        return result

    common = {"fine": {"physical_action": SimpleNamespace(
        apply=lambda source, target: target.array.__setitem__(slice(None), native @ source.array_r))}}
    adapter = RetainedOuterAdapter(runtime, common, {}, rhs, exact_pc,
                                   p4_identity_sha256="p" * 64, pc_counts=lambda: dict(counts))
    adapter.action, adapter.condensed = action, system
    adapter.cache = {k: v for k, v in _cache_identity(action).items() if k != "arrays"}
    adapter.full_source, adapter.full_target = rhs.duplicate(), rhs.duplicate()
    adapter.rhs = action.create_reduced_rhs_vector()
    adapter.rhs.array[:] = action.reduce_rhs(rhs, rhs_is_mpc_dual=True)
    adapter.bridge = P6RetainedBALHBridge(action, adapter._bal_h_array)
    saved = []

    def checkpoint(iteration, full, residual):
        assert (tmp_path / f"x2_y_{iteration:04d}.json").exists()
        saved.append(iteration)
        if residual <= 1e-6:
            np.testing.assert_allclose(native @ full.array_r, rhs.array_r, rtol=1e-11, atol=1e-11)

    result = None
    try:
        result = adapter.solve(checkpoint=checkpoint, append=lambda *_: None,
                               seconds=lambda: 1.0, resource_sample=lambda: None,
                               stop_requested=lambda: False)
        assert result["status"] == "TRUE_RESIDUAL_PASS"
        assert result["iterations"] == 1
        assert saved == [0, 1]
        packet = json.loads((tmp_path / "x2_retained_final.json").read_text())
        independent = residual_facts(load_arrays(packet, "residuals", tmp_path), packet["facts"], terminal=True)
        assert independent["passed"], independent
        assert result["actual_pc_counts_including_one_setup_call"] == {"bal_h": 1, "p4_mat_solve": 2, "h6": 1}
    finally:
        if result is not None:
            result["final_solution"].destroy()
        adapter.destroy()
        rhs.destroy()
