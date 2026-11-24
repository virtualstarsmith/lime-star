"""回合循环（纯核心）：循环状态机与回合编排。

边界以 internal/aiprompts/architecture.md 为准：这里不做模型线路细节、工具执行、终端输出，
也不依赖具体的模型客户端、工具实现或存储实现，只依赖 protocol。
"""

from lime_star.agent_runtime.loop import MAX_REQUESTS, run_turn

__all__ = ["MAX_REQUESTS", "run_turn"]
