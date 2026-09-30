"""V17 evidence counterexamples: labels cannot manufacture qualification."""
import copy
import math

from src.io.resumable_trace_evidence_check import caps, field_gate, resume_pair


def complete_field():
    audit={k:0. for k in ('schur_relative','native_relative','augmented_relative',
            'original_total_augmented_relative','port_full_rhs_relative','port_operation_relative',
            'recovery_relative','schur_original_identity_operation_relative','slave_storage_max',
            'independent_DOLFINx_total_native_relative')}
    fields={k:0. for k in ('full_FE_L2_relative','full_FE_scaled_curl_relative',
            'scattered_FE_L2_relative','scattered_scaled_curl_relative','selected_E_relative','selected_H_relative')}
    return dict(status='SAME_DISCRETE_QUALIFIED',audit=audit,fields=fields,
            comparison=dict(ordered_complex_ports_relative=0.,max_channel_power_difference=0.,
                energy_closure_absolute=0.,power_absolute_differences={k:0. for k in ('R_total','T_total','A_balance','A_volume')}),
            ordered_complex_total_ports=[dict(real=1.,imag=0.) for _ in range(40)],
            ordered_complex_scattered_ports=[dict(real=1.,imag=0.) for _ in range(40)])


def test_false_success_fields_and_identity_remain_failures():
    row=complete_field();assert field_gate(row,True)
    for container,key,value in ((row['fields'],'scattered_FE_L2_relative',.01),
            (row['audit'],'schur_original_identity_operation_relative',1e-8),
            (row['audit'],'schur_relative',.001),
            (row['comparison'],'max_channel_power_difference',.001),
            (row['fields'],'selected_H_relative',math.nan)):
        old=container[key];container[key]=value
        assert not field_gate(row,True)
        container[key]=old
    row['ordered_complex_total_ports'].pop();assert not field_gate(row,True)
    assert not field_gate(complete_field(),False)


def test_resume_boolean_does_not_override_a_changed_GK_vector():
    image=dict(rank=3098,columns=3098,relative_rank_threshold=1e-12,
            Q_orthogonality=0.,U_orthogonality=0.,A_QR_reconstruction=0.,
            original_pairings=[dict(operation_relative=0.)],bar_checks=dict(Hhat_condition=100.,
            Hhat_solve_operation_relative=[0.],single_SH_vs_legacy_two_SH=[dict(operation_relative=0.)]))
    projected=dict(dot_tests=[dict(operation_relative=0.)],idempotence=dict(Pt=dict(operation_relative=0.)),
            annihilation=dict(Q=0.),original_residual_identity_relative=0.)
    pair=dict(qualified=True,short_steps=32,independent_reader=True,production_progress_unchanged=True,
            reference_read=False,full_GK_differences=dict(x=dict(operation_relative=0.),u=dict(operation_relative=0.)),
            z=dict(operation_relative=0.),original_action=dict(operation_relative=0.))
    witness=dict(known_z_relative=0.,manufactured_residual_relative=0.,homogeneous_recovery_operation_relative=0.,
            projected_identity=dict(operation_relative=0.),physical_rhs_unchanged=True,
            iterative_manufactured_solve=False,reference_read=False)
    row=dict(original_image=image,operator_checks=projected,resume_pair=pair,algebra_witness=witness)
    assert resume_pair(row)
    pair['full_GK_differences']['u']['operation_relative']=1e-8
    assert not resume_pair(row)


def test_lower_labels_do_not_reset_charged_resume_caps():
    library=dict(wall_seconds=9000.,actions_upper=24000,new_updates=8192,reentries=2,correction_restarts=1)
    ledger=dict(closed=True,actions_upper=56000,audits_upper=420,new_A_columns=6196,image_QR=2,
            field_states=12,reentries=3,cooldown_seconds=1800,repairs=[1,2,3,4],routes=dict(GPOLY=copy.copy(library),GNN=copy.copy(library)))
    budget=dict(uniform_route_wall_seconds=9000)
    assert caps(ledger,budget)
    for container,key in ((ledger,'actions_upper'),(ledger['routes']['GPOLY'],'new_updates'),
            (ledger['routes']['GNN'],'wall_seconds'),(ledger,'field_states'),(ledger,'reentries')):
        old=container[key];container[key]+=1;assert not caps(ledger,budget);container[key]=old
    ledger['active']=dict(actions_lower=0);assert not caps(ledger,budget)
