#!/usr/bin/env bash
set -euo pipefail

readonly EXPECTED_BRANCH="codex/only-one-13p5nm-surrogate-inversion"
readonly EXPECTED_ORIGIN="https://github.com/Rookie1234567/MyFEniCS.git"

root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
[[ "$(git -C "${root}" branch --show-current)" == "${EXPECTED_BRANCH}" ]] || {
  echo "ERROR: refusing to install guards on another branch" >&2
  exit 2
}
[[ "$(git -C "${root}" remote get-url origin)" == "${EXPECTED_ORIGIN}" ]] || {
  echo "ERROR: refusing to install guards for another origin" >&2
  exit 2
}
[[ "$(git -C "${root}" rev-parse --abbrev-ref --symbolic-full-name '@{u}')" \
    == "origin/${EXPECTED_BRANCH}" ]] || {
  echo "ERROR: refusing to install guards with another upstream" >&2
  exit 2
}

install_hook() {
  local name="$1"
  local source_path="${root}/.githooks/task000/${name}"
  local target_path="${root}/.git/hooks/${name}"
  if [[ -e "${target_path}" ]] && ! cmp -s "${source_path}" "${target_path}"; then
    if ! grep -q 'TASK000_GUARD_ID="myfenics-surrogate-task000-v1"' \
        "${target_path}"; then
      echo "ERROR: existing ${target_path} is not a Task000 guard; inspect it before replacement" >&2
      exit 2
    fi
  fi
  install -m 0755 "${source_path}" "${target_path}"
}

git -C "${root}" config --local push.default simple
git -C "${root}" config --local pull.ff only
git -C "${root}" config --local --replace-all remote.origin.push \
  "HEAD:refs/heads/${EXPECTED_BRANCH}"
install_hook pre-commit
install_hook pre-push

echo "Task000 Git guards installed for ${EXPECTED_BRANCH}."
