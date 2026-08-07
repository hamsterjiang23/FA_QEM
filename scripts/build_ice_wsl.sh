#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ice_source="/mnt/c/Users/admin/.cache/checkouts/github.com/HTDerekLiu/intrinsic-simplification"

if [[ ! -f "${ice_source}/README.md" ]]; then
  echo "ICE checkout is missing: ${ice_source}" >&2
  exit 2
fi
if [[ ! -f "${ice_source}/externals/libigl/CMakeLists.txt" ]]; then
  echo "ICE libigl submodule is not initialized" >&2
  exit 3
fi

cmake -S "${root}/native/ice_adapter" -B "${root}/build-wsl-ice" -G Ninja \
  -DICE_SOURCE_ROOT="${ice_source}" -DCMAKE_BUILD_TYPE=Release
cmake --build "${root}/build-wsl-ice" --parallel 12
mkdir -p "${root}/external/bin"
cmake -E copy_if_different "${root}/build-wsl-ice/bin/ice_coarsening" \
  "${root}/external/bin/ice_coarsening"

