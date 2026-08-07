from __future__ import annotations

import shutil
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from trimesh.sample import sample_surface

from ..mesh import load_mesh
from ..process import ProcessResult, run_measured


@dataclass(frozen=True)
class AdapterContext:
    root: Path
    prepared_mesh: Path
    run_dir: Path
    target_faces: int
    threads: int
    parameters: dict[str, Any]


@dataclass(frozen=True)
class AdapterResult:
    output: Path
    source: str
    command: list[str]
    timing: dict[str, Any]
    parameters: dict[str, Any]


class BaselineAdapter(ABC):
    name: str
    source: str

    @abstractmethod
    def available(self, root: Path) -> tuple[bool, str]:
        raise NotImplementedError

    @abstractmethod
    def run(self, context: AdapterContext) -> AdapterResult:
        raise NotImplementedError


class ExecutableAdapter(BaselineAdapter):
    executable_relative: Path

    def executable(self, root: Path) -> Path:
        return root / self.executable_relative

    def available(self, root: Path) -> tuple[bool, str]:
        executable = self.executable(root)
        return executable.is_file(), str(executable)

    def measured(self, command: list[str], context: AdapterContext) -> ProcessResult:
        return run_measured(command, context.root, context.run_dir / "logs")


class QSlimAdapter(BaselineAdapter):
    name = "qem"
    source = "official QSlim 1.0 public-domain source"

    def available(self, root: Path) -> tuple[bool, str]:
        executable = root / "external" / "qslim" / "qslim"
        return executable.is_file(), str(executable)

    def run(self, context: AdapterContext) -> AdapterResult:
        output = context.run_dir / "native.obj"
        executable = context.root / "external" / "qslim" / "qslim"
        command = [
            "wsl.exe",
            PaperExecutableAdapter._wsl_path(executable),
            "-s",
            str(context.target_faces),
            "-o",
            PaperExecutableAdapter._wsl_path(output),
            PaperExecutableAdapter._wsl_path(context.prepared_mesh),
        ]
        measured = run_measured(command, context.root, context.run_dir / "logs")
        if measured.returncode != 0:
            raise RuntimeError(f"QSlim exited with {measured.returncode}")
        return AdapterResult(
            output=output,
            source=self.source,
            command=command,
            timing={
                "algorithm_wall_seconds": measured.wall_seconds,
                "cpu_seconds": measured.cpu_seconds,
                "peak_rss_bytes": measured.peak_rss_bytes,
                "repetitions": 1,
            },
            parameters={"target_faces": context.target_faces, "optimization": 3},
        )


class PaperExecutableAdapter(ExecutableAdapter):
    executable_relative = Path("build") / "bin" / "paper_simplify.exe"

    @staticmethod
    def _wsl_path(path: Path) -> str:
        resolved = path.resolve()
        drive = resolved.drive.rstrip(":").lower()
        suffix = resolved.as_posix().split(":", 1)[1]
        return f"/mnt/{drive}{suffix}"

    def _command_prefix(self, root: Path) -> tuple[list[str], str]:
        windows = self.executable(root)
        if windows.is_file():
            return [str(windows)], "windows-native"
        linux = root / "build-wsl" / "bin" / "paper_simplify"
        if linux.is_file():
            return ["wsl.exe", self._wsl_path(linux)], "wsl2"
        return [], "missing"

    def available(self, root: Path) -> tuple[bool, str]:
        prefix, runtime = self._command_prefix(root)
        if prefix:
            return True, f"{runtime}: {prefix[-1]}"
        return False, f"{self.executable(root)} or {root / 'build-wsl' / 'bin' / 'paper_simplify'}"

    def run(self, context: AdapterContext) -> AdapterResult:
        output = context.run_dir / "native.obj"
        prefix, runtime = self._command_prefix(context.root)
        if not prefix:
            raise RuntimeError("paper simplifier executable is unavailable")
        def native(path: Path) -> str:
            return self._wsl_path(path) if runtime == "wsl2" else str(path)

        command = [
            *prefix,
            "--method",
            self.name,
            "--input",
            native(context.prepared_mesh),
            "--output",
            native(output),
            "--target-faces",
            str(context.target_faces),
            "--checkpoint-dir",
            native(context.run_dir / "checkpoints"),
        ]
        measured = self.measured(command, context)
        if measured.returncode != 0:
            raise RuntimeError(f"{self.name} exited with {measured.returncode}")
        return AdapterResult(
            output=output,
            source=self.source,
            command=command,
            timing={
                "algorithm_wall_seconds": measured.wall_seconds,
                "cpu_seconds": measured.cpu_seconds,
                "peak_rss_bytes": measured.peak_rss_bytes,
                "repetitions": 1,
            },
            parameters=context.parameters,
        )


class QEM4VRAdapter(PaperExecutableAdapter):
    name = "qem4vr"
    source = "paper-guided local reimplementation; assumptions disclosed"


class STMWAdapter(PaperExecutableAdapter):
    name = "stmw"
    source = "partial paper-guided local reimplementation; known gaps disclosed"


class ExternalTemplateAdapter(ExecutableAdapter):
    name = ""
    source = "official external implementation"

    def run(self, context: AdapterContext) -> AdapterResult:
        raise RuntimeError(f"{self.name} adapter is not configured; run acquisition/build first")


class RobustLPMAdapter(ExternalTemplateAdapter):
    name = "robustlpm"
    executable_relative = (
        Path("external") / "robustlpm" / "RoLoPM_EXE" / "SurfaceRemeshingCli_bin.exe"
    )

    def run(self, context: AdapterContext) -> AdapterResult:
        executable = self.executable(context.root)
        screen_size = int(context.parameters.get("screen_size", 100))
        attempts: list[dict[str, Any]] = []
        best: tuple[int, Path, ProcessResult, list[str]] | None = None
        calibration_start = time.perf_counter()
        for attempt_index in range(4):
            output_dir = context.run_dir / f"robustlpm-n{screen_size}"
            output_dir.mkdir(parents=True, exist_ok=True)
            command = [
                str(executable),
                "-i",
                str(context.prepared_mesh),
                "-n",
                str(screen_size),
                "-f",
                str(context.target_faces),
                "-o",
                str(output_dir),
            ]
            measured = run_measured(
                command,
                context.root,
                context.run_dir / "logs" / f"n{screen_size}",
            )
            if measured.returncode != 0:
                raise RuntimeError(f"RobustLPM exited with {measured.returncode} at -n {screen_size}")
            expected = output_dir / f"{context.prepared_mesh.stem}_ours_final.obj"
            candidates = sorted(output_dir.glob("*_ours_final.obj"))
            if expected.is_file():
                produced = expected
            elif len(candidates) == 1:
                produced = candidates[0]
            else:
                raise RuntimeError("RobustLPM did not produce an unambiguous final OBJ")
            actual_faces = len(load_mesh(produced, process=False).faces)
            relative_error = abs(actual_faces - context.target_faces) / context.target_faces
            attempts.append(
                {
                    "attempt": attempt_index + 1,
                    "screen_size": screen_size,
                    "actual_faces": actual_faces,
                    "wall_seconds": measured.wall_seconds,
                }
            )
            error = abs(actual_faces - context.target_faces)
            if best is None or error < best[0]:
                best = (error, produced, measured, command)
            if relative_error <= 0.02:
                break
            if actual_faces >= context.target_faces:
                break
            scale = (context.target_faces / max(actual_faces, 1)) ** 0.5
            screen_size = min(400, max(screen_size + 1, int(np.ceil(screen_size * scale * 1.01))))
        if best is None:
            raise RuntimeError("RobustLPM calibration produced no output")
        _, produced, measured, command = best
        output = context.run_dir / "native.obj"
        shutil.copy2(produced, output)
        return AdapterResult(
            output=output,
            source=self.source,
            command=command,
            timing={
                "algorithm_wall_seconds": measured.wall_seconds,
                "calibration_wall_seconds": time.perf_counter() - calibration_start,
                "cpu_seconds": measured.cpu_seconds,
                "peak_rss_bytes": measured.peak_rss_bytes,
                "repetitions": 1,
            },
            parameters={
                "screen_size": int(command[command.index("-n") + 1]),
                "final_face_cap": context.target_faces,
                "target_control": "official -f option",
                "calibration_attempts": attempts,
            },
        )


class ICEAdapter(ExternalTemplateAdapter):
    name = "ice"
    executable_relative = Path("external") / "bin" / "ice_coarsening"

    def run(self, context: AdapterContext) -> AdapterResult:
        executable = self.executable(context.root)
        target_vertices = max(4, context.target_faces // 2 + 2)
        attempts: list[dict[str, Any]] = []
        best: tuple[int, Path, ProcessResult] | None = None
        calibration_start = time.perf_counter()
        tried: set[int] = set()
        for _ in range(6):
            if target_vertices in tried:
                break
            tried.add(target_vertices)
            candidate = context.run_dir / f"ice-v{target_vertices}.obj"
            command = [
                "wsl.exe",
                PaperExecutableAdapter._wsl_path(executable),
                PaperExecutableAdapter._wsl_path(context.prepared_mesh),
                str(target_vertices),
                PaperExecutableAdapter._wsl_path(candidate),
            ]
            measured = run_measured(
                command,
                context.root,
                context.run_dir / "logs" / f"ice-v{target_vertices}",
            )
            if measured.returncode != 0 or not candidate.is_file():
                raise RuntimeError(f"ICE exited with {measured.returncode} at {target_vertices} vertices")
            actual_faces = len(load_mesh(candidate, process=False).faces)
            attempts.append(
                {
                    "target_vertices": target_vertices,
                    "actual_faces": actual_faces,
                    "wall_seconds": measured.wall_seconds,
                }
            )
            error = abs(actual_faces - context.target_faces)
            if best is None or error < best[0]:
                best = (error, candidate, measured)
            if error / context.target_faces <= 0.02:
                break
            target_vertices = max(4, round(target_vertices * context.target_faces / max(actual_faces, 1)))
        if best is None:
            raise RuntimeError("ICE calibration produced no output")
        _, best_path, measured = best
        output = context.run_dir / "native.obj"
        shutil.copy2(best_path, output)
        return AdapterResult(
            output=output,
            source=self.source,
            command=measured.command,
            timing={
                "algorithm_wall_seconds": measured.wall_seconds,
                "calibration_wall_seconds": time.perf_counter() - calibration_start,
                "cpu_seconds": measured.cpu_seconds,
                "peak_rss_bytes": measured.peak_rss_bytes,
                "repetitions": 1,
            },
            parameters={
                "weight": 0.0,
                "export_semantics": "intrinsic_visualization_geometry",
                "calibration_attempts": attempts,
            },
        )


class CWFAdapter(ExternalTemplateAdapter):
    name = "cwf"
    executable_relative = Path("external") / "bin" / "cwf"

    def available(self, root: Path) -> tuple[bool, str]:
        executable = self.executable(root)
        return executable.is_file(), f"wsl2: {executable}"

    def run(self, context: AdapterContext) -> AdapterResult:
        executable = self.executable(context.root)
        mesh = load_mesh(context.prepared_mesh, process=False)
        target_sites = max(4, context.target_faces // 2 + 2)
        seed = int(context.parameters.get("seed", 20240801))
        sampled = sample_surface(mesh, target_sites, sample_color=False, seed=seed)
        points = sampled[0]
        face_ids = sampled[1]
        normals = np.asarray(mesh.face_normals)[face_ids]
        initial_points = context.run_dir / "cwf-initial-points.xyz"
        np.savetxt(initial_points, np.column_stack((points, normals)), fmt="%.17g")
        max_iterations = int(context.parameters.get("max_iterations", 50))
        command = [
            "wsl.exe",
            PaperExecutableAdapter._wsl_path(executable),
            PaperExecutableAdapter._wsl_path(context.prepared_mesh),
            PaperExecutableAdapter._wsl_path(initial_points),
            str(max_iterations),
        ]
        measured = run_measured(command, context.run_dir, context.run_dir / "logs")
        if measured.returncode != 0:
            raise RuntimeError(f"CWF exited with {measured.returncode}")
        candidates = sorted(context.run_dir.glob("Ours_*_Remesh.obj"))
        final_candidates = [path for path in candidates if "Iter" not in path.name]
        if len(final_candidates) != 1:
            raise RuntimeError("CWF did not produce an unambiguous final remesh")
        output = context.run_dir / "native.obj"
        shutil.copy2(final_candidates[0], output)
        return AdapterResult(
            output=output,
            source=self.source,
            command=command,
            timing={
                "algorithm_wall_seconds": measured.wall_seconds,
                "cpu_seconds": measured.cpu_seconds,
                "peak_rss_bytes": measured.peak_rss_bytes,
                "repetitions": 1,
            },
            parameters={
                "target_sites": target_sites,
                "initialization": "seeded area-weighted source-surface samples",
                "seed": seed,
                "max_iterations": max_iterations,
            },
        )


def adapter_for(name: str) -> BaselineAdapter:
    adapters: dict[str, BaselineAdapter] = {
        "qem": QSlimAdapter(),
        "qem4vr": QEM4VRAdapter(),
        "robustlpm": RobustLPMAdapter(),
        "ice": ICEAdapter(),
        "stmw": STMWAdapter(),
        "cwf": CWFAdapter(),
    }
    try:
        return adapters[name]
    except KeyError as error:
        raise ValueError(f"unknown baseline: {name}") from error
