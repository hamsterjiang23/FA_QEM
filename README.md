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
uv run fa-qem-bench --config experiment.yaml sweep --resume --resolution 2048
uv run python scripts/validate_qem_consistency.py
uv run pytest
```

The `sweep` command executes each source ratio independently, evaluates the
research output, creates an explicit asset-track result even when the research
run fails, conditionally repairs, bakes the common PBR asset, and rebuilds the
report. It writes `artifacts/sweep-progress.json` after every stage and validates
source/output hashes before resuming. Use `--no-resume` to deliberately rerun
the selected methods and ratios.

For a WSL process that started before GNU `time -v` measurement was enabled,
recover its sampled resource record with:

```powershell
uv run fa-qem-bench --config experiment.yaml recover-resources `
  --run-id cwf-0p5-research `
  --monitor artifacts/jobs/cwf-0p5-resource.csv
```

External repositories and binaries are intentionally excluded from Git. Their
URLs, revisions, hashes, license notes, and compatibility patches are recorded
in `third_party.lock.yaml`; per-run commands and environments are written under
the ignored `artifacts/runs/` tree.
