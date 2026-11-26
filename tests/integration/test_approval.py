"""危险操作的批准经 app 回合入口：respond_action、批准项落盘、拒绝后回合继续、逐个批准。

覆盖 R7.6 到 R7.13、R8.2-S2。证据等级：入口集成。模型是本地替身服务，响应是手写的；工具是真的，
写文件和执行命令都在临时工作目录里发生。决定由测试经 Session.respond_action 交回；终端怎样提问在
test_cli_chat.py、test_cli_process.py、test_cli_console.py。
"""

import json
import threading
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from lime_star.app import Outcome, Session, SessionError
from lime_star.protocol import (
    Approval,
    Decision,
    Item,
    ModelText,
    Pending,
    ToolCall,
    ToolResult,
    TurnEnd,
    TurnStart,
    UserMessage,
)
from lime_star.thread_store import read
from lime_star.tool_runtime import REJECTED
from tests.integration.fake_model import FakeModel
from tests.integration.support import transcript_file, written

CANCELLED_BY_USER = "用户按 Ctrl+C 取消"
NOT_RUN_CANCELLED = "没有执行：用户取消了这个回合。"
WRITTEN = "已写入 hello.py（新建文件，1 行）。"
WRITTEN_SUMMARY = "已写入 hello.py，新建文件，1 行"
REPLY = "这是最终回复。"


class Asker:
    """提问回调的替身：记下每次等待批准的操作，按脚本交回决定；脚本用完之后一律拒绝。"""

    def __init__(self, session: Session, *decisions: Decision) -> None:
        self.session = session
        self.decisions = list(decisions)
        self.pending: list[Pending] = []

    def __call__(self, pending: Pending) -> None:
        self.pending.append(pending)
        decision = self.decisions.pop(0) if self.decisions else "rejected"
        self.session.respond_action(pending.call_id, decision)


def ask_to_write(fake_model: FakeModel, path: str = "hello.py") -> ToolCall:
    """让替身模型请求写一个文件，再给一句最终回复。返回模型会发出的那次调用。"""
    arguments = json.dumps({"path": path, "content": "print('hello')\n"})
    fake_model.call(("write_file", arguments))
    fake_model.reply(REPLY)
    return ToolCall(call_id="call1", name="write_file", arguments=arguments)


def approved(call: ToolCall) -> Approval:
    return Approval(call.call_id, call.name, call.arguments, "approved")


def rejected(call: ToolCall) -> Approval:
    return Approval(call.call_id, call.name, call.arguments, "rejected")


def items(session: Session) -> list[Item]:
    """会话记录里的项，不带信封，按写入顺序。"""
    return list(written(session.read_thread()))


def test_a_write_waits_for_approval_then_runs(
    make_session: Any, fake_model: FakeModel, tmp_path: Path
) -> None:
    """R7.6-S1、R7.7-S1、R7.12：批准提示出现时文件还没有写；批准之后执行；
    调用、批准、结果依次落盘，批准项带着时间、会话和回合。"""
    call = ask_to_write(fake_model)
    session: Session = make_session()
    target = tmp_path / "hello.py"
    notes: list[str] = []

    def ask(pending: Pending) -> None:
        notes.append(pending.note)
        assert not target.exists()  # 用户还没有回应：没有写
        session.respond_action(pending.call_id, "approved")

    result = session.start_turn("新建 hello.py", ask=ask)
    assert (result.outcome, result.reply) == (Outcome.DONE, REPLY)
    assert target.read_bytes() == b"print('hello')\n"
    assert items(session) == [
        TurnStart(),
        UserMessage("新建 hello.py"),
        call,
        approved(call),
        ToolResult("call1", WRITTEN, summary=WRITTEN_SUMMARY),
        ModelText(REPLY),
        TurnEnd(Outcome.DONE, ""),
    ]
    entries = session.read_thread()
    assert isinstance(entries[3].time, datetime)
    assert entries[3].turn_id == entries[0].turn_id == result.turn_id
    assert entries[3].thread_id == entries[0].thread_id
    [note] = notes
    assert note == (
        "请求批准 write_file：写入 hello.py（新建文件）。要写入的内容：\n"
        "print('hello')\n"
        "----- 内容结束，共 1 行 -----"
    )
    # 文件里也是这个顺序（Gate A：只凭会话记录的文件读回）。
    assert read(transcript_file(tmp_path)) == entries


def test_a_rejection_is_recorded_and_the_turn_goes_on(
    make_session: Any, fake_model: FakeModel, tmp_path: Path
) -> None:
    """R7.10-S1、R7.12-S1、R7.13-S1：用户拒绝写文件，文件没有被改动，记录里有写明拒绝的批准项，
    模型收到"用户拒绝了这次操作"的结果，回合没有结束。"""
    call = ask_to_write(fake_model)
    session: Session = make_session()
    result = session.start_turn("新建 hello.py", ask=Asker(session, "rejected"))
    assert (result.outcome, result.reply) == (Outcome.DONE, REPLY)
    assert not (tmp_path / "hello.py").exists()
    assert items(session) == [
        TurnStart(),
        UserMessage("新建 hello.py"),
        call,
        rejected(call),
        ToolResult("call1", REJECTED, True, REJECTED),
        ModelText(REPLY),
        TurnEnd(Outcome.DONE, ""),
    ]
    second = fake_model.requests()[1]
    assert second.messages[3] == {"role": "tool", "tool_call_id": "call1", "content": REJECTED}


def test_a_rejected_command_never_runs(
    make_session: Any, fake_model: FakeModel, tmp_path: Path
) -> None:
    """R7.10-S2、R7.12-S1：用户拒绝执行命令，这条命令没有运行过；批准项里写着命令原文和拒绝。"""
    command = "python -c \"from pathlib import Path; Path('ran.txt').write_text('x')\""
    fake_model.call(("run_command", {"command": command}))
    fake_model.reply("没有运行。")
    session: Session = make_session()
    session.start_turn("运行它", ask=Asker(session, "rejected"))
    assert not (tmp_path / "ran.txt").exists()
    call = ToolCall("call1", "run_command", json.dumps({"command": command}))
    assert items(session) == [
        TurnStart(),
        UserMessage("运行它"),
        call,
        rejected(call),
        ToolResult("call1", REJECTED, True, REJECTED),
        ModelText("没有运行。"),
        TurnEnd(Outcome.DONE, ""),
    ]


def test_the_command_prompt_shows_the_command_verbatim(
    make_session: Any, fake_model: FakeModel, tmp_path: Path
) -> None:
    """R7.8-S1：批准提示里的命令与请求的逐字相同，包括引号、空格和多行。"""
    command = "python -c \"print('你好')\"\nWrite-Output '第二行'"
    fake_model.call(("run_command", {"command": command}))
    fake_model.reply("跑完了")
    session: Session = make_session()
    ask = Asker(session, "approved")
    result = session.start_turn("运行它", ask=ask)
    assert result.outcome is Outcome.DONE
    [pending] = ask.pending
    assert pending.note == f"请求批准 run_command：在工作目录里执行下面的命令：\n{command}"


def test_an_overwrite_is_announced(
    make_session: Any, fake_model: FakeModel, tmp_path: Path
) -> None:
    """R7.7-S2：目标文件已存在时，批准提示标明会覆盖已有文件。"""
    (tmp_path / "hello.py").write_bytes(b"OLD\n")
    ask_to_write(fake_model)
    session: Session = make_session()
    ask = Asker(session, "approved")
    session.start_turn("改一下", ask=ask)
    [pending] = ask.pending
    assert pending.note.startswith("请求批准 write_file：写入 hello.py（覆盖已有文件）。")
    assert (tmp_path / "hello.py").read_bytes() == b"print('hello')\n"


def test_read_only_tools_never_ask(
    make_session: Any, fake_model: FakeModel, tmp_path: Path
) -> None:
    """R7.6-S2：read_file 和 list_dir 执行时不出现批准提示。"""
    (tmp_path / "notes.txt").write_text("甲\n", encoding="utf-8")
    fake_model.call(("list_dir", {}), ("read_file", {"path": "notes.txt"}))
    fake_model.reply("看过了")
    asked: list[Pending] = []
    session: Session = make_session()
    result = session.start_turn("看看", ask=asked.append)
    assert (result.outcome, asked) == (Outcome.DONE, [])


def test_two_dangerous_calls_are_approved_one_after_the_other(
    make_session: Any, fake_model: FakeModel, tmp_path: Path
) -> None:
    """R7.11-S1：模型一次请求写两个文件，出现两次批准提示，各自独立决定；前一个被拒绝，后一个仍然执行。"""
    first = ToolCall("call1", "write_file", '{"path": "a.txt", "content": "A"}')
    second = ToolCall("call2", "write_file", '{"path": "b.txt", "content": "B"}')
    fake_model.call(
        ("write_file", {"path": "a.txt", "content": "A"}),
        ("write_file", {"path": "b.txt", "content": "B"}),
    )
    fake_model.reply("做完了")
    session: Session = make_session()
    ask = Asker(session, "rejected", "approved")
    result = session.start_turn("写两个文件", ask=ask)
    assert result.outcome is Outcome.DONE
    assert [(p.call_id, p.name, p.arguments) for p in ask.pending] == [
        ("call1", "write_file", first.arguments),
        ("call2", "write_file", second.arguments),
    ]
    assert not (tmp_path / "a.txt").exists()
    assert (tmp_path / "b.txt").read_bytes() == b"B"
    assert items(session) == [
        TurnStart(),
        UserMessage("写两个文件"),
        first,
        second,
        rejected(first),
        ToolResult("call1", REJECTED, True, REJECTED),
        approved(second),
        ToolResult(
            "call2", "已写入 b.txt（新建文件，1 行）。", summary="已写入 b.txt，新建文件，1 行"
        ),
        ModelText("做完了"),
        TurnEnd(Outcome.DONE, ""),
    ]


def test_an_out_of_bounds_write_never_reaches_the_prompt(
    make_session: Any, fake_model: FakeModel, tmp_path: Path
) -> None:
    """R8.2-S2：模型请求写工作目录之外的路径，没有出现批准提示，越界结果交给模型，磁盘没有变化。"""
    fake_model.call(("write_file", {"path": "../outside.txt", "content": "x"}))
    fake_model.reply("写不了")
    asked: list[Pending] = []
    session: Session = make_session()
    result = session.start_turn("写到外面", ask=asked.append)
    assert (result.outcome, asked) == (Outcome.DONE, [])
    assert not (tmp_path.parent / "outside.txt").exists()
    second = fake_model.requests()[1]
    assert second.messages[3]["content"] == "超出工作目录：../outside.txt。"
    assert "approval" not in [entry.item.kind for entry in session.read_thread()]


def test_without_a_way_to_ask_every_dangerous_call_is_refused(
    make_session: Any, fake_model: FakeModel, tmp_path: Path
) -> None:
    """R7.6：没有人可问时拿不到批准，危险操作不执行；拒绝照样记进会话记录，回合继续。"""
    call = ask_to_write(fake_model)
    session: Session = make_session()
    result = session.start_turn("新建 hello.py")
    assert (result.outcome, result.reply) == (Outcome.DONE, REPLY)
    assert not (tmp_path / "hello.py").exists()
    assert items(session)[2:5] == [
        call,
        rejected(call),
        ToolResult("call1", REJECTED, True, REJECTED),
    ]


def test_responding_to_something_that_is_not_waiting_is_refused(
    make_session: Any, fake_model: FakeModel, tmp_path: Path
) -> None:
    """respond_action 只认正在等待的那次调用：回合之外、或者调用编号对不上，都不放行。"""
    call = ask_to_write(fake_model)
    session: Session = make_session()
    with pytest.raises(SessionError):
        session.respond_action("call1", "approved")  # 回合之外
    result = session.start_turn(
        "新建 hello.py", ask=lambda _pending: session.respond_action("nope", "approved")
    )
    assert (result.outcome, result.reply) == (Outcome.DONE, REPLY)
    assert not (tmp_path / "hello.py").exists()
    assert items(session) == [
        TurnStart(),
        UserMessage("新建 hello.py"),
        call,
        ToolResult(
            "call1", "工具运行出错（SessionError）。", True, "工具运行出错（SessionError）。"
        ),
        ModelText(REPLY),
        TurnEnd(Outcome.DONE, ""),
    ]


def test_a_decision_that_arrives_later_still_releases_the_tool(
    make_session: Any, fake_model: FakeModel, tmp_path: Path
) -> None:
    """提问回调可以先返回，等用户决定了再交回：回合停在这次调用上，拿到决定才执行。"""
    ask_to_write(fake_model)
    session: Session = make_session()
    waiting = threading.Event()

    def answer_later(pending: Pending) -> None:
        waiting.set()

        def later() -> None:
            time.sleep(0.2)
            session.respond_action(pending.call_id, "approved")

        threading.Thread(target=later, daemon=True).start()

    result = session.start_turn("新建 hello.py", ask=answer_later)
    assert (waiting.is_set(), result.outcome) == (True, Outcome.DONE)
    assert (tmp_path / "hello.py").read_bytes() == b"print('hello')\n"


def test_ctrl_c_while_waiting_for_approval_cancels_without_executing(
    make_session: Any,
    fake_model: FakeModel,
    tmp_path: Path,
    ctrl_c: Callable[[Callable[[], bool]], None],
) -> None:
    """R12.5、R7.6-S1：等待批准时按 Ctrl+C，回合以取消结束，操作没有执行，记录里没有批准项。"""
    call = ask_to_write(fake_model)
    session: Session = make_session()
    waiting = threading.Event()
    ctrl_c(waiting.is_set)
    result = session.start_turn("新建 hello.py", ask=lambda _pending: waiting.set())
    assert (result.outcome, result.reason, result.reply) == (
        Outcome.CANCELLED,
        CANCELLED_BY_USER,
        "",
    )
    assert not (tmp_path / "hello.py").exists()
    assert items(session) == [
        TurnStart(),
        UserMessage("新建 hello.py"),
        call,
        ToolResult("call1", NOT_RUN_CANCELLED, True, NOT_RUN_CANCELLED),
        TurnEnd(Outcome.CANCELLED, CANCELLED_BY_USER),
    ]


def test_the_session_goes_on_after_a_rejected_turn(
    make_session: Any, fake_model: FakeModel, tmp_path: Path
) -> None:
    """拒绝之后的下一条消息开始新回合，带上之前的历史；下一次照样可以批准执行。"""
    ask_to_write(fake_model, "a.txt")
    ask_to_write(fake_model, "b.txt")
    session: Session = make_session()
    session.start_turn("写 a", ask=Asker(session, "rejected"))
    session.start_turn("写 b", ask=Asker(session, "approved"))
    assert not (tmp_path / "a.txt").exists()
    assert (tmp_path / "b.txt").read_bytes() == b"print('hello')\n"
    third = fake_model.requests()[2]  # 第二个回合的第一次请求
    assert [(message["role"], message["content"]) for message in third.messages[1:]] == [
        ("user", "写 a"),
        ("assistant", None),
        ("tool", REJECTED),
        ("assistant", REPLY),
        ("user", "写 b"),
    ]
