"""Independent saved-array audit of native integration; no solve or teacher."""

import numpy as np

from benchmarks.check_boundary_witness import metric, read_arrays


def literal_layout_checks(element, layout, patch, conversion):
    """Reconstruct native basis/MPC versus compact equations, never fit them."""
    lit = read_arrays(patch["literal"])
    saved = read_arrays(conversion)
    n = patch["storage_rows"]
    offsets = lit.get("master_offsets", np.arange(n + 1))
    masters = lit.get("master_rows", np.arange(n))
    dual = lit.get("master_dual_coefficients", np.ones(n, complex))
    if (
        len(offsets) != n + 1
        or offsets[-1] != len(masters)
        or len(dual) != len(masters)
    ):
        raise ValueError("literal independent MPC inventory")
    X = saved["primal_map"]
    native_rows = saved["native_rows"]
    compact = saved["compact_rows"]
    if X.shape != (len(native_rows), len(compact)):
        raise ValueError("literal row conversion shape")
    checks = []
    for cell, dofs in enumerate(lit["cell_dofs"]):
        coords = lit["coordinates"][lit["geometry_dofmap"][cell]]
        bounds = np.column_stack((coords.min(axis=0), coords.max(axis=0))).tolist()
        found = [d for d in patch["description"]["cells"] if d["bounds_nm"] == bounds]
        if len(found) != 1:
            raise ValueError("literal native cell bounds")
        desc = found[0]
        side = desc["side"]
        i, j, _ = desc["indices"]
        active = layout.polynomial.active[side]
        orientation = np.zeros((element.dim, len(active)))
        orientation[active, np.arange(len(active))] = 1
        element.T_apply(
            orientation.ravel(), len(active), int(lit["permutations"][cell])
        )
        primal = np.zeros((len(active), len(native_rows)), np.complex128)
        lookup = {int(r): k for k, r in enumerate(native_rows)}
        for a, row in enumerate(np.asarray(dofs)[active]):
            for k in range(int(offsets[row]), int(offsets[row + 1])):
                if int(masters[k]) not in lookup:
                    if dual[k] != 0:
                        raise ValueError("literal adapter omitted native master")
                else:
                    primal[a, lookup[int(masters[k])]] += dual[k].conjugate()
        left = orientation[active].T @ primal @ X
        right = np.zeros((len(active), len(compact)), np.complex128)
        rows = layout.maps[side][i, j]
        positions = np.searchsorted(compact, rows)
        if np.any(positions >= len(compact)) or not np.array_equal(
            compact[positions], rows
        ):
            raise ValueError("literal adapter omitted compact entity")
        right[np.arange(len(active)), positions] = layout.weights[side][i, j]
        checks.append(
            dict(
                kind="independent_literal_adapter",
                patch=patch["description"]["name"],
                cell=cell,
                **metric(left, right),
            )
        )
    return checks


def check_adapter_vectors(data):
    required = {
        "C_native",
        "D_native",
        "C_from_adapter",
        "D_from_adapter",
        "slaves",
        "interiors",
        "alpha",
        "modal",
        "oracle_modal",
        "boundary_dual",
        "extract_inner",
        "scatter_inner",
    }
    required |= {
        f"{label}_{kind}"
        for label in ("a", "b", "interior", "zero", "scale")
        for kind in (
            "x",
            "t",
            "forward",
            "oracle_forward",
            "adjoint",
            "oracle_adjoint",
            "amplitudes",
            "oracle_amplitudes",
        )
    }
    if not required <= set(data):
        raise ValueError("complete native adapter witness inventory")
    C, D = data["C_native"], data["D_native"]
    if C.ndim != 2 or D.shape != (C.shape[1], C.shape[0]):
        raise ValueError("native adapter matrix inventory shape")
    n, nm = C.shape
    if any(not np.isfinite(value).all() for value in data.values()):
        raise ValueError("nonfinite adapter evidence")
    if (
        data["C_from_adapter"].shape != C.shape
        or data["D_from_adapter"].shape != D.shape
    ):
        raise ValueError("adapter versus native inventory shape")
    if data["alpha"].shape != (nm,) or data["modal"].shape != (n,):
        raise ValueError("complete native port witness shape")
    for label in ("a", "b", "interior", "zero", "scale"):
        for kind in ("x", "forward", "oracle_forward", "adjoint", "oracle_adjoint"):
            if data[label + "_" + kind].shape != (n,):
                raise ValueError("complete native input/output shape")
        if data[label + "_amplitudes"].shape != (nm,):
            raise ValueError("complete ordered amplitude shape")
    # The unit-input structural-zero test is a new witness, not a relabeling
    # of the historical unnormalized failure. Enforce its saved input too.
    if abs(float(np.linalg.norm(data["interior_x"])) - 1.0) > 1e-14:
        raise ValueError("unit internal input witness")
    noninternal = np.setdiff1d(np.arange(n), data["interiors"])
    if np.any(data["interior_x"][noninternal]) or np.any(data["zero_x"]):
        raise ValueError("internal/zero input support")
    if not np.array_equal(data["scale_x"], (0.37 - 0.91j) * data["a_x"]):
        raise ValueError("complex scale input identity")
    checks = [
        dict(kind=k, **metric(data[k + "_native"], data[k + "_from_adapter"]))
        for k in ("C", "D")
    ]
    for label in ("a", "b", "interior", "zero", "scale"):
        for kind in ("forward", "adjoint", "amplitudes"):
            left, right = data[label + "_" + kind], data[label + "_oracle_" + kind]
            if label == "interior":
                # Preregistered structural-zero rule: native polynomial
                # tabulation may have absolute roundoff, never clip it.
                difference = float(np.linalg.norm(left - right))
                checks.append(
                    {
                        "input": label,
                        "kind": kind,
                        "numerator": difference,
                        "denominator": float(np.linalg.norm(right)),
                        "absolute_rule": 1e-12,
                        "passed": bool(difference <= 1e-12),
                    }
                )
            else:
                checks.append(dict(input=label, kind=kind, **metric(left, right)))
        if np.any(data[label + "_x"][data["slaves"]] != 0):
            raise ValueError("nonzero computation slave")
        if label in ("interior", "zero") and np.any(data[label + "_t"]):
            raise ValueError("internal/zero input extracted boundary")
        if label == "zero" and any(
            np.any(data[label + "_" + k]) for k in ("forward", "adjoint", "amplitudes")
        ):
            raise ValueError("zero exact")
    if np.any(data["C_from_adapter"][data["interiors"]]) or np.any(
        data["D_from_adapter"][:, data["interiors"]]
    ):
        raise ValueError("interior boundary dual force")
    checks.append(
        dict(
            kind="complex_linearity",
            **metric(data["scale_forward"], (0.37 - 0.91j) * data["a_forward"]),
        )
    )
    checks.append(
        dict(
            kind="native_boundary_dual",
            **metric(
                np.array([np.vdot(data["b_x"], data["a_forward"])]),
                np.array([np.vdot(data["b_adjoint"], data["a_x"])]),
            ),
        )
    )
    checks.append(
        dict(kind="pure_port_modal", **metric(data["modal"], data["oracle_modal"]))
    )
    checks.append(
        dict(
            kind="extract_conjugate_scatter",
            **metric(data["extract_inner"], data["scatter_inner"]),
        )
    )
    return checks


def native_entity_map_checks(element, layout, description, literal, adapter_arrays):
    """Independent literal cell equations for the sparse adapter E.

    Expand the literal MPC coefficients directly here. This never calls the
    production map constructor or fits the saved map to modal observations.
    """
    from scipy.sparse import csr_matrix

    n, nb = map(int, adapter_arrays["sizes"])
    compact = adapter_arrays["compact_rows"]
    E = csr_matrix(
        (
            adapter_arrays["E_data"],
            adapter_arrays["E_indices"],
            adapter_arrays["E_indptr"],
        ),
        shape=(len(compact), n),
    )
    if nb != layout.rows or E[:, literal["slaves"]].nnz:
        raise ValueError("native adapter independent layout/slave identity")
    checks = []
    offsets = literal["master_offsets"]
    masters = literal["master_rows"]
    dual = literal["master_dual_coefficients"]
    for cell, dofs in enumerate(literal["cell_dofs"]):
        coords = literal["coordinates"][literal["geometry_dofmap"][cell]]
        bounds = np.column_stack((coords.min(axis=0), coords.max(axis=0))).tolist()
        found = [d for d in description["cells"] if d["bounds_nm"] == bounds]
        if len(found) != 1:
            raise ValueError("native checker cell/geometry inventory")
        desc = found[0]
        side = desc["side"]
        i, j, _ = desc["indices"]
        active = layout.polynomial.active[side]
        orientation = np.zeros((element.dim, len(active)))
        orientation[active, np.arange(len(active))] = 1
        element.T_apply(
            orientation.ravel(), len(active), int(literal["permutations"][cell])
        )
        expansion = np.zeros((len(active), n), np.complex128)
        for a, row in enumerate(dofs[active]):
            for k in range(int(offsets[row]), int(offsets[row + 1])):
                expansion[a, int(masters[k])] += dual[k].conjugate()
        expected = orientation[active].T @ expansion
        rows = layout.maps[side][i, j]
        positions = np.searchsorted(compact, rows)
        if np.any(positions >= len(compact)) or not np.array_equal(
            compact[positions], rows
        ):
            raise ValueError("native checker complete boundary entity inventory")
        observed = layout.weights[side][i, j, :, None] * E[positions].toarray()
        checks.append(
            dict(
                kind="independent_native_entity_equation",
                cell=cell,
                **metric(observed, expected),
            )
        )
    return checks


def check_coupled_vectors(data):
    required = {
        "x",
        "y",
        "f",
        "g",
        "alpha",
        "u_storage",
        "u_expanded",
        "slaves",
        "interiors",
        "volume",
        "volume_oracle",
        "full_action",
        "full_action_oracle",
        "adjoint",
        "adjoint_oracle",
        "r_FE",
        "r_port",
        "r_native",
        "B_rport",
        "local_internal_balance",
        "condensed_identity_left",
        "condensed_identity_right",
        "affine_error_correct",
        "affine_error_subtraction",
        "internal_trace_values",
    }
    if not required <= set(data):
        raise ValueError("complete coupled affine inventory")
    if not np.any(data["f"][data["interiors"]]) or not np.any(data["g"]):
        raise ValueError("nonzero internal/port witness required")
    if np.any(data["u_storage"][data["slaves"]]):
        raise ValueError("strict storage slave zero")
    if not data["slaves"].size or not np.any(data["u_expanded"][data["slaves"]]):
        raise ValueError("physical MPC expansion witness missing")
    checks = []
    for key in ("volume", "full_action", "adjoint"):
        checks.append(dict(kind=key, **metric(data[key], data[key + "_oracle"])))
    checks.append(
        dict(
            kind="original_native_augmented_identity",
            **metric(data["r_native"], data["r_FE"] - data["B_rport"]),
        )
    )
    checks.append(
        dict(
            kind="condensed_rhs_restore_identity",
            **metric(data["condensed_identity_left"], data["condensed_identity_right"]),
        )
    )
    checks.append(
        dict(
            kind="homogeneous_affine_recovery",
            **metric(data["affine_error_correct"], data["affine_error_subtraction"]),
        )
    )
    internal = data["local_internal_balance"]
    scale = np.linalg.norm(data["f"][data["interiors"]])
    checks.append(
        {
            "kind": "local_internal_nonzero_rhs",
            "numerator": float(np.linalg.norm(internal)),
            "denominator": float(scale),
            "relative": float(np.linalg.norm(internal) / scale),
            "passed": bool(np.linalg.norm(internal) / scale <= 1e-10),
        }
    )
    checks.append(
        {
            "kind": "interior_boundary_trace",
            "maximum_absolute": float(
                np.max(np.abs(data["internal_trace_values"]), initial=0)
            ),
            "passed": bool(
                np.max(np.abs(data["internal_trace_values"]), initial=0) <= 1e-10
            ),
        }
    )
    return checks
