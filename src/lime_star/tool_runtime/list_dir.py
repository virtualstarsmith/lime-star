"""list_dir：列出一个目录的直接子项，标明每一项是目录还是文件（需求 R5.4）。

只能列出工作目录里面的目录，越界时返回"超出工作目录"的结果，不读目录（需求 R8.1 到 R8.3）。
不隐藏任何条目，包括点开头的名字和 .lime-star（决策 D-14）。
"""

from collections.abc import Mapping
from pathlib import Path
from typing import cast

from lime_star.protocol import Json
from lime_star.tool_runtime.paths import inside
from lime_star.tool_runtime.registry import Tool, ToolOutput

NAME = "list_dir"

DESCRIPTION = (
    "列出一个目录的直接子项，每行一项，标明是目录还是文件。路径为空时列出工作目录。不隐藏任何条目。"
)
PARAMETERS: dict[str, Json] = {
    "type": "object",
    "properties": {
        "path": {"type": "string", "description": "相对工作目录的目录路径，留空表示工作目录。"}
    },
}


def list_dir(workdir: Path) -> Tool:
    """造一个只列 workdir 里面目录的 list_dir 工具。"""

    def run(arguments: Mapping[str, Json]) -> ToolOutput:
        # 参数模式已经保证 path 是一个字符串。
        shown = cast(str, arguments.get("path", ""))
        where = shown or "."
        target = inside(workdir, shown)
        if target is None:
            return ToolOutput(f"超出工作目录：{where}。", error=True)
        try:
            if not target.exists():
                return ToolOutput(f"目录不存在：{where}。", error=True)
            if not target.is_dir():
                return ToolOutput(f"这不是一个目录：{where}。", error=True)
            entries = sorted(
                target.iterdir(), key=lambda entry: (entry.name.casefold(), entry.name)
            )
        except OSError as exc:
            return ToolOutput(f"无法列出 {where}（{type(exc).__name__}）。", error=True)
        if not entries:
            return ToolOutput("（空目录）", summary="空目录")
        rows = [f"{_kind(entry)}  {entry.name}" for entry in entries]
        return ToolOutput("\n".join(rows), summary=f"列出 {len(rows)} 项")

    return Tool(name=NAME, description=DESCRIPTION, parameters=PARAMETERS, run=run)


def _kind(entry: Path) -> str:
    """一项的类型：目录、文件，或者两者都不是（例如断掉的链接）。"""
    if entry.is_dir():
        return "目录"
    return "文件" if entry.is_file() else "其他"
