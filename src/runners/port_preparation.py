"""Component-only adapter reusing the established admission and subreaper.

Each phase has a new output directory. Completed immutable phases are consumed
through a hash-bound pointer; a failed phase is not a completed checkpoint.
No V35 cross-launch numerical continuation is claimed.
"""

import fcntl
import hashlib
import json
import os
import subprocess
import sys
import time
import traceback
from pathlib import Path

from benchmarks.subreaper_watchdog import supervise
from src.io.port_preparation import ARTIFACT, PLAN, ROOT, read_stage
from src.runners.diagnostic_storage import inventory_paths
from src.runners.task042_shared import (
    SharedHealth,
    _json_metadata,
    audit,
    shared_envelope,
    write_json,
)
from src.solvers.port_preparation_window import implementation_hashes, window


def storage_limits(namespace):
    if namespace in ("v50", "v51", "v52", "v53", "v54", "v55", "v56", "v57", "v58", "v59", "v60", "v61", "v62", "v63", "v64", "v65", "v66", "v67"):
        from src.solvers.phase_explicit_accuracy_scope import plan_record
        if namespace == "v50":
            from src.solvers.scattering_accuracy_scope import plan_record
        elif namespace == "v52":
            from src.solvers.phase_notch_hp_scope import plan_record
        elif namespace == "v53":
            from src.solvers.phase_hp_completion_scope import plan_record
        elif namespace == "v54":
            from src.solvers.phase_p_order_dtn_scope import plan_record
        elif namespace == "v67":
            from src.solvers.local_p_mode_scope import plan_record
        elif namespace == "v66":
            from src.solvers.frozen_local_h_scope import plan_record
        elif namespace == "v65":
            from src.solvers.p6_completion_scope import plan_record
        elif namespace == "v64":
            from src.solvers.local_h_pilot_scope import plan_record
        elif namespace == "v63":
            from src.solvers.fine_tetra_scope import plan_record
        elif namespace == "v62":
            from src.solvers.independent_tetra_scope import plan_record
        elif namespace == "v61":
            from src.solvers.face_trace_scope import plan_record
        elif namespace == "v60":
            from src.solvers.local_subcell_scope import plan_record
        elif namespace == "v59":
            from src.solvers.trace_interior_scope import plan_record
        elif namespace == "v58":
            from src.solvers.phase_deployment_scope import plan_record
        elif namespace == "v57":
            from src.solvers.common_weak_phase_scope import plan_record
        elif namespace == "v56":
            from src.solvers.phase_saved_closure_scope import plan_record
        elif namespace == "v55":
            from src.solvers.phase_spatial_resolution_scope import plan_record
        p = plan_record()
        return {k:p[k] for k in ("new_storage_bytes", "task_storage_bytes", "free_bytes", "evidence_reserve_bytes")}
    if namespace == "v49":
        from src.solvers.scattering_anchor_scope import plan_record
        p = plan_record()
        return {k:p[k] for k in ("new_storage_bytes", "task_storage_bytes", "free_bytes", "evidence_reserve_bytes")}
    if namespace == "v48":
        from src.solvers.vector_storage_scope import plan_record

        plan = plan_record()
        return {k: plan[k] for k in ("new_storage_bytes", "task_storage_bytes", "free_bytes", "evidence_reserve_bytes")}
    if namespace == "v47":
        from src.solvers.trace_selection_scope import plan_record

        plan = plan_record()
        return {k: plan[k] for k in ("new_storage_bytes", "task_storage_bytes", "free_bytes", "evidence_reserve_bytes")}
    if namespace == "v46":
        from src.solvers.neural_decision_scope import plan_record

        plan = plan_record()
        return {
            k: plan[k]
            for k in (
                "new_storage_bytes",
                "task_storage_bytes",
                "free_bytes",
                "evidence_reserve_bytes",
            )
        }
    if namespace == "v45":
        from src.solvers.full_moment_scope import plan_record

        plan = plan_record()
        return {
            k: plan[k]
            for k in (
                "new_storage_bytes",
                "task_storage_bytes",
                "free_bytes",
                "evidence_reserve_bytes",
            )
        }
    return {
        "new_storage_bytes": (
            (4 if namespace in ("v43", "v44") else 40) * 2**30
            if namespace in ("v42", "v43", "v44")
            else (2048 if namespace in ("v39", "v40", "v41") else 512) * 2**20
        ),
        "task_storage_bytes": (
            64 if namespace == "v42" else 24 if namespace in ("v43", "v44") else 20
        )
        * 2**30,
        "free_bytes": (100 if namespace == "v42" else 50) * 2**30,
        "evidence_reserve_bytes": 0,
    }


class PreparationHealth:
    def __init__(self, folder, neighbors, namespace, *, limits=None, baseline_storage=None):
        self.limits = storage_limits(namespace) if limits is None else limits
        if namespace in ("v45", "v46", "v47", "v48", "v49", "v50", "v51", "v52", "v53", "v54", "v55", "v56", "v57", "v58", "v59", "v60", "v61", "v62", "v63", "v64", "v65", "v66", "v67") and self.limits != storage_limits(namespace):
            raise ValueError("live guard must use the identical frozen plan")
        self.namespace, self.folder = namespace, folder
        self.baseline_storage = baseline_storage
        if namespace in ('v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56', 'v57', 'v58', 'v59', 'v60', 'v61', 'v62', 'v63', 'v64', 'v65', 'v66', 'v67') and baseline_storage is None:
            raise ValueError('V50 exact prelaunch full-scope inventory required')
        self.shared = SharedHealth(folder, neighbors, artifact_limit_bytes=self.limits["task_storage_bytes"],
            artifact_bytes_provider=self.live_task_bytes if namespace in ('v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56', 'v57', 'v58', 'v59', 'v60', 'v61', 'v62', 'v63', 'v64', 'v65', 'v66', 'v67') else None)

    def own_bytes(self):
        own=[ROOT / ('tmp/task042/'+self.namespace),ROOT / ('benchmarks/artifacts/task042/'+self.namespace)]
        own.extend((ROOT/'results/task042').glob('task042_'+self.namespace+'_*'))
        return inventory_paths(own,ROOT)['bytes']

    def live_task_bytes(self):
        # Sole-writer lock plus frozen immutable historical roots: count them
        # exactly at launch, then add only the changing V50 namespace. No old
        # file is removed or treated as free. Full total is rechecked at every
        # stage boundary and final settlement.
        return self.baseline_storage['task_artifact_bytes']-self.baseline_storage['new_bytes']+self.own_bytes()

    def __call__(self):
        row = dict(self.shared())
        if self.namespace in ("v50", "v51", "v52", "v53", "v54", "v55", "v56", "v57", "v58", "v59", "v60", "v61", "v62", "v63", "v64", "v65", "v66", "v67"):
            row['artifact_bytes']=self.live_task_bytes()
            row['storage_scope']=f'exact immutable historical baseline + current sole-writer {self.namespace.upper()}; full inventory each stage boundary'
        if self.namespace in (
            "v37",
            "v38",
            "v39",
            "v40",
            "v41",
            "v42",
            "v43",
            "v44",
            "v45",
            "v46",
            "v47",
            "v48",
            "v49",
            "v50",
            "v51",
            "v52",
            "v53",
            "v54",
            "v55",
            "v56",
            "v57",
            "v58",
            "v59",
            "v60",
            "v61",
            "v62",
            "v63",
            "v64",
            "v65", "v66", "v67",
        ):
            own = [
                ROOT / ("tmp/task042/" + self.namespace),
                ROOT / ("benchmarks/artifacts/task042/" + self.namespace),
            ]
            own.extend(
                (ROOT / "results/task042").glob("task042_" + self.namespace + "_*")
            )
            size = inventory_paths(own, ROOT)["bytes"]
            row["new_preparation_bytes"] = size
            limit = self.limits["new_storage_bytes"]
            reserve = self.limits["evidence_reserve_bytes"]
            own_reserve = 0 if self.namespace == "v46" else reserve
            if (
                size + own_reserve > limit
                or row["artifact_bytes"] + reserve > self.limits["task_storage_bytes"]
                or row["disk_free_bytes"] < self.limits["free_bytes"] + reserve
            ):
                row["stop_reason"] = "RESOURCE_CONTROLLED_STOP"
            if self.namespace in ("v39", "v40"):
                jit = ROOT / ("tmp/task042/" + self.namespace + "/formal/xdg/fenics")
                jit_bytes = inventory_paths([jit], ROOT)["bytes"]
                row["new_native_jit_bytes"] = jit_bytes
                if jit_bytes > 1536 * 2**20:
                    row["stop_reason"] = "RESOURCE_CONTROLLED_STOP"
        return row


FE_ROLES = (
    "COMPONENT",
    "PATCH",
    "CAPACITY",
    "BRIDGE",
    "LAYOUT",
    "ORACLE",
    "ADAPTER",
    "COUPLED",
)


def scoped_tetra_memory(namespace,role):
    modules={'v63':'fine_tetra_scope','v64':'local_h_pilot_scope','v65':'p6_completion_scope','v66':'frozen_local_h_scope','v67':'local_p_mode_scope'}
    return __import__('src.solvers.'+modules[namespace],fromlist=['memory_budget']).memory_budget(role)


def preparation_memory_envelope(namespace, role=None):
    env=shared_envelope()
    if namespace in ('v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56', 'v57', 'v58', 'v59', 'v60', 'v61', 'v62', 'v63', 'v64', 'v65', 'v66', 'v67'):
        # Preserve host/growth reserves. V50 alone has an explicit24GiB
        # sampled hard cap; ordinary namespaces retain their original gate.
        env['launch_cap_bytes']=min(24*2**30,env['effective_available_bytes']-env['reserve_bytes'])
        env['planning_cap_bytes']=16*2**30
    if namespace in ('v53','v54','v55','v56', 'v57', 'v58', 'v59', 'v60', 'v61', 'v62', 'v63', 'v64', 'v65', 'v66', 'v67'):
        if namespace=='v67':
            from src.solvers.local_p_mode_scope import plan_record
        elif namespace=='v66':
            from src.solvers.frozen_local_h_scope import plan_record
        elif namespace=='v65':
            from src.solvers.p6_completion_scope import plan_record
        elif namespace=='v64':
            from src.solvers.local_h_pilot_scope import plan_record
        elif namespace=='v63':
            from src.solvers.fine_tetra_scope import plan_record
        elif namespace=='v62':
            from src.solvers.independent_tetra_scope import plan_record
        elif namespace=='v61':
            from src.solvers.face_trace_scope import plan_record
        elif namespace=='v60':
            from src.solvers.local_subcell_scope import plan_record
        elif namespace=='v59':
            from src.solvers.trace_interior_scope import plan_record
        elif namespace=='v58':
            from src.solvers.phase_deployment_scope import plan_record
        elif namespace=='v57':
            from src.solvers.common_weak_phase_scope import plan_record
        elif namespace=='v56':
            from src.solvers.phase_saved_closure_scope import plan_record
        elif namespace=='v55':
            from src.solvers.phase_spatial_resolution_scope import plan_record
        elif namespace=='v54':
            from src.solvers.phase_p_order_dtn_scope import plan_record
        else:
            from src.solvers.phase_hp_completion_scope import plan_record
        budget=plan_record()['memory_budget']
        if namespace in ('v63','v64', 'v65', 'v66', 'v67'):
            memory_budget=lambda r:scoped_tetra_memory(namespace,r)
            budget=memory_budget(role)
        env['neighbor_growth_allowance_bytes']=budget['neighbor_growth_gib']*2**30
        env['reserve_bytes']=env['system_reserve_bytes']+env['neighbor_growth_allowance_bytes']
        env['launch_cap_bytes']=min(budget['sampled_stop_gib']*2**30,env['effective_available_bytes']-env['reserve_bytes'])
        env['planning_cap_bytes']=budget['planning_gib']*2**30
    return env


def context(namespace):
    if namespace in ("v50", "v51", "v52", "v53", "v54", "v55", "v56", "v57", "v58", "v59", "v60", "v61", "v62", "v63", "v64", "v65", "v66", "v67"):
        from src.solvers import phase_explicit_accuracy_scope as scope
        if namespace == "v50":
            from src.solvers import scattering_accuracy_scope as scope
        elif namespace == "v52":
            from src.solvers import phase_notch_hp_scope as scope
        elif namespace == "v53":
            from src.solvers import phase_hp_completion_scope as scope
        elif namespace == "v54":
            from src.solvers import phase_p_order_dtn_scope as scope
        elif namespace == "v67":
            from src.solvers import local_p_mode_scope as scope
        elif namespace == "v66":
            from src.solvers import frozen_local_h_scope as scope
        elif namespace == "v65":
            from src.solvers import p6_completion_scope as scope
        elif namespace == "v64":
            from src.solvers import local_h_pilot_scope as scope
        elif namespace == "v63":
            from src.solvers import fine_tetra_scope as scope
        elif namespace == "v62":
            from src.solvers import independent_tetra_scope as scope
        elif namespace == "v61":
            from src.solvers import face_trace_scope as scope
        elif namespace == "v60":
            from src.solvers import local_subcell_scope as scope
        elif namespace == "v59":
            from src.solvers import trace_interior_scope as scope
        elif namespace == "v58":
            from src.solvers import phase_deployment_scope as scope
        elif namespace == "v57":
            from src.solvers import common_weak_phase_scope as scope
        elif namespace == "v56":
            from src.solvers import phase_saved_closure_scope as scope
        elif namespace == "v55":
            from src.solvers import phase_spatial_resolution_scope as scope
        return scope.window, scope.ARTIFACT, scope.PLAN, scope.implementation_hashes
    if namespace == "v49":
        from src.solvers import scattering_anchor_scope as scope
        return scope.window, scope.ARTIFACT, scope.PLAN, scope.implementation_hashes
    if namespace == "v48":
        from src.solvers import vector_storage_scope as scope

        return scope.window, scope.ARTIFACT, scope.PLAN, scope.implementation_hashes
    if namespace == "v47":
        from src.solvers import trace_selection_scope as scope

        return scope.window, scope.ARTIFACT, scope.PLAN, scope.implementation_hashes
    if namespace == "v46":
        from src.solvers import neural_decision_scope as scope

        return scope.window, scope.ARTIFACT, scope.PLAN, scope.implementation_hashes
    if namespace == "v45":
        from src.solvers import full_moment_scope as scope

        return scope.window, scope.ARTIFACT, scope.PLAN, scope.implementation_hashes
    if namespace == "v44":
        from src.solvers import neighborhood_late_error_scope as scope

        return scope.window, scope.ARTIFACT, scope.PLAN, scope.implementation_hashes
    if namespace in ("v43", "v44", "v45"):
        from src.solvers import neighborhood_residual_scope as scope

        return scope.window, scope.ARTIFACT, scope.PLAN, scope.implementation_hashes
    if namespace == "v42":
        from src.solvers import distributed_volume_scope as scope

        return scope.window, scope.ARTIFACT, scope.PLAN, scope.implementation_hashes
    if namespace == "v41":
        from src.solvers import native_entity_scope as scope

        return scope.window, scope.ARTIFACT, scope.PLAN, scope.implementation_hashes
    if namespace == "v40":
        from src.solvers import native_recovery_scope as scope

        return scope.window, scope.ARTIFACT, scope.PLAN, scope.implementation_hashes
    if namespace == "v39":
        from src.solvers import native_integration_scope as scope

        return scope.window, scope.ARTIFACT, scope.PLAN, scope.implementation_hashes
    if namespace == "v38":
        from src.solvers import boundary_structure_scope as scope

        return scope.window, scope.ARTIFACT, scope.PLAN, scope.implementation_hashes
    if namespace == "v37":
        from src.solvers import boundary_witness_scope as scope

        return scope.window, scope.ARTIFACT, scope.PLAN, scope.implementation_hashes
    if namespace != "v36":
        raise ValueError("explicit preparation namespace")
    return window, ARTIFACT, PLAN, implementation_hashes


def storage(reserve=0, *, namespace="v36", cleanup=False):
    _, artifact, _, _ = context(namespace)
    own = [ROOT / ("tmp/task042/" + namespace), artifact]
    own.extend((ROOT / "results/task042").glob("task042_" + namespace + "_*"))
    new = inventory_paths(own, ROOT)["bytes"]
    roots = [ROOT / "benchmarks/artifacts/task042"]
    if namespace in ("v50", "v51", "v52", "v53", "v54", "v55", "v56", "v57", "v58", "v59", "v60", "v61", "v62", "v63", "v64", "v65", "v66", "v67"):
        roots += [ROOT / "tmp/task042", ROOT / "results/task042", ROOT / "docs/task042_neural_coarse_inverse"]
    total = inventory_paths(roots, ROOT)["bytes"]
    free = __import__("shutil").disk_usage(ROOT).free
    limits = storage_limits(namespace)
    limit, task_limit, free_limit = (
        limits[k] for k in ("new_storage_bytes", "task_storage_bytes", "free_bytes")
    )
    if namespace in ("v45", "v46", "v47", "v48", "v49", "v50", "v51", "v52", "v53", "v54", "v55", "v56", "v57", "v58", "v59", "v60", "v61", "v62", "v63", "v64", "v65", "v66", "v67"):
        reserve = max(reserve, limits["evidence_reserve_bytes"])
    new_reserve = 0 if namespace == "v46" else reserve
    if (
        (new + new_reserve > limit and not cleanup)
        or total + reserve > task_limit
        or free < free_limit + reserve
    ):
        raise MemoryError(f"{namespace} frozen new/task/free storage reserve")
    return {
        "new_bytes": new,
        "task_artifact_bytes": total,
        "free_bytes": free,
        "reserve_bytes": reserve,
    }


def require_component_gate(*, namespace="v36"):
    window, _, _, implementation_hashes = context(namespace)
    q = json.loads((window.TMP / "qualification.json").read_text())
    if q["status"] != "PASSED" or q["implementation_hashes"] != implementation_hashes():
        raise ValueError("V36 final implementation focused qualification missing")
    receipt = Path(q["receipt_path"]).resolve()
    if (
        not receipt.is_relative_to(window.TMP)
        or hashlib.sha256(receipt.read_bytes()).hexdigest() != q["receipt_sha256"]
    ):
        raise ValueError("V36 qualification receipt hash")
    result = json.loads((receipt.parent / "summary.json").read_text())
    if (
        result["classification"] != "COMPLETED"
        or result["leader_exit_code"] != 0
        or not result["descendants_cleared"]
    ):
        raise ValueError("V36 qualification supervision failed")
    return q


def diagnosed_phase_repair(namespace, role, previous, plan):
    if namespace=='v62' and previous.get('arrays'):
        from src.solvers.independent_tetra_scope import window
        path=window.TMP/(role+'_post_resume.json')
        if path.exists():
            item=json.loads(path.read_text());old=item.get('completed_outputs',{})
            producer=Path(old.get('path','/not_present'))
            return (item.get('root_cause')=='port_audit_denominator' and item.get('audit_recompute') is True
                and producer.is_file() and hashlib.sha256(producer.read_bytes()).hexdigest()==old.get('sha256')
                and json.loads(producer.read_text())['arrays']['sha256']==previous['arrays']['sha256'])
    if namespace=='v57' and role=='K' and previous.get('status')=='COMPLETED' and not previous.get('p6_pass'):
        from src.solvers.common_weak_phase_scope import window
        fix=window.TMP/'K_checker_resume.json'
        if fix.exists():
            item=json.loads(fix.read_text());p=Path(item['path'])
            return (item.get('root_cause')=='local_rhs_near_zero_operation_scale' and p.is_file()
                and hashlib.sha256(p.read_bytes()).hexdigest()==item['sha256']
                and json.loads(p.read_text()).get('source_sha')==previous.get('source_sha'))
    if namespace=='v54' and role=='D':
        fix=plan.get('diagnosed_p_order_scale_recheck',{});path=Path(fix.get('evidence_path','/not_present'))
        return (previous.get('classification')=='CROSS_P_CONSISTENCY_NOT_ESTABLISHED' and previous.get('same_p_paths_trusted') is True
            and fix.get('source_sha')==previous.get('source_sha') and path.is_file()
            and hashlib.sha256(path.read_bytes()).hexdigest()==fix.get('evidence_sha256')
            and fix.get('root_cause')=='operation_result_denominator')
    if namespace in ('v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56', 'v57', 'v58', 'v59', 'v60', 'v61', 'v62', 'v63', 'v64', 'v65', 'v66', 'v67') and role == 'BOUNDARY':
        fix=plan.get('diagnosed_boundary_inventory_repair',{})
        path=Path(fix.get('evidence_path','/not_present'))
        return (fix.get('source_sha')==previous.get('source_sha') and path.is_file()
            and hashlib.sha256(path.read_bytes()).hexdigest()==fix.get('evidence_sha256')
            and fix.get('root_cause')=='downstream_sparse_cutoff')
    if namespace in ("v43", "v44", "v45", "v47", "v49", "v50", "v51", "v52", "v53", "v54", "v55", "v56", "v57", "v58", "v59", "v60", "v61", "v62", "v63", "v64", "v65", "v66", "v67"):
        return previous.get("status") == "FAILED"
    if namespace == "v42":
        # A failed attempt never counts as a published successful checkpoint.
        # Retain its result and source; numerical stages reuse only committed
        # immutable class packets with the live dependency gate.
        return previous.get("status") == "FAILED"
    if namespace in ("v39", "v40"):
        return previous["status"] in (
            "NATIVE_ADAPTER_NOT_QUALIFIED",
            "COUPLED_INTERFACE_NOT_QUALIFIED",
            "NATIVE_RECOVERY_NOT_QUALIFIED",
        )
    if namespace == "v41" and role == "ROUTING":
        repair = plan.get("diagnosed_routing_replay", {})
        return (
            previous["status"] == "TARGET_BOUNDARY_OWNER_ROUTING_NOT_QUALIFIED"
            and repair.get("failed_source") == previous["source_sha"]
            and repair.get("root_cause") == "frozen_adjoint_wrong_input"
            and repair.get("evidence_path") is not None
            and hashlib.sha256(Path(repair["evidence_path"]).read_bytes()).hexdigest()
            == repair.get("evidence_sha256")
        )
    return False


def launch(
    specification=None, *, command=None, phase=None, attempt=None, namespace="v36"
):
    if specification is not None:
        namespace = specification.derived.get("preparation_scope", "v36")
        if (
            namespace in ("v43", "v44", "v45", "v47", "v49", "v50", "v51", "v52", "v53", "v54", "v55", "v56", "v57", "v58", "v59", "v60", "v61", "v62", "v63", "v64", "v65", "v66", "v67")
            and os.environ.get("TASK042_ENV_MODE")
            != specification.derived["environment_mode"]
        ):
            raise RuntimeError("V43 per-stage qualified FE/ML environment mismatch")
    window, ARTIFACT, PLAN, implementation_hashes = context(namespace)
    started = time.monotonic()
    window.require_ready()
    role = phase if specification is None else specification.derived["stage"]
    if namespace in ("v48", "v49", "v50", "v51", "v52", "v53", "v54", "v55", "v56", "v57", "v58", "v59", "v60", "v61", "v62", "v63", "v64", "v65", "v66", "v67") and subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True):
        raise RuntimeError("V48 all producers/checkers/analysis require committed clean source")
    is_fe = role in FE_ROLES or (namespace == "v40" and specification is not None)
    if namespace == "v41":
        from src.solvers.native_entity_scope import NATIVE

        is_fe = role in NATIVE
    if namespace == "v42":
        from src.solvers.distributed_volume_scope import NATIVE

        is_fe = role in NATIVE
    if namespace in ("v43", "v44", "v45", "v47", "v49", "v50", "v51", "v52", "v53", "v54", "v55", "v56", "v57", "v58", "v59", "v60", "v61", "v62", "v63", "v64", "v65", "v66", "v67"):
        is_fe = specification is not None
    if namespace == "v63" and role in ("compare_A", "compare_gate"):
        # These saved consumers rebuild only mesh/space and evaluate fields.
        # They use the default FE profile, never B's larger reference budget.
        is_fe = True
    if is_fe or (
        namespace in ("v41", "v42", "v43", "v44", "v45", "v47", "v49", "v50", "v51", "v52", "v53", "v54", "v55", "v56", "v57", "v58", "v59", "v60", "v61", "v62", "v63", "v64", "v65", "v66", "v67") and specification is not None
    ):
        require_component_gate(namespace=namespace)
        if namespace == "v36":
            read_stage("INVENTORY")
    if specification is not None:
        if ARTIFACT.joinpath(role + ".json").exists():
            pointer = ARTIFACT.joinpath(role + ".json")
            previous = json.loads(pointer.read_text())
            prior_result = json.loads(
                __import__("pathlib").Path(previous["path"]).read_text()
            )
            if not diagnosed_phase_repair(
                namespace, role, prior_result, json.loads(PLAN.read_text())
            ):
                raise ValueError(
                    "completed qualified phase already published; reuse pointer, no restart"
                )
            # This allows only a diagnosed repair of a nonqualified phase.
            # Its result/arrays/source remain immutable and the superseded
            # pointer is saved beside the new run before publication.
        status = subprocess.check_output(
            ["git", "status", "--porcelain"], cwd=ROOT, text=True
        )
        if status:
            raise RuntimeError("V36 formal component/preparation requires clean source")
    limits = storage_limits(namespace)
    if (
        specification is not None
        and namespace in ("v45", "v47", "v49", "v50", "v51", "v52", "v53", "v54", "v55", "v56", "v57", "v58", "v59", "v60", "v61", "v62", "v63", "v64", "v65", "v66", "v67")
        and dict(specification.derived["storage_limits"]) != limits
    ):
        raise ValueError("V45 resolved/live budget mismatch")
    if namespace in ("v53","v54","v55","v56", "v57", "v58", "v59", "v60", "v61", "v62", "v63", "v64", "v65", "v66", "v67") and specification is not None:
        if namespace=="v67":
            from src.solvers.local_p_mode_scope import plan_record
        elif namespace=="v66":
            from src.solvers.frozen_local_h_scope import plan_record
        elif namespace=="v65":
            from src.solvers.p6_completion_scope import plan_record
        elif namespace=="v64":
            from src.solvers.local_h_pilot_scope import plan_record
        elif namespace=="v63":
            from src.solvers.fine_tetra_scope import plan_record
        elif namespace=="v62":
            from src.solvers.independent_tetra_scope import plan_record
        elif namespace=="v61":
            from src.solvers.face_trace_scope import plan_record
        elif namespace=="v60":
            from src.solvers.local_subcell_scope import plan_record
        elif namespace=="v59":
            from src.solvers.trace_interior_scope import plan_record
        elif namespace=="v58":
            from src.solvers.phase_deployment_scope import plan_record
        elif namespace=="v57":
            from src.solvers.common_weak_phase_scope import plan_record
        elif namespace=="v56":
            from src.solvers.phase_saved_closure_scope import plan_record
        elif namespace=="v55":
            from src.solvers.phase_spatial_resolution_scope import plan_record
        elif namespace=="v54":
            from src.solvers.phase_p_order_dtn_scope import plan_record
        else:
            from src.solvers.phase_hp_completion_scope import plan_record
        budget=plan_record()["memory_budget"]
        if namespace in ("v63","v64", "v65", "v66", "v67"):
            memory_budget=lambda r:scoped_tetra_memory(namespace,r)
            budget=memory_budget(role)
        if dict(specification.derived["memory_budget"]) != budget or [specification.execution[k] for k in ("planning_memory_gib","warning_memory_gib","terminate_memory_gib")] != [budget[k] for k in ("planning_gib","warning_gib","sampled_stop_gib")]:
            raise ValueError("V53 resolved/launcher/factor memory contract mismatch")
    seconds = window.remaining(role)
    if specification is not None and namespace in ("v41", "v42", "v43", "v44", "v45", "v47", "v49", "v50", "v51", "v52", "v53", "v54", "v55", "v56", "v57", "v58", "v59", "v60", "v61", "v62", "v63", "v64", "v65", "v66", "v67"):
        seconds = min(seconds, float(specification.execution["timeout_seconds"]))
    if seconds <= 5:
        raise RuntimeError("V36 phase paid wall exhausted")
    source = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    if specification is None:
        folder = window.TMP / ("aux_" + phase + "_" + attempt)
    else:
        from datetime import datetime, timezone

        folder = (
            ROOT
            / "results/task042"
            / (
                specification.identity["run_id"]
                + "_"
                + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
            )
        )
    folder.mkdir(parents=True, exist_ok=False)
    if (
        specification is not None
        and namespace in ("v39", "v40", "v43", "v44", "v45", "v47", "v49", "v50", "v51", "v52", "v53", "v54", "v55", "v56", "v57", "v58", "v59", "v60", "v61", "v62", "v63", "v64", "v65", "v66", "v67")
        and ARTIFACT.joinpath(role + ".json").exists()
    ):
        (folder / "superseded_partial_pointer.json").write_bytes(
            ARTIFACT.joinpath(role + ".json").read_bytes()
        )
    v60_archive = (namespace == 'v60' and role == 'archive'
        and specification is None and len(command or []) == 3
        and command[0] in ('python', sys.executable)
        and command[1:] == ['-m', 'benchmarks.compact_local_subcell_raw'])
    if v60_archive:
        # An archive may consume evidence reserve, never exceed the actual
        # frozen cap. All scientific producers retain the original gate.
        limited = storage(namespace=namespace, cleanup=True)
        if limited['new_bytes'] + 32*2**20 > storage_limits(namespace)['new_storage_bytes']:
            raise MemoryError('V60 bounded archive does not fit actual cap')
    storage_record = storage(
        (1024 if namespace == "v42" else 32) * 2**20,
        namespace=namespace,
        cleanup=((namespace in ("v37", "v40") and role == "archive") or v60_archive),
    )
    with (ROOT / "tmp/task042/task042_shared.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        baseline = window.admission(
            audit,
            receipt_path=folder / "admission.json",
            observed_activity=True,
            input_path=str(specification.source_path)
            if specification
            else str(command),
        )
        expected_stop=(scoped_tetra_memory(namespace,role)['sampled_stop_gib'] if namespace in ('v64','v65', 'v66', 'v67') else 192 if namespace=='v63' and role=='B' else 96 if namespace in ('v55','v56', 'v57', 'v58', 'v59', 'v60', 'v61', 'v62', 'v63', 'v64', 'v65', 'v66', 'v67') else 48 if namespace in ('v53','v54') else 24)*2**30
        if namespace in ('v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56', 'v57', 'v58', 'v59', 'v60', 'v61', 'v62', 'v63', 'v64', 'v65', 'v66', 'v67') and preparation_memory_envelope(namespace, role)['launch_cap_bytes'] < expected_stop:
            raise MemoryError('explicit task stop budget exceeds host/cgroup/growth reserves')
        ranks = (
            int(specification.execution["mpi_size"]) if specification is not None else 1
        )
        cpus = [baseline["cpu"]]
        if namespace in ("v41", "v42"):
            cpus, used = [], set()
            for t in baseline["topology"]:
                key = (t["socket"], t["core"])
                if t["cpu"] in baseline["candidate_cpus"] and key not in used:
                    cpus.append(t["cpu"])
                    used.add(key)
                if len(cpus) == ranks:
                    break
            if len(cpus) != ranks:
                write_json(
                    window.TMP / "resource_wait.json",
                    {
                        "next_probe_monotonic": time.monotonic() + 120,
                        "cause": "insufficient distinct audited physical cores for ranks",
                    },
                )
                raise RuntimeError("V41 per-rank CPU/SMT admission rejected")
        os.sched_setaffinity(0, set(cpus))
        os.nice(10)
        subprocess.run(["ionice", "-c", "3", "-p", str(os.getpid())], check=True)
        write_json(folder / "resource_baseline.json", baseline)
        hashes = implementation_hashes()
        if namespace in ("v63","v64", "v65", "v66", "v67") and is_fe:
            memory_budget=lambda r:scoped_tetra_memory(namespace,r)
        state = {
            "source_sha": source,
            "stage": namespace.upper() + "-" + role,
            "scope": namespace,
            "window": window.snapshot(),
            "implementation_hashes": hashes,
            "shared_workstation": True,
            "environment_mode": os.environ.get("TASK042_ENV_MODE"),
            "cpu": baseline["cpu"],
            "rank_cpus": cpus,
            "MPI_size": ranks,
            "planned_bytes": (memory_budget(role)["planning_gib"]*2**30 if namespace in ("v63","v64", "v65", "v66", "v67") and is_fe else 64*2**30) if namespace in ("v55","v56", "v57", "v58", "v59", "v60", "v61", "v62", "v63", "v64", "v65", "v66", "v67") and is_fe else 32*2**30 if namespace in ("v53","v54") and is_fe else 16*2**30 if namespace in ("v50", "v51", "v52", "v53", "v54", "v55", "v56", "v57", "v58", "v59", "v60", "v61", "v62", "v63", "v64", "v65", "v66", "v67") and is_fe else 8*2**30 if namespace == "v49" and is_fe else int(1.8 * 2**30) if namespace in ("v47", "v48") else 6 * 2**30 if is_fe else 2 * 2**30,
            "new_volume_action_count": None if namespace in ("v49", "v50", "v51", "v52", "v53", "v54", "v55", "v56", "v57", "v58", "v59", "v60", "v61", "v62", "v63", "v64", "v65", "v66", "v67") else 0,
            "new_factor_count": None if namespace in ("v49", "v50", "v51", "v52", "v53", "v54", "v55", "v56", "v57", "v58", "v59", "v60", "v61", "v62", "v63", "v64", "v65", "v66", "v67") else 0,
            "numeric_object_inventory_status": "actual stage inventory in result/events; launcher unknown" if namespace in ("v49", "v50", "v51", "v52", "v53", "v54", "v55", "v56", "v57", "v58", "v59", "v60", "v61", "v62", "v63", "v64", "v65", "v66", "v67") else "historical scope inventory",
            "storage_limits": limits,
        }
        if namespace in ("v63","v64", "v65", "v66", "v67") and is_fe:
            state["memory_budget"] = memory_budget(role)
            state["planned_bytes"] = state["memory_budget"]["planning_gib"] * 2**30
        if specification is not None:
            write_json(folder / "resolved_config.json", specification.as_jsonable())
            (folder / "input_original.dat").write_bytes(specification.raw_input_bytes)
            if namespace in ("v53","v54","v55","v56", "v57", "v58", "v59", "v60", "v61", "v62", "v63", "v64", "v65", "v66", "v67"):
                state["memory_budget"]=dict(specification.derived["memory_budget"])
            state.update(
                input_sha256=specification.input_sha256,
                physical_sha256=specification.physical_model_sha256,
                plan_sha256=hashlib.sha256(PLAN.read_bytes()).hexdigest(),
            )
            if namespace in ("v49", "v50", "v51", "v52", "v53", "v54", "v55", "v56", "v57", "v58", "v59", "v60", "v61", "v62", "v63", "v64", "v65", "v66", "v67"):
                from src.io.scattering_anchor import write_identity_texts
                write_identity_texts(folder, specification)
            if namespace in ("v44", "v45") and specification.derived.get(
                "training_resume"
            ):
                state["training_resume"] = specification.derived["training_resume"]
            if namespace in ("v51", "v52", "v53", "v54", "v55", "v56", "v57", "v58", "v59", "v60", "v61", "v62", "v63", "v64", "v65", "v66", "v67") and specification.derived.get("postprocessing_resume"):
                state["postprocessing_resume"] = specification.derived["postprocessing_resume"]
            if namespace in ("v51", "v52", "v53", "v54", "v55", "v56", "v57", "v58", "v59", "v60", "v61", "v62", "v63", "v64", "v65", "v66", "v67") and specification.derived.get("verification_inventory"):
                state["verification_inventory"] = specification.derived["verification_inventory"]
            (folder / "source_sha.txt").write_text(source + "\n")
            command = [
                sys.executable,
                "-m",
                "src.runners.port_preparation",
                "--worker",
                str(folder),
                namespace,
            ]
            if namespace in ("v41", "v42") and ranks > 1:
                command = ["mpiexec", "--bind-to", "none", "-n", str(ranks), *command]
        # RunSpecification deliberately freezes nested mappings. Normalize the
        # live source envelope too: write_json converts a copy, while supervise
        # receives this object and must serialize its own final receipt.
        state = _json_metadata(state)
        write_json(folder / "run_manifest.json", state)
        window.begin(role, folder, source)
        result = supervise(
            command,
            folder / "supervision",
            wall_seconds=seconds,
            interval=0.5,
            timebase_guard=True,
            hard_stop_immediate=True,
            rss_hard_limit_bytes=(memory_budget(role)["sampled_stop_gib"] if namespace in ("v64","v65", "v66", "v67") and is_fe else 192 if namespace=="v63" and role=="B" and is_fe else 96 if namespace in ("v55","v56", "v57", "v58", "v59", "v60", "v61", "v62", "v63", "v64", "v65", "v66", "v67") and is_fe else 48 if namespace in ("v53","v54") and is_fe else 24 if namespace in ("v50", "v51", "v52", "v53", "v54", "v55", "v56", "v57", "v58", "v59", "v60", "v61", "v62", "v63", "v64", "v65", "v66", "v67") and is_fe else 16 if namespace == "v49" and is_fe else 2 if namespace == "v47" else 8 if is_fe else 2) * 2**30,
            rss_warning_bytes=(memory_budget(role)["warning_gib"]*2**30 if namespace in ("v64","v65", "v66", "v67") and is_fe else 160*2**30 if namespace=="v63" and role=="B" and is_fe else 80 * 2**30 if namespace in ("v55","v56", "v57", "v58", "v59", "v60", "v61", "v62", "v63", "v64", "v65", "v66", "v67") and is_fe else 40 * 2**30 if namespace in ("v53","v54") and is_fe else 20 * 2**30 if namespace in ("v50", "v51", "v52", "v53", "v54", "v55", "v56", "v57", "v58", "v59", "v60", "v61", "v62", "v63", "v64", "v65", "v66", "v67") and is_fe else 12 * 2**30 if namespace == "v49" and is_fe else int(1.5 * 2**30) if namespace in ("v47", "v48") else (6 if is_fe else 1) * 2**30),
            memory_envelope_provider=lambda: preparation_memory_envelope(namespace, role),
            include_pss=False,
            source_state=state,
            worker_environment={
                "TASK042_WATCHDOG_PARENT_PID": str(os.getpid()),
                "TASK042_V36_AUX_DIRECTORY": str(folder),
                "TASK042_PREPARATION_SCOPE": namespace,
                "TASK042_RANK_CPUS": ",".join(map(str, cpus)),
                "PYTHONDONTWRITEBYTECODE": "1",
            },
            health_check=(
                SharedHealth(
                    folder,
                    baseline["neighbor_processes"],
                    artifact_limit_bytes=limits["task_storage_bytes"],
                )
                if role == "archive"
                else PreparationHealth(
                    folder, baseline["neighbor_processes"], namespace, limits=limits, baseline_storage=storage_record
                )
            ),
            stop_on_global_swap=False,
        )
        result.update(
            stage=role,
            directory=str(folder),
            launch_wall_seconds=time.monotonic() - started,
            shared_workstation=True,
        )
        write_json(
            folder / ("summary.json" if specification is None else "run_summary.json"),
            result,
        )
        window.settle(result, folder)
        if (
            specification is None
            and result["classification"] == "COMPLETED"
            and result["leader_exit_code"] == 0
            and role == "pre"
        ):
            write_json(
                window.TMP / "qualification.json",
                {
                    "status": "PASSED",
                    "implementation_hashes": implementation_hashes(),
                    "receipt_path": str(folder / "tests.json"),
                    "receipt_sha256": hashlib.sha256(
                        (folder / "tests.json").read_bytes()
                    ).hexdigest(),
                },
            )
        storage(namespace=namespace)
        return result


def worker(folder, namespace="v36"):
    window, ARTIFACT, _plan, implementation_hashes = context(namespace)
    if namespace in ("v41", "v42"):
        from src.solvers.native_entity_scope import guard_entity_worker

        guard_entity_worker(window)
    else:
        window.guard_worker_parent()
    state = json.loads((folder / "run_manifest.json").read_text())
    if (
        state["source_sha"]
        != subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
        or state["implementation_hashes"] != implementation_hashes()
    ):
        raise RuntimeError("V36 active source changed")
    role = state["stage"].removeprefix(namespace.upper() + "-")
    artifact = ARTIFACT / folder.name
    if namespace in ("v41", "v42"):
        from mpi4py import MPI

        comm = MPI.COMM_WORLD
        if comm.rank == 0:
            artifact.mkdir(parents=True, exist_ok=False)
        comm.barrier()
    else:
        artifact.mkdir(parents=True, exist_ok=False)
    began = time.monotonic()
    result = {"status": "FAILED", "stage": role, "source_sha": state["source_sha"]}
    try:
        if namespace in ("v50", "v51", "v52", "v53", "v54", "v55", "v56", "v57", "v58", "v59", "v60", "v61", "v62", "v63", "v64", "v65", "v66", "v67"):
            from src.solvers.phase_explicit_accuracy import execute
            if namespace == "v50":
                from src.solvers.scattering_accuracy import execute
            elif namespace == "v52":
                from src.solvers.phase_notch_hp import execute
            elif namespace == "v53":
                from src.solvers.phase_hp_completion import execute
            elif namespace == "v54":
                from src.solvers.phase_p_order_dtn import execute
            elif namespace == "v67":
                from src.solvers.local_p_mode_study import execute
            elif namespace == "v66":
                from src.solvers.frozen_local_h_study import execute
            elif namespace == "v65":
                from src.solvers.p6_completion_study import execute
            elif namespace == "v64":
                from src.solvers.local_h_pilot import execute
            elif namespace == "v63":
                from src.solvers.fine_tetra_study import execute
            elif namespace == "v62":
                from src.solvers.independent_tetra_study import execute
            elif namespace == "v61":
                from src.solvers.face_trace_study import execute
            elif namespace == "v60":
                from src.solvers.local_subcell_study import execute
            elif namespace == "v59":
                from src.solvers.trace_interior_study import execute
            elif namespace == "v58":
                from src.solvers.phase_deployment import execute
            elif namespace == "v57":
                from src.solvers.common_weak_phase import execute
            elif namespace == "v56":
                from src.solvers.phase_saved_closure import execute
            elif namespace == "v55":
                from src.solvers.phase_spatial_resolution import execute
        elif namespace == "v49":
            from src.solvers.scattering_anchor import execute
        elif namespace == "v47":
            from src.solvers.trace_selection_study import execute
        elif namespace == "v45":
            from src.solvers.full_moment_study import execute
        elif namespace == "v44":
            from src.solvers.neighborhood_late_error_study import execute
        elif namespace == "v43":
            from src.solvers.neighborhood_residual_study import execute
        elif namespace == "v42":
            from src.solvers.distributed_volume_study import execute
        elif namespace == "v41":
            from src.solvers.native_entity_study import execute
        elif namespace == "v40":
            from src.solvers.native_recovery_study import execute
        elif namespace == "v39":
            from src.solvers.native_integration_study import execute
        elif namespace == "v38":
            from src.solvers.boundary_structure_study import execute
        elif namespace == "v37":
            from src.solvers.target_boundary_witness import execute
        else:
            from src.solvers.port_component_study import execute

        os.environ["TASK042_RUN_SOURCE"] = state["source_sha"]
        result = execute(role, artifact, state)
    except BaseException as exc:
        result["error"] = repr(exc)
        traceback.print_exc()
        raise
    finally:
        result.update(
            stage=role,
            source_sha=state["source_sha"],
            elapsed_worker_seconds=time.monotonic() - began,
            input_sha256=state["input_sha256"],
            physical_contract_sha256=state["physical_sha256"],
        )
        result_path = artifact / (
            "result.json"
            if namespace not in ("v41", "v42") or comm.rank == 0
            else f"result_rank{comm.rank}.json"
        )
        write_json(result_path, result)
        if (
            namespace in ("v41", "v42")
            and comm.size > 1
            and result["status"] == "FAILED"
        ):
            # Keep the failed rank's result, then terminate only this MPI job
            # instead of waiting in MPI_Finalize with blocked peers.
            comm.Abort(1)
        if result["status"] != "FAILED" and (
            namespace not in ("v41", "v42") or comm.rank == 0
        ):
            write_json(
                ARTIFACT / (role + ".json"),
                {
                    "path": str(artifact / "result.json"),
                    "sha256": hashlib.sha256(
                        (artifact / "result.json").read_bytes()
                    ).hexdigest(),
                },
            )


def main():
    if sys.argv[1] == "--worker":
        worker(Path(sys.argv[2]).resolve(), sys.argv[3] if len(sys.argv) > 3 else "v36")
        return 0
    if sys.argv[1] == "--aux":
        result = launch(
            command=sys.argv[4:],
            phase=sys.argv[2],
            attempt=sys.argv[3],
            namespace=os.environ.get("TASK042_PREPARATION_SCOPE", "v36"),
        )
        print(
            json.dumps(
                {
                    "directory": result["directory"],
                    "classification": result["classification"],
                    "seconds": result["elapsed_seconds"],
                    "exit_code": result["leader_exit_code"],
                }
            )
        )
        return (
            0
            if result["classification"] == "COMPLETED"
            and result["leader_exit_code"] == 0
            else 1
        )
    raise ValueError("V36 worker/foreground supervised auxiliary only")


if __name__ == "__main__":
    sys.exit(main())
