from __future__ import annotations

import hashlib

import numpy as np


def _canonical_global_row_ids_fingerprint(indices: np.ndarray) -> str:
    """Fingerprint global row IDs and their order with a fixed wire format."""

    canonical = np.asarray(indices, dtype="<i8")
    if canonical.ndim != 1:
        raise ValueError("canonical global row IDs must be one-dimensional")
    digest = hashlib.sha256()
    digest.update(b"task037.global-row-ids-order.v1|dtype=<i8|order=C\0")
    digest.update(np.asarray([canonical.size], dtype="<u8").tobytes())
    digest.update(canonical.tobytes(order="C"))
    return digest.hexdigest()


def _exact_reuse_necessary_prefix(
    row_ids_sha256: str, shifted_matrix_sha256: str
) -> str:
    """Combine the two necessary exact-reuse fingerprints into one prefix."""

    digest = hashlib.sha256()
    digest.update(b"task037.exact-reuse-necessary-prefix.v1\0")
    digest.update(row_ids_sha256.encode("ascii"))
    digest.update(b"\0")
    digest.update(shifted_matrix_sha256.encode("ascii"))
    return digest.hexdigest()
