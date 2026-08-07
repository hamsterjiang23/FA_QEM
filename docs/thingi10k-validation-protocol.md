# Thingi10K FA-QEM validation protocol

FA-QEM evaluates geometric fidelity and robustness on Thingi10K at 10% and 1% of the input face count. The paper fixes all weights across datasets but does not publish its exact model list or sufficient metric scaling detail for a model-for-model reconstruction of Table 2. This repository therefore labels the following procedure an independent reproduction on the authors' dataset, not an exact recreation of the paper aggregate.

## Dataset provenance

- Dataset: official Thingi10K `npz` variant
- Metadata repository commit: `aaae0bb650cf464eb6c7d86d5ce39597cb71e106`
- Individual NPZ repository commit: `901c950e67abfafbc1718ab3e3cd480d51cc003e`
- Full archive fallback: `Thingi10K_npz.tar.gz`, 4,083,478,827 bytes, SHA-256 `0a9e3e7f0df0393c9f12959b5c3691ec01a4032a9c5c13ee9cc9a6e3f3d11e0c`
- Geometry and license metadata are hashed into the generated experiment manifest.

The fixed subset is downloaded as individual NPZ files from the official historical commit that predates consolidation into one archive. The manifest records every resolved URL, byte size, and downloaded SHA-256, avoiding a multi-gigabyte transfer without changing model contents.

The five corrupt IDs listed by the current official repository are excluded: 49911, 74463, 77942, 81313, and 286163.

## Fixed split

Models are restricted to 5,000–200,000 input faces, then assigned to four mutually exclusive topology strata:

1. clean, closed, oriented, single-component manifold;
2. non-manifold;
3. open manifold;
4. multi-component or self-intersecting.

Within each stratum, models are sorted by `SHA256("260514029:<file_id>")`, using the experiment's fixed random seed. The first two form the validation split and the next two form the untouched holdout split, giving 8 models per split and 16 total. The validation split may be used to resolve implementation ambiguities. Published weights remain fixed. The holdout split is opened only after a candidate implementation choice has been frozen.

## Evaluation

- Each 10% and 1% target starts independently from the original NPZ geometry.
- Inputs are centered and scaled to unit bounding-box diagonal before simplification.
- Target tolerance is 2%; failures and unreachable targets remain explicit results.
- Geometry error uses 100,000 deterministic area samples per direction.
- Reported errors are sampled symmetric Hausdorff distance and mean-squared symmetric Chamfer distance in unit-diagonal coordinates.
- The implementation records command, hashes, wall/CPU time, peak RSS, topology, triangle quality, and per-model license.

## Commands

```text
uv run fa-qem-bench --config experiment.yaml thingi10k-select \
  --metadata-dir artifacts/datasets/thingi10k/metadata \
  --dataset-root artifacts/datasets/thingi10k/extracted \
  --output artifacts/datasets/thingi10k/manifest.json

uv run fa-qem-bench --config experiment.yaml thingi10k-fetch \
  --manifest artifacts/datasets/thingi10k/manifest.json

uv run fa-qem-bench --config experiment.yaml thingi10k-run \
  --manifest artifacts/datasets/thingi10k/manifest.json \
  --split validation --ratios 0.1 0.01 --variant paper-topology
```
# Implementation variants

- `published`: the first implementation used before the paper's flip-only collapse veto was reconciled.
- `paper-topology`: the literal generalized flip-only implementation used for all inputs.
- `adaptive-topology`: the interim classifier based on edge incidence; retained because its validation failure motivated vertex-link checks.
- `final-topology`: the audited rerun after the manifold classifier was expanded from edge incidence alone to full vertex-link connectivity.
