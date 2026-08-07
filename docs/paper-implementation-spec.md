# Paper implementation specification

## QEM4VR

Source: Bahirat et al., *Designing and Evaluating a Mesh Simplification Algorithm for Virtual Reality*, DOI 10.1145/3209661.

Implemented semantics:

- Garland-Heckbert memory quadrics with the paper's subset endpoint-placement policy.
- Exact-position duplicate welding retains per-corner UV and normal values, so texture seams do not become false geometric boundaries.
- Boundary constraint planes are multiplied independently by each endpoint's discrete curve curvature from equations (4)–(6). Boundary vertices with other than two boundary neighbors are marked complex and excluded from collapse.
- Vertices associated with multiple material or texture values have their quadrics multiplied by the published material weight. During collapse, per-face UV and normals use the closest attribute at the selected endpoint subject to matching material indices.
- Face-flip and degenerate-face rejection keeps valid local geometry.

The experimental values published in section 4 are used directly: boundary weight `W_b=5` and material/critical-vertex weight `W_t=1000`. The paper's historical code URL no longer exposes a discoverable download, so this remains a clean-room paper reimplementation rather than the official executable.

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
