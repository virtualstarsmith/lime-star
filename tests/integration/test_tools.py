"""read_file 经 app 回合入口被模型调用（R5.1 到 R5.3）。

证据等级：入口集成。模型是本地替身服务，响应是手写的。read_file 经 open_session 的 tools 参数注册，
正式命令在路线图 P2 不向模型提供任何工具。read_file 自身的细节由 tests/unit/test_read_file.py 守。
"""

from pathlib import Path
from typing import Any

from lime_star.app import Outcome
from lime_star.protocol import ModelText, ToolCall, ToolResult, UserMessage
from lime_star.tool_runtime import Registry
from tests.integration.fake_model import FakeModel


def put(base: Path, relative: str, data: bytes) -> None:
    """在工作目录里放一个文件，内容是给定的字节。"""
    path = base / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def ask_to_read(
    make_session: Any, fake_model: FakeModel, file_tools: Registry, path: str
) -> tuple[Any, str]:
    """让替身模型请求读 path，再给一句最终回复。

    返回会话记录和模型收到的工具消息内容。
    """
    fake_model.call(("read_file", {"path": path}))
    fake_model.reply("好")
    session = make_session(tools=file_tools)
    result = session.start_turn(f"读一下 {path}")
    assert (result.outcome, result.reply) == (Outcome.DONE, "好")
    first, second = fake_model.requests()
    assert [message["role"] for message in first.messages] == ["system", "user"]
    assert [message["role"] for message in second.messages] == [
        "system",
        "user",
        "assistant",
        "tool",
    ]
    assert second.messages[3]["tool_call_id"] == "call1"
    return session.read_thread(), second.messages[3]["content"]


def test_three_lines_come_back_numbered(
    make_session: Any, fake_model: FakeModel, file_tools: Registry, tmp_path: Path
) -> None:
    """R5.1-S1：三行的文本文件，模型收到这三行，每行前面有行号。"""
    put(tmp_path, "notes.txt", "第一行\n第二行\n第三行\n".encode())
    record, content = ask_to_read(make_session, fake_model, file_tools, "notes.txt")
    assert content == "     1  第一行\n     2  第二行\n     3  第三行"
    assert record.items == (
        UserMessage(content="读一下 notes.txt"),
        ToolCall(call_id="call1", name="read_file", arguments='{"path": "notes.txt"}'),
        ToolResult(call_id="call1", content=content),
        ModelText(content="好"),
    )


def test_a_directory_is_reported_as_a_directory(
    make_session: Any, fake_model: FakeModel, file_tools: Registry, tmp_path: Path
) -> None:
    """R5.1-S2：路径指向目录，模型收到"这是一个目录"的结果，回合照常结束。"""
    put(tmp_path, "sub/.keep", b"")
    record, content = ask_to_read(make_session, fake_model, file_tools, "sub")
    assert content == "这是一个目录：sub。"
    assert record.items[2] == ToolResult(call_id="call1", content=content, error=True)


def test_a_long_file_is_cut_at_2000_lines(
    make_session: Any, fake_model: FakeModel, file_tools: Registry, tmp_path: Path
) -> None:
    """R5.2-S1：5000 行的文件，模型收到前 2000 行，并说明还有 3000 行没有读。"""
    put(tmp_path, "long.txt", "".join(f"行{number}\n" for number in range(1, 5001)).encode())
    record, content = ask_to_read(make_session, fake_model, file_tools, "long.txt")
    rows = content.split("\n")
    assert len(rows) == 2001
    assert (rows[0], rows[1999]) == ("     1  行1", "  2000  行2000")
    assert rows[2000] == "（文件共 5000 行，只读到前 2000 行，还有 3000 行没有读。）"
    assert record.items[2] == ToolResult(call_id="call1", content=content)


def test_a_file_with_a_nul_byte_is_binary(
    make_session: Any, fake_model: FakeModel, file_tools: Registry, tmp_path: Path
) -> None:
    """R5.3-S1：含空字节的文件，模型收到"二进制文件"的错误，收不到内容。"""
    put(tmp_path, "blob.bin", b"abc\x00" + "你看不见我".encode())
    _, content = ask_to_read(make_session, fake_model, file_tools, "blob.bin")
    assert content == "二进制文件，不能按文本读取：blob.bin。"
    assert "你看不见我" not in content


def test_a_gbk_file_is_reported_as_not_utf8(
    make_session: Any, fake_model: FakeModel, file_tools: Registry, tmp_path: Path
) -> None:
    """R5.3-S2：GBK 编码的中文文本，模型收到"非 UTF-8 编码"的错误，收不到内容。"""
    put(tmp_path, "gbk.txt", "你好，世界".encode("gbk"))
    _, content = ask_to_read(make_session, fake_model, file_tools, "gbk.txt")
    assert content == "非 UTF-8 编码的文件，不能读取：gbk.txt。"


def test_a_missing_file_is_a_tool_result_and_the_turn_goes_on(
    make_session: Any, fake_model: FakeModel, file_tools: Registry
) -> None:
    """R12.2-S1：读一个不存在的文件，模型收到"文件不存在"的结果，回合没有结束。"""
    _, content = ask_to_read(make_session, fake_model, file_tools, "nope.txt")
    assert content == "文件不存在：nope.txt。"
