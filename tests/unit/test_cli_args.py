"""parse_args 的单元测试：参数解析的纯函数部分（R1.1 到 R1.3）。

真实进程里的退出码与输出流向，由 tests/integration/test_cli_process.py 覆盖。
"""

import pytest

from lime_star.cli.main import Args, UsageError, parse_args


def test_version_flag() -> None:
    assert parse_args(["--version"]) == Args(show_version=True, show_help=False)


@pytest.mark.parametrize("flag", ["-h", "--help"])
def test_help_flags(flag: str) -> None:
    assert parse_args([flag]) == Args(show_version=False, show_help=True)


def test_resume_flag() -> None:
    """R1.2：--resume 是已知的参数，它启动恢复而不是新会话。"""
    assert parse_args(["--resume"]) == Args(resume=True)


def test_version_and_help_take_precedence_over_resume() -> None:
    assert parse_args(["--resume", "--version"]) == Args(show_version=True, resume=True)
    assert parse_args(["--resume", "-h"]) == Args(show_help=True, resume=True)


def test_resume_next_to_an_unknown_argument_is_rejected() -> None:
    with pytest.raises(UsageError) as excinfo:
        parse_args(["--resume", "--nosuch"])
    assert str(excinfo.value) == "未知的参数：--nosuch"


def test_version_takes_precedence_over_help() -> None:
    assert parse_args(["--help", "--version"]) == Args(show_version=True, show_help=True)


@pytest.mark.parametrize(
    ("argv", "unknown"),
    [
        (["--nosuch"], "--nosuch"),
        (["--version", "--nosuch"], "--nosuch"),
        (["-version"], "-version"),
        (["--version=1"], "--version=1"),
        (["--a", "--b"], "--a --b"),
    ],
)
def test_unknown_argument_is_rejected_and_named(argv: list[str], unknown: str) -> None:
    """R1.3：只要有一个未知参数就拒绝，并在错误里点名全部未知项。"""
    with pytest.raises(UsageError) as excinfo:
        parse_args(argv)
    assert str(excinfo.value) == f"未知的参数：{unknown}"
