from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import time


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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--capture-root", required=True)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--ordering", default="COLAMD")
    args = parser.parse_args()

    capture_root = Path(args.capture_root)
    output_root = Path(args.output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    rows = []
    started = time.perf_counter()
    for slab in range(16):
        output = output_root / f"slab_{slab:03d}"
        command = [
            sys.executable,
            "-m",
            "benchmarks.neural_pc.build_lu_teacher_dataset",
            "--capture-a",
            str(_slab_directory(capture_root, "T1", slab)),
            "--capture-b",
            str(_slab_directory(capture_root, "T2", slab)),
            "--capture-c",
            str(_slab_directory(capture_root, "V", slab)),
            "--capture-d",
            str(_slab_directory(capture_root, "H", slab)),
            "--capture-a-record",
            str(capture_root / "T1" / "solver_record.json"),
            "--capture-b-record",
            str(capture_root / "T2" / "solver_record.json"),
            "--capture-c-record",
            str(capture_root / "V" / "solver_record.json"),
            "--capture-d-record",
            str(capture_root / "H" / "solver_record.json"),
            "--output",
            str(output),
            "--ordering",
            args.ordering,
        ]
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            print(result.stdout[-4000:], file=sys.stderr)
            print(result.stderr[-4000:], file=sys.stderr)
            raise RuntimeError(f"teacher generation failed for slab {slab}")
        manifest = json.loads((output / "dataset.json").read_text(encoding="utf-8"))
        rows.append(
            {
                "slab": slab,
                "operator_fingerprint": manifest["operator_fingerprint"],
                "shape": manifest["teacher"]["size"],
                "matrix_nnz": manifest["teacher"]["matrix_nnz"],
                "factor_nnz": manifest["teacher"]["factor_nnz"],
                "factor_storage_bytes": manifest["teacher"]["factor_storage_bytes"],
                "factorization_s": manifest["teacher"]["factorization_s"],
                "solve_mean_s": manifest["triangular_solve"]["mean_s"],
                "solve_p95_s": manifest["triangular_solve"]["p95_s"],
                "teacher_rho_max": manifest["teacher_rho"]["max"],
                "factor_destroy_confirmed": manifest["factor_destroy_confirmed"],
                "split_counts": manifest["split_counts"],
            }
        )
        print(
            f"slab {slab:02d}: rho_max={manifest['teacher_rho']['max']:.3e}, "
            f"factor_destroyed={manifest['factor_destroy_confirmed']}",
            flush=True,
        )
    summary = {
        "schema": "myfenics.task005.all_slab_lu_teacher.summary.v1",
        "slab_count": len(rows),
        "all_factor_destroy_confirmed": all(
            row["factor_destroy_confirmed"] for row in rows
        ),
        "total_wall_s": time.perf_counter() - started,
        "slabs": rows,
    }
    (output_root / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
