"""OpenAI 兼容接口的客户端：由模型配置构造。"""

from openai import OpenAI

from lime_star.model_provider.config import ModelConfig


def open_client(config: ModelConfig) -> OpenAI:
    """关掉 SDK 的自动重试（决策 D-11）。超时沿用 SDK 的默认值：连接 5 秒，读 600 秒。"""
    return OpenAI(base_url=config.base_url, api_key=config.api_key, max_retries=0)
