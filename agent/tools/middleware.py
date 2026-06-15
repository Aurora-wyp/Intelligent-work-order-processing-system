from langchain.agents import AgentState
from langchain.agents.middleware import wrap_tool_call, before_model
from langgraph.prebuilt.tool_node import ToolCallRequest
from typing import Callable
from langgraph.runtime import Runtime
from utils.logger_handler import logger
from langchain_core.messages import ToolMessage
from langgraph.types import Command


@wrap_tool_call
def monitor_tool(
    request: ToolCallRequest,
    handler: Callable[[ToolCallRequest], ToolMessage | Command],
) -> ToolMessage | Command:
    """工具调用监控中间件：记录每次工具调用的名称、参数和结果。"""
    logger.info(f"[tool monitor] 执行工具：{request.tool_call['name']}")
    logger.info(f"[tool monitor] 传入参数：{request.tool_call['args']}")

    try:
        result = handler(request)
        logger.info(f"[tool monitor] 工具 {request.tool_call['name']} 调用成功")
        return result
    except Exception as e:
        logger.error(f"[tool monitor] 工具 {request.tool_call['name']} 调用失败，原因：{str(e)}")
        raise e


@before_model
def log_before_model(
    state: AgentState,
    runtime: Runtime
):
    """模型调用前日志中间件：记录即将发送给模型的消息数量。"""
    logger.info(f"[log_before_model] 即将调用模型，带有 {len(state['messages'])} 条消息")
    logger.debug(f"[log_before_model] {type(state['messages'][-1]).__name__} | {state['messages'][-1].content}")
    return None
