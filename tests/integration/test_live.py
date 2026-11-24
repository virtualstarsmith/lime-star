"""真实模型上的验证（Live）。默认不运行，需要显式打开。

它调用真实接口并产生费用，所以不进默认的测试集。打开方式（在仓库根目录）：

    LIME_STAR_LIVE=1 uv run pytest tests/integration/test_live.py -s -v

配置按产品自己的读法取得：环境变量优先，其次工作目录下的 .env。配置只经环境变量传给
在临时目录里运行的子进程，不写进用例、断言信息或仓库根。
断言一律不直接比较密钥：pytest 的失败信息会回显参与比较的值，所以先算出不带值的布尔结果。
证据等级：Live 加 Gate B，真实进程、真实模型。
覆盖 R2.1-S1（三轮对话后记得名字）、R3.1（真实接口下的请求记录和 token 用量）、
R3.2-S1（日志里没有内容）、R4.3（终端和日志里没有密钥）、R12.4-S1（鉴权错误）、R13.10-S2。
"""

import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from lime_star.model_provider import API_KEY_VAR, BASE_URL_VAR, MODEL_VAR, ConfigError, load_config
from tests.integration.support import PROMPT, CliProcess, read_log

LIVE_SWITCH = "LIME_STAR_LIVE"
NAME = "林小星"
QUESTIONS = (
    f"我叫{NAME}，请记住我的名字。只回复“好的”。",
    "一加一等于几？只回复数字。",
    "我刚才说的名字是什么？只回复名字。",
)
WRONG_KEY = "not-a-real-key"
TURN_TIMEOUT = 180.0

pytestmark = pytest.mark.skipif(
    os.environ.get(LIVE_SWITCH) != "1",
    reason=f"默认不调用真实接口；设置 {LIVE_SWITCH}=1 打开",
)


@pytest.fixture(scope="module")
def live_env() -> dict[str, str]:
    """真实配置，放进子进程的环境变量。缺配置时跳过，而不是失败。"""
    try:
        config = load_config(os.environ, Path.cwd())
    except ConfigError:
        pytest.skip("没有模型配置：设置三个 LIME_STAR_ 环境变量，或在仓库根放 .env")
    return {BASE_URL_VAR: config.base_url, API_KEY_VAR: config.api_key, MODEL_VAR: config.model}


def leaks(env: dict[str, str], *texts: str) -> bool:
    """这些文本里是否出现了密钥。调用方只断言返回的布尔值，不把密钥带进断言表达式。"""
    return any(env[API_KEY_VAR] in text for text in texts)


def check_usage(record: dict[str, Any]) -> dict[str, Any]:
    usage = record["usage"]
    assert isinstance(usage, dict), record
    assert isinstance(usage["input"], int) and usage["input"] > 0, usage
    assert isinstance(usage["output"], int) and usage["output"] > 0, usage
    assert usage["total"] == usage["input"] + usage["output"], usage
    return usage


def test_model_remembers_the_name_across_three_turns(
    start_cli: Callable[..., CliProcess], live_env: dict[str, str], log_path: Path
) -> None:
    """R2.1-S1：第一轮说一个名字，第三轮问这个名字，回答里出现它。"""
    process = start_cli(live_env)
    process.wait_for("stdout", PROMPT, timeout=TURN_TIMEOUT)
    for index, question in enumerate(QUESTIONS, start=1):
        process.send(question)
        process.wait_for("stdout", PROMPT, count=index + 1, timeout=TURN_TIMEOUT)
    process.send("/exit")
    code = process.finish()
    stdout, errors, raw = process.output("stdout"), process.output("stderr"), read_text(log_path)

    # 先确认没有泄漏，再打印或比对任何子进程的输出。
    assert not leaks(live_env, stdout, errors, raw), "终端输出或请求日志里出现了密钥"
    assert code == 0
    assert errors == ""

    replies = stdout.split(PROMPT)[1:-1]
    assert len(replies) == 3
    for question, reply in zip(QUESTIONS, replies, strict=True):
        print(f"\n问：{question}\n答：{reply.strip()}")
    assert NAME in replies[2], f"第三轮的回答里没有出现名字：{replies[2].strip()!r}"

    records = read_log(log_path)
    assert [record["status"] for record in records] == ["ok"] * 3
    assert len({record["session_id"] for record in records}) == 1
    assert len({record["thread_id"] for record in records}) == 1
    assert len({record["turn_id"] for record in records}) == 3
    assert len({record["request_id"] for record in records}) == 3
    assert [record["model"] for record in records] == [live_env[MODEL_VAR]] * 3
    for record in records:
        usage = check_usage(record)
        print(
            f"请求 {record['request_id'][:8]}：耗时 {record['elapsed_ms']} 毫秒，token 用量 {usage}"
        )
    assert NAME not in raw, "请求日志里出现了用户消息的内容"
    assert QUESTIONS[1] not in raw, "请求日志里出现了用户消息的内容"


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def test_wrong_key_is_reported_as_auth_error(
    start_cli: Callable[..., CliProcess], live_env: dict[str, str], log_path: Path
) -> None:
    """R12.4-S1、R4.3-S2、R13.10-S2：真实接口拒绝错误的密钥时说明是鉴权问题，不重试，随后正常退出。

    这里故意用一个无效的密钥请求一次真实接口，不使用真实密钥。
    """
    process = start_cli({**live_env, API_KEY_VAR: WRONG_KEY})
    process.wait_for("stdout", PROMPT, timeout=TURN_TIMEOUT)
    process.send("你好")
    process.wait_for("stderr", "回合出错：", timeout=TURN_TIMEOUT)
    process.wait_for("stdout", PROMPT, count=2, timeout=TURN_TIMEOUT)
    process.send("/exit")
    code = process.finish()
    stdout, errors, raw = process.output("stdout"), process.output("stderr"), read_text(log_path)

    assert not leaks(live_env, stdout, errors, raw), "终端输出或请求日志里出现了密钥"
    assert not leaks({API_KEY_VAR: WRONG_KEY}, stdout, errors, raw), "用过的无效密钥被回显"
    assert code == 0
    print(f"\n错误说明：{errors.strip()}")
    assert "鉴权" in errors, "真实接口对错误密钥的说明不是鉴权问题"
    [record] = read_log(log_path)
    assert record["status"] == "failed"
    assert record["error"]["kind"] == "auth"
    assert isinstance(record["error"]["status_code"], int)
    print(f"接口状态码：{record['error']['status_code']}")
