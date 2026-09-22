"""Post-setup opt-in replacement of only B6 and PC-internal physical volume."""
import hashlib
import json

import numpy as np
from dolfinx import fem

from .fullspace_mpc_action import FullspaceMpcFormAction
from .fullspace_partial_assembly import IsotropicPartialAssembly
from .fullspace_physical_action import FullspacePhysicalAction, FullspaceSplitVolumeAction
from .fullspace_same_mesh_hcurl_pmg_global import same_mesh_positive_form

from src.io.physical_intermediate_profile import FAST_PROFILE, PACKED_PROFILE


def build_packed_physical_action(
    common,
    cfg,
    *,
    contiguous_work=True,
    preallocated_work=False,
    sum_factorized_work=False,
    reuse_projection_work=False,
    share_readonly_geometry=False,
    geometry_bundle=None,
):
    """Build a packed volume action for one explicit PC owner.

    The returned physical action borrows the established degree-6 DtN action
    and owns only the two packed volume components.  Keeping this object
    separate from ``common['fine']['physical_action']`` preserves the native
    A6 action as the independent residual authority.
    """

    from .fullspace_physical_action import FullspacePhysicalAction

    levels = common["levels"]
    fine = common["fine"]
    space = levels["floquets"][6].mpc.function_space
    original_components = fine["volume_action"].component_actions
    forms = tuple(
        original_components[key]._bilinear_form
        for key in ("curl", "material_mass")
    )
    dg = fem.functionspace(space.mesh, ("DG", 0))
    physical_mu, physical_mass = fem.Function(dg), fem.Function(dg)
    kernels = ()
    volume = action = None
    try:
        physical_mu.x.array[:] = 0
        physical_mass.x.array[:] = 0
        tags = levels["mesh_data"].cell_tags
        for tag, epsilon in (
            (cfg.tags.air, cfg.eps_r),
            (cfg.tags.substrate, cfg.substrate_index**2),
            (cfg.tags.grating, cfg.grating_index**2),
        ):
            for cell in tags.find(tag):
                dof = dg.dofmap.cell_dofs(cell)[0]
                physical_mu.x.array[dof] += 1 / cfg.mu_r
                physical_mass.x.array[dof] += -cfg.k0**2 * epsilon
        physical_mu.x.scatter_forward()
        physical_mass.x.scatter_forward()
        kernels_list = []
        external_geometry_bundle = geometry_bundle if share_readonly_geometry else None
        geometry_bundle = None
        geometry_borrowed_components = []
        geometry_fallbacks = []
        for index, (form, component) in enumerate(
            zip(forms, ("curl", "mass"), strict=True)
        ):
            candidate_bundle = (
                external_geometry_bundle if index == 0 else geometry_bundle
            ) if share_readonly_geometry else None
            try:
                kernel = IsotropicPartialAssembly(
                    space,
                    physical_mu,
                    physical_mass,
                    component_form=form,
                    component=component,
                    contiguous_work=contiguous_work,
                    preallocated_work=preallocated_work,
                    sum_factorized_work=sum_factorized_work,
                    reuse_projection_work=reuse_projection_work,
                    share_geometry=share_readonly_geometry,
                    geometry_bundle=candidate_bundle,
                )
                if candidate_bundle is not None:
                    geometry_borrowed_components.append(component)
            except ValueError as exc:
                if candidate_bundle is None or str(exc) not in {
                    "shared geometry bundle quadrature identity mismatch",
                    "shared reference bundle identity mismatch",
                }:
                    raise
                geometry_fallbacks.append({"component": component, "reason": str(exc)})
                kernel = IsotropicPartialAssembly(
                    space,
                    physical_mu,
                    physical_mass,
                    component_form=form,
                    component=component,
                    contiguous_work=contiguous_work,
                    preallocated_work=preallocated_work,
                    sum_factorized_work=sum_factorized_work,
                    reuse_projection_work=reuse_projection_work,
                    share_geometry=share_readonly_geometry,
                )
            kernels_list.append(kernel)
            if share_readonly_geometry and geometry_bundle is None:
                geometry_bundle = kernel.geometry_bundle
        kernels = tuple(kernels_list)
        volume = FullspaceSplitVolumeAction(
            *forms, space, mpc=levels["floquets"][6].mpc, local_kernels=kernels
        )
        action = FullspacePhysicalAction(
            volume, fine["dtn_action"], owns_dtn=False
        )
        component_audits = [
            dict(component)
            for component in action.audit["volume_action"]["components"].values()
        ]
        facts = {
            "schema": "task039extra.v24.packed-pc-physical-action.v1",
            "backend": "isotropic_partial_assembly",
            "contiguous_work": bool(contiguous_work),
            "preallocated_work": bool(preallocated_work),
            "sum_factorized_work": bool(sum_factorized_work),
            "reuse_projection_work": bool(reuse_projection_work),
            "shared_geometry_bundle": (
                {
                    "schema": geometry_bundle["schema"],
                    "identity": dict(geometry_bundle["identity"]),
                    "enabled": bool(geometry_borrowed_components),
                    "same_owner": True,
                    "borrowed_components": list(geometry_borrowed_components),
                    "source_owner": (
                        "h6_external"
                        if external_geometry_bundle is not None
                        and "curl" in geometry_borrowed_components
                        else "a6_curl"
                    ),
                    "readonly_arrays": all(
                        not geometry_bundle[key].flags.writeable
                        for key in (
                            "dofs",
                            "permutations",
                            "metrics",
                            "geometry_derivatives",
                        )
                    ),
                    "reference_data_shared": bool(
                        geometry_borrowed_components
                        and geometry_bundle.get("reference_bundle") is not None
                    ),
                    "reference_quadrature_not_shared": not bool(
                        geometry_borrowed_components
                        and geometry_bundle.get("reference_bundle") is not None
                    ),
                    "material_data_not_shared": True,
                    "fallbacks": geometry_fallbacks,
                }
                if share_readonly_geometry
                else {"enabled": False}
            ),
            "dtn_borrowed": True,
            "native_a6_independent": True,
            "material_function_array_bytes": int(
                physical_mu.x.array.nbytes + physical_mass.x.array.nbytes
            ),
            "kernels": [dict(kernel.audit) for kernel in kernels],
            "kernel_temporary_bytes": int(
                max(kernel.audit["temporary_budget_bytes"] for kernel in kernels)
            ),
            "reference_initialization_array_upper_bound_bytes": int(
                max(
                    kernel.audit["reference_initialization_array_upper_bound_bytes"]
                    for kernel in kernels
                )
            ),
            "component_audits": component_audits,
        }
        return {
            "physical_action": action,
            "volume_action": volume,
            "kernels": kernels,
            "material_functions": (physical_mu, physical_mass),
            "facts": facts,
        }
    except BaseException:
        if action is not None:
            action.destroy()
        elif volume is not None:
            volume.destroy()
        raise


def frozen_smoother_identity(positive):
    """Hash the actual original setup state, not a reconstruction from a seed."""
    def array_sha(array):
        return hashlib.sha256(np.ascontiguousarray(array).tobytes()).hexdigest()
    facts = {'p6_diagonal_sha256': array_sha(positive['p6_shell'].diagonal.array)}
    for role in ('upper', 'lower'):
        smoother = positive[role+'_cycle'].smoother
        window = dict(lambda_lo=smoother.lambda_lo, lambda_hi=smoother.lambda_hi,
                      lambda_power10=smoother.lambda_power10, power_history=list(smoother.power_history))
        facts[role] = dict(inverse_sqrt_diagonal_sha256=array_sha(smoother._inv_sqrt.array),
            window=window, window_sha256=hashlib.sha256(json.dumps(window, sort_keys=True).encode()).hexdigest())
    return facts


def shared_setup_identity(bundle):
    """Process-local identities prove the paired paths borrow the same objects."""
    p = bundle['positive']
    return dict(reference_factor=id(bundle['reference_factor']),
        fine_authority=id(bundle['fine']['physical_action']),
        upper=id(p['upper_cycle']), lower=id(p['lower_cycle']),
        upper_smoother=id(p['upper_cycle'].smoother), lower_smoother=id(p['lower_cycle'].smoother),
        transfers={str(k):id(v) for k,v in bundle.get('actions', {}).get('transfers', {}).items()},
        p63=id(getattr(p['upper_cycle'], 'p63_transfer', None)),
        p31=id(getattr(p['lower_cycle'], 'owner_transfer', None)),
        p3=id(getattr(p['lower_cycle'], 'fine_matrix', None)),
        p1=id(getattr(p['lower_cycle'], 'coarse_matrix', None)),
        p1_factor=id(getattr(p['lower_cycle'], 'coarse_solver', None)))


def install_equivalent_fast(
    bundle, cfg, *, profile=FAST_PROFILE, preallocated_work=False
):
    """Called only after the original setup, windows and qualification finish."""
    if 'equivalent_fast' in bundle:
        raise ValueError('fast PC backend already installed')
    if profile not in (FAST_PROFILE, PACKED_PROFILE):
        raise ValueError('unknown equivalent backend')
    packed = profile == PACKED_PROFILE
    positive, fine, levels = bundle['positive'], bundle['fine'], bundle['levels']
    before = frozen_smoother_identity(positive)
    shared = shared_setup_identity(bundle)
    mpc = levels['floquets'][6].mpc
    space = mpc.function_space
    fast_b6 = fast_volume = fast_physical = None
    try:
        mu, mass = levels['mu'], levels['mass']
        form = same_mesh_positive_form(space, curl_coefficient=mu, mass_coefficient=mass)
        fast_b6 = FullspaceMpcFormAction(form, space, mpc=mpc,
            local_kernel=IsotropicPartialAssembly(
                space,
                mu,
                mass,
                contiguous_work=packed,
                preallocated_work=preallocated_work,
            ))
        # Borrow original split forms with their individual tags/rules.
        original_components = fine['volume_action'].component_actions
        forms = tuple(original_components[k]._bilinear_form for k in ('curl', 'material_mass'))
        dg = fem.functionspace(space.mesh, ('DG', 0))
        physical_mu, physical_mass = fem.Function(dg), fem.Function(dg)
        physical_mu.x.array[:] = 0
        physical_mass.x.array[:] = 0
        tags = levels['mesh_data'].cell_tags
        for tag, epsilon in ((cfg.tags.air, cfg.eps_r),
                (cfg.tags.substrate, cfg.substrate_index**2), (cfg.tags.grating, cfg.grating_index**2)):
            for cell in tags.find(tag):
                dof = dg.dofmap.cell_dofs(cell)[0]
                physical_mu.x.array[dof] += 1/cfg.mu_r
                physical_mass.x.array[dof] += -cfg.k0**2*epsilon
        physical_mu.x.scatter_forward()
        physical_mass.x.scatter_forward()
        kernels = tuple(IsotropicPartialAssembly(space, physical_mu, physical_mass,
            component_form=form, component=component, contiguous_work=packed,
            preallocated_work=preallocated_work)
            for form, component in zip(forms, ('curl', 'mass'), strict=True))
        fast_volume = FullspaceSplitVolumeAction(*forms, space, mpc=mpc, local_kernels=kernels)
        fast_physical = FullspacePhysicalAction(fast_volume, fine['dtn_action'], owns_dtn=False)
        old_b6 = positive['p6_shell'].action
        positive['p6_shell'].action = fast_b6
        bundle['pc'].fine_action = fast_physical
        after = frozen_smoother_identity(positive)
        facts = dict(profile=profile, original_setup_before=before, installed_after=after,
            shared_setup_objects=shared,
            original_state_preserved=before == after, window_reference='same-run original setup before replacement',
            r0_window_array_hash_available=False, original_a6_authority=True, owns_dtn=False,
            physical_dg0_function_arrays_bytes=int(physical_mu.x.array.nbytes + physical_mass.x.array.nbytes),
            component_payload_accounting='component table/metadata upper bounds; borrowed metadata may overlap; not unique RSS',
            kernels=[dict(fast_b6._local_kernel.audit), *(dict(k.audit) for k in kernels)])
        bundle['equivalent_fast'] = dict(original_b6=old_b6, b6=fast_b6,
            physical_action=fast_physical, volume_action=fast_volume, facts=facts)
        if before != after:
            raise RuntimeError('fast installation changed original diagonal/window')
        return facts
    except BaseException:
        if 'equivalent_fast' in bundle:
            release_equivalent_fast(bundle)
        else:
            if fast_physical is not None:
                fast_physical.destroy()
            elif fast_volume is not None:
                fast_volume.destroy()
            if fast_b6 is not None:
                fast_b6.destroy()
        raise


def select_equivalent_backend(bundle, *, packed):
    """Switch only borrowed action references, with all timing wrappers closed."""
    fast = bundle['equivalent_fast']
    if fast['facts']['profile'] != PACKED_PROFILE:
        raise ValueError('paired switching requires the explicit packed V2 profile')
    if frozen_smoother_identity(bundle['positive']) != fast['facts']['original_setup_before']:
        raise RuntimeError('paired switch changed original setup/window')
    if shared_setup_identity(bundle) != fast['facts']['shared_setup_objects']:
        raise RuntimeError('paired switch changed transfer/factor or has active timing wrappers')
    bundle['positive']['p6_shell'].action = fast['b6'] if packed else fast['original_b6']
    bundle['pc'].fine_action = fast['physical_action'] if packed else bundle['fine']['physical_action']


def release_equivalent_fast(bundle):
    fast = bundle.pop('equivalent_fast', None)
    if fast is None:
        return
    bundle['pc'].fine_action = bundle['fine']['physical_action']
    bundle['positive']['p6_shell'].action = fast['original_b6']
    fast['physical_action'].destroy()
    fast['b6'].destroy()
