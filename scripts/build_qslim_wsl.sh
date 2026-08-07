#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source_root="${root}/downloads/qslim-1_0"
output_root="${root}/external/qslim"
patched_root="${root}/build/qslim-src"

if [[ ! -f "${source_root}/README" ]]; then
  echo "QSlim source is missing: ${source_root}" >&2
  exit 2
fi

mkdir -p "${output_root}"
mkdir -p "${patched_root}"
cmake -E copy_directory "${source_root}" "${patched_root}"
cmake -E copy_if_different "${root}/native/qslim_compat/Buffer.h" \
  "${patched_root}/gfx/tools/Buffer.h"
cd "${patched_root}"

g++ -std=gnu++98 -O2 -fpermissive -DGFX_NO_BOOL -DGFX_DEF_FMATH -DHUGE=HUGE_VAL \
  -I"${root}/native/qslim_compat" -I. \
  qslim/qslim.cxx qslim/cmdline.cxx qslim/avars.cxx \
  qslim/decimate.cxx qslim/quadrics.cxx qslim/AdjPrims.cxx \
  qslim/AdjModel.cxx qslim/Nvars.cxx \
  gfx/math/Mat2.cxx gfx/math/Mat3.cxx gfx/math/Mat4.cxx \
  gfx/math/cholesky.cxx gfx/math/jacobi.cxx gfx/tools/heap.cxx \
  gfx/sys/futils.cxx gfx/sys/timing.cxx \
  gfx/geom/3D.cxx gfx/geom/ProjectH.cxx gfx/geom/ProxGrid.cxx \
  gfx/SMF/smf.cxx gfx/SMF/smfstate.cxx \
  -o "${output_root}/qslim" -lm

"${output_root}/qslim" -s 8 -o "${root}/artifacts/smoke-native/qslim-cube.smf" \
  "${root}/tests/fixtures/qslim_cube.smf"
