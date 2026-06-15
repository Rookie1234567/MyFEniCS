#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_DIR}"

DOCKER_BIN="${DOCKER_BIN:-docker}"
IMAGE_NAME="${IMAGE_NAME:-code-dolfinx-mpc:latest}"

if ! "${DOCKER_BIN}" image inspect "${IMAGE_NAME}" >/dev/null 2>&1; then
  "${DOCKER_BIN}" build \
    -f fenics_vector_maxwell_floquet_demo_v2_parallel/Dockerfile.mpc \
    -t "${IMAGE_NAME}" \
    fenics_vector_maxwell_floquet_demo_v2_parallel
fi

CMD=(
  "${DOCKER_BIN}" run --rm
  -v "${PROJECT_DIR}:/work"
  -w /work
  "${IMAGE_NAME}"
  sh -lc ". dolfinx-complex-mode && python3 -m fenics_vector_maxwell_floquet_demo_v2_parallel.src.main --constraint-backend manual"
)

printf '将执行 Docker 命令：'
printf ' %q' "${CMD[@]}"
printf '\n'

"${CMD[@]}"
