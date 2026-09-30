"""V12 independent compact Gate derivation from raw numbers, not saved labels."""

from __future__ import annotations

import math

from src.io.stable_head_varpro_check import same_discrete_gate


def finite(value):
    return isinstance(value, (int, float)) and math.isfinite(value)


def roundoff_gate(round_record):
    if round_record.get("T1_original_actions", 10**9)>32 or round_record.get("T1_wall_seconds", 10**9)>600:
        return False
    if set(round_record.get("rows",{}))!={"M2","physical"}:
        return False
    return all(finite(row["residual_norms"]["vector_reassembly"])
               and row["residual_norms"]["vector_reassembly"]<=1e-10
               and finite(row["homogeneous_recovery_N_vs_P"])
               and row["homogeneous_recovery_N_vs_P"]<=1e-10
               for row in round_record["rows"].values())


def fixed_head_fd_gate(fd, delta_eval):
    if not finite(delta_eval) or delta_eval<0:
        return False
    rows=fd.get("directions",[])
    if len(rows)!=3 or fd.get("derivative_kind")!="FIXED_HEAD_PARTIAL_GRADIENT":
        return False
    if [row["direction"] for row in rows[:2]]!=["421201","421202"]:
        return False
    if fd.get("perturbation_points",10**9)>30 or not fd.get("fixed_gamma_all_points"):
        return False
    for row in rows:
        a=row["analytic"]
        if not finite(a):
            return False
        estimates=row.get("estimates",[])
        if not 2<=len(estimates)<=5:
            return False
        stable=False
        for left,right in zip(estimates,estimates[1:]):
            if not all(finite(x.get(k)) for x in (left,right)
                       for k in ("h","slope","signal_over_delta")):
                return False
            if right["h"]!=left["h"]/10:
                return False
            lo,hi=left["slope"],right["slope"]
            err_lo=abs(lo-a)/max(abs(lo),abs(a),1e-12)
            err_hi=abs(hi-a)/max(abs(hi),abs(a),1e-12)
            trend=abs(lo-hi)/max(abs(lo),abs(hi),1e-12)
            if (err_lo<=1e-5 and err_hi<=1e-5 and trend<=1e-5
                    and left["signal_over_delta"]>=10
                    and right["signal_over_delta"]>=10):
                stable=True
        if abs(a)<=1e-10:
            stable=stable or any(abs(x["slope"]-a)<=1e-10 and
                                 x["signal_over_delta"]>=10 for x in estimates)
        if not stable:
            return False
    return True


def state_identity(row):
    state=row["state"]
    point=row["point"]
    return (state["gamma_sha256"]==point["gamma_hash"]
            and state["hidden_sha256"]==point["hidden_hash"]
            and state["z_sha256"] and state["port_sha256"]
            and row["gamma_frozen_within_block"])


def accepted_progress_step(row, prior_loss, expected_gamma_hash):
    """A saved success flag never overrides the actual Armijo and port data."""
    if row["gamma_sha256"]!=expected_gamma_hash or not row["gamma_frozen"]:
        return False
    if not finite(row["loss"]) or not finite(prior_loss) or not finite(row["delta_eval"]):
        return False
    if not (0<=row["backtracks"]<8 and row["alpha"]>0):
        return False
    margin=max(1e-12,20*row["delta_eval"])
    return (row["loss"]<=prior_loss-margin
            and row["port"]<=1e-6 and row["actual_loss_accepted"]
            and row["derivative_kind"]=="FIXED_HEAD_PARTIAL_GRADIENT")


def verified_field_gate(row):
    if not same_discrete_gate(row):
        return False
    for key in ("ordered_complex_total_ports","ordered_complex_scattered_ports"):
        if len(row[key])!=40:
            return False
        for value in row[key]:
            if not isinstance(value,dict) or not finite(value.get("real")) or not finite(value.get("imag")):
                return False
    return True


def check_v12(round_record, descent, verify):
    round_ok=roundoff_gate(round_record)
    delta=descent["repeated_loss"]["delta_eval"]
    fd=descent.get("finite_difference") or {}
    gradient_ok=fixed_head_fd_gate(fd,delta)
    states_ok=all(state_identity(row) for row in descent["states"])
    field={name:verified_field_gate(row) for name,row in verify["rows"].items()}
    mismatches=[]
    if round_ok!=(round_record["status"]=="COMPLETE"):
        mismatches.append("ROUND.status")
    if gradient_ok!=descent.get("T2_gradient_qualified",False):
        mismatches.append("DESCENT.T2_gradient_qualified")
    if not states_ok:
        mismatches.append("DESCENT.state_identity")
    if not gradient_ok and descent.get("accepted_hidden_updates",0)>0:
        mismatches.append("DESCENT.unqualified_gradient_hidden_updates")
    for name,passed in field.items():
        if passed!=(verify["rows"][name]["status"]=="SAME_DISCRETE_QUALIFIED"):
            mismatches.append("VERIFY."+name+".status")
    counts=descent["budget_counts"]
    limits=dict(loss_forward=900,VJP=240,PA_builds=4,thin_head_resolves=8,
                original_audits=100)
    if any(counts[key]>bound for key,bound in limits.items()):
        mismatches.append("DESCENT.budget")
    if verify["all_batch_equivalent_actions"]>15000:
        mismatches.append("VERIFY.action_budget")
    if descent.get("function_only_poll"):
        poll=descent["function_only_poll"]
        if poll["trial_count"]!=8 or len(poll["trials"])!=8:
            mismatches.append("DESCENT.F_trial_inventory")
        if poll["accepted"]:
            improved=poll["repeated_loss"]<=descent["initial_loss"]-poll["margin"]
            improved &= poll["native_best"]<=1.05*poll["native_before"]
            if not improved:
                mismatches.append("DESCENT.F_false_acceptance")
    return dict(status="PASS" if not mismatches else "RAW_STATUS_MISMATCH",
                mismatches=mismatches,roundoff_identity=round_ok,
                fixed_head_gradient_qualified=gradient_ok,state_identity=bool(states_ok),
                same_discrete=field,formal_micro_qualification=bool(states_ok and all(field.values())),
                saved_statuses_not_trusted=True,
                reference_only_after_solver_frozen=verify["reference_only_after_solver_frozen"])
