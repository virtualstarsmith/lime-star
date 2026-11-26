"""write_file：把内容原样写入工作目录里的一个文件（需求 R7.1、R7.2）。

文件不存在时新建，存在时覆盖，不做换行符转换；父目录不存在时出错，不创建目录（决策 D-15）。
这是危险操作（决策 D-19）：执行前必须经用户批准（R7.6），批准提示显示目标路径、新建还是覆盖、
全部要写入的内容（R7.7）。目标越界时直接拒绝，不进入批准提示（R8.2-S2）。

写入分两步：先写同目录下的临时文件，再替换目标文件。被打断或写失败时目标文件保持原样，
所以被打断的写入说"没有执行"是属实的（R12.5）。
"""

import os
from collections.abc import Mapping
from pathlib import Path
from typing import cast

from lime_star.protocol import Json
from lime_star.tool_runtime.paths import inside
from lime_star.tool_runtime.registry import Tool, ToolOutput

NAME = "write_file"

DESCRIPTION = (
    "把内容原样写入工作目录里的一个文件：文件不存在时新建，存在时覆盖，不做换行符转换。"
    "父目录必须已经存在，不会自动创建。"
    "这是危险操作：执行前需要用户批准，用户会看到路径和全部要写入的内容。"
)
PARAMETERS: dict[str, Json] = {
    "type": "object",
    "properties": {
        "path": {"type": "string", "description": "相对工作目录的文件路径。"},
        "content": {"type": "string", "description": "要写入的全部内容，原样写入。"},
    },
    "required": ["path", "content"],
}


def write_file(workdir: Path) -> Tool:
    """造一个只能写 workdir 里面文件的 write_file 工具。"""

    def danger(arguments: Mapping[str, Json]) -> str | ToolOutput:
        """批准之前先检查目标，再给出给用户看的说明（R7.7）。"""
        found = _locate(workdir, arguments)
        if isinstance(found, ToolOutput):
            return found
        target, shown = found
        content = cast(str, arguments["content"])
        return (
            f"请求批准 write_file：写入 {shown}（{_state(target)}）。要写入的内容：\n"
            f"{_closed(content)}"
            f"----- 内容结束，共 {len(content.splitlines())} 行 -----"
        )

    def run(arguments: Mapping[str, Json]) -> ToolOutput:
        found = _locate(workdir, arguments)
        if isinstance(found, ToolOutput):
            return found
        target, shown = found
        # 参数模式已经保证 content 是一个字符串。
        content = cast(str, arguments["content"])
        state = _state(target)
        lines = len(content.splitlines())
        temp = target.with_name(f".{target.name}.tmp")
        try:
            temp.write_bytes(content.encode("utf-8"))
            os.replace(temp, target)
        except OSError as exc:
            _discard(temp)
            return ToolOutput(f"无法写入 {shown}（{type(exc).__name__}）。", error=True)
        except BaseException:
            # 被打断：目标文件还是原样，只可能留下临时文件。清掉它，再让中断向上传。
            _discard(temp)
            raise
        return ToolOutput(
            f"已写入 {shown}（{state}，{lines} 行）。",
            summary=f"已写入 {shown}，{state}，{lines} 行",
        )

    return Tool(name=NAME, description=DESCRIPTION, parameters=PARAMETERS, run=run, danger=danger)


def _locate(workdir: Path, arguments: Mapping[str, Json]) -> tuple[Path, str] | ToolOutput:
    """解析目标路径。越界、是目录、父目录不存在时给出结果：这次调用不会执行，也不必批准。"""
    # 参数模式已经保证 path 是一个字符串。
    shown = cast(str, arguments["path"])
    target = inside(workdir, shown)
    if target is None:
        return ToolOutput(f"超出工作目录：{shown}。", error=True)
    if target.is_dir():
        return ToolOutput(f"这是一个目录，不能写入：{shown}。", error=True)
    if not target.parent.is_dir():
        return ToolOutput(f"父目录不存在，没有写入：{shown}。", error=True)
    return target, shown


def _state(target: Path) -> str:
    return "覆盖已有文件" if target.exists() else "新建文件"


def _closed(content: str) -> str:
    """说明里的内容以换行收尾，后面一行的结束标记才另起一行。"""
    return content if not content or content.endswith("\n") else content + "\n"


def _discard(temp: Path) -> None:
    try:
        temp.unlink(missing_ok=True)
    except OSError:
        pass  # 临时文件已经不在，或者删不掉；后者会在目录里留下一个点开头的临时文件。
