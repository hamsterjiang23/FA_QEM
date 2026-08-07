from __future__ import annotations

import shutil
import statistics
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from trimesh.sample import sample_surface

from ..mesh import load_mesh
from ..process import ProcessResult, run_measured, run_measured_wsl, run_repeated
from ..util import sha256_file


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


def _timing_summary(
    warmups: list[ProcessResult],
    results: list[ProcessResult],
    *,
    calibration_wall_seconds: float | None = None,
) -> dict[str, Any]:
    if not results:
        raise ValueError("at least one measured result is required")
    wall = [result.wall_seconds for result in results]
    cpu = [result.cpu_seconds for result in results]
    rss = [result.peak_rss_bytes for result in results]
    summary: dict[str, Any] = {
        "algorithm_wall_seconds": statistics.median(wall),
        "algorithm_wall_seconds_range": [min(wall), max(wall)],
        "algorithm_wall_seconds_samples": wall,
        "cpu_seconds": statistics.median(cpu),
        "cpu_seconds_range": [min(cpu), max(cpu)],
        "cpu_seconds_samples": cpu,
        "peak_rss_bytes": max(rss),
        "peak_rss_bytes_samples": rss,
        "resource_measurement": results[-1].resource_source,
        "warmup_runs": len(warmups),
        "warmup_wall_seconds": [result.wall_seconds for result in warmups],
        "repetitions": len(results),
    }
    if calibration_wall_seconds is not None:
        summary["calibration_wall_seconds"] = calibration_wall_seconds
    return summary


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
        if command and Path(command[0]).name.lower() == "wsl.exe":
            return run_measured_wsl(command, context.root, context.run_dir / "logs")
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
        warmups, results = run_repeated(
            command,
            context.root,
            context.run_dir / "logs" / "benchmark",
            wsl=True,
            warmups=int(context.parameters.get("warmup_runs", 1)),
            repetitions=int(context.parameters.get("timed_repetitions", 3)),
        )
        failed = next((result for result in [*warmups, *results] if result.returncode != 0), None)
        if failed is not None:
            raise RuntimeError(f"QSlim exited with {failed.returncode}")
        measured = results[-1]
        return AdapterResult(
            output=output,
            source=self.source,
            command=measured.command,
            timing=_timing_summary(warmups, results),
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
        parameters = dict(context.parameters)
        successive_map = context.run_dir / "successive-map.bin"
        if self.name in {"stmw", "fa-qem"}:
            command.extend(
                [
                    "--virtual-radius",
                    "0.01",
                    "--successive-map",
                    native(successive_map),
                ]
            )
            parameters["virtual_radius_unit_diagonal"] = 0.01
            if self.name == "fa-qem":
                command.extend(
                    [
                        "--area-weight",
                        "100",
                        "--boundary-weight",
                        "500",
                        "--uv-weight",
                        "5000",
                        "--normal-weight",
                        "0.01",
                        "--plane-area-weight",
                        "1",
                    ]
                )
                parameters.update(
                    {
                        "area_weight": 100.0,
                        "boundary_weight": 500.0,
                        "uv_seam_weight": 5000.0,
                        "normal_weight": 0.01,
                        "plane_area_weight": 1.0,
                        "weld_absolute_tolerance": 1e-6,
                        "minimum_edge_relative_diagonal": 1e-8,
                        "collapse_validation": (
                            "paper flip-only veto plus zero-area safeguard; "
                            "link condition retained when the welded input is initially manifold"
                        ),
                    }
                )
        elif self.name == "qem4vr":
            command.extend(["--boundary-weight", "5", "--material-weight", "1000"])
            parameters.update(
                {
                    "boundary_weight": 5.0,
                    "material_critical_weight": 1000.0,
                    "placement_policy": "subset_endpoint",
                }
            )
        warmups, results = run_repeated(
            command,
            context.root,
            context.run_dir / "logs" / "benchmark",
            wsl=runtime == "wsl2",
            warmups=int(context.parameters.get("warmup_runs", 1)),
            repetitions=int(context.parameters.get("timed_repetitions", 3)),
        )
        failed = next((result for result in [*warmups, *results] if result.returncode != 0), None)
        if failed is not None:
            raise RuntimeError(f"{self.name} exited with {failed.returncode}")
        measured = results[-1]
        if self.name in {"stmw", "fa-qem"}:
            if not successive_map.is_file():
                raise RuntimeError(f"{self.name} did not produce its successive mapping history")
            parameters.update(
                {
                    "successive_mapping_path": str(successive_map.relative_to(context.root)),
                    "successive_mapping_sha256": sha256_file(successive_map),
                }
            )
        return AdapterResult(
            output=output,
            source=self.source,
            command=measured.command,
            timing=_timing_summary(warmups, results),
            parameters=parameters,
        )


class QEM4VRAdapter(PaperExecutableAdapter):
    name = "qem4vr"
    source = "paper-guided local reimplementation; published weights"


class STMWAdapter(PaperExecutableAdapter):
    name = "stmw"
    source = "paper-guided local reimplementation; radius assumption disclosed"


class FAQEMAdapter(PaperExecutableAdapter):
    name = "fa-qem"
    source = "paper-guided local reimplementation; author repository contains no implementation"


class ExternalTemplateAdapter(ExecutableAdapter):
    name = ""
    source = "official external implementation"

    def run(self, context: AdapterContext) -> AdapterResult:
        raise RuntimeError(f"{self.name} adapter is not configured; run acquisition/build first")


class RobustLPMAdapter(ExternalTemplateAdapter):
    name = "robustlpm"
    executable_relative = Path("external") / "robustlpm" / "RoLoPM_EXE" / "SurfaceRemeshingCli_bin.exe"

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
        calibration_wall = time.perf_counter() - calibration_start
        _, _, _, best_command = best
        best_screen_size = int(best_command[best_command.index("-n") + 1])
        benchmark_token = time.time_ns()

        def benchmark_once(label: str) -> tuple[Path, ProcessResult, int]:
            output_dir = context.run_dir / f"robustlpm-benchmark-{benchmark_token}-{label}"
            output_dir.mkdir(parents=True, exist_ok=True)
            command = [
                str(executable),
                "-i",
                str(context.prepared_mesh),
                "-n",
                str(best_screen_size),
                "-f",
                str(context.target_faces),
                "-o",
                str(output_dir),
            ]
            measured = run_measured(
                command,
                context.root,
                context.run_dir / "logs" / f"benchmark-{label}",
            )
            if measured.returncode != 0:
                raise RuntimeError(f"RobustLPM benchmark {label} exited with {measured.returncode}")
            candidates = sorted(output_dir.glob("*_ours_final.obj"))
            if len(candidates) != 1:
                raise RuntimeError(f"RobustLPM benchmark {label} produced ambiguous output")
            return candidates[0], measured, len(load_mesh(candidates[0], process=False).faces)

        warmup_count = int(context.parameters.get("warmup_runs", 1))
        repetition_count = int(context.parameters.get("timed_repetitions", 3))
        warmup_outputs = [benchmark_once(f"warmup-{index + 1}") for index in range(warmup_count)]
        measured_outputs = [benchmark_once(f"repeat-{index + 1}") for index in range(repetition_count)]
        produced, measured, _ = measured_outputs[-1]
        results = [item[1] for item in measured_outputs]
        output = context.run_dir / "native.obj"
        shutil.copy2(produced, output)
        return AdapterResult(
            output=output,
            source=self.source,
            command=measured.command,
            timing=_timing_summary(
                [item[1] for item in warmup_outputs],
                results,
                calibration_wall_seconds=calibration_wall,
            ),
            parameters={
                "screen_size": best_screen_size,
                "final_face_cap": context.target_faces,
                "target_control": "official -f option",
                "calibration_attempts": attempts,
                "benchmark_actual_faces": {
                    "warmup": [item[2] for item in warmup_outputs],
                    "repetitions": [item[2] for item in measured_outputs],
                },
            },
        )


class ICEAdapter(ExternalTemplateAdapter):
    name = "ice"
    executable_relative = Path("external") / "bin" / "ice_coarsening"

    def run(self, context: AdapterContext) -> AdapterResult:
        executable = self.executable(context.root)
        target_vertices = max(4, context.target_faces // 2 + 2)
        attempts: list[dict[str, Any]] = []
        best: tuple[int, Path, ProcessResult, int] | None = None
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
            measured = run_measured_wsl(
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
                best = (error, candidate, measured, target_vertices)
            if error / context.target_faces <= 0.02:
                break
            target_vertices = max(4, round(target_vertices * context.target_faces / max(actual_faces, 1)))
        if best is None:
            raise RuntimeError("ICE calibration produced no output")
        calibration_wall = time.perf_counter() - calibration_start
        _, _, _, calibrated_vertices = best

        def benchmark_once(label: str) -> tuple[Path, ProcessResult, int]:
            candidate = context.run_dir / f"ice-benchmark-{label}-v{calibrated_vertices}.obj"
            command = [
                "wsl.exe",
                PaperExecutableAdapter._wsl_path(executable),
                PaperExecutableAdapter._wsl_path(context.prepared_mesh),
                str(calibrated_vertices),
                PaperExecutableAdapter._wsl_path(candidate),
            ]
            measured = run_measured_wsl(
                command,
                context.root,
                context.run_dir / "logs" / f"benchmark-{label}",
            )
            if measured.returncode != 0 or not candidate.is_file():
                raise RuntimeError(f"ICE benchmark {label} exited with {measured.returncode}")
            return candidate, measured, len(load_mesh(candidate, process=False).faces)

        warmup_count = int(context.parameters.get("warmup_runs", 1))
        repetition_count = int(context.parameters.get("timed_repetitions", 3))
        warmup_outputs = [benchmark_once(f"warmup-{index + 1}") for index in range(warmup_count)]
        measured_outputs = [benchmark_once(f"repeat-{index + 1}") for index in range(repetition_count)]
        best_path, measured, _ = measured_outputs[-1]
        results = [item[1] for item in measured_outputs]
        output = context.run_dir / "native.obj"
        shutil.copy2(best_path, output)
        return AdapterResult(
            output=output,
            source=self.source,
            command=measured.command,
            timing=_timing_summary(
                [item[1] for item in warmup_outputs],
                results,
                calibration_wall_seconds=calibration_wall,
            ),
            parameters={
                "weight": 0.0,
                "export_semantics": "intrinsic_visualization_geometry",
                "calibration_attempts": attempts,
                "calibrated_target_vertices": calibrated_vertices,
                "benchmark_actual_faces": {
                    "warmup": [item[2] for item in warmup_outputs],
                    "repetitions": [item[2] for item in measured_outputs],
                },
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
        probe = run_measured_wsl(command, context.run_dir, context.run_dir / "logs" / "classification-probe")
        if probe.returncode != 0:
            raise RuntimeError(f"CWF exited with {probe.returncode}")
        slow_threshold = float(context.parameters.get("slow_threshold_seconds", 3600.0))
        if probe.wall_seconds < slow_threshold:
            _, results = run_repeated(
                command,
                context.run_dir,
                context.run_dir / "logs" / "benchmark",
                wsl=True,
                warmups=0,
                repetitions=int(context.parameters.get("timed_repetitions", 3)),
            )
            failed = next((result for result in results if result.returncode != 0), None)
            if failed is not None:
                raise RuntimeError(f"CWF benchmark exited with {failed.returncode}")
            warmups = [probe]
        else:
            warmups = []
            results = [probe]
        measured = results[-1]
        candidates = sorted(context.run_dir.glob("Ours_*_Remesh.obj"))
        final_candidates = [path for path in candidates if "Iter" not in path.name]
        if len(final_candidates) != 1:
            raise RuntimeError("CWF did not produce an unambiguous final remesh")
        output = context.run_dir / "native.obj"
        shutil.copy2(final_candidates[0], output)
        return AdapterResult(
            output=output,
            source=self.source,
            command=measured.command,
            timing={
                **_timing_summary(warmups, results),
                "classification_probe_wall_seconds": probe.wall_seconds,
                "slow_threshold_seconds": slow_threshold,
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
        "fa-qem": FAQEMAdapter(),
    }
    try:
        return adapters[name]
    except KeyError as error:
        raise ValueError(f"unknown baseline: {name}") from error
