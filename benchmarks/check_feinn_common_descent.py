"""Independent raw-array checker. No optimization, solver or network imports."""

import numpy as np

POINTS = {"zero", "residual", "field", "common"}
ORACLE_ROLE = "REFERENCE_EXPOSED_LOCAL_ORACLE"
CANDIDATE_ROLE = "UNLABELED_PDE8_RESIDUAL_CANDIDATE"
FALSE_FLAGS = ("pde_only_solve", "production_initialization_allowed",
               "official_candidate_results", "true_NN_increment")


def need(condition, message):
    if not condition:
        raise ValueError(message)


def same(x, y, tolerance=1e-8):
    x, y = np.asarray(x), np.asarray(y)
    need(x.shape == y.shape and np.isfinite(x).all() and np.isfinite(y).all(), "CHECKER_SHAPE_FINITE")
    need(np.linalg.norm(x - y) <= tolerance * max(1, np.linalg.norm(x), np.linalg.norm(y)), "CHECKER_VALUE")


def classify(F, R, lower, margin, valid):
    if not valid:
        return "UNKNOWN"
    if max(F, R) <= 0.999 - 1e-10:
        return "COMMON_DESCENT_AT_LEAST_0P1_PERCENT"
    if lower - margin > 0.999 + 1e-10:
        return "NO_0P1_PERCENT_COMMON_DESCENT_IN_RETAINED_BALL"
    return "UNKNOWN_THRESHOLD_BRACKET"


def diagnostic_policy(record, *, top=False):
    """Old top-level v1 omitted flags: explicit row flags remain mandatory."""
    if top:
        need(record["value_kind"] == "DERIVED_LOCAL_LINEAR_MODEL", "TOP_VALUE_ROLE")
        need(record["main_solver"] == "FEINN_MAIN_SOLVER_ON_HOLD"
             and record["NN_increment"] == "NO_VERIFIED_NN_INCREMENT", "TOP_SOLVER_ROLE")
        for key in ("status", "gate_status"):
            if key in record:
                need(record[key] in ("PARTIAL", "UNKNOWN", "COMPLETE_RECORDS_VERIFIED"), "FALSE_GLOBAL_PASS")
    else:
        need(record["reference_used_for_oracle"] is True, "REFERENCE_ORACLE_ROLE")
        need(record["oracle_data_role"] == ORACLE_ROLE, "ORACLE_DATA_ROLE")
        if "value_kind" in record:
            need(record["value_kind"] == "DERIVED_LOCAL_LINEAR_MODEL", "ROW_VALUE_ROLE")
    if "data_role" in record:
        need(record["data_role"] == ORACLE_ROLE, "BATCH_OR_ROW_DATA_ROLE")
    if "reference_used_for_training" in record:
        need(record["reference_used_for_training"] is False, "NO_TRAINING_IN_ARRAY_DIAGNOSTIC")
    for flag in FALSE_FLAGS:
        if not top or flag in record:
            need(record.get(flag) is False, "DIAGNOSTIC_POLICY_" + flag)
    # Reject extra declarations that would promote a diagnostic to a solver.
    for flag in ("pde_only_solver_qualified", "production_solver_qualified"):
        if flag in record:
            need(record[flag] is False, "DIAGNOSTIC_POLICY_" + flag)


def configuration_coverage(result, design):
    """Exactly one success or sourced UNKNOWN for every design key."""
    rconds = design["rconds"]
    need(len(rconds) == 2 and set(rconds) == {1e-10, 1e-12}, "FIXED_DESIGN_RCONDS")
    expected = {(state, subset, rc) for state in design["states"]
                for subset in ("PDE8", "ALL16") for rc in rconds}
    need(expected, "EMPTY_EXPECTED_BATCH")
    found, unknown = {}, {}
    for row in result["configurations"]:
        key = (row["state"], row["subset"], row["rcond"])
        need(key in expected, "EXTRA_CONFIGURATION_KEY")
        need(key not in found, "DUPLICATE_CONFIGURATION_KEY")
        found[key] = row
    for index, row in enumerate(result["unknown"]):
        need(row.get("status") == "UNKNOWN" and row.get("phase") and row.get("reason"), "UNKNOWN_REASON_STAGE")
        need(row["state"] in design["states"], "UNKNOWN_STATE")
        source = row.get("source_sha", result["source_sha"])
        need(source == result["source_sha"] and bool(source), "UNKNOWN_SOURCE")
        subsets = (row["subset"],) if "subset" in row else ("PDE8", "ALL16")
        values = (row["rcond"],) if "rcond" in row else rconds
        for subset in subsets:
            for rc in values:
                key = (row["state"], subset, rc)
                need(key in expected and key not in found and key not in unknown, "UNKNOWN_OVERLAP_OR_KEY")
                unknown[key] = dict(state=key[0], subset=key[1], rcond=key[2], status="UNKNOWN",
                                    phase=row["phase"], reason=row["reason"], source_sha=source,
                                    expanded_from_unknown_index=index)
    need(set(found) | set(unknown) == expected, "MISSING_CONFIGURATION_WITHOUT_UNKNOWN")
    return expected, found, unknown


def admission(rows, states, rconds, freeze_qualified):
    """Only frozen PDE8 residual points, both states and both fixed rconds."""
    per_candidate = []
    for state in states:
        for rc in rconds:
            matches = [r for r in rows if (r["state"], r["subset"], r["rcond"]) == (state, "PDE8", rc)]
            if not matches:
                per_candidate.append(dict(state=state, rcond=rc, status="UNKNOWN", reason="NUMERICAL_RECORD_UNAVAILABLE"))
                continue
            row = matches[0]
            point, zero = row["recomputed_points"]["residual"], row["recomputed_points"]["zero"]
            tests = dict(F_energy=point["F"] <= .999 - 1e-10,
                         R_energy=point["R"] <= .999 - 1e-10,
                         native_nonincrease=point["native_linear"] <= zero["native_linear"] - 1e-10)
            clear_failure = (point["F"] > .999 + 1e-10 or point["R"] > .999 + 1e-10
                             or point["native_linear"] > zero["native_linear"] + 1e-10)
            status = "PASS" if all(tests.values()) and freeze_qualified else "NOT_ADMITTED" if clear_failure else "UNKNOWN"
            per_candidate.append(dict(state=state, rcond=rc, status=status, tests=tests,
                                      F=point["F"], R=point["R"], native_before=zero["native_linear"],
                                      native_after=point["native_linear"], freeze_qualified=freeze_qualified))
    statuses = [r["status"] for r in per_candidate]
    status = "ADMITTED" if statuses and all(s == "PASS" for s in statuses) else "NOT_ADMITTED" if "NOT_ADMITTED" in statuses else "UNKNOWN"
    return dict(status=status, admitted=status == "ADMITTED", candidates=per_candidate,
                scope="FROZEN_PDE8_ONLY_BOTH_STATES_BOTH_RCONDS", true_NN_increment=False)


def verify_configuration(record, raw, metadata, theta_norm, native_denominator):
    """Recompute physical steps, spectra/duality and provenance from raw arrays."""
    state, subset = record["state"], record["subset"]
    diagnostic_policy(record)
    need(set(record["points"]) == POINTS, "FOUR_COMPARISON_POINTS_REQUIRED")
    need(np.isfinite(native_denominator) and native_denominator > 0, "RAW_NATIVE_DENOMINATOR")
    need(state == metadata["name"] and subset in ("PDE8", "ALL16"), "STATE_IDENTITY")
    need(record["state_identity"] == metadata["identity"], "STATE_HASH_IDENTITY")
    active = [d for d in metadata["directions"] if "column" in d]
    need(sorted(d["column"] for d in active) == list(range(raw["P"].shape[1])), "RAW_COLUMN_MAP")
    need(all(d["kind"] in ("PDE", "reference_G") for d in active), "RAW_COLUMN_KIND")
    columns = sorted(d["column"] for d in active if subset == "ALL16" or d["kind"] == "PDE")
    need(record["columns"] == columns, "COLUMN_PROVENANCE")
    need(record["residual_candidate_unlabeled"] is (subset == "PDE8"), "LABEL_ROLE")
    selected = {k: v[:, columns] if k in ("P", "X", "GX", "Y", "WY") else v for k, v in raw.items()}
    for value in selected.values():
        need(np.isfinite(value).all(), "RAW_NONFINITE")
    P, T = selected["P"], np.asarray(record["T"])
    need(P.dtype == np.float64 and not np.iscomplexobj(T), "REAL_PARAMETER")
    need(T.ndim == 2 and np.isfinite(T).all() and T.shape[1] <= 16, "BASIS_LAYOUT_FINITE")
    rho = 1e-3 * max(theta_norm, 1)
    same(record["rho"], rho, 1e-12)
    need(record["rcond"] in (1e-10, 1e-12), "RCOND_CONTRACT")
    scales = np.linalg.norm(P, axis=0)
    safe = np.where(scales > 0, scales, 1)
    U, sigma, _ = np.linalg.svd(P / safe, full_matrices=False)
    keep = sigma > (record["rcond"] * sigma[0] if len(sigma) else 0)
    need(record["basis"]["rank"] == int(keep.sum()) and T.shape == (len(columns), int(keep.sum())), "RANK_LAYOUT")
    need(record["basis"]["truncation"] == (~keep).tolist(), "TRUNCATION")
    same(record["basis"]["singular_values"], sigma, 1e-10)
    same(record["basis"]["column_scales"], scales, 1e-10)
    Q = P @ T
    orth = np.linalg.norm(Q.T @ Q - np.eye(Q.shape[1]))
    need(orth <= 1e-10, "RAW_PARAMETER_ORTHOGONALITY")
    same(record["basis"]["parameter_orthogonality"], orth, 1e-10)
    same(Q @ (Q.T @ U[:, keep]), U[:, keep], 1e-10)
    reconstruction = np.linalg.norm(P / safe - Q @ (Q.T @ (P / safe))) / max(np.linalg.norm(P / safe), 1)
    same(record["basis"]["parameter_reconstruction"], reconstruction, 1e-10)
    quadratics = {}
    for key, col, wcol, t, wt in (("F", "X", "GX", "e", "Ge"), ("R", "Y", "WY", "r", "qr")):
        x, wx = selected[t], selected[wt]
        d = np.vdot(x, wx)
        need(d.real > 256 * np.finfo(float).eps * np.linalg.norm(x) * np.linalg.norm(wx), "RAW_DENOMINATOR")
        need(abs(d.imag) <= 256 * np.finfo(float).eps * np.linalg.norm(x) * np.linalg.norm(wx), "RAW_ENERGY_IMAGINARY")
        C, WC = rho * selected[col] @ T, rho * selected[wcol] @ T
        Hfull = C.conj().T @ WC / d.real
        need(np.linalg.norm(Hfull - Hfull.conj().T) <= 1e-10 * max(np.linalg.norm(Hfull), np.finfo(float).tiny), "RAW_HERMITIAN")
        H = (Hfull.real + Hfull.real.T) / 2
        a = (C.conj().T @ wx).real / d.real
        stored = record["quadratic_" + key]
        same(stored["denominator"], d.real, 1e-12)
        same(stored["H"], H, 1e-10)
        same(stored["a"], a, 1e-10)
        same(stored["eigenvalues"], np.linalg.eigvalsh(H), 1e-10)
        need(not len(a) or np.linalg.eigvalsh(H)[0] >= -256 * np.finfo(float).eps * np.linalg.norm(H, 2), "RAW_PSD")
        quadratics[key] = (H, a)
    worst, recomputed = 0.0, {}
    for name, row in record["points"].items():
        u, alpha = np.asarray(row["u"]), np.asarray(row["alpha"])
        need(u.shape == (T.shape[1],) and alpha.shape == (len(columns),)
             and not np.iscomplexobj(u) and not np.iscomplexobj(alpha)
             and np.isfinite(u).all() and np.isfinite(alpha).all(), "POINT_LAYOUT_FINITE")
        need(row["value_kind"] == "DERIVED_LOCAL_LINEAR_MODEL", "POINT_VALUE_ROLE")
        role = CANDIDATE_ROLE if subset == "PDE8" and name == "residual" else ORACLE_ROLE
        if "data_role" in row:
            need(row["data_role"] == role, "POINT_DATA_ROLE")
        if "reference_used_for_construction" in row:
            need(row["reference_used_for_construction"] is (role != CANDIDATE_ROLE), "POINT_LABEL_ROLE")
        for flag in FALSE_FLAGS:
            if flag in row:
                need(row[flag] is False, "POINT_DIAGNOSTIC_POLICY_" + flag)
        if name == "zero":
            need(np.count_nonzero(u) == np.count_nonzero(alpha) == 0, "ZERO_STEP_REQUIRED")
            same([row["F"], row["R"]], [1., 1.], 1e-12)
        if name != "zero":
            same(u, record["common"][{"residual": "u_R", "field": "u_F", "common": "u"}[name]], 1e-12)
        recomputed[name] = dict(data_role=role, reference_used_for_construction=role != CANDIDATE_ROLE)
        need(np.linalg.norm(u) <= 1 + 1e-10, "BALL_FEASIBILITY")
        same(alpha, rho * T @ u, 1e-10)
        step = np.linalg.norm(P @ alpha)
        need(step <= rho * (1 + 1e-10), "PARAMETER_RADIUS")
        same(row["parameter_step_norm"], step, 1e-10)
        for key, col, wcol, t, wt in (("F", "X", "GX", "e", "Ge"), ("R", "Y", "WY", "r", "qr")):
            x, wx = selected[t], selected[wt]
            delta, wdelta = selected[col] @ alpha, selected[wcol] @ alpha
            before = np.vdot(x, wx).real
            after = np.vdot(x + delta, wx + wdelta).real
            cross, update = 2 * np.vdot(x, wdelta).real, np.vdot(delta, wdelta).real
            same(row[key], after / before, 1e-10)
            recomputed[name][key] = float(after / before)
            recomputed[name][key + "_energy"] = dict(before=float(before), after=float(after),
                                                       signed_cross=float(cross), update=float(update))
            for field, value in (("before", before), ("after", after), ("signed_cross", cross), ("update", update)):
                same(row[key + "_energy"][field], value, 1e-10)
            defect = abs(after - before - cross - update) / max(before, abs(cross) + abs(update))
            need(defect <= 1e-8, "RAW_CROSS_RECONSTRUCTION")
            worst = max(worst, defect)
            H, a = quadratics[key]
            same(row[key], 1 + 2 * a @ u + u @ H @ u, 1e-8)
        native = float(np.linalg.norm(selected["r"] + selected["Y"] @ alpha) / native_denominator)
        same(row["native_linear"], native, 1e-10)
        recomputed[name].update(native_linear=native, parameter_step_norm=float(step))
        if name in ("residual", "field"):
            key = "R" if name == "residual" else "F"
            H, a = quadratics[key]
            mu = record["common"]["endpoint_multipliers"][key]
            need(np.isfinite(mu) and mu >= 0, "ENDPOINT_MULTIPLIER")
            need(np.linalg.norm((H + mu * np.eye(len(u))) @ u + a) <= 1e-8 * max(1, np.linalg.norm(a), np.linalg.norm(H)), "ENDPOINT_STATIONARITY")
            need(abs(mu * (u @ u - 1)) <= 1e-8 * max(1, mu), "ENDPOINT_COMPLEMENTARITY")
    common = record["common"]
    u = np.asarray(common["u"])
    same(u, record["points"]["common"]["u"], 1e-12)
    upper = max(recomputed["common"]["F"], recomputed["common"]["R"])
    same(common["U"], upper, 1e-10)
    certificate = common["certificate"]
    weight, mu = certificate["lambda_"], certificate["mu"]
    need(np.isfinite(weight) and np.isfinite(mu) and 0 <= weight <= 1 and mu >= 0, "DUAL_MULTIPLIERS")
    HF, aF = quadratics["F"]
    HR, aR = quadratics["R"]
    H, a = weight * HF + (1 - weight) * HR, weight * aF + (1 - weight) * aR
    M = H + mu * np.eye(len(a))
    spectrum = np.linalg.eigvalsh(M)
    need(not len(a) or spectrum[0] >= 0, "DUAL_PSD")
    same(certificate["spectrum"], spectrum, 1e-10)
    # Independent dense solve only of the <=16 by16 saved certificate matrix.
    if len(a) and spectrum[0] > 0:
        z = np.linalg.solve(M, a)
    else:
        z = np.linalg.lstsq(M, a, rcond=1e-14)[0] if len(a) else np.empty(0)
    same(certificate["inverse_action"], z, 1e-8)
    range_defect = np.linalg.norm(M @ np.asarray(certificate["inverse_action"]) - a)
    same(certificate["range_defect"], range_defect, 1e-8)
    need(range_defect <= 1e-8 * max(1, np.linalg.norm(a)), "DUAL_RANGE")
    lower = 1 - mu - a @ z
    same(certificate["lower"], lower, 1e-8)
    margin = 4096 * np.finfo(float).eps * (1 + abs(mu) + np.linalg.norm(H) + np.linalg.norm(a) * np.linalg.norm(certificate["inverse_action"])) + 4 * range_defect * max(1, np.linalg.norm(certificate["inverse_action"]))
    same(certificate["numerical_margin"], margin, 1e-10)
    need(certificate["numerical_margin"] >= 0, "NUMERICAL_MARGIN")
    same(common["gap"], upper - certificate["lower"], 1e-8)
    need(upper + certificate["numerical_margin"] >= certificate["lower"] - 1e-10, "BOUND_ORDER")
    same(certificate["stationarity"], np.linalg.norm(M @ u + a), 1e-10)
    same(certificate["complementarity"], abs(mu * (u @ u - 1)), 1e-10)
    need(common["lambda_evaluations"] <= 64 and common["root_iteration_max"] <= 80, "ITERATION_CAP")
    valid = reconstruction <= 1e-10 and worst <= 1e-8
    # Certificate inverse action is independently paired above; preserve the
    # original margin formula and original certificate, never optimize it here.
    result = classify(recomputed["common"]["F"], recomputed["common"]["R"], float(lower), float(margin), valid)
    need(record["classification"] == result, "FALSE_PRODUCER_CLASSIFICATION")
    need(record["bounds_closed"] == (common["gap"] + certificate["numerical_margin"] <= 1e-8), "BOUND_GAP_STATUS")
    need(not record["true_NN_increment"] and not record["official_candidate_results"], "DIAGNOSTIC_LABEL")
    return dict(state=state, subset=subset, rcond=record["rcond"], classification=result,
                U=upper, L=float(lower), margin=float(margin), raw_cross_defect=worst,
                bound_width=float(upper - lower + margin),
                bound_width_qualification="PASS" if upper - lower + margin <= 1e-8 else "UNKNOWN",
                numerical_validity="PASS", recomputed_points=recomputed,
                rank=int(keep.sum()), native_denominator=float(native_denominator))
