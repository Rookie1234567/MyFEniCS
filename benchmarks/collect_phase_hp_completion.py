"""V53 thin binding of the independent saved-field checker and cost collector."""
import sys
from src.solvers import phase_hp_completion_scope as scope
from benchmarks.collect_phase_notch_hp import collect,documents


if __name__=='__main__':
    if sys.argv[1:]==['--docs']:
        documents(scope=scope,review_name='review_report_v51.md',response_name='response_v53.md',outcome_name='phase_hp_completion_v53.md')
    elif sys.argv[1:]==['--modal']:
        from benchmarks.collect_phase_explicit_accuracy import modal_recalculation
        roles=tuple(r for r in scope.SOLVES if (scope.ARTIFACT/(r+'.json')).exists() and scope.stage(r).get('equation_pass'))
        modal_recalculation(scope=scope,role_names=roles)
    elif not sys.argv[1:]:collect(scope=scope)
    else:raise ValueError('V53 collector arguments')
