# FA-QEM Baseline Bench

Reproducible harness for QEM, QEM4VR, RobustLPM, ICE, STMW, and CWF on the
single source asset in `Test_Model/`.

The harness records two output tracks:

- `research`: untouched native geometry from each baseline.
- `asset`: gated/repaired geometry prepared for the common texture-transfer pipeline.

Quick start:

```powershell
uv sync --extra dev
uv run fa-qem-bench --config experiment.yaml doctor
uv run fa-qem-bench --config experiment.yaml prepare
uv run fa-qem-bench --config experiment.yaml run --method qem --ratio 0.5
uv run fa-qem-bench --config experiment.yaml run --method fa-qem --ratio 0.5
uv run fa-qem-bench --config experiment.yaml sweep --resume --resolution 2048
uv run fa-qem-bench --config experiment.yaml audit
uv run python scripts/validate_qem_consistency.py
uv run pytest
```

`fa-qem` is the evaluated target method and is intentionally excluded from the fixed six-baseline sweep/audit count. Its paper-to-code mapping and disclosed assumptions are documented in [docs/fa-qem-implementation-spec.md](docs/fa-qem-implementation-spec.md).

## Implementation fidelity and limitations

No benchmark path is a toy, mock, placeholder, or precomputed-output shim. Each
run invokes either an author-provided implementation or a native simplifier that
performs the complete priority-queue/collapse loop and writes a measured result.
This does **not** mean that every method is an exact reproduction of the authors'
unpublished implementation:

| Method | Implementation provenance | Fidelity limitation |
|---|---|---|
| QEM | Official public-domain QSlim 1.0 source | The original source is kept algorithmically unchanged; tracked compatibility headers only make it build on modern compilers. |
| RobustLPM | Official author-distributed Windows executable | The method is authoritative but black-box; its internals cannot be independently audited or redistributed. |
| CWF | Official repository at the locked commit | The WSL build applies a tracked GCC compatibility patch that renames a symbol and fixes an output path; the optimization core is otherwise unchanged. |
| ICE | Official coarsening core with a local non-interactive CLI | The exported OBJ is the official example's retained-position visualization geometry and does not realize intrinsic edge lengths as an exact Euclidean embedding. |
| QEM4VR | Clean-room, paper-guided local implementation | No currently available official code exists for cross-validation. The implementation covers geometry, curvature boundaries, subset placement, UVs, normals, materials, and attribute transfer, but has no independent vertex-color channel; it must not be labeled an exact author implementation. |
| STMW | Paper-guided local implementation | The paper does not publish a numeric virtual-edge radius, so the harness discloses a 1%-of-diagonal assumption. Successive mapping and texture baking use the repository's documented local interchange/adaptation rather than author code. |
| FA-QEM | Paper-guided local implementation | The paper and public project do not provide algorithm source. UV-penalty placement, vertex-normal estimation, boundary-neighbor ordering, and appearance transfer require disclosed choices; manifold inputs additionally retain a link-condition safeguard discovered during validation. |

Therefore, QEM, RobustLPM, and CWF are official/reference executions; ICE uses
the official algorithm core with an export caveat; QEM4VR, STMW, and FA-QEM are
real research implementations but are reported as `paper-guided local
reimplementation`, not as bit-for-bit author reproductions. Detailed mappings
and assumptions are in
[docs/paper-implementation-spec.md](docs/paper-implementation-spec.md) and
[docs/fa-qem-implementation-spec.md](docs/fa-qem-implementation-spec.md).

Additional experimental limitations:

- The six-baseline headline experiment covers one local source asset at three
  face ratios; it does not reproduce every dataset or aggregate table from the
  original papers.
- The FA-QEM Thingi10K study is a deterministic 16-model independent
  validation/holdout reproduction because the paper does not publish its exact
  model list or sufficient metric-scaling detail for a model-for-model Table 2
  reconstruction.
- External inspection did not evaluate self-intersections in this run. A
  `not_evaluated` field must not be interpreted as zero self-intersections.
- Large meshes, textures, intermediate RVD files, binaries, and run logs remain
  outside Git. The repository tracks their versions, hashes, commands, and
  provenance so the local audit package can be verified or regenerated.

Report-preview provenance:

- The source base color is pinned in `experiment.yaml` to the original 4096px
  `Test_Model/deliverty/textures/basecolor.png` with its SHA-256. A report build
  fails validation if that file changes.
- A right-hand preview uses an embedded base-color texture when available,
  otherwise it uses the native UVs with the pinned source image or projects the
  source image from the nearest source surface. This display-only projection
  does not change native geometry or texture metrics.
- `REPAIR_FAILED` asset records render their retained best debug candidate only
  for diagnosis. Both the image header and report metadata label that input as
  a failed-repair debug candidate; it is not a successful compatible asset.

The completed results and acceptance evidence are summarized in
[docs/final-acceptance-report.md](docs/final-acceptance-report.md).
The seven-method visual comparisons and key-metric tables are available for
[50%](docs/ratio-0p5-seven-method-summary.md),
[10%](docs/ratio-0p1-seven-method-summary.md), and
[1%](docs/ratio-0p01-seven-method-summary.md).
The independent STMW ratio sweep from 0.1 through 0.9 is documented in
[docs/stmw-ratio-metrics.md](docs/stmw-ratio-metrics.md).

The `sweep` command executes each source ratio independently, evaluates the
research output, creates an explicit asset-track result even when the research
run fails, conditionally repairs, bakes the common PBR asset, and rebuilds the
report. It writes `artifacts/sweep-progress.json` after every stage and validates
source/output hashes before resuming. Use `--no-resume` to deliberately rerun
the selected methods and ratios.

The `audit` command is the final acceptance gate for all 36 records. During an
active sweep, `audit --allow-incomplete` checks every available record while
reporting the missing run IDs without failing solely because they are pending.

For a WSL process that started before GNU `time -v` measurement was enabled,
recover its sampled resource record with:

```powershell
uv run fa-qem-bench --config experiment.yaml recover-resources `
  --run-id cwf-0p5-research `
  --monitor artifacts/jobs/cwf-0p5-resource.csv `
  --repository-commit 5f3710b `
  --repository-dirty `
  --provenance-note "job launched before repository snapshot support"
```

External repositories and binaries are intentionally excluded from Git. Their
URLs, revisions, hashes, license notes, and compatibility patches are recorded
in `third_party.lock.yaml`; per-run commands and environments are written under
the ignored `artifacts/runs/` tree.
