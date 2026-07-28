#!/usr/bin/env bash
set -euo pipefail

readonly EXPECTED_BRANCH="codex/only-one-13p5nm-surrogate-inversion"
readonly EXPECTED_ORIGIN="https://github.com/Rookie1234567/MyFEniCS.git"
readonly DOLFINX_DEB_VERSION="1:0.10.0.post3-2~ppa2~noble7"
readonly MPC_TAG="v0.10.1"
readonly MPC_COMMIT="a444aa3006fdf492091443cc8c885c1eec006c2f"
# 0.11 is the first release line with PEP 639 license-expression support,
# which dolfinx_mpc v0.10.1 requires via `project.license = "MIT"`.
readonly SCIKIT_BUILD_CORE_VERSION="0.11.1"
# Match the nanobind ABI used by the pinned FEniCS PPA DOLFINx package.  A
# separately built extension can link the same libdolfinx yet still reject
# DOLFINx Python objects when its nanobind internals ABI differs.
readonly NANOBIND_VERSION="2.9.2"

usage() {
  cat <<'EOF'
Usage:
  scripts/install_local_wsl_environment.sh --check
  sudo scripts/install_local_wsl_environment.sh --system
  scripts/install_local_wsl_environment.sh --user

--system changes Ubuntu packages and must be run by the user with sudo.
--user never uses sudo; it creates the ignored project .venv and builds the
fixed dolfinx_mpc source into a project-local complex prefix.
EOF
}

die() {
  echo "ERROR: $*" >&2
  exit 2
}

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"

require_wsl_repo_identity() {
  grep -qi microsoft /proc/sys/kernel/osrelease || die "native WSL2 is required"
  [[ "${repo_root}" != /mnt/* ]] || die "repository must be on the WSL Linux filesystem"
  [[ "$(git -c safe.directory="${repo_root}" -C "${repo_root}" \
      rev-parse --show-toplevel)" == "${repo_root}" ]] \
    || die "repository root identity failed"
  [[ "$(git -c safe.directory="${repo_root}" -C "${repo_root}" \
      remote get-url origin)" == "${EXPECTED_ORIGIN}" ]] \
    || die "unexpected origin"
  [[ "$(git -c safe.directory="${repo_root}" -C "${repo_root}" \
      branch --show-current)" == "${EXPECTED_BRANCH}" ]] \
    || die "unexpected branch"
  [[ "$(git -c safe.directory="${repo_root}" -C "${repo_root}" \
      rev-parse --abbrev-ref --symbolic-full-name '@{u}')" \
      == "origin/${EXPECTED_BRANCH}" ]] || die "unexpected upstream"
  # The task outputs created before qualification may be uncommitted. System
  # installation is allowed, but formal FEM remains blocked until source-clean.
}

require_noble() {
  # shellcheck disable=SC1091
  source /etc/os-release
  [[ "${ID}" == "ubuntu" && "${VERSION_CODENAME}" == "noble" ]] \
    || die "this qualified recipe requires Ubuntu 24.04 Noble"
}

system_install() {
  [[ "${EUID}" -eq 0 ]] || die \
    "system phase requires root; run: sudo ${repo_root}/scripts/install_local_wsl_environment.sh --system"
  require_noble
  echo "Installing the qualified native WSL package stack; Docker is not used."
  export DEBIAN_FRONTEND=noninteractive
  apt-get update
  apt-get install -y --no-install-recommends \
    ca-certificates software-properties-common
  add-apt-repository -y ppa:fenics-packages/fenics
  apt-get update

  local candidate
  candidate="$(apt-cache policy python3-dolfinx-complex \
    | awk '/Candidate:/ {candidate=$2} END {print candidate}')"
  [[ "${candidate}" == "${DOLFINX_DEB_VERSION}" ]] \
    || die "unexpected python3-dolfinx-complex candidate: ${candidate}"

  apt-get install -y --no-install-recommends \
    "python3-dolfinx-complex=${DOLFINX_DEB_VERSION}" \
    "libdolfinx-complex-dev=${DOLFINX_DEB_VERSION}" \
    python3-petsc4py-complex python3-slepc4py-complex python3-mpi4py \
    libpetsc-complex3.19-dev libslepc-complex3.19-dev libmumps-dev \
    openmpi-bin libopenmpi-dev \
    python3.12-venv python3-pip python3-wheel python3-setuptools \
    python3-cffi python3-gmsh python3-scipy python3-pytest python3-pyvista \
    cmake ninja-build g++ gfortran pkg-config git

  echo "System phase complete. Return to the normal WSL user and run:"
  echo "  ${repo_root}/scripts/install_local_wsl_environment.sh --user"
}

system_gate() {
  local package
  for package in \
    python3-dolfinx-complex libdolfinx-complex-dev \
    python3-petsc4py-complex python3-slepc4py-complex python3-mpi4py \
    openmpi-bin cmake ninja-build python3-pyvista; do
    dpkg-query -W -f='${db:Status-Status}' "${package}" 2>/dev/null \
      | grep -qx installed || die "missing system package: ${package}"
  done
  [[ "$(dpkg-query -W -f='${Version}' python3-dolfinx-complex)" \
      == "${DOLFINX_DEB_VERSION}" ]] || die "DOLFINx package version drift"
  [[ -d /usr/lib/petscdir/petsc3.19/x86_64-linux-gnu-complex ]] \
    || die "complex PETSc 3.19 directory missing"
  [[ -d /usr/lib/slepcdir/slepc3.19/x86_64-linux-gnu-complex ]] \
    || die "complex SLEPc 3.19 directory missing"
}

user_install() {
  [[ "${EUID}" -ne 0 ]] || die "user phase must not run as root"
  system_gate

  cd -- "${repo_root}"
  if [[ ! -f .venv/bin/activate ]]; then
    /usr/bin/python3 -m venv --system-site-packages .venv
  fi
  # shellcheck disable=SC1091
  source .venv/bin/activate
  export PETSC_DIR=/usr/lib/petscdir/petsc3.19/x86_64-linux-gnu-complex
  export SLEPC_DIR=/usr/lib/slepcdir/slepc3.19/x86_64-linux-gnu-complex
  export PATH="${VIRTUAL_ENV}/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
  unset PYTHONHOME

  python -m pip install --disable-pip-version-check \
    "scikit-build-core==${SCIKIT_BUILD_CORE_VERSION}" \
    "nanobind==${NANOBIND_VERSION}"

  local source_dir="${VIRTUAL_ENV}/src/dolfinx_mpc-${MPC_TAG}"
  local build_dir="${VIRTUAL_ENV}/build/dolfinx_mpc-${MPC_TAG}"
  local prefix="${VIRTUAL_ENV}/dolfinx_mpc-complex"
  mkdir -p -- "$(dirname -- "${source_dir}")" "${build_dir}"
  if [[ ! -d "${source_dir}/.git" ]]; then
    git clone --filter=blob:none --no-checkout \
      https://github.com/jorgensd/dolfinx_mpc.git "${source_dir}"
    git -C "${source_dir}" checkout --detach "${MPC_COMMIT}"
  fi
  [[ "$(git -C "${source_dir}" rev-parse HEAD)" == "${MPC_COMMIT}" ]] \
    || die "dolfinx_mpc source identity mismatch"
  [[ -z "$(git -C "${source_dir}" status --short)" ]] \
    || die "dolfinx_mpc source tree is dirty"

  cmake -S "${source_dir}/cpp" -B "${build_dir}/cpp" -G Ninja \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_INSTALL_PREFIX="${prefix}" \
    -DCMAKE_INSTALL_RPATH_USE_LINK_PATH=ON
  cmake --build "${build_dir}/cpp" --parallel 1
  cmake --install "${build_dir}/cpp"

  export CMAKE_PREFIX_PATH="${prefix}"
  export LD_LIBRARY_PATH="${prefix}/lib${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}"
  python -m pip install --disable-pip-version-check --no-deps \
    --no-build-isolation --config-settings=cmake.build-type=Release \
    --force-reinstall "${source_dir}/python"

  source "${repo_root}/scripts/activate_myfenics_surrogate_wsl.sh"
  python - <<'PY'
import pathlib
import numpy as np
from petsc4py import PETSc
import dolfinx
import dolfinx_mpc

assert np.dtype(PETSc.ScalarType) == np.dtype(np.complex128)
root = pathlib.Path.cwd().resolve()
assert pathlib.Path(dolfinx_mpc.__file__).resolve().is_relative_to(root / ".venv")
print("qualified user environment:", dolfinx.__version__, dolfinx_mpc.__file__)
PY
}

check_only() {
  require_noble
  system_gate
  [[ -x "${repo_root}/.venv/bin/python" ]] || die "project .venv is missing"
  # shellcheck disable=SC1091
  source "${repo_root}/scripts/activate_myfenics_surrogate_wsl.sh"
  python -c 'import numpy as np; from petsc4py import PETSc; import dolfinx,dolfinx_mpc; assert np.dtype(PETSc.ScalarType) == np.dtype(np.complex128)'
  echo "environment check passed"
}

[[ $# -eq 1 ]] || { usage >&2; exit 2; }
require_wsl_repo_identity
case "$1" in
  --system) system_install ;;
  --user) user_install ;;
  --check) check_only ;;
  -h|--help) usage ;;
  *) usage >&2; exit 2 ;;
esac
