"""入口集成与进程用例共用的夹具：本地替身模型、指向它的会话、模拟的 Ctrl+C。"""

import _thread
import os
import sys
import threading
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest

from lime_star.app import Session, open_session
from lime_star.model_provider import API_KEY_VAR, BASE_URL_VAR, MODEL_VAR
from lime_star.model_provider.request_log import LOG_DIR, REQUEST_LOG
from tests.integration.fake_model import FAKE_KEY, FAKE_MODEL, FakeModel
from tests.integration.support import CliProcess, child_env, client_for


@pytest.fixture(scope="session")
def lime_star() -> Path:
    """与运行测试的解释器装在同一个环境里的 lime-star 命令。"""
    name = "lime-star.exe" if os.name == "nt" else "lime-star"
    exe = Path(sys.executable).with_name(name)
    if not exe.is_file():
        pytest.fail(f"找不到 {exe}：先执行 uv sync，再用 uv run pytest 运行", pytrace=False)
    return exe


@pytest.fixture
def fake_model() -> Iterator[FakeModel]:
    model = FakeModel()
    model.start()
    yield model
    model.stop()


@pytest.fixture
def model_env(fake_model: FakeModel) -> dict[str, str]:
    """指向替身服务的三个模型配置变量。"""
    return {BASE_URL_VAR: fake_model.url, API_KEY_VAR: FAKE_KEY, MODEL_VAR: FAKE_MODEL}


@pytest.fixture
def make_session(
    fake_model: FakeModel, model_env: dict[str, str], tmp_path: Path
) -> Callable[..., Session]:
    """在临时工作目录里打开一个指向替身服务的会话。额外的关键字参数原样交给 open_session。"""

    def make(**overrides: Any) -> Session:
        return open_session(
            env=model_env, workdir=tmp_path, client=client_for(fake_model), **overrides
        )

    return make


@pytest.fixture
def log_path(tmp_path: Path) -> Path:
    return tmp_path / LOG_DIR / REQUEST_LOG


@pytest.fixture
def ctrl_c() -> Callable[[Callable[[], bool]], None]:
    """等到谓词成立后，在主线程里模拟一次 Ctrl+C。"""

    def fire(when: Callable[[], bool]) -> None:
        def run() -> None:
            deadline = time.monotonic() + 30.0
            while not when():
                if time.monotonic() > deadline:
                    return
                time.sleep(0.005)
            _thread.interrupt_main()

        threading.Thread(target=run, name="ctrl-c", daemon=True).start()

    return fire


@pytest.fixture
def start_cli(lime_star: Path, tmp_path: Path) -> Iterator[Callable[..., CliProcess]]:
    """在临时工作目录里启动真实的会话进程，用例结束时保证它不残留。"""
    started: list[CliProcess] = []

    def start(model_env: dict[str, str] | None = None) -> CliProcess:
        process = CliProcess(lime_star, tmp_path, child_env(model_env or {}))
        started.append(process)
        return process

    yield start
    for process in started:
        process.close()
