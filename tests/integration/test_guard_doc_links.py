"""文档链接守卫在真实进程里的回归（技术债 CCD-001）。

退出条件要求两条：带目录的错误路径会报违规；裸文件名可以按文件名全树查找。
每条用例在临时目录里搭一个最小的文档树，再运行 scripts/check-doc-links.mjs。
"""

import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "check-doc-links.mjs"
REAL = "# 真实文件\n"


def run_guard(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["node", str(SCRIPT), "--root", str(root)],
        cwd=REPO,
        capture_output=True,
        encoding="utf-8",
        timeout=60,
        check=False,
    )


def make_tree(base: Path, files: dict[str, str]) -> Path:
    for relative, text in files.items():
        path = base / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return base


def test_wrong_path_with_a_directory_is_a_violation(tmp_path: Path) -> None:
    """带目录的引用写错了目录：即使同名文件在别处，也按路径找不到，报违规并提示同名文件的位置。"""
    root = make_tree(
        tmp_path,
        {"internal/x/doc.md": "见 `y/real.md`。\n", "internal/y/real.md": REAL},
    )
    result = run_guard(root)
    assert result.returncode == 1
    assert "doc.md -> y/real.md（按路径未找到；同名文件在 internal/y/real.md）" in result.stderr


def test_bare_file_name_is_looked_up_in_the_whole_tree(tmp_path: Path) -> None:
    """裸文件名不带目录：可以在全树按文件名找到，通过。"""
    root = make_tree(
        tmp_path, {"internal/x/doc.md": "见 `real.md`。\n", "internal/y/real.md": REAL}
    )
    result = run_guard(root)
    assert (result.returncode, result.stderr) == (0, "")


def test_correct_relative_path_passes(tmp_path: Path) -> None:
    root = make_tree(
        tmp_path, {"internal/x/doc.md": "见 `../y/real.md`。\n", "internal/y/real.md": REAL}
    )
    assert run_guard(root).returncode == 0


def test_path_from_the_repository_root_passes(tmp_path: Path) -> None:
    root = make_tree(
        tmp_path, {"internal/x/doc.md": "见 `internal/y/real.md`。\n", "internal/y/real.md": REAL}
    )
    assert run_guard(root).returncode == 0


def test_reference_escaping_the_repository_is_a_violation(tmp_path: Path) -> None:
    """引用解析到仓库之外：即使那个文件存在，也不算找到。"""
    base = tmp_path / "base"
    root = base / "repo"
    make_tree(base, {"outside.md": REAL})
    make_tree(root, {"internal/x/doc.md": "见 `../../../outside.md`。\n"})
    result = run_guard(root)
    assert result.returncode == 1
    assert "doc.md -> ../../../outside.md" in result.stderr


def test_missing_bare_file_name_is_a_violation(tmp_path: Path) -> None:
    root = make_tree(tmp_path, {"internal/x/doc.md": "见 `nowhere.md`。\n"})
    result = run_guard(root)
    assert result.returncode == 1
    assert "doc.md -> nowhere.md" in result.stderr


def test_clean_tree_passes(tmp_path: Path) -> None:
    root = make_tree(tmp_path, {"AGENTS.md": "没有引用。\n", "internal/a/b.md": "正文\n"})
    result = run_guard(root)
    assert (result.returncode, result.stderr) == (0, "")


def test_this_repository_passes() -> None:
    assert run_guard(REPO).returncode == 0
