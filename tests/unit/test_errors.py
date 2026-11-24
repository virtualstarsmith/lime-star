"""classify 的单元测试：SDK 的异常怎样归类，失败里为什么不带错误正文（R12.4、R3.3）。"""

import dataclasses

import httpx2
import openai
import pytest

from lime_star.model_provider import ErrorKind, classify

URL = "https://model.invalid/chat/completions"
DETAIL = "DETAIL-MARKER-0123456789"


def request() -> httpx2.Request:
    return httpx2.Request("POST", URL)


def status_error(
    cls: type[openai.APIStatusError], status: int, body: object = None
) -> openai.APIStatusError:
    response = httpx2.Response(status, request=request())
    return cls("err", response=response, body=body)


def error_body(code: str = "invalid_request_error", message: str = DETAIL) -> dict[str, object]:
    return {"error": {"message": message, "type": "invalid_request_error", "code": code}}


def test_auth_error_is_reported_as_auth_with_status() -> None:
    """R12.4-S1：鉴权错误归为一类，说明里有类别和接口状态码。"""
    failure = classify(status_error(openai.AuthenticationError, 401))
    assert dataclasses.asdict(failure) == {
        "kind": ErrorKind.AUTH,
        "status_code": 401,
        "detail": "",
    }
    assert failure.describe() == "鉴权失败（HTTP 401）"
    assert classify(status_error(openai.PermissionDeniedError, 403)).kind is ErrorKind.AUTH


@pytest.mark.parametrize(
    ("status", "kind", "label"),
    [
        (429, ErrorKind.RATE_LIMIT, "请求过于频繁"),
        (404, ErrorKind.NOT_FOUND, "接口或模型不存在"),
        (500, ErrorKind.SERVER, "模型服务出错"),
        (503, ErrorKind.SERVER, "模型服务出错"),
        (418, ErrorKind.REJECTED, "模型接口返回错误"),
    ],
)
def test_status_codes_map_to_kinds(status: int, kind: ErrorKind, label: str) -> None:
    failure = classify(status_error(openai.APIStatusError, status))
    assert failure.kind is kind
    assert failure.status_code == status
    assert failure.describe() == f"{label}（HTTP {status}）"


def test_bad_request_without_overflow_marker() -> None:
    failure = classify(status_error(openai.BadRequestError, 400, error_body()))
    assert failure.kind is ErrorKind.BAD_REQUEST


@pytest.mark.parametrize(
    "body",
    [
        error_body(code="context_length_exceeded"),
        error_body(message="This model's maximum context length is 128000 tokens"),
        error_body(message="Your input exceeds the context window of this model"),
        {"error": {"code": "context_length_exceeded", "message": "too long"}},
    ],
)
def test_context_overflow_is_its_own_kind(body: object) -> None:
    """R12.4-S2：会话历史超出上下文上限时归为上下文超限，不是一般的请求被拒。"""
    failure = classify(status_error(openai.BadRequestError, 400, body))
    assert failure.kind is ErrorKind.CONTEXT
    assert failure.status_code == 400
    assert failure.describe() == "上下文超出上限（HTTP 400）"


def test_error_body_is_not_kept() -> None:
    """R3.3：失败对象里只有类别、状态码和说明，没有接口返回的错误正文。"""
    exc = status_error(openai.AuthenticationError, 401, error_body())
    failure = classify(exc)
    assert DETAIL not in failure.describe()
    assert DETAIL not in repr(dataclasses.asdict(failure))


def test_timeout_and_connection_errors() -> None:
    timeout = classify(openai.APITimeoutError(request=request()))
    assert dataclasses.asdict(timeout) == {
        "kind": ErrorKind.TIMEOUT,
        "status_code": None,
        "detail": "",
    }
    assert timeout.describe() == "请求超时"
    connection = classify(openai.APIConnectionError(message=DETAIL, request=request()))
    assert connection.kind is ErrorKind.NETWORK
    assert DETAIL not in connection.describe()


def test_response_that_does_not_match_the_protocol() -> None:
    exc = openai.APIResponseValidationError(
        response=httpx2.Response(200, request=request()), body={}
    )
    failure = classify(exc)
    assert failure.kind is ErrorKind.BAD_RESPONSE
    assert failure.status_code == 200


def test_other_sdk_errors() -> None:
    assert classify(openai.OpenAIError(DETAIL)).kind is ErrorKind.API


def test_unexpected_exception_keeps_only_its_class_name() -> None:
    failure = classify(RuntimeError(DETAIL))
    assert dataclasses.asdict(failure) == {
        "kind": ErrorKind.INTERNAL,
        "status_code": None,
        "detail": "RuntimeError",
    }
    assert DETAIL not in failure.describe()
