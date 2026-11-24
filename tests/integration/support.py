"""入口集成与进程用例共用的小工具：指向替身的客户端、请求日志的读取与等待、管道驱动的真实进程。"""

import io
import json
import os
import subprocess
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx2
import pytest
from openai import OpenAI

from tests.integration.fake_model import FAKE_KEY, FakeModel

PROMPT = "你> "
"""会话的输入提示。"""

DROP_PREFIXES = ("LIME_STAR_", "OPENAI_")
# 不让本机的这些设置掩盖用例要验证的行为，例如输出编码。
DROP_NAMES = ("NO_PROXY", "PYTHONIOENCODING", "PYTHONUTF8", "PYTHONLEGACYWINDOWSSTDIO")


def child_env(model_env: dict[str, str]) -> dict[str, str]:
    """子进程的环境：去掉模型配置、SDK 和编码相关的变量，再按用例加入；回环地址不走代理。"""
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(DROP_PREFIXES) and key not in DROP_NAMES
    }
    env.update(model_env)
    env["NO_PROXY"] = "127.0.0.1,localhost"
    return env


RECORD_KEYS = [
    "time",
    "session_id",
    "thread_id",
    "turn_id",
    "request_id",
    "model",
    "status",
    "elapsed_ms",
    "usage",
    "error",
]
"""请求日志一条记录的全部字段（需求 R3.1）。"""


def client_for(model: FakeModel) -> OpenAI:
    """指向替身服务的客户端。不读环境里的代理设置，关掉自动重试。"""
    return OpenAI(
        base_url=model.url,
        api_key=FAKE_KEY,
        max_retries=0,
        http_client=httpx2.Client(trust_env=False),
    )


def read_log(path: Path) -> list[dict[str, Any]]:
    """读出请求日志的全部记录。文件还不存在时返回空列表。"""
    if not path.is_file():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line]


def wait_until(condition: Callable[[], bool], timeout: float = 10.0) -> None:
    """反复检查一个终态条件，直到它成立；到期还不成立按用例失败处理。"""
    deadline = time.monotonic() + timeout
    while not condition():
        if time.monotonic() > deadline:
            raise AssertionError(f"场景：等待条件成立；超时 {timeout} 秒")
        time.sleep(0.005)


def wait_for_log(path: Path, count: int, timeout: float = 10.0) -> list[dict[str, Any]]:
    """等到请求日志里有了 count 条记录。"""
    try:
        wait_until(lambda: len(read_log(path)) >= count, timeout)
    except AssertionError as exc:
        records = read_log(path)
        raise AssertionError(
            f"场景：等待请求日志；期望 {count} 条，实际 {len(records)} 条，超时 {timeout} 秒"
        ) from exc
    return read_log(path)


def decode_prefix(data: bytes) -> tuple[str, bytes]:
    """解码 data 里完整的 UTF-8 前缀；末尾不完整的多字节序列（最多 3 字节）留到下一次。

    完整的 data 优先整体解码。只有末尾确实是不完整序列时才留下尾巴；
    中间就有非法字节时整体按替换字符解码，不让尾巴无限增长。
    """
    for keep in range(0, min(3, len(data)) + 1):
        cut = len(data) - keep
        try:
            return data[:cut].decode("utf-8"), data[cut:]
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace"), b""


def run_lime_star(exe: Path, args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    """在给定目录里启动命令并等它结束。环境里不带任何模型配置变量。"""
    return subprocess.run(
        [str(exe), *args],
        cwd=cwd,
        env=child_env({}),
        capture_output=True,
        encoding="utf-8",
        timeout=30,
        check=False,
    )


class CliProcess:
    """通过管道驱动一个真实的 lime-star 进程：写一行输入、等某一路输出、收尾。"""

    def __init__(self, exe: Path, cwd: Path, env: dict[str, str]) -> None:
        self.process: subprocess.Popen[bytes] = subprocess.Popen(
            [str(exe)],
            cwd=cwd,
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self._text = {"stdout": "", "stderr": ""}
        self._changed = threading.Condition()
        self._readers = [
            threading.Thread(target=self._pump, args=(name,), daemon=True)
            for name in ("stdout", "stderr")
        ]
        for reader in self._readers:
            reader.start()

    def _pump(self, name: str) -> None:
        stream: io.BufferedReader = getattr(self.process, name)
        pending = b""
        for chunk in iter(lambda: stream.read1(4096), b""):
            text, pending = decode_prefix(pending + chunk)
            if text:
                with self._changed:
                    self._text[name] += text
                    self._changed.notify_all()
        if pending:
            with self._changed:
                self._text[name] += pending.decode("utf-8", errors="replace")
                self._changed.notify_all()

    def send(self, line: str) -> None:
        stdin = self.process.stdin
        assert stdin is not None
        stdin.write((line + "\n").encode("utf-8"))
        stdin.flush()

    def close_input(self) -> None:
        stdin = self.process.stdin
        if stdin is not None:
            stdin.close()

    def wait_for(self, stream: str, text: str, count: int = 1, timeout: float = 20.0) -> None:
        """等某一路输出里出现 count 处 text。等的是输出本身，不是固定时长。"""
        with self._changed:
            arrived = self._changed.wait_for(
                lambda: self.output(stream).count(text) >= count, timeout
            )
            seen = {name: self.output(name) for name in ("stdout", "stderr")}
        if not arrived:
            pytest.fail(
                f"场景：等待子进程 {stream} 里出现 {count} 处 {text!r}，超时 {timeout} 秒。"
                f"stdout={seen['stdout']!r} stderr={seen['stderr']!r}"
            )

    def output(self, stream: str) -> str:
        """到此刻为止的输出。Windows 管道上的换行是 CRLF，这里统一成 LF 再比对。"""
        with self._changed:
            return self._text[stream].replace("\r\n", "\n")

    def finish(self, timeout: float = 20.0) -> int:
        """等进程退出，返回退出码。"""
        try:
            code = self.process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            seen = {name: self.output(name) for name in ("stdout", "stderr")}
            self.close()
            pytest.fail(
                f"场景：等待子进程退出，超时 {timeout} 秒。"
                f"stdout={seen['stdout']!r} stderr={seen['stderr']!r}"
            )
        for reader in self._readers:
            reader.join(timeout=5)
        return code

    def close(self) -> None:
        """收尾：进程还活着就结束它，管道全部关掉。"""
        if self.process.poll() is None:
            self.process.kill()
            self.process.wait(timeout=10)
        for pipe in (self.process.stdin, self.process.stdout, self.process.stderr):
            if pipe is not None:
                pipe.close()
