"""Saved-space coverage and affine port derivatives, without reference feedback."""

import json
from pathlib import Path

import numpy as np
from scipy import sparse

from src.io.neural_wave_campaign import ROOT, digest
from src.solvers.neural_wave_greedy import atomic_npz

OLD = ROOT / "benchmarks/artifacts/task42extra/v31"


def audit_support(action, packet, design, artifact, marker):
    identity_file = ROOT / design["support_audit"]["identity_path"]
    if digest(identity_file) != design["support_audit"]["identity_sha256"]:
        raise ValueError("ORIGINAL_MODE_IDENTITY_CHANGED")
    modes = json.loads(identity_file.read_text())["identity"]["modes"]
    bottom = np.array([m["side"] == "bottom" for m in modes])
    a = action.a
    P = sparse.csr_matrix(
        (a["dv"] / a["H"][a["dp"]], (a["dp"], a["dr"])), shape=(action.np, action.size)
    )
    output = {}
    for stage in ("v31_fixed_block_wave", "v31_learned_block_wave"):
        directory = OLD / stage / "basis"
        file = directory / "committed.json"
        bound = json.loads(file.read_text())
        if digest(file) != design["support_audit"][stage]:
            raise ValueError("OLD_BOUNDARY_CHANGED")
        nonzero_local = np.zeros(action.nc * action.dim, bool)
        nonzero_master = np.zeros(action.size, bool)
        row_energy = np.zeros(action.nc * action.dim)
        gram = np.zeros((int(bottom.sum()), int(bottom.sum())), complex)
        scales, cell_nnz, patches = [], [], []
        derivative_nonzero = False
        for i, entry in enumerate(bound["chunks"]):
            p = directory / entry["path"]
            if digest(p) != entry["sha256"]:
                raise ValueError("OLD_COLUMN_HASH_CHANGED")
            with np.load(p, allow_pickle=False) as z:
                U = np.array(z["u"])
                local = np.zeros((action.nc * action.dim, U.shape[1]), complex)
                np.add.at(local, a["erows"], a["evals"][:, None] * U[a["eids"]])
                nonzero_local |= np.any(local != 0, axis=1)
                nonzero_master |= np.any(U != 0, axis=1)
                row_energy += np.sum(abs(local) ** 2, axis=1)
                derivative = P @ U
                derivative_nonzero |= bool(np.any(derivative[bottom] != 0))
                gram += derivative[bottom] @ derivative[bottom].conj().T
                scales.extend(np.linalg.norm(U, axis=0).tolist())
                cell_nnz.append(np.count_nonzero(np.any(local != 0, axis=1)))
                patches.append(
                    dict(
                        level=int(z["patch_level"]),
                        center=z["center"].tolist(),
                        radius=z["radius"].tolist(),
                        retained=U.shape[1],
                        bottom_derivative_max=float(
                            np.max(abs(derivative[bottom]), initial=0)
                        ),
                    )
                )
            if i % 32 == 0:
                marker(
                    "saved_space_support_stream",
                    dict(stage=stage, chunk=i, chunks=len(bound["chunks"])),
                )
        missing = np.flatnonzero(~nonzero_local.reshape(action.nc, action.dim).any(1))
        sv = np.sqrt(np.maximum(np.linalg.eigvalsh(gram), 0))[::-1]
        state = directory / bound["state"]["path"]
        if digest(state) != bound["state"]["sha256"]:
            raise ValueError("OLD_FIELD_STATE_CHANGED")
        with np.load(state, allow_pickle=False) as z:
            c = np.array(z["c"])
        fields = {}
        area = np.prod(
            np.diff(np.array(design["model"]["geometry"]["bounds_nm"])[:2], axis=1)
        )
        incident_power = 0.5 * area * np.sin(np.deg2rad(1))
        for name, field in (("zero_scattering", np.zeros_like(c)), ("candidate", c)):
            alpha = action.alpha(field)
            total = alpha + a["background_alpha"]
            power = []
            for j, mode in enumerate(modes):
                kz = complex(mode["k_vector"][2]["real"], mode["k_vector"][2]["imag"])
                zref = design["model"]["geometry"]["bounds_nm"][2][
                    1 if mode["side"] == "top" else 0
                ]
                power.append(
                    max(0, mode["power_per_unit_amplitude"])
                    * abs(total[j] * np.exp(1j * kz * zref)) ** 2
                    / incident_power
                )
            fields[name] = dict(
                alpha_bottom=alpha[bottom],
                alpha_total_bottom=total[bottom],
                T=float(np.sum(np.array(power)[bottom])),
            )
        fields["background"] = dict(alpha_bottom=a["background_alpha"][bottom])
        path = Path(artifact) / (stage + "_support.npz")
        atomic_npz(
            path,
            exactly_nonzero_local=nonzero_local.reshape(action.nc, action.dim),
            row_energy=row_energy.reshape(action.nc, action.dim),
            zero_cells=missing,
            bottom_derivative_gram=gram,
            bottom_mask=bottom,
            cell_centers=packet["origins"] + packet["jacobians"].sum(axis=2) / 2,
        )
        output[stage] = dict(
            columns=bound["columns"],
            boundary_sha256=digest(file),
            state_sha256=digest(state),
            candidate_source=bound["binding"]["source_sha"],
            exact_zero_cells=missing.tolist(),
            exact_zero_master_count=int((~nonzero_master).sum()),
            local_family_nonzero_counts=dict(
                edge=int(nonzero_local.reshape(action.nc, -1)[:, :36].sum()),
                face=int(nonzero_local.reshape(action.nc, -1)[:, 36:108].sum()),
                interior=int(nonzero_local.reshape(action.nc, -1)[:, 108:].sum()),
            ),
            bottom_PU_exactly_zero=not derivative_nonzero,
            bottom_PU_frobenius=float(np.sqrt(np.trace(gram).real)),
            bottom_singular_estimates=sv,
            diagnostic_rank_rcond=1e-12,
            diagnostic_rank=int(np.count_nonzero(sv > 1e-12 * sv[0]))
            if sv[0] > 0
            else 0,
            rank_method="small port Gram eigenspectrum; numerical diagnostic, not exact rank",
            scale_min=min(scales),
            scale_max=max(scales),
            patches=patches,
            fields=fields,
            support_arrays=dict(path=str(path.relative_to(ROOT)), sha256=digest(path)),
        )
    return dict(
        reference_loaded=False,
        amplitude_threshold_used=False,
        structural_test="exact complex128 nonzero after full MPC expansion once",
        affine_derivative="P=H^-1 D; alpha(0) is excluded from PU",
        routes=output,
    )


def reference_zero_cell_bound(frozen, design):
    # Separate scoring role: nothing from this reference process goes to training.
    previous = json.loads((OLD / "v31_block_reconstruct/result.json").read_text())
    path = ROOT / previous["raw_complete_fields"]["path"]
    if digest(path) != previous["raw_complete_fields"]["sha256"]:
        raise ValueError("SAVED_REFERENCE_SAMPLES_CHANGED")
    with np.load(path, allow_pickle=False) as z:
        energy = np.sum(
            z["weights"]
            * (
                np.sum(abs(z["REFERENCE_E"]) ** 2, axis=-1)
                + 25 * np.sum(abs(z["REFERENCE_curl"]) ** 2, axis=-1)
            ),
            axis=1,
        )
    return dict(
        reference_read_only_scoring_process=True,
        reference_samples_sha256=digest(path),
        routes={
            name: dict(
                strict_zero_cells=item["exact_zero_cells"],
                squared_G_error_discrete_lower_bound=float(
                    energy[item["exact_zero_cells"]].sum()
                ),
                reference_squared_G_norm=float(energy.sum()),
                does_not_prove_sufficiency=not bool(item["exact_zero_cells"]),
            )
            for name, item in frozen["routes"].items()
        },
        reference_feedback_to_training=False,
    )


def direction_witness(action, packet, design, artifact, marker):
    from src.solvers.neural_wave_block import BlockWaveSubspace, BlockBasisStore
    from src.solvers.neural_wave_moments import WaveMoments
    from src.solvers.neural_wave_greedy import (
        direction_dictionary,
        select_patch,
        variable_projection,
    )
    from src.solvers.neural_wave_multiscale import MultiscaleSupportPolicy

    directory = OLD / "v31_learned_block_wave/basis"
    b = json.loads((directory / "committed.json").read_text())
    space = BlockWaveSubspace(action, b["columns"])
    BlockBasisStore(directory, b["binding"]).restore(space, np.random.default_rng(0))
    moments = WaveMoments(packet, 8)
    policy = MultiscaleSupportPolicy(design["model"]["geometry"], moments)
    sensitivity = action.apply(space.r, adjoint=True)
    selected, _, _ = policy.preselect(sensitivity, 32)
    candidates = [
        policy.global_patch,
        policy.global_patch,
        selected[1],
        selected[3],
        selected[4],
        select_patch(policy.pools[2], moments, space.r, 0),
        policy.ports[0],
        policy.ports[-1],
    ]
    dictionary = direction_dictionary(2 * np.pi / 5, 12)
    output = []
    for i, p in enumerate(candidates):
        # Frozen eight-role recipe: incident except global reflected. 8*3 =24.
        q = dictionary[[22 if i == 1 else 21]]
        v = variable_projection(action, space, moments, p, q, gradient=False)
        rows = np.unique(moments.rows[moments.cells(p)])
        rows = rows[rows >= 0]
        from dataclasses import asdict

        output.append(
            dict(
                role=design["support_audit"]["witness_roles"][i],
                patch=asdict(p),
                q=q,
                projected_score=v[0],
                score_load_scaled=v[0] / action.bnorm**2,
                AH_preselection=float(
                    np.vdot(sensitivity[rows], sensitivity[rows]).real
                )
                / max(1, len(rows)),
                residual_preselection=float(np.vdot(space.r[rows], space.r[rows]).real)
                / max(1, len(rows)),
            )
        )
        marker("unlabelled_direction_witness", output[-1])
    return dict(
        full_amplitude_columns=24,
        accepted_updates=0,
        reference_loaded=False,
        old_boundary_sha256=digest(directory / "committed.json"),
        directions=output,
        counts=action.counts,
    )
