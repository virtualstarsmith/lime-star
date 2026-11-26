"""从 app 回合入口恢复会话（需求 R9）。

证据等级：入口集成。模型是本地替身服务，响应是手写的；工具是真的，写文件发生在临时工作目录里。
这里也是根 AGENTS.md 里持久化硬规则的守卫：恢复只从 thread_store 的会话记录读回，
写入之后以新的实例读取，读到的与文件逐项一致；会话在内存里不留第二份。
"进程被结束"在这里用 tests/integration/support.py 的 Died 模拟。真实的两个进程在
test_cli_resume.py 里，真实控制台上的 Ctrl+C 在 test_cli_console.py 里。
"""

import json
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from lime_star.app import (
    ConfigError,
    NoSession,
    Outcome,
    Recap,
    Session,
    SessionError,
    resume_session,
)
from lime_star.model_provider import API_KEY_VAR, BASE_URL_VAR, MODEL_VAR
from lime_star.protocol import (
    Approval,
    Json,
    ModelText,
    Pending,
    ToolCall,
    ToolResult,
    TurnEnd,
    TurnStart,
    UserMessage,
)
from lime_star.thread_store import Transcript
from lime_star.thread_store.turns import NOT_CLOSED, UNKNOWN, WAITING
from lime_star.tool_runtime import Registry, Tool, ToolOutput
from tests.integration.fake_model import FAKE_KEY, FakeModel, Hold
from tests.integration.support import (
    Died,
    client_for,
    entries_of,
    kinds,
    read_log,
    transcript_file,
    transcript_files,
    written,
)

EARLY = datetime(2026, 11, 26, 1, 0, 0, tzinfo=UTC)
LATE = EARLY.replace(minute=5)
WRITE_HELLO = json.dumps({"path": "hello.py", "content": "print('hello')\n"})


def die(_pending: Pending) -> None:
    """进程在等待批准时被结束：不回应，也不让回合收尾。"""
    raise Died


def approve_at_once(session: Session) -> Callable[[Pending], None]:
    return lambda pending: session.respond_action(pending.call_id, "approved")


def resume_in(
    fake_model: FakeModel, model_env: dict[str, str], tmp_path: Path, **overrides: Any
) -> tuple[Session, Recap]:
    """在同一个工作目录里恢复会话。额外的关键字参数原样交给 resume_session。"""
    return resume_session(
        env=model_env, workdir=tmp_path, client=client_for(fake_model), **overrides
    )


def test_a_new_instance_reads_back_what_was_written_and_goes_on(
    make_session: Any, fake_model: FakeModel, model_env: dict[str, str], tmp_path: Path
) -> None:
    """R9.5-S1、R9.1、R9.2-S1，也是持久化硬规则的守卫。

    写入之后以新的实例读取：它读到的历史与文件逐项一致，不依赖旧的那个实例；
    恢复后的第一个请求带上了恢复之前的问答，新的项接着写在同一份记录的后面。
    """
    fake_model.reply("好的。")
    fake_model.reply("你好！")
    old: Session = make_session()
    old.start_turn("我叫小星")
    old.start_turn("你好")
    old.close()
    path = transcript_file(tmp_path)
    fake_model.reply("小星")
    session, recap = resume_in(fake_model, model_env, tmp_path)
    assert recap == Recap(path.stem, 2, "")
    assert session.read_thread() == tuple(entries_of(path))  # 用例自己解析文件
    session.start_turn("我刚才说的名字是什么")
    [_, _, third] = fake_model.requests()
    assert [(message["role"], message["content"]) for message in third.messages[1:]] == [
        ("user", "我叫小星"),
        ("assistant", "好的。"),
        ("user", "你好"),
        ("assistant", "你好！"),
        ("user", "我刚才说的名字是什么"),
    ]
    entries = entries_of(path)
    assert [entry.seq for entry in entries] == list(range(1, 13))
    assert written(entries)[-4:] == (
        TurnStart(),
        UserMessage("我刚才说的名字是什么"),
        ModelText("小星"),
        TurnEnd(Outcome.DONE, ""),
    )
    assert transcript_files(tmp_path) == [path]  # 还是同一份记录，没有另起一份


def test_the_live_session_rereads_the_file_for_every_turn(
    make_session: Any, fake_model: FakeModel, tmp_path: Path
) -> None:
    """硬规则的另一半：会话在内存里不留第二份。别的写入者追加了一项，下一次请求就看得到它。"""
    fake_model.reply("答一")
    fake_model.reply("答二")
    session: Session = make_session()
    session.start_turn("问一")
    path = transcript_file(tmp_path)
    Transcript(path, path.stem, now=lambda: EARLY).append(UserMessage("外面追加的一句"), "outside")
    session.start_turn("问二")
    [_, second] = fake_model.requests()
    assert [message["content"] for message in second.messages[1:]] == [
        "问一",
        "答一",
        "外面追加的一句",
        "问二",
    ]


def test_the_last_session_that_was_active_is_resumed(
    make_session: Any, fake_model: FakeModel, model_env: dict[str, str], tmp_path: Path
) -> None:
    """R9.1-S1：工作目录下有两个会话，恢复的是最后有活动的那个。"""
    fake_model.reply("第一答")
    fake_model.reply("第二答")
    first: Session = make_session(now=lambda: EARLY)
    first.start_turn("甲的问题")
    first.close()
    second: Session = make_session(now=lambda: LATE)
    second.start_turn("乙的问题")
    second.close()
    files = transcript_files(tmp_path)
    assert len(files) == 2
    later = second.read_thread()[0].thread_id
    fake_model.reply("接着答")
    session, recap = resume_in(fake_model, model_env, tmp_path)
    assert (recap.thread_id, recap.turns, recap.reason) == (later, 1, "")
    session.start_turn("接着问")
    [_, _, third] = fake_model.requests()
    said = [message["content"] for message in third.messages[1:]]
    assert "乙的问题" in said and "甲的问题" not in said
    assert transcript_files(tmp_path) == files  # 没有另起一份记录


def test_a_turn_cut_off_at_an_approval_is_closed_and_explained(
    make_session: Any, fake_model: FakeModel, model_env: dict[str, str], tmp_path: Path
) -> None:
    """R9.3-S2、R9.4-S1：进程在等待批准时被结束。恢复时这个回合被判为中断，原因写明那次操作没有执行；
    没有续跑，没有重新请求批准，也没有任何操作被执行。"""
    fake_model.call(("write_file", json.loads(WRITE_HELLO)))
    first: Session = make_session()
    with pytest.raises(Died):
        first.start_turn("新建 hello.py", ask=die)
    first.close()
    path = transcript_file(tmp_path)
    assert kinds(entries_of(path)) == ["turn_start", "user_message", "tool_call"]
    fake_model.reply("没有写，上次在等待批准时中断了。")
    session, recap = resume_in(fake_model, model_env, tmp_path)
    reason = f"{NOT_CLOSED}，当时正在等待批准 write_file，这次操作没有执行"
    assert (recap.turns, recap.reason) == (1, reason)
    assert len(fake_model.requests()) == 1  # 只有被结束之前的那一次：恢复没有请求模型
    assert not (tmp_path / "hello.py").exists()
    entries = entries_of(path)
    turn_id = entries[0].turn_id
    assert written(entries) == (
        TurnStart(),
        UserMessage("新建 hello.py"),
        ToolCall("call1", "write_file", WRITE_HELLO),
        ToolResult("call1", WAITING, True, WAITING),
        TurnEnd(Outcome.INTERRUPTED, reason),
    )
    assert [entry.seq for entry in entries] == [1, 2, 3, 4, 5]
    assert {entry.turn_id for entry in entries} == {turn_id}  # 补上的项属于被中断的那个回合
    # 接着对话：模型看得到那条"没有执行"的结果。
    session.start_turn("hello.py 写好了吗")
    [_, second] = fake_model.requests()
    assert [(message["role"], message["content"]) for message in second.messages[1:]] == [
        ("user", "新建 hello.py"),
        ("assistant", None),
        ("tool", WAITING),
        ("user", "hello.py 写好了吗"),
    ]
    assert not (tmp_path / "hello.py").exists()


def test_an_approved_operation_cut_off_midway_is_reported_as_unknown(
    make_session: Any, fake_model: FakeModel, model_env: dict[str, str], tmp_path: Path
) -> None:
    """R9.3：已获批准的操作在执行途中被结束。恢复时如实说结果未知、可能已经发生，不说成没有执行。"""
    session = make_session(tools=Registry([_bomb()]))
    fake_model.call(("explode", {}))
    with pytest.raises(Died):
        session.start_turn("炸一下", ask=approve_at_once(session))
    session.close()
    path = transcript_file(tmp_path)
    assert kinds(entries_of(path)) == ["turn_start", "user_message", "tool_call", "approval"]
    session, recap = resume_in(fake_model, model_env, tmp_path, tools=Registry([_bomb()]))
    reason = f"{NOT_CLOSED}，explode 已获批准却没有留下结果，这次操作可能已经发生"
    assert recap.reason == reason
    assert written(entries_of(path))[2:] == (
        ToolCall("call1", "explode", "{}"),
        Approval("call1", "explode", "{}", "approved"),
        ToolResult("call1", UNKNOWN, True, UNKNOWN),
        TurnEnd(Outcome.INTERRUPTED, reason),
    )


def test_resume_after_a_cancelled_turn_says_it_was_cancelled(
    make_session: Any,
    fake_model: FakeModel,
    model_env: dict[str, str],
    tmp_path: Path,
    ctrl_c: Callable[..., Any],
) -> None:
    """R9.4-S2：上一个回合被 Ctrl+C 取消，恢复时的原因取它的结局项；有结局的回合不需要补记。"""
    hold = Hold()
    fake_model.reply("迟到的回复", hold=hold)
    session: Session = make_session()
    ctrl_c(lambda: len(fake_model.requests()) >= 1)
    assert session.start_turn("第一问").outcome is Outcome.CANCELLED
    hold.release()
    session.close()
    before = entries_of(transcript_file(tmp_path))
    fake_model.reply("接着答")
    resumed, recap = resume_in(fake_model, model_env, tmp_path)
    assert (recap.turns, recap.reason) == (1, "用户按 Ctrl+C 取消")
    assert entries_of(transcript_file(tmp_path)) == before
    assert resumed.start_turn("第二问").outcome is Outcome.DONE


def test_resume_after_a_failed_or_finished_turn_names_its_reason(
    make_session: Any, fake_model: FakeModel, model_env: dict[str, str], tmp_path: Path
) -> None:
    """上一个回合出错时原因取结局项；正常完成时没有原因。"""
    fake_model.fail(401)
    session: Session = make_session()
    session.start_turn("会失败的问题")
    session.close()
    resumed, recap = resume_in(fake_model, model_env, tmp_path)
    assert (recap.turns, recap.reason) == (1, "鉴权失败（HTTP 401）")
    resumed.close()
    fake_model.reply("这次成功了")
    resumed, recap = resume_in(fake_model, model_env, tmp_path)
    resumed.start_turn("再问")
    resumed.close()
    _, recap = resume_in(fake_model, model_env, tmp_path)
    assert (recap.turns, recap.reason) == (2, "")


def test_a_thread_has_one_writer_at_a_time(
    make_session: Any, fake_model: FakeModel, model_env: dict[str, str], tmp_path: Path
) -> None:
    """一个会话记录同一时刻只有一个写入者：进程还开着的时候，恢复同一个会话被拒；放开之后可以。"""
    fake_model.reply("答")
    first: Session = make_session()
    first.start_turn("问")  # 写下第一项，这个会话才有记录可恢复
    with pytest.raises(SessionError, match="正被另一个进程使用") as excinfo:
        resume_in(fake_model, model_env, tmp_path)
    assert "不能恢复" in str(excinfo.value)
    first.close()
    resumed, _ = resume_in(fake_model, model_env, tmp_path)
    with pytest.raises(SessionError, match="正被另一个进程使用"):
        resume_in(fake_model, model_env, tmp_path)


def test_the_model_config_is_read_again(
    make_session: Any, fake_model: FakeModel, tmp_path: Path
) -> None:
    """R9.5、R4.1、R4.2：模型配置不随会话保存，恢复时重新读取；缺项时照样拒绝启动。"""
    fake_model.reply("答")
    first: Session = make_session()
    first.start_turn("问")
    first.close()
    with pytest.raises(ConfigError) as excinfo:
        resume_session(
            env={BASE_URL_VAR: fake_model.url, MODEL_VAR: "m"},
            workdir=tmp_path,
            client=client_for(fake_model),
        )
    assert "LIME_STAR_API_KEY" in excinfo.value.message
    other = FakeModel()
    other.start()
    try:
        other.reply("我是另一个模型")
        resumed, _ = resume_session(
            env={BASE_URL_VAR: other.url, API_KEY_VAR: FAKE_KEY, MODEL_VAR: "another"},
            workdir=tmp_path,
            client=client_for(other),
        )
        resumed.start_turn("再问")
        [request] = other.requests()
        assert request.model == "another"
        assert len(fake_model.requests()) == 1
    finally:
        other.stop()


def test_the_request_log_keeps_the_thread_and_takes_a_new_session(
    make_session: Any,
    fake_model: FakeModel,
    model_env: dict[str, str],
    tmp_path: Path,
    log_path: Path,
) -> None:
    """R3.4：恢复后的请求带新的 session_id 和原来的 thread_id，凭它们分得清恢复前后的请求。"""
    fake_model.reply("答一")
    first: Session = make_session()
    first.start_turn("问一")
    first.close()
    fake_model.reply("答二")
    session, recap = resume_in(fake_model, model_env, tmp_path)
    session.start_turn("问二")
    [old, new] = read_log(log_path)
    assert old["session_id"] != new["session_id"]
    assert (old["thread_id"], new["thread_id"]) == (recap.thread_id, recap.thread_id)
    for record in (old, new):
        turns = [
            entry
            for entry in entries_of(transcript_file(tmp_path))
            if entry.turn_id == record["turn_id"]
        ]
        assert {entry.item.kind for entry in turns} >= {"turn_start", "turn_end"}


def test_a_record_that_cannot_be_read_is_not_resumed(
    make_session: Any, fake_model: FakeModel, model_env: dict[str, str], tmp_path: Path
) -> None:
    """记录里有一行读不懂：拒绝恢复，什么也不往上写；再试一次还是同样的原因，不是"正被另一个进程使用"。"""
    fake_model.reply("答")
    first: Session = make_session()
    first.start_turn("问")
    first.close()
    path = transcript_file(tmp_path)
    path.write_bytes(path.read_bytes() + b"not json\n")
    raw = path.read_bytes()
    with pytest.raises(SessionError, match="读不懂") as excinfo:
        resume_in(fake_model, model_env, tmp_path)
    assert "不是合法的 JSON" in str(excinfo.value)
    assert path.read_bytes() == raw
    with pytest.raises(SessionError, match="读不懂"):
        resume_in(fake_model, model_env, tmp_path)


def _drop_second_line(path: Path) -> None:
    lines = path.read_bytes().splitlines(keepends=True)
    path.write_bytes(b"".join([lines[0], *lines[2:]]))


def _rename_thread(path: Path) -> None:
    path.write_bytes(
        path.read_bytes().replace(
            f'"thread_id": "{path.stem}"'.encode(), b'"thread_id": "someone-else"'
        )
    )


@pytest.mark.parametrize(
    ("damage", "match"), [(_drop_second_line, "序号不连续"), (_rename_thread, "不属于这个会话")]
)
def test_a_record_that_does_not_add_up_is_not_resumed(
    make_session: Any,
    fake_model: FakeModel,
    model_env: dict[str, str],
    tmp_path: Path,
    damage: Callable[[Path], None],
    match: str,
) -> None:
    """序号不连续、或者有一项不属于这个会话：记录被改过，或者被两个进程同时写过，拒绝恢复。

    这时独占写入已经取到手上：失败之后必须放开，再试一次仍是同样的原因，不是"正被另一个进程使用"。
    """
    fake_model.reply("答")
    first: Session = make_session()
    first.start_turn("问")
    first.close()
    path = transcript_file(tmp_path)
    damage(path)
    raw = path.read_bytes()
    with pytest.raises(SessionError, match=match):
        resume_in(fake_model, model_env, tmp_path)
    assert path.read_bytes() == raw
    with pytest.raises(SessionError, match=match) as again:
        resume_in(fake_model, model_env, tmp_path)
    assert "正被另一个进程使用" not in str(again.value)


def test_nothing_to_resume_is_a_usage_error(
    fake_model: FakeModel, model_env: dict[str, str], tmp_path: Path
) -> None:
    """R9.1-S2：工作目录下没有会话时不能恢复；不建运行时目录，也不发请求。"""
    with pytest.raises(NoSession) as excinfo:
        resume_in(fake_model, model_env, tmp_path)
    assert str(excinfo.value) == "工作目录下没有可恢复的会话。"
    assert (list(tmp_path.iterdir()), fake_model.requests()) == ([], [])


def _bomb() -> Tool:
    def explode(_arguments: Mapping[str, Json]) -> ToolOutput:
        raise Died  # 已获批准的操作执行到一半，进程被结束

    return Tool(
        "explode", "会爆炸", {"type": "object"}, explode, danger=lambda _arguments: "要爆炸了"
    )
