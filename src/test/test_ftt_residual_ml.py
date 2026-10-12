"""Real complex FTT zero start, independent point sum and complete-state rejection."""

# ruff: noqa: E402 -- skip in the pure environment before importing ML modules.

from copy import deepcopy
import numpy as np
import pytest

torch = pytest.importorskip("torch")
from src.solvers.ftt_bloch_field import BlochFTTField
from src.solvers.ftt_conditional_core import DirectionField
from src.solvers.ftt_residual_branch import (
    frozen_base_and_zero_correction,
    independent_sum_field,
    ResidualTrainingAction,
    ResidualBranchContext,
)
from src.test.test_ftt_residual_branch import MatrixAction


def fields():
    phase = dict(
        coordinate_unit="physical_nm",
        sign=1,
        unfolded_incident_wavevector=True,
        wavevector_nm_inverse=[1.2, 0.4, 0],
        origin_nm=[0, 0, 0],
        mode_manifest_sha256="12" * 32,
    )
    base = BlochFTTField([[-1, 1]] * 3, "fttnn", phase, hidden_width=32)
    base.nonzero_qualification_state()
    return base, frozen_base_and_zero_correction(base)


def test_deep_copy_frozen_base_zero_correction_and_nonzero_z_direction():
    base, delta = fields()
    points = torch.tensor([[0.2, 0.3, 0.1], [-0.4, 0.1, -0.3]], dtype=torch.float64)
    assert torch.count_nonzero(delta(points)) == 0
    assert not any(p.requires_grad for p in base.parameters())
    assert all(p.dtype == torch.float64 for p in delta.parameters())
    for name, value in delta.state_dict().items():
        assert value.data_ptr() != base.state_dict()[name].data_ptr()
        if not name.startswith("cores.2.4."):
            assert value.equal(base.state_dict()[name])
    direction = np.ones((33, 3, 8, 1), dtype=np.complex128) * 1j
    assert torch.linalg.vector_norm(DirectionField(delta, 2, direction)(points)) > 0
    saved = deepcopy(base.state_dict())
    delta.nonzero_qualification_state()
    assert all(v.equal(base.state_dict()[k]) for k, v in saved.items())


def test_independent_two_point_networks_sum_with_phase_once():
    base, delta = fields()
    delta.nonzero_qualification_state()
    points = torch.tensor([[0.2, 0.3, 0.1], [-0.4, 0.1, -0.3]], dtype=torch.float64)
    expected = base(points) + delta(points)
    torch.testing.assert_close(
        independent_sum_field(base, delta)(points), expected, rtol=1e-13, atol=1e-13
    )
    duplicate = expected * torch.exp(1j * (points @ base.phase_wavevector))[:, None]
    assert torch.linalg.vector_norm(duplicate - expected) > 1e-5


@pytest.mark.parametrize(
    "wrong",
    [
        "g",
        "c_base",
        "c_combined",
        "r_original",
        "base_model_hash",
        "residual_branch_identity",
        "base_model",
        "base_RNG",
        "model",
    ],
)
def test_saved_composite_state_rejects_wrong_or_repeated_branch(wrong):
    base, delta = fields()
    a = MatrixAction()
    view = ResidualTrainingAction(a, np.array([0.1j, 0.2 + 0j]))
    context = ResidualBranchContext(
        base, view, dict(base_checkpoint_sha256="a" * 64, phase_sha256="b" * 64)
    )
    context.base_RNG = dict(
        torch_rng=torch.get_rng_state().clone(),
        numpy_rng=deepcopy(np.random.get_state()),
    )
    d = np.array([0.2j, 0.4 + 0j])
    r = view.apply(d) - view.f
    state = context.checkpoint_fields(d, r)
    state.update(c=d.copy(), r=r.copy(), model=deepcopy(delta.state_dict()))
    context.verify_saved(state)
    bad = deepcopy(state)
    if wrong == "base_model":
        key = next(iter(bad[wrong]))
        bad[wrong][key] += 1
    elif wrong == "base_RNG":
        bad[wrong]["torch_rng"][0] += 1
    elif wrong == "model":
        bad[wrong]["phase_wavevector"][0] += 0.1
    elif wrong in ("base_model_hash", "residual_branch_identity"):
        bad[wrong] = "wrong"
    else:
        bad[wrong] = bad[wrong] + 0.1
    with pytest.raises(ValueError):
        context.verify_saved(bad)


def test_correction_parameter_version_invalidates_cache_without_base_pollution():
    from src.test.test_ftt_structure import fixture
    from src.solvers.ftt_factored_moments import FactoredMomentMap, model_identity
    from src.solvers.ftt_moments import StreamingMomentMap

    base, delta = fields()
    mapping = FactoredMomentMap(fixture())
    old = StreamingMomentMap(fixture())
    c_base = mapping.forward(base)
    base_key = mapping.cache_key
    assert not np.any(mapping.forward(delta)) and mapping.cache_key != base_key
    delta.nonzero_qualification_state()
    c_delta = mapping.forward(delta)
    assert mapping.cache_key == model_identity(delta)
    np.testing.assert_allclose(c_delta, old.forward(delta), rtol=1e-12, atol=1e-14)
    np.testing.assert_array_equal(mapping.forward(base), c_base)
    assert mapping.cache_key == base_key


def test_nonzero_correction_hidden_complex_loss_finite_difference():
    base, delta = fields()
    delta.nonzero_qualification_state()
    points = torch.tensor(
        [[0.2, 0.3, 0.1], [-0.4, 0.1, -0.3], [0.1, -0.2, 0.4]], dtype=torch.float64
    )
    target = torch.tensor(
        [[1 + 2j, 0.3j, -0.4], [0.2j, 0.8, 1j], [0.4, -0.2j, 0.1]],
        dtype=torch.complex128,
    )

    def loss():
        return torch.sum(torch.abs(delta(points) - target) ** 2) / 2

    loss().backward()
    p = delta.cores[0][0].bias
    direction = torch.linspace(0.1, 1, 32, dtype=torch.float64)
    direction /= torch.linalg.vector_norm(direction)
    analytic = torch.dot(p.grad, direction).item()
    assert abs(analytic) > 1e-8
    original = p.detach().clone()
    values = []
    for h in (1e-4, 1e-5, 1e-6):
        results = []
        for sign in (1, -1):
            with torch.no_grad():
                p.copy_(original + sign * h * direction)
            results.append(loss().item())
        numeric = (results[0] - results[1]) / (2 * h)
        values.append(abs(analytic - numeric) / max(abs(analytic), abs(numeric)))
    with torch.no_grad():
        p.copy_(original)
    assert min(values) < 1e-5
