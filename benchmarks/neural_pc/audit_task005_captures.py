from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np

from benchmarks.neural_pc.build_lu_teacher_dataset import _load_raw_capture
from benchmarks.neural_pc.data_contract import load_operator


SPLITS = ("T1", "T2", "V", "H")
EXPECTED_COUNTS = {"T1": 512, "T2": 512, "V": 256, "H": 256}


def _slab_directory(capture_root: Path, split: str, slab: int) -> Path:
    matches = list(
        (capture_root / split / "raw").glob(
            f"rank_*/slab_{slab:03d}"
        )
    )
    if len(matches) != 1:
        raise RuntimeError(
            f"expected one {split} directory for slab {slab}, found {len(matches)}"
        )
    return matches[0]


def _row_digest(row: np.ndarray) -> str:
    contiguous = np.ascontiguousarray(row, dtype=np.complex128)
    return hashlib.sha256(contiguous.view(np.uint8)).hexdigest()


def _near_duplicate_audit(
    rows: dict[str, np.ndarray],
    *,
    device: str,
    slab: int,
) -> dict[str, Any]:
    import torch

    if device.startswith("cuda") and not torch.cuda.is_available():
        raise RuntimeError("CUDA capture audit requested but unavailable")
    torch_device = torch.device(device)
    generator = torch.Generator(device=torch_device)
    generator.manual_seed(20260718 + slab)
    width = next(iter(rows.values())).shape[1]
    sketch_width = min(256, width)
    projection = torch.complex(
        torch.randn(
            width,
            sketch_width,
            device=torch_device,
            dtype=torch.float32,
            generator=generator,
        ),
        torch.randn(
            width,
            sketch_width,
            device=torch_device,
            dtype=torch.float32,
            generator=generator,
        ),
    )
    sketches = {}
    tensors = {}
    for name, values in rows.items():
        tensor = torch.as_tensor(values, dtype=torch.complex64, device=torch_device)
        tensor = tensor / torch.linalg.vector_norm(tensor, dim=1).clamp_min(1e-30)[:, None]
        sketch = tensor @ projection
        sketch = sketch / torch.linalg.vector_norm(sketch, dim=1).clamp_min(1e-30)[:, None]
        tensors[name] = tensor
        sketches[name] = sketch

    pair_rows = []
    near_duplicate_count = 0
    for left_index, left in enumerate(SPLITS):
        for right in SPLITS[left_index + 1 :]:
            similarity = torch.abs(sketches[left] @ sketches[right].mH)
            flat_index = int(torch.argmax(similarity).item())
            right_count = similarity.shape[1]
            left_row, right_row = divmod(flat_index, right_count)
            exact_cosine = float(
                torch.abs(
                    torch.vdot(
                        tensors[left][left_row],
                        tensors[right][right_row],
                    )
                ).item()
            )
            is_near_duplicate = exact_cosine >= 1.0 - 1e-8
            near_duplicate_count += int(is_near_duplicate)
            pair_rows.append(
                {
                    "left": left,
                    "right": right,
                    "screen_max_cosine": float(torch.max(similarity).item()),
                    "screen_argmax": [left_row, right_row],
                    "exact_cosine_at_screen_argmax": exact_cosine,
                    "near_duplicate": is_near_duplicate,
                }
            )
    return {
        "method": "deterministic_256d_complex_JL_screen_then_exact_argmax",
        "threshold": 1.0 - 1e-8,
        "near_duplicate_pair_count": near_duplicate_count,
        "pairs": pair_rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--capture-root", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--device", default="cuda:0")
    args = parser.parse_args()

    capture_root = Path(args.capture_root)
    slab_rows = []
    for slab in range(16):
        operators = {
            split: load_operator(_slab_directory(capture_root, split, slab))
            for split in SPLITS
        }
        fingerprints = {
            split: operator.fingerprint
            for split, operator in operators.items()
        }
        if len(set(fingerprints.values())) != 1:
            raise RuntimeError(f"operator fingerprint mismatch for slab {slab}")
        rhs = {}
        apply_indices = {}
        digests = {}
        for split in SPLITS:
            rhs[split], apply_indices[split] = _load_raw_capture(
                _slab_directory(capture_root, split, slab)
            )
            if len(rhs[split]) != EXPECTED_COUNTS[split]:
                raise RuntimeError(
                    f"{split} slab {slab} count {len(rhs[split])} "
                    f"!= {EXPECTED_COUNTS[split]}"
                )
            if not np.all(np.isfinite(rhs[split])):
                raise RuntimeError(f"{split} slab {slab} contains NaN or Inf")
            digests[split] = {_row_digest(row) for row in rhs[split]}

        overlap_rows = []
        exact_duplicate_count = 0
        schedule_overlap_count = 0
        for left_index, left in enumerate(SPLITS):
            for right in SPLITS[left_index + 1 :]:
                exact_overlap = len(digests[left] & digests[right])
                schedule_overlap = len(
                    set(apply_indices[left].tolist())
                    & set(apply_indices[right].tolist())
                )
                exact_duplicate_count += exact_overlap
                schedule_overlap_count += schedule_overlap
                overlap_rows.append(
                    {
                        "left": left,
                        "right": right,
                        "exact_rhs_duplicates": exact_overlap,
                        "apply_index_overlap": schedule_overlap,
                    }
                )
        near = _near_duplicate_audit(rhs, device=args.device, slab=slab)
        if exact_duplicate_count or schedule_overlap_count or near["near_duplicate_pair_count"]:
            raise RuntimeError(f"capture leakage detected for slab {slab}")
        row = {
            "slab": slab,
            "operator_fingerprint": next(iter(fingerprints.values())),
            "counts": {split: len(rhs[split]) for split in SPLITS},
            "sampling": {
                split: {
                    "first_apply_index": int(apply_indices[split][0]),
                    "last_apply_index": int(apply_indices[split][-1]),
                }
                for split in SPLITS
            },
            "pairwise_overlap": overlap_rows,
            "near_duplicate_audit": near,
        }
        slab_rows.append(row)
        print(
            f"slab {slab:02d}: fingerprint pass, exact/schedule/near overlap = 0",
            flush=True,
        )

    result = {
        "schema": "myfenics.task005.capture_leakage_audit.v1",
        "device": args.device,
        "slab_count": len(slab_rows),
        "all_operator_fingerprints_stable": True,
        "all_expected_counts_present": True,
        "exact_duplicate_count": 0,
        "schedule_overlap_count": 0,
        "near_duplicate_pair_count": 0,
        "slabs": slab_rows,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(result, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    print(json.dumps({key: value for key, value in result.items() if key != "slabs"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
