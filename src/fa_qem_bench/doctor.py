from __future__ import annotations

import importlib.util
import shutil
from typing import Any

import psutil

from .adapters import adapter_for
from .config import RUNNABLE_METHODS, ExperimentConfig
from .util import command_version, environment_snapshot, sha256_file


def doctor(config: ExperimentConfig) -> dict[str, Any]:
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage(config.root.anchor)
    packages = {
        name: importlib.util.find_spec(name) is not None
        for name in (
            "numpy",
            "scipy",
            "trimesh",
            "rtree",
            "fast_simplification",
            "xatlas",
            "pygltflib",
        )
    }
    methods = {}
    for method in RUNNABLE_METHODS:
        available, detail = adapter_for(method).available(config.root)
        methods[method] = {"available": available, "detail": detail}
    return {
        "ok": sha256_file(config.source) == config.data["source"]["sha256"],
        "source": str(config.source),
        "source_sha256": sha256_file(config.source),
        "environment": environment_snapshot(config.root),
        "commands": {
            name: shutil.which(name)
            for name in (
                "git",
                "uv",
                "cmake",
                "ninja",
                "cl",
                "gcc",
                "g++",
                "blender",
                "pueue",
                "codegraph",
            )
        },
        "versions": {
            "uv": command_version(["uv", "--version"]),
            "gcc": command_version(["gcc", "--version"]),
        },
        "packages": packages,
        "methods": methods,
        "resources": {
            "physical_cores": psutil.cpu_count(logical=False),
            "logical_cores": psutil.cpu_count(logical=True),
            "memory_total": memory.total,
            "memory_available": memory.available,
            "disk_free": disk.free,
        },
    }
