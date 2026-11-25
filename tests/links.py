"""测试共用：建一个指向目录的链接。

Windows 上用目录联接，不需要管理员权限，Path.resolve() 会跟踪它；其他平台用符号链接。
"""

import sys
from pathlib import Path


def link_directory(target: Path, link: Path) -> None:
    """让 link 指向 target。link 必须还不存在。"""
    if sys.platform == "win32":
        import _winapi

        _winapi.CreateJunction(str(target), str(link))
    else:
        link.symlink_to(target, target_is_directory=True)
