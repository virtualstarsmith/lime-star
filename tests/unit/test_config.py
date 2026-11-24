"""load_config 的单元测试：配置从哪里来、缺项和不合法的值怎样被拒绝（R4.1、R4.2，决策 D-01）。"""

from pathlib import Path

import pytest

from lime_star.model_provider import (
    API_KEY_VAR,
    BASE_URL_VAR,
    MODEL_VAR,
    ConfigError,
    ModelConfig,
    load_config,
)

URL = "https://api.example.com/v1"
KEY = "test-key-0123456789"
MODEL = "model-a"
FULL = {BASE_URL_VAR: URL, API_KEY_VAR: KEY, MODEL_VAR: MODEL}


def write_env_file(workdir: Path, text: str) -> None:
    workdir.joinpath(".env").write_bytes(text.encode("utf-8"))


def test_reads_three_variables_from_env(tmp_path: Path) -> None:
    """R4.1：三个变量都在环境里时直接读取，工作目录里不需要 .env。"""
    assert load_config(FULL, tmp_path) == ModelConfig(URL, KEY, MODEL)


def test_env_file_fills_only_the_missing_items(tmp_path: Path) -> None:
    """决策 D-01：环境变量优先，缺项才读工作目录下的 .env；成对引号会被去掉。"""
    write_env_file(
        tmp_path,
        f"# 注释行\n"
        "OTHER=x\n"
        f"{BASE_URL_VAR}=https://from-env-file.invalid\n"
        f'{API_KEY_VAR}="{KEY}"\n'
        f"{MODEL_VAR}='{MODEL}'\n",
    )
    assert load_config({BASE_URL_VAR: URL}, tmp_path) == ModelConfig(URL, KEY, MODEL)


def test_env_file_is_not_read_when_nothing_is_missing(tmp_path: Path) -> None:
    """决策 D-01 的另一面：三个变量齐全时不去读 .env，哪怕它无法解析。"""
    write_env_file(tmp_path, "这一行无法解析\n")
    assert load_config(FULL, tmp_path) == ModelConfig(URL, KEY, MODEL)


def test_missing_items_are_all_named(tmp_path: Path) -> None:
    """R4.2：缺哪几个变量就点名哪几个，已经有的不点名。"""
    with pytest.raises(ConfigError) as excinfo:
        load_config({BASE_URL_VAR: URL}, tmp_path)
    assert excinfo.value.message.startswith(f"缺少模型配置：{API_KEY_VAR}、{MODEL_VAR}。")
    assert BASE_URL_VAR not in excinfo.value.message


def test_missing_without_any_source_lists_three_in_order(tmp_path: Path) -> None:
    with pytest.raises(ConfigError) as excinfo:
        load_config({}, tmp_path)
    assert excinfo.value.message.startswith(
        f"缺少模型配置：{BASE_URL_VAR}、{API_KEY_VAR}、{MODEL_VAR}。"
    )


def test_blank_value_counts_as_missing(tmp_path: Path) -> None:
    with pytest.raises(ConfigError) as excinfo:
        load_config({BASE_URL_VAR: "  ", API_KEY_VAR: KEY, MODEL_VAR: MODEL}, tmp_path)
    assert excinfo.value.message.startswith(f"缺少模型配置：{BASE_URL_VAR}。")


def test_env_file_is_read_only_from_the_workdir(tmp_path: Path) -> None:
    """决策 D-01：只读工作目录下的那一个 .env，上一级目录里的不算。"""
    parent = tmp_path / "parent"
    workdir = parent / "project"
    workdir.mkdir(parents=True)
    write_env_file(parent, f"{BASE_URL_VAR}={URL}\n{API_KEY_VAR}={KEY}\n{MODEL_VAR}={MODEL}\n")
    with pytest.raises(ConfigError):
        load_config({}, workdir)


def test_unparsable_env_file_line_is_reported_by_number_only(tmp_path: Path) -> None:
    """出错的行只报行号，不回显那一行的内容。"""
    detail = "DETAIL-MARKER-0123456789"
    write_env_file(tmp_path, f"{API_KEY_VAR}={KEY}\n这条无法解析 {detail}\n")
    with pytest.raises(ConfigError) as excinfo:
        load_config({}, tmp_path)
    assert excinfo.value.message == ".env 第 2 行无法解析：应当写成 NAME=VALUE。"
    assert detail not in excinfo.value.message


def test_env_file_may_use_crlf_and_start_with_bom(tmp_path: Path) -> None:
    """Windows 上的编辑器常写出带 BOM、以 CRLF 换行的文件。"""
    text = f"\ufeff{BASE_URL_VAR}={URL}\r\n{API_KEY_VAR}={KEY}\r\n{MODEL_VAR}={MODEL}\r\n"
    (tmp_path / ".env").write_bytes(text.encode("utf-8"))
    assert load_config({}, tmp_path) == ModelConfig(URL, KEY, MODEL)


def test_env_file_that_is_not_utf8_is_rejected(tmp_path: Path) -> None:
    (tmp_path / ".env").write_bytes(b"\xff\xfe\x00\x00")
    with pytest.raises(ConfigError) as excinfo:
        load_config({}, tmp_path)
    assert excinfo.value.message == ".env 不是合法的 UTF-8 文件。"


@pytest.mark.parametrize(
    "url",
    [
        "ftp://DETAILMARKER.invalid/v1",
        "DETAILMARKER.invalid/v1",
        "http://",
        "https://[::1",
        "not a url",
    ],
)
def test_invalid_base_url_is_rejected_without_echo(tmp_path: Path, url: str) -> None:
    """不合法的地址以配置错误拒绝；消息里只有变量名和示例，不回显用户填的值。"""
    with pytest.raises(ConfigError) as excinfo:
        load_config({BASE_URL_VAR: url, API_KEY_VAR: KEY, MODEL_VAR: MODEL}, tmp_path)
    assert excinfo.value.message == (
        f"{BASE_URL_VAR} 必须是 http 或 https 地址，例如 https://api.example.com/v1。"
    )


def test_loopback_http_address_is_accepted(tmp_path: Path) -> None:
    config = load_config({**FULL, BASE_URL_VAR: "http://127.0.0.1:8000/v1"}, tmp_path)
    assert config.base_url == "http://127.0.0.1:8000/v1"


@pytest.mark.parametrize("key", ["ab cd", "密钥", "key\ttab", "key\nline"])
def test_key_with_space_or_non_ascii_is_rejected_without_echo(tmp_path: Path, key: str) -> None:
    with pytest.raises(ConfigError) as excinfo:
        load_config({BASE_URL_VAR: URL, API_KEY_VAR: key, MODEL_VAR: MODEL}, tmp_path)
    assert excinfo.value.message == f"{API_KEY_VAR} 含有空白或不可打印的字符。"
    assert key not in excinfo.value.message


def test_key_with_printable_ascii_symbols_is_accepted(tmp_path: Path) -> None:
    key = "a-b_c.d/e+f=g:,h"
    assert load_config({**FULL, API_KEY_VAR: key}, tmp_path).api_key == key
