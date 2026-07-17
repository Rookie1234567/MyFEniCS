#!/usr/bin/env bash
set -euo pipefail

echo "Case093 is a gated evidence recipe; execute each stage manually."
echo "Required order: clean baseline -> operator capture -> factor census -> G4 -> G8 -> G16 two-step -> conditional G16 one-step."
echo "Formal runs use benchmarks.run_task031_memory_forensics with MPI4, FGMRES90, h5, overlap0.25, ILU0, post-smooth, local shift and factor-only storage."
echo "G4 exact slabs: 0,5,10,15"
echo "G8 exact slabs: 0,2,5,7,8,10,13,15"
echo "G16 exact slabs: 0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15"
echo "Do not run model training, h3 or h2 in PARA-Task004."
