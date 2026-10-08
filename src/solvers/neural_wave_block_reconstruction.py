"""Independent actual point values of the block readout; no ideal-vector shortcut."""

import json
from pathlib import Path

import numpy as np
from scipy import sparse

from src.solvers.neural_wave_greedy import sha
from src.solvers.neural_wave_moments import Patch


def frozen_models(directory, *, include_decay=False):
    directory = Path(directory)
    boundary = json.loads((directory / "committed.json").read_text())
    if boundary["schema"] == "neural-wave.complex-backfit-boundary.v1":
        from src.io.neural_wave_backfit_store import check_boundary

        check_boundary(directory / "committed.json")
    state = directory / boundary["state"]["path"]
    if sha(state) != boundary["state"]["sha256"]:
        raise ValueError("FROZEN_COEFFICIENT_STATE_HASH_FAILED")
    with np.load(state, allow_pickle=False) as arrays:
        a, saved = (np.array(arrays[k]) for k in ("a", "c"))
    models = []
    covered = 0
    block = boundary["schema"] in (
        "neural-wave.complete-block-boundary.v1", "neural-wave.backfit-boundary.v1",
        "neural-wave.complex-backfit-boundary.v1",
    )
    for i, entry in enumerate(boundary["chunks"]):
        file = directory / entry["path"]
        if sha(file) != entry["sha256"]:
            raise ValueError("FROZEN_NETWORK_CHUNK_HASH_FAILED")
        with np.load(file, allow_pickle=False) as arrays:
            patch = Patch(
                tuple(arrays["center"]),
                tuple(arrays["radius"]),
                kind=str(arrays["patch_kind"])
                if "patch_kind" in arrays.files
                else "local",
            )
            q = np.array(arrays["wave_q"])
            decay = (np.array(arrays["decay_kappa"])
                     if "decay_kappa" in arrays.files else np.zeros_like(q))
            if (np.iscomplexobj(q) or np.iscomplexobj(decay) or decay.shape != q.shape
                    or not np.isfinite(decay).all() or not np.isfinite(q).all()):
                raise ValueError("ACTUAL_NETWORK_EXPLICIT_REAL_Q_KAPPA_REQUIRED")
            if not include_decay and np.any(decay != 0):
                raise ValueError("DECAY_MODEL_REQUIRES_DECAY_AWARE_RECONSTRUCTION")
            if block:
                first, last = entry["start"], entry["stop"]
                if first != covered or not first < last <= len(a):
                    raise ValueError("BLOCK_MODEL_COVERAGE_FAILED")
                mapping = np.array(arrays["amplitude_map"])
                if mapping.shape != (3 * len(q), last - first):
                    raise ValueError("BLOCK_AMPLITUDE_LAYOUT_FAILED")
                p = (mapping @ a[first:last]).reshape(-1, 3)
                covered = last
            else:
                p = (
                    (np.array(arrays["amplitude_real"]) + 1j * arrays["amplitude_imag"])
                    * a[i]
                    / float(arrays["scale"])
                )
                covered += 1
            models.append((patch, q, p, decay) if include_decay else (patch, q, p))
    if covered != boundary["columns"] or covered != len(a):
        raise ValueError("FROZEN_NETWORK_COVERAGE_FAILED")
    return models, saved, boundary


def rebuild_stable(directory, packet, marker=lambda *_: None, *, module_first=False):
    models, saved, boundary = frozen_models(directory, include_decay=True)
    interpolation = sparse.csr_matrix(packet["interpolation"])
    c = np.zeros(int(packet["active_rows"]), np.complex128)
    for cell, jac in enumerate(packet["jacobians"]):
        x = packet["origins"][cell] + packet["reference_points"] @ jac.T
        lo, hi = x.min(0), x.max(0)
        total = np.zeros(
            interpolation.shape[0] if module_first else x.shape, np.complex128
        )
        correction = np.zeros_like(total)
        for patch, q, p, decay in models:
            center, radius = np.array(patch.center), np.array(patch.radius)
            if patch.kind != "global" and (
                np.any(hi < center - radius) or np.any(lo > center + radius)
            ):
                continue
            window = patch.window(x)
            selected = window != 0
            raw = np.zeros_like(x, dtype=np.complex128)
            exponent = (x[selected] - center) @ (1j * q - decay).T
            if np.max(abs(exponent.real), initial=0) > 8 + 1e-12:
                raise ValueError("ACTUAL_NETWORK_DECAY_BOUND_EXCEEDED")
            raw[selected] = window[selected, None] * (np.exp(exponent) @ p)
            value = interpolation @ (raw @ jac).T.ravel() if module_first else raw
            updated = total + value
            correction += np.where(
                abs(total) >= abs(value),
                (total - updated) + value,
                (value - updated) + total,
            )
            total = updated
        total += correction
        moments = total if module_first else interpolation @ (total @ jac).T.ravel()
        local = packet["transforms"][packet["orientation_ids"][cell]] @ moments
        rows = packet["owner_rows"][cell]
        c[rows[rows >= 0]] = local[rows >= 0]
        if cell % 32 == 0:
            marker(
                "stable_frozen_model_rebuild",
                dict(
                    cell=cell,
                    cells=len(packet["origins"]),
                    blocks=len(models),
                    columns=boundary["columns"],
                    quadrature=int(packet["quadrature_degree"]),
                    module_first=module_first,
                ),
            )
    return c, saved, boundary


def reconstruction_stability(action, packet, artifact, marker, old_root):
    from src.solvers.neural_wave_greedy import atomic_npz

    records = {}
    for stage in ("v30_m5_fixed_wave", "v30_m5_learned_wave"):
        directory = Path(old_root) / stage / "basis"
        models, saved, boundary = frozen_models(directory)
        state = directory / boundary["state"]["path"]
        with np.load(state, allow_pickle=False) as a:
            amplitudes = np.array(a["a"])
        value = np.zeros_like(saved)
        correction = np.zeros_like(saved)
        norm_sum = 0.0
        max_scale = 0.0
        for i, entry in enumerate(boundary["chunks"]):
            file = directory / entry["path"]
            if sha(file) != entry["sha256"]:
                raise ValueError("FROZEN_BLOCK_HASH_FAILED")
            with np.load(file, allow_pickle=False) as a:
                contribution = np.array(a["u"]) * amplitudes[i]
                max_scale = max(max_scale, abs(amplitudes[i] / float(a["scale"])))
            updated = value + contribution
            correction += np.where(
                abs(value) >= abs(contribution),
                (value - updated) + contribution,
                (contribution - updated) + value,
            )
            value = updated
            norm_sum += float(np.linalg.norm(contribution))
        value += correction
        point, _, _ = rebuild_stable(directory, packet, marker)
        module, _, _ = rebuild_stable(directory, packet, marker, module_first=True)
        old_file = Path(old_root) / "v30_m5_verify" / (stage + "_rebuild.npz")
        with np.load(old_file, allow_pickle=False) as a:
            old = np.array(a["c30"])
        denominator = max(np.linalg.norm(saved), 1e-30)
        worst = int(np.argmax(abs(point - saved)))
        path = Path(artifact) / (stage + "_stable_paths.npz")
        atomic_npz(
            path,
            saved=saved,
            old_point=old,
            compensated_Ua=value,
            point_first=point,
            module_first=module,
        )
        rec = dict(
            original_model_mapping_relative=float(
                np.linalg.norm(old - saved) / denominator
            ),
            compensated_Ua_relative=float(np.linalg.norm(value - saved) / denominator),
            module_first_relative=float(np.linalg.norm(module - saved) / denominator),
            point_first_relative=float(np.linalg.norm(point - saved) / denominator),
            independent_stable_paths_relative=float(
                np.linalg.norm(point - module) / denominator
            ),
            original_action_stable_path_difference=float(
                np.linalg.norm(action.apply(point - module)) / action.bnorm
            ),
            maximum_raw_amplitude_scale=max_scale,
            stored_amplitude_norm=float(np.linalg.norm(amplitudes)),
            coefficient_norm=float(denominator),
            contribution_norm_sum=norm_sum,
            module_cancellation_norm_ratio=norm_sum / denominator,
            worst_coefficient_index=worst,
            worst_absolute_point_error=float(abs(point[worst] - saved[worst])),
            raw_paths=dict(path=str(path), sha256=sha(path)),
            precision="complex128 fixed-order Neumaier accumulation; no extended precision",
            old_bytes_and_failure_unchanged=True,
            qualification_scope="reconstruction diagnosis only; no substitute for complete original-equation/field gates",
        )
        records[stage] = rec
        marker("reconstruction_path_attribution", rec)
    return dict(
        records=records,
        old_training_repeated=False,
        healthy_q30_q60_rebuilds_repeated=False,
        new_stable_q30_diagnostic_paths_only=True,
        reference_read_count=0,
    )
