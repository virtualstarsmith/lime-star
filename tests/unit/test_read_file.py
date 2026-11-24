"""read_file 的单元测试：带行号的内容、行数上限、二进制与非 UTF-8 文件、目录与文件不存在。

覆盖 R5.1 到 R5.3，以及 R12.2-S1 里文件不存在的情况。
证据等级：Unit。它经 app 回合入口被模型调用的场景在 tests/integration/test_tools.py 里。
"""

import json
from pathlib import Path

from lime_star.protocol import ToolCall, ToolResult
from lime_star.tool_runtime import Registry, read_file


def read(workdir: Path, path: str) -> ToolResult:
    """经注册表调用 read_file，和模型调用它时走的是同一条路。"""
    call = ToolCall(call_id="c1", name="read_file", arguments=json.dumps({"path": path}))
    return Registry([read_file(workdir)]).execute(call)


def test_three_lines_come_back_numbered(tmp_path: Path) -> None:
    """R5.1-S1：三行的文本文件返回三行，每行前面有行号。"""
    (tmp_path / "notes.txt").write_text("第一行\n第二行\n第三行\n", encoding="utf-8")
    result = read(tmp_path, "notes.txt")
    assert (result.error, result.call_id) == (False, "c1")
    assert result.content.split("\n") == ["     1  第一行", "     2  第二行", "     3  第三行"]


def test_a_file_in_a_subdirectory_is_found_by_its_relative_path(tmp_path: Path) -> None:
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "notes.txt").write_text("在里面\n", encoding="utf-8")
    assert read(tmp_path, "sub/notes.txt").content == "     1  在里面"


def test_a_directory_is_reported_as_a_directory(tmp_path: Path) -> None:
    """R5.1-S2：路径指向目录时返回"这是一个目录"的结果，不抛出异常。"""
    (tmp_path / "sub").mkdir()
    assert read(tmp_path, "sub") == ToolResult("c1", "这是一个目录：sub。", error=True)


def test_only_the_first_2000_lines_are_returned(tmp_path: Path) -> None:
    """R5.2-S1：5000 行的文件只返回前 2000 行，并说明还有 3000 行没有读。"""
    (tmp_path / "long.txt").write_text(
        "".join(f"行{number}\n" for number in range(1, 5001)), encoding="utf-8"
    )
    result = read(tmp_path, "long.txt")
    assert result.error is False
    rows = result.content.split("\n")
    assert len(rows) == 2001
    assert (rows[0], rows[1999]) == ("     1  行1", "  2000  行2000")
    assert rows[2000] == "（文件共 5000 行，只读到前 2000 行，还有 3000 行没有读。）"


def test_a_file_within_the_limit_has_no_note(tmp_path: Path) -> None:
    body = "".join(f"行{number}" + ("\n" if number < 2000 else "") for number in range(1, 2001))
    (tmp_path / "edge.txt").write_text(body, encoding="utf-8")
    rows = read(tmp_path, "edge.txt").content.split("\n")
    assert len(rows) == 2000
    assert rows[-1] == "  2000  行2000"


def test_a_file_with_a_nul_byte_is_binary(tmp_path: Path) -> None:
    """R5.3-S1：含空字节的文件返回"二进制文件"的错误，不返回内容。"""
    (tmp_path / "blob.bin").write_bytes(b"abc\x00" + "你看不见我".encode())
    result = read(tmp_path, "blob.bin")
    assert result == ToolResult("c1", "二进制文件，不能按文本读取：blob.bin。", error=True)
    assert "你看不见我" not in result.content


def test_a_gbk_file_is_reported_as_not_utf8(tmp_path: Path) -> None:
    """R5.3-S2：GBK 编码的中文文本返回"非 UTF-8 编码"的错误，不返回内容。"""
    (tmp_path / "gbk.txt").write_bytes("你好，世界".encode("gbk"))
    found = read(tmp_path, "gbk.txt")
    assert found == ToolResult("c1", "非 UTF-8 编码的文件，不能读取：gbk.txt。", error=True)


def test_a_missing_file_is_an_error_result(tmp_path: Path) -> None:
    """R12.2-S1：读一个不存在的文件，得到"文件不存在"的结果，而不是异常。"""
    assert read(tmp_path, "nope.txt") == ToolResult("c1", "文件不存在：nope.txt。", error=True)


def test_line_breaks_and_the_bom_do_not_change_the_lines(tmp_path: Path) -> None:
    (tmp_path / "mixed.txt").write_bytes("\ufeff甲\r\n乙\r丙\n".encode())
    rows = read(tmp_path, "mixed.txt").content.split("\n")
    assert rows == ["     1  甲", "     2  乙", "     3  丙"]


def test_an_empty_file_says_so(tmp_path: Path) -> None:
    (tmp_path / "empty.txt").write_bytes(b"")
    assert read(tmp_path, "empty.txt").content == "（空文件）"
    (tmp_path / "bom.txt").write_bytes("\ufeff".encode())
    assert read(tmp_path, "bom.txt").content == "（空文件）"
