"""工具边界：工具注册表、参数校验、工具执行，以及 read_file。

边界以 internal/aiprompts/architecture.md 为准：这里不做终端交互，也不发模型请求。
路径边界和危险等级随路线图 P4 加入。
"""

from lime_star.tool_runtime.read_file import read_file
from lime_star.tool_runtime.registry import Registry, Tool, ToolOutput

__all__ = ["Registry", "Tool", "ToolOutput", "read_file"]
