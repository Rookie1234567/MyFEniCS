#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -ne 3 ]; then
  echo "usage: run_capture.sh <T1|T2|V|H> <sample-limit> <stride>" >&2
  exit 2
fi

split="$1"
limit="$2"
stride="$3"
case "$split" in
  T1|T2|V|H) ;;
  *) echo "invalid split identity: $split" >&2; exit 2 ;;
esac

root="/mnt/c/Users/Administrator/Desktop/MyProject"
cd "$root"
if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
  echo "tracked source must be clean before an independent capture" >&2
  exit 2
fi
sha="$(git rev-parse HEAD)"
branch="$(git branch --show-current)"
target="$root/benchmarks/artifacts/cases/094/captures/$split"
if [ -e "$target" ]; then
  echo "refusing to overwrite capture: $target" >&2
  exit 2
fi
mkdir -p "$target"

export BENCHMARK_COMMIT_SHA="$sha"
export BENCHMARK_VERIFIED_CLEAN_SHA="$sha"
export BENCHMARK_BRANCH="$branch"
export BENCHMARK_EXACT_COMMAND="Case094 independent raw capture $split"
export OMP_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export MKL_NUM_THREADS=1
export NUMEXPR_NUM_THREADS=1

mpiexec -n 4 /home/fenics/.local/bin/myfenics-python-complex \
  -m benchmarks.run_workstation_iterative \
  --h-nm 5 \
  --num-slabs 16 \
  --overlap-layers 0.25 \
  --ilu-levels 0 \
  --ksp-type fgmres \
  --smoother-ksp-type gmres \
  --smoother-iterations 2 \
  --restart 90 \
  --max-it 1200 \
  --rtol 1e-6 \
  --rta-threshold 1.1e-6 \
  --monitor-stride 50 \
  --case-label "para_task005_capture_${split}" \
  --record "$target/solver_record.json" \
  --results-dir "$target/heavy" \
  --post-smooth \
  --subdomain-local-shift \
  --factor-only-storage \
  --compact-lifecycle \
  --neural-capture-dir "$target/raw" \
  --neural-capture-limit "$limit" \
  --neural-capture-stride "$stride" \
  --neural-capture-raw-rhs-only
