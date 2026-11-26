"""write_file 的单元测试：原样写入、新建与覆盖、父目录不存在、批准之前的检查、越界与真实位置。

覆盖 R7.1、R7.2、R7.7 里写文件的说明，R7.10-S1，以及 R8.1 到 R8.3 里 write_file 的部分。
证据等级：Unit。批准怎样经 app 回合入口进行，在 tests/integration/test_approval.py 里。
"""

import json
import os
from pathlib import Path
from typing import Any

import pytest

from lime_star.protocol import Pending, ToolCall, ToolResult
from lime_star.tool_runtime import REJECTED, Registry, write_file
from tests.links import link_directory

OUTSIDE = "OUTSIDE-MARKER"


class Writer:
    """经注册表调用 write_file 的调用方：记下批准提示，按给定的决定回应。"""

    def __init__(self, workdir: Path, approved: bool = True) -> None:
        self.notes: list[str] = []
        self.approved = approved
        self.tools = Registry([write_file(workdir)]).approved_by(self._approve)

    def _approve(self, pending: Pending) -> bool:
        self.notes.append(pending.note)
        return self.approved

    def write(self, path: str, content: str) -> ToolResult:
        arguments = json.dumps({"path": path, "content": content}, ensure_ascii=False)
        call = ToolCall(call_id="c1", name="write_file", arguments=arguments)
        return self.tools.execute(call)


def failed(reason: str) -> ToolResult:
    """出错的工具结果：同一句说明既交给模型，也是给终端看的摘要。"""
    return ToolResult("c1", reason, error=True, summary=reason)


def outside_dir(base: Path) -> Path:
    outside = base / "outside"
    outside.mkdir()
    return outside


def test_a_new_file_gets_exactly_the_given_bytes(tmp_path: Path) -> None:
    """R7.1-S1：批准并执行后，文件内容与提示里显示的内容逐字节相同。"""
    content = "print('hello')\nprint('世界')\n"
    writer = Writer(tmp_path)
    result = writer.write("hello.py", content)
    assert result == ToolResult(
        "c1", "已写入 hello.py（新建文件，2 行）。", summary="已写入 hello.py，新建文件，2 行"
    )
    assert (tmp_path / "hello.py").read_bytes() == content.encode("utf-8")


def test_the_prompt_shows_the_path_the_state_and_the_whole_content(tmp_path: Path) -> None:
    """R7.7-S1：批准提示里有路径、"新建"的字样和完整的要写入内容。"""
    content = "第一行\n第二行\n第三行"
    writer = Writer(tmp_path)
    writer.write("notes.txt", content)
    assert writer.notes == [
        "请求批准 write_file：写入 notes.txt（新建文件）。要写入的内容：\n"
        "第一行\n第二行\n第三行\n"
        "----- 内容结束，共 3 行 -----"
    ]


def test_line_feeds_are_not_converted(tmp_path: Path) -> None:
    """R7.1-S2：内容里的换行符原样写入，Windows 上也不会变成 CRLF。"""
    content = "甲\n乙\r\n丙\r丁"
    Writer(tmp_path).write("mixed.txt", content)
    assert (tmp_path / "mixed.txt").read_bytes() == content.encode("utf-8")


def test_an_existing_file_is_overwritten_and_the_prompt_says_so(tmp_path: Path) -> None:
    """R7.1、R7.7-S2：目标文件已存在时覆盖它，提示标明会覆盖已有文件。"""
    (tmp_path / "notes.txt").write_bytes(b"OLD-CONTENT\n")
    writer = Writer(tmp_path)
    result = writer.write("notes.txt", "NEW\n")
    assert writer.notes == [
        "请求批准 write_file：写入 notes.txt（覆盖已有文件）。要写入的内容：\n"
        "NEW\n"
        "----- 内容结束，共 1 行 -----"
    ]
    assert (result.content, (tmp_path / "notes.txt").read_bytes()) == (
        "已写入 notes.txt（覆盖已有文件，1 行）。",
        b"NEW\n",
    )


def test_empty_content_makes_an_empty_file(tmp_path: Path) -> None:
    writer = Writer(tmp_path)
    writer.write("empty.txt", "")
    assert (tmp_path / "empty.txt").read_bytes() == b""
    assert writer.notes == [
        "请求批准 write_file：写入 empty.txt（新建文件）。要写入的内容：\n"
        "----- 内容结束，共 0 行 -----"
    ]


def test_a_missing_parent_directory_is_an_error_and_nothing_is_written(tmp_path: Path) -> None:
    """R7.2-S1：父目录不存在时返回错误说明，不创建目录，也不写文件，不进入批准提示（决策 D-15）。"""
    writer = Writer(tmp_path)
    result = writer.write("no/such/file.txt", "x")
    assert result == failed("父目录不存在，没有写入：no/such/file.txt。")
    assert (writer.notes, list(tmp_path.iterdir())) == ([], [])


def test_a_directory_cannot_be_written(tmp_path: Path) -> None:
    (tmp_path / "sub").mkdir()
    writer = Writer(tmp_path)
    assert writer.write("sub", "x") == failed("这是一个目录，不能写入：sub。")
    assert writer.notes == []


def test_a_rejected_write_leaves_the_disk_alone(tmp_path: Path) -> None:
    """R7.10-S1：用户拒绝了写文件，目标文件没有被改动，拒绝作为结果交回。"""
    (tmp_path / "notes.txt").write_bytes(b"OLD\n")
    call = ToolCall(
        call_id="c1", name="write_file", arguments='{"path": "notes.txt", "content": "x"}'
    )
    assert Registry([write_file(tmp_path)]).execute(call) == failed(REJECTED)
    assert (tmp_path / "notes.txt").read_bytes() == b"OLD\n"
    assert sorted(path.name for path in tmp_path.iterdir()) == ["notes.txt"]


def test_a_file_in_a_subdirectory_is_allowed(tmp_path: Path) -> None:
    """R8.1-S1：目标在工作目录之内，允许写入。"""
    (tmp_path / "sub").mkdir()
    Writer(tmp_path).write("sub/notes.txt", "甲\n")
    assert (tmp_path / "sub" / "notes.txt").read_bytes() == "甲\n".encode()


def test_a_path_outside_the_workdir_is_refused_without_asking(tmp_path: Path) -> None:
    """R8.2-S2：写工作目录之外的路径，没有出现批准提示，返回越界结果，磁盘没有变化。"""
    outside = outside_dir(tmp_path)
    work = tmp_path / "work"
    work.mkdir()
    writer = Writer(work)
    assert writer.write("../outside/new.txt", "x") == failed("超出工作目录：../outside/new.txt。")
    assert (writer.notes, list(outside.iterdir())) == ([], [])


def test_an_absolute_path_outside_the_workdir_is_refused(tmp_path: Path) -> None:
    outside = outside_dir(tmp_path)
    work = tmp_path / "work"
    work.mkdir()
    writer = Writer(work)
    target = str(outside / "new.txt")
    assert writer.write(target, "x") == failed(f"超出工作目录：{target}。")
    assert list(outside.iterdir()) == []


def test_a_link_to_outside_is_refused(tmp_path: Path) -> None:
    """R8.3-S1：工作目录里有一个指向外部目录的链接，通过它写入被拒绝，外部没有变化。"""
    outside = outside_dir(tmp_path)
    work = tmp_path / "work"
    work.mkdir()
    link_directory(outside, work / "link")
    writer = Writer(work)
    assert writer.write("link/new.txt", "x") == failed("超出工作目录：link/new.txt。")
    assert (writer.notes, list(outside.iterdir())) == ([], [])


def test_a_path_that_wanders_out_and_back_is_allowed(tmp_path: Path) -> None:
    """R8.3-S2：先向上两级再回到目录内，解析后仍落在工作目录内，允许写入。"""
    (tmp_path / "work" / "sub").mkdir(parents=True)
    Writer(tmp_path / "work").write("sub/../../work/sub/../sub/notes.txt", "甲\n")
    assert (tmp_path / "work" / "sub" / "notes.txt").read_bytes() == "甲\n".encode()


@pytest.mark.skipif(os.name != "nt", reason="只在 Windows 上不区分大小写")
def test_another_case_spelling_writes_into_the_same_directory(tmp_path: Path) -> None:
    """R8.3-S3：路径里目录名的大小写与实际不同，写进的是同一个目录。"""
    (tmp_path / "Sub").mkdir()
    Writer(tmp_path).write("SUB/Notes.TXT", "甲\n")
    assert [path.name for path in (tmp_path / "Sub").iterdir()] == ["Notes.TXT"]


def test_a_write_that_cannot_replace_the_target_is_an_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """替换目标失败时给出错误，原来的内容留着，临时文件被清掉。"""
    target = tmp_path / "notes.txt"
    target.write_bytes(b"OLD\n")

    def locked(_source: Any, _destination: Any) -> None:
        raise PermissionError("locked")

    monkeypatch.setattr(os, "replace", locked)
    result = Writer(tmp_path).write("notes.txt", "NEW\n")
    assert result == failed("无法写入 notes.txt（PermissionError）。")
    assert target.read_bytes() == b"OLD\n"
    assert [path.name for path in tmp_path.iterdir()] == ["notes.txt"]


def test_bad_arguments_do_not_reach_the_approval(tmp_path: Path) -> None:
    """参数不合法时不进入批准提示，也不写文件。"""
    writer = Writer(tmp_path)
    missing = ToolCall(call_id="c1", name="write_file", arguments='{"path": "a.txt"}')
    assert writer.tools.execute(missing) == failed("缺少必填的参数：content。")
    wrong = ToolCall(call_id="c1", name="write_file", arguments='{"path": 3, "content": "x"}')
    assert writer.tools.execute(wrong) == failed("参数 path：应当是字符串，实际是整数。")
    assert (writer.notes, list(tmp_path.iterdir())) == ([], [])
