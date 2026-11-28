"""
Current fixture：用录制的真实响应驱动完整主链（需求 R11.1、R12.1、R11.6）。

证据等级：Current fixture。模型是回放夹具：响应录自真实模型的一次会话，这里不联网，
所以它证明的不是"真实模型现在会这样回答"，而是"真实形状的响应能走通主链"。
四份夹具都在 2026-11-27 按现行的系统指令重录（glm-5.2）：read_file（P3 起的场景）、
mvp（三个回合：主场景、拒绝写文件、失败的命令）、ask（缺信息场景：两个候选配置文件，
由 test_harness.py 回放），以及 resume（六个回合分在六个进程里，其中一次在等待批准时进程被结束）。
"""

import json
import socket
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from lime_star.app import Recap, Session, open_session, resume_session
from lime_star.model_provider import API_KEY_VAR, BASE_URL_VAR, MODEL_VAR
from lime_star.protocol import (
    Approval,
    Decision,
    Outcome,
    Pending,
    ToolCall,
    ToolResult,
    TurnEnd,
)
from lime_star.thread_store import read
from lime_star.thread_store.turns import NOT_CLOSED, WAITING
from tests.integration.fake_model import FAKE_KEY
from tests.integration.replay import BASE_URL, Replay, load, recorded_bodies, runs, turns
from tests.integration.smoke import CLAIM
from tests.integration.support import Died, transcript_files

ROOT = Path(__file__).resolve().parents[2]
PRODUCT = ROOT / "src" / "lime_star"


def _refuse(_self: socket.socket, address: object) -> None:
    raise AssertionError(f"场景：回放不联网，却连接了 {address!r}")


@pytest.fixture(autouse=True)
def offline(monkeypatch: pytest.MonkeyPatch) -> None:
    """运行前禁用全部 socket：回放不联网。"""
    monkeypatch.setattr(socket.socket, "connect", _refuse)


def stage(fixture: dict[str, Any], workdir: Path) -> None:
    """照夹具在工作目录里放上录制时有的文件。"""
    for name, content in fixture["workdir"].items():
        path = workdir / str(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(str(content), encoding="utf-8")


def play(session: Session, fixture: dict[str, Any]) -> list[Decision]:
    """按夹具逐个回合地驱动会话，批准按录制时的做法交回。返回交回的决定。"""
    decisions: list[Decision] = []
    for turn in turns(fixture):
        policy: Decision = turn["policy"]

        def ask(pending: Pending, decision: Decision = policy) -> None:
            decisions.append(decision)
            session.respond_action(pending.call_id, decision)

        result = session.start_turn(turn["message"], ask=ask)
        assert result.outcome.value == turn["outcome"], (turn["message"], result.reason)
    return decisions


def assert_same_as_recorded(fixture: dict[str, Any], replay: Replay) -> None:
    """回放时发给模型的内容与录制时逐项相同（系统指令除外）。"""
    recorded = recorded_bodies(fixture)
    assert [sent["model"] for sent in replay.sent] == [body["model"] for body in recorded]
    assert [sent["messages"][1:] for sent in replay.sent] == [
        body["messages"][1:] for body in recorded
    ]
    assert all(body["messages"][0]["role"] == "system" for body in recorded)


def test_the_recorded_read_file_exchange_drives_the_whole_chain(tmp_path: Path) -> None:
    """R11.1-S1、R12.1：回放录下的响应，不联网也走完"模型请求工具、执行、回填、再请求、结束"。"""
    fixture: dict[str, Any] = load("read_file")
    stage(fixture, tmp_path)
    replay = Replay(fixture)
    env = {
        BASE_URL_VAR: BASE_URL,
        API_KEY_VAR: FAKE_KEY,
        MODEL_VAR: str(fixture["model"]),
    }
    session = open_session(env=env, workdir=tmp_path, client=replay.client())
    decisions = play(session, fixture)
    assert decisions == []
    items = [entry.item for entry in session.read_thread()]
    kinds = [item.kind for item in items]
    assert kinds[:2] == ["turn_start", "user_message"]
    assert kinds[-1] == "turn_end"
    assert kinds.count("tool_call") == kinds.count("tool_result") >= 1
    call = next(item for item in items if isinstance(item, ToolCall))
    found = next(item for item in items if isinstance(item, ToolResult))
    assert call.name == "read_file"
    assert items.index(call) < items.index(found) < kinds.index("turn_end")
    # 真实工具读出的内容也一样，所以发给模型的第二次请求与录制时相同。
    assert_same_as_recorded(fixture, replay)
    assert replay.sent[0]["tools"][0]["function"]["name"] == "read_file"


def test_the_product_has_no_replay_switch() -> None:
    """R11.6-S1：正式命令没有任何回放或替身的开关。产品代码里不出现这两个词，回放只住在测试里。"""
    offenders = [
        path.relative_to(ROOT).as_posix()
        for path in sorted(PRODUCT.rglob("*.py"))
        if "replay" in (text := path.read_text(encoding="utf-8").lower()) or "fixture" in text
    ]
    assert offenders == []


DANGEROUS = ("write_file", "run_command")


def test_the_recorded_mvp_exchange_drives_three_turns(tmp_path: Path) -> None:
    """R11.1-S1、R7.6、R7.10-S1、R7.13：录制的 MVP 场景三个回合不联网走完整主链。
    写文件和运行脚本经批准才执行；被拒绝的写入没有发生，拒绝作为工具结果交回模型后回合继续；
    失败的命令以退出码 1 交回。模型为回放夹具。"""
    fixture: dict[str, Any] = load("mvp")
    stage(fixture, tmp_path)
    replay = Replay(fixture)
    env = {
        BASE_URL_VAR: BASE_URL,
        API_KEY_VAR: FAKE_KEY,
        MODEL_VAR: str(fixture["model"]),
    }
    session = open_session(env=env, workdir=tmp_path, client=replay.client())
    decisions = play(session, fixture)
    assert decisions == [decision for turn in turns(fixture) for decision in turn["decisions"]]
    assert decisions == ["approved", "approved", "rejected", "approved"]
    items = [entry.item for entry in session.read_thread()]
    kinds = [item.kind for item in items]
    # 三个回合各有开始和结局，中间是四次危险调用，每次的批准项和结果都指向它。
    assert kinds.count("turn_start") == kinds.count("turn_end") == 3
    assert (kinds[:2], kinds[-1]) == (["turn_start", "user_message"], "turn_end")
    assert [item.decision for item in items if isinstance(item, Approval)] == decisions
    for index, item in enumerate(items):
        if isinstance(item, ToolCall) and item.name in DANGEROUS:
            approval, result = items[index + 1], items[index + 2]
            assert isinstance(approval, Approval) and approval.call_id == item.call_id
            assert isinstance(result, ToolResult) and result.call_id == item.call_id
            if approval.decision == "rejected":
                assert result.content == "用户拒绝了这次操作，没有执行。"
    writes = [item for item in items if isinstance(item, ToolCall) and item.name == "write_file"]
    content = json.loads(writes[0].arguments)["content"]
    assert json.loads(writes[0].arguments)["path"] == "hello.py"
    assert (tmp_path / "hello.py").read_bytes() == content.encode("utf-8")
    assert not (tmp_path / "bye.py").exists()
    # 真实的工具执行产生的内容与录制时相同，所以发给模型的每一次请求都与录制时相同。
    assert_same_as_recorded(fixture, replay)


def test_the_recorded_replies_follow_the_report_rules() -> None:
    """R14.1-S1、R14.2-S1：录制时真实模型（glm-5.2，2026-11-27）的最终回复。被拒绝的写入没有被说成已完成；
    以退出码 1 结束的命令被指出失败了。这里核对的是录下来的回复，不是现在再问一次模型；
    现在的模型怎样回答，由冒烟脚本的 --live 去看。"""
    fixture: dict[str, Any] = load("mvp")
    replies = [
        exchange["response"]["body"]["choices"][0]["message"]["content"]
        for turn in turns(fixture)
        for exchange in turn["exchanges"][-1:]
    ]
    assert len(replies) == 3
    assert CLAIM.search(replies[0]) and "hello" in replies[0] and "0" in replies[0]
    assert not CLAIM.search(replies[1]), replies[1]
    assert "拒绝" in replies[1]
    assert "失败" in replies[2] and "退出码" in replies[2] and "1" in replies[2]


def test_the_recorded_resume_runs_drive_the_whole_chain(tmp_path: Path) -> None:
    """R9.1、R9.2-S1、R9.3-S2、R11.1-S1：录制的恢复场景分在几个进程里，这里在同一个进程里按段回放。

    每一段相当于一个进程：新会话，或者恢复工作目录下最近的会话；段与段之间先放开上一个会话的独占写入。
    录制时在等待批准中被结束的那个回合，这里照录制的办法模拟：不回应批准，回合就地停住。
    恢复时它被判为中断，补上结果和结局；之后发给模型的内容与录制时逐项相同（系统指令除外）。
    模型为回放夹具。
    """
    fixture: dict[str, Any] = load("resume")
    stage(fixture, tmp_path)
    replay = Replay(fixture)
    env = {
        BASE_URL_VAR: BASE_URL,
        API_KEY_VAR: FAKE_KEY,
        MODEL_VAR: str(fixture["model"]),
    }
    client = replay.client()
    recaps: list[Recap | None] = []
    held: Session | None = None
    try:
        for run in runs(fixture):
            if held is not None:
                held.close()  # 相当于上一个进程退出：独占写入随之放开
            if run.resume:
                held, recap = resume_session(env=env, workdir=tmp_path, client=client)
            else:
                held, recap = open_session(env=env, workdir=tmp_path, client=client), None
            recaps.append(recap)
            for index in run.turns:
                turn = turns(fixture)[index]
                message, policy = str(turn["message"]), turn["policy"]
                if turn["outcome"] == "interrupted":
                    with pytest.raises(Died):
                        held.start_turn(message, ask=die)
                    held.close()  # 进程被结束
                    held = None
                    break
                assert held.start_turn(message, ask=by(held, policy)).outcome.value == "done"
    finally:
        if held is not None:
            held.close()
    assert [recap is not None for recap in recaps] == [False, True, False, True, False, True]
    files = transcript_files(tmp_path)
    assert len(files) == 3  # 三个新会话各一份记录；恢复没有另起一份
    resumed = [recap for recap in recaps if recap is not None]
    assert {(recap.thread_id, recap.turns) for recap in resumed} == {
        (path.stem, 1) for path in files
    }
    reason = f"{NOT_CLOSED}，当时正在等待批准 write_file，这次操作没有执行"
    assert [recap.reason for recap in resumed] == ["", "", reason]
    cut = [
        entry.item
        for entry in read(tmp_path / ".lime-star" / "threads" / f"{resumed[2].thread_id}.jsonl")
    ]
    end = next(number for number, item in enumerate(cut) if isinstance(item, TurnEnd))
    closing, mended = cut[end], cut[end - 1]
    assert closing == TurnEnd(Outcome.INTERRUPTED, reason)
    assert isinstance(mended, ToolResult) and mended.content == WAITING
    answered = next(
        item for item in cut[:end] if isinstance(item, ToolCall) and item.call_id == mended.call_id
    )
    assert answered.name == "write_file"
    assert not (tmp_path / "hi.py").exists()
    assert_same_as_recorded(fixture, replay)


def die(_pending: Pending) -> None:
    raise Died  # 进程在等待批准时被结束：不回应，也不让回合收尾


def by(session: Session, policy: Decision) -> Callable[[Pending], None]:
    return lambda pending: session.respond_action(pending.call_id, policy)
