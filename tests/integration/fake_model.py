"""测试替身：一个说 OpenAI Chat Completions 协议的本地 HTTP 服务。

它走真实 HTTP，按脚本顺序返回响应。响应是手写的，没有从真实运行录制；
录制的响应在 tests/fixtures/provider/ 下，由 tests/integration/replay.py 回放。
只供测试使用（需求 R11.6：正式命令没有替身开关）。
"""

import json
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

FAKE_KEY = "FAKE-KEY-FOR-TESTS-0123456789"
FAKE_MODEL = "fake-model"

# 按住的响应最多等这么久，避免用例失败时替身线程一直挂着。
HOLD_LIMIT = 30.0


class Hold:
    """按住一个响应直到测试放行，用来把回合停在等待模型的状态。"""

    def __init__(self) -> None:
        self._released = threading.Event()

    def release(self) -> None:
        self._released.set()

    def wait(self, timeout: float) -> bool:
        return self._released.wait(timeout)


@dataclass(frozen=True)
class SeenRequest:
    """替身收到的一次请求。"""

    path: str
    model: Any
    messages: list[dict[str, Any]]
    authorization: str | None
    tools: Any
    keys: list[str]


@dataclass(frozen=True)
class Step:
    """脚本里的一步：返回什么状态码和响应体，返回之前是否按住。"""

    status: int
    body: dict[str, Any]
    hold: Hold | None = None


def completion(text: str, *, input_tokens: int = 12, output_tokens: int = 34) -> dict[str, Any]:
    """一条手写的 Chat Completions 成功响应。"""
    return {
        "id": "chatcmpl-fake",
        "object": "chat.completion",
        "created": 1700000000,
        "model": FAKE_MODEL,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": text},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": input_tokens,
            "completion_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
        },
    }


def calling(
    calls: Sequence[tuple[str, Mapping[str, Any] | str]], *, text: str | None = None
) -> dict[str, Any]:
    """一条手写的 Chat Completions 响应：模型按顺序请求几次函数调用，可以附带一段文本。

    参数写成字典时转成 JSON 文本；写成字符串时原样发出，用来模拟不合法的参数。
    """
    return {
        "id": "chatcmpl-fake",
        "object": "chat.completion",
        "created": 1700000000,
        "model": FAKE_MODEL,
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": text,
                    "tool_calls": [
                        {
                            "id": f"call{index}",
                            "type": "function",
                            "function": {"name": name, "arguments": _as_json(arguments)},
                        }
                        for index, (name, arguments) in enumerate(calls, start=1)
                    ],
                },
                "finish_reason": "tool_calls",
            }
        ],
        "usage": {"prompt_tokens": 12, "completion_tokens": 34, "total_tokens": 46},
    }


def _as_json(arguments: Mapping[str, Any] | str) -> str:
    return arguments if isinstance(arguments, str) else json.dumps(arguments)


def error_body(message: str, *, code: str = "invalid_request_error") -> dict[str, Any]:
    """一条手写的错误响应体，形状按 OpenAI 接口的错误格式。"""
    return {
        "error": {
            "message": message,
            "type": "invalid_request_error",
            "param": None,
            "code": code,
        }
    }


class FakeModel:
    """按脚本响应的本地替身服务。一个用例用一个实例。"""

    def __init__(self) -> None:
        self._steps: list[Step] = []
        self._seen: list[SeenRequest] = []
        self._changed = threading.Condition()
        self._closing = threading.Event()
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler_type())
        self.on_request: Callable[[SeenRequest], None] | None = None
        self._server.daemon_threads = True

    def start(self) -> None:
        threading.Thread(target=self._server.serve_forever, name="fake-model", daemon=True).start()

    def stop(self) -> None:
        self._closing.set()
        self._server.shutdown()
        self._server.server_close()

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self._server.server_address[1]}"

    def reply(self, text: str, *, hold: Hold | None = None) -> None:
        """脚本化一条成功响应，按收到的先后顺序消费。"""
        with self._changed:
            self._steps.append(Step(200, completion(text), hold))

    def call(
        self,
        *calls: tuple[str, Mapping[str, Any] | str],
        text: str | None = None,
        hold: Hold | None = None,
    ) -> None:
        """脚本化一条带工具调用的成功响应。"""
        with self._changed:
            self._steps.append(Step(200, calling(calls, text=text), hold))

    def fail(
        self,
        status: int,
        body: dict[str, Any] | None = None,
        *,
        hold: Hold | None = None,
    ) -> None:
        """脚本化一条响应：默认是错误响应；给出 status 和 body 时按给出的发。"""
        with self._changed:
            self._steps.append(Step(status, body or error_body("fake failure"), hold))

    def requests(self) -> list[SeenRequest]:
        with self._changed:
            return list(self._seen)

    def wait_for_requests(self, count: int, timeout: float = 10.0) -> list[SeenRequest]:
        """等到第 count 个请求到达。超时按用例失败处理。"""
        with self._changed:
            arrived = self._changed.wait_for(lambda: len(self._seen) >= count, timeout)
            seen = list(self._seen)
        if not arrived:
            raise AssertionError(
                f"场景：等待替身收到请求；期望 {count} 个，实际 {len(seen)} 个，超时 {timeout} 秒"
            )
        return seen

    def _handler_type(self) -> type[BaseHTTPRequestHandler]:
        model = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def do_POST(self) -> None:
                try:
                    model._answer(self)
                except OSError:
                    # 调用方已经不等这次响应了（回合被取消后进程退出），直接收摊。
                    pass

            def log_message(self, format: str, *args: Any) -> None:
                pass

        return Handler

    def _answer(self, handler: BaseHTTPRequestHandler) -> None:
        length = int(handler.headers.get("Content-Length", "0"))
        try:
            payload = json.loads(handler.rfile.read(length) or b"{}")
        except ValueError:
            payload = {}
        seen = SeenRequest(
            path=handler.path,
            model=payload.get("model"),
            messages=payload.get("messages", []),
            authorization=handler.headers.get("Authorization"),
            tools=payload.get("tools"),
            keys=sorted(payload),
        )
        with self._changed:
            self._seen.append(seen)
            step = self._steps.pop(0) if self._steps else None
            self._changed.notify_all()
        if self.on_request is not None:
            # 请求到达时替身线程里调用一次：用例借此查看此刻磁盘上的状态。
            self.on_request(seen)
        if step is None:
            self._write(handler, 500, error_body("no scripted step"))
            return
        if step.hold is not None:
            deadline = time.monotonic() + HOLD_LIMIT
            while not step.hold.wait(0.05):
                if self._closing.is_set() or time.monotonic() > deadline:
                    self._write(handler, 500, error_body("hold ended"))
                    return
        self._write(handler, step.status, step.body)

    def _write(self, handler: BaseHTTPRequestHandler, status: int, body: dict[str, Any]) -> None:
        raw = json.dumps(body).encode("utf-8")
        handler.send_response(status)
        handler.send_header("Content-Type", "application/json")
        handler.send_header("Content-Length", str(len(raw)))
        handler.end_headers()
        handler.wfile.write(raw)
