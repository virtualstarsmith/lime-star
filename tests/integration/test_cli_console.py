"""真实控制台里的 lime-star：真实的 Ctrl+C 事件和真实控制台上的输入读取。

只在 Windows 上运行。每条用例在一个隐藏的新控制台里启动真实的 lime-star 进程，
由同一控制台里的宿主进程（console_host.py）投递按键和 Ctrl+C 事件。
证据等级：Gate B，进程的输入输出是真实控制台；模型是测试替身。
覆盖 R13.8-S1、R13.9-S1、R13.11-S1、R13.12-S1、R12.5-S2、R12.6-S1。
路线图 P4 加入 R7.9-S1（在控制台上输入 y）和 R12.5-S1（命令运行中的 Ctrl+C 结束整棵进程树）。
管道驱动的用例补不到这里的 Ctrl+C：它必须是一次真实的控制台事件。
"""

import ctypes
import json
import os
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Iterator
from ctypes import wintypes
from pathlib import Path
from typing import Any

import pytest

from lime_star import __version__
from lime_star.cli.chat import ASK
from tests.integration.fake_model import FAKE_KEY, FakeModel, Hold
from tests.integration.support import (
    PROMPT,
    SLEEPER,
    alive,
    child_env,
    transcript_file,
    wait_for_log,
    wait_until,
)

HOST = Path(__file__).with_name("console_host.py")
SYNCHRONIZE = 0x00100000

pytestmark = pytest.mark.skipif(
    os.name != "nt", reason="只在 Windows 上运行：依赖 Windows 控制台接口"
)


def _start_hidden(
    command: str, cwd: Path, out: Path, err: Path, env: dict[str, str]
) -> subprocess.Popen[bytes]:
    """在新的隐藏控制台里经宿主启动命令，返回宿主进程。"""
    if sys.platform != "win32":
        raise AssertionError("只在 Windows 上运行")
    startup = subprocess.STARTUPINFO()
    startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startup.wShowWindow = subprocess.SW_HIDE
    return subprocess.Popen(
        [sys.executable, str(HOST), command, str(cwd), str(out), str(err)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=subprocess.CREATE_NEW_CONSOLE,
        startupinfo=startup,
        env=env,
    )


def _open_wait_handle(pid: int) -> tuple[Any, int]:
    """打开一个只能用来等待的进程句柄。

    之后凭它判断会话进程是否结束：句柄认的是进程对象，不受进程号被复用的影响。
    """
    if sys.platform != "win32":
        raise AssertionError("只在 Windows 上运行")
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.WaitForSingleObject.restype = wintypes.DWORD
    kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel32.OpenProcess(SYNCHRONIZE, False, pid)
    if handle is None:
        raise OSError(f"OpenProcess 失败，Windows 错误码 {ctypes.get_last_error()}")
    return kernel32, handle


class ConsoleSession:
    """隐藏控制台里的一个真实会话进程。"""

    def __init__(self, exe: Path, cwd: Path, env: dict[str, str]) -> None:
        self._paths = {"stdout": cwd / "console-stdout.log", "stderr": cwd / "console-stderr.log"}
        self._cwd = cwd
        self._closed = False
        self._kernel32: Any = None
        self._wait: int | None = None
        self._host = _start_hidden(str(exe), cwd, self._paths["stdout"], self._paths["stderr"], env)
        if not self._adopt_reported_process():
            self.close()
            pytest.fail(
                "场景：宿主启动被测进程后报告它的进程号；"
                f"宿主 stderr={self._host_errors().decode('utf-8', 'replace')!r}"
            )

    def _adopt_reported_process(self) -> bool:
        """读宿主报告的被测进程号，并为它打开等待句柄。"""
        reported: list[bytes] = []
        stdout = self._host.stdout
        if stdout is None:
            return False

        def read() -> None:
            reported.append(stdout.readline())

        reader = threading.Thread(target=read, daemon=True)
        reader.start()
        reader.join(timeout=20)
        if len(reported) != 1 or not reported[0].strip().isdigit():
            return False
        self._kernel32, self._wait = _open_wait_handle(int(reported[0]))
        return True

    def type(self, text: str) -> None:
        self._send("text " + text)

    def ctrl_c(self) -> None:
        self._send("ctrlc")

    def wait_for(self, stream: str, text: str, count: int = 1, timeout: float = 10.0) -> None:
        """等某一路输出里出现 count 处 text。等的是输出本身，不是固定时长。"""
        deadline = time.monotonic() + timeout
        while self.output(stream).count(text) < count:
            if time.monotonic() > deadline:
                pytest.fail(
                    f"场景：等待控制台会话的 {stream} 里出现 {count} 处 {text!r}，"
                    f"超时 {timeout} 秒。stdout={self.output('stdout')!r} "
                    f"stderr={self.output('stderr')!r}"
                )
            time.sleep(0.01)

    def output(self, stream: str) -> str:
        """到此刻为止的输出。控制台会话的输出被重定向到文件，换行是 CRLF，这里统一成 LF。"""
        try:
            return self._paths[stream].read_bytes().decode("utf-8").replace("\r\n", "\n")
        except FileNotFoundError:
            return ""

    def finish(self, timeout: float = 10.0) -> int:
        """等会话进程退出，返回它的退出码。"""
        try:
            code = self._host.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            self.close()
            pytest.fail(
                f"场景：等待控制台会话退出，超时 {timeout} 秒。"
                f"stdout={self.output('stdout')!r} stderr={self.output('stderr')!r}"
            )
        assert self._host_errors() == b"", self._host_errors().decode("utf-8", "replace")
        self.close()
        return code

    def close(self) -> None:
        """收尾，并确认会话进程已经结束。

        先关命令管道：宿主读到输入结束，就结束会话进程并以它的退出码退出。
        宿主仍在运行时结束宿主，它持有的作业随之关闭，会话进程也结束。
        最后凭进程句柄等到会话进程结束，超时按用例失败处理。
        """
        if self._closed:
            return
        self._closed = True
        if self._host.poll() is None:
            if self._host.stdin is not None:
                self._host.stdin.close()
            try:
                self._host.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._host.kill()
                self._host.wait(timeout=10)
        if self._wait is not None and self._kernel32 is not None:
            if self._kernel32.WaitForSingleObject(self._wait, 5000) != 0:
                pytest.fail("场景：收尾后确认会话进程已经结束；它 5 秒后仍然活着")
            self._kernel32.CloseHandle(self._wait)
        for pipe in (self._host.stdin, self._host.stdout, self._host.stderr):
            if pipe is not None:
                pipe.close()

    def banner(self) -> str:
        return f"lime-star {__version__}  {self._cwd}\n"

    def _send(self, command: str) -> None:
        stdin = self._host.stdin
        assert stdin is not None
        stdin.write((command + "\n").encode("utf-8"))
        stdin.flush()

    def _host_errors(self) -> bytes:
        stderr = self._host.stderr
        return stderr.read() if stderr is not None else b""


@pytest.fixture
def start_console(
    lime_star: Path, tmp_path: Path
) -> Iterator[Callable[[dict[str, str]], ConsoleSession]]:
    started: list[ConsoleSession] = []

    def start(model_env: dict[str, str]) -> ConsoleSession:
        session = ConsoleSession(lime_star, tmp_path, child_env(model_env))
        started.append(session)
        return session

    yield start
    for session in started:
        session.close()


def contents(messages: list[dict[str, object]]) -> list[object]:
    """请求里系统指令之后的消息文本。"""
    return [message["content"] for message in messages[1:]]


def test_ctrl_c_during_a_turn_cancels_it_and_returns_to_the_prompt(
    start_console: Callable[..., ConsoleSession],
    model_env: dict[str, str],
    fake_model: FakeModel,
    log_path: Path,
) -> None:
    """R13.11-S1、R12.5-S2：回合进行中按 Ctrl+C，回合停止并显示已取消，随后回到输入提示。"""
    hold = Hold()
    fake_model.reply("迟到的回复", hold=hold)
    session = start_console(model_env)
    session.wait_for("stdout", PROMPT)
    session.type("第一问")
    fake_model.wait_for_requests(1)
    pressed = time.monotonic()
    session.ctrl_c()
    session.wait_for("stdout", "已取消。\n" + PROMPT)
    assert time.monotonic() - pressed < 5, "Ctrl+C 之后 5 秒内回合应当已经取消"
    hold.release()
    [record] = wait_for_log(log_path, 1)
    assert record["status"] == "ok"
    session.type("/exit")
    assert session.finish() == 0
    assert session.output("stdout") == session.banner() + PROMPT + "已取消。\n" + PROMPT
    assert session.output("stderr") == ""


def test_ctrl_c_at_the_prompt_ends_the_session_with_zero(
    start_console: Callable[..., ConsoleSession],
    model_env: dict[str, str],
    fake_model: FakeModel,
) -> None:
    """R13.12-S1：在输入提示处按 Ctrl+C，会话以 0 结束。"""
    session = start_console(model_env)
    session.wait_for("stdout", PROMPT)
    session.ctrl_c()
    assert session.finish() == 0
    assert session.output("stdout") == session.banner() + PROMPT
    assert session.output("stderr") == ""
    assert fake_model.requests() == []


def test_session_goes_on_after_a_cancelled_turn(
    start_console: Callable[..., ConsoleSession],
    model_env: dict[str, str],
    fake_model: FakeModel,
) -> None:
    """R12.6-S1：取消后下一条消息开始新回合，带上取消之前的历史；迟到的回复不进入会话。"""
    hold = Hold()
    fake_model.reply("迟到的回复", hold=hold)
    fake_model.reply("第二答")
    session = start_console(model_env)
    session.wait_for("stdout", PROMPT)
    session.type("第一问")
    fake_model.wait_for_requests(1)
    session.ctrl_c()
    session.wait_for("stdout", "已取消。\n" + PROMPT)
    hold.release()
    session.type("第二问")
    session.wait_for("stdout", "第二答\n" + PROMPT)
    session.type("/exit")
    assert session.finish() == 0
    assert session.output("stdout") == (
        session.banner() + PROMPT + "已取消。\n" + PROMPT + "第二答\n" + PROMPT
    )
    first, second = fake_model.requests()
    assert contents(first.messages) == ["第一问"]
    assert contents(second.messages) == ["第一问", "第二问"]


def test_input_typed_during_a_turn_is_dropped_and_reported(
    start_console: Callable[..., ConsoleSession],
    model_env: dict[str, str],
    fake_model: FakeModel,
) -> None:
    """R13.8-S1、R13.9-S1：回合进行中在控制台里输入的行不进入会话，回合结束后提示忽略。"""
    hold = Hold()
    fake_model.reply("答", hold=hold)
    fake_model.reply("再答")
    session = start_console(model_env)
    session.wait_for("stdout", PROMPT)
    session.type("第一问")
    fake_model.wait_for_requests(1)
    session.type("被丢弃的一行")
    hold.release()
    session.wait_for("stderr", "已忽略 1 行回合中收到的输入。\n")
    session.wait_for("stdout", PROMPT, count=2)
    session.type("第二问")
    session.wait_for("stdout", "再答\n" + PROMPT)
    session.type("/exit")
    assert session.finish() == 0
    assert session.output("stderr") == "已忽略 1 行回合中收到的输入。\n"
    first, second = fake_model.requests()
    assert contents(first.messages) == ["第一问"]
    assert contents(second.messages) == ["第一问", "答", "第二问"]
    assert FAKE_KEY not in session.output("stdout") + session.output("stderr")


def test_closing_a_stuck_session_ends_the_process(
    start_console: Callable[..., ConsoleSession],
    model_env: dict[str, str],
    fake_model: FakeModel,
) -> None:
    """夹具自己的保证：用例在回合中途失败时，收尾也必须结束会话进程。

    close() 凭进程句柄确认会话进程已经结束，确认不了就让用例失败。
    没有这条保证，失败的用例会在隐藏控制台里留下一个一直等输入的进程。
    """
    hold = Hold()
    fake_model.reply("迟到的回复", hold=hold)
    session = start_console(model_env)
    session.wait_for("stdout", PROMPT)
    session.type("第一问")
    fake_model.wait_for_requests(1)
    session.close()
    hold.release()


def test_y_typed_on_the_console_approves_a_write(
    start_console: Callable[..., ConsoleSession],
    model_env: dict[str, str],
    fake_model: FakeModel,
    tmp_path: Path,
) -> None:
    """R7.9-S1、R13.6：在真实控制台上对着批准提示输入 y，写文件执行；中文的提示和内容不乱码。"""
    content = "print('你好')\n"
    write = json.dumps({"path": "hello.py", "content": content}, ensure_ascii=False)
    fake_model.call(("write_file", write))
    fake_model.reply("写好了")
    session = start_console(model_env)
    session.wait_for("stdout", PROMPT)
    session.type("新建 hello.py")
    session.wait_for("stdout", ASK)
    session.type("y")
    session.wait_for("stdout", PROMPT, count=2)
    session.type("/exit")
    assert session.finish() == 0
    assert (tmp_path / "hello.py").read_bytes() == content.encode("utf-8")
    assert session.output("stdout") == (
        session.banner()
        + PROMPT
        + f"调用 write_file {write}\n"
        + "请求批准 write_file：写入 hello.py（新建文件）。要写入的内容：\n"
        + f"{content}----- 内容结束，共 1 行 -----\n"
        + "[y/n] 已批准。\n结果：已写入 hello.py，新建文件，1 行\n"
        + "写好了\n"
        + PROMPT
    )
    assert session.output("stderr") == ""
    assert FAKE_KEY not in session.output("stdout") + session.output("stderr")


def test_ctrl_c_while_a_command_runs_ends_the_whole_process_tree(
    start_console: Callable[..., ConsoleSession],
    model_env: dict[str, str],
    fake_model: FakeModel,
    tmp_path: Path,
) -> None:
    """R12.5-S1：命令运行中按真实的 Ctrl+C，命令进程及其子进程都结束，终端显示已取消；
    已经产生的输出如实记进了会话记录。"""
    (tmp_path / "sleeper.py").write_text(SLEEPER, encoding="utf-8")
    command = "python sleeper.py"
    fake_model.call(("run_command", {"command": command}))
    session = start_console(model_env)
    session.wait_for("stdout", PROMPT)
    session.type("运行 sleeper.py")
    session.wait_for("stdout", ASK)
    session.type("y")
    session.wait_for("stdout", "已批准。\n")
    wait_until(lambda: (tmp_path / "pids.txt").exists())
    pressed = time.monotonic()
    session.ctrl_c()
    session.wait_for("stdout", "已取消。\n" + PROMPT)
    assert time.monotonic() - pressed < 5, "Ctrl+C 之后 5 秒内回合应当已经取消"
    parent, child = map(int, (tmp_path / "pids.txt").read_text().split())
    wait_until(lambda: not (alive(parent) or alive(child)))
    session.type("/exit")
    assert session.finish() == 0
    assert session.output("stdout") == (
        session.banner()
        + PROMPT
        + f"调用 run_command {json.dumps({'command': command})}\n"
        + f"请求批准 run_command：在工作目录里执行下面的命令：\n{command}\n"
        + "[y/n] 已批准。\n结果出错：已取消，命令已终止\n"
        + "已取消。\n"
        + PROMPT
    )
    assert session.output("stderr") == ""
    raw = transcript_file(tmp_path).read_bytes()
    entries = [json.loads(line) for line in raw.split(b"\n")[:-1]]
    assert [(entry["type"], entry.get("decision"), entry.get("outcome")) for entry in entries] == [
        ("turn_start", None, None),
        ("user_message", None, None),
        ("tool_call", None, None),
        ("approval", "approved", None),
        ("tool_result", None, None),
        ("turn_end", None, "cancelled"),
    ]
    assert entries[4]["content"] == (
        "用户按 Ctrl+C 取消了回合，命令已被终止。截至那时已有的输出如下。\nstarted"
    )
    assert entries[4]["summary"] == "已取消，命令已终止"
