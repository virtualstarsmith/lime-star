"""工作目录边界的单元测试：真实位置、..、链接与目录联接、Windows 上不分大小写（R8.1 到 R8.3）。"""

import os
from pathlib import Path

import pytest

from lime_star.tool_runtime import inside
from tests.links import link_directory

OUTSIDE = "OUTSIDE-MARKER"


def make_workdir(base: Path) -> Path:
    work = base / "work"
    (work / "sub").mkdir(parents=True)
    (work / "sub" / "notes.txt").write_text("在里面\n", encoding="utf-8")
    return work


@pytest.fixture
def layout(tmp_path: Path) -> tuple[Path, Path]:
    """返回工作目录和它外面的一个目录，两边各放一个文件。"""
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text(OUTSIDE + "\n", encoding="utf-8")
    return make_workdir(tmp_path), outside


def test_a_path_inside_the_workdir_is_allowed(layout: tuple[Path, Path]) -> None:
    """R8.1-S1：工作目录之内的路径允许访问；空路径就是工作目录自己。"""
    work, _ = layout
    assert inside(work, "sub/notes.txt") == (work / "sub" / "notes.txt").resolve()
    assert inside(work, "") == work.resolve()


def test_a_path_outside_the_workdir_is_refused(layout: tuple[Path, Path]) -> None:
    """R8.2：越过工作目录的相对路径，和指向外面的绝对路径，都被拒绝。"""
    work, outside = layout
    assert inside(work, "../outside/secret.txt") is None
    assert inside(work, str(outside / "secret.txt")) is None


def test_dots_that_come_back_are_allowed(layout: tuple[Path, Path]) -> None:
    """R8.3-S2：路径先向上两级再回到目录内，解析后仍落在工作目录内，允许访问。"""
    work, _ = layout
    assert (
        inside(work, "sub/../../work/sub/../sub/notes.txt")
        == (work / "sub" / "notes.txt").resolve()
    )


def test_a_link_to_outside_cannot_be_followed(layout: tuple[Path, Path]) -> None:
    """R8.3-S1：工作目录里有一个指向外部目录的链接，通过它访问被拒绝。"""
    work, outside = layout
    link_directory(outside, work / "link")
    assert inside(work, "link/secret.txt") is None


def test_a_link_to_inside_is_allowed(layout: tuple[Path, Path]) -> None:
    """指向工作目录里面目录的链接，解析后仍在工作目录内。"""
    work, _ = layout
    link_directory(work / "sub", work / "alias")
    assert inside(work, "alias/notes.txt") == (work / "sub" / "notes.txt").resolve()


def test_a_workdir_entered_through_a_link_still_works(tmp_path: Path) -> None:
    """工作目录自己是经由链接进入的：按它的真实位置判断，里面的文件照常允许。"""
    real = make_workdir(tmp_path / "real")
    link_directory(real, tmp_path / "door")
    assert inside(tmp_path / "door", "sub/notes.txt") == (real / "sub" / "notes.txt").resolve()


@pytest.mark.skipif(os.name != "nt", reason="只在 Windows 上不区分大小写")
def test_directories_spelled_with_another_case_are_the_same(layout: tuple[Path, Path]) -> None:
    """R8.3-S3：路径里目录名的大小写与实际不同，按同一目录处理。"""
    work, _ = layout
    assert inside(work, "SUB/Notes.TXT") == (work / "sub" / "notes.txt").resolve()


def test_the_top_of_a_drive_counts_as_its_own_boundary() -> None:
    """极端情况：工作目录是盘符根或文件系统根时，它下面的路径仍然算在里面。"""
    top = Path(Path.cwd().anchor)
    assert inside(top, "somewhere/file.txt") is not None
