# Paper implementation specification

## QEM4VR

Source: Bahirat et al., *Designing and Evaluating a Mesh Simplification Algorithm for Virtual Reality*, DOI 10.1145/3209661.

Implemented semantics:

- Garland-Heckbert memory quadrics and optimal edge-collapse placement.
- Boundary constraint planes whose weight increases with boundary turning curvature, so curved boundaries resist collapse more than near-linear boundaries.
- UV, normal, and material discontinuities contribute explicit collapse penalties; merged attributes propagate by normalized averaging.
- Face-flip and degenerate-face rejection keeps valid local geometry.

The paper is closed-access in the available environment. Numeric weights are therefore declared experiment parameters and must be reported as reproduction assumptions rather than official defaults.

## STMW

Source: Liu, Zhang, and Yuksel, *Simplifying Textured Triangle Meshes in the Wild*, arXiv:2409.15458, sections 4.1–4.3 and appendices A–C.

Implemented semantics:

- A list-of-lists simplicial 2-complex representation through vertex-to-edge, vertex-to-face, and edge-to-face incidence.
- Physical and virtual vertex-pair collapses, memory edge quadrics, and checkpointed collapse history.
- Closed-manifold inputs contain no area/virtual augmentation and therefore use the same QEM objective.
- Local face-flip rejection is enabled for the benchmark's canonical manifold input.

Implementation details and disclosed assumption:

- The executable uses exact triangle-to-triangle distance tests inside an expanded-AABB spatial hash to create virtual edges between the closest vertex pairs of different components. It uses memory edge quadrics and recomputes the boundary-edge area quadric for every candidate without accumulating it across collapses.
- Every collapse writes the pre-collapse edge one-ring triangle snapshots and post-collapse vertex one-ring face identifiers to a versioned binary lineage. During rebaking, texels are mapped backwards only through histories containing their current face, closest-point projection is restricted to the saved pre-collapse one-ring, and the original target-space texel position is reused at every level as specified in section 4.3.1 and appendix C.2.
- The virtual-edge radius defaults to 1% of the unit bounding-box diagonal because the paper does not publish a numeric radius. The benchmark model's welded scientific geometry is a single closed component, so this assumption does not affect its geometry-only STMW result.

## ICE export semantics

The official `00_coarsening` example states that its embedded coarse visualization uses retained original positions and therefore does not realize the intrinsic edge lengths. The local CLI keeps the official coarsening core unchanged and exports exactly that visualization geometry for interoperability; run records must label it `intrinsic_visualization_geometry`, not an exact Euclidean embedding.
