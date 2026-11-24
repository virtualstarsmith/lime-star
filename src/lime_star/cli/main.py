"""lime-star 命令入口。

现在只处理 --version、--help 和未知参数（需求 R1.1 到 R1.3）。
不带参数时开始会话（R13.1）由路线图 P1 交付，在那之前按用法错误处理。
退出码只有三种（R13.10）：0 正常结束，1 运行期错误，2 用法或配置错误。
"""

import io
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from typing import TextIO

from lime_star import __version__

EXIT_OK = 0
EXIT_USAGE = 2

PROG = "lime-star"

USAGE = """\
用法：lime-star [--version]

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
    """用法错误：有未知的参数，或者没有给出任何参数。"""


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
    _use_utf8(sys.stdout, sys.stderr)
    args = list(sys.argv[1:] if argv is None else argv)
    try:
        parsed = parse_args(args)
        if not (parsed.show_version or parsed.show_help):
            raise UsageError("没有给出参数。")
    except UsageError as exc:
        print(f"{PROG}：{exc}", file=sys.stderr)
        sys.stderr.write(USAGE)
        return EXIT_USAGE
    if parsed.show_version:
        print(f"{PROG} {__version__}")
    else:
        sys.stdout.write(USAGE)
    return EXIT_OK


def _use_utf8(*streams: TextIO) -> None:
    """让标准输出和标准错误一律用 UTF-8。

    Windows 下它们接到管道或文件时，默认会用本地代码页。
    """
    for stream in streams:
        if isinstance(stream, io.TextIOWrapper):
            stream.reconfigure(encoding="utf-8")
