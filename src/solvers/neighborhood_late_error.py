"""V44 opt-in: actual post-64 error labels and equal full error/residual loss.

No teacher inverse, reference reader, new action or change to V43 semantics.
"""

import numpy as np
import torch

from src.solvers.neighborhood_residual_models import _OriginalAction


def squared_ratio(error, target):
    """Exact zero denominator uses absolute squared error; never an arbitrary floor."""
    numerator = torch.sum(error.abs() ** 2, dim=1)
    denominator = torch.sum(target.abs() ** 2, dim=1)
    return numerator / torch.where(
        denominator == 0, torch.ones_like(denominator), denominator
    )


def late_loss(model, residual, label, action, *, mixed, independent):
    delta = model(residual)
    equation_error = residual - _OriginalAction.apply(delta, action)
    qr2 = squared_ratio(equation_error, residual)
    if label is None:
        if mixed:
            raise ValueError(
                "mixed loss requires the authorized train/validation label"
            )
        qe2 = torch.zeros_like(qr2)
    else:
        qe2 = squared_ratio(
            delta[:, independent] - label[:, independent], label[:, independent]
        )
    per = (qr2 + qe2 if mixed else qr2) / 2
    return per.mean(), delta, qr2, qe2


def label_identity(action, rhs, prefix, label):
    """Cancellation reported on both operation and small-result scales."""
    ap = action.apply(prefix)
    residual = rhs - ap
    ad = action.apply(label)
    numerator = float(np.linalg.norm(residual - ad))
    operation = float(np.linalg.norm(rhs) + np.linalg.norm(ap) + np.linalg.norm(ad))
    result = float(np.linalg.norm(residual))
    return residual, {
        "numerator": numerator,
        "operation_denominator": operation,
        "operation_relative": numerator / operation if operation else None,
        "result_denominator": result,
        "result_relative": numerator / result if result else None,
        "passed": numerator <= 1e-10 * operation if operation else numerator == 0,
    }


def frozen_reader(dataset, split, read_arrays, *, labels):
    if split not in ("train", "validation"):
        raise ValueError("V44 opt-in label reader accepts train/validation only")
    values = read_arrays(dataset["prefix"][split])
    if labels:
        allowed = read_arrays(dataset["labels"][split])
        values.update(label=allowed["label"], error=allowed["error"])
    return values


def choose_checkpoint(checkpoints, *, residual_only):
    if residual_only:
        return min(checkpoints, key=lambda p: (p["median_qr"], p["update"]))
    return min(
        checkpoints,
        key=lambda p: (p["median_qe"], p["max_qe"], p["median_qr"], p["update"]),
    )
