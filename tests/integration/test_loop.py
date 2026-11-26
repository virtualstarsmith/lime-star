"""回合循环经 app 回合入口的接线：模型调用工具、结果回填、再请求，以及循环的结局。

证据等级：入口集成。模型是本地替身服务，响应是手写的，没有从真实运行录制。
循环自身的状态转移由 tests/unit/test_loop.py 不联网地守着，会话记录文件本身由
tests/integration/test_transcript.py 守着，这里守的是接线。
"""

import threading
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from lime_star.agent_runtime.loop import (
    NOT_RUN_AT_LIMIT,
    NOT_RUN_CANCELLED,
    STEP_LIMIT_REACHED,
)
from lime_star.app import Outcome, Session
from lime_star.protocol import (
    Json,
    ModelText,
    ToolCall,
    ToolResult,
    TurnEnd,
    TurnStart,
    UserMessage,
)
from lime_star.tool_runtime import Registry, Tool, ToolOutput
from tests.integration.fake_model import FakeModel, calling, completion
from tests.integration.support import endings, kinds, read_log, wait_for_log, written

READ_A = ("read_file", {"path": "a.txt"})
CALL_A = ToolCall(call_id="call1", name="read_file", arguments='{"path": "a.txt"}')
CONTENT_A = "     1  甲"
RESULT_A = ToolResult(call_id="call1", content=CONTENT_A, summary="读到 1 行")
DONE = TurnEnd(Outcome.DONE, "")
LIMIT = TurnEnd(Outcome.STEP_LIMIT, STEP_LIMIT_REACHED)
CANCELLED = TurnEnd(Outcome.CANCELLED, "用户按 Ctrl+C 取消")


def put(base: Path, relative: str, text: str) -> None:
    """在工作目录里放一个文本文件。"""
    path = base / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def roles(request: Any) -> list[str]:
    return [message["role"] for message in request.messages]


def test_a_tool_call_is_run_and_its_result_goes_back_to_the_model(
    make_session: Any, fake_model: FakeModel, tmp_path: Path
) -> None:
    """R12.1-S1：模型请求工具、程序执行、结果回填、再请求、结束。正式命令默认就带着 read_file。"""
    put(tmp_path, "a.txt", "甲\n")
    fake_model.call(READ_A)
    fake_model.reply("文件读了")
    session: Session = make_session()
    result = session.start_turn("读一下 a.txt")
    assert (result.outcome, result.reply) == (Outcome.DONE, "文件读了")
    first, second = fake_model.requests()
    assert roles(first) == ["system", "user"]
    assert second.messages[1:3] == [
        {"role": "user", "content": "读一下 a.txt"},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call1",
                    "type": "function",
                    "function": {"name": "read_file", "arguments": '{"path": "a.txt"}'},
                }
            ],
        },
    ]
    assert second.messages[3] == {"role": "tool", "tool_call_id": "call1", "content": CONTENT_A}
    assert written(session.read_thread()) == (
        TurnStart(),
        UserMessage(content="读一下 a.txt"),
        CALL_A,
        RESULT_A,
        ModelText(content="文件读了"),
        DONE,
    )


def test_the_product_session_offers_the_four_tools(
    make_session: Any, fake_model: FakeModel, tmp_path: Path
) -> None:
    """正式命令的工具集是四个工具，read_file 在第一位；一个回合的每次请求都带同一份工具定义。"""
    put(tmp_path, "a.txt", "甲\n")
    fake_model.call(READ_A)
    fake_model.reply("好")
    make_session().start_turn("读一下 a.txt")
    first, second = fake_model.requests()
    assert first.tools == second.tools
    functions = [tool["function"] for tool in first.tools]
    assert [function["name"] for function in functions] == [
        "read_file",
        "list_dir",
        "write_file",
        "run_command",
    ]
    assert functions[0] == {
        "name": "read_file",
        "description": "读取工作目录里的一个 UTF-8 文本文件，返回带行号的文件内容。"
        "一次最多返回 2000 行，更长的文件会说明还有多少行没有读。",
        "parameters": {
            "type": "object",
            "properties": {"path": {"type": "string", "description": "相对工作目录的文件路径。"}},
            "required": ["path"],
        },
    }
    assert [function["parameters"].get("required", []) for function in functions] == [
        ["path"],
        [],
        ["path", "content"],
        ["command"],
    ]
    assert all("危险操作" in function["description"] for function in functions[2:])


def test_a_session_with_an_empty_registry_sends_no_tool_definitions(
    make_session: Any, fake_model: FakeModel
) -> None:
    """注册表是空的时候，请求里没有 tools 字段。"""
    fake_model.reply("答")
    result = make_session(tools=Registry()).start_turn("问")
    assert result.outcome is Outcome.DONE
    [request] = fake_model.requests()
    assert request.keys == ["messages", "model"]
    assert request.tools is None
    assert roles(request) == ["system", "user"]


def test_every_tool_result_is_back_before_the_next_request(
    make_session: Any, fake_model: FakeModel, tmp_path: Path
) -> None:
    """R12.1-S2：一次响应请求三次调用，三个结果都回填之后才发起下一次请求，顺序不变。"""
    for name in ("a.txt", "b.txt", "c.txt"):
        put(tmp_path, name, f"{name} 的内容\n")
    fake_model.call(READ_A, ("read_file", {"path": "b.txt"}), ("read_file", {"path": "c.txt"}))
    fake_model.reply("都读了")
    session: Session = make_session()
    result = session.start_turn("读三个文件")
    assert (result.outcome, result.reply) == (Outcome.DONE, "都读了")
    assert len(fake_model.requests()) == 2
    second = fake_model.requests()[1]
    assert roles(second) == ["system", "user", "assistant", "tool", "tool", "tool"]
    assert [call["id"] for call in second.messages[2]["tool_calls"]] == [
        "call1",
        "call2",
        "call3",
    ]
    assert [message["tool_call_id"] for message in second.messages[3:]] == [
        "call1",
        "call2",
        "call3",
    ]
    assert [message["content"] for message in second.messages[3:]] == [
        f"     1  {name} 的内容" for name in ("a.txt", "b.txt", "c.txt")
    ]
    assert kinds(session.read_thread()) == [
        "turn_start",
        "user_message",
        "tool_call",
        "tool_call",
        "tool_call",
        "tool_result",
        "tool_result",
        "tool_result",
        "model_text",
        "turn_end",
    ]


def test_text_and_tool_calls_of_one_response_share_one_assistant_message(
    make_session: Any, fake_model: FakeModel, tmp_path: Path
) -> None:
    """一步一物化在接口上的样子：同一次响应里的文本和工具调用转成同一条 assistant 消息。"""
    put(tmp_path, "a.txt", "甲\n")
    fake_model.call(READ_A, text="我先看看")
    fake_model.reply("好了")
    session: Session = make_session()
    result = session.start_turn("看看 a.txt")
    assert result.outcome is Outcome.DONE
    second = fake_model.requests()[1]
    assert roles(second) == ["system", "user", "assistant", "tool"]
    assert second.messages[2]["content"] == "我先看看"
    assert len(second.messages[2]["tool_calls"]) == 1
    assert kinds(session.read_thread()) == [
        "turn_start",
        "user_message",
        "model_text",
        "tool_call",
        "tool_result",
        "model_text",
        "turn_end",
    ]


def test_tool_calls_of_an_earlier_turn_are_carried_in_order(
    make_session: Any, fake_model: FakeModel, tmp_path: Path
) -> None:
    """R2.1-S2：上一个回合里有两次工具调用，新回合的第一次请求里两次调用和结果都在，顺序不变。"""
    put(tmp_path, "a.txt", "甲\n")
    put(tmp_path, "b.txt", "乙\n")
    fake_model.call(READ_A, ("read_file", {"path": "b.txt"}))
    fake_model.reply("读完了")
    fake_model.reply("现在读过了")
    session = make_session()
    session.start_turn("读两个文件")
    session.start_turn("现在呢？")
    third = fake_model.requests()[2]
    assert roles(third) == ["system", "user", "assistant", "tool", "tool", "assistant", "user"]
    assert [message["tool_call_id"] for message in third.messages[3:5]] == ["call1", "call2"]
    assert [message["content"] for message in third.messages[3:5]] == [CONTENT_A, "     1  乙"]
    assert third.messages[6]["content"] == "现在呢？"


def test_an_unknown_tool_is_reported_to_the_model_and_the_turn_goes_on(
    make_session: Any, fake_model: FakeModel
) -> None:
    """R12.2：模型调用了没有注册的工具，这作为工具结果交回模型，回合继续。"""
    fake_model.call(("no_such_tool", {}))
    fake_model.reply("那算了")
    result = make_session().start_turn("问")
    assert (result.outcome, result.reply) == (Outcome.DONE, "那算了")
    second = fake_model.requests()[1]
    assert second.messages[3] == {
        "role": "tool",
        "tool_call_id": "call1",
        "content": "没有名为 no_such_tool 的工具。",
    }


def test_a_model_failure_after_a_tool_call_ends_the_turn(
    make_session: Any, fake_model: FakeModel, tmp_path: Path
) -> None:
    """R12.4：工具结果回填之后的那次请求失败，回合以出错结束，不再发起请求（决策 D-11）。"""
    put(tmp_path, "a.txt", "甲\n")
    fake_model.call(READ_A)
    fake_model.fail(401)
    session: Session = make_session()
    result = session.start_turn("读一下 a.txt")
    assert (result.outcome, result.reason, result.reply) == (
        Outcome.ERROR,
        "鉴权失败（HTTP 401）",
        "",
    )
    assert len(fake_model.requests()) == 2
    assert kinds(session.read_thread()) == [
        "turn_start",
        "user_message",
        "tool_call",
        "tool_result",
        "turn_end",
    ]
    assert endings(session.read_thread()) == [TurnEnd(Outcome.ERROR, "鉴权失败（HTTP 401）")]


def test_the_step_limit_ends_the_turn_without_running_the_last_tools(
    make_session: Any,
    fake_model: FakeModel,
    log_path: Path,
    tmp_path: Path,
) -> None:
    """R12.3-S1：模型每次都调用工具，第 20 次请求结束后回合以步数上限结束。"""
    put(tmp_path, "a.txt", "甲\n")
    for _ in range(20):
        fake_model.call(READ_A)
    session: Session = make_session()
    result = session.start_turn("一直读")
    assert result.outcome is Outcome.STEP_LIMIT
    assert (result.reply, "步数上限" in result.reason) == ("", True)
    assert len(fake_model.requests()) == 20
    records = wait_for_log(log_path, 20)
    assert len(records) == 20
    assert {record["turn_id"] for record in records} == {result.turn_id}
    assert len({record["request_id"] for record in records}) == 20
    assert kinds(session.read_thread()) == [
        "turn_start",
        "user_message",
        *(["tool_call", "tool_result"] * 20),
        "turn_end",
    ]
    # 第 20 次响应的调用留在记录里，没有执行，补了一条"没有执行"的结果。
    assert written(session.read_thread())[-2:] == (
        ToolResult("call1", NOT_RUN_AT_LIMIT, True, NOT_RUN_AT_LIMIT),
        LIMIT,
    )


def test_ctrl_c_while_a_tool_runs_cancels_the_turn(
    make_session: Any, fake_model: FakeModel, ctrl_c: Any, tmp_path: Path
) -> None:
    """R12.5：工具执行中按 Ctrl+C，回合以取消结束，同一响应里后面的工具调用不再执行。"""
    started = threading.Event()

    def stall(_arguments: Mapping[str, Json]) -> ToolOutput:
        started.set()
        # 模拟的 Ctrl+C 打不断一次长的阻塞，只在上一个字节码边界生效，所以按切片等。
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            time.sleep(0.1)
        return ToolOutput("不该走到这里")

    put(tmp_path, "a.txt", "甲\n")
    tools = Registry([Tool("stall", "卡住不动", {"type": "object"}, stall)])
    fake_model.call(("stall", {}))
    session: Session = make_session(tools=tools)
    ctrl_c(started.is_set)
    result = session.start_turn("先卡住")
    assert result.outcome is Outcome.CANCELLED
    assert "Ctrl+C" in result.reason
    assert len(fake_model.requests()) == 1
    # 被中断的调用没有完成，补了一条"没有执行"的结果；结局项当场写下。
    assert written(session.read_thread())[-2:] == (
        ToolResult("call1", NOT_RUN_CANCELLED, True, NOT_RUN_CANCELLED),
        CANCELLED,
    )


def test_tool_calls_without_an_id_or_arguments_still_get_results(
    make_session: Any, fake_model: FakeModel, tmp_path: Path
) -> None:
    """接口没有给调用编号时按序号补一个；参数是空串时当作没有参数，校验结果照样交回模型。"""
    body = calling([("read_file", "")])
    body["choices"][0]["message"]["tool_calls"][0]["id"] = ""
    fake_model.fail(200, body)
    fake_model.reply("好")
    result = make_session().start_turn("读")
    assert result.outcome is Outcome.DONE
    second = fake_model.requests()[1]
    assert second.messages[2]["tool_calls"][0]["id"] == "call1"
    assert second.messages[3] == {
        "role": "tool",
        "tool_call_id": "call1",
        "content": "缺少必填的参数：path。",
    }


def test_an_empty_reply_is_reported_as_unparseable(
    make_session: Any, fake_model: FakeModel, log_path: Path
) -> None:
    """响应里既没有文本也没有工具调用：按无法解析处理，回合以出错结束。"""
    fake_model.fail(200, completion(""))
    result = make_session().start_turn("问")
    assert (result.outcome, result.reason) == (Outcome.ERROR, "无法解析模型的响应")
    assert [record["error"]["kind"] for record in read_log(log_path)] == ["bad_response"]
