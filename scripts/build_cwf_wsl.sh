#!/usr/bin/env bash
set -euo pipefail

root_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source_dir="${CWF_SOURCE_DIR:-${root_dir}/external/cwf-src}"
libigl_include="${LIBIGL_INCLUDE:-${root_dir}/external/libigl/include}"
build_dir="${root_dir}/build-wsl-cwf"
patch_file="${root_dir}/patches/cwf-gcc-compat.patch"

test -f "${source_dir}/MAIN/cwf.cpp"
test -f "${libigl_include}/igl/readOBJ.h"

if git -C "${source_dir}" apply --check "${patch_file}" >/dev/null 2>&1; then
  git -C "${source_dir}" apply "${patch_file}"
elif ! git -C "${source_dir}" apply --reverse --check "${patch_file}" >/dev/null 2>&1; then
  echo "CWF compatibility patch neither applies nor is already applied" >&2
  exit 2
fi

cmake -S "${source_dir}" -B "${build_dir}" -G Ninja \
  -DCMAKE_BUILD_TYPE=Release \
  -DLIBIGL_INCLUDE="${libigl_include}" \
  -DCMAKE_CXX_FLAGS=-fpermissive
cmake --build "${build_dir}" --target cwf -j "${BUILD_JOBS:-4}"
mkdir -p "${root_dir}/external/bin"
cp "${build_dir}/MAIN/cwf" "${root_dir}/external/bin/cwf"
