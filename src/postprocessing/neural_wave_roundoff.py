"""Selected-entry attribution, not a higher-precision field or training solve."""

from decimal import Decimal, localcontext
import json
from pathlib import Path

import numpy as np
from scipy import sparse

from src.solvers.neural_wave_greedy import sha
from src.solvers.neural_wave_moments import Patch


def decimal_sum(terms):
    with localcontext() as context:
        context.prec = 110
        real = sum((Decimal.from_float(float(v.real)) for v in terms), Decimal(0))
        imag = sum((Decimal.from_float(float(v.imag)) for v in terms), Decimal(0))
        return complex(float(real), float(imag)), dict(
            real=str(real), imag=str(imag), precision=110
        )


def selected_entry_witness(packet, stability, old_root):
    records = {}
    for stage, item in stability["records"].items():
        row = item["worst_coefficient_index"]
        owners = np.argwhere(packet["owner_rows"] == row)
        if owners.shape != (1, 2):
            raise ValueError("UNIQUE_ORIGINAL_ENTITY_OWNER_REQUIRED")
        cell, local_index = map(int, owners[0])
        jac = packet["jacobians"][cell]
        x = packet["origins"][cell] + packet["reference_points"] @ jac.T
        interpolation = sparse.csr_matrix(packet["interpolation"])
        transform = packet["transforms"][packet["orientation_ids"][cell]]
        directory = Path(old_root) / stage / "basis"
        boundary = json.loads((directory / "committed.json").read_text())
        state = directory / boundary["state"]["path"]
        if sha(state) != boundary["state"]["sha256"]:
            raise ValueError("FROZEN_COEFFICIENT_STATE_CHANGED")
        with np.load(state, allow_pickle=False) as arrays:
            a, saved = (np.array(arrays[k]) for k in ("a", "c"))
        stored_terms = []
        unscaled_terms = []
        model_terms = []
        raw_sum = np.zeros_like(x, dtype=complex)
        active = 0
        for i, entry in enumerate(boundary["chunks"]):
            path = directory / entry["path"]
            if sha(path) != entry["sha256"]:
                raise ValueError("FROZEN_NETWORK_CHUNK_CHANGED")
            with np.load(path, allow_pickle=False) as arrays:
                stored_terms.append(complex(arrays["u"][row] * a[i]))
                patch = Patch(tuple(arrays["center"]), tuple(arrays["radius"]))
                q = np.array(arrays["wave_q"])
                p = np.array(arrays["amplitude_real"]) + 1j * arrays["amplitude_imag"]
                scale = float(arrays["scale"])
            window = patch.window(x)
            if not np.any(window):
                unscaled_terms.append(0j)
                model_terms.append(0j)
                continue
            active += 1
            wave = np.exp(1j * (x - np.array(patch.center)) @ q.T)
            before = transform @ (
                interpolation @ ((window[:, None] * (wave @ p)) @ jac).T.ravel()
            )
            raw = window[:, None] * (wave @ (p * a[i] / scale))
            after = transform @ (interpolation @ (raw @ jac).T.ravel())
            unscaled_terms.append(complex(before[local_index] / scale * a[i]))
            model_terms.append(complex(after[local_index]))
            raw_sum += raw
        stored, ds = decimal_sum(stored_terms)
        before, db = decimal_sum(unscaled_terms)
        after, da = decimal_sum(model_terms)
        point = complex(
            (transform @ (interpolation @ (raw_sum @ jac).T.ravel()))[local_index]
        )
        records[stage] = dict(
            row=row,
            owner_cell=cell,
            local_moment_index=local_index,
            active_modules=active,
            stored_Ua_decimal110=ds,
            interpolate_before_global_readout_decimal110=db,
            amplitude_readout_before_interpolation_decimal110=da,
            saved_vs_exact_stored_terms_absolute=abs(complex(saved[row]) - stored),
            normalization_and_basis_construction_absolute=abs(before - stored),
            amplitude_scaling_before_interpolation_absolute=abs(after - before),
            point_accumulation_and_final_interpolation_absolute=abs(point - after),
            sum_absolute_stored_terms=float(sum(abs(v) for v in stored_terms)),
            sum_absolute_model_terms=float(sum(abs(v) for v in model_terms)),
            identity="same original modules and unique owner; only one worst coefficient",
            interpretation="separates quantized stored-basis sum, basis normalization, amplitude scaling, and point summation; not a full-vector causal bound",
            new_field_or_training_precision=False,
            reference_read_count=0,
        )
    return dict(
        records=records,
        scope="one selected worst coefficient per old route; Decimal110 only for sums of retained IEEE terms",
        old_vectors_unchanged=True,
    )
