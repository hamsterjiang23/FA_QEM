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
uv run python scripts/validate_qem_consistency.py
uv run pytest
```

External repositories and binaries are intentionally excluded from Git. Their
URLs, revisions, hashes, license notes, and compatibility patches are recorded
in `third_party.lock.yaml`; per-run commands and environments are written under
the ignored `artifacts/runs/` tree.
