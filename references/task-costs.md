# Task cost and I/O table

| Task | Cost | Runtime | Peak memory | Probe evidence |
|---|---|---:|---:|---|
| `doctor` / `prepare` | Light | < 2 min | < 2 GB | Initial classification |
| one 50% baseline smoke test | Unknown | Unknown | Unknown | Probe required |
| one 10%/1% production baseline | Unknown | Unknown | Unknown | Probe required |
| 100k nearest-triangle evaluation | Unknown | Unknown | Unknown | Probe required |
| texture rebake | Unknown | Unknown | Unknown | Probe required |

| Task | Reads | Writes | Conflict rule |
|---|---|---|---|
| `prepare` | source GLB, config | `artifacts/prepared` | Exclusive writer |
| `run` | prepared geometry, adapter install | run-specific directory | Safe across distinct run IDs, but benchmark policy serializes heavy jobs |
| `repair` | frozen native output | run-specific repair directory | Run only after native run terminates |
| `evaluate` | source and one frozen output | run-specific metrics | Run only after selected output is frozen |
| `report` | all run records | report directory | Run after active writers terminate |

