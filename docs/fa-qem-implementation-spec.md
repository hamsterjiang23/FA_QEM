# FA-QEM implementation specification

This repository implements FA-QEM from the paper *Fast and Robust Mesh Simplification for Generated and Real-World 3D Assets* (arXiv:2605.14029v1). The authors' public repository contains the project page but no algorithm source as of 2026-08-07, so this is a paper-guided reimplementation rather than an official implementation.

Primary sources:

- Paper and supplementary material: <https://arxiv.org/html/2605.14029>
- Author project page: <https://b22237.github.io/FA-QEM/>
- Author repository: <https://github.com/b22237/FA-QEM>

## Implemented paper terms

For homogeneous position $v=[x,y,z,1]^T$, the executable constructs

$$
Q_{gf}^k=Q_{base}^k+Q_{boundary}^k+Q_{normal}^k
$$

and minimizes the merged endpoint quadric $Q_{gf}'=Q_{gf}^i+Q_{gf}^j$. The base term is the inverse-area-weighted face-plane sum from Eq. 5:

$$
Q_{base}=\sum_p \frac{p p^T}{w_{plane\_area} A_p}.
$$

For a boundary vertex with exactly two boundary-chain neighbors, the implementation evaluates Eq. 6 and adds both raw plane outer products from Eqs. 7–9, scaled by $w_{boundary}\kappa$. It also adds the vertex tangent-plane quadric from Eq. 10 using an area-weighted incident-face normal.

The candidate position is solved from $Q_{gf}'$ only. Singular systems use the lower-cost choice among the two endpoints and midpoint. The boundary-area quadric from Eq. 11 is then evaluated independently and added as

$$
cost_{total}=v^TQ_{gf}'v+w_{area}v^TQ^Av.
$$

Only boundary edges incident to either collapse endpoint contribute to $Q^A$, matching Sec. 3.2.2.

## Fixed paper parameters

| CLI option | Default experiment value |
|---|---:|
| `--area-weight` | 100 |
| `--boundary-weight` | 500 |
| `--uv-weight` | 5000 |
| `--normal-weight` | 0.01 |
| `--plane-area-weight` | 1 |
| `--virtual-radius` | 0.01 of the bounding-box diagonal |

The loader welds positions within the paper's absolute $10^{-6}$ tolerance. Edges shorter than $10^{-8}$ times the bounding-box diagonal receive infinite cost. Candidate collapses are rejected when they create a degenerate triangle, duplicate a face, violate the link condition, or flip an affected face normal.

Disconnected components are identified from generalized vertex adjacency. Triangle centroids are queried within $0.01L_{diag}$; the closest vertex pair for each qualifying cross-component triangle pair becomes a virtual collapse edge. Collapse history is serialized for the common successive-mapping baker.

## Explicit reproduction assumptions

The paper does not define the exact application point for the stated "multiplicative penalty for vertices on UV seams." This implementation multiplies the complete initialized per-vertex $Q_{gf}$ by $w_{uv}$ when the welded geometric vertex has more than one corner UV value.

The paper calls $n_k$ a unit vertex normal but does not specify its estimator. This implementation normalizes the sum of incident unnormalized face cross products, i.e. an area-weighted vertex normal.

Eqs. 7 and 8 publish unnormalized vectors $n_1$ and $d$. Their outer products are used as written. Inputs produced by the harness are centered and scaled to unit bounding-box diagonal.

The two neighbors of a simple boundary vertex have no orientation rule in the paper. They are sorted by stable vertex index before assigning $v_2$ and $v_3$, making the asymmetric $d=v_1-v_2$ term deterministic.

The paper describes nearest-parent reassignment during reverse collapses but does not publish an interchange format or complete texture-baking code. The native executable records the full local collapse lineage; the shared asset baker currently applies reverse local one-ring projection. This is a disclosed appearance-transfer adaptation. The geometric FA-QEM cost and collapse decisions do not depend on it.

## Commands

```text
cmake --build build-wsl --target paper_simplify
ctest --test-dir build-wsl --output-on-failure
uv run fa-qem-bench --config experiment.yaml run --method fa-qem --ratio 0.5
```
