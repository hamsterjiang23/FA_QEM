from __future__ import annotations

import struct
from pathlib import Path

import numpy as np

from fa_qem_bench.successive import (
    atlas_faces_to_target_faces,
    load_successive_map,
    map_points_successively,
)


def _snapshot(face: int, z: float) -> bytes:
    triangle = (0.0, 0.0, z, 1.0, 0.0, z, 0.0, 1.0, z)
    return struct.pack("<I9d", face, *triangle)


def test_successive_map_replays_local_face_lineage(tmp_path: Path) -> None:
    payload = bytearray(struct.pack("<8sIIQQ", b"FQSMAP1\0", 1, 0, 2, 1))
    payload.extend(struct.pack("<II", 1, 1))
    payload.extend(_snapshot(1, 0.0))
    payload.extend(struct.pack("<I", 2))
    payload.extend(struct.pack("<II", 1, 1))
    payload.extend(_snapshot(2, 0.1))
    payload.extend(struct.pack("<I", 3))
    payload.extend(struct.pack("<I", 3))
    path = tmp_path / "map.bin"
    path.write_bytes(payload)

    history = load_successive_map(path)
    mapped, audit = map_points_successively(
        history,
        np.array([[0.25, 0.25, 0.2]], dtype=np.float64),
        np.array([3], dtype=np.uint32),
    )

    assert mapped.tolist() == [1]
    assert audit == {"history_records": 2, "applied_records": 2, "sample_transitions": 2}


def test_atlas_faces_are_matched_after_vertex_duplication() -> None:
    target_faces = np.array([[0, 1, 2], [1, 3, 2]], dtype=np.int64)
    mapping = np.array([1, 3, 2, 0, 1, 2], dtype=np.int64)
    atlas_faces = np.array([[0, 1, 2], [3, 4, 5]], dtype=np.int64)

    result = atlas_faces_to_target_faces(mapping, atlas_faces, target_faces)

    assert result.tolist() == [1, 0]
