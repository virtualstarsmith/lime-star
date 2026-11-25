"""回放：用录制的真实响应驱动模型边界（需求 R11.1）。只在测试里使用（R11.6）。

夹具在 tests/fixtures/provider/ 下，是自描述的：录制时间、模型名、工作目录里的文件、用户的消息，
以及逐次的请求与响应。回放按顺序取响应，并记下它收到的每个请求，用例据此核对。

产品代码对回放一无所知：这里只是经 open_session 现有的 client 参数换上了一个 HTTP 传输。
"""

import json
from pathlib import Path
from typing import Any

import httpx2
from openai import OpenAI

from tests.integration.fake_model import FAKE_KEY

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "provider"
BASE_URL = "http://replay.invalid/v1"
"""回放用的接口地址：它不会被访问，传输直接在进程内回应。"""


def load(name: str) -> dict[str, Any]:
    """读一份夹具。"""
    loaded: dict[str, Any] = json.loads((FIXTURES / f"{name}.json").read_text("utf-8"))
    return loaded


def recorded_bodies(fixture: dict[str, Any]) -> list[dict[str, Any]]:
    """夹具里逐次请求的正文。"""
    return [exchange["request"]["body"] for exchange in fixture["exchanges"]]


class Replay:
    """按夹具回应的 HTTP 传输，并记下收到的每个请求的正文。"""

    def __init__(self, fixture: dict[str, Any]) -> None:
        self._responses = [exchange["response"] for exchange in fixture["exchanges"]]
        self.sent: list[dict[str, Any]] = []

    def client(self) -> OpenAI:
        return OpenAI(
            base_url=BASE_URL,
            api_key=FAKE_KEY,
            max_retries=0,
            http_client=httpx2.Client(transport=self._transport(), trust_env=False),
        )

    def _transport(self) -> httpx2.MockTransport:
        return httpx2.MockTransport(self._answer)

    def _answer(self, request: httpx2.Request) -> httpx2.Response:
        request.read()
        self.sent.append(json.loads(request.content))
        if not self._responses:
            return httpx2.Response(500, json={"error": {"message": "no recorded exchange"}})
        response = self._responses.pop(0)
        return httpx2.Response(response["status"], json=response["body"])
