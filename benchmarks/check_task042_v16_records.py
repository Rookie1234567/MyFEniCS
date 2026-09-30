"""Hash-bound V16 evidence checker; performs no operator action or FE solve."""

import argparse
import json
from pathlib import Path

from src.io.augmented_trace_evidence_check import check_v16
from src.io.augmented_trace_lsqr import read_result
from src.runners.task042_shared import write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    pre, _ = read_result("PREFLIGHT")
    routes = {name: read_result(name)[0] for name in ("ZERO", "GPOLY", "GNN")}
    verify, _ = read_result("VERIFY")
    result = check_v16(pre, routes, verify)
    write_json(args.output, result)
    print(json.dumps(result, ensure_ascii=False))
    return 1 if result["mismatches"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
