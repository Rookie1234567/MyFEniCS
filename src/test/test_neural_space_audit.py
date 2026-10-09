"""Review V34 targeted fixed-space regression, with independent small solves."""

import numpy as np
import pytest
from scipy import linalg

from src.solvers.neural_space_audit import original_readout, field_oracle, relative
from src.io.neural_space_campaign import unlabelled_open_allowed, ROOT, load_space
from src.io.input_loader import InputError
from src.io.neural_space_campaign import field_policy, POLICY, require_oracle_policy
from src.solvers.feinn_gqr import project, GramColumns


def test_nonhermitian_original_readout():
    rng = np.random.default_rng(4213501)
    U = rng.normal(size=(12, 5)) + 1j * rng.normal(size=(12, 5))
    A = rng.normal(size=(12, 12)) + 1j * rng.normal(size=(12, 12))
    f = rng.normal(size=12) + 1j * rng.normal(size=12)
    Q, R = linalg.qr(A @ U, mode="economic")
    arrays, stats = original_readout(U, Q, R, f, lambda x: A @ x)
    expected = linalg.lstsq(A @ U, f, cond=1e-12)[0]
    assert relative(arrays["c"], U @ expected) < 1e-10
    assert stats["full_column_rank"] and stats["floating_numerical_qualified"]


@pytest.mark.parametrize("kind", ["full", "duplicate", "scales"])
def test_fixed_G_projection_whitened(kind):
    rng = np.random.default_rng(4213502)
    U = rng.normal(size=(17, 6)) + 1j * rng.normal(size=(17, 6))
    if kind == "duplicate":
        U[:, -1] = U[:, 0]
    if kind == "scales":
        U *= np.geomspace(1e-5, 1e5, 6)
    d = rng.normal(size=17) + 1j * rng.normal(size=17)
    W = rng.normal(size=(17, 17)) + 1j * rng.normal(size=(17, 17))
    G = W.conj().T @ W + np.eye(17)
    C = linalg.cholesky(G, lower=False)
    arrays, stats = field_oracle(U, d, G, deadline=float("inf"))
    scales = np.linalg.norm(C @ U, axis=0)
    z = linalg.lstsq(C @ U / scales, C @ d, cond=1e-12)[0]
    assert relative(arrays["c"], U @ (z / scales)) < 1e-10
    assert stats["small_M_orthogonality_F"] < 1e-9
    assert stats["full_column_space_retained"] == (kind != "duplicate")


def test_label_firewall(tmp_path):
    design = dict(files={}, unlabelled_bound_files=[])
    assert not unlabelled_open_allowed(
        ROOT / "benchmarks/artifacts/task42extra/reference_state.npz", design, tmp_path
    )
    assert not unlabelled_open_allowed(
        ROOT / "benchmarks/artifacts/task42extra/undisclosed.npz", design, tmp_path
    )
    assert unlabelled_open_allowed(tmp_path / "state.npz", design, tmp_path)


def test_new_schema_rejects_reference_path():
    with pytest.raises(InputError):
        load_space(
            ROOT / "x.dat",
            dict(
                schema_version=6,
                neural_wave=dict(
                    stage="v35_unlabelled_readout_audit",
                    design_sha256="x",
                    reference="teacher.npz",
                ),
            ),
            b"x",
        )


def test_truncated_minimum_not_full_space_lower_bound():
    U = np.eye(5, dtype=complex)[:, :3]
    U[:, -1] *= 1e-14
    Q, R = linalg.qr(U, mode="economic")
    _, stats = original_readout(U, Q, R, np.ones(5, complex), lambda x: x)
    assert stats["retained_rank"] == 2
    assert stats["conclusion"] == "RANK_OR_OPTIMALITY_UNRESOLVED"
    assert stats["truncated_minimum_is_full_space_upper_bound"]


def test_scoring_cannot_turn_oracle_into_solver():
    assert field_policy("x_ORACLE")["reference_used_for_training"] is True
    assert field_policy("x_ORACLE_PRODUCER")["official_candidate_results"] is False
    assert field_policy("x_UNLABELLED")["reference_used_for_training"] is False
    assert field_policy("x_UNLABELLED")["pde_only_solve"] is True


def test_eight_column_stream_pairs_original_projection():
    rng = np.random.default_rng(4213503)
    U = rng.normal(size=(39, 19)) + 1j * rng.normal(size=(39, 19))
    d = rng.normal(size=39) + 1j * rng.normal(size=39)
    x = rng.normal(size=(39, 39)) + 1j * rng.normal(size=(39, 39))
    G = x.conj().T @ x + np.eye(39)
    old, _ = project(U, d, d, GramColumns(G))
    new, _ = project(U, d, d, GramColumns(G), block_columns=8)
    assert relative(new["delta_columns"], old["delta_columns"]) < 1e-10


@pytest.mark.parametrize("replacement", ["false", 0, 1, None])
def test_oracle_consumer_strict_flag_types(replacement):
    value = dict(POLICY, official_candidate_results=replacement)
    with pytest.raises(InputError):
        require_oracle_policy(value)


def test_v35_admission_dispatch_and_shared_clock(monkeypatch, tmp_path):
    from src.runners import block_wave_admission as admission
    from src.runners import neural_wave_dependencies as deps
    from src.runners import neural_wave_campaign as campaign

    monkeypatch.setattr(
        admission, "fresh_admission", lambda *a, **kw: {"new_pool": True}
    )
    assert deps.fresh_admission(ROOT / "tmp/task42extra/v35/test", 2 * 2**30)[
        "new_pool"
    ]
    assert admission.wait_limit(ROOT / "tmp/task42extra/v35/test") == 900
    monkeypatch.setattr(campaign, "profile_paths", lambda spec: {"root": tmp_path})
    spec = dict(campaign_version=35, role="space_unlabelled")
    first, _ = campaign.stage_deadline(
        spec,
        dict(origin_monotonic=100, deadline_monotonic=3100),
        dict(deadline_monotonic=15000),
    )
    assert first == 3100
    spec["role"] = "space_oracle"
    next_deadline, _ = campaign.stage_deadline(
        spec,
        dict(origin_monotonic=3100, deadline_monotonic=10300),
        dict(deadline_monotonic=15000),
    )
    assert next_deadline == 7300


def test_actual_small_qualification_with_repaired_reader(tmp_path):
    from src.solvers.neural_space_qualification import qualify

    result = qualify(tmp_path, dict(source_sha="0" * 40, design_sha256="0" * 64))
    assert result["implementation_qualified"]
    assert result["actual_writer_seal_reopen"]


def test_full_rank_triangular_reader_preserves_fixed_rank_rule():
    rng = np.random.default_rng(4213505)
    Q, _ = linalg.qr(
        rng.normal(size=(25, 8)) + 1j * rng.normal(size=(25, 8)), mode="economic"
    )
    R = np.triu(rng.normal(size=(8, 8)) + 1j * rng.normal(size=(8, 8)))
    R[np.diag_indices(8)] = np.geomspace(1, 1e-6, 8)
    U = Q @ R
    _, stats = original_readout(
        U, Q, R, rng.normal(size=25) + 1j * rng.normal(size=25), lambda x: x
    )
    # Very correlated synthetic columns may still be truncated by 1e-12.
    assert stats["SVD_rcond"] == 1e-12
    if stats["full_column_rank"]:
        assert stats["amplitude_solver"] == "SVD_RANK_QUALIFIED_QR_BACK_SUBSTITUTION"
