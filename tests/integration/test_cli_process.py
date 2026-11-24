"""真实进程里的 lime-star 命令（R1.1 到 R1.3）。

每条用例都启动已安装的 lime-star 命令，核对退出码、标准输出和标准错误。
命令来自 uv sync 装好的项目环境，所以要用 uv run pytest 运行。
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from lime_star import __version__

MODEL_ENV_PREFIX = "LIME_STAR_"


@pytest.fixture(scope="session")
def lime_star() -> Path:
    """与运行测试的解释器装在同一个环境里的 lime-star 命令。"""
    name = "lime-star.exe" if os.name == "nt" else "lime-star"
    exe = Path(sys.executable).with_name(name)
    if not exe.is_file():
        pytest.fail(f"找不到 {exe}：先执行 uv sync，再用 uv run pytest 运行", pytrace=False)
    return exe


def run_lime_star(exe: Path, args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    """在给定目录里启动命令。环境里不带任何模型配置变量。"""
    env = {key: value for key, value in os.environ.items() if not key.startswith(MODEL_ENV_PREFIX)}
    return subprocess.run(
        [str(exe), *args],
        cwd=cwd,
        env=env,
        capture_output=True,
        encoding="utf-8",
        timeout=30,
        check=False,
    )


def test_version_prints_one_line_and_exits_zero(lime_star: Path, tmp_path: Path) -> None:
    """R1.1-S1：标准输出只有版本这一行，退出码为 0。"""
    result = run_lime_star(lime_star, ["--version"], tmp_path)
    assert result.returncode == 0
    assert result.stdout.splitlines() == [f"lime-star {__version__}"]
    assert result.stderr == ""


def test_version_works_without_model_config(lime_star: Path, tmp_path: Path) -> None:
    """R1.1-S2：工作目录里没有模型配置，查版本仍然成功。"""
    assert list(tmp_path.iterdir()) == []
    result = run_lime_star(lime_star, ["--version"], tmp_path)
    assert result.returncode == 0
    assert result.stdout.splitlines() == [f"lime-star {__version__}"]


def test_help_lists_version_with_description(lime_star: Path, tmp_path: Path) -> None:
    """R1.2-S1：帮助里有 --version 和一句话说明，退出码为 0。"""
    result = run_lime_star(lime_star, ["--help"], tmp_path)
    assert result.returncode == 0
    assert "--version" in result.stdout
    assert "显示版本号并退出" in result.stdout
    assert result.stderr == ""


def test_help_does_not_list_resume_yet(lime_star: Path, tmp_path: Path) -> None:
    """R1.3 的边界：--resume 由路线图 P5 交付，在那之前帮助里不列它。"""
    result = run_lime_star(lime_star, ["--help"], tmp_path)
    assert "--resume" not in result.stdout


def test_unknown_argument_exits_two_and_names_it(lime_star: Path, tmp_path: Path) -> None:
    """R1.3-S1：退出码为 2，标准错误指明未知的参数，标准输出为空。"""
    result = run_lime_star(lime_star, ["--nosuch"], tmp_path)
    assert result.returncode == 2
    assert "--nosuch" in result.stderr
    assert result.stdout == ""


def test_bare_command_is_a_usage_error_for_now(lime_star: Path, tmp_path: Path) -> None:
    """过渡行为，没有需求编号。路线图 P1 用 R13.1 取代它，届时删除本用例。"""
    result = run_lime_star(lime_star, [], tmp_path)
    assert result.returncode == 2
    assert "用法" in result.stderr
    assert result.stdout == ""
