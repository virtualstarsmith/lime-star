"""密钥守卫在真实进程里的回归：干净的仓库通过，违规被报出（R4.5、R4.6，决策 D-02）。

每条用例在临时目录里建一个真实的 Git 仓库，再运行 scripts/security/check-secrets.mjs。
样例密钥在运行时拼出来，不写成完整的字面量，免得守卫扫到这个文件自己。
"""

import os
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "security" / "check-secrets.mjs"
# 临时仓库不受本机 Git 全局配置影响：不签名、不挂钩子。
GIT_ENV = {**os.environ, "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull}


def run_guard(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["node", str(SCRIPT), "--root", str(root)],
        cwd=REPO,
        capture_output=True,
        encoding="utf-8",
        timeout=60,
        check=False,
    )


def git(repo: Path, *args: str) -> None:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        env=GIT_ENV,
        capture_output=True,
        encoding="utf-8",
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, f"场景：准备临时仓库；git {' '.join(args)} 失败：{result.stderr}"


def commit(repo: Path) -> None:
    git(repo, "add", "-A")
    git(
        repo,
        "-c",
        "user.name=tests",
        "-c",
        "user.email=tests@example.invalid",
        "-c",
        "commit.gpgsign=false",
        "commit",
        "-q",
        "-m",
        "step",
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """一个干净的临时仓库：.env 已被忽略，带占位值的 .env.example 被跟踪。"""
    tmp_path.joinpath(".gitignore").write_text(".env\n", encoding="utf-8")
    tmp_path.joinpath(".env.example").write_text("LIME_STAR_API_KEY=<你的密钥>\n", encoding="utf-8")
    tmp_path.joinpath("README.md").write_text("# 测试仓库\n", encoding="utf-8")
    git(tmp_path, "init", "-q")
    commit(tmp_path)
    return tmp_path


def test_clean_repository_passes(repo: Path) -> None:
    """R4.4-S1：只有变量名和占位值的 .env.example 可以被跟踪。"""
    result = run_guard(repo)
    assert (result.returncode, result.stderr) == (0, "")
    assert "密钥守卫通过。" in result.stdout


def test_this_repository_passes_and_ignores_env() -> None:
    """R4.5-S1：在本仓库执行 git check-ignore .env，它被报告为已忽略；守卫本身也通过。"""
    ignored = subprocess.run(
        ["git", "check-ignore", ".env"],
        cwd=REPO,
        capture_output=True,
        encoding="utf-8",
        timeout=60,
        check=False,
    )
    assert (ignored.returncode, ignored.stdout.strip()) == (0, ".env")
    assert run_guard(REPO).returncode == 0


def test_env_that_is_not_ignored_is_reported(repo: Path) -> None:
    """R4.5：.env 不在忽略规则里就是违规。"""
    repo.joinpath(".gitignore").write_text("node_modules/\n", encoding="utf-8")
    commit(repo)
    result = run_guard(repo)
    assert result.returncode == 1
    assert result.stderr.count("✗") == 1
    assert ".env 没有被 Git 忽略：在 .gitignore 里加入一行 .env" in result.stderr


def test_tracked_env_file_is_reported(repo: Path) -> None:
    """R4.5：被强制加入索引的 .env 是违规，即使忽略规则里有它。"""
    repo.joinpath(".env").write_text("LIME_STAR_API_KEY=placeholder\n", encoding="utf-8")
    git(repo, "add", "-f", ".env")
    result = run_guard(repo)
    assert result.returncode == 1
    assert ".env：密钥文件被 Git 跟踪，用 git rm --cached 移出" in result.stderr


@pytest.mark.parametrize(
    ("key", "rule"),
    [
        ("sk-" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4", "openai-key"),
        ("ghp_" + "a" * 36, "github-token"),
        ("AKIA" + "ABCDEFGHIJ234567", "aws-access-key"),
        ("-----BEGIN " + "PRIVATE KEY-----", "private-key"),
        ('MY_TOKEN = "' + "z" * 30 + '"', "assigned-secret"),
    ],
)
def test_key_in_a_staged_file_is_reported_without_being_echoed(
    repo: Path, key: str, rule: str
) -> None:
    """R4.6-S1：已跟踪文件里出现常见格式的密钥时报错并非零退出；输出里不回显密钥。"""
    repo.joinpath("notes.txt").write_text(f"第一行\n{key}\n", encoding="utf-8")
    git(repo, "add", "notes.txt")
    result = run_guard(repo)
    assert result.returncode == 1
    assert f"notes.txt:2：发现疑似密钥（规则 {rule}）" in result.stderr
    assert key not in result.stdout + result.stderr


def test_key_in_a_committed_file_is_reported(repo: Path) -> None:
    repo.joinpath("notes.txt").write_text("sk-" + "B" * 24 + "\n", encoding="utf-8")
    commit(repo)
    result = run_guard(repo)
    assert result.returncode == 1
    assert "notes.txt:1：发现疑似密钥（规则 openai-key）" in result.stderr


def test_ignored_env_file_may_hold_a_key(repo: Path) -> None:
    """决策 D-01：密钥就该放在被忽略的 .env 里，守卫不扫它。"""
    repo.joinpath(".env").write_text("LIME_STAR_API_KEY=sk-" + "c" * 30 + "\n", encoding="utf-8")
    assert run_guard(repo).returncode == 0


def test_running_outside_a_git_repository_fails_clearly(tmp_path: Path) -> None:
    result = run_guard(tmp_path / "empty")
    assert result.returncode == 2
    assert "不是 Git 仓库" in result.stderr
