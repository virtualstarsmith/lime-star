"""工具边界：工具注册表、参数校验、工作目录边界、工具执行，以及 read_file。

边界以 internal/aiprompts/architecture.md 为准：这里不做终端交互，也不发模型请求。
列目录、写文件、执行命令、危险等级和审批随路线图 P4 加入。
"""

from pathlib import Path

from lime_star.tool_runtime.paths import inside
from lime_star.tool_runtime.read_file import read_file
from lime_star.tool_runtime.registry import Registry, Tool, ToolOutput


def default_tools(workdir: Path) -> Registry:
    """正式命令的工具集。路线图 P3 只有 read_file；其余工具随 P4 加入。"""
    return Registry([read_file(workdir)])


__all__ = ["Registry", "Tool", "ToolOutput", "default_tools", "inside", "read_file"]
