"""list_dir 的单元测试：直接子项与类型、空路径、排序与不隐藏、出错、越界与真实位置。

覆盖 R5.4，以及 R8.1 到 R8.3 里 list_dir 的部分。证据等级：Unit。
"""

import json
import os
from pathlib import Path

import pytest

from lime_star.protocol import ToolCall, ToolResult
from lime_star.tool_runtime import Registry, list_dir
from tests.links import link_directory

SECRET = "secret.txt"


def listing(workdir: Path, path: str = "") -> ToolResult:
    """经注册表调用 list_dir，和模型调用它时走的是同一条路。"""
    arguments = json.dumps({"path": path} if path else {})
    call = ToolCall(call_id="c1", name="list_dir", arguments=arguments)
    return Registry([list_dir(workdir)]).execute(call)


def failed(reason: str) -> ToolResult:
    """出错的工具结果：同一句说明既交给模型，也是给终端看的摘要。"""
    return ToolResult("c1", reason, error=True, summary=reason)


def three_entries(base: Path) -> None:
    (base / "a.txt").write_text("甲", encoding="utf-8")
    (base / "b.txt").write_text("乙", encoding="utf-8")
    (base / "sub").mkdir()


THREE = ToolResult("c1", "文件  a.txt\n文件  b.txt\n目录  sub", summary="列出 3 项")


def test_files_and_a_subdirectory_come_back_with_their_kind(tmp_path: Path) -> None:
    """R5.4-S1：两个文件和一个子目录，返回这三项并标明类型。"""
    three_entries(tmp_path)
    assert listing(tmp_path, ".") == THREE


def test_an_empty_path_lists_the_workdir(tmp_path: Path) -> None:
    """R5.4：路径为空时列出工作目录。"""
    three_entries(tmp_path)
    assert listing(tmp_path) == THREE
    assert listing(tmp_path, "") == THREE


def test_a_subdirectory_is_listed_by_its_path(tmp_path: Path) -> None:
    (tmp_path / "sub" / "deeper").mkdir(parents=True)
    (tmp_path / "sub" / "a.txt").write_text("甲", encoding="utf-8")
    assert listing(tmp_path, "sub") == ToolResult(
        "c1", "文件  a.txt\n目录  deeper", summary="列出 2 项"
    )
    assert listing(tmp_path, "sub/") == ToolResult(
        "c1", "文件  a.txt\n目录  deeper", summary="列出 2 项"
    )


def test_nothing_is_hidden_and_names_sort_together(tmp_path: Path) -> None:
    """决策 D-14：点开头的条目和 .lime-star 也列出来；排序不区分大小写。"""
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config").write_text("", encoding="utf-8")
    (tmp_path / ".lime-star").mkdir()
    (tmp_path / "Z.txt").write_text("", encoding="utf-8")
    (tmp_path / "a.txt").write_text("", encoding="utf-8")
    assert listing(tmp_path) == ToolResult(
        "c1", "目录  .git\n目录  .lime-star\n文件  a.txt\n文件  Z.txt", summary="列出 4 项"
    )
    assert listing(tmp_path, ".git") == ToolResult("c1", "文件  config", summary="列出 1 项")


def test_an_empty_directory_says_so(tmp_path: Path) -> None:
    (tmp_path / "sub").mkdir()
    assert listing(tmp_path, "sub") == ToolResult("c1", "（空目录）", summary="空目录")


def test_a_missing_directory_is_an_error(tmp_path: Path) -> None:
    assert listing(tmp_path, "nope") == failed("目录不存在：nope。")


def test_a_file_is_not_a_directory(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("甲", encoding="utf-8")
    assert listing(tmp_path, "a.txt") == failed("这不是一个目录：a.txt。")


def test_a_directory_inside_the_workdir_is_allowed(tmp_path: Path) -> None:
    """R8.1-S1：目录在工作目录之内，允许列出。"""
    three_entries(tmp_path)
    assert listing(tmp_path, "sub") == ToolResult("c1", "（空目录）", summary="空目录")


def test_a_path_outside_the_workdir_is_refused(tmp_path: Path) -> None:
    """R8.2-S1：列工作目录之外的目录，返回"超出工作目录"的结果，没有读它。"""
    (tmp_path / "outside").mkdir()
    (tmp_path / "outside" / SECRET).write_text("", encoding="utf-8")
    work = tmp_path / "work"
    work.mkdir()
    assert listing(work, "../outside") == failed("超出工作目录：../outside。")
    assert listing(work, str(tmp_path / "outside")) == failed(
        f"超出工作目录：{tmp_path / 'outside'}。"
    )
    assert SECRET not in listing(work, "..").content


def test_a_link_to_outside_is_refused(tmp_path: Path) -> None:
    """R8.3-S1：工作目录里有一个指向外部目录的链接，通过它列目录被拒绝。"""
    (tmp_path / "outside").mkdir()
    (tmp_path / "outside" / SECRET).write_text("", encoding="utf-8")
    work = tmp_path / "work"
    work.mkdir()
    link_directory(tmp_path / "outside", work / "link")
    assert listing(work, "link") == failed("超出工作目录：link。")


def test_a_path_that_wanders_out_and_back_is_allowed(tmp_path: Path) -> None:
    """R8.3-S2：先向上两级再回到目录内，解析后仍落在工作目录内，允许列出。"""
    (tmp_path / "work" / "sub").mkdir(parents=True)
    (tmp_path / "work" / "sub" / "a.txt").write_text("甲", encoding="utf-8")
    assert listing(tmp_path / "work", "sub/../../work/sub/../sub") == ToolResult(
        "c1", "文件  a.txt", summary="列出 1 项"
    )


@pytest.mark.skipif(os.name != "nt", reason="只在 Windows 上不区分大小写")
def test_another_case_spelling_lists_the_same_directory(tmp_path: Path) -> None:
    """R8.3-S3：路径里目录名的大小写与实际不同，列出的是同一个目录。"""
    (tmp_path / "Sub").mkdir()
    (tmp_path / "Sub" / "a.txt").write_text("甲", encoding="utf-8")
    assert listing(tmp_path, "SUB") == ToolResult("c1", "文件  a.txt", summary="列出 1 项")
