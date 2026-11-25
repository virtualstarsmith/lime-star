"""工作目录边界（需求 R8.1 到 R8.3）：文件工具只能访问工作目录里面的路径。

run_command 不受它约束，它的唯一安全边界是审批（R8.4，决策 D-22）。
"""

import os
from pathlib import Path


def inside(workdir: Path, path: str) -> Path | None:
    """把 path 当作相对工作目录的路径，返回解析后的真实位置；落在工作目录之外时返回 None。

    判断用真实位置：展开 ..，跟踪符号链接和目录联接。Windows 上比较时不区分大小写，
    所以路径里目录名的大小写与实际不同也算同一个目录。
    """
    root = _key(workdir.resolve())
    resolved = (workdir / path).resolve()
    target = _key(resolved)
    boundary = root if root.endswith(os.sep) else root + os.sep
    if target == root or target.startswith(boundary):
        return resolved
    return None


def _key(path: Path) -> str:
    return os.path.normcase(str(path))
