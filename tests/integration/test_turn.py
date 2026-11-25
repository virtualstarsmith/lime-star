"""从 app 回合入口驱动一个会话：历史、系统指令、请求日志、出错与取消。

证据等级：入口集成。模型是本地替身服务，不是真实模型，也没有从真实运行录制。
覆盖 R2.1、R2.2、R3.1 到 R3.3、R12.4、R12.5-S2、R12.6-S1，以及决策 D-09、D-11、D-29。
回合循环经模型调用工具的接线在 test_loop.py 里。
"""

import json
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from lime_star.app import ConfigError, Outcome, Session, SessionError, open_session
from lime_star.protocol import ModelText, TurnEnd, TurnStart, UserMessage
from lime_star.tool_runtime import Registry
from tests.integration.fake_model import (
    FAKE_KEY,
    FAKE_MODEL,
    FakeModel,
    Hold,
    SeenRequest,
    error_body,
)
from tests.integration.support import endings, read_log, wait_for_log, written


def write(base: Path, relative: str, data: str) -> None:
    """在工作目录里放一个文本文件。"""
    path = base / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(data, encoding="utf-8")


FIXED_TIME = datetime(2026, 11, 24, 1, 2, 3, 400000, tzinfo=UTC)
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


def roles(request: SeenRequest) -> list[str]:
    return [message["role"] for message in request.messages]


def contents(request: SeenRequest) -> list[Any]:
    return [message["content"] for message in request.messages]


def counted() -> Iterator[str]:
    number = 0
    while True:
        number += 1
        yield f"id{number}"


def without_elapsed(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """去掉耗时字段以便逐字段比对；耗时本身只断言是非负整数。"""
    stripped = []
    for record in records:
        assert isinstance(record["elapsed_ms"], int) and record["elapsed_ms"] >= 0
        stripped.append({key: value for key, value in record.items() if key != "elapsed_ms"})
    return stripped


def test_first_turn_sends_instruction_and_user_message(
    make_session: Any, fake_model: FakeModel
) -> None:
    """R13.2-S1、R4.1-S1：请求发往配置的地址，用配置的模型和密钥，带系统指令和用户消息。"""
    fake_model.reply("你好，我是替身。")
    result = make_session().start_turn("你好")
    assert (result.outcome, result.reply, result.reason) == (Outcome.DONE, "你好，我是替身。", "")
    [request] = fake_model.requests()
    assert request.path == "/chat/completions"
    assert request.model == FAKE_MODEL
    assert request.authorization == f"Bearer {FAKE_KEY}"
    assert roles(request) == ["system", "user"]
    assert request.messages[1]["content"] == "你好"
    assert result.turn_id


def test_history_is_carried_in_order(make_session: Any, fake_model: FakeModel) -> None:
    """R2.1：每次请求都带上到此刻为止的全部历史，顺序与发生顺序一致。"""
    for text in ("第一答", "第二答", "第三答"):
        fake_model.reply(text)
    session = make_session()
    for text in ("我叫小星", "你好", "我刚才说的名字是什么"):
        session.start_turn(text)
    first, second, third = fake_model.requests()
    assert roles(first) == ["system", "user"]
    assert roles(second) == ["system", "user", "assistant", "user"]
    assert roles(third) == ["system", "user", "assistant", "user", "assistant", "user"]
    assert contents(third)[1:] == ["我叫小星", "第一答", "你好", "第二答", "我刚才说的名字是什么"]
    assert third.messages[0] == second.messages[0] == first.messages[0]


def test_instruction_is_identical_in_every_request(
    make_session: Any, fake_model: FakeModel
) -> None:
    """R2.2-S1：五个回合的五次请求里，系统指令逐字相同。"""
    for index in range(5):
        fake_model.reply(f"第{index}答")
    session = make_session()
    for index in range(5):
        session.start_turn(f"第{index}问")
    requests = fake_model.requests()
    assert len(requests) == 5
    instructions = [json.dumps(request.messages[0], sort_keys=True) for request in requests]
    assert len(set(instructions)) == 1
    assert all(roles(request)[0] == "system" for request in requests)
    assert all(len(request.messages[0]) == 2 for request in requests)


def test_request_log_has_one_record_per_request(
    make_session: Any, fake_model: FakeModel, log_path: Path
) -> None:
    """R3.1、R3.2-S1：每次请求一条字段齐全的记录；提示和回复的内容不进日志。"""
    marker = "UNIQUE-MARKER-七七八八"
    fake_model.reply("第一答")
    fake_model.reply("第二答")
    ids = counted()
    session = make_session(now=lambda: FIXED_TIME, new_id=lambda: next(ids))
    session.start_turn(f"第一问 {marker}")
    session.start_turn("第二问")
    records = read_log(log_path)
    assert [list(record) for record in records] == [RECORD_KEYS, RECORD_KEYS]
    assert without_elapsed(records) == [
        {
            "time": "2026-11-24T01:02:03.400000+00:00",
            "session_id": "id1",
            "thread_id": "id2",
            "turn_id": "id3",
            "request_id": "id4",
            "model": FAKE_MODEL,
            "status": "ok",
            "usage": {"input": 12, "output": 34, "total": 46},
            "error": None,
        },
        {
            "time": "2026-11-24T01:02:03.400000+00:00",
            "session_id": "id1",
            "thread_id": "id2",
            "turn_id": "id5",
            "request_id": "id6",
            "model": FAKE_MODEL,
            "status": "ok",
            "usage": {"input": 12, "output": 34, "total": 46},
            "error": None,
        },
    ]
    raw = log_path.read_text(encoding="utf-8")
    assert marker not in raw
    assert "第一答" not in raw
    assert FAKE_KEY not in raw


def test_three_requests_under_one_turn_get_distinct_request_ids(
    make_session: Any,
    fake_model: FakeModel,
    file_tools: Registry,
    log_path: Path,
    tmp_path: Path,
) -> None:
    """R3.1-S1：一个回合里的三次模型请求得到三条记录，request_id 互不相同。

    回合里模型先两次调用 read_file，第三次才给出最终回复，请求由真实的循环发出。
    """
    write(tmp_path, "a.txt", "甲\n")
    write(tmp_path, "b.txt", "乙\n")
    fake_model.call(("read_file", {"path": "a.txt"}))
    fake_model.call(("read_file", {"path": "b.txt"}))
    fake_model.reply("读完了")
    ids = counted()
    session = make_session(tools=file_tools, now=lambda: FIXED_TIME, new_id=lambda: next(ids))
    result = session.start_turn("把两个文件都读一下")
    assert (result.outcome, result.reply) == (Outcome.DONE, "读完了")
    records = read_log(log_path)
    assert [record["turn_id"] for record in records] == [result.turn_id] * 3
    assert len({record["request_id"] for record in records}) == 3
    assert [record["status"] for record in records] == ["ok"] * 3
    assert [record["usage"] for record in records] == [{"input": 12, "output": 34, "total": 46}] * 3


def test_failed_request_is_logged_with_kind_and_status_only(
    make_session: Any, fake_model: FakeModel, log_path: Path
) -> None:
    """R3.1-S2、R3.3-S1：失败也有一条记录，只记类别和状态码，不记错误正文。"""
    detail = "DETAIL-MARKER-" + "x" * 40
    fake_model.fail(400, error_body(detail, code="bad_request"))
    result = make_session().start_turn("会失败的问题")
    assert result.outcome is Outcome.ERROR
    [record] = read_log(log_path)
    assert record["status"] == "failed"
    assert record["usage"] is None
    assert record["error"] == {"kind": "bad_request", "status_code": 400, "detail": ""}
    assert detail not in log_path.read_text(encoding="utf-8")


def test_auth_error_ends_the_turn_and_the_session_goes_on(
    make_session: Any, fake_model: FakeModel
) -> None:
    """R12.4-S1：鉴权错误结束这个回合并说明是鉴权问题；不自动重试；随后还能继续对话。"""
    fake_model.fail(401, error_body("Incorrect API key provided"))
    fake_model.reply("这次成功了")
    session: Session = make_session()
    failed = session.start_turn("第一问")
    assert (failed.outcome, failed.reply, failed.reason) == (
        Outcome.ERROR,
        "",
        "鉴权失败（HTTP 401）",
    )
    assert endings(session.read_thread()) == [TurnEnd(Outcome.ERROR, "鉴权失败（HTTP 401）")]
    done = session.start_turn("第二问")
    assert (done.outcome, done.reply) == (Outcome.DONE, "这次成功了")
    assert len(fake_model.requests()) == 2


def test_context_overflow_is_treated_as_an_error(make_session: Any, fake_model: FakeModel) -> None:
    """R12.4-S2：历史超出模型上下文上限时按出错处理，回合结束。"""
    fake_model.fail(400, error_body("too long", code="context_length_exceeded"))
    result = make_session().start_turn("很长的问题")
    assert (result.outcome, result.reason) == (Outcome.ERROR, "上下文超出上限（HTTP 400）")


def test_server_error_is_not_retried(
    make_session: Any, fake_model: FakeModel, log_path: Path
) -> None:
    """决策 D-11：模型出错不自动重试，接口只收到一次请求。"""
    fake_model.fail(500)
    result = make_session().start_turn("问")
    assert (result.outcome, result.reason) == (Outcome.ERROR, "模型服务出错（HTTP 500）")
    fake_model.wait_for_requests(1)
    assert len(fake_model.requests()) == 1
    assert [record["error"]["kind"] for record in read_log(log_path)] == ["server"]


def test_cancel_stops_waiting_and_next_turn_keeps_history(
    make_session: Any, fake_model: FakeModel, log_path: Path, ctrl_c: Any
) -> None:
    """R12.5-S2、R12.6-S1：等待模型时按 Ctrl+C，回合以取消结束。

    下一条消息开始新回合，并带上取消之前的历史。
    """
    hold = Hold()
    fake_model.reply("迟到的回复", hold=hold)
    fake_model.reply("第二答")
    session: Session = make_session()
    ctrl_c(lambda: len(fake_model.requests()) >= 1)
    cancelled = session.start_turn("第一问")
    assert (cancelled.outcome, cancelled.reason, cancelled.reply) == (
        Outcome.CANCELLED,
        "用户按 Ctrl+C 取消",
        "",
    )
    done = session.start_turn("第二问")
    assert (done.outcome, done.reply) == (Outcome.DONE, "第二答")
    [first, second] = fake_model.requests()
    assert contents(second)[1:] == ["第一问", "第二问"]
    record = session.read_thread()
    assert endings(record) == [
        TurnEnd(Outcome.CANCELLED, "用户按 Ctrl+C 取消"),
        TurnEnd(Outcome.DONE, ""),
    ]
    assert written(record) == (
        TurnStart(),
        UserMessage(content="第一问"),
        TurnEnd(Outcome.CANCELLED, "用户按 Ctrl+C 取消"),
        TurnStart(),
        UserMessage(content="第二问"),
        ModelText(content="第二答"),
        TurnEnd(Outcome.DONE, ""),
    )
    hold.release()
    by_turn = {record["turn_id"]: record for record in wait_for_log(log_path, 2)}
    # 已经发出的请求照常留下记录；它晚到，所以不能假设它在日志里的先后。
    assert by_turn[cancelled.turn_id]["status"] == "ok"
    assert by_turn[done.turn_id]["status"] == "ok"
    # 迟到的回复进了日志，没有进会话记录。
    assert session.read_thread() == record
    assert first.messages[1]["content"] == "第一问"


def test_runtime_directory_is_created_only_when_the_session_opens(
    tmp_path: Path, model_env: dict[str, str]
) -> None:
    """决策 D-29：打开会话时在工作目录下建 .lime-star/logs；配置缺失时什么都不建。"""
    with pytest.raises(ConfigError):
        open_session(env={}, workdir=tmp_path)
    assert list(tmp_path.iterdir()) == []
    open_session(env=model_env, workdir=tmp_path)
    assert tmp_path.joinpath(".lime-star", "logs").is_dir()


def test_unwritable_runtime_directory_is_a_session_error(
    tmp_path: Path, model_env: dict[str, str]
) -> None:
    tmp_path.joinpath(".lime-star").write_text("占位", encoding="utf-8")
    with pytest.raises(SessionError) as excinfo:
        open_session(env=model_env, workdir=tmp_path)
    assert str(excinfo.value).startswith("无法在工作目录下创建 .lime-star")
