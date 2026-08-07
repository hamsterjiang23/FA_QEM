# Implementation notes

## Deviations

- `codegraph init -i` exceeded the 120-second foreground timeout, but left a live indexing process and a populated `.codegraph` database. The process is being left to finish rather than terminated; health will be checked before using the index.

## Discovered edge cases

- The source GLB contains attribute-split seam vertices; topology checks must use the canonical welded geometry view while texture transfer keeps the original corner attributes.
- `pueue` is not installed, so long jobs cannot yet use the planned persistent queue. Install it before production sweeps or use the harness resume records conservatively.
- The user added a GitHub synchronization requirement after implementation began. Core source and reproducibility metadata will be pushed; models, third-party code/binaries, and generated artifacts remain excluded.
- Concurrent `uv run` commands raced while initializing the user-level cache on Windows. Verification commands now use the project-local `.uv-cache` and run sequentially.
- Trimesh component splitting needs its optional `networkx` dependency on this input. It is now an explicit locked runtime dependency rather than an undeclared environment assumption.
- QEM4VR's ACM endpoint was inaccessible, but the complete author-uploaded text was later found through ResearchGate. It publishes `W_b=5`, `W_t=1000`, per-endpoint curve curvature, subset placement, complex-boundary rejection, and material-constrained closest attribute transfer; the implementation was revised to match those details.
- STMW's first executable checkpoint used component-aware spatial vertex proximity for virtual-edge discovery. It has since been replaced by expanded-AABB candidate generation followed by exact triangle-to-triangle distance tests.
- WSL 2 was adopted as the primary C++ build environment after the user authorized it. The minimal build toolchain is GCC 11.4, CMake, Ninja, and Eigen; Windows remains the host orchestrator.
- QSlim 1.0 predates standard C++ headers and two-phase template lookup. The official source remains immutable; tracked compatibility headers are overlaid onto an ignored build copy. Its bundled SMF fixtures use CRLF and are normalized to LF only for the smoke test.
- ICE's shared `src` directory includes `bake_texture.cpp`, which unnecessarily depends on Polyscope's stb layout. The headless adapter excludes that unrelated translation unit while compiling every coarsening-core source unchanged.
- RobustLPM's shipped CLI exposes an undocumented-in-the-plan `-f` final-face cap. The adapter uses it directly with `-n 100`; this replaces the planned 1..400 precision search unless the cap misses the 2% tolerance.
- The first centralized CWF cache was corrupt: checkout reported missing Git object SHA-1s. A clean fixed-commit clone is kept under ignored `external/cwf-src` instead.
- STMW currently runs on the welded closed geometry view. Using the attribute-split OBJ would turn UV seams into 73 disconnected components and cause the incomplete virtual-edge proxy to affect the main geometry result.
- CWF's Windows-oriented source collides with glibc's legacy `gamma()` symbol and relies on permissive unqualified `isinf` lookup. The tracked WSL build applies a behavior-preserving identifier rename and `-fpermissive`; the official optimization code is otherwise unchanged.
- The foreground shell wrapper timed out at 600 seconds during the real QEM4VR 50% run, but its Python/WSL child remained alive and continued writing five-minute checkpoints. Future long runs need a persistent queue or an explicit detached-run command rather than a foreground tool timeout.
- The user clarified that the supported repair environment is `E:/skills/asset_pipeline_tools_v2/.venv`. Its doctor reports Light and Manifold available; the redundant project-local repair environment is ignored and is not used by the harness.
- QEM 50% repair produced no candidate that passed all hard constraints. Light retained open/non-manifold defects, Manifold rejected a component, and the four remaining backends were unavailable; the asset result is correctly `REPAIR_FAILED` with a debug candidate retained.
- The original QEM4VR/STMW collapse loop rebuilt global connectivity after every collapse and projected the 50% run into hours. Incremental one-ring face/neighbor updates reduced the same target to seconds; the abandoned partial run is preserved under `artifacts/aborted`.
- CWF's first real one-iteration probe produced 82,814 faces after roughly 20 minutes end-to-end and exposed non-manifold output on this input. The formal 50-iteration run is therefore isolated in a detached process and its native topology will be reported without repair-induced masking.
- STMW now recomputes its boundary-edge area quadric per candidate without accumulating it, and discovers virtual edges with exact triangle-to-triangle distance inside an expanded-AABB hash. A regression fixture covers overlapping projected triangle interiors whose vertex pairs are all outside the virtual radius.
- STMW texture transfer now records a versioned binary collapse lineage containing pre-collapse edge one-rings and post-collapse vertex one-rings. The asset baker traverses only relevant records in reverse, projects into each saved local one-ring, and reuses the final texel position throughout the traversal.
- QEM4VR now welds exact duplicate positions while retaining per-corner UV/normal attributes, preventing texture seams from being treated as disconnected geometry. The research OBJ exports the transferred attributes; topology gates use a welded geometry view and preserve the attribute-split view separately.
- The paper-correct QEM4VR 50% run reached exactly 82,470 faces in 7.56 seconds. Its welded geometry is one closed manifold component; the native OBJ also retains 247,410 per-corner attribute vertices, which are reported separately rather than misclassified as geometric cracks.
- `trimesh.split` made component counting on fully split attribute views exceed the diagnostic timeout. Topology reporting now uses SciPy sparse connected components and computes both the attribute and `1e-6` welded geometry views in a few seconds.
- Windows process-tree sampling cannot see Linux descendants behind `wsl.exe`. New WSL runs are wrapped in `/usr/bin/time -v` and label CPU/RSS provenance as `gnu_time_v_inside_wsl`; the already-running CWF 50% job has a separate 60-second `/proc` monitor because it predates this change.
- The repair tool's inspect command reports self-intersection as `not_evaluated` in the current environment because no backend is available. Evaluation records preserve that explicit status instead of treating it as zero intersections.
- Sub-hour adapters now consume the experiment timing configuration, run one warmup followed by three measured repetitions, and report all samples plus median/range. RobustLPM and ICE keep target calibration time separate and rerun the selected parameter into distinct benchmark outputs; hour-scale CWF remains a single measured run.

## Questions for review

- None.
