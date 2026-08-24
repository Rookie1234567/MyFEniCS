"""Focused pure-algebra and immutable-packet tests for Task040 V3-1."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from mpi4py import MPI

from benchmarks.check_task040_v3_coupled import (
    _load_augmented_middle_matrix,
    recompute_v3_1_augmented_packet,
    recompute_v3_1_packet,
)
from src.solvers.hybrid_interface_coupled import (
    assemble_coupled_interface_matrices,
    matrix_diagnostics,
    solve_coupled_interface,
)


def _block(rows: int, columns: int, seed: int, shift: float = 0.0) -> np.ndarray:
    row = np.arange(rows, dtype=float)[:, None]
    column = np.arange(columns, dtype=float)[None, :]
    values = (
        0.07 * (seed + 1.0) * (row + 1.0)
        + 0.03 * (column + 1.0)
        + 0.02j * (row + 2.0 * column + seed + 1.0)
    ).astype(np.complex128)
    if rows == columns:
        values += (shift + 0.11j * (seed + 1.0)) * np.eye(rows, dtype=np.complex128)
    return values


def _schur(
    boundary: np.ndarray,
    boundary_to_interior: np.ndarray,
    interior: np.ndarray,
    interior_to_boundary: np.ndarray,
) -> np.ndarray:
    return boundary - boundary_to_interior @ np.linalg.solve(
        interior, interior_to_boundary
    )


def _independent_three_subdomain_fixture() -> tuple[
    dict[str, np.ndarray],
    dict[str, np.ndarray],
    dict[str, np.ndarray],
    np.ndarray,
    np.ndarray,
    np.ndarray,
    np.ndarray,
]:
    lower = upper = 2
    interior = 2
    e0 = _block(lower, lower, 1, 3.0)
    c0 = _block(lower, interior, 2)
    b0 = _block(interior, interior, 3, 4.0)
    d0 = _block(interior, lower, 4)

    e1 = _block(lower + upper, lower + upper, 5, 3.5)
    c1 = _block(lower + upper, interior, 6)
    b1 = _block(interior, interior, 7, 4.5)
    d1 = _block(interior, lower + upper, 8)

    e2 = _block(upper, upper, 9, 3.25)
    c2 = _block(upper, interior, 10)
    b2 = _block(interior, interior, 11, 4.25)
    d2 = _block(interior, upper, 12)

    s0 = _schur(e0, c0, b0, d0)
    s1 = _schur(e1, c1, b1, d1)
    s2 = _schur(e2, c2, b2, d2)

    zero_lower = np.zeros((upper, interior), dtype=np.complex128)
    zero_upper = np.zeros((lower, interior), dtype=np.complex128)
    c2_joint = np.vstack((zero_lower, c2))
    d2_joint = np.hstack((np.zeros((interior, lower), dtype=np.complex128), d2))
    c_joint = np.hstack((np.vstack((c0, zero_upper)), c1, c2_joint))
    d_joint = np.vstack(
        (
            np.hstack((d0, np.zeros((interior, upper), dtype=np.complex128))),
            d1,
            d2_joint,
        )
    )
    boundary_block = e1 + np.block(
        [
            [e0, np.zeros((lower, upper), dtype=np.complex128)],
            [np.zeros((upper, lower), dtype=np.complex128), e2],
        ]
    )
    interior_block = np.block(
        [
            [
                b0,
                np.zeros((interior, interior), dtype=np.complex128),
                np.zeros((interior, interior), dtype=np.complex128),
            ],
            [
                np.zeros((interior, interior), dtype=np.complex128),
                b1,
                np.zeros((interior, interior), dtype=np.complex128),
            ],
            [
                np.zeros((interior, interior), dtype=np.complex128),
                np.zeros((interior, interior), dtype=np.complex128),
                b2,
            ],
        ]
    )
    full_schur = boundary_block - c_joint @ np.linalg.solve(interior_block, d_joint)
    groups = [
        {
            "gram": _block(lower, lower, 13, 2.0),
            "projected_scalar": s0 + 0.2 * np.eye(lower, dtype=np.complex128),
            "projected_exact": s0,
        },
        {
            "gram": _block(lower + upper, lower + upper, 14, 2.5),
            "projected_scalar": s1 + 0.25 * np.eye(lower + upper, dtype=np.complex128),
            "projected_exact": s1,
        },
        {
            "gram": _block(upper, upper, 15, 2.25),
            "projected_scalar": s2 + 0.3 * np.eye(upper, dtype=np.complex128),
            "projected_exact": s2,
        },
    ]
    return groups[0], groups[1], groups[2], full_schur, interior_block, c_joint, d_joint


def test_coupled_joint_matches_independent_full_interior_elimination() -> None:
    group0, group1, group2, authority, interior, c_joint, d_joint = (
        _independent_three_subdomain_fixture()
    )
    assembled = assemble_coupled_interface_matrices(
        (group0, group1, group2), expected_span_sizes=(2, 4, 2)
    )
    joint = assembled["joint_projected_exact"]
    np.testing.assert_allclose(joint, authority, rtol=0.0, atol=1.0e-12)
    assert "joint_gram" not in assembled
    assert assembled["diagnostics"]["joint_exact_blocks"]["LU"]["condition"] is None
    assert assembled["diagnostics"]["joint_exact_blocks"]["UL"]["condition"] is None
    assert assembled["diagnostics"]["joint_exact_blocks"]["LL"]["shape"] == [2, 2]
    assert assembled["diagnostics"]["joint_exact_blocks"]["LU"]["shape"] == [2, 2]
    assert assembled["diagnostics"]["joint_exact_blocks"]["UL"]["shape"] == [2, 2]
    assert assembled["diagnostics"]["joint_exact_blocks"]["UU"]["shape"] == [2, 2]
    assert assembled["diagnostics"]["joint_exact_blocks"]["LU"]["frobenius_norm"] > 0.0
    assert assembled["diagnostics"]["joint_exact_blocks"]["UL"]["frobenius_norm"] > 0.0

    rhs_gamma = _block(4, 1, 16).ravel()
    rhs_interior = _block(6, 1, 17).ravel()
    rhs_schur = rhs_gamma - c_joint @ np.linalg.solve(interior, rhs_interior)
    gamma_solution = solve_coupled_interface(joint, rhs_schur)
    matrix_relative_error = np.linalg.norm(joint - authority) / max(
        np.linalg.norm(authority), 1.0e-30
    )
    action_reference = authority @ gamma_solution
    action_relative_error = np.linalg.norm(
        joint @ gamma_solution - action_reference
    ) / max(np.linalg.norm(action_reference), 1.0e-30)
    interior_solution = np.linalg.solve(
        interior, rhs_interior - d_joint @ gamma_solution
    )
    full_boundary = authority + c_joint @ np.linalg.solve(interior, d_joint)
    full_matrix = np.block([[full_boundary, c_joint], [d_joint, interior]])
    full_solution = np.concatenate((gamma_solution, interior_solution))
    full_rhs = np.concatenate((rhs_gamma, rhs_interior))
    independent_full_solution = np.linalg.solve(full_matrix, full_rhs)
    solution_relative_error = np.linalg.norm(
        full_solution - independent_full_solution
    ) / max(np.linalg.norm(independent_full_solution), 1.0e-30)
    full_relative_residual = np.linalg.norm(
        full_matrix @ full_solution - full_rhs
    ) / max(np.linalg.norm(full_rhs), 1.0e-30)
    assert matrix_relative_error <= 1.0e-12
    assert action_relative_error <= 1.0e-12
    assert solution_relative_error <= 1.0e-12
    assert full_relative_residual <= 1.0e-12

    omitted = joint.copy()
    omitted[:2, 2:] = 0.0
    omitted[2:, :2] = 0.0
    assert np.linalg.norm(omitted - authority) > 1.0e-8
    assert np.linalg.norm(omitted @ gamma_solution - rhs_schur) > 1.0e-8


def test_coupled_diagnostics_retain_rectangular_cross_blocks() -> None:
    value = _block(2, 3, 18)
    diagnostics = matrix_diagnostics(value, square=False)
    assert diagnostics["shape"] == [2, 3]
    assert diagnostics["condition"] is None
    with pytest.raises(ValueError, match="square"):
        matrix_diagnostics(value)


def test_coupled_small_hash_consensus_without_numeric_allgather() -> None:
    group0, group1, group2, _authority, _interior, _c_joint, _d_joint = (
        _independent_three_subdomain_fixture()
    )
    assembled = assemble_coupled_interface_matrices(
        (group0, group1, group2), expected_span_sizes=(2, 4, 2)
    )
    local_hash = assembled["diagnostics"]["joint"]["projected_exact"]["sha256"]
    hashes = MPI.COMM_WORLD.allgather(local_hash)
    assert len(set(hashes)) == 1


def test_immutable_v2_packet_lacks_v3_local_middle_schur() -> None:
    comm = MPI.COMM_WORLD
    if comm.size != 1:
        pytest.skip("the immutable packet audit is run once in serial")
    root = Path(__file__).resolve().parents[2]
    packet_root = (
        root
        / "results/task040_v2_interface_packet_producer_mpi8_942c4388/worker/interface_packet"
    )
    watchdog = (
        root
        / "results/task040_v2_interface_packet_producer_mpi8_942c4388/watchdog_summary.json"
    )
    if not packet_root.is_dir() or not watchdog.is_file():
        pytest.skip("immutable V2 packet evidence is unavailable")
    result = recompute_v3_1_packet(packet_root, watchdog_summary_path=watchdog)
    assert result["packet_sufficient"] is False
    assert result["classification"] == "COUPLED_PACKET_INFORMATION_INCOMPLETE"
    assert result["checks"] == {
        "manifest_hash": True,
        "packet_authority": True,
        "group_order": True,
        "span_sizes": True,
        "group_gram_diagnostics": True,
        "joint_scalar_diagnostics": True,
        "joint_exact_structural_diagnostic": True,
        "joint_exact_blocks": True,
        "ordering_identity": True,
        "report_decomposition": True,
        "local_middle_schur_evidence": False,
    }
    assert result["v2_packet_checks"]["factor_lifecycle"] is True
    assert result["v2_packet_checks"]["watchdog"] is True
    assert result["checks"]["joint_exact_structural_diagnostic"] is True
    assert set(result["joint_exact_blocks"]) == {"LL", "LU", "UL", "UU"}
    assert result["span_sizes"] == [296, 776, 480]
    assert result["group_order"] == ["group0", "group1", "group2"]
    assert result["joint_checks"]["gram_is_group_local"] is True
    assert result["joint_checks"]["joint_gram_defined"] is False
    decomposition = result["failure_decomposition"]
    assert decomposition["physical"]["count"] == 15
    assert decomposition["modal_combination"]["count"] == 4
    assert decomposition["complement"]["count"] == 4
    assert decomposition["middle_lower_to_upper"]["count"] == 4
    assert decomposition["middle_upper_to_lower"]["count"] == 4
    assert decomposition["physical"]["scalar_exact_relative_max"] > 0.0
    assert (
        decomposition["modal_combination"]["in_span_projection_relative_max"] < 1.0e-6
    )
    assert decomposition["complement"]["complement_orthogonality_max"] < 1.0e-8
    assert decomposition["middle_lower_to_upper"]["cross_energy_ratio_max"] >= 0.0
    assert decomposition["middle_upper_to_lower"]["cross_energy_ratio_max"] >= 0.0
    semantics = result["semantic_mapping"]
    assert semantics["projected_exact_semantics"] == "directed_neighbor_transmission"
    assert semantics["incoming_neighbor_map_bound"] is True
    assert semantics["middle_cross_sampled_response_present"] is True
    assert semantics["missing_local_middle_projected_exact"] is True
    assert semantics["missing_middle_cross_blocks"] is True
    assert semantics["missing_local_middle_blocks"] == ["S1_LU", "S1_UL"]
    assert semantics["z_gamma_in_packet"] is False
    assert semantics["y_reconstructible_from_v_g"] is True
    assert semantics["z_reconstructible_from_u"] is False


def test_augmented_packet_recomputes_true_middle_joint() -> None:
    comm = MPI.COMM_WORLD
    if comm.size != 1:
        pytest.skip("the augmented packet audit is run once in serial")
    root = Path(__file__).resolve().parents[2]
    packet_root = (
        root
        / "results/task040_v3_1_middle_schur_producer_mpi8_fa1720d8/worker/interface_packet"
    )
    watchdog = (
        root
        / "results/task040_v3_1_middle_schur_producer_mpi8_fa1720d8/watchdog_summary.json"
    )
    if not packet_root.is_dir() or not watchdog.is_file():
        pytest.skip("augmented V3-1 packet evidence is unavailable")
    result = recompute_v3_1_augmented_packet(
        packet_root, watchdog_summary_path=watchdog
    )
    assert result["packet_sufficient"] is True
    assert result["classification"] == "COUPLED_INTERFACE_ALGEBRA_EVIDENCE_VALID"
    assert all(result["checks"].values())
    assert result["additional_middle_metadata"]["apply_count"] == 776
    assert result["additional_middle_diagnostics"]["rank"] == 776
    assert result["joint_diagnostics"]["rank"] == 776
    assert result["joint_diagnostics"]["condition"] <= 1.0e12
    assert result["identity_relative_errors"]["lower"] <= 1.0e-12
    assert result["identity_relative_errors"]["upper"] <= 1.0e-12
    assert set(result["joint_exact_blocks"]) == {"LL", "LU", "UL", "UU"}
    assert result["joint_exact_blocks"]["LL"]["shape"] == [296, 296]
    assert result["joint_exact_blocks"]["LU"]["shape"] == [296, 480]
    assert result["joint_exact_blocks"]["UL"]["shape"] == [480, 296]
    assert result["joint_exact_blocks"]["UU"]["shape"] == [480, 480]
    assert result["joint_exact_blocks"]["LU"]["frobenius_norm"] > 0.0
    assert result["joint_exact_blocks"]["UL"]["frobenius_norm"] > 0.0
    assert result["checks"]["manifest_hash"] is True
    assert result["checks"]["run_summary_hash"] is True
    assert result["checks"]["watchdog_hash"] is True
    assert result["v2_packet_checks"]["factor_lifecycle"] is True
    assert result["v2_packet_checks"]["watchdog"] is True
    assert json.dumps(result, sort_keys=True)
    assert all(
        np.isfinite(block["frobenius_norm"])
        for block in result["joint_exact_blocks"].values()
    )


def test_augmented_middle_metadata_tamper_fails_closed() -> None:
    comm = MPI.COMM_WORLD
    if comm.size != 1:
        pytest.skip("the augmented packet audit is run once in serial")
    root = Path(__file__).resolve().parents[2]
    packet_root = (
        root
        / "results/task040_v3_1_middle_schur_producer_mpi8_fa1720d8/worker/interface_packet"
    )
    manifest_path = packet_root / "manifest.json"
    if not manifest_path.is_file():
        pytest.skip("augmented V3-1 packet evidence is unavailable")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["diagnostics"]["additional_projected_matrices"][
        "projected_middle_group_schur"
    ]["schema"] = "tampered"
    with pytest.raises(ValueError, match="schema"):
        _load_augmented_middle_matrix(packet_root, manifest)
