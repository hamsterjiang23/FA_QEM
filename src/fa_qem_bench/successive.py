from __future__ import annotations

import struct
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from numpy.typing import NDArray
from trimesh.triangles import closest_point

_HEADER = struct.Struct("<8sIIQQ")
_COUNTS = struct.Struct("<II")
_SNAPSHOT_DTYPE = np.dtype([("face", "<u4"), ("triangle", "<f8", (3, 3))])


@dataclass(frozen=True)
class SuccessiveMap:
    data: np.memmap
    record_offsets: NDArray[np.uint64]
    final_face_ids: NDArray[np.uint32]

    def records_reverse(
        self,
    ) -> Iterator[tuple[NDArray[np.void], NDArray[np.uint32]]]:
        for raw_offset in self.record_offsets[::-1]:
            offset = int(raw_offset)
            before_count, after_count = _COUNTS.unpack_from(self.data, offset)
            before_offset = offset + _COUNTS.size
            before = np.frombuffer(
                self.data,
                dtype=_SNAPSHOT_DTYPE,
                count=before_count,
                offset=before_offset,
            )
            after_offset = before_offset + before_count * _SNAPSHOT_DTYPE.itemsize
            after = np.frombuffer(
                self.data,
                dtype="<u4",
                count=after_count,
                offset=after_offset,
            )
            yield before, after


def load_successive_map(path: Path) -> SuccessiveMap:
    data = np.memmap(path, mode="r", dtype=np.uint8)
    if data.size < _HEADER.size:
        raise ValueError("successive map is truncated")
    magic, version, reserved, record_count, final_face_count = _HEADER.unpack_from(data, 0)
    if magic != b"FQSMAP1\0" or version != 1 or reserved != 0:
        raise ValueError("unsupported successive map header")
    offsets = np.empty(record_count, dtype=np.uint64)
    offset = _HEADER.size
    for index in range(record_count):
        if offset + _COUNTS.size > data.size:
            raise ValueError("successive map record header is truncated")
        offsets[index] = offset
        before_count, after_count = _COUNTS.unpack_from(data, offset)
        offset += _COUNTS.size + before_count * _SNAPSHOT_DTYPE.itemsize + after_count * np.dtype("<u4").itemsize
        if offset > data.size:
            raise ValueError("successive map record is truncated")
    final_bytes = final_face_count * np.dtype("<u4").itemsize
    if offset + final_bytes != data.size:
        raise ValueError("successive map final-face table has an invalid size")
    final_face_ids = np.frombuffer(
        data,
        dtype="<u4",
        count=final_face_count,
        offset=offset,
    )
    return SuccessiveMap(data=data, record_offsets=offsets, final_face_ids=final_face_ids)


def _closest_local_faces(
    points: NDArray[np.float64],
    face_ids: NDArray[np.uint32],
    triangles: NDArray[np.float64],
) -> NDArray[np.uint32]:
    result = np.empty(len(points), dtype=np.uint32)
    max_pairs = 1_000_000
    chunk_size = max(1, max_pairs // max(1, len(triangles)))
    for start in range(0, len(points), chunk_size):
        stop = min(start + chunk_size, len(points))
        batch = points[start:stop]
        repeated_points = np.repeat(batch, len(triangles), axis=0)
        tiled_triangles = np.tile(triangles, (len(batch), 1, 1))
        projected = closest_point(tiled_triangles, repeated_points)
        squared = np.sum((projected - repeated_points) ** 2, axis=1).reshape(len(batch), len(triangles))
        result[start:stop] = face_ids[np.argmin(squared, axis=1)]
    return result


def map_points_successively(
    history: SuccessiveMap,
    points: NDArray[np.float64],
    final_internal_faces: NDArray[np.uint32],
) -> tuple[NDArray[np.uint32], dict[str, int]]:
    if len(points) != len(final_internal_faces):
        raise ValueError("point and face arrays must have equal length")
    current = np.asarray(final_internal_faces, dtype=np.uint32).copy()
    buckets: dict[int, NDArray[np.int64]] = {}
    for face in np.unique(current):
        buckets[int(face)] = np.flatnonzero(current == face)
    transitioned_samples = 0
    applied_records = 0
    for before, after in history.records_reverse():
        selected = [buckets.pop(int(face)) for face in after if int(face) in buckets]
        if not selected:
            continue
        sample_indices = selected[0] if len(selected) == 1 else np.concatenate(selected)
        if len(before) == 0:
            raise ValueError("successive map has samples in an empty pre-collapse one-ring")
        mapped = _closest_local_faces(
            points[sample_indices],
            np.asarray(before["face"], dtype=np.uint32),
            np.asarray(before["triangle"], dtype=np.float64),
        )
        current[sample_indices] = mapped
        for face in np.unique(mapped):
            local = sample_indices[mapped == face]
            existing = buckets.get(int(face))
            buckets[int(face)] = local if existing is None else np.concatenate((existing, local))
        transitioned_samples += len(sample_indices)
        applied_records += 1
    return current, {
        "history_records": int(len(history.record_offsets)),
        "applied_records": applied_records,
        "sample_transitions": transitioned_samples,
    }


def atlas_faces_to_target_faces(
    mapping: NDArray[np.integer],
    atlas_faces: NDArray[np.integer],
    target_faces: NDArray[np.integer],
) -> NDArray[np.int64]:
    lookup: dict[tuple[int, int, int], int] = {}
    for face_index, face in enumerate(target_faces):
        ordered = sorted(int(vertex) for vertex in face)
        key = (ordered[0], ordered[1], ordered[2])
        if key in lookup:
            raise ValueError("target contains duplicate faces; atlas lineage is ambiguous")
        lookup[key] = face_index
    result = np.empty(len(atlas_faces), dtype=np.int64)
    for face_index, face in enumerate(np.asarray(mapping)[atlas_faces]):
        ordered = sorted(int(vertex) for vertex in face)
        key = (ordered[0], ordered[1], ordered[2])
        try:
            result[face_index] = lookup[key]
        except KeyError as error:
            raise ValueError("xatlas face cannot be matched to the target mesh") from error
    return result
