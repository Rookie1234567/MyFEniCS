#!/usr/bin/env bash
set -euo pipefail

echo "Case092 commands are evidence recipes; run stages manually in task order."
echo "Heavy outputs belong under benchmarks/artifacts/cases/092/."
echo "P0 baseline -> captures A/B/C -> P1 teacher -> P2 oracle."
echo "P3-P7 are locked because the three-slab oracle Gate failed."
