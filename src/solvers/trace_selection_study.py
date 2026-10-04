"""One-run V47 stages, with FE interpolation separated from CSR residency."""

from pathlib import Path
from time import perf_counter

import numpy as np

from src.runners.task042_shared import write_json
from src.solvers.bound_array_identity import (
    consume_identity,
    original_source,
    read_arrays,
    source_identity,
)
from src.solvers.port_component_study import array_file, environment
from src.solvers.trace_selection_scope import (
    ROOT,
    ActionBudget,
    parent,
    plan_record,
    stage,
    window,
)
from src.solvers.trace_subspace_selection import (
    SingleCSR,
    bridge_checks,
    bridge_packet,
    expand_mpc,
    grouped_omission,
    interpolate_complete,
    mask_from_scores,
    masked_coefficients,
    relative,
    wave_parameters,
    witness_metrics,
)


def save(folder, name, **arrays):
    return array_file(folder / (name + ".npz"), compressed=True, **arrays)


def graph_packet():
    original = parent("graph")
    if not original.get("passed") or original.get("native_rows") != 45000 or original.get("independent_rows") != 42624:
        raise ValueError("original qualified canonical decoder identity")
    graph = read_arrays(original["graph"], ROOT)
    bridge, ntrace = bridge_packet(graph)
    checks = bridge_checks(bridge, graph)
    if not checks["passed"] or ntrace != 13824:
        raise ValueError("canonical decoder coverage/orthonormality")
    return bridge, graph, ntrace, checks


def literal_packet():
    packet = parent("bridge")["results"][0]["packets"][0]
    names = ["coordinates", "cell_vertices", "cell_native_dofs", "cell_permutations", "cell_tags",
             "slave_local_dofs", "MPC_offsets", "MPC_masters", "MPC_coefficients"]
    return read_arrays(packet["numeric"], ROOT, names=names), packet["metadata"]


def bind_identity():
    plan = plan_record()
    snapshot = parent("dot_compact")
    src = plan["dot_source"]
    raw = original_source(ROOT, src["commit"], src["path"], src["blob"])
    actual = source_identity(raw, snapshot, blob=src["blob"])
    rejection = consume_identity({"degree": 6}, actual, lambda _: (_ for _ in ()).throw(AssertionError("p4 consumer must not run")))
    if actual["degree"] != 4 or rejection["accepted"] or rejection["consumer_called"]:
        raise ValueError("bound original p4/p6 rejection gate")
    csr = parent("csr")
    if csr["dependencies"]["basis"] != "N1E p6 Legendre complete 6/60/450 moments" or csr["dependencies"]["scalar_dtype"] != "complex128":
        raise ValueError("bound finite p6 basis/scalar identity")
    return {"historical_dot": actual, "declared_p6_rejected_before_consumer": rejection,
            "finite_original_csr": plan["parents"]["csr"], "finite_degree": 6,
            "degree_evidence": csr["dependencies"]["basis"], "DtN": "absent",
            "production_engine_qualification": False, "historical_fixture_unchanged": True}


def data(folder):
    import basix

    env = environment(fe=True)
    identities = bind_identity()
    bridge, graph, ntrace, checks = graph_packet()
    literal, _metadata = literal_packet()
    element = basix.create_element(basix.ElementFamily.N1E, basix.CellType.hexahedron, 6, basix.LagrangeVariant.legendre)
    if element.dim != 882 or len(element.entity_dofs[3][0]) != 450 or len(literal["cell_vertices"]) != 64:
        raise ValueError("complete finite p6 moments/cells")
    bounds = [[float(np.min(literal["coordinates"][:, i])), float(np.max(literal["coordinates"][:, i]))] for i in range(3)]
    rules = plan_record()["generation"]
    pairings = []
    for seed in rules["witness_seeds"]:
        parameters = wave_parameters(seed, "two_waves", bounds, rules)
        fast, fast_cells, duplicate = interpolate_complete(element, literal, parameters)
        independent, independent_cells, duplicate2 = interpolate_complete(element, literal, parameters, independent=True)
        error, local_error = relative(fast, independent), relative(fast_cells, independent_cells)
        receipt = save(folder, f"mapping_{seed}", direct=fast, independent=independent,
                       direct_cells=fast_cells, independent_cells=independent_cells)
        pairings.append({"seed": seed, "arrays": receipt, "all_coeff_relative": error,
                         "all_cell_relative": local_error, "shared_dof_max_relative": max(duplicate, duplicate2),
                         "nonzero_internal_moments": int(np.count_nonzero(fast_cells[:, element.entity_dofs[3][0]])),
                         "passed": error <= 1e-10 and local_error <= 1e-10 and max(duplicate, duplicate2) <= 1e-10})
    write_json(folder / "mapping_gate.json", {"pairings": pairings, "bridge_checks": checks})
    if not all(p["passed"] for p in pairings):
        return {"status": "COMPLETE_MOMENT_MAPPING_NOT_QUALIFIED", "passed": False,
                "pairings": pairings, "identity": identities, "environment": env}
    datasets, inventory = {}, []
    for split, registration in plan_record()["split"].items():
        rows = []
        for index, (seed, family) in enumerate(zip(registration["seeds"], registration["families"], strict=True)):
            parameters = wave_parameters(seed, family, bounds, rules)
            native, _locals, duplicate = interpolate_complete(element, literal, parameters)
            native[graph["slaves"]] = 0
            canonical = bridge.conjugate().T @ native
            e = bridge @ canonical
            scale = float(np.linalg.norm(e))
            if not np.isfinite(scale) or scale == 0 or duplicate > 1e-10:
                raise ValueError("nonzero complete manufactured interpolation")
            canonical, e = canonical / scale, e / scale
            expanded = expand_mpc(e, literal)
            receipt = save(folder, f"sealed_{split}_{index:02d}", e=e, canonical=canonical, expanded=expanded,
                           directions=parameters["directions"], polarizations=parameters["polarizations"],
                           amplitudes=parameters["amplitudes"], phase=parameters["phase"],
                           center=parameters["center"], width=parameters["width"])
            rows.append({"sample": index, "seed": seed, "family": family, "arrays": receipt})
            inventory.append({"split": split, "sample": index, "seed": seed, "family": family,
                              "normalization_native_coefficient_norm": scale, "slave_carrier_zero": True,
                              "trace_rows": ntrace, "internal_rows": 28800, "all_internal_retained": True})
            write_json(folder / "data_checkpoint.json", {"datasets": datasets, "active_split": split, "completed": rows})
        datasets[split] = rows
    return {"status": "COMPLETE_OSCILLATORY_DATA_FROZEN", "passed": True, "datasets": datasets,
            "inventory": inventory, "pairings": pairings, "bridge_checks": checks, "identity": identities,
            "environment": env, "moment_interpolation": "original full Basix x/M, not a new quadrature/form or continuum accuracy claim",
            "volume_quadrature": 15, "native_permutations": np.unique(literal["cell_permutations"]).tolist(),
            "seal": "heldout canonical/e not available to oracle or training readers"}


def load_action(budget):
    began = perf_counter()
    original = parent("csr")
    arrays = read_arrays(original["arrays"], ROOT)
    action = SingleCSR(arrays, budget)
    return action, {"seconds": perf_counter()-began, "payload_bytes": action.payload_bytes,
                    "adjoint_data_copy": False, "hash_reader": "streaming file and no-copy member memoryview",
                    "csr_index_dtype": action.matrix.indices.dtype.str,
                    "native_declared_index_dtype": original["dependencies"]["index_dtype"],
                    "source_manifest": plan_record()["parents"]["csr"]}


def oracle(folder, budget):
    source = stage("DATA")
    if not source["passed"]:
        raise ValueError("real complete moment/mapping gate not passed")
    env = environment()
    bridge, graph, ntrace, _ = graph_packet()
    action, loading = load_action(budget)
    # Both new A/AH access paths paired to the original sparse matrix algebra.
    rng = np.random.default_rng(427910)
    x, y = rng.normal(size=(2, 45000)) + 1j*rng.normal(size=(2, 45000))
    ax, ahy = action.apply(x), action.apply(y, adjoint=True)
    dual_error = float(abs(np.vdot(y, ax)-np.vdot(ahy, x))/(np.linalg.norm(y)*np.linalg.norm(ax)))
    if dual_error > 1e-10:
        raise ArithmeticError("original CSR adjoint chain")
    results, groups, sorting = [], [], []
    for split in ("train", "validation"):
        for sample in source["datasets"][split]:
            values = read_arrays(sample["arrays"], ROOT, names=("e", "canonical"))
            e, c = values["e"], values["canonical"]
            rhs = action.apply(e)
            full = bridge @ c
            full_residual = action.apply(full)-rhs
            full_pass = relative(full, e) <= 1e-10 and np.linalg.norm(full_residual) <= 1e-10*np.linalg.norm(rhs)
            for fraction in (0.5, 0.8):
                began = perf_counter()
                mask = mask_from_scores(abs(c[:ntrace]), ntrace, fraction)
                sorting.append(perf_counter()-began)
                selected = masked_coefficients(c, mask)
                e_m = bridge @ selected
                residual = action.apply(e_m)-rhs
                metrics = witness_metrics(c, selected, rhs, residual, ntrace)
                constrained = bool(np.count_nonzero(e_m[graph["slaves"]]) == 0 and np.array_equal(selected[ntrace:], c[ntrace:]))
                metrics["passed"] = bool(metrics["passed"] and constrained and full_pass)
                num = float(np.linalg.norm(e-e_m))
                metrics["original_action_gain"] = float(np.linalg.norm(residual))/num if num else None
                packet = save(folder, f"{split}_{sample['sample']:02d}_{int(fraction*100)}", mask=mask,
                              e=e, canonical=c, rhs=rhs, selected=selected, e_M=e_m, residual=residual,
                              full_residual=full_residual)
                result = {"split": split, "sample": sample["sample"], "seed": sample["seed"], "family": sample["family"],
                          "fraction": fraction, "keep_count": int(mask.sum()), "arrays": packet, "metrics": metrics,
                          "constraints": constrained, "full_keep_pass": bool(full_pass),
                          "omission": grouped_omission(c, selected, graph, ntrace)}
                results.append(result)
                if split == "train" and sample["sample"] == 0 and fraction == 0.5:
                    node_of = np.repeat(np.arange(len(graph["sizes"])), graph["sizes"])
                    delta = c-selected
                    for dimension in (1, 2):
                        part = np.zeros_like(delta)
                        take = graph["keys"][node_of, 0] == dimension
                        part[take] = delta[take]
                        action_part = action.apply(bridge @ part)
                        groups.append({"sample": "train:0", "dimension": dimension,
                                       "arrays": save(folder, f"error_group{dimension}", coefficients=part,
                                                      native=bridge @ part, action=action_part),
                                       "coefficient_norm": float(np.linalg.norm(part)),
                                       "action_norm": float(np.linalg.norm(action_part))})
                write_json(folder / "oracle_checkpoint.json", {"results": results, "groups": groups})
    main = [r for r in results if r["fraction"] == 0.5]
    admitted = len(main) == 20 and all(r["metrics"]["passed"] for r in main)
    return {"status": "ORACLE_TRAINING_ADMITTED" if admitted else "FIXED_COORDINATE_SELECTION_CLOSED",
            "training_admitted": bool(admitted), "results": results, "error_groups": groups,
            "A_AH_dual_relative": dual_error, "loading": loading, "sorting_seconds": sorting,
            "action_calls": action.calls, "action_seconds": action.seconds, "environment": env,
            "freeze": {"masks": plan_record()["masks"], "training": "eligible" if admitted else "NOT_RUN_ORACLE_GATE",
                       "heldout": "sealed; not consumed when oracle closes the candidate"},
            "scope": "minimum coefficient error at fixed coordinate cardinality, not minimum residual over re-solved subspace"}


def analysis(folder):
    oracle_result = stage("ORACLE")
    main = [r for r in oracle_result["results"] if r["fraction"] == 0.5]
    diagnostic = [r for r in oracle_result["results"] if r["fraction"] == 0.8]
    trace, internal = 105298704, 238885200
    payload = (trace+internal)*16
    fraction = (trace//2)*16/payload
    return {"status": "FINITE_SELECTION_ANALYSIS_COMPLETE", "scope": "SUBSPACE_WITNESS_ONLY",
            "main_failures": [{k: r[k] for k in ("split", "sample", "family", "metrics", "omission")} for r in main if not r["metrics"]["passed"]],
            "diagnostic80_range": {k: [min(r["metrics"][k] for r in diagnostic), max(r["metrics"][k] for r in diagnostic)] for k in ("eta", "trace_error", "rho")},
            "capacity": {"target_trace": trace, "target_internal": internal, "target_total": trace+internal,
                         "one_full_vector_bytes": payload, "one_trace_vector_bytes": trace*16,
                         "half_trace_saved_payload_bytes": (trace//2)*16, "max_full_vector_payload_saving": fraction,
                         "trace_fraction": trace/(trace+internal),
                         "17_FP64_feature_bytes_unstreamed": trace*17*8,
                         "float64_scores_bytes": trace*8, "sort_int64_index_bytes": trace*8,
                         "bool_mask_bytes": trace, "network_max_parameters_FP64_bytes": 10000*8,
                         "actual_finite_median_sort_seconds": float(np.median(oracle_result["sorting_seconds"])),
                         "target_sort_prediction_seconds": float(np.median(oracle_result["sorting_seconds"]))*trace/13824*np.log2(trace)/np.log2(13824),
                         "prediction_scope": "single-core n log n same sorting, cache/communication/streaming unknown",
                         "solver_periodic_blocks_factor_residual_internal_lifetimes": "unknown",
                         "full_rhs_streaming_interface": "unknown", "simultaneous_target_peak": "unknown"},
            "cost_necessary": {"condition": "f*V-H >= .2*T_B; s >= (.2+H/T_B)/f", "target_T_B": "unknown",
                               "f": "unknown for solver; vector-payload bound is not time saving",
                               "H": "actual V47 full new research cost plus unknown historical/cold data components; N=1 pays all",
                               "NN20": "NOT_QUALIFIED", "multiple_RHS_amortization": "separate, not N=1"},
            "actual_training": "NOT_RUN_ORACLE_GATE" if not oracle_result["training_admitted"] else "conditional queue required",
            "next": "different admissible representation needs evidence; do not retrain to defeat this fixed-coordinate lower bound",
            "qualification": {"forward_solve": "NOT_RUN", "complete_DtN_EH_power": "NOT_QUALIFIED",
                              "original_size": "NOT_QUALIFIED", "2TB_48h": "NOT_QUALIFIED", "NN20": "NOT_QUALIFIED"},
            "environment": environment(), "actions_in_analysis": 0}


def execute(role, folder, state):
    window.guard_worker_parent()
    # Counters belong beside the supervisor, not the array archive.
    import os
    budget = ActionBudget(Path(os.environ["TASK042_V36_AUX_DIRECTORY"]))
    if role == "DATA":
        return data(folder)
    if role == "ORACLE":
        return oracle(folder, budget)
    if role == "CHECK":
        from benchmarks.check_trace_selection import check_saved

        return check_saved(folder, budget)
    if role == "ANALYSIS":
        return analysis(folder)
    raise RuntimeError("conditional selector implementation requires admitted oracle; no blind training")
