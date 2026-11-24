"""read_file：读取工作目录里的 UTF-8 文本文件，返回带行号的文件内容（需求 R5.1 到 R5.3）。

路径边界（R8）随路线图 P4 加入。在那之前正式命令不向模型提供任何工具，read_file 只在
入口集成测试里经 open_session 的 tools 参数注册。
"""

from collections.abc import Mapping
from pathlib import Path
from typing import cast

from lime_star.protocol import Json
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
    """造一个在 workdir 里读取文件的 read_file 工具。"""

    def run(arguments: Mapping[str, Json]) -> ToolOutput:
        # 参数模式已经保证 path 是一个字符串。
        path = cast(str, arguments["path"])
        target = workdir / path
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
        return ToolOutput(_numbered(text))

    return Tool(name=NAME, description=DESCRIPTION, parameters=PARAMETERS, run=run)


def _numbered(text: str) -> str:
    """给每一行加上行号；超过上限时只保留前面的行，并在末尾说明还有多少行没有读。"""
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    if lines[-1] == "":
        lines.pop()  # 末尾的换行不算一行
    if not lines:
        return "（空文件）"
    shown = lines[:MAX_LINES]
    rows = [f"{number:>{_NUMBER_WIDTH}}  {line}" for number, line in enumerate(shown, start=1)]
    rest = len(lines) - len(shown)
    if rest:
        rows.append(f"（文件共 {len(lines)} 行，只读到前 {MAX_LINES} 行，还有 {rest} 行没有读。）")
    return "\n".join(rows)
