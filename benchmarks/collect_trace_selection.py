"""Compact V47 aggregation of saved witnesses; no A, FE, or model invocation."""

import json
from pathlib import Path

import numpy as np

from src.runners.task042_shared import write_json
from src.solvers.bound_array_identity import read_arrays
from src.solvers.trace_selection_scope import (
    ROOT,
    parent,
    plan_record,
    stage,
    window,
)


def sample_analysis(record, graph, ntrace):
    saved = read_arrays(record["arrays"], ROOT, names=("canonical", "selected"))
    c, selected = saved["canonical"], saved["selected"]
    node = np.repeat(np.arange(len(graph["sizes"])), graph["sizes"])
    energy = abs(c-selected)**2
    norm2 = abs(c)**2
    centers = graph["centers"][node[:ntrace]]
    codes = ((centers[:, 0] > 25).astype(int) + 2*(centers[:, 1] > 12.5).astype(int)
             + 4*(centers[:, 2] > 60).astype(int))
    spatial = []
    for region in range(8):
        keep = codes == region
        denominator = float(norm2[:ntrace][keep].sum())
        numerator = float(energy[:ntrace][keep].sum())
        spatial.append({"region": region, "row_count": int(keep.sum()),
                        "coefficient_energy": denominator, "omitted_energy": numerator,
                        "relative_error": float(np.sqrt(numerator/denominator)) if denominator else None})
    moments = []
    for dim, size in ((1, 6), (2, 60)):
        for m in range(size):
            ids = np.array([int(o)+m for o, s in zip(graph["offsets"][:-1], graph["sizes"], strict=True) if s == size])
            numerator, denominator = float(energy[ids].sum()), float(norm2[ids].sum())
            moments.append({"dimension": dim, "moment_index": m, "omitted_energy": numerator,
                            "coefficient_energy": denominator,
                            "relative_error": float(np.sqrt(numerator/denominator)) if denominator else None})
    return {"split": record["split"], "sample": record["sample"], "fraction": record["fraction"],
            "spatial_boxes": spatial, "complete_moment_groups": moments,
            "spatial_square_sum_defect": abs(sum(r["omitted_energy"] for r in spatial)-float(energy.sum())),
            "parent_arrays_sha256": record["arrays"]["sha256"]}


def main():
    import os

    window.guard_worker_parent()
    folder = Path(os.environ["TASK042_V36_AUX_DIRECTORY"])
    oracle, check = stage("ORACLE"), stage("CHECK")
    if not check["all_saved_identity_checks"] or check["training_admitted"]:
        raise ValueError("this collector is the qualified negative-oracle branch")
    graph = read_arrays(parent("graph")["graph"], ROOT)
    ntrace = plan_record()["finite_identity"]["trace_rows"]
    details = [sample_analysis(r, graph, ntrace) for r in oracle["results"]]
    literal_receipt = parent("bridge")["results"][0]["packets"][0]["numeric"]
    literal = read_arrays(literal_receipt, ROOT, names=("slave_local_dofs", "MPC_offsets", "MPC_masters", "MPC_coefficients"))
    constraint_checks = []
    for record in oracle["results"]:
        value = read_arrays(record["arrays"], ROOT, names=("e_M",))["e_M"]
        expanded = value.copy()
        for slave in literal["slave_local_dofs"]:
            lo, hi = literal["MPC_offsets"][slave:slave+2]
            expanded[slave] = literal["MPC_coefficients"][lo:hi] @ value[literal["MPC_masters"][lo:hi]]
        defects = []
        for slave in literal["slave_local_dofs"]:
            lo, hi = literal["MPC_offsets"][slave:slave+2]
            defects.append(expanded[slave]-sum(coef*expanded[master] for coef,master in zip(literal["MPC_coefficients"][lo:hi],literal["MPC_masters"][lo:hi],strict=True)))
        relative = float(np.linalg.norm(defects)/np.linalg.norm(expanded))
        if relative > 1e-10 or np.count_nonzero(value[literal["slave_local_dofs"]]):
            raise ValueError("masked carrier / literal physical MPC identity")
        constraint_checks.append({"split":record["split"],"sample":record["sample"],"fraction":record["fraction"],
                                  "carrier_slave_zero":True,"physical_MPC_relative":relative,
                                  "slave_count":len(defects),"literal_sha256":literal_receipt["sha256"]})
    # Separate effects, then the complex cross term; not just their cancellation.
    groups = [read_arrays(r["arrays"], ROOT, names=("action",)) for r in oracle["error_groups"]]
    edge, face = [g["action"] for g in groups]
    first = read_arrays(oracle["results"][0]["arrays"], ROOT, names=("residual",))
    combined = edge+face
    norm2 = float(np.linalg.norm(combined)**2)
    cross = np.vdot(edge, face)
    group_balance = {"sample":"train:0", "edge_action_norm":float(np.linalg.norm(edge)),
                     "face_action_norm":float(np.linalg.norm(face)), "combined_norm":float(np.linalg.norm(combined)),
                     "complex_inner_product":[float(cross.real),float(cross.imag)],
                     "two_real_cross_term":float(2*cross.real),
                     "square_norm_identity_defect":abs(norm2-(np.linalg.norm(edge)**2+np.linalg.norm(face)**2+2*cross.real)),
                     "full_saved_residual_sum_relative":float(np.linalg.norm(combined+first["residual"])/np.linalg.norm(first["residual"])),
                     "not_a_condition_number":True}
    write_json(folder/"spatial_and_action_analysis.json", {"status":"NEGATIVE_WITNESS_DECOMPOSED",
               "spatial_rule":"x=25/y=12.5/z=60; centers on cut choose low side; from frozen finite geometry, no new masks",
               "samples":details,"action_balance":group_balance,"constraint_checks":constraint_checks,"new_actions":0,
               "training":"NOT_RUN_ORACLE_GATE","heldout_consumed":False})
    print(json.dumps({"samples":len(details),"new_actions":0,"training":"NOT_RUN_ORACLE_GATE"}))


if __name__ == "__main__":
    main()
