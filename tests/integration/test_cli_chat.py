"""进程内运行会话的终端交互循环：横幅与提示、空行、退出、输入结束、Ctrl+C。

证据等级：入口集成（CLI 的交互循环这一层，不经过真实进程）。真实进程的用例在
test_cli_process.py。Ctrl+C 用 _thread.interrupt_main() 模拟：它和真实 Ctrl+C 一样
在主线程里挂起一个中断，但不经过控制台。模型是测试替身。
覆盖 R13.1-S1、R13.3-S1、R13.4-S1、R13.9-S1、R13.11-S1、R13.12-S1、R13.13-S1。
"""

import io
import queue
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from lime_star import __version__
from lime_star.app import Outcome, Session
from lime_star.cli.chat import PROMPT, InputError, StdinLines, chat
from tests.integration.fake_model import FAKE_KEY, FakeModel, Hold
from tests.integration.support import wait_until

BLANK_LINES = 3


class ScriptedLines:
    """按脚本给行的输入源。没有给出下一行之前一直等；end() 之后返回 None。"""

    def __init__(self) -> None:
        self._queue: queue.Queue[str | None] = queue.Queue()
        self.dropped = 0

    def feed(self, line: str) -> None:
        self._queue.put(line)

    def end(self) -> None:
        self._queue.put(None)

    def next_line(self) -> str | None:
        while True:
            try:
                return self._queue.get(timeout=0.01)
            except queue.Empty:
                continue

    def drain(self) -> int:
        dropped, self.dropped = self.dropped, 0
        return dropped


def in_thread(action: Callable[[], None]) -> threading.Thread:
    thread = threading.Thread(target=action, daemon=True)
    thread.start()
    return thread


def banner(workdir: Path) -> str:
    return f"lime-star {__version__}  {workdir}\n"


def test_banner_then_prompt_then_exit_command(make_session: Any, tmp_path: Path) -> None:
    """R13.1-S1、R13.4-S1：先显示版本号和工作目录，随后出现输入提示；/exit 以 0 结束。"""
    lines = ScriptedLines()
    lines.feed("/exit")
    out, err = io.StringIO(), io.StringIO()
    code = chat(make_session(), lines, out, err, tmp_path)
    assert (code, out.getvalue(), err.getvalue()) == (0, banner(tmp_path) + PROMPT, "")


def test_blank_lines_are_ignored(make_session: Any, fake_model: FakeModel, tmp_path: Path) -> None:
    """R13.3-S1：空行不开始回合，继续等待输入。"""
    lines = ScriptedLines()
    for text in ("", "   \t", ""):
        lines.feed(text)
    lines.feed("/exit")
    out, err = io.StringIO(), io.StringIO()
    code = chat(make_session(), lines, out, err, tmp_path)
    assert code == 0
    assert out.getvalue() == banner(tmp_path) + PROMPT * (1 + BLANK_LINES)
    assert fake_model.requests() == []


def test_other_slash_input_is_sent_as_a_message(
    make_session: Any, fake_model: FakeModel, tmp_path: Path
) -> None:
    """决策 D-04：/exit 以外的斜杠输入当作普通消息。"""
    fake_model.reply("答")
    lines = ScriptedLines()
    lines.feed("/help")
    lines.feed("/exit")
    out, err = io.StringIO(), io.StringIO()
    code = chat(make_session(), lines, out, err, tmp_path)
    assert (code, err.getvalue()) == (0, "")
    assert out.getvalue() == banner(tmp_path) + PROMPT + "答\n" + PROMPT
    [request] = fake_model.requests()
    assert request.messages[1]["content"] == "/help"


def test_closed_input_ends_the_session_with_zero(
    make_session: Any, fake_model: FakeModel, tmp_path: Path
) -> None:
    """R13.13-S1：输入提示处读到输入结束，以 0 退出；之前的回合照常完成。"""
    fake_model.reply("答")
    lines = ScriptedLines()
    lines.feed("问")
    lines.end()
    out, err = io.StringIO(), io.StringIO()
    code = chat(make_session(), lines, out, err, tmp_path)
    assert (code, err.getvalue()) == (0, "")
    assert out.getvalue() == banner(tmp_path) + PROMPT + "答\n" + PROMPT


def test_model_error_goes_to_stderr_and_the_session_goes_on(
    make_session: Any, fake_model: FakeModel, tmp_path: Path
) -> None:
    """R13.5-S2：模型调用失败的说明写在标准错误；随后还能继续对话。"""
    fake_model.fail(401)
    fake_model.reply("第二答")
    lines = ScriptedLines()
    for text in ("第一问", "第二问", "/exit"):
        lines.feed(text)
    out, err = io.StringIO(), io.StringIO()
    code = chat(make_session(), lines, out, err, tmp_path)
    assert code == 0
    assert err.getvalue() == "回合出错：鉴权失败（HTTP 401）。\n"
    assert out.getvalue() == banner(tmp_path) + PROMPT * 2 + "第二答\n" + PROMPT
    assert FAKE_KEY not in out.getvalue() + err.getvalue()


def test_ignored_input_is_reported_after_the_turn(
    make_session: Any, fake_model: FakeModel, tmp_path: Path
) -> None:
    """R13.9-S1：回合进行中收到过输入时，回合结束后提示忽略了几行。"""
    fake_model.reply("答")
    lines = ScriptedLines()
    lines.feed("问")
    lines.dropped = 2
    lines.feed("/exit")
    out, err = io.StringIO(), io.StringIO()
    code = chat(make_session(), lines, out, err, tmp_path)
    assert (code, err.getvalue()) == (0, "已忽略 2 行回合中收到的输入。\n")
    assert out.getvalue() == banner(tmp_path) + PROMPT + "答\n" + PROMPT


def test_ctrl_c_at_the_prompt_ends_the_session_with_zero(
    make_session: Any, ctrl_c: Any, tmp_path: Path
) -> None:
    """R13.12-S1：在输入提示处按 Ctrl+C，会话以 0 结束。"""
    out, err = io.StringIO(), io.StringIO()
    ctrl_c(lambda: PROMPT in out.getvalue())
    code = chat(make_session(), ScriptedLines(), out, err, tmp_path)
    assert (code, out.getvalue(), err.getvalue()) == (0, banner(tmp_path) + PROMPT, "")


def test_ctrl_c_during_a_turn_cancels_it_and_returns_to_the_prompt(
    make_session: Any, fake_model: FakeModel, ctrl_c: Any, tmp_path: Path
) -> None:
    """R13.11-S1：回合进行中按 Ctrl+C，回合停止并显示已取消，随后回到输入提示。"""
    hold = Hold()
    fake_model.reply("迟到的回复", hold=hold)
    lines = ScriptedLines()
    lines.feed("第一问")
    out, err = io.StringIO(), io.StringIO()
    session: Session = make_session()

    def after_cancel() -> None:
        wait_until(lambda: out.getvalue().count(PROMPT) >= 2)
        hold.release()
        lines.feed("/exit")

    in_thread(after_cancel)
    ctrl_c(lambda: len(fake_model.requests()) >= 1)
    code = chat(session, lines, out, err, tmp_path)
    assert (code, err.getvalue()) == (0, "")
    assert out.getvalue() == banner(tmp_path) + PROMPT + "已取消。\n" + PROMPT
    assert session.read_thread().turns[0].outcome is Outcome.CANCELLED


def test_session_goes_on_after_a_cancelled_turn(
    make_session: Any, fake_model: FakeModel, ctrl_c: Any, tmp_path: Path
) -> None:
    """R12.6-S1（交互循环这一层）：取消后下一条消息开始新回合，并带上取消之前的历史。"""
    hold = Hold()
    fake_model.reply("迟到的回复", hold=hold)
    fake_model.reply("第二答")
    lines = ScriptedLines()
    lines.feed("第一问")
    out, err = io.StringIO(), io.StringIO()
    session: Session = make_session()

    def after_cancel() -> None:
        wait_until(lambda: out.getvalue().count(PROMPT) >= 2)
        hold.release()
        lines.feed("第二问")
        wait_until(lambda: "第二答\n" in out.getvalue())
        lines.feed("/exit")

    in_thread(after_cancel)
    ctrl_c(lambda: len(fake_model.requests()) >= 1)
    code = chat(session, lines, out, err, tmp_path)
    assert (code, err.getvalue()) == (0, "")
    assert out.getvalue() == banner(tmp_path) + PROMPT + "已取消。\n" + PROMPT + "第二答\n" + PROMPT
    [first, second] = fake_model.requests()
    assert first.messages[1]["content"] == "第一问"
    assert [message["content"] for message in second.messages[1:]] == ["第一问", "第二问"]


class BrokenStream:
    """readline 一调用就出错，模拟读不下去的标准输入。"""

    def readline(self) -> str:
        raise OSError("broken")


def test_unreadable_input_ends_the_session_with_exit_code_one(
    make_session: Any, tmp_path: Path
) -> None:
    lines = StdinLines(BrokenStream())
    lines.start()
    out, err = io.StringIO(), io.StringIO()
    code = chat(make_session(), lines, out, err, tmp_path)
    assert code == 1
    assert err.getvalue() == "标准输入无法读取，会话结束。\n"


def test_stdin_lines_reads_lines_until_input_ends() -> None:
    lines = StdinLines(io.StringIO("甲\n\n乙\n"))
    lines.start()
    assert [lines.next_line() for _ in range(3)] == ["甲\n", "\n", "乙\n"]
    assert lines.next_line() is None
    assert lines.next_line() is None


def test_stdin_lines_drops_arrived_lines_and_keeps_the_end_of_input() -> None:
    """R13.8 的丢弃逻辑：已经到达的行被丢掉并计数，输入结束的信号留到下一次取用。"""
    lines = StdinLines(io.StringIO("甲\n乙\n"))
    lines.start()

    def take() -> list[object]:
        return [lines.next_line()]

    dropped = 0
    while dropped < 2:
        dropped += lines.drain()
    assert dropped == 2
    taken: list[object] = []
    in_thread(lambda: taken.append(take()[0])).join(timeout=10)
    assert taken == [None]
    assert lines.drain() == 0


def test_stdin_lines_reports_a_broken_stream() -> None:
    lines = StdinLines(BrokenStream())
    lines.start()
    with pytest.raises(InputError):
        lines.next_line()
