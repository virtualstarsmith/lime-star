"""终端入口（Surface）：参数解析、终端投影、向用户发起审批。

边界以 internal/aiprompts/architecture.md 为准：这里不做业务编排，
不拼模型请求，也不绕过 app 回合入口去调用循环、模型或工具。
"""
