"""Only the fine H6 smoother needed by the explicit lightweight physical PC."""
import hashlib

from .fullspace_mpc_action import FullspaceMpcFormAction
from .fullspace_partial_assembly import IsotropicPartialAssembly
from .fullspace_quadrature_diagonal import build_quadrature_positive_diagonal
from .fullspace_same_mesh_hcurl_pmg_global import same_mesh_positive_form
from .fullspace_same_mesh_hcurl_pmg_p6 import SameMeshP6MatrixFreeShell
from .fullspace_lor_edge_geometric_mg_global import FixedChebyshevJacobiPETSc
from .fullspace_lor_native_hx_fixture import build_frozen_fullspace_primal_source


def build_light_h6_setup(levels, cfg, marker):
    space, floquet = levels['spaces'][6], levels['floquets'][6]
    mu, mass = levels['mu'], levels['mass']
    action = diagonal = shell = smoother = None
    try:
        marker('h6_original_setup_started', {})
        form = same_mesh_positive_form(space, curl_coefficient=mu, mass_coefficient=mass)
        action = FullspaceMpcFormAction(form, space, mpc=floquet.mpc)
        diagonal = build_quadrature_positive_diagonal(space, mu, mass, floquet.mpc)
        shell = SameMeshP6MatrixFreeShell(action, diagonal)
        action = diagonal = None
        seed, _ = build_frozen_fullspace_primal_source(space, floquet, cfg, 'random')
        try:
            seed_sha = hashlib.sha256(seed.array.tobytes()).hexdigest()
            smoother = FixedChebyshevJacobiPETSc(shell.matrix, power_seed=seed)
        finally:
            seed.destroy()
        # The original FFCx action determines the frozen power10 window.
        # Only subsequent H6 applications use the qualified packed kernel.
        fast = FullspaceMpcFormAction(form, space, mpc=floquet.mpc,
            local_kernel=IsotropicPartialAssembly(floquet.mpc.function_space, mu, mass, contiguous_work=True))
        original = shell.action
        shell.action = fast
        original.destroy()
        facts = dict(schema='physical-intermediate.light-h6-setup.v1', shared_mesh_levels=[6, 4],
            positive_p3_p1_constructed=False, positive_factor_count=0, h6_degree=3,
            calls_per_PC=dict(H6=2, S6=0, B6=4, positive_p3=0, positive_p1=0),
            seed_sha256=seed_sha, seed_recipe='build_frozen_fullspace_primal_source random',
            diagonal_sha256=hashlib.sha256(shell.diagonal.array.tobytes()).hexdigest(),
            inverse_sqrt_diagonal_sha256=hashlib.sha256(smoother._inv_sqrt.array.tobytes()).hexdigest(),
            power_history=list(smoother.power_history), lambda_lo=smoother.lambda_lo, lambda_hi=smoother.lambda_hi,
            power_matrix_mult_count=smoother.power_matrix_mult_count,
            kernel=dict(fast._local_kernel.audit))
        marker('h6_original_window_and_packed_action_complete', facts)
        return dict(p6_shell=shell, h6=smoother, light_facts=facts)
    except BaseException:
        if smoother is not None: smoother.destroy()
        if shell is not None: shell.destroy()
        if action is not None: action.destroy()
        if diagonal is not None: diagonal.destroy()
        raise
