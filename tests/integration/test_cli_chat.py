"""进程内运行会话的终端交互循环：横幅与提示、空行、退出、输入结束、Ctrl+C。

证据等级：入口集成（CLI 的交互循环这一层，不经过真实进程）。真实进程的用例在
test_cli_process.py。Ctrl+C 用 _thread.interrupt_main() 模拟：它和真实 Ctrl+C 一样
在主线程里挂起一个中断，但不经过控制台。模型是测试替身。
覆盖 R13.1-S1、R13.3-S1、R13.4-S1、R13.9-S1、R13.11-S1、R13.12-S1、R13.13-S1；
路线图 P3 加入 R13.14-S1、R13.14-S2、R13.15-S1（工具调用和结果摘要的显示）。
"""

import io
import json
import queue
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from lime_star import __version__
from lime_star.app import Outcome, Session
from lime_star.cli.chat import ASK, PROMPT, InputError, StdinLines, chat
from tests.integration.fake_model import FAKE_KEY, FakeModel, Hold
from tests.integration.support import endings, wait_until

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


class QueuedLines(ScriptedLines):
    """照产品的做法丢弃已经排队的行并计数的输入源：别的用例预先把 /exit 排进队列，靠的是不丢。"""

    def drain(self) -> int:
        dropped = 0
        ended = False
        while True:
            try:
                item = self._queue.get_nowait()
            except queue.Empty:
                break
            if item is None:
                ended = True
            else:
                dropped += 1
        if ended:
            self._queue.put(None)
        return dropped


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
    assert endings(session.read_thread())[0].outcome is Outcome.CANCELLED


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


class BreakingStream:
    """给出第一行之后就读不下去的输入流。"""

    def __init__(self, first: str) -> None:
        self._first: str | None = first

    def readline(self) -> str:
        if self._first is None:
            raise OSError("broken")
        line, self._first = self._first, None
        return line


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


def test_a_tool_call_and_its_result_are_shown_as_they_are_recorded(
    make_session: Any, fake_model: FakeModel, tmp_path: Path
) -> None:
    """R13.14-S1、R13.14-S2、R13.15-S1：模型文本产出后显示；工具调用显示名称和目标；结果显示一行摘要。"""
    (tmp_path / "notes.txt").write_text("甲\n乙\n", encoding="utf-8")
    fake_model.call(("read_file", {"path": "notes.txt"}), text="我先看看")
    fake_model.reply("有两行")
    lines = ScriptedLines()
    lines.feed("notes.txt 有几行")
    lines.feed("/exit")
    out, err = io.StringIO(), io.StringIO()
    code = chat(make_session(), lines, out, err, tmp_path)
    assert (code, err.getvalue()) == (0, "")
    assert out.getvalue() == (
        banner(tmp_path)
        + PROMPT
        + "我先看看\n"
        + '调用 read_file {"path": "notes.txt"}\n'
        + "结果：读到 2 行\n"
        + "有两行\n"
        + PROMPT
    )


def test_a_failed_tool_result_is_shown_with_its_error(
    make_session: Any, fake_model: FakeModel, tmp_path: Path
) -> None:
    """R13.15-S1 的另一半：工具出错时，终端上有一行说明出了什么错。"""
    fake_model.call(("read_file", {"path": "nope.txt"}))
    fake_model.reply("没有这个文件")
    lines = ScriptedLines()
    lines.feed("读一下 nope.txt")
    lines.feed("/exit")
    out, err = io.StringIO(), io.StringIO()
    code = chat(make_session(), lines, out, err, tmp_path)
    assert (code, err.getvalue()) == (0, "")
    assert out.getvalue() == (
        banner(tmp_path)
        + PROMPT
        + '调用 read_file {"path": "nope.txt"}\n'
        + "结果出错：文件不存在：nope.txt。\n"
        + "没有这个文件\n"
        + PROMPT
    )


WRITE_PROMPT = (
    "请求批准 write_file：写入 hello.py（新建文件）。要写入的内容：\n"
    "print('hello')\n"
    "----- 内容结束，共 1 行 -----\n"
)
REJECTION = "结果出错：用户拒绝了这次操作，没有执行。\n"


def ask_to_write(fake_model: FakeModel) -> str:
    """让替身模型请求写 hello.py，再给一句最终回复。返回模型给出的参数原文。"""
    arguments = json.dumps({"path": "hello.py", "content": "print('hello')\n"})
    fake_model.call(("write_file", arguments))
    fake_model.reply("写好了")
    return arguments


def answer_when_asked(
    lines: ScriptedLines, out: io.StringIO, answer: str | None, then: str = "/exit"
) -> None:
    """提示出现之后才给输入：等到 [y/n] 再送一行（None 表示输入结束），回合结束后再送 then。"""

    def act() -> None:
        wait_until(lambda: ASK in out.getvalue())
        if answer is None:
            lines.end()
        else:
            lines.feed(answer)
        wait_until(lambda: out.getvalue().count(PROMPT) >= 2)
        lines.feed(then)

    in_thread(act)


def test_y_at_the_approval_prompt_lets_the_write_run(
    make_session: Any, fake_model: FakeModel, tmp_path: Path
) -> None:
    """R7.6、R7.7-S1、R7.9-S1：写文件的批准提示显示路径、新建和完整内容；输入 y 之后执行。"""
    arguments = ask_to_write(fake_model)
    lines = ScriptedLines()
    lines.feed("新建 hello.py")
    out, err = io.StringIO(), io.StringIO()
    answer_when_asked(lines, out, "y")
    session: Session = make_session()
    code = chat(session, lines, out, err, tmp_path)
    assert (code, err.getvalue()) == (0, "")
    assert out.getvalue() == (
        banner(tmp_path)
        + PROMPT
        + f"调用 write_file {arguments}\n"
        + WRITE_PROMPT
        + "[y/n] 已批准。\n结果：已写入 hello.py，新建文件，1 行\n写好了\n"
        + PROMPT
    )
    assert (tmp_path / "hello.py").read_bytes() == b"print('hello')\n"
    assert [entry.item.kind for entry in session.read_thread()] == [
        "turn_start",
        "user_message",
        "tool_call",
        "approval",
        "tool_result",
        "model_text",
        "turn_end",
    ]


def test_input_typed_before_the_prompt_is_not_an_answer(
    make_session: Any, fake_model: FakeModel, tmp_path: Path
) -> None:
    """R13.8、决策 D-20：提示出现之前到达的输入不算对它的回应，按回合中的输入丢弃并计数；
    想批准，必须在看到提示之后输入。"""
    ask_to_write(fake_model)
    lines = QueuedLines()
    lines.feed("新建 hello.py")
    lines.feed("y")  # 提示还没出现就到了：不算批准
    out, err = io.StringIO(), io.StringIO()
    answer_when_asked(lines, out, "y")
    session: Session = make_session()
    code = chat(session, lines, out, err, tmp_path)
    assert (code, err.getvalue()) == (0, "已忽略 1 行回合中收到的输入。\n")
    assert out.getvalue().count(WRITE_PROMPT + "[y/n] 已批准。\n") == 1
    assert (tmp_path / "hello.py").read_bytes() == b"print('hello')\n"
    assert [entry.item.kind for entry in session.read_thread()].count("user_message") == 1


@pytest.mark.parametrize("answer", ["", "n", "yes", "Y", "批准"])
def test_anything_but_y_at_the_prompt_rejects(
    make_session: Any, fake_model: FakeModel, tmp_path: Path, answer: str
) -> None:
    """R7.9、R7.9-S2、R7.10-S1：只有 y 算批准；空输入、n、别的文字都算拒绝，文件没有被写入。"""
    arguments = ask_to_write(fake_model)
    lines = ScriptedLines()
    lines.feed("新建 hello.py")
    out, err = io.StringIO(), io.StringIO()
    answer_when_asked(lines, out, answer)
    code = chat(make_session(), lines, out, err, tmp_path)
    assert (code, err.getvalue()) == (0, "")
    assert out.getvalue() == (
        banner(tmp_path)
        + PROMPT
        + f"调用 write_file {arguments}\n"
        + WRITE_PROMPT
        + "[y/n] 已拒绝。\n"
        + REJECTION
        + "写好了\n"
        + PROMPT
    )
    assert not (tmp_path / "hello.py").exists()


@pytest.mark.parametrize("answer", ["y", "y\r", "  y  "])
def test_y_with_surrounding_space_or_a_carriage_return_is_still_y(
    make_session: Any, fake_model: FakeModel, tmp_path: Path, answer: str
) -> None:
    """去掉首尾空白之后恰好是 y 就算批准：Windows 控制台的行尾带着回车。"""
    ask_to_write(fake_model)
    lines = ScriptedLines()
    lines.feed("新建 hello.py")
    out, err = io.StringIO(), io.StringIO()
    answer_when_asked(lines, out, answer)
    code = chat(make_session(), lines, out, err, tmp_path)
    assert (code, err.getvalue()) == (0, "")
    assert "[y/n] 已批准。\n" in out.getvalue()
    assert (tmp_path / "hello.py").read_bytes() == b"print('hello')\n"


def test_input_end_at_the_approval_prompt_rejects(
    make_session: Any, fake_model: FakeModel, tmp_path: Path
) -> None:
    """R7.9、R13.13 的边界：批准提示处的输入结束按拒绝处理；
    随后回到输入提示，输入结束，以 0 退出。"""
    arguments = ask_to_write(fake_model)
    lines = ScriptedLines()
    lines.feed("新建 hello.py")
    out, err = io.StringIO(), io.StringIO()
    answer_when_asked(lines, out, None)
    code = chat(make_session(), lines, out, err, tmp_path)
    assert (code, err.getvalue()) == (0, "")
    assert out.getvalue() == (
        banner(tmp_path)
        + PROMPT
        + f"调用 write_file {arguments}\n"
        + WRITE_PROMPT
        + "[y/n] 已拒绝。\n"
        + REJECTION
        + "写好了\n"
        + PROMPT
    )
    assert not (tmp_path / "hello.py").exists()


def test_unreadable_input_at_the_approval_prompt_rejects(
    make_session: Any, fake_model: FakeModel, tmp_path: Path
) -> None:
    """R7.9：批准提示处读不到输入，就没有批准；随后输入提示处读不下去，以 1 结束。"""
    arguments = ask_to_write(fake_model)
    lines = StdinLines(BreakingStream("新建 hello.py\n"))
    lines.start()
    out, err = io.StringIO(), io.StringIO()
    code = chat(make_session(), lines, out, err, tmp_path)
    assert (code, err.getvalue()) == (1, "标准输入无法读取，会话结束。\n")
    assert out.getvalue() == (
        banner(tmp_path)
        + PROMPT
        + f"调用 write_file {arguments}\n"
        + WRITE_PROMPT
        + "[y/n] 已拒绝。\n"
        + REJECTION
        + "写好了\n"
        + PROMPT
    )
    assert not (tmp_path / "hello.py").exists()
