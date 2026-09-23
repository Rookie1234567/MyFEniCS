"""Only the fine H6 smoother needed by the explicit lightweight physical PC."""
import hashlib
import time

from .fullspace_mpc_action import FullspaceMpcFormAction
from .fullspace_partial_assembly import IsotropicPartialAssembly
from .fullspace_quadrature_diagonal import build_quadrature_positive_diagonal
from .fullspace_same_mesh_hcurl_pmg_global import same_mesh_positive_form
from .fullspace_same_mesh_hcurl_pmg_p6 import SameMeshP6MatrixFreeShell
from .fullspace_lor_edge_geometric_mg_global import FixedChebyshevJacobiPETSc
from .fullspace_lor_native_hx_fixture import build_frozen_fullspace_primal_source


def build_light_h6_setup(
    levels,
    cfg,
    marker,
    *,
    packed_power10=False,
    packed_apply=True,
    preallocated_work=False,
    preallocated_power10=None,
    sum_factorized_work=False,
    sum_factorized_power10=None,
    shared_contractions=False,
    direct_selected_backend=False,
    reuse_projection_work=False,
    batched_target_grouping=False,
):
    if sum_factorized_power10 is None:
        sum_factorized_power10 = bool(sum_factorized_work)
    return build_light_level_setup(
        levels,
        cfg,
        marker,
        degree=6,
        packed_power10=packed_power10,
        packed_apply=packed_apply,
        preallocated_work=preallocated_work,
        preallocated_power10=preallocated_power10,
        sum_factorized_work=sum_factorized_work,
        sum_factorized_power10=sum_factorized_power10,
        shared_contractions=shared_contractions,
        direct_selected_backend=direct_selected_backend,
        reuse_projection_work=reuse_projection_work,
        batched_target_grouping=batched_target_grouping,
    )


def build_light_level_setup(
    levels,
    cfg,
    marker,
    *,
    degree,
    packed_power10=False,
    packed_apply=True,
    preallocated_work=False,
    preallocated_power10=None,
    sum_factorized_work=False,
    sum_factorized_power10=None,
    shared_contractions=False,
    direct_selected_backend=False,
    reuse_projection_work=False,
    batched_target_grouping=False,
):
    if degree not in (4, 6):
        raise ValueError('physical pilot smoother supports p6/p4 only')
    if preallocated_power10 is None:
        preallocated_power10 = bool(preallocated_work)
    if sum_factorized_power10 is None:
        sum_factorized_power10 = bool(sum_factorized_work)
    space, floquet = levels['spaces'][degree], levels['floquets'][degree]
    mu, mass = levels['mu'], levels['mass']
    action = diagonal = shell = smoother = None
    timing = {}
    power10_kernel_facts = {
        'backend': 'native_ffcx',
        'temporary_budget_bytes': 0,
        'reference_table_bytes': 0,
        'cell_metadata_bytes': 0,
    }
    try:
        marker('h6_original_setup_started' if degree == 6 else 'h4_setup_started', {})
        started = time.perf_counter()
        form = same_mesh_positive_form(space, curl_coefficient=mu, mass_coefficient=mass)
        direct_backend = bool(
            direct_selected_backend
            and packed_power10
            and packed_apply
            and bool(preallocated_power10) == bool(preallocated_work)
            and bool(sum_factorized_power10) == bool(sum_factorized_work)
        )
        if direct_backend:
            action = FullspaceMpcFormAction(
                form,
                space,
                mpc=floquet.mpc,
                local_kernel=IsotropicPartialAssembly(
                    floquet.mpc.function_space,
                    mu,
                    mass,
                    contiguous_work=True,
                    preallocated_work=preallocated_work,
                    sum_factorized_work=sum_factorized_work,
                    shared_contractions=shared_contractions,
                    reuse_projection_work=reuse_projection_work,
                    share_geometry=direct_backend,
                ),
            )
            power10_kernel_facts = dict(action._local_kernel.audit)
            timing['positive_selected_action_seconds'] = time.perf_counter() - started
        else:
            action = FullspaceMpcFormAction(form, space, mpc=floquet.mpc)
            timing['positive_native_action_seconds'] = time.perf_counter() - started
        started = time.perf_counter()
        diagonal_audit = {}
        diagonal = build_quadrature_positive_diagonal(
            space,
            mu,
            mass,
            floquet.mpc,
            batched_target_grouping=bool(batched_target_grouping and direct_backend),
            reuse_local_types=bool(direct_backend),
            audit=diagonal_audit,
        )
        timing['diagonal_seconds'] = time.perf_counter() - started
        started = time.perf_counter()
        shell = SameMeshP6MatrixFreeShell(action, diagonal)
        timing['b6_shell_seconds'] = time.perf_counter() - started
        action = diagonal = None
        if packed_power10 and not direct_backend:
            packed = FullspaceMpcFormAction(
                form,
                space,
                mpc=floquet.mpc,
                local_kernel=IsotropicPartialAssembly(
                    floquet.mpc.function_space,
                    mu,
                    mass,
                    contiguous_work=True,
                    preallocated_work=preallocated_power10,
                    sum_factorized_work=sum_factorized_power10,
                    shared_contractions=shared_contractions,
                    reuse_projection_work=reuse_projection_work,
                    share_geometry=direct_backend,
                ),
            )
            power10_kernel_facts = dict(packed._local_kernel.audit)
            original = shell.action
            shell.action = packed
            original.destroy()
        seed, _ = build_frozen_fullspace_primal_source(space, floquet, cfg, 'random')
        try:
            seed_sha = hashlib.sha256(seed.array.tobytes()).hexdigest()
            started = time.perf_counter()
            smoother = FixedChebyshevJacobiPETSc(shell.matrix, power_seed=seed)
            timing['power10_seconds'] = time.perf_counter() - started
        finally:
            seed.destroy()
        if not packed_power10 and packed_apply:
            # The original FFCx action determines the frozen power10 window.
            # Only subsequent H6 applications use the qualified packed kernel.
            packed = FullspaceMpcFormAction(
                form,
                space,
                mpc=floquet.mpc,
                local_kernel=IsotropicPartialAssembly(
                    floquet.mpc.function_space,
                    mu,
                    mass,
                    contiguous_work=True,
                    preallocated_work=preallocated_work,
                    sum_factorized_work=sum_factorized_work,
                    shared_contractions=shared_contractions,
                    reuse_projection_work=reuse_projection_work,
                    share_geometry=direct_backend,
                ),
            )
            original = shell.action
            shell.action = packed
            original.destroy()
        elif packed_power10 and packed_apply and not direct_backend and (
            bool(preallocated_power10) != bool(preallocated_work)
            or bool(sum_factorized_power10) != bool(sum_factorized_work)
        ):
            # Keep setup and post-setup apply candidates independently
            # selectable.  The initial packed action owns the power-estimation
            # kernel; this replacement owns the later apply kernel.
            packed = FullspaceMpcFormAction(
                form,
                space,
                mpc=floquet.mpc,
                local_kernel=IsotropicPartialAssembly(
                    floquet.mpc.function_space,
                    mu,
                    mass,
                    contiguous_work=True,
                    preallocated_work=preallocated_work,
                    sum_factorized_work=sum_factorized_work,
                    shared_contractions=shared_contractions,
                    reuse_projection_work=reuse_projection_work,
                    share_geometry=direct_backend,
                ),
            )
            original = shell.action
            shell.action = packed
            original.destroy()
        elif packed_power10 and not packed_apply:
            # The power estimate was intentionally obtained from the packed
            # action, but this paired setup keeps the subsequent H6 apply on
            # the native action.  This is an opt-in measurement path; the
            # historical default remains packed_apply=True.
            native = FullspaceMpcFormAction(form, space, mpc=floquet.mpc)
            original = shell.action
            shell.action = native
            original.destroy()
        kernel = getattr(shell.action, "_local_kernel", None)
        kernel_facts = (
            dict(kernel.audit)
            if kernel is not None
            else {
                "backend": "native_ffcx",
                "temporary_budget_bytes": 0,
                "reference_table_bytes": 0,
                "cell_metadata_bytes": 0,
            }
        )
        facts = dict(schema='physical-intermediate.light-h6-setup.v1', shared_mesh_levels=[6],
            positive_p3_p1_constructed=False, positive_factor_count=0, h6_degree=3,
            calls_per_PC=dict(H6=2, S6=0, B6=4, positive_p3=0, positive_p1=0),
            seed_sha256=seed_sha, seed_recipe='build_frozen_fullspace_primal_source random',
            diagonal_sha256=hashlib.sha256(shell.diagonal.array.tobytes()).hexdigest(),
            inverse_sqrt_diagonal_sha256=hashlib.sha256(smoother._inv_sqrt.array.tobytes()).hexdigest(),
            power_history=list(smoother.power_history), lambda_lo=smoother.lambda_lo, lambda_hi=smoother.lambda_hi,
            lambda_power10=smoother.lambda_power10,
            power_matrix_mult_count=smoother.power_matrix_mult_count,
            power_matrix_mult_seconds=smoother.power_matrix_mult_seconds,
            power10_action_backend=(
                'packed_partial_assembly' if packed_power10 else 'native_ffcx'
            ),
            power10_kernel=power10_kernel_facts,
            packed_power10_opt_in=bool(packed_power10),
            power10_preallocated_work_opt_in=bool(preallocated_power10),
            apply_action_backend=(
                'packed_partial_assembly' if packed_apply else 'native_ffcx'
            ),
            packed_apply_opt_in=bool(packed_apply),
            apply_preallocated_work_opt_in=bool(preallocated_work),
            sum_factorized_work_opt_in=bool(sum_factorized_work),
            sum_factorized_power10_opt_in=bool(sum_factorized_power10),
            shared_contractions_opt_in=bool(shared_contractions),
            direct_selected_backend_opt_in=bool(direct_selected_backend),
            direct_selected_backend_used=bool(direct_backend),
            reuse_projection_work_opt_in=bool(reuse_projection_work),
            batched_target_grouping_opt_in=bool(
                batched_target_grouping and direct_backend
            ),
            diagonal_local_type_reuse=dict(diagonal_audit),
            kernel=kernel_facts)
        facts['setup_timing_seconds'] = dict(timing)
        if degree != 6:
            facts.update(schema='physical-recursive.h4-setup.v1', level=degree, shared_mesh_levels=[6, 4, 2],
                calls_per_PC=dict(H4=1, B4_positive=2), h4_degree=3)
            facts.pop('h6_degree', None)
        marker('h6_original_window_and_packed_action_complete' if degree == 6 else 'h4_window_complete', facts)
        if degree == 6:
            return dict(
                p6_shell=shell,
                h6=smoother,
                light_facts=facts,
                geometry_bundle=getattr(kernel, "geometry_bundle", None),
            )
        return dict(shell=shell, smoother=smoother, light_facts=facts)
    except BaseException:
        if smoother is not None: smoother.destroy()
        if shell is not None: shell.destroy()
        if action is not None: action.destroy()
        if diagonal is not None: diagonal.destroy()
        raise
