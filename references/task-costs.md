# Task cost and I/O table

| Task | Cost | Runtime | Peak memory | Probe evidence |
|---|---|---:|---:|---|
| `doctor` / `prepare` | Light | < 2 min | < 2 GB | Initial classification |
| QEM 50% native run | Light | ~28 s before repeated-timing revision | < 2 GB | Formal single-run predecessor |
| QEM4VR 50% native run | Light | ~8 s per run | < 2 GB | Paper-correct formal predecessor |
| STMW 50% native run | Light | ~10 s per run | < 2 GB | Successive-map formal predecessor |
| ICE 50% native run | Light | ~5 s per run plus calibration | < 2 GB | Official headless formal predecessor |
| RobustLPM 50% native run | Moderate | median 194 s; 373 s calibration | ~1.25 GiB | Official binary, 1 warmup + 3 measured |
| RobustLPM 10% native run | Moderate | median 64 s; 63 s calibration | ~1.15 GiB | Official binary, 1 warmup + 3 measured |
| RobustLPM 1% native run | Moderate | median 39 s; 38 s calibration | ~1.15 GiB | Official binary, 1 warmup + 3 measured |
| CWF 50% native run, 50 iterations | Heavy by runtime | > 1 hr; still running | ~1.3 GiB observed RSS | Formal `/proc` monitor; peak is partial |
| one 10%/1% production baseline | Unknown | Unknown | Unknown | Run serially; classify from first formal result |
| 100k nearest-triangle evaluation | Light | ~9-15 s | < 2 GB | 15 formal research evaluations |
| 256 px texture rebake | Light | < 10 min | < 2 GB | QEM4VR/STMW/ICE smoke outputs completed |
| 2048 px texture rebake | Moderate by memory caution | ~86-149 s | Not instrumented; completed with >12 GiB free | Seven formal assets, serial execution |
| 30-record contact-sheet report | Light | 18 s | < 2 GB | Depth-sorted polygon renderer |

| Task | Reads | Writes | Conflict rule |
|---|---|---|---|
| `prepare` | source GLB, config | `artifacts/prepared` | Exclusive writer |
| `run` | prepared geometry, adapter install | run-specific directory | Safe across distinct run IDs, but benchmark policy serializes heavy jobs |
| `repair` | frozen native output | run-specific repair directory | Run only after native run terminates |
| `evaluate` | source and one frozen output | run-specific metrics | Run only after selected output is frozen |
| `report` | all run records | report directory | Run after active writers terminate |
