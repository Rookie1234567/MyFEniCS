"""Independent saved witness consumption; never accepts a producer status flag."""


import numpy as np
from scipy.sparse import csr_matrix

from src.solvers.bound_array_identity import read_arrays
from src.solvers.port_component_study import environment
from src.solvers.trace_selection_scope import ROOT, parent, plan_record, stage


def inventory(plan, records):
    expected = {(s, i, f) for s in ("train", "validation") for i in range(len(plan["split"][s]["seeds"])) for f in (0.5, 0.8)}
    observed = [(r["split"], r["sample"], r["fraction"]) for r in records]
    if len(observed) != len(set(observed)) or set(observed) != expected:
        raise ValueError("independent complete oracle sample/fraction inventory")
    for r in records:
        sample = plan["split"][r["split"]]
        if r["seed"] != sample["seeds"][r["sample"]] or r["family"] != sample["families"][r["sample"]]:
            raise ValueError("independent seed/family identity")


def check_saved(folder, budget):
    oracle = stage("ORACLE")
    data = stage("DATA")
    plan = plan_record()
    inventory(plan, oracle["results"])
    graph = read_arrays(parent("graph")["graph"], ROOT)
    bridge = csr_matrix((graph["bridge_data"], graph["bridge_indices"], graph["bridge_indptr"]), shape=tuple(graph["shape"]), copy=False)
    a = read_arrays(parent("csr")["arrays"], ROOT)
    original = csr_matrix((a["data"], a["indices"], a["indptr"]), shape=tuple(a["shape"]), copy=False)
    ntrace = plan["finite_identity"]["trace_rows"]
    outcomes, cache = [], {}
    for row in oracle["results"]:
        sample_key = (row["split"], row["sample"])
        values = read_arrays(row["arrays"], ROOT)
        if sample_key not in cache:
            sealed = read_arrays(data["datasets"][row["split"]][row["sample"]]["arrays"], ROOT, names=("e", "canonical"))
            rhs = budget.call(original.__matmul__, sealed["e"], kind="CHECK_original_rhs")
            cache[sample_key] = sealed, rhs
        sealed, rhs = cache[sample_key]
        e, c = sealed["e"], sealed["canonical"]
        mask = values["mask"]
        count = int(np.floor(ntrace * row["fraction"]))
        index = np.lexsort((np.arange(ntrace), -np.abs(c[:ntrace])))[:count]
        expected_mask = np.zeros(ntrace, bool)
        expected_mask[index] = True
        selected = c.copy()
        selected[:ntrace] *= expected_mask
        witness = bridge @ selected
        residual = budget.call(original.__matmul__, witness, kind="CHECK_full_witness")-rhs
        eta = float(np.linalg.norm(selected-c)/np.linalg.norm(c))
        trace = float(np.linalg.norm((selected-c)[:ntrace])/np.linalg.norm(c[:ntrace]))
        rho = float(np.linalg.norm(residual)/np.linalg.norm(rhs))
        identities = {
            "sealed_e": np.array_equal(values["e"], e), "sealed_c": np.array_equal(values["canonical"], c),
            "mask": np.array_equal(mask, expected_mask), "count": int(mask.sum()) == count == row["keep_count"],
            "internal_unchanged": np.array_equal(selected[ntrace:], c[ntrace:]),
            "canonical_selected": np.array_equal(selected, values["selected"]),
            "witness": np.linalg.norm(witness-values["e_M"]) <= 1e-10*np.linalg.norm(witness),
            "rhs": np.linalg.norm(rhs-values["rhs"]) <= 1e-10*np.linalg.norm(rhs),
            "saved_residual": np.linalg.norm(residual-values["residual"]) <= 1e-10*np.linalg.norm(rhs),
            "slave_zero": not np.count_nonzero(witness[graph["slaves"]]),
            "full_keep": np.linalg.norm(bridge@c-e) <= 1e-10*np.linalg.norm(e),
            "omitted_energy": abs(np.linalg.norm(selected-c)**2-row["metrics"]["omitted_energy"]) <= 1e-10*max(np.linalg.norm(c)**2, np.finfo(float).tiny),
        }
        for name, value in (("eta", eta), ("trace_error", trace), ("rho", rho)):
            identities["reported_"+name] = abs(value-row["metrics"][name]) <= 1e-10*max(abs(value), np.finfo(float).tiny)
        consistent = bool(all(identities.values()))
        passed = consistent and eta <= 1e-4 and trace <= 1e-4 and rho <= 1e-6
        if not consistent:
            raise ValueError("saved witness identity inconsistent: " + str({k:v for k,v in identities.items() if not v}))
        outcomes.append({"split": row["split"], "sample": row["sample"], "fraction": row["fraction"],
                         "eta": eta, "trace_error": trace, "rho": rho, "passed": passed,
                         "identity_checks": identities, "parent_arrays": row["arrays"]["sha256"]})
    group_checks = []
    for record in oracle["error_groups"]:
        values = read_arrays(record["arrays"], ROOT)
        actual = budget.call(original.__matmul__, values["native"], kind="CHECK_preregistered_group")
        good = np.linalg.norm(actual-values["action"]) <= 1e-10*max(np.linalg.norm(actual), np.finfo(float).tiny)
        group_checks.append({"dimension": record["dimension"], "passed": bool(good)})
        if not good:
            raise ValueError("saved error group action differs from original")
    admitted = all(r["passed"] for r in outcomes if r["fraction"] == 0.5)
    if admitted != oracle["training_admitted"]:
        raise ValueError("training admission disagrees with independent consumed arrays")
    return {"status": "SAVED_WITNESS_CHECKED", "all_saved_identity_checks": True, "training_admitted": admitted,
            "outcomes": outcomes, "group_checks": group_checks, "state_count": len(cache),
            "heldout_consumed": False, "classification": "SUBSPACE_WITNESS_ONLY", "environment": environment(),
            "no_reference_solver_qualification": True}
