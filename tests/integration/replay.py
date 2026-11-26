"""回放：用录制的真实响应驱动模型边界（需求 R11.1）。只在测试里使用（R11.6）。

夹具在 tests/fixtures/provider/ 下，是自描述的：录制时间、模型名、工作目录里的文件，以及若干个回合。
每个回合有用户的消息、录制时对每次批准请求的做法（policy）和实际交回的决定（decisions），
还有逐次的请求与响应。录制见 record_provider.py。

两种回放，都按先后顺序取录下的响应，并记下收到的每个请求：
- Replay 是进程内的 HTTP 传输，给 open_session 的 client 参数用；
- ReplayServer 是本地的 HTTP 服务，给一个真实的 lime-star 进程用（冒烟脚本）。

产品代码对回放一无所知。
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import httpx2
from openai import OpenAI

from tests.integration.fake_model import FAKE_KEY

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "provider"
BASE_URL = "http://replay.invalid/v1"
"""进程内回放用的接口地址：它不会被访问，传输直接在进程内回应。"""


def load(name: str) -> dict[str, Any]:
    """读一份夹具。"""
    loaded: dict[str, Any] = json.loads((FIXTURES / f"{name}.json").read_text("utf-8"))
    return loaded


def turns(fixture: dict[str, Any]) -> list[dict[str, Any]]:
    """夹具里的回合，按录制的先后。"""
    recorded: list[dict[str, Any]] = fixture["turns"]
    return recorded


def recorded_bodies(fixture: dict[str, Any]) -> list[dict[str, Any]]:
    """夹具里逐次请求的正文。"""
    return [
        exchange["request"]["body"] for turn in turns(fixture) for exchange in turn["exchanges"]
    ]


class Script:
    """按夹具回应，并记下收到的每个请求的正文。用例据此核对回放时发给模型的内容。"""

    def __init__(self, fixture: dict[str, Any]) -> None:
        self.responses = [
            exchange["response"] for turn in turns(fixture) for exchange in turn["exchanges"]
        ]
        self.sent: list[dict[str, Any]] = []

    def answer(self, body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        self.sent.append(body)
        if not self.responses:
            return 500, {"error": {"message": "no recorded exchange"}}
        response = self.responses.pop(0)
        return response["status"], response["body"]


class Replay:
    """进程内的回放：一个按夹具回应的 HTTP 传输。"""

    def __init__(self, fixture: dict[str, Any]) -> None:
        self.script = Script(fixture)

    @property
    def sent(self) -> list[dict[str, Any]]:
        return self.script.sent

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
        status, body = self.script.answer(json.loads(request.content))
        return httpx2.Response(status, json=body)


class ReplayServer:
    """本地 HTTP 服务：按夹具回放录下的响应，给一个真实的 lime-star 进程用。"""

    def __init__(self, fixture: dict[str, Any]) -> None:
        self.script = Script(fixture)
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler_type())
        self._server.daemon_threads = True
        threading.Thread(target=self._server.serve_forever, name="replay", daemon=True).start()

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self._server.server_address[1]}"

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()

    def _handler_type(self) -> type[BaseHTTPRequestHandler]:
        script = self.script

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def do_POST(self) -> None:
                length = int(self.headers.get("Content-Length", "0"))
                try:
                    body: Any = json.loads(self.rfile.read(length) or b"{}")
                except ValueError:
                    body = {}
                status, reply = script.answer(body)
                raw = json.dumps(reply).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                try:
                    self.wfile.write(raw)
                except OSError:
                    pass  # 调用方已经不等这次响应了（进程被结束）

            def log_message(self, format: str, *args: Any) -> None:
                pass

        return Handler
