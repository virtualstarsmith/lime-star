"""冒烟脚本共用的小工具（scripts/smoke/ 下的脚本用）：逐项检查并打印、等某一路输出、找命令。

冒烟脚本经 uv 运行，不在 pytest 的收集范围里；放一个小工具模块在这里，两个冒烟脚本就不用各抄一份。
"""

import os
import re
import sys
import time
from collections.abc import Sequence
from pathlib import Path

from tests.integration.support import CliProcess

LIMIT = 300.0
"""整个冒烟最多等这么久；等不到某段输出按失败处理，不让脚本挂着。"""

CLAIM = re.compile(
    r"(已经?|成功)(?:为您|帮你)?(?:在\S{0,12}?)?(?:写入|创建|新建|保存)|(?:写入|创建|新建|保存)成功"
)
"""把操作说成已完成的说法，例如"已写入 hello.py""已在工作目录新建""创建成功"。"""


class SmokeFailure(Exception):
    """冒烟跑不下去了：等不到要等的输出。消息里有当时的两路输出。"""


class Checks:
    """逐项检查，逐行打印；任何一项失败，最后的退出码就是 1。"""

    def __init__(self) -> None:
        self.failed = 0
        self.passed = 0

    def that(self, name: str, ok: bool, detail: str = "") -> bool:
        if ok:
            self.passed += 1
        else:
            self.failed += 1
        print(
            f"{'通过' if ok else '失败'}：{name}" + (f"  ← {detail}" if detail and not ok else "")
        )
        return ok


def lime_star() -> Path:
    """与运行本脚本的解释器装在同一个环境里的 lime-star 命令。"""
    exe = Path(sys.executable).with_name("lime-star.exe" if os.name == "nt" else "lime-star")
    if not exe.is_file():
        raise SmokeFailure(f"找不到 {exe}：先执行 uv sync，再用 uv run 运行")
    return exe


def wait_for_any(process: CliProcess, marks: Sequence[tuple[str, int]], started: float) -> str:
    """等标准输出里出现任意一个标记的第 n 处，返回那个标记。等的是输出本身，不是固定时长。"""
    while True:
        for text, count in marks:
            if process.output("stdout").count(text) >= count:
                return text
        if time.monotonic() - started > LIMIT:
            raise SmokeFailure(
                f"等待 {marks} 超过 {LIMIT:.0f} 秒。"
                f"stdout={process.output('stdout')[-800:]!r}"
                f" stderr={process.output('stderr')[-400:]!r}"
            )
        time.sleep(0.01)
