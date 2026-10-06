"""Descriptor-only size and lifetime bridge; no target mesh or PDE objects."""
from dataclasses import replace
import math
import numpy as np
from src.runners.task042_shared import write_json
from .scattering_anchor import save_arrays


def layout(nx,ny,nz,p):
    fe=nx*ny*p*p*(3*p*nz+2);inside=3*nx*ny*nz*p*(p-1)**2
    trace=nx*ny*p*((6*p-3)*nz+2*p)
    if fe!=trace+inside:raise ValueError('periodic layout exact partition')
    return dict(cells=nx*ny*nz,independent_FE=fe,trace=trace,internal=inside,
        one_full_complex128_vector_bytes=16*fe,one_trace_vector_bytes=16*trace,
        Krylov_32_inventory_scenario_bytes=16*fe*34,
        Krylov_inventory_label='32 retained search directions plus two vectors, capacity scenario only; no algorithm chosen',
        raw_tensor_one_local_class_bytes=(3*p*(p+1)**2)**2*16,
        local_recovery_dense_one_cell_bytes=(3*p*(p-1)**2)*(3*p*(p+1)**2)*16)


def target_bridge(science,folder,journal):
    from .phase_explicit_accuracy import configuration
    from . import phase_saved_closure_scope as scope
    from src.common.modes_3d import outgoing_port_modes_3d
    original=scope.plan_record()['physical_descriptor'];base=configuration('NOTCH',6)
    check=layout(4,4,20,7);h7=scope.plan_record()['cases']['H7']
    if (check['independent_FE'],check['trace'],check['internal'])!=(h7['independent'],h7['trace'],h7['internal']):raise ValueError('H7 structured formula calibration')
    rows=[]
    with journal.measured('descriptor_only_bridge_mode_inventory_no_target_mesh'):
        for numerator in (14,28,135):
            s=numerator/135;ratio=numerator/7;factor=math.ceil(ratio)
            nx=4*factor;ny=4*factor;nz=20*factor
            # Preserve the physical transverse reciprocal cutoff of the measured
            # 828 inventory; this is an explicit planning rule, not an M pass.
            m=math.ceil(11*ratio);n=math.ceil(4*ratio)
            cfg=replace(base,period_x=50*s,period_y=25*s,z_min=-10*s,z_max=130*s,
                stage4_dtn_order_policy='manual',
                diffraction_order_max_m=m,diffraction_order_max_n=n)
            modes=outgoing_port_modes_3d(cfg)
            keys=np.asarray([(0 if x.side=='top' else 1,x.m,x.n,0 if x.polarization=='s' else 1) for x in modes],np.int32)
            wave=np.asarray([[x.alpha,x.gamma,x.beta] for x in modes],complex)
            receipt=save_arrays(folder/f'bridge_s{numerator}_physical_mode_inventory.npz',keys=keys,wavenumbers=wave)
            count=len(modes);del modes
            cases={str(p):layout(nx,ny,nz,p) for p in (6,7)}
            for x in cases.values():
                x.update(complete_modes=count,condensed_rows=x['trace']+count,mode_vector_bytes=16*count,
                    unstreamed_C_D_dense_bytes=32*x['trace']*count,
                    streamed_DtN_boundary_workspace='depends on actual boundary partition, batching and shared tables; unknown')
            rows.append(dict(scale_fraction=f'{numerator}/135',lambda_nm=.7,periods_nm=[50*s,25*s],z_nm=[-10*s,130*s],
                notch_box_nm=[v*ratio for v in original['geometry']['notch_box_nm']],
                Nx=nx,Ny=ny,Nz=nz,physical_h_scenario='ceil(scale/base_scale) subdivision factor, based on p7/Z4; not accuracy qualified',
                modes=count,mode_rule=dict(policy='manual',m=[-m,m],n=[-n,n],rule='same physical reciprocal cutoff, rounded outward'),
                actual_mode_inventory=receipt,layouts=cases,
                factor_fill='unknown',iteration_count='unknown',simultaneous_tree_RSS='unknown',hours48_qualified=False,
                target_mesh_or_vectors_allocated=False))
    r=dict(H7_formula_calibration=check,accuracy=dict(same_p_h=science['comparisons']['R7_H7']['pass_gate'],
        cross_p=science['comparisons']['R6_H7']['pass_gate'],new_h_under_changed_M='unknown',continuum=False),
        bridge_scenarios=rows,twoTB_48h_qualification='NOT_QUALIFIED',NN20='NOT_MEASURED; deterministic accuracy work',
        action_contract=dict(representation='E=g*u, Ckappa=curl(u)+i*kappa cross u; envelope MPC',
            kappa=[8.94046081729244,.7821889682108057,0.],mode_keys='side,m,n,polarization,physical reference plane; all modes',
            operator='independent uncondensed Ckappa volume + complete DtN',restore='original total native envelope, nonzero internal particular retained',
            reference_inverse_in_this_space='not qualified; no inheritance from another gauge/space'),
        cost=dict(H7_parent_dat_lower_seconds=13627.054710610071,H7_raw_parent_seconds=12393.272463684902,
            H7_parent_tail_solve_and_refinement_seconds=14.232067284057848,
            cached_consumer_increment_seconds=sum(journal.timings.values()),
            cached_consumer_increment_note='stage timings may be nested; authoritative unique wall in supervision ledger, do not add nesting',
            necessary_fresh_cold_N1='unknown; parent preparation plus new consumption not free',
            inherited_research_known_lower_seconds=scope.plan_record()['historical_loaded_known_lower_seconds']),
        next_pilot='If same-p h is small but cross-p remains large: one independent discrete-stability/field-representation check at the saved p6/p7 pair; do not continue the same hp/M loop',
        no_new_solver_or_target_PDE=True)
    write_json(folder/'target_gap_and_cost.json',r);return r
