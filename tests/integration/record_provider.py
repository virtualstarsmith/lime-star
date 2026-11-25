"""从真实模型录制一组请求与响应，存成回放夹具（需求 R11.1）。只在需要新夹具时手动运行：

    uv run python -m tests.integration.record_provider

它会消耗真实接口的额度。配置经产品自己的 load_config 读取；密钥只用于这一次请求，
不写进夹具，也不打印。录的是一段固定的对话：请模型读一个三行的文件并说出它有几行。
"""

import hashlib
import json
import os
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx2
from openai import OpenAI

from lime_star.app import Outcome, open_session
from lime_star.model_provider import API_KEY_VAR, BASE_URL_VAR, MODEL_VAR, ModelConfig, load_config
from lime_star.model_provider.prompt import SYSTEM_INSTRUCTION
from tests.integration.replay import FIXTURES

NAME = "read_file"
FILE = "notes.txt"
CONTENT = "第一行：lime-star\n第二行：会话记录\n第三行：回放夹具\n"
MESSAGE = "请读取 notes.txt，告诉我它一共有几行。"


def main() -> int:
    exchanges: list[dict[str, Any]] = []

    def on_response(response: httpx2.Response) -> None:
        response.read()
        exchanges.append(
            {
                "request": {
                    "path": response.request.url.path,
                    "body": json.loads(response.request.content),
                },
                "response": {"status": response.status_code, "body": response.json()},
            }
        )

    try:
        config = load_config(os.environ, Path.cwd())
    except Exception as exc:
        print(f"读不到模型配置（{type(exc).__name__}）：")
        print("在仓库根配置 .env，或者设置三个环境变量。")
        return 2
    with tempfile.TemporaryDirectory(prefix="lime-star-record-") as tmp:
        workdir = Path(tmp)
        (workdir / FILE).write_text(CONTENT, encoding="utf-8")
        try:
            with _recording(config, on_response) as client:
                session = open_session(
                    env={
                        BASE_URL_VAR: config.base_url,
                        API_KEY_VAR: config.api_key,
                        MODEL_VAR: config.model,
                    },
                    workdir=workdir,
                    client=client,
                )
                result = session.start_turn(MESSAGE)
        except Exception as exc:
            # 异常文本可能带着请求头，所以只写异常类名。
            print(f"录制没有完成（{type(exc).__name__}）。")
            return 1
        text = _fixture_text(config, tmp, exchanges)
    if text is None:
        return 1
    FIXTURES.mkdir(parents=True, exist_ok=True)
    target = FIXTURES / f"{NAME}.json"
    target.write_text(text, encoding="utf-8", newline="\n")
    called = sorted(
        call["function"]["name"]
        for exchange in exchanges
        for choice in exchange["response"]["body"].get("choices", [])
        for call in choice["message"].get("tool_calls") or []
    )
    print(
        f"模型：{config.model}；结局：{result.outcome.value}。"
        f"请求与响应 {len(exchanges)} 组；工具调用：{called or '无'}。"
    )
    print(f"交回模型的工具结果：{_tool_result(exchanges) or '无'}")
    print(f"已写入 {target.name}（{len(text)} 个字符）。")
    succeeded = _tool_result(exchanges).startswith("     1  ")
    if not succeeded:
        print("工具没有读到文件，这份夹具不是要录的那段对话。")
    return 0 if result.outcome is Outcome.DONE and called and succeeded else 1


def _tool_result(exchanges: list[dict[str, Any]]) -> str:
    """第二次请求里交回模型的工具消息，也就是真实工具读出来的东西。"""
    for exchange in exchanges[1:]:
        for message in exchange["request"]["body"]["messages"]:
            if message["role"] == "tool":
                return str(message["content"]).split("\\n")[0]
    return ""


@contextmanager
def _recording(config: ModelConfig, on_response: Any) -> Iterator[OpenAI]:
    with httpx2.Client(event_hooks={"response": [on_response]}) as http:
        yield OpenAI(
            base_url=config.base_url,
            api_key=config.api_key,
            max_retries=0,
            http_client=http,
        )


def _fixture_text(config: ModelConfig, tmp: str, exchanges: list[dict[str, Any]]) -> str | None:
    """拼出夹具的文本；里面有密钥、接口地址或本机路径时不写，返回 None。"""
    fixture = {
        "recorded": datetime.now(UTC).isoformat(timespec="seconds"),
        "model": config.model,
        "source": (
            "uv run python -m tests.integration.record_provider 的一次运行："
            "真实接口，经正式的回合入口。"
        ),
        "instruction_sha256": hashlib.sha256(SYSTEM_INSTRUCTION.encode()).hexdigest(),
        "workdir": {FILE: CONTENT},
        "message": MESSAGE,
        "exchanges": exchanges,
    }
    text = json.dumps(fixture, ensure_ascii=False, indent=2) + "\n"
    for private in (config.api_key, config.base_url, tmp, str(Path.home())):
        if private and private in text:
            print("夹具里出现了不该入库的内容（密钥、接口地址或本机路径），没有写入。")
            return None
    return text


if __name__ == "__main__":
    raise SystemExit(main())
