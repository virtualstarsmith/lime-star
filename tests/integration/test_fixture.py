"""Current fixture：用录制的真实响应驱动完整主链（需求 R11.1、R12.1、R11.6）。

证据等级：Current fixture。模型是回放夹具：响应录自真实模型的一次会话，这里不联网。
所以它证明的不是"真实模型现在会这样回答"，而是"真实形状的响应能走通主链"。
"""

from pathlib import Path

from lime_star.app import Outcome, open_session
from lime_star.model_provider import API_KEY_VAR, BASE_URL_VAR, MODEL_VAR
from lime_star.protocol import ToolCall, ToolResult
from tests.integration.fake_model import FAKE_KEY
from tests.integration.replay import BASE_URL, Replay, load, recorded_bodies

ROOT = Path(__file__).resolve().parents[2]
PRODUCT = ROOT / "src" / "lime_star"


def test_the_recorded_read_file_exchange_drives_the_whole_chain(tmp_path: Path) -> None:
    """R11.1-S1、R12.1：回放录下的响应，不联网也走完"模型请求工具、执行、回填、再请求、结束"。"""
    fixture = load("read_file")
    for name, content in fixture["workdir"].items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    replay = Replay(fixture)
    env = {BASE_URL_VAR: BASE_URL, API_KEY_VAR: FAKE_KEY, MODEL_VAR: fixture["model"]}
    session = open_session(env=env, workdir=tmp_path, client=replay.client())
    result = session.start_turn(fixture["message"])
    assert result.outcome is Outcome.DONE, result.reason
    items = [entry.item for entry in session.read_thread()]
    kinds = [item.kind for item in items]
    assert kinds[:2] == ["turn_start", "user_message"]
    assert kinds[-1] == "turn_end"
    assert kinds.count("tool_call") == kinds.count("tool_result") >= 1
    call = next(item for item in items if isinstance(item, ToolCall))
    found = next(item for item in items if isinstance(item, ToolResult))
    assert call.name == "read_file"
    assert items.index(call) < items.index(found) < kinds.index("turn_end")
    # 回放时发给模型的内容与录制时逐项相同（系统指令除外）：真实工具读出的内容也一样。
    recorded = recorded_bodies(fixture)
    assert [sent["model"] for sent in replay.sent] == [body["model"] for body in recorded]
    assert [sent["messages"][1:] for sent in replay.sent] == [
        body["messages"][1:] for body in recorded
    ]
    assert all(body["messages"][0]["role"] == "system" for body in recorded)
    assert replay.sent[0]["tools"][0]["function"]["name"] == "read_file"


def test_the_product_has_no_replay_switch() -> None:
    """R11.6-S1：正式命令没有任何回放或替身的开关。产品代码里不出现这两个词，回放只住在测试里。"""
    offenders = [
        path.relative_to(ROOT).as_posix()
        for path in sorted(PRODUCT.rglob("*.py"))
        if "replay" in (text := path.read_text(encoding="utf-8").lower()) or "fixture" in text
    ]
    assert offenders == []
