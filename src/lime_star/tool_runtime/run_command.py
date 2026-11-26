"""run_command：在工作目录里执行一条命令，返回退出码和输出（需求 R7.3 到 R7.5）。

这是危险操作（决策 D-19）：执行前必须经用户批准，批准提示显示原样的命令（R7.6、R7.8）。
它不受路径边界约束，唯一的安全边界是审批（R8.4，决策 D-22）。

Windows 上命令交给系统自带的 Windows PowerShell 解释，其他平台交给 /bin/sh（决策 D-16）。
命令的进程被圈在一棵进程树里（见 tree.py）：超时（R7.4）和 Ctrl+C（R12.5-S1）
都是结束整棵树；命令结束后它留下的后台进程也一并结束。
"""

import locale
import subprocess
import sys
import threading
import time
from collections.abc import Mapping
from pathlib import Path
from typing import IO, Any, cast

from lime_star.protocol import Halted, Json
from lime_star.tool_runtime.registry import Tool, ToolOutput
from lime_star.tool_runtime.tree import Tree

NAME = "run_command"

TIMEOUT = 120.0
"""命令运行超过这么多秒就被终止（R7.4，决策 D-17）。"""

LIMIT = 10000
"""命令输出最多保留这么多字符，只留结尾（R7.5，决策 D-18）。"""

DESCRIPTION = (
    "在工作目录里执行一条命令，返回退出码、标准输出和标准错误。"
    "命令继承本进程的环境变量，读不到标准输入。"
    "Windows 上由 Windows PowerShell 解释，其他平台由 /bin/sh 解释。"
    "运行超过 120 秒会被终止；输出只保留最后 10000 个字符。"
    "这是危险操作：执行前需要用户批准，用户会看到原样的命令。"
)
PARAMETERS: dict[str, Json] = {
    "type": "object",
    "properties": {"command": {"type": "string", "description": "要执行的命令原文。"}},
    "required": ["command"],
}

# 主线程按这个切片反复等命令结束，理由同 model_provider 里的等待：
# Ctrl+C 最多晚一个切片生效，命令一结束等待立即返回。
_WAIT_SLICE = 0.1
_DRAIN_LIMIT = 5.0
"""进程树结束之后，最多再等这么久让输出读完；有圈外的进程占着管道时就不再等。"""
_CHUNK = 65536
STDERR_MARK = "（以下是标准错误）"

if sys.platform == "win32":
    import os

    _POWERSHELL = (
        Path(os.environ.get("SystemRoot", r"C:\Windows"))
        / "System32"
        / "WindowsPowerShell"
        / "v1.0"
        / "powershell.exe"
    )
    # 只用 -Command 时，PowerShell 自己的退出码只说明最后一条语句成没成功（0 或 1）。
    # 追加这几行把原生命令的退出码如实带出来：最后一条语句成功是 0；失败时是非零的
    # $LASTEXITCODE，没有就是 1。命令自己写了 exit，走它自己的。
    _KEEP_EXIT_CODE = (
        "\nif (-not $?) {\n"
        "  if ($null -ne $LASTEXITCODE -and $LASTEXITCODE -ne 0) { exit $LASTEXITCODE }\n"
        "  exit 1\n"
        "}\n"
        "exit 0\n"
    )


def run_command(workdir: Path, timeout: float = TIMEOUT) -> Tool:
    """造一个在 workdir 里执行命令的 run_command 工具。timeout 是它运行的上限秒数。"""

    def danger(arguments: Mapping[str, Json]) -> str:
        # 参数模式已经保证 command 是一个字符串。
        command = cast(str, arguments["command"])
        return f"请求批准 run_command：在工作目录里执行下面的命令：\n{command}"

    def run(arguments: Mapping[str, Json]) -> ToolOutput:
        command = cast(str, arguments["command"])
        return _execute(command, workdir, timeout)

    return Tool(name=NAME, description=DESCRIPTION, parameters=PARAMETERS, run=run, danger=danger)


def _execute(command: str, workdir: Path, timeout: float) -> ToolOutput:
    """启动命令，等它结束。超时和 Ctrl+C 都先结束整棵进程树，再带上已经有的输出。"""
    argv, options = _launch(command)
    process: subprocess.Popen[bytes] | None = None
    try:
        process = subprocess.Popen(
            argv,
            cwd=workdir,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,
            **options,
        )
        tree = Tree(process)
    except OSError as exc:
        _abandon(process)
        if process is None:
            return ToolOutput(f"命令无法启动（{type(exc).__name__}）。", error=True)
        return ToolOutput(f"管不住命令的进程（{type(exc).__name__}），命令没有执行。", error=True)
    except BaseException:
        # 刚启动就被打断：命令不能没人看着继续跑。
        _abandon(process)
        raise
    out = _Flow(cast(IO[bytes], process.stdout))
    err = _Flow(cast(IO[bytes], process.stderr))
    deadline = time.monotonic() + timeout
    try:
        while True:
            try:
                code = process.wait(timeout=_WAIT_SLICE)
            except subprocess.TimeoutExpired:
                if time.monotonic() < deadline:
                    continue
                # 超时（R7.4）：结束整棵进程树，带上截至那时已有的输出。
                tree.end()
                seconds = int(timeout)
                return ToolOutput(
                    _report(f"命令超过 {seconds} 秒，已被终止（超时）。", out, err),
                    error=True,
                    summary=f"超过 {seconds} 秒，已终止",
                )
            # 命令进程结束了。它留下的后台进程占着管道的话，不等它们：一并结束。
            tree.end()
            break
    except KeyboardInterrupt:
        # Ctrl+C（R12.5-S1）：命令执行到一半，已经有的输出要如实记下，不能说成没有执行。
        tree.end()
        raise Halted(
            _report("用户按 Ctrl+C 取消了回合，命令已被终止。", out, err),
            summary="已取消，命令已终止",
        ) from None
    finally:
        tree.close()
    text, errors = out.text(), err.text()
    return ToolOutput(_text(f"退出码：{code}", text, errors), code != 0, f"退出码 {code}")


def _launch(command: str) -> tuple[list[str], dict[str, Any]]:
    """命令怎样启动（决策 D-16）。"""
    if sys.platform == "win32":
        return (
            [
                str(_POWERSHELL),
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                command + _KEEP_EXIT_CODE,
            ],
            # 不给命令控制台：它拿不到用户的控制台输入，也不会闪出窗口。
            {"creationflags": subprocess.CREATE_NO_WINDOW},
        )
    return ["/bin/sh", "-c", command], {"start_new_session": True}


def _abandon(process: subprocess.Popen[bytes] | None) -> None:
    """启动之后、管起来之前出了事：结束命令进程，不给它继续跑的机会。"""
    if process is None:
        return
    try:
        process.kill()
        process.wait(timeout=10)
    except OSError:
        pass


class _Flow:
    """一路输出（标准输出或标准错误）：后台线程一块一块地收，主线程随时能拿到已经收到的内容。"""

    def __init__(self, stream: IO[bytes]) -> None:
        self._chunks: list[bytes] = []
        self._thread = threading.Thread(target=self._pump, args=(stream,), daemon=True)
        self._thread.start()

    def _pump(self, stream: IO[bytes]) -> None:
        try:
            for chunk in iter(lambda: stream.read(_CHUNK), b""):
                self._chunks.append(chunk)
        except OSError:
            pass  # 管道已经被收掉

    def text(self) -> str:
        """等到管道走到末尾（最多 _DRAIN_LIMIT 秒），返回收到的全部内容。"""
        self._thread.join(timeout=_DRAIN_LIMIT)
        return _decode(b"".join(self._chunks))


def _report(head: str, out: _Flow, err: _Flow) -> str:
    """命令被终止后的结果：原因，加上截至那时已有的输出。"""
    text, errors = out.text(), err.text()
    tail = "截至那时已有的输出如下。" if text or errors else "没有输出。"
    return _text(head + tail, text, errors)


def _text(head: str, out: str, errors: str) -> str:
    """结果正文：第一行是退出码或终止的原因，之后是输出；太长时只留结尾并说明（R7.5）。"""
    body = out.rstrip("\n")
    if errors:
        body += ("\n" if body else "") + STDERR_MARK + "\n" + errors.rstrip("\n")
    if len(body) > LIMIT:
        cut = len(body) - LIMIT
        body = (
            f"（命令输出共 {len(body)} 个字符，只保留最后 {LIMIT} 个，截掉了前面的 {cut} 个。）\n"
            + body[cut:]
        )
    return f"{head}\n{body}" if body else head


def _decode(raw: bytes) -> str:
    """命令的输出按 UTF-8 解码；解不开时按系统代码页，解不开的字符用替换字符。换行统一成 LF。"""
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode(locale.getencoding(), errors="replace")
    return text.replace("\r\n", "\n")
