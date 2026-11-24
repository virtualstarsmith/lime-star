"""lime-star 命令入口。

--version、--help 和未知参数见需求 R1；不带参数时在工作目录开始会话（R13.1）。
退出码只有三种（R13.10）：0 正常结束，1 运行期错误，2 用法或配置错误。
"""

import io
import os
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

from lime_star import __version__
from lime_star.app import ConfigError, SessionError, open_session
from lime_star.cli.chat import StdinLines, chat

EXIT_OK = 0
EXIT_RUNTIME = 1
EXIT_USAGE = 2

PROG = "lime-star"

USAGE = """\
用法：lime-star [--version]

不带参数：在工作目录开始一个会话

选项：
  --version    显示版本号并退出
  -h, --help   显示这份帮助并退出
"""

KNOWN_FLAGS = frozenset({"--version", "-h", "--help"})


@dataclass(frozen=True)
class Args:
    """解析后的命令行参数。"""

    show_version: bool
    show_help: bool


class UsageError(Exception):
    """用法错误：有未知的参数。"""


def parse_args(argv: Sequence[str]) -> Args:
    """解析参数。

    先核对每一个参数，有未知的就点名全部未知项；出现未知参数时不做任何动作。
    """
    unknown = [arg for arg in argv if arg not in KNOWN_FLAGS]
    if unknown:
        raise UsageError("未知的参数：" + " ".join(unknown))
    return Args(
        show_version="--version" in argv,
        show_help="-h" in argv or "--help" in argv,
    )


def main(argv: Sequence[str] | None = None) -> int:
    """命令入口，返回值就是进程退出码。"""
    _use_utf8(sys.stdout, sys.stderr, sys.stdin)
    args = list(sys.argv[1:] if argv is None else argv)
    try:
        parsed = parse_args(args)
    except UsageError as exc:
        print(f"{PROG}：{exc}", file=sys.stderr)
        sys.stderr.write(USAGE)
        return EXIT_USAGE
    if parsed.show_version:
        print(f"{PROG} {__version__}")
        return EXIT_OK
    if parsed.show_help:
        sys.stdout.write(USAGE)
        return EXIT_OK
    return run_chat()


def run_chat() -> int:
    """不带参数：读取配置，开始会话。"""
    workdir = Path.cwd()
    try:
        session = open_session(env=os.environ, workdir=workdir)
    except ConfigError as exc:
        sys.stderr.write(f"{PROG}：{exc.message}\n")
        return EXIT_USAGE
    except SessionError as exc:
        sys.stderr.write(f"{PROG}：{exc}\n")
        return EXIT_RUNTIME
    except KeyboardInterrupt:
        return EXIT_OK
    except Exception as exc:
        return _runtime_error(exc)
    lines = StdinLines(sys.stdin)
    lines.start()
    try:
        return chat(session, lines, sys.stdout, sys.stderr, workdir)
    except KeyboardInterrupt:
        return EXIT_OK
    except Exception as exc:
        return _runtime_error(exc)


def _runtime_error(exc: Exception) -> int:
    # 只写异常类名：异常文本可能带着请求详情或路径以外的敏感内容。
    sys.stderr.write(f"{PROG}：运行期错误：{type(exc).__name__}。\n")
    return EXIT_RUNTIME


def _use_utf8(*streams: TextIO | None) -> None:
    """让标准输入、输出、错误一律用 UTF-8。

    Windows 下它们接到管道或文件时，默认会用本地代码页。
    """
    for stream in streams:
        if isinstance(stream, io.TextIOWrapper):
            stream.reconfigure(encoding="utf-8")
