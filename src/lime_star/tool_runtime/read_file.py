"""read_file：读取工作目录里的 UTF-8 文本文件，返回带行号的文件内容（需求 R5.1 到 R5.3）。

只能读工作目录里面的路径，越界时返回"超出工作目录"的结果，不读文件（需求 R8.1 到 R8.3）。
"""

from collections.abc import Mapping
from pathlib import Path
from typing import cast

from lime_star.protocol import Json
from lime_star.tool_runtime.paths import inside
from lime_star.tool_runtime.registry import Tool, ToolOutput

NAME = "read_file"
MAX_LINES = 2000
"""单次最多返回的行数（R5.2，决策 D-13）。"""

_NUMBER_WIDTH = 6
"""行号占的宽度：右对齐，后面跟两个空格。"""

DESCRIPTION = (
    "读取工作目录里的一个 UTF-8 文本文件，返回带行号的文件内容。"
    "一次最多返回 2000 行，更长的文件会说明还有多少行没有读。"
)
PARAMETERS: dict[str, Json] = {
    "type": "object",
    "properties": {"path": {"type": "string", "description": "相对工作目录的文件路径。"}},
    "required": ["path"],
}


def read_file(workdir: Path) -> Tool:
    """造一个只读 workdir 里面文件的 read_file 工具。"""

    def run(arguments: Mapping[str, Json]) -> ToolOutput:
        # 参数模式已经保证 path 是一个字符串。
        path = cast(str, arguments["path"])
        target = inside(workdir, path)
        if target is None:
            return ToolOutput(f"超出工作目录：{path}。", error=True)
        if target.is_dir():
            return ToolOutput(f"这是一个目录：{path}。", error=True)
        try:
            raw = target.read_bytes()
        except FileNotFoundError:
            return ToolOutput(f"文件不存在：{path}。", error=True)
        except OSError as exc:
            return ToolOutput(f"无法读取 {path}（{type(exc).__name__}）。", error=True)
        if b"\x00" in raw:
            return ToolOutput(f"二进制文件，不能按文本读取：{path}。", error=True)
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            return ToolOutput(f"非 UTF-8 编码的文件，不能读取：{path}。", error=True)
        return _read(text)

    return Tool(name=NAME, description=DESCRIPTION, parameters=PARAMETERS, run=run)


def _read(text: str) -> ToolOutput:
    """把解码后的文本变成带行号的内容，外加一行给终端看的摘要。"""
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    if lines[-1] == "":
        lines.pop()  # 末尾的换行不算一行
    if not lines:
        return ToolOutput("（空文件）", summary="空文件")
    shown = lines[:MAX_LINES]
    rows = [f"{number:>{_NUMBER_WIDTH}}  {line}" for number, line in enumerate(shown, start=1)]
    rest = len(lines) - len(shown)
    if rest:
        rows.append(f"（文件共 {len(lines)} 行，只读到前 {MAX_LINES} 行，还有 {rest} 行没有读。）")
    summary = f"读到 {len(shown)} 行" + (f"，还有 {rest} 行没有读" if rest else "")
    return ToolOutput("\n".join(rows), summary=summary)
