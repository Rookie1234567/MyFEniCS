"""Adversarial claimed-success records must not bypass original gates."""
from src.io.augmented_trace_evidence_check import equation, image, projected


def test_claimed_success_with_wrong_port_or_recovery_is_rejected():
    a=dict.fromkeys(('schur_relative','native_relative','augmented_relative',
        'original_total_augmented_relative','port_full_rhs_relative','port_operation_relative',
        'recovery_relative','schur_original_identity_operation_relative','slave_storage_max'),0.)
    a['status']='ORIGINAL_EQUATION_PASS'
    assert equation(a)
    for key,value in [('port_full_rhs_relative',1e-4),('recovery_relative',1e-8),
                      ('slave_storage_max',1e-20),('native_relative',float('nan'))]:
        wrong=dict(a);wrong[key]=value
        assert not equation(wrong)


def test_initial_large_state_stress_failure_cannot_be_relabelled_by_status():
    c=dict(dot_tests=[dict(operation_relative=1e-17)],idempotence={'Pt':dict(operation_relative=1e-16)},
        annihilation={'Pt':1e-16,'Pr':1e-16},original_residual_identity_relative=1.1125765242162454e-7,
        qualified=True,residual_witness_rule='normalized')
    assert not projected(c)
    c['original_residual_identity_relative']=1.0282827753123975e-12
    assert projected(c)


def test_fixed_library_rank_threshold_and_real_action_pairing_are_required():
    a=dict(rank=3098,columns=3098,relative_rank_threshold=1e-12,Q_orthogonality=1e-15,
        U_orthogonality=1e-15,A_QR_reconstruction=1e-15,original_pairings=[dict(operation_relative=1e-15)],
        bar_checks=dict(Hhat_condition=13284.,Hhat_solve_operation_relative=[1e-20],
                        single_SH_vs_legacy_two_SH=[dict(operation_relative=1e-17)]))
    assert image(a)
    for key,value in [('rank',3097),('relative_rank_threshold',1e-8),('A_QR_reconstruction',1e-7)]:
        wrong=dict(a);wrong[key]=value
        assert not image(wrong)
    wrong=dict(a);wrong['original_pairings']=[dict(operation_relative=1e-7)]
    assert not image(wrong)
