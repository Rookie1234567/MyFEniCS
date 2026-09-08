"""Owned formal adapter; no reference field or error samples enter this module."""
from copy import deepcopy
import numpy as np


def install_balanced_pc(bundle, cfg, identity, *, sample, marker, save, append):
    from src.io.physical_balanced_profile import BALANCED_ROUTES
    from .physical_balanced_coupling import PhysicalBalancedCoupling
    from .physical_reference_diagnostics import DiagnosticRefinementV4
    from .fullspace_physical_intermediate import apply_owned
    from .fullspace_physical_intermediate_runtime import attach_physical_reference
    route = BALANCED_ROUTES[identity]
    light = route != 'BAL_S'
    actions = bundle['actions']
    limit = (7 if route == 'PROJ_K6' else 2)*2048
    policy = DiagnosticRefinementV4(save, actions['physical'][4]['dtn_action'], np.empty(0),
        dict(profile=identity, mode_sha256=bundle['fine']['mode_sha256'],
             quadrature=actions['volume_quadrature_metadata']),
        logical_limit=limit, solve_limit=3*limit, capture_success_vectors=False,
        retain_records=False, replay_first_failure=False, verify_first_actions=False)
    attach_physical_reference(bundle, cfg, resource_sample=sample, marker=marker,
        light=light, diagnostic_refinement_v4=policy)
    transfer = actions['transfers'][(6,4)]
    factor = bundle['reference_factor']
    smoother = bundle['positive']['h6' if light else 'upper_cycle']
    smooth_facts = []  # at most six small scalar facts, cleared for every PC

    def coarse(source):
        rhs = transfer.apply_adjoint(source)
        value = None
        try:
            value = factor.solve_intermediate(rhs)['final_solution']
            return transfer.apply_primal(value)
        finally:
            if value is not None:
                value.destroy()
            rhs.destroy()

    def smooth(source):
        value = smoother.apply(source)
        try:
            smooth_facts.append(deepcopy(smoother.last_apply_facts))
            return value
        except BaseException:
            value.destroy()
            raise

    pc = PhysicalBalancedCoupling(lambda x: apply_owned(bundle['fine']['physical_action'], x),
        coarse, smooth, transfer.apply_adjoint, route=route, checkpoint=sample)

    def apply(source):
        smooth_facts.clear()
        before = dict(policy.action_counts, MatSolve=policy.external_solves, C=policy.logical_rhs)
        policy.label = f'formal_pc_{pc.attempted+1:06d}'
        value = None
        try:
            value = pc.apply(source)
            row = dict(pc.last_apply_facts, smoother_facts=list(smooth_facts),
                p4_counts={k:v-before[k] for k,v in
                    dict(policy.action_counts, MatSolve=policy.external_solves, C=policy.logical_rhs).items()})
            append('pc_applies.jsonl', row)
            return value
        except BaseException as exc:
            if value is not None:
                value.destroy()
            save(policy.label+'_failure', dict(input=source.array.copy(),
                stages=pc.last_apply_facts, exception_type=type(exc).__name__, reason=str(exc)))
            raise
        finally:
            smooth_facts.clear()

    bundle['pc'] = pc
    return apply, policy
