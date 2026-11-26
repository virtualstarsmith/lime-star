"""工具边界：工具注册表、参数校验、工作目录边界、危险等级、执行前的批准，以及四个工具。

边界以 internal/aiprompts/architecture.md 为准：这里不做终端交互，也不发模型请求。
危险操作要等用户批准：批准来源由 app 回合入口绑定，工具只负责说明这次调用要做什么。
"""

from pathlib import Path

from lime_star.tool_runtime.list_dir import list_dir
from lime_star.tool_runtime.paths import inside
from lime_star.tool_runtime.read_file import read_file
from lime_star.tool_runtime.registry import REJECTED, Granted, Registry, Tool, ToolOutput
from lime_star.tool_runtime.run_command import run_command
from lime_star.tool_runtime.write_file import write_file


def default_tools(workdir: Path) -> Registry:
    """正式命令的工具集：两个只读工具，两个要先经用户批准的危险工具。"""
    return Registry(
        [read_file(workdir), list_dir(workdir), write_file(workdir), run_command(workdir)]
    )


__all__ = [
    "REJECTED",
    "Granted",
    "Registry",
    "Tool",
    "ToolOutput",
    "default_tools",
    "inside",
    "list_dir",
    "read_file",
    "run_command",
    "write_file",
]
