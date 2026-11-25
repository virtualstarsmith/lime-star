"""read_file 的单元测试：带行号的内容与摘要、行数上限、二进制与非 UTF-8 文件、越界与出错。

覆盖 R5.1 到 R5.3、R8.1 到 R8.3 里 read_file 的部分，以及 R12.2-S1 里文件不存在的情况。
证据等级：Unit。它经 app 回合入口被模型调用的场景在 tests/integration/test_tools.py 里。
"""

import json
import os
from pathlib import Path

import pytest

from lime_star.protocol import ToolCall, ToolResult
from lime_star.tool_runtime import Registry, read_file
from tests.links import link_directory

OUTSIDE = "OUTSIDE-MARKER"


def read(workdir: Path, path: str) -> ToolResult:
    """经注册表调用 read_file，和模型调用它时走的是同一条路。"""
    call = ToolCall(call_id="c1", name="read_file", arguments=json.dumps({"path": path}))
    return Registry([read_file(workdir)]).execute(call)


def failed(reason: str) -> ToolResult:
    """出错的工具结果：同一句说明既交给模型，也是给终端看的摘要。"""
    return ToolResult("c1", reason, error=True, summary=reason)


def test_three_lines_come_back_numbered(tmp_path: Path) -> None:
    """R5.1-S1：三行的文本文件返回三行，每行前面有行号；摘要说明读到了几行。"""
    (tmp_path / "notes.txt").write_text("第一行\n第二行\n第三行\n", encoding="utf-8")
    result = read(tmp_path, "notes.txt")
    assert result == ToolResult(
        "c1",
        "     1  第一行\n     2  第二行\n     3  第三行",
        summary="读到 3 行",
    )


def test_a_file_in_a_subdirectory_is_found_by_its_relative_path(tmp_path: Path) -> None:
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "notes.txt").write_text("在里面\n", encoding="utf-8")
    assert read(tmp_path, "sub/notes.txt").content == "     1  在里面"


def test_a_directory_is_reported_as_a_directory(tmp_path: Path) -> None:
    """R5.1-S2：路径指向目录时返回"这是一个目录"的结果，不抛出异常。"""
    (tmp_path / "sub").mkdir()
    assert read(tmp_path, "sub") == failed("这是一个目录：sub。")


def test_only_the_first_2000_lines_are_returned(tmp_path: Path) -> None:
    """R5.2-S1：5000 行的文件只返回前 2000 行，并说明还有 3000 行没有读。"""
    (tmp_path / "long.txt").write_text(
        "".join(f"行{number}\n" for number in range(1, 5001)), encoding="utf-8"
    )
    result = read(tmp_path, "long.txt")
    assert (result.error, result.summary) == (False, "读到 2000 行，还有 3000 行没有读")
    rows = result.content.split("\n")
    assert len(rows) == 2001
    assert (rows[0], rows[1999]) == ("     1  行1", "  2000  行2000")
    assert rows[2000] == "（文件共 5000 行，只读到前 2000 行，还有 3000 行没有读。）"


def test_a_file_within_the_limit_has_no_note(tmp_path: Path) -> None:
    body = "".join(f"行{number}" + ("\n" if number < 2000 else "") for number in range(1, 2001))
    (tmp_path / "edge.txt").write_text(body, encoding="utf-8")
    result = read(tmp_path, "edge.txt")
    rows = result.content.split("\n")
    assert (len(rows), rows[-1], result.summary) == (2000, "  2000  行2000", "读到 2000 行")


def test_a_file_with_a_nul_byte_is_binary(tmp_path: Path) -> None:
    """R5.3-S1：含空字节的文件返回"二进制文件"的错误，不返回内容。"""
    (tmp_path / "blob.bin").write_bytes(b"abc\x00" + "你看不见我".encode())
    result = read(tmp_path, "blob.bin")
    assert result == failed("二进制文件，不能按文本读取：blob.bin。")
    assert "你看不见我" not in result.content


def test_a_gbk_file_is_reported_as_not_utf8(tmp_path: Path) -> None:
    """R5.3-S2：GBK 编码的中文文本返回"非 UTF-8 编码"的错误，不返回内容。"""
    (tmp_path / "gbk.txt").write_bytes("你好，世界".encode("gbk"))
    assert read(tmp_path, "gbk.txt") == failed("非 UTF-8 编码的文件，不能读取：gbk.txt。")


def test_a_missing_file_is_an_error_result(tmp_path: Path) -> None:
    """R12.2-S1：读一个不存在的文件，得到"文件不存在"的结果，而不是异常。"""
    assert read(tmp_path, "nope.txt") == failed("文件不存在：nope.txt。")


def test_line_breaks_and_the_bom_do_not_change_the_lines(tmp_path: Path) -> None:
    (tmp_path / "mixed.txt").write_bytes("\ufeff甲\r\n乙\r丙\n".encode())
    assert read(tmp_path, "mixed.txt").content == "     1  甲\n     2  乙\n     3  丙"


def test_an_empty_file_says_so(tmp_path: Path) -> None:
    (tmp_path / "empty.txt").write_bytes(b"")
    assert read(tmp_path, "empty.txt") == ToolResult("c1", "（空文件）", summary="空文件")
    (tmp_path / "bom.txt").write_bytes("\ufeff".encode())
    assert read(tmp_path, "bom.txt").content == "（空文件）"


def outside_file(base: Path) -> Path:
    secret = base / "outside" / "secret.txt"
    secret.parent.mkdir(parents=True, exist_ok=True)
    secret.write_text(OUTSIDE + "\n", encoding="utf-8")
    return secret


def test_a_path_outside_the_workdir_is_refused_without_reading(tmp_path: Path) -> None:
    """R8.2-S1：读工作目录之外的文件，返回"超出工作目录"的结果，文件没有被读取。"""
    outside_file(tmp_path)
    (tmp_path / "work").mkdir()
    result = read(tmp_path / "work", "../outside/secret.txt")
    assert result == failed("超出工作目录：../outside/secret.txt。")
    assert OUTSIDE not in result.content


def test_an_absolute_path_outside_the_workdir_is_refused(tmp_path: Path) -> None:
    secret = outside_file(tmp_path)
    (tmp_path / "work").mkdir()
    result = read(tmp_path / "work", str(secret))
    assert result == failed(f"超出工作目录：{secret}。")
    assert OUTSIDE not in result.content


def test_a_link_to_outside_is_refused(tmp_path: Path) -> None:
    """R8.3-S1：工作目录里有一个指向外部目录的链接，通过它读取被拒绝。"""
    outside_file(tmp_path)
    work = tmp_path / "work"
    work.mkdir()
    link_directory(tmp_path / "outside", work / "link")
    result = read(work, "link/secret.txt")
    assert result == failed("超出工作目录：link/secret.txt。")
    assert OUTSIDE not in result.content


def test_a_path_that_wanders_out_and_back_is_allowed(tmp_path: Path) -> None:
    """R8.3-S2：先向上两级再回到目录内，解析后仍落在工作目录内，允许访问。"""
    (tmp_path / "work" / "sub").mkdir(parents=True)
    (tmp_path / "work" / "sub" / "notes.txt").write_text("甲\n", encoding="utf-8")
    result = read(tmp_path / "work", "sub/../../work/sub/../sub/notes.txt")
    assert (result.error, result.content) == (False, "     1  甲")


@pytest.mark.skipif(os.name != "nt", reason="只在 Windows 上不区分大小写")
def test_another_case_spelling_reads_the_same_file(tmp_path: Path) -> None:
    """R8.3-S3：路径里目录名的大小写与实际不同，按同一目录处理。"""
    (tmp_path / "Sub").mkdir()
    (tmp_path / "Sub" / "notes.txt").write_text("甲\n", encoding="utf-8")
    assert read(tmp_path, "SUB/Notes.TXT").content == "     1  甲"
