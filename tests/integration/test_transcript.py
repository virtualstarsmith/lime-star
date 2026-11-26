"""会话记录的事实：只凭文件核对（需求 R3.4、R6.1 到 R6.7、R12.7）。

证据等级：Gate A 加入口集成。断言的对象是磁盘上那份 JSON Lines 文件；这里的用例自己解析它，
不经过产品的读回代码。read_thread 的结果要与文件一致，这也是根 AGENTS.md 里
"不得自己拼第二份会话真相"那条硬规则的守卫。模型是本地替身服务。
"""

import dataclasses
import io
import queue
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from lime_star import __version__
from lime_star.app import Outcome, Session
from lime_star.cli.chat import PROMPT, chat, project
from lime_star.protocol import (
    ENVELOPE,
    Entry,
    Json,
    ToolCall,
    ToolResult,
    TurnEnd,
    TurnStart,
)
from lime_star.thread_store import read
from lime_star.tool_runtime import Registry, Tool, ToolOutput
from tests.integration.fake_model import FakeModel, Hold
from tests.integration.support import (
    KINDS,
    CliProcess,
    entries_of,
    kill_tree,
    lines_of,
    read_log,
    transcript_file,
    wait_until,
)

FIXED = datetime(2026, 11, 25, 1, 2, 3, 400000, tzinfo=UTC)

READ = ("read_file", {"path": "notes.txt"})
NOTES = "甲\n乙\n"
TOOL_TURN = [
    "turn_start",
    "user_message",
    "tool_call",
    "tool_result",
    "model_text",
    "turn_end",
]


def put(base: Path, relative: str, text: str) -> None:
    path = base / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def types_on_disk(workdir: Path) -> list[str]:
    return [line["type"] for line in lines_of(transcript_file(workdir))]


class Lines:
    """按脚本给行的输入源，没有后台线程：事先放进去的行不会被当作回合中的输入。"""

    def __init__(self, *lines: str) -> None:
        self._queue: queue.Queue[str | None] = queue.Queue()
        for line in lines:
            self._queue.put(line)
        self._queue.put(None)

    def next_line(self) -> str | None:
        return self._queue.get()

    def drain(self) -> int:
        return 0


def shown(entries: list[Entry]) -> str:
    """把这些项逐个交给终端投影，得到它们在终端上的样子。"""
    out, err = io.StringIO(), io.StringIO()
    for entry in entries:
        project(entry, out, err)
    return out.getvalue()


def probe_tool(name: str, seen: list[list[str]], workdir: Path) -> Tool:
    """一个把工作目录里此刻的会话记录抄下来的工具。"""

    def run(_arguments: Mapping[str, Json]) -> ToolOutput:
        seen.append(types_on_disk(workdir))
        return ToolOutput(f"{name} 的结果")

    return Tool(name, "", {"type": "object"}, run)


def test_what_read_thread_returns_is_what_the_file_holds(
    make_session: Any, fake_model: FakeModel, tmp_path: Path
) -> None:
    """R6.7-S1，也是硬规则的守卫：read_thread 的结果与文件逐项一致，序号、时间、关联键都在。"""
    put(tmp_path, "notes.txt", NOTES)
    fake_model.call(READ)
    fake_model.reply("两行")
    fake_model.reply("第二答")
    session: Session = make_session(now=lambda: FIXED)
    first = session.start_turn("notes.txt 有几行")
    second = session.start_turn("再问一次")
    entries = session.read_thread()
    path = transcript_file(tmp_path)
    lines = lines_of(path)
    assert [line["type"] for line in lines] == [
        *TOOL_TURN,
        "turn_start",
        "user_message",
        "model_text",
        "turn_end",
    ]
    assert [line["seq"] for line in lines] == list(range(1, 11))
    assert {line["time"] for line in lines} == {"2026-11-25T01:02:03.400000+00:00"}
    assert {line["thread_id"] for line in lines} == {path.stem}
    starts = [line["turn_id"] for line in lines if line["type"] == "turn_start"]
    assert starts == [first.turn_id, second.turn_id]
    for line in lines:
        fields = [field.name for field in dataclasses.fields(KINDS[line["type"]])]
        assert sorted(line) == sorted([*ENVELOPE, "type", *fields]), line["type"]
    # 逐项比对：产品读回的结果，与用例自己从文件里拼出来的一样。
    assert entries == tuple(entries_of(path))


def test_one_session_leaves_one_file_and_the_terminal_follows_it(
    make_session: Any, fake_model: FakeModel, tmp_path: Path
) -> None:
    """R6.1-S1：磁盘上只有一份属于这个会话的记录，终端上的每一行都是它按顺序投影出来的。"""
    put(tmp_path, "notes.txt", NOTES)
    fake_model.call(READ, text="我先看看")
    fake_model.reply("两行")
    fake_model.reply("第二答")
    out, err = io.StringIO(), io.StringIO()
    lines = Lines("notes.txt 有几行", "再问一次", "/exit")
    code = chat(make_session(), lines, out, err, tmp_path)
    assert (code, err.getvalue()) == (0, "")
    files = sorted((tmp_path / ".lime-star" / "threads").iterdir())
    assert len(files) == 1
    entries = entries_of(files[0])
    first, second = list(dict.fromkeys(entry.turn_id for entry in entries))
    assert out.getvalue() == (
        f"lime-star {__version__}  {tmp_path}\n"
        + PROMPT
        + shown([entry for entry in entries if entry.turn_id == first])
        + PROMPT
        + shown([entry for entry in entries if entry.turn_id == second])
        + PROMPT
    )
    # 顺带把工具调用和结果摘要在终端上的样子固定下来（R13.14-S1、R13.15-S1）。
    assert (
        '我先看看\n调用 read_file {"path": "notes.txt"}\n结果：读到 2 行\n两行\n' in out.getvalue()
    )


def test_the_response_is_on_disk_before_its_tools_run(
    make_session: Any, fake_model: FakeModel, tmp_path: Path
) -> None:
    """R6.2-S1：一次响应里有一个工具调用，这个工具开始执行时，文件里已经有这次响应的项。"""
    seen: list[list[str]] = []
    tools = Registry([probe_tool("probe", seen, tmp_path)])
    fake_model.call(("probe", {}))
    fake_model.reply("好")
    result = make_session(tools=tools).start_turn("问")
    assert result.outcome is Outcome.DONE
    assert seen == [["turn_start", "user_message", "tool_call"]]


def test_results_are_written_before_the_next_request(
    make_session: Any, fake_model: FakeModel, tmp_path: Path
) -> None:
    """R6.3-S1、R6.3-S2：第一个调用执行完时，文件里有它的结果、没有第二个，也没有发起下一次请求；
    下一次请求到达时，文件里已经有全部结果。"""
    seen: list[list[str]] = []
    tools = Registry([probe_tool("first", seen, tmp_path), probe_tool("second", seen, tmp_path)])
    fake_model.call(("first", {}), ("second", {}))
    fake_model.reply("好")
    at_request: list[list[str]] = []
    fake_model.on_request = lambda _request: at_request.append(types_on_disk(tmp_path))
    result = make_session(tools=tools).start_turn("问")
    assert result.outcome is Outcome.DONE
    assert seen == [
        ["turn_start", "user_message", "tool_call", "tool_call"],
        ["turn_start", "user_message", "tool_call", "tool_call", "tool_result"],
    ]
    assert at_request == [
        ["turn_start", "user_message"],
        [
            "turn_start",
            "user_message",
            "tool_call",
            "tool_call",
            "tool_result",
            "tool_result",
        ],
    ]


def test_the_tool_arguments_and_results_recorded_are_what_the_model_receives(
    make_session: Any, fake_model: FakeModel, tmp_path: Path
) -> None:
    """R6.4-S1：记录里的工具参数和工具结果，与发给模型的内容逐字相同；被截断的读取结果也一样。"""
    put(tmp_path, "long.txt", "".join(f"行{number}\n" for number in range(1, 5001)))
    fake_model.call(("read_file", {"path": "long.txt"}), ("read_file", {"path": "nope.txt"}))
    fake_model.reply("好")
    make_session().start_turn("读两个文件")
    entries = entries_of(transcript_file(tmp_path))
    calls = [entry.item for entry in entries if isinstance(entry.item, ToolCall)]
    results = [entry.item for entry in entries if isinstance(entry.item, ToolResult)]
    second = fake_model.requests()[1]
    wire_calls = second.messages[2]["tool_calls"]
    assert [call["function"]["arguments"] for call in wire_calls] == [
        call.arguments for call in calls
    ]
    wire_results = [message for message in second.messages if message["role"] == "tool"]
    assert [message["content"] for message in wire_results] == [
        result.content for result in results
    ]
    assert len(results[0].content.split("\n")) == 2001  # 被截断的那一次读取
    assert results[1].content == "文件不存在：nope.txt。"


def test_a_killed_process_leaves_only_complete_lines(
    start_cli: Callable[..., CliProcess],
    model_env: dict[str, str],
    fake_model: FakeModel,
    tmp_path: Path,
) -> None:
    """R6.5-S1：记录了十项之后进程被强制结束，重新读这份记录得到完整的十项，没有残缺的半行。"""
    hold = Hold()
    fake_model.call(("first", {}), ("second", {}))
    fake_model.reply("第一答")
    fake_model.reply("迟到的回复", hold=hold)
    process = start_cli(model_env)
    process.wait_for("stdout", PROMPT)
    process.send("第一问")
    process.wait_for("stdout", PROMPT, count=2)
    process.send("第二问")
    wait_until(lambda: len(types_on_disk(tmp_path)) >= 10)
    kill_tree(process.process)
    process.close()
    hold.release()
    path = transcript_file(tmp_path)
    raw = path.read_bytes()
    assert (raw.count(b"\n"), raw.endswith(b"\n")) == (10, True)
    assert types_on_disk(tmp_path) == [
        "turn_start",
        "user_message",
        "tool_call",
        "tool_call",
        "tool_result",
        "tool_result",
        "model_text",
        "turn_end",
        "turn_start",
        "user_message",
    ]
    assert len(read(path)) == 10
    # 第二个回合有开始、没有结局。只凭文件读回时它原样读出；恢复会话的一方把它判为中断，
    # 见 test_resume.py 和 test_cli_resume.py。


def test_every_request_log_record_points_at_exactly_one_turn(
    make_session: Any, fake_model: FakeModel, log_path: Path, tmp_path: Path
) -> None:
    """R3.4-S1：凭请求日志里的 thread_id 和 turn_id 去查会话记录，恰好找到对应的那一个回合。"""
    put(tmp_path, "notes.txt", NOTES)
    fake_model.call(READ)
    fake_model.reply("两行")
    fake_model.reply("第二答")
    session: Session = make_session()
    session.start_turn("notes.txt 有几行")
    session.start_turn("再问一次")
    path = transcript_file(tmp_path)
    records = read_log(log_path)
    assert len(records) == 3
    for record in records:
        assert record["thread_id"] == path.stem
        turn = [entry for entry in entries_of(path) if entry.turn_id == record["turn_id"]]
        edges = [entry.item for entry in turn if isinstance(entry.item, TurnStart | TurnEnd)]
        assert [edge.kind for edge in edges] == ["turn_start", "turn_end"]
    assert [record["turn_id"] for record in records].count(records[0]["turn_id"]) == 2


def test_a_cancelled_turn_records_its_end_on_the_spot(
    make_session: Any, fake_model: FakeModel, ctrl_c: Any, tmp_path: Path
) -> None:
    """R12.7-S1、R9.3-S1、R6.6-S1：带工具调用又被 Ctrl+C 打断的回合，当场写下结局。

    读记录时，用户消息、工具调用、工具结果、回合开始、回合结局都能按类型辨认出来。
    批准项没有生产它的流程（审批属于 P4），它的往返由 tests/unit/test_transcript.py 验证。
    """
    hold = Hold()
    fake_model.call(READ)
    fake_model.reply("迟到的回复", hold=hold)
    ctrl_c(lambda: len(fake_model.requests()) >= 2)
    session: Session = make_session()
    result = session.start_turn("notes.txt 有几行")
    hold.release()
    assert result.outcome is Outcome.CANCELLED
    assert types_on_disk(tmp_path) == [*TOOL_TURN[:4], "turn_end"]
    entries = entries_of(transcript_file(tmp_path))
    assert entries[-1].item == TurnEnd(Outcome.CANCELLED, "用户按 Ctrl+C 取消")
    assert entries[-1].turn_id == entries[0].turn_id == result.turn_id


def test_each_ending_is_written_with_its_reason(
    make_session: Any, fake_model: FakeModel, tmp_path: Path
) -> None:
    """R12.7：完成、出错、步数上限三种结局的结局项各是什么样；取消见上一条用例。"""
    fake_model.reply("第一答")
    fake_model.fail(401)
    for _ in range(20):
        fake_model.call(("no_such_tool", {}))
    session: Session = make_session()
    session.start_turn("问一")
    session.start_turn("问二")
    session.start_turn("问三")
    entries = entries_of(transcript_file(tmp_path))
    assert [entry.item for entry in entries if isinstance(entry.item, TurnEnd)] == [
        TurnEnd(Outcome.DONE, ""),
        TurnEnd(Outcome.ERROR, "鉴权失败（HTTP 401）"),
        TurnEnd(Outcome.STEP_LIMIT, "已达到步数上限（一个回合最多 20 次模型请求）"),
    ]
    # 没有执行的最后一次调用也有一条结果，所以每个回合里调用和结果一样多。
    kinds_counted = [entry.item.kind for entry in entries]
    assert kinds_counted.count("tool_call") == kinds_counted.count("tool_result") == 20
