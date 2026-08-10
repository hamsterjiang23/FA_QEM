from pathlib import Path

import pytest

from fa_qem_bench.config import load_config


def test_config_targets() -> None:
    config = load_config(Path("experiment.yaml"))
    assert config.target("0.5") == 82470
    assert config.target("0.1") == 16494
    assert config.target("0.01") == 1649
    assert config.source_base_color == Path("Test_Model/deliverty/textures/basecolor.png").resolve()


def test_config_rejects_unknown_ratio() -> None:
    config = load_config(Path("experiment.yaml"))
    with pytest.raises(ValueError, match="unsupported ratio"):
        config.target("0.2")
