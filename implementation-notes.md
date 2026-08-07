# Implementation notes

## Deviations

- `codegraph init -i` exceeded the 120-second foreground timeout, but left a live indexing process and a populated `.codegraph` database. The process is being left to finish rather than terminated; health will be checked before using the index.

## Discovered edge cases

- The source GLB contains attribute-split seam vertices; topology checks must use the canonical welded geometry view while texture transfer keeps the original corner attributes.
- `pueue` is not installed, so long jobs cannot yet use the planned persistent queue. Install it before production sweeps or use the harness resume records conservatively.
- The user added a GitHub synchronization requirement after implementation began. Core source and reproducibility metadata will be pushed; models, third-party code/binaries, and generated artifacts remain excluded.
- Concurrent `uv run` commands raced while initializing the user-level cache on Windows. Verification commands now use the project-local `.uv-cache` and run sequentially.
- Trimesh component splitting needs its optional `networkx` dependency on this input. It is now an explicit locked runtime dependency rather than an undeclared environment assumption.
- QEM4VR is closed-access from this environment (ACM returned HTTP 403 and OpenAlex reports no OA copy). The first implementation exposes all non-paper numeric weights and labels them assumptions; exact defaults require a user-provided PDF or author clarification.
- STMW's first executable checkpoint uses component-aware spatial vertex proximity for virtual-edge discovery rather than the paper's triangle-to-triangle distance. It is sufficient for the current single closed canonical geometry but not yet paper-faithful for general triangle soups.
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

## Questions for review

- None.
