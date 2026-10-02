"""Fixed-state derivative qualification and complete-work cost measurements.

State selection is exclusively the four predeclared V9 committed finals.
Full trajectories remain private artifacts; this module returns compact facts.
"""

import csv
import gc
import json
from io import StringIO
from pathlib import Path
from time import perf_counter

import numpy as np
from scipy import sparse

from src.solvers.damped_gauss_newton import DampedGNState
from src.solvers.feinn_cached_derivatives import CachedMomentJacobian
from src.solvers.feinn_gn_training import GNProblem
from src.solvers.feinn_phase_training import configure, policy
from src.solvers.feinn_phase_verification import restore_network
from src.solvers.feinn_torch import CompleteMomentMap
from src.solvers.feinn_validation import load_moments, paired, parameters, assign
from src.solvers.feinn_native import load_native, ResidualMetric
from src.solvers.feinn_reference_fit import FitMetric
from src.solvers.feinn_riesz import SparseRiesz
from src.solvers.neural_fe_action_packet import array_hash
from src.solvers.optimization_checkpoint import (
    atomic_json,
    atomic_write,
    digest,
    restore,
    load_checkpoint,
    parameter_order,
)

ROOT = Path(__file__).resolve().parents[2]
DESIGN_RECORD = (
    ROOT / "docs/task042extra_feinn_5nm/outcomes/records/campaign_design_v10.json"
)


def frozen_entries():
    return json.loads(DESIGN_RECORD.read_text())["frozen_states"]


def load_final(design, entry):
    for name in ("checkpoint", "durable_final", "checkpoint_index"):
        if digest(entry[name]["path"]) != entry[name]["sha256"]:
            raise ValueError("FROZEN_V9_FINAL_BYTES_CHANGED:" + name)
    model, c, state = restore_network(
        design,
        entry["checkpoint"],
        entry["durable_final"],
        phase=entry["phase"],
        supervised=entry["supervised"],
    )
    meta = state["metadata"]
    index = json.loads(Path(entry["checkpoint_index"]["path"]).read_text())
    if (
        index["current"]["sha256"] != entry["durable_final"]["sha256"]
        or meta["state_kind"] != "final_committed"
        or state["optimizer_class"] != "DampedGNState"
    ):
        raise ValueError("NOT_V9_FINAL_COMPLETE_GN_STATE")
    if (
        meta["source_sha"] != entry["source_sha"]
        or meta["complete_c_sha256"] != array_hash(c)
        or meta["parameter_sha256"] != array_hash(parameters(model))
    ):
        raise ValueError("V9_FINAL_SOURCE_PARAMETER_COEFFICIENT_CHANGED")
    for name, value in policy(entry["supervised"]).items():
        if meta[name] is not value:
            raise ValueError("V9_FINAL_LABEL_POLICY_CHANGED")
    gn = state["optimizer"]
    if (
        any(gn[name] != meta[name] for name in ("mu", "h0"))
        or gn["accepted"] != meta["accepted_outer"]
    ):
        raise ValueError("V9_FINAL_GN_METADATA_MISMATCH")
    for key in (
        "slow_streak",
        "pc_builds",
        "V",
        "lam",
        "pc_max_builds",
        "last_pc_outer",
    ):
        if key not in gn:
            raise ValueError("V9_FINAL_RECOVERY_STATE_NOT_RETAINED:" + key)
    return model, c, state


def load_recovery(design, entry, recovery):
    """Restore the newest complete own V10 state, never an uncommitted trial."""
    model, _, original = load_final(design, entry)
    for key in (
        "checkpoint_pointer",
        "durable_final",
        "history",
        "prior_manifest",
        "prior_summary",
    ):
        if digest(recovery[key]["path"]) != recovery[key]["sha256"]:
            raise ValueError("OWN_RECOVERY_BYTES_CHANGED:" + key)
    saved = load_checkpoint(
        recovery["durable_final"]["path"], recovery["durable_final"]["sha256"]
    )
    meta = saved["metadata"]
    if (
        meta != recovery["committed_metadata"]
        or saved["optimizer_class"] != "DampedGNState"
    ):
        raise ValueError("OWN_RECOVERY_METADATA_MISMATCH")
    if saved["parameter_order"] != parameter_order(model):
        raise ValueError("OWN_RECOVERY_PARAMETER_ORDER_CHANGED")
    if meta["prefix_sha256"] != entry["durable_final"]["sha256"]:
        raise ValueError("OWN_RECOVERY_ORIGINAL_V9_IDENTITY_CHANGED")
    if (
        abs(
            recovery["original_V9_logical_prefix_seconds"]
            - original["metadata"]["logical_path_seconds"]
        )
        > 1e-6
    ):
        raise ValueError("OWN_RECOVERY_ORIGINAL_PATH_COST_CHANGED")
    for key in ("native_sha256", "Gram_sha256", "moments_sha256", "buffers_sha256"):
        if meta[key] != original["metadata"][key]:
            raise ValueError("OWN_RECOVERY_PHYSICAL_IDENTITY_CHANGED:" + key)
    for key, expected in policy(entry["supervised"]).items():
        if meta[key] is not expected:
            raise ValueError("OWN_RECOVERY_LABEL_BOUNDARY_CHANGED")
    for key in ("torch_rng", "numpy_rng", "python_rng", "complete_c"):
        if key not in saved:
            raise ValueError("OWN_RECOVERY_STATE_NOT_RETAINED:" + key)
    gn = saved["optimizer"]
    if (
        gn["h0"] != original["optimizer"]["h0"]
        or gn["mu"] != meta["mu"]
        or gn["accepted"] != meta["accepted_outer"]
    ):
        raise ValueError("OWN_RECOVERY_GN_SCALE_OR_STATE_CHANGED")
    if len(gn["pc_builds"]) > (1 if entry["supervised"] else 2):
        raise ValueError("OWN_RECOVERY_PC_LIFETIME_EXCEEDED")
    model.load_state_dict(saved["model"], strict=True)
    if {n: array_hash(b.detach().numpy()) for n, b in model.named_buffers()} != meta[
        "buffers_sha256"
    ]:
        raise ValueError("OWN_RECOVERY_COORDINATE_OR_PHASE_BUFFERS_CHANGED")
    if (
        array_hash(parameters(model)) != meta["parameter_sha256"]
        or array_hash(saved["complete_c"]) != meta["complete_c_sha256"]
    ):
        raise ValueError("OWN_RECOVERY_PARAMETER_OR_FIELD_HASH_CHANGED")
    return model, saved["complete_c"], saved


def distribution(values):
    a = np.asarray([v for v in values if v is not None], float)
    return (
        dict(
            count=len(a),
            min=float(a.min()),
            median=float(np.median(a)),
            max=float(a.max()),
        )
        if len(a)
        else "NOT_RETAINED"
    )


def audit(design, native, qualification, artifact, marker, manifest, load_index):
    configure()
    mapping = CompleteMomentMap(load_moments(qualification["files"]["moments"]["path"]))
    packet = load_native(native["files"]["native"]["path"])
    identities, summaries, outer = {}, {}, []
    for name, entry in frozen_entries().items():
        model, c, state = load_final(design, entry)
        pair = paired(mapping.forward(model), c)
        if pair["relative"] > 1e-12:
            raise ValueError("V9_FINAL_NETWORK_FULL_C_MISMATCH")
        idx = load_index(entry["stage"])
        result = idx["result"]
        actual = packet.audit(c)
        if (
            abs(actual["native_relative"] - result["final_audit"]["native_relative"])
            > 1e-10
        ):
            raise ValueError("V9_FINAL_NATIVE_IDENTITY_FAILED")
        gn = state["optimizer"]
        identities[name] = dict(
            entry,
            parameters_to_saved_c=pair,
            native_identity=actual["native_relative"],
            GN=dict(
                h0=gn["h0"],
                mu=gn["mu"],
                accepted=gn["accepted"],
                slow_streak=gn["slow_streak"],
                PC_completed=len(gn["pc_builds"]),
                PC_last_source=gn["last_pc_outer"],
                PC_basis_sha256=None if gn["V"] is None else array_hash(gn["V"]),
                PC_eigenvalues_sha256=None
                if gn["lam"] is None
                else array_hash(gn["lam"]),
            ),
            RNG_retained=True,
            parameter_only=False,
            label_policy=policy(entry["supervised"]),
        )
        rows = [
            json.loads(line)
            for line in Path(entry["history"]["path"]).read_text().splitlines()
        ]
        trials = [r for r in rows if r["kind"] in ("GN_TRIAL", "CAUCHY_TRIAL")]
        for number, row in enumerate(trials):
            cg = row.get("cg") or {}
            outer.append(
                dict(
                    state=name,
                    proposal=number,
                    kind=row["kind"],
                    accepted=row.get("accepted"),
                    mu=row.get("mu"),
                    pred=row.get("pred"),
                    ared=row.get("ared"),
                    eta=row.get("eta"),
                    cg_iterations=cg.get("iterations", "NOT_RETAINED"),
                    cg_true_relative=cg.get("true_relative", "NOT_RETAINED"),
                    elapsed_seconds=row.get("elapsed_charged_seconds"),
                )
            )
        last = next(
            (r for r in reversed(rows) if r["kind"] == "DURABLE_ACCEPTED"), None
        )
        committed_K = last["counts"]["K"] if last else 6
        summaries[name] = dict(
            accepted=sum(bool(r.get("accepted")) for r in trials),
            rejected=sum(not r.get("accepted", False) for r in trials),
            cg_iterations=distribution(
                [(r.get("cg") or {}).get("iterations") for r in trials]
            ),
            cg_true_relative=distribution(
                [(r.get("cg") or {}).get("true_relative") for r in trials]
            ),
            pred=distribution([r.get("pred") for r in trials]),
            ared=distribution([r.get("ared") for r in trials]),
            eta=distribution([r.get("eta") for r in trials]),
            PC_completed=len(gn["pc_builds"]),
            PC_started="NOT_RETAINED",
            PC_interrupted="NOT_RETAINED",
            uncommitted_K=result["counts"]["K"] - committed_K,
            uncommitted_subphase="NOT_RETAINED",
            counts=result["counts"],
            JVP_VJP_counts=result["JVP_VJP_counts"],
            JVP_VJP_costs=result["JVP_VJP_costs"],
            native_costs=result["native_action_costs"],
            nested_timers_not_additive=result["nested_timers"],
            original_history=entry["history"],
            final_GN=identities[name]["GN"],
        )
        marker(
            "V9_final_identity",
            dict(state=name, native=actual["native_relative"], accepted=gn["accepted"]),
        )
    identity_path, summary_path, csv_path = (
        artifact / "state_identity.json",
        artifact / "inner_summary.json",
        artifact / "outer_history.csv",
    )
    atomic_json(identity_path, identities)
    atomic_json(summary_path, summaries)
    with csv_path.open("w") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(outer[0]))
        writer.writeheader()
        writer.writerows(outer)
    return dict(
        status="V9_FINAL_STATES_AND_WORK_AUDITED",
        states=identities,
        inner_summary=summaries,
        reference_loaded=False,
        missing_work_not_replayed=True,
    ), dict(
        state_identity=identity_path, inner_summary=summary_path, outer_history=csv_path
    )


def make_problem(model, mapping, packet, metric, supervised, cached):
    problem = GNProblem(model, mapping, packet, metric, supervised=supervised)
    if cached:
        problem.jac = CachedMomentJacobian(mapping)
    return problem


def setup(design, native, qualification, reference, marker):
    configure()
    packet = load_native(native["files"]["native"]["path"])
    mapping = CompleteMomentMap(load_moments(qualification["files"]["moments"]["path"]))
    G = sparse.load_npz(native["files"]["gram"]["path"])
    factor = SparseRiesz(G, design, marker)
    pde = ResidualMetric(packet, factor)
    return packet, mapping, G, factor, pde


def checks(design, native, qualification, reference, artifact, marker, manifest):
    packet, mapping, G, factor, pde = setup(
        design, native, qualification, reference, marker
    )
    rows = {}
    rng = np.random.default_rng(4211001)
    fit = None
    try:
        for name, entry in frozen_entries().items():
            model, c, saved = load_final(design, entry)
            if entry["supervised"] and fit is None:
                from src.solvers.feinn_error_geometry import reference_label

                ref, _ = reference_label(
                    native, reference, packet, used_for_training=True
                )
                fit = FitMetric(G, ref)
            metric = fit if entry["supervised"] else pde
            old = make_problem(
                model, mapping, packet, metric, entry["supervised"], False
            )
            new = make_problem(
                model, mapping, packet, metric, entry["supervised"], True
            )
            base = parameters(model)
            cpair = paired(new.jac.forward(model), c)
            pairs = []
            for number, kind in enumerate(("hidden", "last", "random")):
                v = rng.normal(size=base.size)
                v[-390:] = 0 if kind == "hidden" else v[-390:]
                v[:-390] = 0 if kind == "last" else v[:-390]
                v /= np.linalg.norm(v)
                w = 1j * rng.normal(size=packet.size)
                if number != 1:
                    w += rng.normal(size=packet.size)
                jo, jn = old.jac.jvp(model, v), new.jac.jvp(model, v)
                go, gn = old.jac.vjp(model, w), new.jac.vjp(model, w)
                adj = abs(np.vdot(w, jn).real - v @ gn) / max(
                    np.linalg.norm(w) * np.linalg.norm(jn)
                    + np.linalg.norm(v) * np.linalg.norm(gn),
                    1e-30,
                )
                families = {}
                for family in ("edge", "face", "interior"):
                    positions = mapping.packet[family + "_positions"]
                    ids = mapping.packet["owner_rows"][:, positions].ravel()
                    ids = ids[ids >= 0]
                    families[family] = paired(jn[ids], jo[ids])
                pairs.append(
                    dict(
                        kind=kind,
                        JVP=paired(jn, jo),
                        VJP=paired(gn, go),
                        real_adjoint=float(adj),
                        families=families,
                    )
                )
            kv = new.K(v)
            Kpair = paired(kv, old.K(v))
            u = rng.normal(size=base.size)
            u /= np.linalg.norm(u)
            ku = new.K(u)
            symmetry = float(
                abs(u @ kv - v @ ku)
                / max(
                    np.linalg.norm(u) * np.linalg.norm(kv)
                    + np.linalg.norm(v) * np.linalg.norm(ku),
                    1e-30,
                )
            )
            jv = new.jac.jvp(model, v)
            if entry["supervised"]:
                energy = float(np.vdot(jv, G @ jv).real / metric.denominator)
            else:
                av = packet.apply(jv)
                energy = float(np.vdot(av, factor.solve(av)).real / metric.denominator)
            positive_pair = abs(float(v @ kv) - energy) / max(
                abs(float(v @ kv)), abs(energy), 1e-30
            )
            lo, go, _ = old.value_gradient()
            ln, gn, _ = new.value_gradient()
            gpair = paired(gn, go)
            batch = dict(
                JVP=paired(new.jac.jvp(model, v, 1), new.jac.jvp(model, v, 8)),
                VJP=paired(new.jac.vjp(model, w, 1), new.jac.vjp(model, w, 8)),
                c=paired(new.jac.forward(model, 1), new.jac.forward(model, 8)),
            )
            version = new.jac.version
            key = new.jac.key
            _ = new.value(base + 1e-5 * v)
            new.value(base, restore_only=True)
            new.jac.ensure(model)
            rejected_reuses_base = new.jac.key == key and new.jac.version == version
            assign(model, base + 1e-5 * v)
            new.jac.ensure(model)
            accepted_invalidates = new.jac.key != key and new.jac.version > version
            assign(model, base)
            new.jac.ensure(model)
            buffer = model.center.detach().clone()
            model.center.add_(1e-5)
            new.jac.ensure(model)
            buffer_invalidates = new.jac.key != key
            model.center.copy_(buffer)
            new.jac.ensure(model)
            recovered_optimizer = DampedGNState(saved["optimizer"]["h0"])
            restore(model, recovered_optimizer, saved)
            new.jac.ensure(model)
            mu_key, mu_version = new.jac.key, new.jac.version
            recovered_optimizer.mu *= 3
            new.jac.ensure(model)
            mu_reuses = new.jac.key == mu_key and new.jac.version == mu_version
            assign(model, base + 1e-5 * v)
            new.jac.ensure(model)
            restore(model, recovered_optimizer, saved)
            new.jac.ensure(model)
            recovery_pair = paired(new.jac.jvp(model, v), jv)
            recovery_ok = recovery_pair["relative"] <= 1e-10 and new.jac.key == key
            proposal = None
            if not entry["supervised"]:
                proposal_values = []
                for implementation, problem in (("old_AD", old), ("cached", new)):
                    optimizer = DampedGNState(saved["optimizer"]["h0"])
                    optimizer.load_state_dict(saved["optimizer"])
                    start = perf_counter()
                    loss, gradient, _ = problem.value_gradient()
                    result, row = optimizer.propose(
                        base,
                        loss,
                        gradient,
                        problem.K,
                        problem.value,
                        lambda event, label=implementation: marker(
                            "fixed_state_proposal_event",
                            dict(
                                state=name,
                                implementation=label,
                                **event,
                            ),
                        ),
                    )
                    proposal_values.append((result, row, perf_counter() - start))
                    path = artifact / (
                        name
                        + ("_old" if problem is old else "_cached")
                        + "_proposal.npz"
                    )
                    np.savez(
                        path,
                        theta=base,
                        proposed=np.array([]) if result is None else result,
                    )
                po, pn = proposal_values
                if (po[0] is None) != (pn[0] is None):
                    raise ValueError("OLD_NEW_PROPOSAL_BRANCH_CHANGED")
                proposal = dict(
                    direction=None
                    if po[0] is None
                    else paired(pn[0] - base, po[0] - base),
                    pred=paired(
                        np.array([pn[1].get("pred", 0)]),
                        np.array([po[1].get("pred", 0)]),
                    ),
                    ared=paired(
                        np.array([pn[1].get("ared", 0)]),
                        np.array([po[1].get("ared", 0)]),
                    ),
                    old_seconds=po[2],
                    new_seconds=pn[2],
                    old_final_trial=po[1],
                    cached_final_trial=pn[1],
                )
            maximum = max(
                [cpair["relative"], Kpair["relative"], gpair["relative"]]
                + [p[k]["relative"] for p in pairs for k in ("JVP", "VJP")]
                + [p["real_adjoint"] for p in pairs]
                + [p["relative"] for p in batch.values()]
            )
            derivative_ok = (
                cpair["relative"] <= 1e-10
                and all(
                    p[k]["relative"] <= 1e-10 and p["real_adjoint"] <= 1e-10
                    for p in pairs
                    for k in ("JVP", "VJP")
                )
                and Kpair["relative"] <= 1e-9
                and gpair["relative"] <= 1e-9
                and symmetry <= 1e-8
                and positive_pair <= 1e-8
                and all(p["relative"] <= 1e-10 for p in batch.values())
            )
            proposal_ok = proposal is None or all(
                proposal[k] is None or proposal[k]["relative"] <= 1e-8
                for k in ("direction", "pred", "ared")
            )
            rows[name] = dict(
                c=cpair,
                directions=pairs,
                K=Kpair,
                gradient=gpair,
                loss_absolute=abs(ln - lo),
                batch=batch,
                cache_rejection_reuses=rejected_reuses_base,
                cache_acceptance_invalidates=accepted_invalidates,
                buffer_invalidates=buffer_invalidates,
                mu_only_reuse=mu_reuses,
                recovery_rebuilt=recovery_ok,
                recovery_JVP=recovery_pair,
                K_symmetry=symmetry,
                K_energy_pair=float(positive_pair),
                proposal=proposal,
                maximum_relative=maximum,
                cache=new.jac.record(),
                passed=bool(
                    derivative_ok
                    and proposal_ok
                    and rejected_reuses_base
                    and accepted_invalidates
                    and buffer_invalidates
                    and mu_reuses
                    and recovery_ok
                ),
            )
            atomic_json(artifact / "partial_cache_checks.json", rows)
            new.jac.invalidate()
            del new, old, model
            gc.collect()
            marker(
                "derivative_cache_fixed_state_checked",
                dict(state=name, passed=rows[name]["passed"], maximum_relative=maximum),
            )
    finally:
        factor.close()
    path = artifact / "cache_checks.json"
    atomic_json(path, rows)
    return dict(
        status="EXACT_DERIVATIVE_CHECKS_PASS"
        if all(r["passed"] for r in rows.values())
        else "CACHE_OR_RECOVERY_UNQUALIFIED",
        states=rows,
        Gram_factor=factor.record,
        reference_read_only_for_D=True,
    ), dict(checks=path)


def persist_benchmark_samples(artifact, records, gates):
    """Each complete measurement survives a later stop; no partial row qualifies."""
    if records:
        stream = StringIO()
        writer = csv.DictWriter(stream, fieldnames=list(records[0]))
        writer.writeheader()
        writer.writerows(records)
        data = stream.getvalue().encode()
        atomic_write(artifact / "derivative_benchmark.csv", lambda out: out.write(data))
    atomic_json(
        artifact / "partial_benchmark.json", dict(samples=records, states=gates)
    )


def benchmark(
    design, native, qualification, reference, checks_index, artifact, marker, manifest
):
    packet, mapping, G, factor, pde = setup(
        design, native, qualification, reference, marker
    )
    rng = np.random.default_rng(4211001)
    vectors = rng.normal(size=(16, 8966))
    vectors /= np.linalg.norm(vectors, axis=1)[:, None]
    records, gates = [], {}
    cutoff = (
        manifest["supervision_budget_origin_monotonic"]
        + manifest["supervised_limit_seconds"]
        - 150
    )
    stopped = False
    fit = None
    try:
        for name, entry in frozen_entries().items():
            model, _, _ = load_final(design, entry)
            if entry["supervised"] and fit is None:
                from src.solvers.feinn_error_geometry import reference_label

                ref, _ = reference_label(
                    native, reference, packet, used_for_training=True
                )
                fit = FitMetric(G, ref)
            metric = fit if entry["supervised"] else pde
            for repeat in (-1, 0, 1, 2):
                order = (False, True) if repeat % 2 == 0 else (True, False)
                for cached in order:
                    previous = [
                        r["total_seconds"]
                        for r in records
                        if r["implementation"] == ("cached" if cached else "old_AD")
                    ]
                    if perf_counter() + 1.5 * max(previous[-3:] or [120]) >= cutoff:
                        stopped = True
                        break
                    start = perf_counter()
                    problem = make_problem(
                        model, mapping, packet, metric, entry["supervised"], cached
                    )
                    if cached:
                        problem.jac.ensure(model)
                    build = perf_counter() - start
                    began = perf_counter()
                    problem.value_gradient()
                    gradient = perf_counter() - began
                    began = perf_counter()
                    for v in vectors:
                        problem.K(v)
                    ks = perf_counter() - began
                    record = problem.jac.record() if cached else None
                    began = perf_counter()
                    if cached:
                        problem.jac.invalidate()
                    del problem
                    gc.collect()
                    release = perf_counter() - began
                    row = dict(
                        state=name,
                        implementation="cached" if cached else "old_AD",
                        repeat=repeat,
                        warmup=repeat < 0,
                        build_seconds=build,
                        gradient_seconds=gradient,
                        K16_seconds=ks,
                        release_seconds=release,
                        total_seconds=perf_counter() - start,
                        cache_bytes=0 if record is None else record["resident_bytes"],
                        seed=4211001,
                        K_count=16,
                    )
                    records.append(row)
                    persist_benchmark_samples(artifact, records, gates)
                    marker("derivative_benchmark_sample", row)
                if stopped:
                    break
            if stopped:
                del model
                gc.collect()
                break
            old_times = [
                r["total_seconds"]
                for r in records
                if r["state"] == name
                and not r["warmup"]
                and r["implementation"] == "old_AD"
            ]
            new_times = [
                r["total_seconds"]
                for r in records
                if r["state"] == name
                and not r["warmup"]
                and r["implementation"] == "cached"
            ]
            ratio = float(np.median(old_times) / np.median(new_times))
            chk = checks_index["result"]["states"][name]
            prop = chk["proposal"]
            good = bool(
                chk["passed"]
                and ratio >= 1.30
                and (prop is None or prop["new_seconds"] <= 1.10 * prop["old_seconds"])
            )
            gates[name] = dict(
                passed=good,
                status="EXACT_DERIVATIVE_ACCELERATION_PASS"
                if good
                else "CACHE_OR_RECOVERY_UNQUALIFIED"
                if not chk["passed"]
                else "DERIVATIVE_REUSE_NO_GAIN",
                speedup_including_build_release=ratio,
                old=distribution(old_times),
                cached=distribution(new_times),
                proposal_cost_qualified=prop is None
                or prop["new_seconds"] <= 1.10 * prop["old_seconds"],
                shared_A_G_setup_excluded_equally=True,
                candidate_fresh_G_setup_required=True,
            )
            persist_benchmark_samples(artifact, records, gates)
            del model
            gc.collect()
    finally:
        factor.close()
    for name in frozen_entries():
        if name not in gates:
            gates[name] = dict(
                passed=False,
                status="PERFORMANCE_BUDGET_FRONTIER",
                retained_complete_samples=sum(r["state"] == name for r in records),
                speedup_including_build_release=None,
                reason="No complete warmup and three alternating pairs before save reserve",
            )
    persist_benchmark_samples(artifact, records, gates)
    path = artifact / "derivative_benchmark.csv"
    if not path.exists():
        atomic_write(
            path, lambda stream: stream.write(b"state,implementation,repeat\n")
        )
    return dict(
        status="PERFORMANCE_BUDGET_FRONTIER"
        if stopped
        else "DERIVATIVE_BENCHMARK_COMPLETE",
        states=gates,
        samples=records,
        Gram_factor=factor.record,
        warmup_separate=True,
    ), dict(benchmark=path)
